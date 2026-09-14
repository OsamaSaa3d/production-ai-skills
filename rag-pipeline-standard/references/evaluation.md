# Evaluation

## Core diagnostic

The most useful property of RAG is that retrieval and generation fail differently. Measure them separately.

### Retriever metrics

```text
Contextual Relevancy
Contextual Precision
Contextual Recall
Recall@k
MRR
nDCG
```

### Generator metrics

```text
Answer Relevancy
Faithfulness
Correctness
Citation correctness
```

## Interpretation matrix

| Retriever | Generator | Likely fix |
|---|---|---|
| Low | High | Improve chunking, contextualization, hybrid search, reranking, query rewriting |
| High | Low faithfulness | Improve generation prompt or evidence formatting |
| Low | Low | Fix retrieval first |
| High | High | Measure latency, cost, robustness, and edge cases |

If the relevant evidence was never retrieved, changing the generation prompt cannot fix that. Do not treat retrieval failures as hallucination.

In agentic systems, also measure routing. A model that reliably retrieves from the wrong source can look good under generic retrieval metrics and still answer incorrectly.

## Build the eval set first

Build the evaluation set before tuning. Then sweep:

```text
chunk size
overlap
contextualization
retrieval top-k
BM25 top-k
rerank top-n
embedding model
query rewriting
full-document vs chunk-level generation
```

Stop when metrics plateau. Do not add pipeline complexity without measurement.

## Full-document vs chunk-level generation

Do not assume one strategy always wins. Compare explicitly:

```text
Strategy A: retrieve chunk → send chunk
Strategy B: retrieve chunk → identify document → send full document
Strategy C: retrieve chunk → identify document → send selected surrounding sections
Strategy D: retrieve chunks → rerank → send top chunks
```

Measure:

```text
answer quality
faithfulness
latency
input tokens
output tokens
cost
```

You may discover that:

- full documents are best for small technical docs,
- selected sections are best for medium documents,
- chunks are necessary for huge documents,
- structured queries are better for database-backed facts.

That is a much stronger decision framework than a universal "200K-token rule."

## What doesn't work (measurement perspective)

- **Building RAG solely because the corpus is "large".** Large relative to what? Architecture should be based on document size distribution + query relevance + context budget + latency + cost + answer quality.
- **Putting the entire corpus into every prompt.** Even when technically possible, this wastes input tokens, latency, attention, cost, and useful context capacity.
- **Passing too few chunks.** Evaluate the final evidence size instead of choosing a tiny default arbitrarily.
- **Unbounded agentic retrieval.** Agentic loops need iteration limits.
- **Mismatched distance operators and indexes.** Can quietly degrade query performance.

Use the `evals-before-shipping` skill for the harness and CI integration.
