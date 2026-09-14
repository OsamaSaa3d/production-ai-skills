# Agentic Retrieval

## Single-shot vs agentic

**Single-shot RAG:**

```text
one query → one retrieval pass → one answer
```

A **workflow**. Handles direct lookups well. Cheap and predictable.

**Agentic retrieval** gives the model control over:

- whether to search,
- what to search for,
- which corpus to search,
- whether more evidence is needed,
- whether to search again.

That is an **agent**, with corresponding cost and latency.

## Example

```text
User: "Why does checkout fail for EU customers and is it a known issue?"

Agent:
    → search_confluence_docs("checkout payment flow EU")
    → search_jira_issues("checkout failure EU", status="open")
    → search_jira_issues("VAT validation error")
    → synthesize
```

## When to use agentic retrieval

- the question spans multiple corpora,
- the right query depends on what is discovered,
- the question is compound,
- one retrieval pass frequently comes back insufficient.

## When to stay single-shot

- questions are direct lookups,
- latency matters more than completeness,
- one pass already answers reliably.

## Guardrails

**Cap retrieval iterations.** Unbounded agentic retrieval wastes tokens and latency. Set a max (typically 3–5 retrieval calls).

**Watch context growth.** Every retrieval result that remains in the parent transcript consumes context. For complex searches, a retrieval subagent can run several searches inside its own context and return a compact evidence summary to the parent.

**Measure routing.** In agentic systems, a model that reliably retrieves from the wrong source can look good under generic retrieval metrics and still answer incorrectly.

## Retrieval subagent pattern

When the parent agent needs evidence from multiple corpora but shouldn't accumulate raw chunks in its context:

```text
Parent agent → spawns retrieval subagent with query
    → subagent runs multiple searches, reads results
    → returns compact evidence summary (not raw chunks)
Parent agent → synthesizes answer from summary
```

This keeps the parent context clean while allowing thorough search.

## Cost comparison

| Pattern | Latency | Cost | Best for |
|---|---|---|---|
| Single-shot | Low | Low | Direct lookups |
| Agentic (2-3 iterations) | Medium | Medium | Multi-corpus, compound questions |
| Retrieval subagent | Medium-High | Medium | Complex evidence gathering |

Measure on your task distribution before choosing.
