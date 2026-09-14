# The Self-Updating Rules File

Giving an agent a markdown file it can write to, so it accumulates what it learns about the user, the project, and the conventions. The pattern people mean by "make it learn from me."

It is worth building. It is also **a system prompt that edits itself**, so the whole design problem is the gate between what the agent writes and what gets loaded.

## The two-file split

```text
learned/candidates.md   agent-writable, append-only, never loaded into context
AGENTS.md / CLAUDE.md   human-reviewed, loaded on every request
```

The agent proposes; a human promotes. Nothing the agent writes changes its own behavior until someone reviews a diff.

**Why not let it write directly to the loaded file?** Three reasons, in increasing order of how much they will cost you:

1. A rule learned from one bad session shapes every future session.
2. The file grows monotonically. Agents append; they do not prune.
3. Nothing in a later failure points back at the rule that caused it. You get "the agent has been weird lately" and no diff to bisect.

If you only take one thing from this file: **the writable file and the loaded file are not the same file.**

## Candidate entry format

Structure is what makes the review possible. Freeform notes produce a file nobody reads.

```markdown
## 2026-03-14 — migrations need the schema regenerated
Observed: added a column to `users`, tests failed with a stale-type error.
Took 3 turns to find that `pnpm db:generate` must run after every migration.
Proposed rule: After editing anything in `db/migrations/`, run `pnpm db:generate`.
Evidence: session a4f2, turns 12-18.
Recurrence: 2nd occurrence (first: session 91c0, 2026-03-02).
```

Five fields, all load-bearing:

| Field | Why it's there |
|---|---|
| Date + one-line title | Makes the file scannable and lets you expire stale entries |
| **Observed** | The raw event. This is what you adjudicate against later |
| **Proposed rule** | Forces the agent to state the general form, which is where bad generalizations become visible |
| **Evidence** | Session and turn references. Without these you cannot verify or delete |
| **Recurrence** | The promotion gate's first criterion, tracked at write time rather than reconstructed |

The instruction that produces this:

```text
When you discover something about this project or the user's preferences that
would have saved you time if you had known it at the start, append an entry to
learned/candidates.md using the format at the top of that file.

Record what you observed, not what you concluded from it. One entry per
discovery. Do not edit existing entries; if something recurred, append a new
entry noting the earlier one.

Do not write an entry for anything that is already stated in AGENTS.md, already
in a tool description, or discoverable by reading the code.
```

That last paragraph is the one that keeps the file from filling with restatements of things the agent could have looked up.

## Observations, not inferences

The most common failure is a file full of confident personality readings.

```markdown
# BAD — inferences, unfalsifiable, and wrong about the next case
- The user values clean architecture and dislikes shortcuts.
- The user prefers TDD.
- The user is detail-oriented and wants thorough explanations.
```

```markdown
# GOOD — observations, each traceable to an event
- On 03-02 and 03-11 the user asked for the test to be written before the
  implementation. (sessions 91c0, b7d1)
- The user has twice removed explanatory comments I added to obvious code,
  with the note "the code says this." (sessions b7d1, c440)
- The user stops long responses with "just the answer" when the question was
  a yes/no. (4 occurrences)
```

The good version generalizes *less*, which is the point. "The user values clean architecture" licenses the agent to refactor unprompted. "The user removed comments I added to obvious code" licenses exactly one behavior change.

**What is worth recording:**

- Stated preferences, in the user's words
- Corrections the user made, and what they corrected *from*
- Environment facts that cost time to discover — service startup order, which test suite is slow, what needs to run after what
- Constraints found the hard way — "the staging DB resets nightly, don't rely on seeded data"
- Conventions the code follows but doesn't document

**What is not:**

- Anything inferable from the manifest, the README, or the source tree
- Task state — what is in progress belongs in git and a progress file, not in learned rules
- One-off requests. "Use snake_case here" said once about one file is not a project convention
- Anything already in the loaded file, a tool description, or a hook

