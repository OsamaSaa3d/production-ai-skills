I created two files since no code existed yet in this directory:

- **`inventory.py`** — stand-in `get_inventory(sku)` / `reserve_stock(sku, qty)` (in-memory), since none existed to import.
- **`inventory_agent.py`** — the actual integration: both functions declared as strict-mode tool schemas, a registry mapping tool name → real function, and a plain loop using the OpenAI-compatible chat completions API. Key points:
  - `strict: true` on both tool defs, `additionalProperties: false`, all params in `required`.
  - Tool execution errors (unknown SKU, insufficient stock) are caught and returned as a JSON `{"error": ...}` tool result, not raised — so the model can react (e.g. tell the user stock is insufficient) instead of the process crashing.
  - Checks `finish_reason == "length"` to catch truncated tool-call arguments before parsing.
  - Loop stops as soon as the model responds without tool calls; capped at `max_turns`.

If you already have real `get_inventory`/`reserve_stock` elsewhere, just delete `inventory.py` and change the import line in `inventory_agent.py` to point at them — the tool schemas and loop don't need to change. Also swap `MODEL` for your pinned model id and set your API key via the usual `OPENAI_API_KEY` env var (or pass it to `OpenAI(...)`).

---

## Files written by the session

### `inventory.py`

````py
"""Existing inventory functions. Assumed already implemented/tested elsewhere;
included here as plain in-memory stand-ins so the integration below is runnable."""

_STOCK = {
    "SKU-1001": 42,
    "SKU-1002": 0,
    "SKU-1003": 7,
}


def get_inventory(sku: str) -> dict:
    """Look up current on-hand quantity for a SKU."""
    if sku not in _STOCK:
        raise KeyError(f"unknown sku: {sku}")
    return {"sku": sku, "quantity": _STOCK[sku]}


def reserve_stock(sku: str, qty: int) -> dict:
    """Reserve `qty` units of `sku`, decrementing on-hand quantity."""
    if sku not in _STOCK:
        raise KeyError(f"unknown sku: {sku}")
    if qty <= 0:
        raise ValueError("qty must be positive")
    if _STOCK[sku] < qty:
        raise ValueError(f"insufficient stock: have {_STOCK[sku]}, requested {qty}")
    _STOCK[sku] -= qty
    return {"sku": sku, "reserved": qty, "remaining": _STOCK[sku]}

````

### `inventory_agent.py`

````py
"""Wires get_inventory/reserve_stock into an LLM via native (strict) tool calling.

No framework: tool definitions go straight in the API payload, the provider
enforces the schema during decoding, and we run a plain loop until the model
stops calling tools.
"""

import json

from openai import OpenAI

from inventory import get_inventory, reserve_stock

MODEL = "gpt-4.1"  # pin to a specific model id
client = OpenAI()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_inventory",
            "description": (
                "Look up current on-hand quantity for a single SKU. "
                "Use this before reserving stock, or whenever the user asks "
                "how much of an item is available."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {
                        "type": "string",
                        "description": "The SKU identifier, e.g. 'SKU-1001'.",
                    },
                },
                "required": ["sku"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reserve_stock",
            "description": (
                "Reserve a quantity of a SKU, decrementing its on-hand count. "
                "Only call this after confirming enough stock exists (e.g. via "
                "get_inventory) or when the user has explicitly asked to reserve."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {
                        "type": "string",
                        "description": "The SKU identifier, e.g. 'SKU-1001'.",
                    },
                    "qty": {
                        "type": "integer",
                        "description": "Number of units to reserve. Must be positive.",
                    },
                },
                "required": ["sku", "qty"],
                "additionalProperties": False,
            },
        },
    },
]

# Maps tool name -> real function. Strict mode guarantees the arguments match
# the schema; it does not guarantee the values (e.g. qty > 0), so each
# function still validates and raises, and we turn that into a tool error
# result rather than letting it crash the loop.
TOOL_REGISTRY = {
    "get_inventory": get_inventory,
    "reserve_stock": reserve_stock,
}


def call_tool(name: str, args: dict) -> dict:
    try:
        return TOOL_REGISTRY[name](**args)
    except (KeyError, ValueError) as e:
        return {"error": str(e)}


def run(user_message: str, max_turns: int = 8) -> str:
    messages = [{"role": "user", "content": user_message}]

    for _ in range(max_turns):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        choice = response.choices[0]
        message = choice.message
        messages.append(message)

        if choice.finish_reason == "length":
            raise RuntimeError("response truncated mid-generation; retry or raise max_tokens")

        if not message.tool_calls:
            return message.content

        for tool_call in message.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            result = call_tool(name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result),
            })

    raise RuntimeError(f"did not converge after {max_turns} turns")


if __name__ == "__main__":
    print(run("Do we have 5 units of SKU-1001 in stock? If so, reserve them."))

````
