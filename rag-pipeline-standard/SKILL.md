---
name: rag-pipeline-standard
description: Use this skill when building or fixing retrieval over your own data — a knowledge base assistant, docs search, support bot, or any system answering questions from internal documents, tickets, wikis, or databases. Use it when someone says "RAG," "vector database," "embeddings," "semantic search," or "chunking." Use it when retrieval returns irrelevant chunks, misses exact matches like error codes or ticket IDs, answers from the wrong source system, or breaks on follow-up questions. Covers whether to use RAG or tool calling at all, direct-context loading, document-level retrieval, contextual retrieval, hybrid search, reranking, splitting corpora into separate retrieval tools, agentic retrieval, query rewriting, and vector index selection.
---

# Retrieval: RAG, Tools, and Agentic Search

## First: pick the right mechanism

Not every "the model needs our data" problem is RAG. Get this wrong and everything downstream is wasted work.

The key distinction is not simply **"does the entire corpus fit in the model's context window?"**

The useful question is:

> **How much context can you safely provide for a typical request while leaving enough room for the model's output and other instructions, and how much of the corpus is actually relevant to each request?**

A corpus can technically fit inside a model's context window and still be a bad candidate for putting the entire corpus into every prompt.

| Your data / workload                                                                    | Default                                                           | Why                                                                                                |
| --------------------------------------------------------------------------------------- | ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Small amount of relevant unstructured text                                              | **Put the relevant data directly in the prompt**                  | No retrieval system is needed when the relevant context is already small.                          |
| Corpus is moderate, but each relevant document is small enough to fit safely in context | **Retrieve at chunk level, then load the full matching document** | Retrieval finds the right document efficiently, while generation gets the document's full context. |
| Large unstructured corpus where documents are too large to pass safely                  | **RAG**                                                           | Retrieve the most relevant chunks and pass those chunks to the generator.                          |
| Structured — SQL, CSV, API, spreadsheets                                                | **Tool calling, not RAG**                                         | The structure is the query interface. Don't destroy it.                                            |
| Both structured + unstructured                                                          | **Both, as separate tools**                                       | Query structured fields with tools and retrieve unstructured text separately.                      |

Do **not** use a fixed rule such as "under 200K tokens means put everything in the prompt." Context-window capacity is only an upper bound, not a sensible prompt-size target.

Instead, calculate a context budget based on the **actual model you are using**.

At minimum, account for:

* Model context window
* System instructions
* Tool definitions
* Conversation history
* Retrieved context
* Expected output tokens
* A safety margin

A useful formulation is:

```text
available_input_budget =
    model_context_window
    - system_and_tool_tokens
    - conversation_history_tokens
    - reserved_output_tokens
    - safety_margin
```

Only put a document or set of documents directly into the prompt when their token count fits comfortably inside that budget.

Do not fill the context window to the edge. Leave meaningful headroom for the answer, tool calls, follow-up reasoning, and normal variation in tokenization.

For a document corpus, measure the actual token distribution rather than looking only at totals.

For example:

```text
documents = 1,000

average document size = 2,500 tokens
p50 = 1,900
p95 = 6,800
p99 = 18,000
max = 74,000
```

If the model can safely accept 30K input tokens after accounting for instructions, conversation, output, and margin, then most individual documents may be safely passed in full while the 74K-token document is not.

This leads to a much better architecture than a fixed global threshold:

> **Retrieve the relevant document first, then decide whether to pass the whole document or only its relevant chunks based on that document's actual token size and the model's remaining context budget.**

### Small relevant context: skip retrieval

If you already know which small documents are relevant, load them directly.

For example:

```python
context_budget = (
    MODEL_CONTEXT_WINDOW
    - SYSTEM_PROMPT_TOKENS
    - TOOL_DEFINITION_TOKENS
    - HISTORY_TOKENS
    - RESERVED_OUTPUT_TOKENS
    - SAFETY_MARGIN
)

if token_count(document) <= context_budget:
    prompt_context = document
```

