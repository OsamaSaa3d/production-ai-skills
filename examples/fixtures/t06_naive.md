```python
resp = client.chat.completions.create(model=MODEL,
    messages=[{"role":"user","content":f"Is this email urgent? Answer high, medium or low.\n\n{email}"}])
urgency = resp.choices[0].message.content.strip().lower()
route(urgency)
```
