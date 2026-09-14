You don't need LangGraph for this. Here's a direct implementation that drops the framework:

```python
from openai import OpenAI
client = OpenAI()

def query_orders_step(state):
    r = client.chat.completions.create(model=MODEL, messages=state["messages"], tools=TOOLS)
    return {"messages": state["messages"] + [r.choices[0].message]}
```
Rewriting the pipeline without LangGraph will simplify things.
