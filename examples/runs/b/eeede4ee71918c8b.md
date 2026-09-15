I wrote this to `support_bot.py`. Key points on how it works:

- **Two strict tools**: `lookup_order` (read-only) and `issue_refund` (side-effecting — its description explicitly tells the model to look up the order first and only refund on a clear customer request).
- **The loop** (`run`): each iteration calls the API, appends the assistant turn verbatim, then checks `stop_reason` — `tool_use` executes tools and loops again, anything else returns the final text. `refusal` and `max_tokens` are checked explicitly rather than assumed away.
- **Value validation lives in `issue_refund` itself** (amount > 0, amount ≤ remaining refundable) since JSON Schema `minimum`/`maximum` aren't reliably enforced by strict mode — the tool is the actual guardrail.
- **Tool errors return as data** (`{"error": ...}` + `is_error: True`) instead of raising, so the model can explain the problem to the customer instead of the process crashing.
- **Repeated-call guard**: if the model calls the same tool with identical arguments 3 times, it gets told so in-band instead of looping forever.
- `conversation` is a plain list the caller keeps across turns, so `run()` can be called once per incoming customer message in a real chat loop.

Note: this uses mock in-memory order data (`_ORDERS`) — swap `lookup_order`/`issue_refund` for real calls to your order and payment systems. Since `issue_refund` moves real money, you may also want a human-confirmation step before it executes in production (not added here since you didn't ask for it — flag if you want that gate).

---

## Files written by the session

### `support_bot.py`

````py
"""
Support bot: looks up an order and issues a refund, over multiple turns.

Two tools, native Anthropic tool calling with strict mode. The loop below
appends every assistant turn and every tool result verbatim, checks
stop_reason before doing anything else, and returns tool errors as data
so the model can react to them instead of crashing the process.
"""

import json
from dataclasses import dataclass, field

import anthropic

MODEL = "claude-sonnet-5"
MAX_ITERATIONS = 10

client = anthropic.Anthropic()

# --- Mock backend -----------------------------------------------------
# Replace with real calls to your order-management / payment systems.

_ORDERS = {
    "ORD-1001": {
        "order_id": "ORD-1001",
        "status": "delivered",
        "total_usd": 49.99,
        "refunded_usd": 0.0,
        "items": ["Wireless Mouse"],
    },
    "ORD-1002": {
        "order_id": "ORD-1002",
        "status": "delivered",
        "total_usd": 129.00,
        "refunded_usd": 129.00,
        "items": ["Mechanical Keyboard"],
    },
}


def lookup_order(order_id: str) -> dict:
    order = _ORDERS.get(order_id)
    if order is None:
        return {"error": f"No order found with id {order_id!r}."}
    return order


def issue_refund(order_id: str, amount_usd: float, reason: str) -> dict:
    order = _ORDERS.get(order_id)
    if order is None:
        return {"error": f"No order found with id {order_id!r}."}

    already_refunded = order["refunded_usd"]
    remaining = round(order["total_usd"] - already_refunded, 2)

    # Value constraints the schema can't enforce — checked here, not trusted
    # to `minimum`/`maximum` in the JSON Schema.
    if amount_usd <= 0:
        return {"error": "amount_usd must be greater than 0."}
    if amount_usd > remaining:
        return {
            "error": (
                f"Refund of {amount_usd} exceeds remaining refundable amount "
                f"({remaining}) for {order_id}."
            )
        }

    order["refunded_usd"] = round(already_refunded + amount_usd, 2)
    return {
        "order_id": order_id,
        "refunded_usd": amount_usd,
        "remaining_refundable_usd": round(remaining - amount_usd, 2),
        "reason": reason,
        "confirmation_id": f"RF-{order_id}-{int(order['refunded_usd'] * 100)}",
    }


TOOL_REGISTRY = {
    "lookup_order": lookup_order,
    "issue_refund": issue_refund,
}

TOOLS = [
    {
        "name": "lookup_order",
        "description": (
            "Look up an order by its order ID. Returns the order status, total "
            "amount charged in USD, amount already refunded, and the items in the "
            "order. Use this before issuing a refund to confirm the order exists "
            "and check how much is still refundable. Does not modify anything."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order identifier, e.g. 'ORD-1001'.",
                },
            },
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "issue_refund",
        "description": (
            "Issue a refund against an order. This charges money back to the "
            "customer and cannot be undone — only call it after confirming the "
            "order ID and refund amount with lookup_order, and after the customer "
            "has clearly asked for a refund. Fails if the amount exceeds what is "
            "still refundable on the order."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order identifier to refund, e.g. 'ORD-1001'.",
                },
                "amount_usd": {
                    "type": "number",
                    "description": "Refund amount in USD. Must not exceed the order's remaining refundable balance.",
                },
                "reason": {
                    "type": "string",
                    "description": "Short reason for the refund, shown to the customer and kept for records.",
                },
            },
            "required": ["order_id", "amount_usd", "reason"],
            "additionalProperties": False,
        },
    },
]

