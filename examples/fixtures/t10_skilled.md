Endpoint count is not tool count. Don't wrap the API one-to-one — consolidate around how the agent actually uses it. Frequently-chained calls become one tool.

```python
TOOLS = [
 {"type":"function","function":{"name":"get_customer_context","strict":True,
   "description":"Full picture of one customer: profile, open deals, recent notes. Returns names, not ids.",
   "parameters":{"type":"object","properties":{"contact_id":{"type":"string"}},
                 "required":["contact_id"],"additionalProperties":False}}},
 {"type":"function","function":{"name":"search_crm","strict":True,
   "description":"Search contacts, deals and notes by text, owner and stage.",
   "parameters":{"type":"object","properties":{
       "text":{"type":["string","null"]},
       "entity":{"type":"string","enum":["contact","deal","note"]},
       "stage":{"type":["string","null"],"enum":["lead","qualified","won","lost",None]}},
     "required":["text","entity","stage"],"additionalProperties":False}}},
 {"type":"function","function":{"name":"log_activity","strict":True,
   "description":"Write a note against a contact or deal.",
   "parameters":{"type":"object","properties":{"target_id":{"type":"string"},"body":{"type":"string"}},
                 "required":["target_id","body"],"additionalProperties":False}}},
]
```
`get_contact` + `list_deals` + `list_notes` were always called together, so they are one tool now. Three tools instead of fourteen keeps the catalogue well inside the range where selection accuracy holds.
