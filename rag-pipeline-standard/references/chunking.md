# Chunking

## Defaults

Chunk size and boundaries measurably affect retrieval. There is no universal right answer.

Useful defaults:

- a few hundred to roughly 800 tokens,
- split on natural boundaries,
- preserve headings and sections,
- avoid cutting tables, code blocks, or logical units arbitrarily,
- use modest overlap when appropriate.

Structure-aware splitting usually beats naive fixed-character splitting on real documents. Treat chunk size as a tunable parameter in your eval harness, not a one-time decision. Test multiple configurations.

## By format

### Markdown

Split on heading boundaries (`#`, `##`, `###`). Keep each section intact when possible. If a section exceeds your target size, split on paragraph boundaries within it.

### HTML

Parse the DOM. Split on block-level elements (`<section>`, `<article>`, `<div class="content">`, `<h1>`–`<h6>`). Strip navigation, footers, and boilerplate before chunking.

### PDF

Extract text with structure preservation (headings, columns). PDFs often lose structure — verify extraction quality before chunking. Tables and multi-column layouts are common failure points.

### Code

Split on function/class/module boundaries. Never cut mid-function. Include the enclosing scope (imports, class definition) in metadata so retrieval can identify the file and module.

### Ticket threads

Each ticket is a document. Chunk the description and comments separately, but keep `ticket_id` metadata on every chunk. Comment threads benefit from smaller chunks (individual comments) with thread-level metadata.

## Overlap

Modest overlap (10–20% of chunk size) helps when relevant content spans a boundary. Too much overlap increases index size and can cause near-duplicate results. Measure on your eval set.

## Chunking without context

A chunk can lose the entities and relationships required to understand it. If you are not using contextual retrieval, at minimum attach rich metadata (document title, section, source, identifiers) to every chunk.

## Eval parameters

Sweep these in your eval harness:

```text
chunk_size (256, 512, 800, 1024)
overlap (0%, 10%, 20%)
splitting strategy (fixed-size vs structure-aware)
contextualization (on/off)
```

Stop when recall and answer quality plateau.
