```python
def fix_test(test_name):
    prompt = f"Here is a failing test: {read_test(test_name)}. Write the fix."
    patch = client.chat.completions.create(model=MODEL,
        messages=[{"role":"user","content":prompt}]).choices[0].message.content
    apply_patch(patch)
```
