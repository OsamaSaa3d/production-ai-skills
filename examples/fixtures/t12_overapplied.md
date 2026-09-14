Set this up with deferred loading and examples so it scales:

```python
tools = [
 {"type":"tool_search_tool_regex_20251119","name":"tool_search_tool_regex"},
 {"name":"get_user","description":"Fetch a user by id.",
  "input_schema":{"type":"object","properties":{"user_id":{"type":"string"}},
                  "required":["user_id"],"additionalProperties":False},
  "defer_loading": True,
  "input_examples":[{"user_id":"USR-12345"},{"user_id":"USR-67890"}],
  "allowed_callers":["code_execution_20260120"]},
]
```
