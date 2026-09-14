```python
def research(company):
    prompt = f"Research {company}: pricing, funding history, headcount. Write a brief."
    return client.chat.completions.create(model=MODEL,
        messages=[{"role":"user","content":prompt}]).choices[0].message.content
```
