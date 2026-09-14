# Hybrid Retrieval: Dense + BM25

## Why hybrid

Dense embeddings capture meaning but can miss exact strings. BM25 does lexical matching and catches many of those misses.

The canonical case:

```text
Error code TS-999
```

Embeddings may retrieve documents about error codes generally. BM25 finds the literal string.

Any corpus with identifiers, error codes, SKUs, version numbers, function names, ticket keys, API names, or file paths usually benefits from the lexical half.

## Standard pipeline

```text
dense retrieval
      +
BM25 retrieval
      ↓
RRF
      ↓
reranking
```

## Reciprocal Rank Fusion

RRF avoids having to normalize incompatible score scales:

```python
from collections import defaultdict

def reciprocal_rank_fusion(*ranked_lists, k: int = 60):
    scores = defaultdict(float)

    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] += 1.0 / (k + rank)

    return sorted(scores, key=scores.get, reverse=True)
```

```python
candidates = reciprocal_rank_fusion(
    vector_search(query, top_k=150),
    bm25_search(query, top_k=150),
)
```

Do not use weighted score blending without calibration. Dense and lexical scores are not on the same scale. RRF is a strong baseline because it avoids that normalization problem.

## BM25 tuning

Key parameters:

- **k1** (term frequency saturation): default 1.2–2.0. Higher = more weight on term frequency.
- **b** (length normalization): default 0.75. Higher = stronger penalty for long documents.

For technical corpora with many rare identifiers, slightly higher k1 can help. Measure on your eval set.

## Dense retrieval config

- Match embedding model to your domain (technical docs, support tickets, legal, etc.)
- Normalize vectors if using cosine distance with inner-product index
- Retrieve more candidates than you need (top_k=100–200) before fusion and reranking
- Apply metadata filters before or after retrieval depending on selectivity

## Metadata filtering

Pre-filter when filters are highly selective (e.g., `source=confluence AND space=platform`):

```python
candidates = vector_search(
    query,
    top_k=150,
    filters={"source": "confluence", "space": "platform"},
)
```

Post-filter when filters would eliminate too many candidates from a small result set. Measure filter selectivity on your corpus.

## Lexical index options

Whatever vector store you pick, you also need a lexical retrieval strategy if your corpus benefits from exact matching:

- PostgreSQL full-text search
- Elasticsearch / OpenSearch
- BM25 libraries (rank_bm25, tantivy)
- Provider-specific lexical indexes

A vector-only architecture is not hybrid retrieval.

## Dense-only failure mode

Dense-only retrieval can miss exact identifiers. If your eval set includes questions with error codes, ticket IDs, or function names, hybrid search is usually worth the complexity.
