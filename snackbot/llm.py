"""Thin wrapper around the Groq chat API, with retries for the free tier's rate limits."""
from functools import lru_cache

import groq
from groq import Groq
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from snackbot import config


@lru_cache(maxsize=1)
def client() -> Groq:
    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set. Copy .env.example to .env and add your key.")
    return Groq(api_key=config.GROQ_API_KEY)


@retry(
    retry=retry_if_exception_type((groq.RateLimitError, groq.APIConnectionError, groq.InternalServerError)),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
def chat(messages: list[dict], tools: list[dict] | None = None, model: str | None = None,
         temperature: float | None = None):
    """Call Groq chat completions. Returns the raw response (message is in .choices[0].message)."""
    kwargs = dict(
        model=model or config.GROQ_MODEL,
        messages=messages,
        temperature=config.TEMPERATURE if temperature is None else temperature,
    )
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return client().chat.completions.create(**kwargs)
