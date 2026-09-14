# A Starter Subagent Roster

Four subagents cover most of what teams actually need. Each is defined by the same four decisions: what it does, what it may touch, what it returns, and which model it runs on.

Every one of these is high-compression — much input, little output — which is the property that makes a subagent worth its instance cost. A subagent that reads one file and returns its contents is pure overhead.

## explore

Reads widely, returns a map. The highest-compression pattern there is.

```python
AgentDefinition(
    description=(
        "Searches the codebase to locate and map code. Use to find where "
        "something is implemented, enumerate call sites, or map a module's "
        "structure before changing it. Returns file:line locations with brief "
        "context, never file contents."
    ),
    prompt="""You are a codebase explorer.

Find what was asked for and report locations, not contents.

Return:
- A list of `path:line` entries, each with one line of context
- A two-sentence summary of the overall structure you found
- Anything you searched for and did not find, stated explicitly

Never paste file bodies. Never modify anything. If the search space is
ambiguous, report what you searched and what you would search next.""",
    tools=["Read", "Grep", "Glob"],
    model="sonnet",
)
```

"Never paste file bodies" is the line doing the work. Without it, an explorer returns the thing it was supposed to compress.

"Anything you did not find, stated explicitly" is the second-most valuable line: a silent absence is indistinguishable from a search that was never run.

## triage

Classifies and prioritizes a pile of things. Cheap model, narrow output.

```python
AgentDefinition(
    description=(
        "Triages a set of failures, errors, or tickets into categories with "
        "severities. Use when there are many items and you need the ranked "
        "shortlist rather than the full set."
    ),
    prompt="""You are a triage specialist.

For each item, output exactly one row:
  severity (critical|high|medium|low) | category | one-line description | evidence location

Rank by severity, then by blast radius. End with a two-sentence summary
naming the single item to address first and why.

Do not propose fixes. Do not investigate beyond what is needed to classify.""",
    tools=["Read", "Grep"],
    model="haiku",
)
```

"Do not investigate beyond what is needed to classify" bounds the run. Triage subagents that start debugging are the most common budget overrun in this roster.

## verify

Runs the checks and reports only what failed. Structurally unable to write.

```python
AgentDefinition(
    description=(
        "Runs tests, linters, and type checks and reports failures. Use to "
        "confirm a change is sound before handing it back. Returns only "
        "failures with their causes — never a full passing log."
    ),
    prompt="""You are a verification specialist.

Run the project's checks. Report only what failed:
- the check that failed
- the assertion or error message, verbatim
- the most likely cause, in one sentence
- the file:line to look at

If everything passes, say exactly: "All checks passed." and list what you ran.
Do not fix anything. Do not modify files.""",
    tools=["Bash", "Read", "Grep"],
    model="sonnet",
)
```

Note `Bash` is present — verification needs to execute — but `Edit` and `Write` are not. A verifier that can fix things will fix things, and you will lose the signal about what was broken.

"Report only what failed" matters more than it sounds: a full passing test log is thousands of tokens of nothing.

## audit

Reviews against criteria. Read-only by construction.

```python
AgentDefinition(
    description=(
        "Reviews code for security, correctness, and maintainability issues. "
        "Use before merging or when asked to check quality. Returns a findings "
        "list. Does not modify files."
    ),
    prompt="""You are a code review specialist.

Review the files named in your instructions. For each finding:
  severity | file:line | what is wrong | why it matters | suggested fix (one line)

Order by severity. Report at most 10 findings — if there are more, say so
and report the 10 that matter most.

Only report what you can point at. Do not speculate about code you have not
read. If you found nothing at a given severity, say so explicitly.""",
    tools=["Read", "Grep", "Glob"],
    model="sonnet",
)
```

The cap of 10 is deliberate. Uncapped reviewers pad the list to look thorough, and a 40-item list of nits buries the two real bugs.

## Wiring them up

```python
async for message in query(
    prompt="Review the authentication module for security issues",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Grep", "Glob", "Agent"],   # Agent enables delegation
        agents={
            "explore": explore_def,
            "triage": triage_def,
            "verify": verify_def,
            "audit": audit_def,
        },
        env={
            "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "1",
            "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": "5",
        },
        max_budget_usd=5.0,
    ),
):
    if hasattr(message, "result"):
        print(message.result)
```

Subagents can also live as markdown files in `.claude/agents/`, with YAML frontmatter and the body as the system prompt. Programmatic definitions take precedence over filesystem ones with the same name.

## The four design decisions, applied

| | explore | triage | verify | audit |
|---|---|---|---|---|
| Compression | Very high | High | High | Medium |
| Tools | Read-only | Read-only | Read + execute | Read-only |
| Model | Mid | Cheap | Mid | Mid |
| Output shape | Location list | Ranked rows | Failures only | Capped findings |

**Tool restriction is structural, not advisory.** A tool omitted from `tools` is not in the subagent's session at all — no permission prompt, no error, it simply cannot happen. This is stronger than any instruction, and it is why "do not modify files" appears in the prompt *and* in the tool list.

**Model tiering is not automatic.** Subagents inherit the parent's model by default, so a triage subagent left on the default costs the same per token as the orchestrator. Set `model` explicitly on every bounded subagent.

## Writing the `description`

The parent decides delegation from the `description` exactly as it decides tool calls from tool descriptions. The same rules apply — see `tool-design`.

```python
# BAD — the parent cannot tell these apart
description="Helps with code."
description="Code specialist."

# GOOD — distinct trigger conditions and stated return shape
description=("Searches the codebase to locate code. Use to find where something "
             "is implemented or map a module before changing it. Returns "
             "file:line locations, not file contents.")
```

If the parent is not delegating, the description is usually why. The diagnostic: name the subagent explicitly in the prompt. If it delegates correctly when named and not otherwise, the description is the problem — not the subagent.

## What not to make a subagent

- **A "planner."** Planning needs the parent's full context, which is exactly what a subagent does not get.
- **A "writer" that produces the final answer.** The parent may summarize a subagent's final message rather than passing it through. If the output is the deliverable, produce it in the parent.
- **Anything that reads one file.** No compression, full instance cost.
- **Anything that must negotiate with another subagent.** If two subagents need to talk, they are one subagent.
- **Domain instructions with no isolation need.** That is a skill. Skills load into the parent's context, cost nothing extra, and are the right answer far more often than people expect.
