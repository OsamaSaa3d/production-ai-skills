This one genuinely is an agent. You cannot predict how many steps a fix takes, and the environment tells the truth — the test suite is an objective pass/fail signal at every step, which is exactly the condition that makes agent autonomy work.

```python
MAX_ITERATIONS = 15
MAX_COST_USD = 2.00

def fix_failing_test(test_id: str):
    messages = [{"role":"user","content":f"Get {test_id} passing. Run the suite to check."}]
    spent = 0.0
    for i in range(MAX_ITERATIONS):
        r = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        spent += price(r.usage)
        if spent >= MAX_COST_USD:
            return Result("budget", i, spent)
        msg = r.choices[0].message
        messages.append(msg)
        if not msg.tool_calls:
            return Result("done", i, spent)
        for tc in msg.tool_calls:
            try:
                out = REGISTRY[tc.function.name](**json.loads(tc.function.arguments))
            except Exception as e:
                out = {"error": f"{type(e).__name__}: {e}"}
            messages.append({"role":"tool","tool_call_id":tc.id,"content":json.dumps(out)})
    return Result("max_iterations", MAX_ITERATIONS, spent)
```

Cost, not iteration count, is what actually hurts — one call with 80K of context costs more than six small ones — so the budget cap is checked after each response. Hitting a cap is a return value, not an exception: the caller decides whether a partial run is useful, and raising would lose the transcript and the token count.
