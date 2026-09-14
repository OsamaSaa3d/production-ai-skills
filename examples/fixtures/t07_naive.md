```python
prompt = "Extract the party names and termination clause. Return JSON."
resp = client.chat.completions.create(model=MODEL,
    messages=[{"role":"user","content":prompt + contract}])
return json.loads(resp.choices[0].message.content)
```
