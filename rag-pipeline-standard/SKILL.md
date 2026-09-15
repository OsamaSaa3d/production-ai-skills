---
name: rag-pipeline-standard
description: Builds and fixes retrieval over private data — knowledge bases, docs search, support bots, and RAG pipelines. Use when someone mentions RAG, vector databases, embeddings, semantic search, or chunking; or when retrieval returns irrelevant chunks, misses exact matches like error codes or ticket IDs, answers from the wrong source, or breaks on follow-up questions. Covers RAG vs tool calling vs direct context, document-level and contextual retrieval, hybrid search, reranking, and query rewriting.
version: 1.0
---

# RAG Pipeline Standard

> **Provider-neutral.** The practice here applies to any LLM provider. Code samples name one provider's syntax to stay concrete; equivalents exist elsewhere under different names, and genuinely provider-specific features are labelled where they appear.
>
> **Verify before you build.** Endpoint shapes, parameter names, limits, and model support all move. Search the provider's current API reference before relying on any of them. If something here is stale, make the *smallest* edit that corrects it — replace the outdated token, leave the surrounding argument intact.

## Core principle

The useful question is not "does the corpus fit in the context window?" It is:

> **How much context can you safely provide for a typical request while leaving room for output and instructions — and how much of the corpus is actually relevant to each request?**

A corpus can fit in the window and still be wrong to load entirely on every request. Context-window capacity is an upper bound, not a prompt-size target.

Build the evaluation set before tuning. Add pipeline layers in order and stop when evals say you're done. Measure retrieval and generation separately — they fail differently.

## Avoid / Prefer

| Avoid | Prefer |
|---|---|
| Context-window size as the retrieval threshold | A budget computed from the actual model |
| Embedding structured records | A query tool over typed fields |
| Dense-only search | Dense + BM25, fused with RRF |
| The chunk as final generation context | The chunk as a pointer to its document |
| One blended index over distinct sources | One retrieval tool per corpus |
| The raw follow-up message as the query | A rewritten standalone query |
| A vector database by default | The database you already operate |

These are defaults for the common case; each section below names the conditions that flip it.

## Minimal pattern

```text
Is retrieval the right mechanism at all?
    |
    v
Measure document sizes; compute a context budget
    |
    v
Chunk on structure; index dense + BM25 with document metadata
    |
    v
Retrieve, fuse with RRF, rerank
    |
    v
Resolve chunks to documents; fill the budget
    |
    v
Score retriever and generator separately before adding another layer
```

Everything below is the deep dive: when each step is wrong, and what to do instead.

## When to use this skill

- Building or fixing a knowledge base assistant, docs search, or support bot
- Choosing between RAG, direct context, tool calling, or a hybrid
- Retrieval returns irrelevant chunks, misses exact identifiers, or pulls from the wrong source
- Multi-turn follow-ups break because the search query lacks conversation context
- Tuning chunking, hybrid search, reranking, or vector index configuration
- Splitting multiple corpora (Jira + Confluence, tickets + docs) into retrieval tools

## Choose the right mechanism

| Your data / workload | Default | Why |
|---|---|---|
| Small amount of relevant unstructured text | **Put relevant data directly in the prompt** | No retrieval when context is already small |
| Moderate corpus, each document fits safely in context | **Retrieve chunks, load full matching document** | Chunk finds the doc; generation gets full context |
| Large corpus, documents too large to pass safely | **RAG** | Retrieve relevant chunks only |
| Structured — SQL, CSV, API, spreadsheets | **Tool calling, not RAG** | Structure is the query interface |
| Both structured + unstructured | **Both, as separate tools** | Query fields with tools; retrieve text separately |

Do **not** use a fixed rule like "under 200K tokens means put everything in the prompt."

Calculate a context budget from the **actual model**:

```text
available_input_budget =
    model_context_window
    - system_and_tool_tokens
    - conversation_history_tokens
    - reserved_output_tokens
    - safety_margin
```

Only load a document directly when its token count fits comfortably inside that budget. Leave headroom — do not fill the window to the edge.

For a document corpus, measure token distribution (p50, p95, p99, max), not just averages. A corpus with 2,500-token average and 74,000-token max needs a strategy for the tail.