There is no reason to build embeddings or a vector store merely to retrieve text that you already know is small enough to provide directly.

### Do not confuse "fits in context" with "put the entire corpus in every prompt"

This is an important distinction.

Suppose your entire knowledge base is 120K tokens and your model has a 200K-token context window.

That does **not** automatically mean every user question should send all 120K tokens.

The relevant question is whether:

1. the entire corpus is actually needed for most requests,
2. the corpus fits comfortably after all prompt and output requirements,
3. the latency and cost are acceptable,
4. the model performs better with that much context than with targeted retrieval,
5. the corpus changes frequently enough that repeatedly loading it is operationally sensible.

If the answer to these questions is no, use retrieval.

The context window is a capability, not an architectural mandate.

---

## Document-level retrieval: retrieve chunks, then recover the full document

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

The key idea is that **the chunk is used as a retrieval pointer, not necessarily as the final generation context**.

For example, each indexed chunk can contain metadata such as:

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

The retrieval index uses the chunk text and metadata, but the canonical full document is stored separately:

```text
document_store/
    doc_184.json
    doc_185.json
    doc_186.json
```

or in a database/object store:

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

At query time:

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

Then decide whether to provide the full document or fall back to chunk-level context.

```python
for document in documents:
    if token_count(document.content) <= remaining_context_budget:
        context.append(document.content)
    else:
        context.extend(
            relevant_chunks_for(document.document_id)
        )
```

This is particularly useful when:

* the corpus contains many documents,
* each document is independently small or moderate,
* semantic retrieval can identify the correct document,
* but individual chunks would lose important surrounding context.

For example, a 5,000-token architecture document may contain a relevant paragraph in one chunk, but the answer may depend on definitions, constraints, diagrams represented as text, earlier sections, or later exceptions.

In that situation, retrieving the chunk and then feeding the **5,000-token source document** can be substantially better than feeding only the 500-token chunk.

### Do not use this pattern blindly

The full-document strategy is appropriate only when the document fits comfortably within the remaining context budget.

Do not say:

> "The model supports 200K tokens, so every retrieved document can be sent in full."

Instead:

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

Then compare the **actual token count of the document** against that remaining budget.

When documents have a wide size distribution, measure:

```text
mean
median / p50
p90
p95
p99
maximum
```

Use those measurements when choosing the architecture.

A corpus where the average document is 3K tokens but the maximum is 150K tokens should not be treated as a "3K-token corpus."

You need a strategy for the tail.

### Store the original document separately

Do not make the retrieval index your only copy of the source.

Store:

1. the original document,
2. retrieval chunks,
3. metadata connecting chunks back to the source document.

For example:

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

This allows retrieval to optimize for **finding the right source**, while generation can optimize for **having enough source context to answer correctly**.

It also means you can change your generation strategy without rebuilding the source-of-truth storage.

---

## Structured data: give the agent query tools

If the data lives in a database, a CSV, or an API, do not embed it.

Embedding rows destroys exactly the structure that makes the data answerable.

Consider:

> "How many P1 tickets did the platform team open last month?"

That is a `COUNT` with a `WHERE` clause.

Semantic search over embedded ticket rows returns chunks that sound like the question. The model then counts them — which is wrong whenever the right answer exceeds your top-k, and silently wrong at that.

Structured data is consistent, has a schema, and supports exact filtering, aggregation, joins, and sorting.

A SQL tool gives the agent all of it.

Retrieval gives it none.

```python
# RIGHT: the structure is the interface
{
    "name": "query_tickets",
    "description": (
        "Query the ticket database. Supports filtering by team, priority, "
        "status, and date range, and aggregation by any of those fields."
    ),
    "input_schema": {...}
}

# WRONG:
# embed every ticket row and hope top-k contains everything needed
```

Rule of thumb:

> **If the question has a computable answer, it needs a query, not a similarity search.**

Counting, summing, filtering by exact value, sorting, "the most recent," "all of the X" — all queries.

