"""The agent loop: LLM decides -> we run tools -> LLM sees results -> repeat until it answers.

PHASE 1: the whole run is wrapped in an AGENT span. Everything that happens inside it
(Groq LLM calls, tool calls, retrieval) becomes a child span, so one question = one trace tree.
Errors are still hidden from the user, but now they're recorded on the trace.
"""
from dataclasses import dataclass, field

from openinference.instrumentation import using_attributes
from openinference.semconv.trace import SpanAttributes

from snackbot import config
from snackbot.llm import chat
from snackbot.prompts import PROMPT_VERSION, SYSTEM_PROMPT, prompt_variables, system_prompt
from snackbot.tools import TOOL_SCHEMAS, run_tool
from snackbot.tracing import SpanKind, ids, mark_error, set_output, start_span


@dataclass
class AgentResult:
    answer: str
    tools_used: list[str] = field(default_factory=list)
    trace_id: str | None = None   # PHASE 1: lets you find this exact run in Phoenix
    span_id: str | None = None    # PHASE 2 will use this to attach user feedback to the trace


class SnackBot:
    def __init__(self, model: str | None = None):
        self.model = model or config.GROQ_MODEL

    def answer(self, question: str, history: list[dict] | None = None, *,
               session_id: str | None = None, user_id: str | None = None,
               metadata: dict | None = None, tags: list[str] | None = None) -> AgentResult:
        """history = earlier turns as [{"role": "user"|"assistant", "content": str}, ...]."""

        # PHASE 1: `using_attributes` puts these values into the OpenTelemetry *context*.
        # Every span created inside this block, including Groq's auto-instrumented LLM spans,
        # automatically picks them up. That's how Phoenix groups traces into sessions.
        with using_attributes(
            session_id=session_id or "",
            user_id=user_id or "",
            metadata={"model": self.model, "prompt_version": PROMPT_VERSION, **(metadata or {})},
            tags=tags or [],
            prompt_template=SYSTEM_PROMPT,
            prompt_template_version=PROMPT_VERSION,
            prompt_template_variables=prompt_variables(),
        ), start_span("SnackBot.answer", SpanKind.AGENT, input_value=question, **{
            SpanAttributes.AGENT_NAME: "SnackBot",
            "agent.history_turns": len(history or []) // 2,
        }) as span:
            result = self._run(question, history, span)
            result.trace_id, result.span_id = ids(span)
            set_output(span, result.answer)
            span.set_attribute("agent.tools_used", result.tools_used)
            return result

    def _run(self, question, history, span) -> AgentResult:
        messages = [{"role": "system", "content": system_prompt()}]
        messages += history or []
        messages.append({"role": "user", "content": question})
        tools_used: list[str] = []

        try:
            for step in range(1, config.MAX_AGENT_STEPS + 1):
                span.set_attribute("agent.steps", step)
                response = chat(messages, tools=TOOL_SCHEMAS, model=self.model)  # auto-traced LLM span
                msg = response.choices[0].message

                if not msg.tool_calls:  # the LLM produced a final answer
                    return AgentResult(msg.content or "", tools_used)

                # Keep the assistant's tool-call request in the conversation, then add each result.
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {"id": tc.id, "type": "function",
                         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in msg.tool_calls
                    ],
                })
                for tc in msg.tool_calls:
                    tools_used.append(tc.function.name)
                    result = run_tool(tc.function.name, tc.function.arguments)  # TOOL span
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

            mark_error(span, f"Hit MAX_AGENT_STEPS={config.MAX_AGENT_STEPS} without a final answer")
            return AgentResult("Sorry, I couldn't finish answering that (too many steps).", tools_used)

        except Exception as exc:  # noqa: BLE001
            # The user still sees a polite message, but the real error is now on the trace.
            mark_error(span, exc)
            return AgentResult("Sorry, something went wrong. Please try again.", tools_used)
