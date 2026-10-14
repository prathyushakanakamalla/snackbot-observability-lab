"""The agent's tools: their JSON schemas (what the LLM sees) and their Python implementations."""
import ast
import difflib
import json
import operator
from functools import lru_cache

from openinference.semconv.trace import SpanAttributes

from snackbot import config
from snackbot.retriever import retrieve
from snackbot.tracing import SpanKind, mark_error, set_output, start_span

# ---------------------------------------------------------------------------
# Tool schemas (OpenAI-compatible format, which Groq uses)
# ---------------------------------------------------------------------------
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": (
                "Search Crunchwell Foods internal documents (policies, SOPs, product catalog, promotions, "
                "HR, travel, safety, sustainability). Use for any question about company rules, products or prices."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What to search for."}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_inventory",
            "description": (
                "Look up live inventory (cases on hand and average daily demand) for a product at the "
                "distribution centers: Columbus, Dallas, Fresno, Toronto."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product": {"type": "string", "description": "SKU (e.g. CW-101) or product name."},
                    "warehouse": {"type": "string", "description": "Optional DC name. Omit for all DCs."},
                },
                "required": ["product"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate an arithmetic expression, e.g. '85 * 3 + 7 * 85' or '(38.40 - 33.60) / 38.40 * 100'.",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------
def search_documents(query: str) -> str:
    results = retrieve(query)
    return "\n\n".join(f"[source: {r.doc_id} § {r.section}]\n{r.text}" for r in results)


@lru_cache(maxsize=1)
def _inventory() -> dict:
    return json.loads(config.INVENTORY_PATH.read_text(encoding="utf-8"))


def _find_sku(product: str) -> str | None:
    items = _inventory()["items"]
    key = product.strip().upper()
    if key in items:
        return key
    names = {v["name"].lower(): sku for sku, v in items.items()}
    match = difflib.get_close_matches(product.lower(), list(names), n=1, cutoff=0.5)
    if match:
        return names[match[0]]
    for name, sku in names.items():  # substring fallback, e.g. "zesty lime"
        if product.lower() in name:
            return sku
    return None


def check_inventory(product: str, warehouse: str | None = None) -> str:
    inv = _inventory()
    sku = _find_sku(product)
    if sku is None:
        return json.dumps({"error": f"No product found matching '{product}'."})
    item = inv["items"][sku]
    warehouses = item["warehouses"]
    if warehouse:
        wh = next((w for w in warehouses if w.lower() == warehouse.strip().lower()), None)
        if wh is None:
            return json.dumps({"error": f"Unknown warehouse '{warehouse}'. Options: {list(warehouses)}"})
        warehouses = {wh: warehouses[wh]}
    return json.dumps({"sku": sku, "name": item["name"], "storage": item["storage"],
                       "as_of": inv["as_of"], "unit": inv["unit"], "warehouses": warehouses})


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg, ast.UAdd: operator.pos}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("Only numbers and + - * / ** % ( ) are allowed.")


def calculate(expression: str) -> str:
    try:
        result = _eval(ast.parse(expression.replace(",", ""), mode="eval").body)
        return str(round(result, 6))
    except Exception as exc:  # noqa: BLE001 - return the error text to the LLM
        return f"Error: {exc}"


TOOL_FUNCTIONS = {
    "search_documents": search_documents,
    "check_inventory": check_inventory,
    "calculate": calculate,
}


_DESCRIPTIONS = {s["function"]["name"]: s["function"]["description"] for s in TOOL_SCHEMAS}


def _looks_like_error(result: str) -> str | None:
    """Our tools report problems as text (so the LLM can recover). Detect that for the trace."""
    if result.startswith("Error"):
        return result
    if result.startswith("{") and '"error"' in result:
        return json.loads(result).get("error")
    return None


def run_tool(name: str, arguments_json: str) -> str:
    """Execute a tool call coming from the LLM. Errors are returned as text so the LLM can recover."""
    # PHASE 1: one TOOL span per tool call, with the exact arguments the LLM chose and what came back.
    with start_span(name, SpanKind.TOOL, input_value=arguments_json or "{}", **{
        SpanAttributes.INPUT_MIME_TYPE: "application/json",
        SpanAttributes.TOOL_NAME: name,
        SpanAttributes.TOOL_DESCRIPTION: _DESCRIPTIONS.get(name, ""),
        SpanAttributes.TOOL_PARAMETERS: arguments_json or "{}",
    }) as span:
        if name not in TOOL_FUNCTIONS:
            result = f"Error: unknown tool '{name}'."
        else:
            try:
                args = json.loads(arguments_json or "{}")
                result = TOOL_FUNCTIONS[name](**args)
            except Exception as exc:  # noqa: BLE001
                mark_error(span, exc)  # the exception (with stack trace) is now visible in Phoenix
                result = f"Error running {name}: {exc}"

        set_output(span, result, json_output=(name == "check_inventory"))
        problem = _looks_like_error(result)
        if problem:
            mark_error(span, problem)  # no crash, but the span turns red so you can find it
        return result
