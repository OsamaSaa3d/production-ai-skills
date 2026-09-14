Describe the query syntax in the system prompt and let the model write queries:

```python
SYSTEM = """You can search tickets. Query syntax:
  field:value, field:>value, field:[a TO b], combined with AND / OR / NOT.
Fields: status, team, created, priority, assignee.
Emit only the query string."""

def search(question: str):
    q = client.chat.completions.create(model=MODEL,
        messages=[{"role":"system","content":SYSTEM},{"role":"user","content":question}]
    ).choices[0].message.content.strip()
    return tickets_api.search(q)
```
