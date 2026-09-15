# Three Worked Examples

> **Verify before you build.** Parameter names, limits, and model support named below move between releases. Check the provider's current API reference before relying on them, and correct any drift with the smallest possible edit.

> **The numbers in this file are illustrative.** They show the *shape* of the improvement each change produces and the arithmetic that would reveal it — they are not published measurements from a named corpus, and you should not quote them. Each example states the corpus and assumptions that produce that shape, and ends with the conditions under which it does not hold. Your own eval set is the only source of a number you can defend.

Each example follows the same five parts: **Baseline**, **Failure**, **Change**, **Measurement**, **Result**. The measurement sections use the metric names from `evals-before-shipping/references/rag-suite.md` so the two files describe one harness rather than two vocabularies.

---

## 1. Naive chunk retrieval to document-level retrieval

**Corpus assumed:** ~1,800 internal engineering pages. Token distribution p50 ≈ 1,400, p95 ≈ 6,200, max ≈ 74,000. Context budget after system prompt, tools, history, and reserved output: ~40,000 tokens.

That distribution is the reason this change works here. Most documents fit the budget whole; only the tail does not.

### Baseline

Fixed-size chunks, embedded, top-5 chunks concatenated into the prompt.

```python
CHUNK_TOKENS = 512

def answer(query: str) -> str:
    hits = vector_search(query, top_k=5)
    context = "\n\n---\n\n".join(h.chunk_text for h in hits)
    return generate(query, context)
```

Nothing is wrong with the retrieval here. The chunk that comes back is genuinely the most relevant chunk.

### Failure

> **"Do we still require two approvals for changes under `services/payments/`?"**

The top hit is exactly the right chunk:

```text
All changes to services/payments/ require two approving reviews
before merge. Reviewers must not be the author.
```

The answer generated from it — "yes, two approvals" — is confident, grounded, and wrong. Two chunks later in the same document:

```text
## Exceptions
Reverts of a commit that is already on main require one approval.
Automated dependency bumps require none.
```

The chunk boundary cut the rule away from its exceptions. This failure is invisible to a generation-side review: the model was faithful to the context it received. It is also invisible to `FaithfulnessMetric`, which asks whether claims are grounded in `retrieval_context` — and they were.

### Change

Keep chunks as retrieval pointers. Resolve them to documents, and send whole documents while the budget allows. The full pattern, storage layout, and multi-document budget accounting are in [document-level-retrieval.md](document-level-retrieval.md); the version below is the minimum that produces the measurement.

```python
def answer(query: str, budget: int) -> str:
    hits = vector_search(query, top_k=10)

    seen, context, used = set(), [], 0
    for hit in hits:
        doc_id = hit.metadata["document_id"]
        if doc_id in seen:
            continue
        seen.add(doc_id)

        doc = document_store.get(doc_id)
        doc_tokens = count_tokens(doc.content)

        if used + doc_tokens <= budget:
            context.append(doc.content)
            used += doc_tokens
        else:
            for chunk in chunks_for(doc_id, hits):
                context.append(chunk.chunk_text)
                used += count_tokens(chunk.chunk_text)

    return generate(query, "\n\n---\n\n".join(context))
```

Retrieval is untouched. Only what gets sent to the generator changed, which is what makes the measurement clean.

### Measurement

`ContextualRecallMetric` is the metric that moves, because the question is whether the evidence needed to answer arrived — not whether what arrived was relevant.

Recall needs ground truth, so the goldens carry `expected_output`. Build them by splitting the set into two classes and scoring each separately:

| Golden class | How to build it | Why it is here |
|---|---|---|
| Answer in one contiguous passage | Pull from the support queue; confirm one chunk carries the whole answer | Control — should not move |
| Answer needs two sections of one document | Rules with exceptions, definitions used later, "except" and "unless" clauses | The class this change targets |

```python
for strategy_name, retrieve in {"chunks": chunk_only, "documents": doc_level}.items():
    for cls, goldens in GOLDEN_CLASSES.items():
        cases = [
            LLMTestCase(
                input=g.input,
                actual_output=generate(g.input, retrieve(g.input)),
                retrieval_context=retrieve(g.input),   # what was ACTUALLY sent
                expected_output=g.expected_output,
            )
            for g in goldens
        ]
        report(strategy_name, cls, evaluate(cases, [ContextualRecallMetric()]))
```

Report input tokens per query and p95 latency in the same table. This change buys recall with tokens, and a recall number without the token number is half the result.

### Result

Illustrative shape on the corpus described above:

| | Contiguous-answer class | Split-answer class | Input tokens / query | p95 latency |
|---|---|---|---|---|
| Chunks only | flat | **low** | ~2.5K | baseline |
| Document-level | flat | **large gain** | ~4-6x baseline | +200-400ms |

