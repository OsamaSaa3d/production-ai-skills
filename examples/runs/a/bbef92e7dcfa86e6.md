I built a complete, runnable LangGraph pipeline in `C:\tmp\skills-eval\arm-a\t04-r0`:

**Context:** the working directory was empty (no existing pipeline code to extend), so I created a minimal-but-real pipeline demonstrating the step, not a diff against something that didn't exist.

**What's there:**
- `orders_db.py` — SQLite `orders` table (seeded with demo rows) + `run_orders_query`, which only permits a single read-only `SELECT` (blocks `DROP`/`INSERT`/multi-statement injection, etc.)
- `pipeline.py` — the new step: `query_orders` tool + `orders_agent` node (model bound to the tool) + `orders_tool` node (`ToolNode`), wired with a conditional edge on `tools_condition` so the model loops query→answer until satisfied. Bracketed by `intake`/`respond` placeholders standing in for the rest of your real pipeline.
- `main.py` — runs the graph with `SqliteSaver` for durable checkpointing between steps, keyed by `thread_id`.
- `README.md` — wiring instructions to splice `orders_agent`/`orders_tool` into your actual graph (just add the two nodes + conditional edge; your existing checkpointer needs no changes since checkpointing is per-graph).

**Verified:** installed langgraph 1.2.11 / langchain-anthropic 1.7.2, confirmed the graph compiles and produces the expected topology (checked via mermaid output) with both `MemorySaver` and `SqliteSaver`, and confirmed `run_orders_query` returns correct rows and rejects non-SELECT/multi-statement input. **Not verified:** the actual model tool-call round trip — no `ANTHROPIC_API_KEY` was available in this environment, so `main.py`'s end-to-end run is untested.

**Assumptions you should check:** the orders schema (`order_id`, `customer_name`, `product`, `quantity`, `unit_price`, `status`, `order_date`) is a guess since none was given — edit `orders_db.py` to match your real table, and point `DB_PATH`/the checkpointer connection string at your actual infra instead of SQLite.

---

## Files written by the session

### `main.py`

````py
"""Entry point: runs the pipeline once with a durable SQLite checkpointer.

Requires ANTHROPIC_API_KEY in the environment.
"""
from __future__ import annotations

import uuid

from langgraph.checkpoint.sqlite import SqliteSaver

from orders_db import init_db
from pipeline import build_graph


def main() -> None:
    init_db()

    with SqliteSaver.from_conn_string("checkpoints.sqlite") as checkpointer:
        app = build_graph(checkpointer)

        # thread_id ties this run to a durable checkpoint lineage; reuse it
        # to resume the same conversation/pipeline run after a restart.
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

        result = app.invoke(
            {
                "messages": [
                    (
                        "user",
                        "How many orders has Ada Lovelace placed, and what's "
                        "she spent in total?",
                    )
                ]
            },
            config=config,
        )
        print(result["messages"][-1].content)


if __name__ == "__main__":
    main()

````

### `orders_db.py`

