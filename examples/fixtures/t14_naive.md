```python
TOOLS = [read_issue_tool, search_duplicates_tool, set_label_tool, assign_team_tool]

def triage_agent(issue_id):
    messages = [{"role":"user","content":f"Triage issue {issue_id}"}]
    while True:
        r = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        m = r.choices[0].message
        messages.append(m)
        if not m.tool_calls:
            return m.content
        for tc in m.tool_calls:
            messages.append({"role":"tool","tool_call_id":tc.id,"content":dispatch(tc)})
```
