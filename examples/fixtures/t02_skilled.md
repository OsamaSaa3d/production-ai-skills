```python
import json
MAX_ITERATIONS = 10

tools = [
  {"type":"function","function":{"name":"lookup_order","strict":True,
    "parameters":{"type":"object","properties":{"order_id":{"type":"string"}},
                  "required":["order_id"],"additionalProperties":False}}},
  {"type":"function","function":{"name":"issue_refund","strict":True,
    "parameters":{"type":"object","properties":{"order_id":{"type":"string"},"amount_usd":{"type":"number"}},
                  "required":["order_id","amount_usd"],"additionalProperties":False}}},
]

def run(user_message: str):
    messages = [{"role": "user", "content": user_message}]
    for i in range(MAX_ITERATIONS):
        r = client.chat.completions.create(model=MODEL, messages=messages, tools=tools)
        msg = r.choices[0].message
        messages.append(msg)
        if not msg.tool_calls:
            return msg.content
        for tc in msg.tool_calls:
            try:
                result = REGISTRY[tc.function.name](**json.loads(tc.function.arguments))
            except Exception as e:
                result = {"error": f"{type(e).__name__}: {e}. Check the order id and retry."}
            messages.append({"role":"tool","tool_call_id":tc.id,"content":json.dumps(result)})
    return None  # hit the cap; caller decides what a partial run is worth
```
Verify the order exists before refunding, and cap iterations — an agent without a ceiling burns budget when it gets stuck.