SYSTEM_PROMPT = (
    "You are a support assistant. You can look up orders and issue refunds. "
    "Always look up the order before refunding it, confirm the refund amount "
    "and reason make sense given the order, and only issue a refund the "
    "customer has actually asked for. If a tool returns an error, explain it "
    "to the customer in plain language rather than retrying blindly."
)


@dataclass
class RunResult:
    text: str | None
    stop: str  # "done" | "max_iterations" | "refusal" | "error"
    iterations: int
    tool_calls: list = field(default_factory=list)
    usage: dict = field(default_factory=lambda: {"in": 0, "out": 0})


def execute_tool(block) -> dict:
    name = block.name
    if name not in TOOL_REGISTRY:
        return {"error": f"No tool named {name!r}. Available: {sorted(TOOL_REGISTRY)}"}
    try:
        return TOOL_REGISTRY[name](**block.input)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def run(messages: list, max_iterations: int = MAX_ITERATIONS) -> RunResult:
    """Drive the conversation until the model stops calling tools.

    `messages` is mutated in place so the caller can keep it across
    invocations (e.g. one call per incoming customer message).
    """
    calls = []
    usage = {"in": 0, "out": 0}
    seen_calls: dict[tuple, int] = {}

    for i in range(1, max_iterations + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        usage["in"] += response.usage.input_tokens
        usage["out"] += response.usage.output_tokens

        if response.stop_reason == "refusal":
            return RunResult(None, "refusal", i, calls, usage)
        if response.stop_reason == "max_tokens":
            raise RuntimeError(f"truncated on iteration {i}; raise max_tokens")

        messages.append({"role": "assistant", "content": response.content})  # verbatim

        if response.stop_reason != "tool_use":
            text = "".join(b.text for b in response.content if b.type == "text")
            return RunResult(text, "done", i, calls, usage)

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            signature = (block.name, json.dumps(block.input, sort_keys=True))
            seen_calls[signature] = seen_calls.get(signature, 0) + 1
            calls.append(block.name)

            if seen_calls[signature] >= 3:
                output = {
                    "error": (
                        "You've called this tool with these exact arguments "
                        "multiple times and gotten the same result. Try different "
                        "arguments, ask the customer for clarification, or answer "
                        "with what you have."
                    )
                }
            else:
                output = execute_tool(block)

            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(output),
                **({"is_error": True} if "error" in output else {}),
            })

        messages.append({"role": "user", "content": results})  # all results, one message

    return RunResult(None, "max_iterations", max_iterations, calls, usage)


if __name__ == "__main__":
    conversation = []
    print("Support bot ready. Type 'quit' to exit.")
    while True:
        user_input = input("\ncustomer> ").strip()
        if user_input.lower() in {"quit", "exit"}:
            break

        conversation.append({"role": "user", "content": user_input})
        result = run(conversation)

        if result.stop == "refusal":
            print("bot> I'm not able to help with that request.")
        elif result.stop == "max_iterations":
            print("bot> (took too many steps — escalating to a human agent.)")
        else:
            print(f"bot> {result.text}")

````
