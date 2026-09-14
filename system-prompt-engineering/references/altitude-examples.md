# Altitude Rewrites

The test in every case: **does this describe how to reason, or does it enumerate what to decide?** A rule that generalizes to an input you didn't write down is at the right altitude.

## Escalation policy

```text
# TOO LOW — brittle, and the fifteenth case is already missing
If sentiment is angry and tier is enterprise, escalate.
If sentiment is angry and tier is free, apologize and offer docs.
If the word "lawyer" appears, escalate.
If the word "cancel" appears and tier is enterprise, escalate.
If the customer has written more than 3 messages, escalate.
...

# TOO HIGH — no concrete signal; the model invents its own bar
Escalate when appropriate.

# RIGHT
Escalate when the cost of getting it wrong exceeds the cost of a human turn.
That means: legal or regulatory exposure, an irreversible financial action,
a customer who has explicitly asked for a person, or a second failed attempt
at the same issue. Enterprise accounts lower the bar; they do not remove it.
```

The right-altitude version handles "the customer mentioned their compliance team," which none of the fifteen rules did.

## Code review depth

```text
# TOO LOW
Require two approvals for src/auth/, src/payments/, src/billing/, and
src/admin/. Require one approval and a test for src/api/ and src/jobs/.
No approval for tests/, docs/, or *.md.

# RIGHT
Scale review requirements to blast radius. Code that handles authentication,
money movement, permissions, or data deletion is high-risk: two approvals and
a test that fails before the change. Everything else: one approval. Docs and
test-only changes: none. When a path's risk is unclear, treat it as high-risk
and say why.
```

The last sentence is the part people skip. A heuristic needs a stated default for the ambiguous case, or the model invents one silently.

## Response length

```text
# TOO LOW — a table the model has to look itself up in
1-10 lines changed: 3 sentences.
11-50 lines changed: 5 sentences.
51-200 lines: 8 sentences plus a heading.
...

# TOO HIGH
Be appropriately concise.

# RIGHT
Match length to what the reader has to verify. A small single-file change
needs 2-5 sentences and no headings. A multi-file change needs one or two
bullets per file. Never include before/after pairs or full method bodies —
reference the file and symbol instead.
```

Note that the right-altitude version still contains a precise, low-altitude clause ("never include before/after pairs"). That is correct: **output format is the section where low altitude belongs.** Altitude is per-section.

## Tool eagerness

```text
# TOO LOW — and it contradicts itself the moment traffic is real
Always call search for any question about products.
Never call search for greetings.
For questions with fewer than 5 words, do not call search.
Always call search when the user mentions a price.

# RIGHT
Call a tool when the answer depends on state you cannot know: account data,
current pricing, inventory, anything that changed since training. Answer
directly when the question is conceptual or procedural. If you are unsure
whether a fact is current, call the tool — a stale answer costs more than a
call. If you lack the arguments to call it, ask for what is missing rather
than guessing or passing nulls.
```

The final clause is not optional. An absolute tool rule without an escape hatch produces hallucinated and null arguments.

## Data handling

```text
# TOO HIGH — sounds like a policy, constrains nothing
Handle customer data responsibly.

# RIGHT
Treat any field that could identify a person as need-to-know. Include it in a
response only when the user's request cannot be satisfied without it, and
never in a log line, an error message, or a summary. When you need to refer to
a record, use its ID.
```

## When low altitude is correct

Enumerate when the enumeration *is* the requirement and a wrong answer is not recoverable by judgment:

- **Regulatory disclosures.** The exact sentence is the deliverable.
- **Output schemas and enum values.** These are contracts. Prefer expressing them in a structured-output schema rather than prose — see `structured-output`.
- **Preconditions with legal or financial consequence.** "Refunds over $500 require a human" is a threshold, not a heuristic.
- **Small models.** Less capacity to absorb ambiguity. Explicit scaffolding buys real accuracy; see `model-selection`.

The distinction: heuristics for judgment, enumeration for contracts.

## Rewriting an existing brittle prompt

1. Group the rules by the decision they influence. Fifteen rules usually collapse to three decisions.
2. For each group, write the one sentence a competent new hire would need. That sentence is the heuristic.
3. Keep any rule from the group that the heuristic genuinely does not imply — usually a threshold or a legal requirement.
4. Delete the rest.
5. Run your failure set. Anything that regresses tells you which deleted rule was load-bearing; add it back as a *stated exception* to the heuristic, not as a peer rule.

Step 5 is what makes this safe. Without a failure set, the rewrite is a guess that reads better.
