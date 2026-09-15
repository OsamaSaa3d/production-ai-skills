Both files pass a syntax check. Here's what I built in `C:\tmp\skills-eval\arm-a\t03-r1`:

**`inventory.py`** — stand-in for your existing `get_inventory(sku)` / `reserve_stock(sku, qty)` functions (in-memory store). Swap the internals for your real DB/service calls; the integration only depends on these two signatures.

**`agent.py`** — the Claude integration:
- Wraps both functions with `@beta_tool` (Anthropic SDK's beta tool runner) — Claude sees the schema generated from the type hints + docstrings, so those docstrings are the tool descriptions the model reads.
- Known business errors (unknown SKU, insufficient stock) are caught and returned as a result dict rather than raised, so Claude gets a normal tool result to reason about and relay, instead of the loop crashing.
- `client.beta.messages.tool_runner(...)` drives the whole request → tool-call → feed-results-back loop — no manual `while` loop needed.
- System prompt tells Claude to check availability before reserving and to only report success when the tool result confirms it.
- `ask()` wraps typed error handling for rate limits / API errors / connection errors per the SDK's exception hierarchy.

**`requirements.txt`** — pins `anthropic>=0.130.0` (needed for the beta tool runner / `@beta_tool`).

Usage:
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python agent.py "Do we have SKU-1002 in stock? Reserve 3 for order #4521."
```

Notes/assumptions I made:
- Used `claude-opus-5` (this skill's default) — swap `MODEL` in `agent.py` if you want Sonnet/Haiku instead.
- Used the beta Tool Runner rather than a manual loop since you're wiring up exactly two plain functions — it's the simpler, recommended path and needs no boilerplate loop code.
- Since no code existed yet in this directory, I created `inventory.py` as a clearly-labeled placeholder for "your existing functions" — replace it with an import of your real module (`from your_inventory_module import get_inventory, reserve_stock`) and delete the stub file.

I didn't run a live API call (no key configured, and that would hit the real API) — only a syntax compile check. Let me know if you want me to wire this to your actual inventory module instead of the stub, or add streaming/multi-turn chat on top.

---

## Files written by the session

### `agent.py`

````py
"""Claude integration for the inventory functions.

Lets Claude call the existing get_inventory(sku) and reserve_stock(sku, qty)
functions from inventory.py as tools. Uses the Anthropic SDK's beta tool
runner, which drives the request -> execute -> feed-results-back loop for
you -- no manual while-loop needed.

Setup:
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=sk-ant-...      (or `ant auth login`)

Run:
    python agent.py "Do we have SKU-1002 in stock? Reserve 3 for order #4521."
"""

from __future__ import annotations

import sys

import anthropic
from anthropic import beta_tool

import inventory

MODEL = "claude-opus-5"

client = anthropic.Anthropic()


# --- Tool wrappers -----------------------------------------------------
#
# @beta_tool generates the JSON tool schema from the function's type hints
# and docstring, so the docstring below is what Claude sees as the tool
# description -- keep it accurate. Known business errors (bad SKU,
# insufficient stock) are caught and returned as a plain dict rather than
# raised, so Claude sees a normal tool result it can reason about and
# relay to the user instead of the loop erroring out.


@beta_tool
def get_inventory(sku: str) -> dict:
    """Look up current on-hand, reserved, and available quantity for a SKU.

    Args:
        sku: The product SKU to look up, e.g. "SKU-1001".
    """
    try:
        return inventory.get_inventory(sku)
    except KeyError as e:
        return {"error": str(e)}


@beta_tool
def reserve_stock(sku: str, qty: int) -> dict:
    """Reserve a quantity of stock for a SKU. Fails if the SKU is unknown
    or there isn't enough available stock to cover the request.

    Args:
        sku: The product SKU to reserve, e.g. "SKU-1001".
        qty: Number of units to reserve. Must be a positive integer.
    """
    try:
        return inventory.reserve_stock(sku, qty)
    except (KeyError, ValueError) as e:
        return {"error": str(e)}


SYSTEM_PROMPT = (
    "You are an inventory assistant. Use the get_inventory and reserve_stock "
    "tools to answer stock questions and fulfill reservation requests. Always "
    "check availability with get_inventory before reserving unless the caller "
    "has already given you a fresh availability figure. Only report a "
    "reservation as successful if the reserve_stock tool result confirms it -- "
    "if the tool result contains an error, relay that error to the user "
    "instead of guessing."
)


def ask(user_message: str) -> str:
    """Send one user message through the tool-calling loop and return Claude's
    final text reply."""
    try:
        runner = client.beta.messages.tool_runner(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=[get_inventory, reserve_stock],
            messages=[{"role": "user", "content": user_message}],
        )

        final_text = ""
        for message in runner:
            for block in message.content:
                if block.type == "text":
                    final_text = block.text
        return final_text

    except anthropic.RateLimitError as e:
        retry_after = int(e.response.headers.get("retry-after", "60"))
        return f"Rate limited, retry after {retry_after}s."
    except anthropic.APIStatusError as e:
        return f"API error ({e.status_code}): {e.message}"
    except anthropic.APIConnectionError:
        return "Network error contacting Claude API."


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) or (
        "Do we have SKU-1002 in stock? If there are at least 3 available, "
        "reserve 3 for order #4521."
    )
    print(ask(prompt))

````

### `inventory.py`

````py
"""Existing inventory/reservation business logic.

This module stands in for your existing get_inventory() / reserve_stock()
functions. Replace the in-memory store below with your real database or
service calls -- the Claude integration in agent.py only depends on these
two function signatures, not on how they're implemented.
"""

from __future__ import annotations

_STOCK: dict[str, int] = {
    "SKU-1001": 42,
    "SKU-1002": 5,
    "SKU-1003": 0,
}

_RESERVED: dict[str, int] = {}


def get_inventory(sku: str) -> dict:
    """Return current on-hand / reserved / available quantity for a SKU.

    Raises:
        KeyError: if the SKU does not exist.
    """
    if sku not in _STOCK:
        raise KeyError(f"Unknown SKU: {sku}")
    on_hand = _STOCK[sku]
    reserved = _RESERVED.get(sku, 0)
    return {
        "sku": sku,
        "on_hand": on_hand,
        "reserved": reserved,
        "available": on_hand - reserved,
    }


def reserve_stock(sku: str, qty: int) -> dict:
    """Reserve `qty` units of `sku` against available stock.

    Raises:
        KeyError: if the SKU does not exist.
        ValueError: if qty is not positive or exceeds available stock.
    """
    if sku not in _STOCK:
        raise KeyError(f"Unknown SKU: {sku}")
    if qty <= 0:
        raise ValueError("qty must be a positive integer")

    available = _STOCK[sku] - _RESERVED.get(sku, 0)
    if qty > available:
        raise ValueError(
            f"Only {available} unit(s) of {sku} available; cannot reserve {qty}"
        )

    _RESERVED[sku] = _RESERVED.get(sku, 0) + qty
    return {"sku": sku, "reserved_qty": qty, "total_reserved": _RESERVED[sku]}

````

### `requirements.txt`

````txt
anthropic>=0.130.0

````
