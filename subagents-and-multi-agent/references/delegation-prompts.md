# Writing the Delegation Prompt

The Agent tool's prompt string is the **only** thing that crosses from parent to subagent. Not the conversation, not the tool results, not the reasoning that led here. A subagent asked to "fix the bug we discussed" knows nothing about any discussion.

This is the single most common subagent bug, and it presents as the subagent being stupid rather than as the prompt being empty.

## What crosses the boundary

| The subagent receives | The subagent does not receive |
|---|---|
| Its own system prompt | The parent's system prompt |
| The Agent tool's prompt string | The parent's conversation history |
| Project `CLAUDE.md` | The parent's tool results |
| Tool definitions (inherited, or the `tools` subset) | Preloaded skill content, unless listed in `skills` |

Everything in the right column that the subagent needs has to be restated in the prompt string.

## The five required elements

```text
1. OBJECTIVE      — what to determine or produce, in one sentence
2. CONTEXT        — every fact it needs: paths, ids, errors, decisions already made
3. CONSTRAINTS    — what not to do, what not to touch
4. DONE WHEN      — how it knows it has finished
5. RETURN FORMAT  — the exact shape of the final message
```

Missing any one of them produces a recognizable failure:

| Missing | Failure |
|---|---|
| Objective | Plausible work on the wrong question |
| Context | Rediscovers what the parent already knew, at full cost — or guesses |
| Constraints | Modifies something it shouldn't, or scope-creeps |
| Done when | Burns its budget looking for more |
| Return format | Returns prose the parent must re-read and re-summarize |

## Before and after

```text
BAD:
  "Look into the auth failures."
```

The subagent does not know which failures, where the code is, what has already been ruled out, or what "look into" ends with.

```text
GOOD:
  Determine why POST /api/v1/sessions returns 401 for users authenticated
  via SAML, while password-authenticated users succeed.

  Context:
  - Auth middleware: /repo/src/auth/middleware.py
  - SAML handler:    /repo/src/auth/saml.py
  - Failures started after commit a3f21c9 (2026-09-02)
  - Already ruled out: clock skew (checked, NTP is fine) and the
    certificate expiry (valid until 2027-03)
  - Example failing request id: req_8812f4

  Constraints:
  - Read-only. Do not modify any file.
  - Do not investigate the password auth path; it works.

  Done when: you can name the specific code path that produces the 401,
  or you have eliminated every path in those two files.

  Return:
  - The file:line where the 401 originates
  - The condition that triggers it
  - One sentence on why SAML hits it and password auth does not
  - If inconclusive: what you checked and the single next thing to check
```

The "already ruled out" block is the highest-value part and the one most often omitted. Without it the subagent re-checks clock skew, spends a third of its budget, and reports it as a finding.

## Every identifier, spelled out

```text
BAD                          GOOD
"the config file"       →    /repo/config/production.yaml
"that customer"         →    customer_id CUS-88213
"the failing test"      →    tests/auth/test_saml.py::test_session_creation
"the error we saw"      →    "SAMLResponse signature validation failed" (full text)
"last quarter"          →    2026-04-01 through 2026-06-30
```

If the parent had to look something up to know it, the subagent will have to look it up too — unless you paste it.

## Specify the return format precisely

The parent may summarize the subagent's final message rather than passing it through. A tight, structured return survives that; a five-paragraph essay does not.

```text
Return exactly:
  FOUND: <yes|no>
  LOCATIONS: <path:line, one per line, max 20>
  SUMMARY: <two sentences>
  NOT_FOUND: <what you searched for and did not find>
```

If you need the subagent's output verbatim, say so in the **parent's** prompt — "pass the subagent's findings through unchanged" — not in the subagent's. The parent is the one doing the summarizing.

## Sizing the task

The value of a subagent is the ratio of work done to output returned.

| Prompt | Compression | Verdict |
|---|---|---|
| "Find every call site of `legacy_auth()` and describe each usage context" | 30 files → 20 lines | Excellent |
| "Run the full test suite, report only failures with likely causes" | 4,000 lines → 15 lines | Excellent |
| "Read config.py and tell me what's in it" | 1 file → 1 file | Pointless — just read it |
| "Help with the refactor" | unbounded | No finish line; will burn the cap |
| "Coordinate with the test-runner agent on the approach" | needs negotiation | Should be one subagent |

A subagent whose summary is nearly as long as its input is an extra instance for nothing.

## Passing structured input

For anything with more than a handful of parameters, put the data in the prompt as a structured block rather than as prose:

```python
prompt = f"""Audit these services for unhandled promise rejections.

SERVICES (audit each, in this order):
{json.dumps(services, indent=2)}

For each service return: name | file:line of each unhandled rejection |
severity (crash|silent-failure|benign) | one-line fix.

Skip any service whose directory has no .ts or .js files; report it as skipped.
Do not modify any file."""
```

Prose degrades as the list grows. A JSON block stays parseable by the model at any length, and it makes the "in this order" instruction meaningful.

## Treat the return as untrusted

A subagent's final message is scanned for instruction-shaped patterns before the parent reads it — control-tag imitation, turn markers like a leading `Human:`. The scan neutralizes formatting rather than removing text.

The practical consequence: **a subagent's output is not a trusted channel into the parent.** If a subagent read attacker-controlled content — a web page, a user-submitted file, a third-party API response — its summary can carry that content's suggestions forward. Handle the return as data:

- Have the subagent return findings, not instructions. "Report what you found" rather than "recommend what I should do next."
- Validate structured returns against a schema before acting on them.
- Keep the decision to act in the parent, where the full context lives.

See `system-prompt-engineering`'s `references/prompt-injection.md` for the general shape of this.

## A template

```python
def delegate(objective, context: dict, constraints, done_when, return_format) -> str:
    facts = "\n".join(f"  - {k}: {v}" for k, v in context.items())
    return f"""{objective}

Context:
{facts}

Constraints:
{constraints}

Done when: {done_when}

Return:
{return_format}"""
```

Forcing `context` to be a dict is the useful part: it makes "what does this subagent actually need to know" an explicit list at the call site rather than something you hope you mentioned.
