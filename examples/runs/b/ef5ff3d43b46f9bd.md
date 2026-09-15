No actual `filter_records` implementation exists in this directory (it's only referenced in the tool-design skill docs) — I searched the whole tree, so I'll give you the fix as ready-to-drop-in code rather than an edit.

This is exactly the failure case the `tool-design` skill documents: a polarity/mode flag is the worst kind of wrong-argument bug because a flipped value is structurally valid — no error, no crash, just confidently wrong results. The fix isn't "swap `==` for `!=`" in the handler (that just moves the bug); it's removing the flag from the model's control entirely by splitting it into two unambiguously-named tools.

**Before (the bug's real cause — polarity lives in a parameter the model has to reason about):**
```python
{
    "name": "filter_records",
    "input_schema": {
        "properties": {
            "field": {"type": "string"},
            "value": {"type": "string"},
            "mode": {"type": "string", "enum": ["include", "exclude"]},
        },
        "required": ["field", "value", "mode"],
    },
}
```

**After (polarity lives in the name — nothing left to flip):**
```python
{
    "name": "filter_records_including_value",
    "description": "Return only records where <field> equals <value>.",
    "input_schema": {
        "type": "object",
        "properties": {
            "field": {"type": "string"},
            "value": {"type": "string"},
        },
        "required": ["field", "value"],
        "additionalProperties": False,
    },
},
{
    "name": "filter_records_excluding_value",
    "description": "Return all records except those where <field> equals <value>.",
    "input_schema": {
        "type": "object",
        "properties": {
            "field": {"type": "string"},
            "value": {"type": "string"},
        },
        "required": ["field", "value"],
        "additionalProperties": False,
    },
}
```

**Handler side** — one function, dispatch by tool name instead of by the (formerly unreliable) `mode` argument:

```python
def filter_records_including_value(field: str, value: str, records: list[dict]) -> list[dict]:
    return [r for r in records if r.get(field) == value]

def filter_records_excluding_value(field: str, value: str, records: list[dict]) -> list[dict]:
    return [r for r in records if r.get(field) != value]
```

Point your agent's tool router at these two names instead of `filter_records`, and delete the old `mode`-branching code — there's no flag left to get backwards.

One thing worth doing before you call this closed: the skill's own worked example got here by measuring first (mode correct only 33/40 before the split, 40/40 after). If you have — or can quickly build — a small task set with both "show me only X" and "show me everything except X" phrasings, run it against this split to confirm it actually fixes your agent's specific failure rather than just matching the documented pattern.