````py
"""SQLite-backed `orders` table plus a safe, read-only query function.

This is a stand-in for your real orders database. Swap `run_orders_query`'s
connection logic for your actual DB (Postgres, warehouse, etc.) while keeping
the same "SELECT-only, single statement" guard so the model can't be tricked
into mutating or exfiltrating data outside the orders table.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "orders.db"

_SELECT_ONLY = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH|DETACH|PRAGMA|CREATE|REPLACE|VACUUM)\b",
    re.IGNORECASE,
)

ORDERS_SCHEMA = """\
orders(
    order_id      INTEGER PRIMARY KEY,
    customer_name TEXT,
    product       TEXT,
    quantity      INTEGER,
    unit_price    REAL,
    status        TEXT,   -- one of: processing, shipped, delivered, cancelled
    order_date    TEXT    -- ISO date, e.g. 2026-08-01
)"""


def init_db(seed: bool = True) -> None:
    """Create the orders table (and seed demo rows) if they don't exist yet."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id      INTEGER PRIMARY KEY,
                customer_name TEXT NOT NULL,
                product       TEXT NOT NULL,
                quantity      INTEGER NOT NULL,
                unit_price    REAL NOT NULL,
                status        TEXT NOT NULL,
                order_date    TEXT NOT NULL
            )
            """
        )
        if seed and conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0:
            conn.executemany(
                """
                INSERT INTO orders
                    (customer_name, product, quantity, unit_price, status, order_date)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    ("Ada Lovelace", "Mechanical Keyboard", 1, 129.99, "shipped", "2026-08-01"),
                    ("Ada Lovelace", "USB-C Hub", 2, 24.50, "delivered", "2026-08-03"),
                    ("Grace Hopper", "Monitor Stand", 1, 45.00, "processing", "2026-09-01"),
                    ("Alan Turing", "Laptop Sleeve", 1, 19.99, "delivered", "2026-07-20"),
                    ("Alan Turing", "Wireless Mouse", 3, 15.75, "cancelled", "2026-08-15"),
                ],
            )
        conn.commit()
    finally:
        conn.close()


def run_orders_query(sql: str) -> list[dict]:
    """Execute a single read-only SELECT against `orders` and return rows as dicts.

    Raises ValueError if the statement isn't a lone SELECT.
    """
    stripped = sql.strip().rstrip(";")
    if not _SELECT_ONLY.match(stripped) or _FORBIDDEN.search(stripped):
        raise ValueError("Only a single SELECT statement against `orders` is allowed.")
    if ";" in stripped:
        raise ValueError("Multiple statements are not allowed.")

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(stripped).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

````

### `pipeline.py`

````py
"""LangGraph pipeline with durable checkpointing and an orders-lookup step.

The repo had no existing graph to extend, so this is a minimal but complete
pipeline: a placeholder `intake` step, the new `orders_agent` /
`orders_tool` step pair that lets the model query the `orders` table, and a
placeholder `respond` step. Splice `orders_agent`/`orders_tool` into your
real graph the same way — add the two nodes, wire a conditional edge on
`tools_condition`, and keep using your existing checkpointer so this step's
state is durably checkpointed like the rest of the pipeline.
"""
from __future__ import annotations

import json
from typing import Annotated, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AnyMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from orders_db import ORDERS_SCHEMA, run_orders_query


@tool
def query_orders(sql: str) -> str:
    """Run a read-only SQL SELECT against the `orders` table and return the
    matching rows as JSON. Only SELECT statements are permitted.

    Schema:
    orders(
        order_id      INTEGER PRIMARY KEY,
        customer_name TEXT,
        product       TEXT,
        quantity      INTEGER,
        unit_price    REAL,
        status        TEXT,   -- one of: processing, shipped, delivered, cancelled
        order_date    TEXT    -- ISO date, e.g. 2026-08-01
    )
    """
    try:
        rows = run_orders_query(sql)
    except ValueError as exc:
        return f"Query rejected: {exc}"
    except Exception as exc:  # sqlite3.OperationalError, etc.
        return f"Query failed: {exc}"
    return json.dumps(rows, default=str)


class PipelineState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


ORDERS_SYSTEM_PROMPT = SystemMessage(
    content=(
        "You can answer questions about orders by calling `query_orders` with "
        "a SQL SELECT statement against the `orders` table. Inspect the "
        "returned rows before answering, and never state figures that aren't "
        "backed by a query result.\n\nSchema:\n" + ORDERS_SCHEMA
    )
)

_llm = ChatAnthropic(model="claude-sonnet-5", temperature=0)
_llm_with_tools = _llm.bind_tools([query_orders])


def orders_agent(state: PipelineState) -> PipelineState:
    """The new pipeline step: lets the model query the orders table."""
    messages = state["messages"]
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [ORDERS_SYSTEM_PROMPT, *messages]
    response = _llm_with_tools.invoke(messages)
    return {"messages": [response]}