Use RAG for the unstructured text attached to structured records — the ticket description, comment thread, incident notes, or documentation — while querying the structured fields with tools.

Those are two tools, not one blended index.

---

# The standard pipeline

When retrieval genuinely is the right mechanism, this is the current default.

Each layer's contribution should be measured, so add them in order and stop when your evals say you're done.

A useful baseline pipeline is:

```text
Indexing:
    documents
        → structure-aware chunking
        → optional chunk contextualization
        → embeddings
        → BM25 / lexical index
        → source-document metadata

Query time:
    query
        → optional query rewriting
        → dense search
        → BM25 search
        → RRF fusion
        → reranking
        → document/chunk selection
        → context-budget decision
        → LLM
```

Do not assume every system needs every layer.

Start simple.

Measure.

Then add complexity only when evaluation shows it helps.

---

## Indexing: chunk, then contextualize

Chunking destroys context, and that is a major source of retrieval failure.

A chunk reading:

> "The company's revenue grew by 3% over the previous quarter."

names neither the company nor the quarter.

It cannot be retrieved reliably or used confidently on its own.

**Contextual Retrieval** fixes this by adding chunk-specific context before indexing.

Prepend a short note describing where the chunk sits inside the document and identifying important entities, dates, sections, and relationships.

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
```

```python
def contextualize(document: str, chunk: str) -> str:
    resp = client.messages.create(
        model=CHEAP_MODEL,
        max_tokens=150,
        messages=[{
            "role": "user",
            "content": [{
                "type": "text",
                "text": CONTEXTUALIZE_PROMPT.format(
                    document=document,
                    chunk=chunk,
                ),
            }],
        }],
    )

    return resp.content[0].text
```

Then index:

```python
indexed_text = f"{contextual_context}\n\n{chunk}"
```

Store the original chunk separately.

Do not replace the original source text with the generated contextualization.

A useful record is:

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

The contextualized version improves retrieval.

The original chunk remains the source material.

---

## Metadata can be enough context for small documents

Contextualized chunks are useful, but there is another practical technique when full documents are not too large.

Attach metadata to each chunk describing:

* what document it belongs to,
* document title,
* source system,
* section,
* document type,
* URL,
* version,
* timestamps,
* relevant identifiers.

For example:

```python
{
    "document_id": "confluence_92817",
    "document_title": "Authentication Architecture",
    "section": "SSO Flow",
    "source": "confluence",
    "url": "...",
    "chunk_text": "...",
}
```

Then retrieval can identify the **document** even when the individual chunk is only a small fragment.

This gives you a two-stage strategy:

```text
Semantic / lexical retrieval
        ↓
Find relevant chunk
        ↓
Read document_id from metadata
        ↓
Fetch original document
        ↓
Check document token count
        ↓
Full document if it fits
        ↓
Otherwise relevant chunks
```

This often provides more coherent context than simply passing the retrieved chunk.

---

## Prompt caching

Prompt caching can make repeatedly supplying the same large document considerably more practical on providers that support it.

But caching does **not** mean that a large context is automatically free, instant, or architecturally preferable.

Use caching when:

* the same context is reused across requests,
* the provider's caching semantics are favorable,
* latency and cost measurements justify it.

Still measure:

```text
input tokens
cached input tokens
uncached input tokens
output tokens
latency
cost
```

Do not use caching as an excuse to eliminate retrieval indiscriminately.

---

## Chunking

Chunk size and boundaries measurably affect retrieval.

There is no universal right answer.

Useful defaults:

* a few hundred to roughly 800 tokens,
* split on natural boundaries,
* preserve headings and sections,
* avoid cutting tables, code blocks, or logical units arbitrarily,
* use modest overlap when appropriate.

Structure-aware splitting usually beats naive fixed-character splitting on real documents.

Treat chunk size as a tunable parameter in your eval harness, not a one-time decision.

Test multiple configurations.

---

# Retrieval: hybrid by default for identifier-heavy corpora

Dense embeddings capture meaning but can miss exact strings.

BM25 does lexical matching and catches many of those misses.

The canonical case is:

```text
Error code TS-999
```

Embeddings may retrieve documents about error codes generally.

BM25 finds the literal string.

Any corpus with:

* identifiers,
* error codes,
* SKUs,
* version numbers,
* function names,
* ticket keys,
* API names,
* file paths,

usually benefits from the lexical half.

A standard hybrid pipeline is:

```text
dense retrieval
      +