The control class staying flat is the part that makes the result believable. If both classes move, something other than the chunk boundary changed and the experiment is not isolating what you think.

`FaithfulnessMetric` typically moves very little — it was already high, because the generator was faithfully reporting incomplete evidence. Watching faithfulness alone would have reported this system as healthy.

**When this does not hold.** A corpus whose p95 exceeds the budget falls back to chunks on most queries, so you pay the document-store round trip for nothing. Documents that are collections of unrelated records — a changelog, a ticket export, a FAQ dump — have no surrounding context worth fetching, and sending the whole thing dilutes the evidence instead of completing it. And a smaller generation model can score *worse* with full documents than with chunks: more irrelevant text in the window is more to be distracted by. Compare the strategies rather than assuming; [evaluation.md](evaluation.md) lists the four to put side by side.

---

## 2. Dense-only to hybrid BM25 + dense

**Corpus assumed:** a support knowledge base plus an exported ticket archive. Roughly a third of real user queries contain a literal identifier — an error code, a ticket key, a SKU, a config key, a function name.

That third is the entire reason this change pays. On a corpus of narrative prose it would not.

### Baseline

Dense retrieval only, over a single embedding index.

```python
def retrieve(query: str, k: int = 20):
    return vector_search(query, top_k=k)   # cosine over one embedding index
```

### Failure

> **"Why does TS-999 fire during checkout?"**

Retrieved context, all five hits:

```text
1. "Handling payment errors" (general error-handling guidance)
2. "Checkout troubleshooting overview"
3. "Common error codes and what they mean" (a landing page, no TS-999)
4. "Retry behavior for declined cards"
5. "Escalation paths for checkout incidents"
```

The one page titled `TS-999: card tokenization timeout` is not in the list. Embeddings placed the query near the *topic* of checkout errors; `TS-999` is a rare token carrying almost no semantic weight, so the one document that contains the literal string ranks below five documents that are broadly about the subject.

This is the failure mode that looks worst to users and best to a dashboard: the retrieved context is plausibly on-topic, so relevancy scores stay respectable while the answer is useless.

### Change

Add a lexical index and fuse with Reciprocal Rank Fusion. RRF is used rather than weighted score blending because dense similarity and BM25 scores are not on a common scale; see [retrieval-bm25-dense-hybrid.md](retrieval-bm25-dense-hybrid.md) for BM25 parameter tuning and index options.

```python
from collections import defaultdict

def reciprocal_rank_fusion(*ranked_lists, k: int = 60):
    scores = defaultdict(float)
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] += 1.0 / (k + rank)
    return sorted(scores, key=scores.get, reverse=True)

def retrieve(query: str, k: int = 20):
    return reciprocal_rank_fusion(
        vector_search(query, top_k=150),
        bm25_search(query, top_k=150),
    )[:k]
```

Both arms retrieve far more candidates than the final `k`. Fusion needs depth to work with — a 20-deep BM25 list contributes almost nothing.

### Measurement

**Do not report one aggregate number.** Identifier queries are a minority of most golden sets and a majority of the complaints, so an aggregate recall figure moves a couple of points and hides the change entirely.

Tag every golden with a class and score per class:

```python
CLASSES = {
    "identifier": [g for g in GOLDENS if IDENT_RE.search(g.input)],
    "conceptual": [g for g in GOLDENS if not IDENT_RE.search(g.input)],
}
```

Two metrics, for two different questions:

- `ContextualRecallMetric` — did the page containing the identifier come back at all? This is the primary metric and the one the identifier class exists to move.
- `ContextualRelevancyMetric` — is the fused context still on-topic? This is the guard. BM25 can drag in documents that share a token and nothing else, and a recall gain paid for with a relevancy collapse is not a win.

Record p95 latency: you are now running two searches plus a fusion pass, and on a managed lexical index that second search may dominate.

### Result

Illustrative shape:

| Golden class | `ContextualRecallMetric` | `ContextualRelevancyMetric` |
|---|---|---|
| Identifier-bearing | **large gain** — the failure was categorical, and BM25 fixes it categorically | roughly flat |
| Conceptual | flat, occasionally slightly down | roughly flat |

The asymmetry *is* the result. Hybrid search does not make semantic retrieval better; it adds a second retrieval mode that succeeds exactly where the first one structurally cannot. Expect the conceptual class to dip slightly — RRF gives the lexical arm rank positions it may not deserve on a purely semantic query — and decide whether that trade is acceptable on your traffic mix rather than assuming it is free.

