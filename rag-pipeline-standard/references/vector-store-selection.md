# Vector Store and Index Selection

## Default choice

This is infrastructure, and it matters less than retrieval quality. Don't over-invest here.

**Default: use the database you already run.**

`pgvector` gives you:

- transactions,
- joins against existing tables,
- metadata filtering,
- one system to operate.

Most corpora are well below the scale where a dedicated vector database automatically earns its operational cost.

Do not reach for a vector database by default. Start with existing infrastructure until measurements show something else is justified.

## Distance operators

Pick the metric matching how your embedding model was trained. Keep operator, index operator class, and `ORDER BY` in agreement. A mismatch can prevent the expected index from being used.

| Operator | Metric | Notes |
|---|---|---|
| `<=>` | Cosine distance | Common default |
| `<#>` | Negative inner product | Equivalent to cosine for normalized vectors |
| `<->` | L2 / Euclidean | |
| `<+>` | L1 / Manhattan | |

Many embedding providers return normalized vectors. When vectors are normalized, cosine and inner-product ranking are equivalent.

## Index types

Without an index, pgvector performs exact nearest-neighbor search. Perfect recall, adequate at smaller scale.

Approximate indexes trade some recall for speed.

### HNSW

Builds a navigable multilayer graph.

- **Advantages:** strong speed/recall tradeoff, no training step, incremental insertion, good general default
- **Costs:** higher memory, slower build, tuning still matters
- **Tune:** `hnsw.ef_search`

### IVFFlat

Partitions vectors into clusters around centroids.

- **Advantages:** faster builds, lower memory footprint
- **Costs:** requires representative data before building, clustering degrades when data distribution changes, more operational tuning
- **Tune:** `ivfflat.probes`

**Default to HNSW** unless measurements give you a reason to use IVFFlat. Use IVFFlat when build time and memory dominate at very large scale.

Set tuning parameters locally inside transactions when using connection pools rather than relying on leaking session-level settings.

## Scale

Vector indexes can become memory-heavy. As scale increases, consider:

- lower-precision vectors (halfvec),
- compressed representations,
- approximate indexes,
- disk-oriented ANN solutions (DiskANN),
- partitioning where appropriate.

Do not choose infrastructure based only on database row count. Measure:

```text
index size
RAM consumption
query latency
recall
write cost
build time
filter selectivity
```

## Embedding model selection

Embedding quality generally matters more than vector-store brand. Benchmark two or three plausible embedding models on your own evaluation set.

Measure:

```text
Recall@k
MRR
nDCG
latency
embedding cost
index size
```

Do not choose a model solely because it performs well on a public benchmark. Your identifiers, terminology, document styles, and question distribution may be very different.

## Hybrid indexing per store

Whatever vector store you pick, you also need a lexical retrieval strategy if your corpus benefits from exact matching. Options include PostgreSQL full-text search, Elasticsearch, OpenSearch, BM25 libraries, or provider-specific lexical indexes.

A vector-only architecture is not hybrid retrieval.
