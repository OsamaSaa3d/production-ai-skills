Here are all 14 endpoints as tools:

```python
TOOLS = [
 {"type":"function","function":{"name":"get_contact","parameters":{"type":"object","properties":{"id":{"type":"string"}}}}},
 {"type":"function","function":{"name":"list_contacts","parameters":{"type":"object","properties":{}}}},
 {"type":"function","function":{"name":"create_contact","parameters":{"type":"object","properties":{"name":{"type":"string"}}}}},
 {"type":"function","function":{"name":"update_contact","parameters":{"type":"object","properties":{"id":{"type":"string"}}}}},
 {"type":"function","function":{"name":"delete_contact","parameters":{"type":"object","properties":{"id":{"type":"string"}}}}},
 {"type":"function","function":{"name":"get_deal","parameters":{"type":"object","properties":{"id":{"type":"string"}}}}},
 {"type":"function","function":{"name":"list_deals","parameters":{"type":"object","properties":{}}}},
 {"type":"function","function":{"name":"create_deal","parameters":{"type":"object","properties":{"title":{"type":"string"}}}}},
 {"type":"function","function":{"name":"update_deal","parameters":{"type":"object","properties":{"id":{"type":"string"}}}}},
 {"type":"function","function":{"name":"delete_deal","parameters":{"type":"object","properties":{"id":{"type":"string"}}}}},
 {"type":"function","function":{"name":"get_note","parameters":{"type":"object","properties":{"id":{"type":"string"}}}}},
 {"type":"function","function":{"name":"list_notes","parameters":{"type":"object","properties":{}}}},
 {"type":"function","function":{"name":"create_note","parameters":{"type":"object","properties":{"body":{"type":"string"}}}}},
 {"type":"function","function":{"name":"delete_note","parameters":{"type":"object","properties":{"id":{"type":"string"}}}}},
]
```