BM25 retrieval
      ↓
RRF
      ↓
reranking
```

Example:

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

RRF avoids having to normalize incompatible score scales.

---

# Reranking: candidates down to a smaller final set

Retrieval optimizes for recall.

A reranker optimizes for relevance.

A cross-encoder processes the query and candidate text together and can judge their relationship much more precisely than a basic embedding similarity comparison.

For example:

```python
reranked = reranker.rerank(
    query=query,
    documents=candidates[:150],
    top_n=20,
)

context = [c.text for c in reranked]
```

Do not blindly assume that `20` is universally optimal.

Treat:

```text
retrieval_top_k
rerank_top_n
final_context_size
```

as evaluation parameters.

If your system retrieves full documents rather than chunks, the same principle applies:

```text
retrieve candidate chunks
        ↓
identify candidate documents
        ↓
deduplicate documents
        ↓
rerank documents or evidence
        ↓
load full documents when they fit
        ↓
otherwise use relevant chunks
```

---

# Split the corpus into separate retrieval tools

Do not blend genuinely distinct sources into one index.

If you have Jira issues and Confluence pages, those are two corpora, and they should generally be two tools.

```python
tools = [
    {
        "name": "search_jira_issues",
        "description": (
            "Search Jira issue tickets: bug reports, feature requests, "
            "and their comment threads. Use for questions about specific "
            "problems, what was reported, or work in progress."
        ),
        "input_schema": {
            "properties": {
                "query": {"type": "string"},
                "project": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["open", "in_progress", "done"],
                },
            }
        },
    },
    {
        "name": "search_confluence_docs",
        "description": (
            "Search Confluence documentation: architecture docs, runbooks, "
            "onboarding guides, and policies. Use for questions about how "
            "something is supposed to work or what the official process is."
        ),
        "input_schema": {
            "properties": {
                "query": {"type": "string"},
                "space": {"type": "string"},
            }
        },
    },
]
```

Why this beats one index:

* Different content answers different questions.
* Different structures need different chunking.
* Different metadata enables different filters.
* The tool name itself can provide a routing signal to the model.

For example:

> "What's the retry policy?"

probably wants documentation.

> "Why did checkout break last Tuesday?"

probably wants issues, incident records, and possibly deployment information.

The cost is tool count, so split on genuinely distinct sources, not every folder.

Two to five retrieval tools is often reasonable.

Twenty is usually a smell.

Where a question needs multiple sources, an agent can call multiple retrieval tools and synthesize the results.

---

# Agentic retrieval

Single-shot RAG:

```text
one query
→ one retrieval pass
→ one answer
```

is a **workflow**.

It handles direct lookups well and is cheap and predictable.

Agentic retrieval gives the model control over:

* whether to search,
* what to search for,
* which corpus to search,
* whether more evidence is needed,
* whether to search again.

That is an **agent**, with corresponding cost and latency.

Example:

```text
User:
"Why does checkout fail for EU customers and is it a known issue?"

Agent:
    → search_confluence_docs("checkout payment flow EU")
    → search_jira_issues("checkout failure EU", status="open")
    → search_jira_issues("VAT validation error")
    → synthesize
```

Use agentic retrieval when:

* the question spans multiple corpora,
* the right query depends on what is discovered,
* the question is compound,
* one retrieval pass frequently comes back insufficient.

Stay with single-shot retrieval when:

* questions are direct lookups,
* latency matters more than completeness,
* one pass already answers reliably.

Cap retrieval iterations.

Watch context growth.

Every retrieval result that remains in the parent transcript consumes context.

For complex searches, a retrieval subagent can sometimes run several searches inside its own context and return a compact evidence summary to the parent.

---

# Rewrite the query before retrieving

Retrieval sees the search query, not necessarily the full conversation.

This can break multi-turn systems.

Example:

```text
User:
What's our refund policy for enterprise customers?