**Rule of thumb:** If the question has a computable answer (count, sum, filter, sort, join), it needs a query tool, not similarity search.

For worked examples and the full decision framework, see [references/rag-vs-tools.md](references/rag-vs-tools.md).

## Standard pipeline

Copy this checklist and track progress:

```text
Task Progress:
- [ ] Confirm retrieval is the right mechanism (not tools or direct context)
- [ ] Measure document token distribution and set context budget
- [ ] Index: structure-aware chunking → optional contextualization → embeddings + BM25
- [ ] Query: optional query rewrite → dense + BM25 → RRF → rerank → context selection
- [ ] Split distinct corpora into separate retrieval tools
- [ ] Build eval set; measure retriever and generator separately
- [ ] Sweep parameters; stop when evals plateau
```

Baseline flow:

```text
Indexing:
    documents → structure-aware chunking → optional contextualization
    → embeddings + BM25/lexical index → source-document metadata

Query time:
    query → optional query rewriting → dense search + BM25 search
    → RRF fusion → reranking → document/chunk selection
    → context-budget decision → LLM
```

Do not assume every system needs every layer. Start simple, measure, add complexity only when evaluation shows it helps.

Three of these layers worked end to end — the baseline, the query that broke it, the change, and the measurement that justified keeping it: [references/worked-examples.md](references/worked-examples.md).

## Document-level retrieval

When documents are small-to-moderate, use chunks as **retrieval pointers**, not necessarily as final generation context:

```text
Chunk for retrieval → retrieve relevant chunks → extract document_id
→ fetch full document → check token budget → pass full doc or fall back to chunks
```

Store the original document separately from the retrieval index. Each chunk carries metadata linking back:

```python
{
    "chunk_id": "doc_184_chunk_07",
    "document_id": "doc_184",
    "document_title": "Payment Retry Architecture",
    "source": "confluence",
    "section": "Retry Policy",
    "chunk_text": "...",
}
```

At query time, deduplicate document IDs from retrieved chunks, fetch full documents, then choose per document:

```python
def choose_context(document, relevant_chunks, budget):
    if count_tokens(document.content) <= budget:
        return {"mode": "full_document", "content": document.content}
    return {"mode": "retrieved_chunks", "content": [c.text for c in relevant_chunks]}
```

For multiple documents, account for the **combined** budget — stop adding full documents when the next one would exceed it.

Full pattern, storage layout, and selection logic: [references/document-level-retrieval.md](references/document-level-retrieval.md).

## Structured data: use tools, not RAG

If data lives in a database, CSV, or API, do not embed it. Embedding rows destroys the structure that makes the data answerable.

> "How many P1 tickets did the platform team open last month?" → `COUNT` with `WHERE`. Not semantic search over embedded rows.

Use RAG for unstructured text attached to structured records (descriptions, comment threads, notes). Those are two tools, not one blended index.

**Build that tool to take typed fields, not a query string.** Describing a query syntax in the prompt and letting the model emit it gives up constrained decoding and turns user-controlled text into something you execute. See `tool-design`.

## Indexing: chunk, then contextualize

Chunking destroys context — a chunk reading "revenue grew by 3%" names neither the company nor the quarter.

**Contextual Retrieval** prepends a chunk-specific note before indexing:

```python
CONTEXTUALIZE_PROMPT = """<document>{document}</document>
Here is a chunk from that document:
<chunk>{chunk}</chunk>
Write a short, self-contained note situating this chunk within the document.
Name entities, dates, and section. Answer with the note only."""

indexed_text = f"{contextual_context}\n\n{chunk}"
```

Store the original chunk separately. The contextualized version improves retrieval; the original remains source material.

**Chunking defaults:** a few hundred to ~800 tokens, split on natural boundaries, preserve headings/sections, modest overlap. Treat chunk size as a tunable eval parameter.

Full indexing pipeline, metadata strategy, and prompt caching: [references/contextual-retrieval.md](references/contextual-retrieval.md). Chunking per format: [references/chunking.md](references/chunking.md).

## Retrieval: hybrid by default

Dense embeddings capture meaning but miss exact strings. BM25 catches identifiers, error codes, SKUs, version numbers, ticket keys, function names.

