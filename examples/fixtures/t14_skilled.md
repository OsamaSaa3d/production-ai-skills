You just wrote down the steps — read, dedupe, label, route. That is a workflow, and the steps belong in your code rather than being rediscovered by a model on every issue. Handing a fixed procedure to an agent is slower, costlier and less reliable than a for-loop.

```python
def triage(issue_id: str) -> dict:
    issue = github.get_issue(issue_id)                      # 1. read

    candidates = search_index(issue.title, top_k=5)         # 2. dedupe
    dup = classify(DEDUPE_PROMPT, issue, candidates, schema=Duplicate)
    if dup.is_duplicate:
        return github.close_as_duplicate(issue_id, dup.of_issue)

    sev = classify(SEVERITY_PROMPT, issue, schema=Severity) # 3. label
    github.set_label(issue_id, sev.level)

    team = ROUTING.get(sev.component, "triage-queue")        # 4. route — a dict, not a model
    github.assign(issue_id, team)
    return {"severity": sev.level, "team": team}
```

Two of the four steps do not need a model at all. Routing is a lookup table, and closing a duplicate is an API call. Only dedupe and severity are judgement calls, and each is a single constrained call you can eval independently — which you cannot do with one opaque loop.