Bot:
[answers]

User:
What about annual plans?
```

Searching:

```text
"What about annual plans?"
```

is weak because the subject is missing.

Rewrite it first:

```python
REWRITE_PROMPT = """Given the conversation, rewrite the user's latest message as a
standalone search query that makes sense without the conversation. Keep the user's
terminology. If the message is already self-contained, return it unchanged.

Conversation:
{history}

Latest message:
{message}

Standalone query:"""
```

Then:

```python
search_query = rewrite(history, message)
```

could produce:

```text
refund policy for annual enterprise plans
```

A small model is often sufficient here.

Two related uses of the same step:

### Decomposition

Split a compound question into multiple retrieval queries.

Example:

```text
"How do I set up SSO and what's the rollout timeline?"
```

becomes:

```text
"How do I set up SSO?"
"What's the rollout timeline?"
```

### Expansion

Generate query variants to increase recall, then fuse the results.

In an agentic setup, the model may do these operations implicitly.

In a single-shot pipeline, implement them explicitly when evaluation shows a benefit.

Evaluate query rewriting separately.

A rewrite that sounds better but retrieves worse documents is not an improvement.

---

# Context budgeting

Context budgeting should be treated as a first-class part of retrieval architecture.

Do not think only in terms of:

```text
model_context = 200K
```

Think in terms of:

```text
usable_context =
    model_context
    - system instructions
    - tool definitions
    - conversation
    - retrieval context
    - reserved output
    - safety margin
```

A practical implementation might look like:

```python
def get_context_budget(
    model_context_window: int,
    system_tokens: int,
    tool_tokens: int,
    history_tokens: int,
    reserved_output_tokens: int,
    safety_margin_tokens: int,
) -> int:
    return max(
        0,
        model_context_window
        - system_tokens
        - tool_tokens
        - history_tokens
        - reserved_output_tokens
        - safety_margin_tokens,
    )
```

Then:

```python
budget = get_context_budget(
    model_context_window=MODEL_CONTEXT_WINDOW,
    system_tokens=count_tokens(system_prompt),
    tool_tokens=count_tokens(tool_definitions),
    history_tokens=count_tokens(history),
    reserved_output_tokens=8_000,
    safety_margin_tokens=5_000,
)
```

The exact reserve should be tuned for the application.

The important principle is:

> **Never treat the advertised maximum context window as the amount of context you should automatically send.**

---

# Full-document selection logic

When retrieval identifies a document, use the document's real token size to decide what to provide.

A useful policy:

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

A better implementation may reserve additional space for separators, metadata, citations, and other formatting.

The key idea is dynamic selection rather than a fixed global threshold.

---

# Vector store and index selection

This is infrastructure, and it matters less than retrieval quality.

Don't over-invest here.

**Default: use the database you already run.**

`pgvector` gives you:

* transactions,
* joins against existing tables,
* metadata filtering,
* one system to operate.

Most corpora are well below the scale where a dedicated vector database automatically earns its operational cost.

---

## Distance operators

Pick the metric matching how your embedding model was trained.

Keep:

```text
operator
index operator class
ORDER BY
```

in agreement.

A mismatch can prevent the expected index from being used.

| Operator | Metric                 | Notes                                       |
| -------- | ---------------------- | ------------------------------------------- |
| `<=>`    | Cosine distance        | Common default                              |
| `<#>`    | Negative inner product | Equivalent to cosine for normalized vectors |
| `<->`    | L2 / Euclidean         |                                             |
| `<+>`    | L1 / Manhattan         |                                             |

Many embedding providers return normalized vectors.

When vectors are normalized, cosine and inner-product ranking are equivalent.

---

# Index types

Without an index, pgvector can perform exact nearest-neighbor search.

