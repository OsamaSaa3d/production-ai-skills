# RAG vs Tools vs Direct Context

> **Verify before you build.** Parameter names, limits, and model support named below move between releases. Check the provider's current API reference before relying on them, and correct any drift with the smallest possible edit.

## The key distinction

Not every "the model needs our data" problem is RAG. Get this wrong and everything downstream is wasted work.

The key distinction is not simply **"does the entire corpus fit in the model's context window?"**

The useful question is:

> **How much context can you safely provide for a typical request while leaving enough room for the model's output and other instructions, and how much of the corpus is actually relevant to each request?**

A corpus can technically fit inside a model's context window and still be a bad candidate for putting the entire corpus into every prompt.

## Decision table

| Your data / workload | Default | Why |
|---|---|---|
| Small amount of relevant unstructured text | **Put the relevant data directly in the prompt** | No retrieval system is needed when the relevant context is already small |
| Corpus is moderate, but each relevant document is small enough to fit safely in context | **Retrieve at chunk level, then load the full matching document** | Retrieval finds the right document efficiently, while generation gets the document's full context |
| Large unstructured corpus where documents are too large to pass safely | **RAG** | Retrieve the most relevant chunks and pass those chunks to the generator |
| Structured — SQL, CSV, API, spreadsheets | **Tool calling, not RAG** | The structure is the query interface. Don't destroy it |
| Both structured + unstructured | **Both, as separate tools** | Query structured fields with tools and retrieve unstructured text separately |

## Context budget

Do **not** use a fixed rule such as "under 200K tokens means put everything in the prompt." Context-window capacity is only an upper bound, not a sensible prompt-size target.

Calculate a context budget based on the **actual model you are using**. At minimum, account for:

- Model context window
- System instructions
- Tool definitions
- Conversation history
- Retrieved context
- Expected output tokens
- A safety margin

```text
available_input_budget =
    model_context_window
    - system_and_tool_tokens
    - conversation_history_tokens
    - reserved_output_tokens
    - safety_margin
```

Only put a document or set of documents directly into the prompt when their token count fits comfortably inside that budget. Do not fill the context window to the edge.

## Document size distribution

For a document corpus, measure the actual token distribution rather than looking only at totals:

```text
documents = 1,000
average document size = 2,500 tokens
p50 = 1,900
p95 = 6,800
p99 = 18,000
max = 74,000
```

If the model can safely accept 30K input tokens after accounting for instructions, conversation, output, and margin, then most individual documents may be safely passed in full while the 74K-token document is not.

> **Retrieve the relevant document first, then decide whether to pass the whole document or only its relevant chunks based on that document's actual token size and the model's remaining context budget.**

## Small relevant context: skip retrieval

If you already know which small documents are relevant, load them directly:

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

## "Fits in context" ≠ "put entire corpus in every prompt"

Suppose your entire knowledge base is 120K tokens and your model has a 200K-token context window. That does **not** automatically mean every user question should send all 120K tokens.

Ask whether:

1. the entire corpus is actually needed for most requests,
2. the corpus fits comfortably after all prompt and output requirements,
3. the latency and cost are acceptable,
4. the model performs better with that much context than with targeted retrieval,
5. the corpus changes frequently enough that repeatedly loading it is operationally sensible.

If the answer to these questions is no, use retrieval. The context window is a capability, not an architectural mandate.

## Structured data: give the agent query tools

If the data lives in a database, a CSV, or an API, do not embed it. Embedding rows destroys exactly the structure that makes the data answerable.

Consider: "How many P1 tickets did the platform team open last month?" — that is a `COUNT` with a `WHERE` clause. Semantic search over embedded ticket rows returns chunks that sound like the question. The model then counts them — wrong whenever the right answer exceeds your top-k, and silently wrong at that.

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

# WRONG: embed every ticket row and hope top-k contains everything needed
```

Rule of thumb:

> **If the question has a computable answer, it needs a query, not a similarity search.**

Counting, summing, filtering by exact value, sorting, "the most recent," "all of the X" — all queries.

Use RAG for the unstructured text attached to structured records — the ticket description, comment thread, incident notes, or documentation — while querying the structured fields with tools. Those are two tools, not one blended index.

## Worked example: same question, two mechanisms

**Question:** "How many open P1 tickets does the platform team have?"

- **SQL tool:** `SELECT COUNT(*) FROM tickets WHERE team='platform' AND priority='P1' AND status='open'` → exact answer
- **RAG over embedded rows:** retrieves top-k ticket chunks that mention P1 and platform → model counts them → wrong when count > top-k

**Question:** "What's our retry policy for failed payments?"

- **RAG:** retrieves relevant documentation chunks → answers from prose
- **SQL tool:** no schema column for "retry policy prose" → wrong mechanism
