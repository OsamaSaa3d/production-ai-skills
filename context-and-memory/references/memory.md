# Agent Memory

## The four types

The CoALA taxonomy, now the field default. Naming them prevents the standard mistake: building one store and calling it "memory."

| Type | Answers | Typical lifetime | Where it actually lives |
|---|---|---|---|
| Working | What am I doing right now? | One task | Context window plus the loop's scratchpad |
| Episodic | What happened before? | Days to months | Transcripts, conversation stores, trace backends |
| Semantic | What is true? | Months to forever | A distilled fact store — if anyone built one |
| Procedural | How do I do this here? | Until the method changes | System prompt, tool definitions, skills, a markdown file |

**Working memory you don't build** — the model hands it to you on every call. Managing it is `context-management.md`.

**Episodic memory is the one everyone implements first**, because logging a transcript looks exactly like it and takes an afternoon. It grows without bound and gets over-retrieved.

**Semantic memory cannot be logged, only distilled.** An episode goes in, a claim comes out, and something has to perform that reduction. In most stacks nothing does, so the store fills with episodes and gets called semantic because the embeddings are semantic. If you have no consolidation step, you do not have semantic memory.

**Procedural memory is the one that overlaps your system prompt** — and the one this skill cares about most, because an agent writing to it is editing its own instructions.

## Consolidation: episodes into facts

The step that turns a log into memory. Run it out of band, not in the hot path.

```python
CONSOLIDATE = """Below is a completed session transcript.

Extract durable facts worth remembering for future sessions. A durable fact is
one that will still be true next week and that changes what the assistant
should do.

Include: stated preferences, environment facts, constraints discovered, and
corrections the user made.
Exclude: anything specific to this session's task, anything already obvious
from the codebase, and anything you are inferring rather than observing.

Return a JSON array of {claim, evidence, confidence}. Return [] if there is
nothing durable. Returning [] is the correct answer most of the time.

<transcript>{transcript}</transcript>"""
```

Three things make this work:

- **The empty answer must be explicitly blessed.** Without that line the model finds three facts in every session and your store fills with noise.
- **Every claim carries its evidence.** You will need it to adjudicate contradictions and to justify deletion later.
- **Deduplicate and reconcile on write.** A new claim that contradicts an existing one is a decision, not an append. Newer usually wins, but log the supersession.

## Procedural memory: the gated learned-rules pattern

An agent writing its own rules is a self-modifying system prompt. Genuinely useful, genuinely dangerous — a wrong rule learned from one bad session then shapes every future session, invisibly.

The split that makes it safe:

```text
learned/candidates.md    ← agent-writable, append-only, never loaded
AGENTS.md / CLAUDE.md    ← human-reviewed, loaded every request
```

Promotion requires all four: it recurred, it isn't already covered, it can't be enforced mechanically instead, and there is an eval case that fails without it. That last one is the criterion that lets you ever delete the rule again.

Entry format, observation-versus-inference, contradiction handling, pruning cadence, and the per-user privacy case: `learned-rules.md`.

## Anthropic's memory tool

Client-side. The model requests operations; **your handler executes them.**

```python
tools = [{"type": "memory_20250818", "name": "memory"}]
```

Commands: `view`, `create`, `str_replace`, `insert`, `delete`, `rename`, all scoped under `/memories`. That path is a prefix your handler maps onto real storage — a per-user directory, keys in a database, whatever you run. A later conversation continues from the same memory when it sends the same `tools` entry and your handler serves the same store.

**Do not write your own memory protocol instruction.** When the tool is present, the API injects one into the system prompt: view the memory directory first, record progress as you go, assume the context may reset at any moment. Writing your own copy means maintaining a duplicate of a string you don't control.

What is worth adding is **scope**, not mechanism:

```text
Only record information relevant to <domain> in your memory.
```

And, if files get cluttered despite the tool description already asking for tidiness:

```text
Keep your memory folder up to date, coherent, and organized. Rename or delete
files that are no longer relevant. Do not create new files unless necessary.
```

### Security is entirely yours

Every file operation is executed by your code, so:

- **Validate that every path starts with `/memories`.** Resolve to canonical form and verify it stays inside. Reject `../`, `..\\`, and URL-encoded variants like `%2e%2e%2f`. Use the platform's path utilities (`pathlib.Path.resolve()` plus `relative_to()`), not string matching.
- **Reject `delete` and `rename` on the memory root itself.**
- **Cap file sizes and cap what `view` returns**, letting the model page with `view_range`.
- **Expire stale files** that haven't been accessed in a long time.
- **Strip sensitive data before writing.** Models usually refuse to write secrets to memory; "usually" is not a guarantee you can build on.

```python
from pathlib import Path

ROOT = Path("/srv/agent-memory").resolve()

def resolve(user_id: str, virtual_path: str) -> Path:
    if not virtual_path.startswith("/memories"):
        raise ValueError("path outside memory root")
    rel = virtual_path.removeprefix("/memories").lstrip("/")
    base = (ROOT / user_id).resolve()
    target = (base / rel).resolve()
    target.relative_to(base)          # raises if traversal escaped
    return target
```

## Retrieval: don't dump memory into context

Memory that is always loaded is just a longer system prompt, with all the attention-budget and cache costs. Retrieve selectively:

- **Semantic facts**: retrieve by relevance to the current request. This is a retrieval problem — see `rag-pipeline-standard`.
- **Episodic**: retrieve rarely, and prefer a summary of a past session over its transcript.
- **Procedural**: this is the one case where always-loaded is often right, because it shapes every action. Which is exactly why it must stay small.

## Pitfalls

**Calling a transcript store semantic memory.** Without a consolidation step you have logs.

**Letting the agent promote its own rules.** Diff review plus an eval case, every time.

**No expiry or contradiction handling.** A fact store that only appends eventually contains both "the user prefers tabs" and "the user prefers spaces," and retrieval will pick one at random.

**Memory as a substitute for state.** Task status, test results, and progress belong in structured files and git, not in a fuzzy fact store. Memory is for what you learned, not for where you are.

**Duplicating the injected memory protocol.** You will maintain a stale copy of a string the API owns.

**Unbounded memory files.** Cap size, cap `view` output, page the rest.

**Trusting memory content as instructions.** Memory files are writable by a process that reads untrusted input. Treat their contents as data with the same suspicion as tool output — see `system-prompt-engineering`.