That gives perfect recall and can be perfectly adequate at smaller scale.

Approximate indexes trade some recall for speed.

### HNSW

HNSW builds a navigable multilayer graph.

Advantages:

* strong speed/recall tradeoff,
* no training step,
* incremental insertion,
* good general default.

Costs:

* higher memory,
* slower build,
* tuning still matters.

Tune with parameters such as:

```text
hnsw.ef_search
```

### IVFFlat

IVFFlat partitions vectors into clusters around centroids.

Advantages:

* faster builds,
* lower memory footprint.

Costs:

* requires representative data before building,
* clustering can degrade when the data distribution changes,
* often needs more operational tuning.

Tune with:

```text
ivfflat.probes
```

### Default

Default to HNSW unless measurements give you a reason to use IVFFlat.

Use IVFFlat when build time and memory dominate at very large scale or the workload is especially well suited to it.

Set tuning parameters locally inside transactions when using connection pools rather than relying on leaking session-level settings.

---

# Scale

Vector indexes can become memory-heavy.

As scale increases, consider:

* lower-precision vectors,
* compressed representations,
* approximate indexes,
* disk-oriented ANN solutions,
* partitioning where appropriate.

Do not choose infrastructure based only on database row count.

Measure:

```text
index size
RAM consumption
query latency
recall
write cost
build time
filter selectivity
```

Whatever vector store you pick, you also need a lexical retrieval strategy if your corpus benefits from exact matching.

Options include:

* PostgreSQL full-text search,
* Elasticsearch,
* OpenSearch,
* BM25 libraries,
* provider-specific lexical indexes.

A vector-only architecture is not automatically hybrid retrieval.

---

# Embedding model selection

Embedding quality generally matters more than vector-store brand.

Benchmark two or three plausible embedding models on your own evaluation set.

Measure:

```text
Recall@k
MRR
nDCG
latency
embedding cost
index size
```

Do not choose a model solely because it performs well on a public benchmark.

Your identifiers, terminology, document styles, and question distribution may be very different.

---

# What doesn't work

### Generic document summaries prepended to chunks

A generic document summary says what the document is about.

That does not necessarily make an individual chunk independently retrievable.

Contextual retrieval should be **chunk-specific**.

### Summary-based indexing

Replacing source content with generic summaries often loses the exact details needed for retrieval.

### Building RAG solely because the corpus is "large"

Large relative to what?

A 5,000-token document is large compared with a typical chunk but small compared with many model context windows.

Architecture should be based on:

```text
document size distribution
+
query relevance
+
context budget
+
latency
+
cost
+
answer quality
```

### Putting the entire corpus into every prompt

Even when technically possible, this can waste:

* input tokens,
* latency,
* attention,
* cost,
* and useful context capacity.

Use direct context when it is genuinely appropriate, not simply because the model allows it.

### Embedding structured rows

If the answer requires:

```text
COUNT
SUM
FILTER
SORT
JOIN
MAX
MIN
```

use a query tool.

### Dense-only retrieval

Dense retrieval can miss exact identifiers.

### Chunking without context

A chunk can lose the entities and relationships required to understand it.

### Embedding the raw follow-up message

Multi-turn retrieval usually benefits from query rewriting.

### Weighted score blending without calibration

Dense and lexical scores are not necessarily on the same scale.

RRF is a strong baseline because it avoids that normalization problem.

### Passing too few chunks

Do not choose `top_k=3` simply because it looks tidy.

Measure it.

### Unbounded agentic retrieval

Agentic loops need iteration limits.

### Mismatched distance operators and indexes

This can quietly degrade query performance.

### Treating retrieval failures as hallucination

If the relevant evidence was never retrieved, changing the generation prompt cannot fix that.

Measure:

```text
retrieval quality
vs
generation quality
```

separately.

### Reaching for a vector database by default

Use the database you already operate until measurements show that something else is justified.

---

# Measure the retriever and generator separately

The most useful diagnostic property of RAG is that retrieval and generation fail differently.

Retriever metrics can include:

