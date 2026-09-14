```python
from enum import Enum
from pydantic import BaseModel, Field

class Urgency(str, Enum):
    HIGH = "high"; MEDIUM = "medium"; LOW = "low"; UNCLEAR = "unclear"

class Triage(BaseModel):
    reasoning: str = Field(description="One sentence citing the phrase that decided it.")
    urgency: Urgency = Field(description=(
        "high: outage, data loss, or a blocked paying customer. "
        "medium: degraded but working. low: question or request. "
        "unclear: two levels equally supported — route to a human."))

c = client.chat.completions.parse(model=MODEL, response_format=Triage,
        messages=[{"role":"user","content":email}]).choices[0]
if c.finish_reason == "length" or c.message.refusal:
    return escalate(email)
t = c.message.parsed
route(Urgency(t.urgency.lower()))
```
`reasoning` is declared first so it is thinking the model does before committing, not a rationalisation of a label already emitted. `unclear` is the abstention path — a taxonomy with no escape hatch forces a wrong answer on every out-of-distribution input.
