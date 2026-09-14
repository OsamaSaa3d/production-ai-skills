Use structured outputs so the summary is reliable:

```python
from pydantic import BaseModel

class Summary(BaseModel):
    paragraph: str

completion = client.chat.completions.parse(
    model=MODEL,
    messages=[{"role": "user", "content": transcript}],
    response_format=Summary,
)
return completion.choices[0].message.parsed.paragraph
```
