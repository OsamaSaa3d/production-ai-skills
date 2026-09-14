Don't let the model emit SQL. Give it typed fields and build the query yourself.

```python
import json, psycopg
from openai import OpenAI

MODEL = "..."
client = OpenAI()

tools = [{
    "type": "function",
    "function": {
        "name": "search_orders",
        "description": "Search customer orders. Returns id, status, total_usd, placed_at.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "customer_email": {"type": ["string", "null"]},
                "status": {"type": ["string", "null"], "enum": ["open", "shipped", "cancelled", None]},
                "placed_after": {"type": ["string", "null"], "description": "ISO date"},
            },
            "required": ["customer_email", "status", "placed_after"],
            "additionalProperties": False,
        },
    },
}]

def search_orders(customer_email=None, status=None, placed_after=None):
    clauses, params = [], []
    if customer_email: clauses.append("customer_email = %s"); params.append(customer_email)
    if status:         clauses.append("status = %s");         params.append(status)
    if placed_after:   clauses.append("placed_at >= %s");     params.append(placed_after)
    where = " AND ".join(clauses) or "TRUE"
    with psycopg.connect(DSN) as c:
        return c.execute(f"SELECT id, status, total_usd, placed_at FROM orders WHERE {where} LIMIT 100", params).fetchall()

REGISTRY = {"search_orders": search_orders}

def ask(question: str):
    messages = [{"role": "user", "content": question}]
    resp = client.chat.completions.create(model=MODEL, messages=messages, tools=tools)
    msg = resp.choices[0].message
    messages.append(msg)
    for tc in msg.tool_calls or []:
        try:
            result = REGISTRY[tc.function.name](**json.loads(tc.function.arguments))
        except Exception as e:
            result = {"error": f"{type(e).__name__}: {e}. Narrow the filters and retry."}
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)})
    return client.chat.completions.create(model=MODEL, messages=messages, tools=tools).choices[0].message.content
```

The model never writes SQL — it picks fields, and the WHERE clause is parameterised.
