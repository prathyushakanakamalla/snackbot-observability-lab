"""LLM-as-judge evaluations: a second LLM reads the question, answer and context and grades them.

Use an LLM judge when the rule is about *meaning*: "is this answer correct?", "is every claim
supported by the documents?", "did it decline?". Judges are flexible but cost tokens, are slower,
and can be wrong, so we (1) give them narrow yes/no style questions, (2) ask for an explanation,
(3) use a different model family from the app, and (4) check them against human labels
(scripts/judge_agreement.py).

We use two kinds of judge:
  * Built-in Phoenix evaluators, with prompts Arize has tested: faithfulness, refusal, retrieval relevance.
  * A custom judge we write ourselves: answer_correctness, which compares against our reference answer.
"""
from phoenix.evals import LLM, create_classifier
from phoenix.evals.metrics import FaithfulnessEvaluator, RefusalEvaluator, RetrievalRelevanceEvaluator

from snackbot import config


def judge_llm(model: str | None = None) -> LLM:
    """Groq exposes an OpenAI-compatible API, so Phoenix's 'openai' provider works with a different base_url."""
    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set.")
    return LLM(
        provider="openai",
        model=model or config.JUDGE_MODEL,
        base_url=config.GROQ_OPENAI_BASE_URL,
        api_key=config.GROQ_API_KEY,
        # No max_retries here: Phoenix builds the OpenAI client with max_retries=0 itself (passing it
        # again raises "got multiple values for keyword argument") and retries 429s in its own limiter.
        initial_per_second_request_rate=0.5,   # Phoenix's own limiter: start slow, adapt to rate limits
    )


# Our own judge. Reference-based: it compares the answer to the golden reference answer.
CORRECTNESS_TEMPLATE = """You are grading an internal company assistant's answer against a reference answer
written by an expert who read the company's documents.

[Question]
{input}

[Reference answer]
{reference}

[Assistant's answer]
{output}

Grade the assistant's answer:
- "correct": it states the same key facts as the reference (wording may differ; extra helpful detail is fine).
- "partially_correct": it has some key facts right but misses or gets wrong an important one.
- "incorrect": its main claim contradicts the reference, or it fails to answer.
If the reference says the assistant should decline or say it doesn't know, a polite decline is "correct"
and any invented answer is "incorrect"."""


class Judges:
    def __init__(self, model: str | None = None):
        llm = judge_llm(model)
        self.model = model or config.JUDGE_MODEL
        self.correctness = create_classifier(
            name="answer_correctness", prompt_template=CORRECTNESS_TEMPLATE, llm=llm,
            choices={"correct": 1.0, "partially_correct": 0.5, "incorrect": 0.0},
        )
        self.faithfulness = FaithfulnessEvaluator(llm=llm)        # input, output, context
        self.refusal = RefusalEvaluator(llm=llm)                  # input, output
        self.relevance = RetrievalRelevanceEvaluator(llm=llm)     # input, context (one document)

    @staticmethod
    def _one(evaluator, inputs: dict) -> dict:
        """Run one evaluator and turn its Score into our row format. Errors become a row too."""
        try:
            s = evaluator.evaluate(inputs)[0]
            return {"name": s.name, "label": s.label, "score": s.score, "explanation": s.explanation}
        except Exception as exc:  # noqa: BLE001 - one failed judgement shouldn't stop the whole run
            return {"name": evaluator.name, "label": "error", "score": None,
                    "explanation": f"Judge failed: {type(exc).__name__}: {str(exc)[:300]}"}

    def correctness_of(self, question, answer, reference):
        return self._one(self.correctness, {"input": question, "output": answer, "reference": reference})

    def faithfulness_of(self, question, answer, context):
        return self._one(self.faithfulness, {"input": question, "output": answer, "context": context})

    def refusal_of(self, question, answer):
        return self._one(self.refusal, {"input": question, "output": answer})

    def relevance_of(self, question, document):
        return self._one(self.relevance, {"input": question, "context": document})
