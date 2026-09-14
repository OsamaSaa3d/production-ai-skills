Don't let the model write the query language. Give it typed fields.

```python
tools = [{
  "type": "function",
  "function": {
    "name": "search_tickets",
    "description": "Search tickets. Returns id, title, status, team, created_at.",
    "strict": True,
    "parameters": {
      "type": "object",
      "properties": {
        "text":    {"type": ["string", "null"]},
        "status":  {"type": ["string", "null"], "enum": ["open", "closed", "pending", None]},
        "team":    {"type": ["string", "null"], "enum": ["platform", "billing", "growth", None]},
        "created_after": {"type": ["string", "null"], "description": "ISO date"}
      },
      "required": ["text", "status", "team", "created_after"],
      "additionalProperties": False
    }
  }
}]

def search_tickets(text=None, status=None, team=None, created_after=None):
    parts = []
    if status: parts.append(f"status:{status}")
    if team:   parts.append(f"team:{team}")
    if created_after: parts.append(f"created:>{created_after}")
    if text:   parts.append(f'"{text}"')
    return tickets_api.search(" AND ".join(parts))
```

The model picks fields; our code owns the grammar. An enum of three statuses cannot produce a fourth.
