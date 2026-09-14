LangGraph is load-bearing here — you named durable checkpointing as the reason, and rebuilding that is a real cost with no user-visible benefit. Keep it. Add the tool as a node.

```python
from langgraph.graph import StateGraph

TOOLS = [{"type":"function","function":{"name":"search_orders","strict":True,
  "parameters":{"type":"object","properties":{"customer_email":{"type":["string","null"]},
  "status":{"type":["string","null"]}},"required":["customer_email","status"],
  "additionalProperties":False}}}]

def query_orders(state):
    r = client.chat.completions.create(model=MODEL, messages=state["messages"], tools=TOOLS)
    return {"messages": state["messages"] + [r.choices[0].message]}

graph = StateGraph(State)
graph.add_node("query_orders", query_orders)
```
Note the tool definition still carries `strict: true` — that guarantee is independent of the harness you run it in.
