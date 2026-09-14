```python
tools = [
 {"type":"function","function":{"name":"get_inventory","description":"Current units on hand for a SKU.",
   "strict":True,"parameters":{"type":"object","properties":{"sku":{"type":"string"}},
   "required":["sku"],"additionalProperties":False}}},
 {"type":"function","function":{"name":"reserve_stock","description":"Reserve qty units of a SKU. Reduces available inventory.",
   "strict":True,"parameters":{"type":"object","properties":{"sku":{"type":"string"},"qty":{"type":"integer"}},
   "required":["sku","qty"],"additionalProperties":False}}},
]
REGISTRY = {"get_inventory": get_inventory, "reserve_stock": reserve_stock}

r = client.chat.completions.create(model=MODEL, messages=messages, tools=tools, tool_choice="auto")
msg = r.choices[0].message; messages.append(msg)
for tc in msg.tool_calls or []:
    try:
        out = REGISTRY[tc.function.name](**json.loads(tc.function.arguments))
    except Exception as e:
        out = {"error": str(e)}
    messages.append({"role":"tool","tool_call_id":tc.id,"content":json.dumps(out)})
```
