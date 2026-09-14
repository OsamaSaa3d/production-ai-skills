# Query Rewriting

## The problem

Retrieval sees the search query, not necessarily the full conversation. This breaks multi-turn systems.

```text
User: What's our refund policy for enterprise customers?
Bot: [answers]
User: What about annual plans?
```

Searching `"What about annual plans?"` is weak because the subject is missing.

## Rewriting

Rewrite the latest message into a standalone search query before retrieving:

```python
REWRITE_PROMPT = """Given the conversation, rewrite the user's latest message as a
standalone search query that makes sense without the conversation. Keep the user's
terminology. If the message is already self-contained, return it unchanged.

Conversation:
{history}

Latest message:
{message}

Standalone query:"""

search_query = rewrite(history, message)
# → "refund policy for annual enterprise plans"
```

A small model is often sufficient here.

## Decomposition

Split a compound question into multiple retrieval queries:

```text
"How do I set up SSO and what's the rollout timeline?"
```

becomes:

```text
"How do I set up SSO?"
"What's the rollout timeline?"
```

Run each query separately, fuse or deduplicate results, then pass combined evidence to the generator.

## Expansion

Generate query variants to increase recall, then fuse the results:

```text
Original: "payment retry failure"
Variants:
  "failed payment retry mechanism"
  "retry policy when payment fails"
  "payment processing retry error handling"
```

Useful when terminology varies across your corpus. Adds latency — measure whether recall improvement justifies it.

## Agentic vs explicit

In an agentic setup, the model may do rewriting, decomposition, and expansion implicitly through its reasoning.

In a single-shot pipeline, implement them explicitly when evaluation shows a benefit.

## Evaluation

Evaluate query rewriting separately. A rewrite that sounds better but retrieves worse documents is not an improvement.

Test cases:

- Follow-up questions missing subject from prior turn
- Pronoun references ("that feature", "the same issue")
- Compound questions requiring decomposition
- Already self-contained queries (rewrite should pass through unchanged)

Measure retrieval recall before and after rewriting on each case type.