## The promotion gate

Review the candidates file on a cadence — weekly, or when it passes ~20 entries. For each candidate, all four must hold:

1. **It recurred.** One occurrence is an incident. Two is a pattern. The recurrence field makes this a lookup rather than a judgment call.
2. **It isn't already covered** by an existing rule, a tool description, a skill, or the model's defaults. Check by searching the loaded file, not by memory.
3. **It cannot be enforced mechanically instead.** If a formatter, a lint rule, a test, a permissions entry, or a pre-commit hook can decide it, that is where it goes. Instructions are advisory; hooks run regardless.
4. **There is an eval case that fails without it.** Write the case first. If you cannot construct an input where the presence of the rule changes the output, the rule is not doing anything.

Criterion 4 is skipped almost universally and is the one that matters most, because it is the only thing that makes the rule *deletable*. A file where every line might be load-bearing and none can be tested is a file that only ever grows.

Promotion is a normal diff review: the rule goes in the loaded file, the eval case goes in the suite, both in the same commit, and the candidate entry is marked promoted rather than deleted — you will want the evidence trail when the rule is questioned in six months.

## Contradiction and supersession

A candidate that contradicts a promoted rule is the interesting case, and the one that silently corrupts the file if handled by appending.

- **Newer wins by default**, but record the supersession rather than overwriting. `Superseded 2026-05-02: the user now wants X, previously Y (session d81a).`
- **A contradiction that recurs in both directions is not a rule at all** — it is context-dependent, and the fix is a conditional rule that names the boundary, the same way a contradictory system prompt gets fixed. See `system-prompt-engineering`.
- **Never let the agent resolve a contradiction with a promoted rule on its own.** It has one session of evidence against a rule that was promoted with a test behind it.

## Pruning

Nothing about this pattern removes anything, which is how instruction files become graveyards.

- **Run the eval suite with each rule removed, on a schedule.** Rules that change no measured behavior come out. This is the only reliable pruning signal, and it exists only if criterion 4 was enforced.
- **Rules encode capability gaps, and gaps close.** A rule added to stop a model from over-explaining may be dead weight two model versions later. Re-audit on every model change.
- **Expire unpromoted candidates.** An entry that has sat for three months without recurring is not going to recur.
- **Cap the loaded file.** Anthropic's guidance for `CLAUDE.md` is under 200 lines; teams reporting good results run shorter. When promotion would push past the cap, something else has to come out or move into a path-scoped file or a skill.

## Per-user versus per-project

They are different files with different rules, and merging them is a common mistake.

| | Per-project | Per-user |
|---|---|---|
| Lives in | The repo, committed | User config, not committed |
| Reviewed by | Whoever reviews PRs | The user |
| Contains | Conventions, commands, constraints | Preferences, communication style, defaults |
| Risk | A wrong rule affects the whole team | A wrong rule affects one person, invisibly |
| Privacy | None | Real — it is a behavioral profile of a person |

Per-user files need one thing per-project files don't: the user must be able to **read the whole thing, in plain language, and delete any line.** A file of accumulated observations about someone that they cannot inspect is a profile they did not consent to. Surface it on request, keep it human-readable for exactly this reason, and never write anything into it you would not show them.

## Pitfalls

**One file, agent-writable and loaded.** The failure that makes every other item here moot.

**Recording inferences.** "The user values X" is a personality read from a handful of interactions and will be wrong about the next case.

**No recurrence tracking.** Every incident becomes a rule and the file doubles monthly.

**Promotion without an eval case.** The rule can never be deleted, because nobody can show it does nothing.

**Appending a contradiction.** The file now says both things and retrieval picks one.

**Learned rules doing a hook's job.** 100% compliance is available for free; an instruction gets you less than that at a per-request cost.

**Never pruning.** Rules encode gaps; gaps close. A file nobody deletes from stops being read.

**A per-user profile the user cannot see.** Keep it inspectable and deletable.
