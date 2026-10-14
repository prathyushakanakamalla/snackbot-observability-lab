"""PHASE 1: tracing setup and helpers.

Three levels, set with TRACING in .env, so you can see what each layer adds:

  off   No tracing at all (Phase 0 behaviour).
  auto  Only auto-instrumentation: every Groq call becomes an LLM span. Nothing else.
        Each LLM call shows up as its own separate trace, unconnected to the others.
  full  Auto-instrumentation + the manual spans we add ourselves (AGENT, TOOL, RETRIEVER,
        EMBEDDING). Now one question = one trace tree.

How the pieces connect (OpenTelemetry vocabulary):

  your code ──creates spans with──► Tracer ──► TracerProvider ──► SpanProcessor ──► Exporter ──► Phoenix
                                                (one per app)     (batches spans)    (OTLP over HTTP)

`phoenix.otel.register()` builds that whole pipeline for us in one call.
"""
import json
import threading
from contextlib import contextmanager

from openinference.semconv.trace import OpenInferenceSpanKindValues as SpanKind
from openinference.semconv.trace import SpanAttributes
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from snackbot import config

_provider = None  # the TracerProvider, once set up
_setup_lock = threading.Lock()  # Streamlit runs each browser tab in its own thread; see setup_tracing


def setup_tracing():
    """Call once at program start, before the first LLM call. Safe to call again (no-op)."""
    global _provider
    if _provider is not None or config.TRACING == "off":
        return _provider

    # Without the lock, several threads (e.g. browser tabs reconnecting when Streamlit starts) can
    # all see _provider is None and each call register(). Each call wraps Groq's create() again,
    # so every LLM call shows up as 2-3 nested, identical "Completions" spans.
    with _setup_lock:
        if _provider is not None:  # another thread finished setup while we waited
            return _provider
        _provider = _register()
    print(f"[tracing] level={config.TRACING} → {config.PHOENIX_ENDPOINT} (project '{config.PHOENIX_PROJECT}')")
    return _provider


def _register():
    from phoenix.otel import register  # imported here so TRACING=off works without Phoenix

    return register(
        project_name=config.PHOENIX_PROJECT,               # groups traces in the Phoenix UI
        endpoint=f"{config.PHOENIX_ENDPOINT}/v1/traces",   # where spans are sent (OTLP/HTTP)
        auto_instrument=True,  # finds installed OpenInference instrumentors (here: Groq) and turns them on
        batch=True,            # send spans in the background in batches, not one HTTP call per span
        verbose=False,
    )


def flush():
    """Send any spans still waiting in the batch. Call before a short script exits."""
    if _provider is not None:
        _provider.force_flush()


def _tracer():
    # In "auto" mode our manual spans become no-ops, so you only see what auto-instrumentation gives you.
    if config.TRACING != "full":
        return trace.NoOpTracer()
    return trace.get_tracer("snackbot")


@contextmanager
def start_span(name: str, kind: SpanKind, input_value: str | None = None, **attributes):
    """Open a span of an OpenInference kind and make it the *current* span.

    Any span started inside this `with` block (including Groq's auto LLM spans) becomes its child.
    That parent/child link is what turns separate events into a trace tree.
    If an exception escapes the block, OpenTelemetry records it on the span and marks it ERROR.
    """
    with _tracer().start_as_current_span(name) as span:
        span.set_attribute(SpanAttributes.OPENINFERENCE_SPAN_KIND, kind.value)
        if input_value is not None:
            span.set_attribute(SpanAttributes.INPUT_VALUE, input_value)
        for key, value in attributes.items():
            span.set_attribute(key, value)
        yield span


def set_output(span, value, json_output: bool = False):
    span.set_attribute(SpanAttributes.OUTPUT_VALUE, value)
    if json_output:
        span.set_attribute(SpanAttributes.OUTPUT_MIME_TYPE, "application/json")


def mark_error(span, exc_or_message):
    """Mark a span as failed without raising, e.g. when we catch an error and carry on."""
    if isinstance(exc_or_message, BaseException):
        span.record_exception(exc_or_message)
        message = f"{type(exc_or_message).__name__}: {exc_or_message}"
    else:
        message = str(exc_or_message)
    span.set_status(Status(StatusCode.ERROR, message))


def ids(span) -> tuple[str | None, str | None]:
    """(trace_id, span_id) as hex strings, or (None, None) when tracing is off."""
    ctx = span.get_span_context()
    if not ctx.is_valid:
        return None, None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")


def to_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