**When this does not hold.** A corpus with no identifiers gains nothing and pays the latency. If your embedding model already handles rare tokens well on your domain, the gap is smaller than the canonical example suggests — measure before building the second index. And the failure mode to watch is index skew: if the lexical index is rebuilt on a different schedule than the vector index, hybrid retrieval starts returning documents one arm believes exist and the other does not, which is harder to debug than dense-only ever was.

---

## 3. Raw follow-up to contextual query rewrite

**System assumed:** a multi-turn support chat. Roughly half of all turns are follow-ups that depend on the previous turn for their subject.

### Baseline

The latest user message goes straight to the retriever.

```python
def turn(history, message):
    hits = retrieve(message)          # the raw message, with no history
    return generate(message, history, hits)
```

The generator sees the conversation. The retriever does not. That asymmetry is the bug, and it is easy to miss because the code reads as though history is handled.

### Failure

```text
User: What's our refund policy for enterprise customers?
Bot:  Enterprise customers have a 60-day refund window.
User: What about annual plans?
```

`retrieve("What about annual plans?")` returns pricing pages: annual billing discounts, annual vs monthly comparison, invoice scheduling. Not one refund document. "Refund" does not appear in the query, so nothing scores it — dense or lexical, both arms fail identically here, which is why example 2 does not help with this one.

The generated answer is usually worse than a straight miss: it has the previous turn in history, so it produces something about annual plans that *sounds* continuous while citing pricing documents that say nothing about refunds.

### Change

Rewrite the latest message into a standalone query before retrieving. A small, cheap model is enough. Decomposition and expansion variants are in [query-rewriting.md](query-rewriting.md).

```python
REWRITE_PROMPT = """Given the conversation, rewrite the user's latest message as a
standalone search query that makes sense without the conversation. Keep the user's
terminology and any identifiers exactly as written. If the message is already
self-contained, return it unchanged.

Conversation:
{history}

Latest message:
{message}

Standalone query:"""

def turn(history, message):
    search_query = rewrite(history, message)
    # -> "refund policy for annual enterprise plans"
    hits = retrieve(search_query)
    return generate(message, history, hits)
```

Note "Keep the user's terminology and any identifiers exactly as written." Without that line the rewriter paraphrases, and a paraphrased `TS-999` is a destroyed BM25 match. The two changes in this file interact.

### Measurement

Goldens for a rewriter are conversations, not strings. Each carries the prior turns, the follow-up message, and the `expected_output` the corpus can support.

Score by turn class, and note that one of the classes is a regression guard rather than a target:

| Turn class | Metric | Expectation |
|---|---|---|
| Follow-up missing its subject | `ContextualRecallMetric` | Large gain — the target |
| Pronoun reference ("that feature", "the same issue") | `ContextualRecallMetric` | Gain |
| Already self-contained | `ContextualRecallMetric` | **Must stay flat** |
| Contains a literal identifier | `ContextualRecallMetric` | **Must stay flat** |
| All classes | `AnswerRelevancyMetric` | Gain on follow-ups, flat elsewhere |

The last two rows are the whole discipline here. A rewriter is a second model in the retrieval path, and it can make queries worse in ways that are silent — over-specifying a query that was already fine, or normalizing an error code into prose. Assert pass-through explicitly:

```python
def test_self_contained_passthrough(golden):
    assert rewrite(golden.history, golden.message).strip() == golden.message.strip()
```

That is a plain string assertion, not a judge call, and it will catch the regression long before a recall average does.

### Result

Illustrative shape:

| Turn class | Recall change | Note |
|---|---|---|
| Follow-up missing subject | **large gain** | The baseline was near-total failure, not partial |
| Already self-contained | flat | If this moves, the rewriter is over-editing |
| Identifier-bearing | flat | If this drops, the rewriter is paraphrasing identifiers |

Cost: one extra model call per turn, typically tens of milliseconds to a couple hundred on a small model, on every turn including the ones that needed nothing.

**When this does not hold.** Single-turn systems gain nothing. In an agentic setup the model often reformulates as part of its own reasoning, and an explicit rewriter on top of that is a second opinion you did not need — see [agentic-retrieval.md](agentic-retrieval.md). And where user vocabulary is load-bearing, an aggressive rewriter is a net loss: it makes conceptual queries cleaner and identifier queries unmatched, so the aggregate stays flat while your worst failures get worse.

---

## Reading these together

Three changes, one method. In each case the baseline was a reasonable implementation, the failure was a specific query rather than a vibe, the change was narrow enough that one metric was expected to move, and a control class was measured to prove nothing else did.

The controls are the part that transfers. Without the contiguous-answer class in example 1, the conceptual class in example 2, and the pass-through class in example 3, each of these would have been a plausible improvement with no evidence that it was not also a regression somewhere else.

Metric definitions, thresholds, and the diagnostic table that tells you which of these three to reach for: `evals-before-shipping/references/rag-suite.md`.
