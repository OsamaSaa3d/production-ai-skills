```python
prompt = f"""Extract invoice_number, issue_date, total, customer_name, po_number
from this invoice. Respond with JSON only.

{invoice_text}"""

resp = client.chat.completions.create(model=MODEL, messages=[{"role":"user","content":prompt}])
raw = resp.choices[0].message.content.strip()
if raw.startswith("```"):
    raw = raw.split("```")[1].replace("json", "", 1)
data = json.loads(raw)
db.insert("orders", data)
```