```text
Contextual Relevancy
Contextual Precision
Contextual Recall
Recall@k
MRR
nDCG
```

Generator metrics can include:

```text
Answer Relevancy
Faithfulness
Correctness
Citation correctness
```

Interpretation:

| Retriever | Generator        | Likely fix                                                                     |
| --------- | ---------------- | ------------------------------------------------------------------------------ |
| Low       | High             | Improve chunking, contextualization, hybrid search, reranking, query rewriting |
| High      | Low faithfulness | Improve generation prompt or evidence formatting                               |
| Low       | Low              | Fix retrieval first                                                            |
| High      | High             | Measure latency, cost, robustness, and edge cases                              |

In agentic systems, also measure routing.

A model that reliably retrieves from the wrong source can look good under generic retrieval metrics and still answer incorrectly.

Build the evaluation set before tuning.

Then sweep:

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

---

# Full-document vs chunk-level generation should itself be evaluated

Do not assume one strategy always wins.

Compare:

```text
Strategy A:
retrieve chunk → send chunk

Strategy B:
retrieve chunk → identify document → send full document

Strategy C:
retrieve chunk → identify document → send selected surrounding sections

Strategy D:
retrieve chunks → rerank → send top chunks
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

* full documents are best for small technical docs,
* selected sections are best for medium documents,
* chunks are necessary for huge documents,
* and structured queries are better for database-backed facts.

That is a much stronger decision framework than a universal "200K-token rule."

---

# Pitfalls

**Using RAG on structured data.** If the answer is a count, sum, filter, or sort, it needs a query.

**Building RAG for a tiny amount of already-relevant context.** Check whether the relevant context can simply be passed directly.

**Treating context-window size as a retrieval threshold.** A model having a 200K-token context does not mean you should send 200K tokens.

**Putting the entire corpus into every prompt.** Context capacity is not a reason to provide irrelevant documents.

**Ignoring the document-size distribution.** Average size alone is not enough. Look at p50, p95, p99, and maximum.

**Retrieving chunks but discarding document identity.** Store `document_id` and source metadata so you can recover the canonical document when appropriate.

**Passing a retrieved chunk when the full source document easily fits.** For small documents, full-document generation can preserve important surrounding context.

**Passing a full document without checking its token count.** Always calculate it against the remaining context budget.

**One index for distinct sources.** Split genuinely different corpora into separate tools.

**Dense-only retrieval.** Exact identifiers often need lexical search.

**Chunking without contextualization.** Retrieval quality can suffer when chunks lose their source context.

**Embedding the raw follow-up message.** Multi-turn retrieval needs self-contained queries.

**Weighted score blending without calibration.** Use RRF as a strong baseline.

**Passing too few chunks.** Evaluate the final evidence size instead of choosing a tiny default arbitrarily.

**Unbounded agentic retrieval.** Cap iterations and watch context growth.

**Mismatched distance operators and index classes.** Validate your database query plan.

**Treating retrieval failures as generation failures.** If the evidence was not retrieved, generation cannot use it.

**Reaching for a vector database by default.** Start with your existing infrastructure.

---

# References

* `references/retrieval-bm25-dense-hybrid.md` — BM25 tuning, dense config, RRF variants, metadata filtering
* `references/contextual-retrieval.md` — full indexing pipeline with caching, batching, and cost estimation
* `references/reranking-cross-encoder.md` — hosted vs local rerankers, top-n sweeps, latency budgeting
* `references/chunking.md` — structure-aware splitting for markdown, HTML, PDF, code, and ticket threads
* `references/agentic-retrieval.md` — retrieval agent loops, iteration caps, retrieval subagents, multi-corpus synthesis
* `references/query-rewriting.md` — rewriting, decomposition, expansion, and evaluating each
* `references/vector-store-selection.md` — pgvector setup, HNSW/IVFFlat tuning, halfvec, DiskANN, hybrid indexing per store
* `references/rag-vs-tools.md` — worked examples of the same question answered by SQL tool vs retrieval

---
