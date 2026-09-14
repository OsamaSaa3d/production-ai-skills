Here's an agent that handles the daily sales summary:

```python
from openai import OpenAI
client = OpenAI()

TOOLS = [{"type":"function","function":{"name":"read_csv","parameters":{"type":"object","properties":{"path":{"type":"string"}}}}},
         {"type":"function","function":{"name":"send_email","parameters":{"type":"object","properties":{"to":{"type":"string"},"body":{"type":"string"}}}}}]

def run_agent(goal="Summarise today's sales and email the team"):
    messages = [{"role":"user","content":goal}]
    while True:
        r = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        m = r.choices[0].message
        messages.append(m)
        if not m.tool_calls:
            return m.content
        for tc in m.tool_calls:
            messages.append({"role":"tool","tool_call_id":tc.id,"content":dispatch(tc)})
```
