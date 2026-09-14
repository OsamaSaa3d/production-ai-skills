```python
SYSTEM = """You have these functions:
  get_inventory(sku) -> int
  reserve_stock(sku, qty) -> bool
Respond with JSON: {"fn": "...", "args": {...}}"""

out = client.chat.completions.create(model=MODEL,
    messages=[{"role":"system","content":SYSTEM},{"role":"user","content":q}])
call = json.loads(out.choices[0].message.content)
result = globals()[call["fn"]](**call["args"])
```
