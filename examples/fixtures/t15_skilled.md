The three directions are genuinely independent — pricing, funding and headcount can each be answered without knowing what the others found — so this is the shape where parallel decomposition earns its cost. Be aware what that cost is: multi-agent runs roughly 15x the tokens of a chat interaction, with token usage explaining most of the performance variance. Price it before you build it.

```python
MAX_WORKERS = 3
MAX_ITERATIONS = 6          # per worker; no worker runs unbounded

SUBTASKS = [
    ("pricing",   "Published pricing tiers and list prices for {c}."),
    ("funding",   "Funding rounds, amounts and dates for {c}."),
    ("headcount", "Published or reported employee count for {c}, with as-of date."),
]

async def research(company: str) -> str:
    results = await asyncio.gather(*[
        run_worker(name, tmpl.format(c=company), max_iterations=MAX_ITERATIONS)
        for name, tmpl in SUBTASKS[:MAX_WORKERS]
    ], return_exceptions=True)

    findings = [r for r in results if not isinstance(r, Exception)]
    if not findings:
        raise NoUsableFindings(company)
    return synthesise(company, findings, note_gaps=[n for n, r in zip(SUBTASKS, results)
                                                   if isinstance(r, Exception)])
```

Workers do not talk to each other — if they needed to, they would not be independent and this would collapse back to one agent. Failed workers degrade the brief and are named in it rather than silently dropped.
