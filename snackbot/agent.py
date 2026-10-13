"""The agent loop: LLM decides -> we run tools -> LLM sees results -> repeat until it answers.

PHASE 0 NOTE: on purpose, this file records almost nothing about what happens inside a run.
If an answer is wrong you cannot tell whether retrieval, a tool, or the LLM was at fault.
That blind spot is exactly what Phase 1 (tracing) fixes.
"""
from dataclasses import dataclass, field

from snackbot import config
from snackbot.llm import chat
from snackbot.prompts import system_prompt
from snackbot.tools import TOOL_SCHEMAS, run_tool


@dataclass
class AgentResult:
    answer: str
    tools_used: list[str] = field(default_factory=list)  # just tool names: deliberately thin


class SnackBot:
    def __init__(self, model: str | None = None):
        self.model = model or config.GROQ_MODEL

    def answer(self, question: str, history: list[dict] | None = None) -> AgentResult:
        """history = earlier turns as [{"role": "user"|"assistant", "content": str}, ...]."""
        messages = [{"role": "system", "content": system_prompt()}]
        messages += history or []
        messages.append({"role": "user", "content": question})
        tools_used: list[str] = []

        try:
            for _ in range(config.MAX_AGENT_STEPS):
                response = chat(messages, tools=TOOL_SCHEMAS, model=self.model)
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
                    result = run_tool(tc.function.name, tc.function.arguments)
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

            return AgentResult("Sorry, I couldn't finish answering that (too many steps).", tools_used)

        except Exception:  # noqa: BLE001 - PHASE 0: errors are swallowed. Painful on purpose.
            return AgentResult("Sorry, something went wrong. Please try again.", tools_used)