```text
dense retrieval + BM25 retrieval → RRF → reranking
```

```python
from collections import defaultdict

def reciprocal_rank_fusion(*ranked_lists, k: int = 60):
    scores = defaultdict(float)
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] += 1.0 / (k + rank)
    return sorted(scores, key=scores.get, reverse=True)
```

RRF avoids normalizing incompatible score scales. Do not use weighted score blending without calibration.

Rerank retrieved candidates down to a smaller final set. A cross-encoder judges query-candidate relevance more precisely than embedding similarity. Treat `retrieval_top_k`, `rerank_top_n`, and `final_context_size` as eval parameters — do not assume `top_k=3` or `top_n=20` universally.

Details: [references/retrieval-bm25-dense-hybrid.md](references/retrieval-bm25-dense-hybrid.md), [references/reranking-cross-encoder.md](references/reranking-cross-encoder.md).

## Split distinct corpora into separate tools

Do not blend genuinely distinct sources into one index. Jira issues and Confluence pages are two corpora → two tools.

```python
tools = [
    {
        "name": "search_jira_issues",
        "description": (
            "Search Jira tickets: bug reports, feature requests, comment threads. "
            "Use for specific problems, what was reported, or work in progress."
        ),
        "input_schema": {"properties": {"query": {"type": "string"}, ...}},
    },
    {
        "name": "search_confluence_docs",
        "description": (
            "Search Confluence documentation: architecture docs, runbooks, policies. "
            "Use for how something works or what the official process is."
        ),
        "input_schema": {"properties": {"query": {"type": "string"}, ...}},
    },
]
```

Two to five retrieval tools is often reasonable. Twenty is usually a smell. Split on genuinely distinct sources, not every folder.

## Agentic vs single-shot retrieval

**Single-shot** (one query → one retrieval → one answer): direct lookups, latency-sensitive, one pass already answers reliably.

**Agentic** (model decides whether/how/where to search, may iterate): questions spanning multiple corpora, compound questions, query depends on what is discovered.

Cap retrieval iterations. Watch context growth — every result in the parent transcript consumes context. For complex searches, a retrieval subagent can run several searches and return a compact evidence summary.

Details: [references/agentic-retrieval.md](references/agentic-retrieval.md).

## Query rewriting

Retrieval sees the search query, not the full conversation. "What about annual plans?" after a refund-policy question is weak without context.

Rewrite the latest message into a standalone search query before retrieving:

```python
REWRITE_PROMPT = """Given the conversation, rewrite the user's latest message as a
standalone search query. Keep the user's terminology. If already self-contained,
return unchanged.

Conversation: {history}
Latest message: {message}
Standalone query:"""
```

Also useful: **decomposition** (split compound questions into multiple queries) and **expansion** (generate query variants, fuse results). Evaluate rewriting separately — a rewrite that sounds better but retrieves worse is not an improvement.

Details: [references/query-rewriting.md](references/query-rewriting.md).

## Vector store and embeddings

**Default: use the database you already run.** `pgvector` gives transactions, joins, metadata filtering, and one system to operate. Most corpora are well below the scale where a dedicated vector DB earns its operational cost.

Pick the distance operator matching how your embedding model was trained. Keep operator, index operator class, and `ORDER BY` in agreement. Default to HNSW unless measurements favor IVFFlat.

Embedding quality matters more than vector-store brand. Benchmark 2-3 models on your own eval set — do not choose from public benchmarks alone.

Details: [references/vector-store-selection.md](references/vector-store-selection.md).

## Evaluation

Measure retriever and generator separately:

| Retriever | Generator | Likely fix |
|---|---|---|
| Low | High | Chunking, contextualization, hybrid search, reranking, query rewriting |
| High | Low faithfulness | Generation prompt or evidence formatting |
| Low | Low | Fix retrieval first |
| High | High | Latency, cost, robustness, edge cases |

Sweep: chunk size, overlap, contextualization, retrieval top-k, BM25 top-k, rerank top-n, embedding model, query rewriting, full-document vs chunk-level generation.

Compare strategies explicitly — full document vs chunk vs selected sections — on your corpus. Do not assume one always wins.

Details: [references/evaluation.md](references/evaluation.md). Use the `evals-before-shipping` skill for the harness.

