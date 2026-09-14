# Contextual Retrieval and Indexing

> **Verify before you build.** Parameter names, limits, and model support named below move between releases. Check the provider's current API reference before relying on them, and correct any drift with the smallest possible edit.

## Why contextualize

Chunking destroys context — a major source of retrieval failure.

A chunk reading "The company's revenue grew by 3% over the previous quarter" names neither the company nor the quarter. It cannot be retrieved reliably or used confidently on its own.

**Contextual Retrieval** fixes this by adding chunk-specific context before indexing. Prepend a short note describing where the chunk sits inside the document and identifying important entities, dates, sections, and relationships.

## Implementation

```python
CONTEXTUALIZE_PROMPT = """<document>
{document}
</document>

Here is a chunk from that document:
<chunk>
{chunk}
</chunk>

Write a short, self-contained note situating this chunk within the document so it
can be retrieved on its own. Name the entities, dates, and section it refers to.
Answer with the note only."""

def contextualize(document: str, chunk: str) -> str:
    # one short completion per chunk, on a cheap model — any provider
    return complete(
        model=CHEAP_MODEL,
        max_tokens=150,
        prompt=CONTEXTUALIZE_PROMPT.format(document=document, chunk=chunk),
    )
```

`complete()` is whatever thin wrapper your codebase already has over its provider's completion call. The only requirements are a short output cap and a cheap model.

Then index:

```python
indexed_text = f"{contextual_context}\n\n{chunk}"
```

Store the original chunk separately. Do not replace the original source text with the generated contextualization:

```python
{
    "document_id": "doc_184",
    "chunk_id": "doc_184_chunk_07",
    "original_chunk": chunk,
    "contextualized_chunk": contextual_context,
    "document_title": "Payment Retry Architecture",
    "section": "Retry Policy",
}
```

The contextualized version improves retrieval. The original chunk remains the source material.

## What does not work

**Generic document summaries prepended to chunks.** A generic document summary says what the document is about. That does not make an individual chunk independently retrievable. Contextual retrieval must be **chunk-specific**.

**Summary-based indexing.** Replacing source content with generic summaries often loses the exact details needed for retrieval.

## Full indexing pipeline

```text
documents
    → structure-aware chunking
    → optional chunk contextualization
    → embeddings
    → BM25 / lexical index
    → source-document metadata
```

Add layers in order. Measure each layer's contribution. Stop when evals say you're done.

## Prompt caching

Prompt caching can make repeatedly supplying the same large document more practical on providers that support it. But caching does **not** mean large context is automatically free, instant, or architecturally preferable.

Use caching when:

- the same context is reused across requests,
- the provider's caching semantics are favorable,
- latency and cost measurements justify it.

Still measure input tokens, cached input tokens, uncached input tokens, output tokens, latency, and cost. Do not use caching as an excuse to eliminate retrieval indiscriminately.

## Cost estimation

Contextualization adds an LLM call per chunk at index time. Batch and cache where possible. Use a cheap model — the task is short and does not need frontier reasoning. Estimate:

```text
indexing_cost ≈ num_chunks × contextualize_tokens × cheap_model_price
```

Compare against retrieval quality improvement on your eval set before enabling at scale.