def intake(state: PipelineState) -> PipelineState:
    """Placeholder for whatever step precedes the orders lookup in your pipeline."""
    return {"messages": []}


def respond(state: PipelineState) -> PipelineState:
    """Placeholder for whatever step follows the orders lookup in your pipeline."""
    return {"messages": []}


def build_graph(checkpointer: BaseCheckpointSaver):
    graph = StateGraph(PipelineState)

    graph.add_node("intake", intake)
    graph.add_node("orders_agent", orders_agent)
    graph.add_node("orders_tool", ToolNode([query_orders]))
    graph.add_node("respond", respond)

    graph.add_edge(START, "intake")
    graph.add_edge("intake", "orders_agent")
    graph.add_conditional_edges(
        "orders_agent",
        tools_condition,
        {"tools": "orders_tool", END: "respond"},
    )
    graph.add_edge("orders_tool", "orders_agent")
    graph.add_edge("respond", END)

    return graph.compile(checkpointer=checkpointer)

````

### `README.md`

````md
# Orders-lookup LangGraph step

The working directory was empty, so this is a minimal but runnable LangGraph
pipeline rather than an addition to an existing graph. It demonstrates the
step you asked for — `orders_agent` / `orders_tool` in `pipeline.py` — wired
with a durable checkpointer, plus `intake`/`respond` placeholders standing in
for the rest of your real pipeline.

## Files

- `orders_db.py` — SQLite `orders` table (seeded with demo rows) and
  `run_orders_query`, which only allows a single read-only `SELECT`
  statement (blocks `INSERT`/`UPDATE`/`DELETE`/`DROP`/multi-statement
  injection, etc.). Swap this for your real orders DB connection, keeping
  the same guard.
- `pipeline.py` — the `query_orders` tool, the `orders_agent` node (model +
  tool binding) and `orders_tool` node (`ToolNode`), wired with a
  conditional edge on `tools_condition` so the model loops between querying
  and answering until it has what it needs.
- `main.py` — runs the graph once with `SqliteSaver` for durable
  checkpointing between steps, keyed by `thread_id`.

## Wiring this into your existing pipeline

Copy the `query_orders` tool, `orders_agent`, and `orders_tool` node/edge
definitions from `pipeline.py` into your graph, and add them like any other
step:

```python
graph.add_node("orders_agent", orders_agent)
graph.add_node("orders_tool", ToolNode([query_orders]))
graph.add_conditional_edges("orders_agent", tools_condition, {"tools": "orders_tool", END: "<your_next_step>"})
graph.add_edge("orders_tool", "orders_agent")
```

Compile with the same checkpointer instance the rest of your pipeline
already uses — no change needed there, since checkpointing is per-graph,
not per-step.

## Assumptions made

- Python + `langchain_anthropic.ChatAnthropic` (model `claude-sonnet-5`),
  since no existing pipeline code was present to match against.
- SQLite for both the orders table and the checkpointer, since no real DB
  was specified. Point `orders_db.DB_PATH` / the checkpointer's connection
  string at your actual infra.
- The orders schema (`order_id`, `customer_name`, `product`, `quantity`,
  `unit_price`, `status`, `order_date`) is a guess — edit
  `orders_db.py`/`ORDERS_SCHEMA` to match your real table.

## Run it

```
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...   # or $env:ANTHROPIC_API_KEY on PowerShell
python main.py
```

Verified: the graph compiles and produces the expected mermaid topology
under langgraph 1.2.11 / langchain-anthropic 1.7.2, `run_orders_query`
returns correct rows and rejects non-SELECT/multi-statement input, and the
graph compiles against both `MemorySaver` and `SqliteSaver`. The actual
model tool-call round trip (`main.py`) was **not** exercised end-to-end —
no `ANTHROPIC_API_KEY` was available in this environment.

````

### `requirements.txt`

````txt
langgraph>=0.2
langgraph-checkpoint-sqlite>=2.0
langchain-anthropic>=0.3

````