## Pitfalls

- **RAG on structured data.** Counts, sums, filters need query tools.
- **RAG for tiny already-known context.** Pass it directly.
- **Context window as retrieval threshold.** 200K capacity ≠ send 200K tokens.
- **Entire corpus in every prompt.** Context capacity is not a reason to include irrelevant docs.
- **Average document size only.** Check p50, p95, p99, max.
- **Chunks without document identity.** Store `document_id` and source metadata.
- **Chunk when full document fits.** Small docs lose surrounding context when chunked for generation.
- **Full document without token check.** Always compare against remaining budget.
- **One index for distinct sources.** Split corpora into separate tools.
- **Dense-only retrieval.** Exact identifiers need lexical search.
- **Chunking without contextualization.** Chunks lose entities and relationships.
- **Raw follow-up as search query.** Multi-turn needs query rewriting.
- **Weighted score blending without calibration.** Use RRF.
- **Tiny default top-k.** Evaluate evidence size, don't pick `top_k=3` arbitrarily.
- **Unbounded agentic retrieval.** Cap iterations; watch context growth.
- **Mismatched distance operators and index classes.** Validate query plans.
- **Retrieval failure treated as hallucination.** If evidence wasn't retrieved, generation can't use it.
- **Vector database by default.** Start with existing infrastructure.
- **Generic document summaries on chunks.** Contextualization must be chunk-specific.

## Success criteria

Every layer in the pipeline costs latency, money, and a thing that can break. It earns its place by moving one of these on a fixed eval set, measured before and after the change:

- **Contextual recall** — did the evidence the answer needs actually come back? Hybrid search, query rewriting, and a larger `top_k` move this one first, and nothing downstream can recover what was never retrieved.
- **Contextual precision** — are the relevant chunks ranked above the irrelevant ones? This is the reranker's metric. High recall with low precision is the specific signature that says add a reranker rather than retrieve more.
- **Answer faithfulness** — is every claim traceable to the retrieved context? Document-level retrieval and evidence formatting move this; raising `top_k` usually does not.
- **Answer relevancy** — does the answer address the question asked, rather than the one the retrieved chunks happen to answer?
- **Routing accuracy across corpora** — the share of queries answered from the right source. Splitting corpora into separate tools should drive it up, and a system that retrieves confidently from the wrong index scores well on the four metrics above while being wrong.
- **Latency and cost per query.** Rewriting, expansion, reranking, and contextualization each add both. Record them alongside the quality numbers so the tradeoff is visible rather than assumed.

Metric definitions, thresholds, and the harness: `evals-before-shipping/references/rag-suite.md`. Worked before-and-after examples of three of these changes: [references/worked-examples.md](references/worked-examples.md).

If none of these move, the layer did not help on this corpus. Take it back out — the pipeline you can debug at 3am is worth more than the one with every layer enabled.

## References

- [references/rag-vs-tools.md](references/rag-vs-tools.md) — mechanism selection, direct context, structured data
- [references/document-level-retrieval.md](references/document-level-retrieval.md) — chunk-as-pointer pattern, storage, selection logic
- [references/contextual-retrieval.md](references/contextual-retrieval.md) — indexing pipeline, metadata, prompt caching
- [references/chunking.md](references/chunking.md) — structure-aware splitting for markdown, HTML, PDF, code, tickets
- [references/retrieval-bm25-dense-hybrid.md](references/retrieval-bm25-dense-hybrid.md) — BM25 tuning, dense config, RRF, metadata filtering
- [references/reranking-cross-encoder.md](references/reranking-cross-encoder.md) — hosted vs local rerankers, top-n sweeps
- [references/agentic-retrieval.md](references/agentic-retrieval.md) — retrieval loops, iteration caps, subagents
- [references/query-rewriting.md](references/query-rewriting.md) — rewriting, decomposition, expansion, evaluation
- [references/vector-store-selection.md](references/vector-store-selection.md) — pgvector, HNSW/IVFFlat, scale, hybrid indexing
- [references/evaluation.md](references/evaluation.md) — retriever vs generator metrics, strategy comparison
- [references/worked-examples.md](references/worked-examples.md) — three baseline-to-fix walkthroughs with the measurement that justified each
