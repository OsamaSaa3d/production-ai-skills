```python
def summarise(transcript: str) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": "Summarise this meeting in one short paragraph a manager can skim."},
                  {"role": "user", "content": transcript}])
    return resp.choices[0].message.content
```
