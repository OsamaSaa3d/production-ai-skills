# Document-Level Retrieval

## The pattern

There is an important pattern between "send the whole corpus" and "send only the retrieved chunks."

When documents are reasonably small, a strong approach is:

```text
Full documents
    ↓
Chunk for retrieval
    ↓
Attach document metadata to each chunk
    ↓
Embed / index chunks
    ↓
Retrieve relevant chunks
    ↓
Extract document_id
    ↓
Fetch the original full document
    ↓
Check token budget
    ↓
Pass full document to the LLM
```

The key idea: **the chunk is used as a retrieval pointer, not necessarily as the final generation context**.

## Chunk metadata

Each indexed chunk should contain metadata such as:

```python
{
    "chunk_id": "doc_184_chunk_07",
    "document_id": "doc_184",
    "document_title": "Payment Retry Architecture",
    "source": "confluence",
    "section": "Retry Policy",
    "url": "...",
    "chunk_text": "...",
}
```

## Storage layout

Store the canonical full document separately from the retrieval index:

```text
document_store/
    doc_184.json
    doc_185.json
    doc_186.json
```

Or in a database/object store:

```text
documents
---------
document_id
title
source
content
metadata
updated_at
```

Do not make the retrieval index your only copy of the source. Store:

1. the original document,
2. retrieval chunks,
3. metadata connecting chunks back to the source document.

```text
documents
    ├── document_id
    ├── title
    ├── source
    ├── content
    ├── url
    └── updated_at

chunks
    ├── chunk_id
    ├── document_id
    ├── chunk_text
    ├── contextualized_text
    ├── embedding
    └── retrieval_metadata
```

This allows retrieval to optimize for **finding the right source**, while generation can optimize for **having enough source context to answer correctly**. You can change generation strategy without rebuilding source-of-truth storage.

## Query-time flow

```python
results = retrieve(query, top_k=10)

document_ids = deduplicate(
    result.metadata["document_id"]
    for result in results
)

documents = [
    document_store.get(document_id)
    for document_id in document_ids
]
```

Then decide per document:

```python
for document in documents:
    if token_count(document.content) <= remaining_context_budget:
        context.append(document.content)
    else:
        context.extend(
            relevant_chunks_for(document.document_id)
        )
```

## When this helps

Particularly useful when:

- the corpus contains many documents,
- each document is independently small or moderate,
- semantic retrieval can identify the correct document,
- but individual chunks would lose important surrounding context.

Example: a 5,000-token architecture document may contain a relevant paragraph in one chunk, but the answer may depend on definitions, constraints, earlier sections, or later exceptions. Retrieving the chunk and feeding the **5,000-token source document** can be substantially better than feeding only the 500-token chunk.

## Do not use blindly

The full-document strategy is appropriate only when the document fits comfortably within the remaining context budget.

```text
remaining_budget =
    context_window
    - system_prompt
    - tool_definitions
    - conversation
    - other_context
    - reserved_output
    - safety_margin
```

Compare the **actual token count of the document** against that remaining budget. When documents have a wide size distribution, measure mean, median/p50, p90, p95, p99, and maximum.

A corpus where the average document is 3K tokens but the maximum is 150K tokens should not be treated as a "3K-token corpus." You need a strategy for the tail.

## Selection logic

```python
def choose_context(document, relevant_chunks, budget):
    document_tokens = count_tokens(document.content)

    if document_tokens <= budget:
        return {
            "mode": "full_document",
            "content": document.content,
        }

    return {
        "mode": "retrieved_chunks",
        "content": [chunk.text for chunk in relevant_chunks],
    }
```

For multiple retrieved documents, account for the **combined** token budget:

```python
used = 0
context = []

for document in ranked_documents:
    tokens = count_tokens(document.content)

    if used + tokens <= budget:
        context.append(document.content)
        used += tokens
    else:
        context.extend(
            chunk.text
            for chunk in relevant_chunks(document)
        )
```

A better implementation may reserve additional space for separators, metadata, citations, and other formatting. The key idea is dynamic selection rather than a fixed global threshold.

## Metadata-only context for small documents

Attach metadata to each chunk describing document title, source system, section, document type, URL, version, timestamps, and relevant identifiers. Retrieval can identify the **document** even when the individual chunk is only a small fragment:

```text
Semantic / lexical retrieval → find relevant chunk → read document_id
→ fetch original document → check token count → full document if it fits
→ otherwise relevant chunks
```

This often provides more coherent context than passing the retrieved chunk alone.
