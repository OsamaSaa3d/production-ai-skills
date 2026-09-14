# Reranking

## Role in the pipeline

Retrieval optimizes for recall. A reranker optimizes for relevance.

A cross-encoder processes the query and candidate text together and can judge their relationship much more precisely than basic embedding similarity comparison.

```text
retrieve candidate chunks → RRF fusion → rerank → final context
```

For document-level retrieval:

```text
retrieve candidate chunks → identify candidate documents → deduplicate
→ rerank documents or evidence → load full documents when they fit
→ otherwise use relevant chunks
```

## Implementation

```python
reranked = reranker.rerank(
    query=query,
    documents=candidates[:150],
    top_n=20,
)

context = [c.text for c in reranked]
```

Do not blindly assume that `20` is universally optimal. Treat these as evaluation parameters:

```text
retrieval_top_k
rerank_top_n
final_context_size
```

## Hosted vs local rerankers

**Hosted** (Cohere Rerank, Voyage, Jina): no GPU ops, pay per request, good default for most teams.

**Local** (cross-encoder models via sentence-transformers): no per-request cost, requires GPU for latency, good at scale.

Benchmark both on your eval set including latency budget.

## Top-n sweeps

Run sweeps on your eval set:

```text
rerank_top_n: 5, 10, 20, 50
```

More candidates to the reranker = better relevance but higher latency. Fewer final results = less context for generation but potentially higher precision.

## Latency budgeting

Typical latencies:

- Embedding search: 10–50ms
- BM25 search: 5–20ms
- Cross-encoder rerank (150 docs): 100–500ms depending on model and hardware

If latency budget is tight, rerank fewer candidates or use a smaller cross-encoder. Measure end-to-end, not per-stage in isolation.

## Passing too few chunks

Do not choose `top_k=3` or `top_n=5` simply because it looks tidy. Measure it. Some questions require evidence from multiple documents or distant sections within one document.
