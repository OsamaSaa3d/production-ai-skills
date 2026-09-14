# AGENTS.md and CLAUDE.md

A project instruction file is a system prompt with a different filename. Everything in `SKILL.md` applies — altitude, contradictions, the deletion test — plus one constraint the others don't have: **it loads on every request in that project, whether or not the task needs it.**

That makes it the single most expensive place to be wrong, and the place bloat is least visible, because nobody re-reads a file that has been there for six months.

## The budget

Anthropic's guidance for `CLAUDE.md` is **under 200 lines**. Teams reporting good results run far shorter — 30 to 80 lines is common for a single-service repo.

The failure at length is not that the model cannot read 400 lines. It is that **a bloated file causes the model to ignore the instructions you actually care about.** The three rules that matter get the same weight as the twenty that restate the README, and nothing signals which is which.

If you are over budget, the fix is almost never compression. It is relocation — see *Pushing guidance down* below.

## What earns a line

The test: **would a competent new contributor, with the repo open in front of them, get this wrong?** If they'd get it right by reading the code, it doesn't earn a line.

| Earns a line | Why |
|---|---|
| One-sentence project description | Orients everything else; cheap |
| Non-obvious commands, with flags and working directory | `pnpm test` in the wrong directory silently passes zero tests |
| Expensive operations to avoid | A full rebuild the agent didn't know was 12 minutes |
| Verification steps | What "done" means here, concretely |
| Hard boundaries | Directories not to touch, systems not to call |
| Gotchas not inferable from the tree | "Migrations need `db:generate` after"; "staging DB resets nightly" |

| Does not | Why |
|---|---|
| "Write clean, maintainable code" | No concrete signal; pure token cost |
| Dependency lists, directory trees | Readable from the manifest, and goes stale |
| Coding style the formatter enforces | The formatter already won; see below |
| Architecture essays | Relocate to a doc the agent reads when it needs it |
| Anything restating a tool description | Second source of truth that ages on its own |

```markdown
# BAD — every line is either unverifiable or free to look up
This project uses React, TypeScript, Vite, TailwindCSS, and Vitest.
The src/ directory contains components/, hooks/, utils/, and types/.
Please write clean, maintainable, well-documented code.
Follow best practices and industry standards.
Use meaningful variable names.
Make sure to handle errors appropriately.
```

```markdown
# GOOD — six lines a new contributor would get wrong
Billing service for the checkout flow. Talks to Stripe; never to the ledger directly.

- Tests: `pnpm test --run` from `packages/billing`. Bare `pnpm test` watches and
  from the repo root it matches nothing and exits 0.
- After editing `db/migrations/`, run `pnpm db:generate` or the types go stale
  and the failure surfaces as an unrelated type error.
- `pnpm build` is ~11 minutes. Use `pnpm build:pkg billing` while iterating.
- Never edit `src/generated/`. It is regenerated from the OpenAPI spec.
- Staging DB resets at 04:00 UTC; do not rely on seeded rows persisting.
```

The second file is shorter and does strictly more work, because every line prevents a specific, observed mistake.

## Put must-always rules in hooks

This is the highest-leverage move available and it reduces the file rather than growing it.

Instructions are advisory — the model decides whether to follow them. **Hooks run regardless.** A rule moved into a formatter, a test, a pre-commit hook, or a permissions entry gets 100% compliance at zero instruction budget.

| Rule | Where it actually belongs |
|---|---|
| Run the formatter after editing | A hook or pre-commit |
| Never commit with failing tests | A hook or CI |
| Regenerate types after a migration | A build step, or a path-scoped hook |
| Don't touch `vendor/` or `src/generated/` | Permissions config |
| Conventional-commit messages | A commit-msg hook |
| "Prefer composition over inheritance here" | The file — it needs judgment |

**If a deterministic check can decide it, don't ask the model.** The only rules that belong in prose are the ones requiring judgment.

## Pushing guidance down

Over budget? Relocate rather than compress:

- **Nested files.** A `packages/billing/AGENTS.md` loads when the agent works there. Note the caveat: nested files *merge into* context based on where the agent is working, so splitting one file into three does not by itself reduce what a task in that directory pays. It reduces what tasks *elsewhere* pay.
- **Path-scoped rules**, where the harness supports them — the same idea with finer granularity.
- **Skills.** Domain guidance with a clear trigger belongs in a skill: ~100 tokens of metadata resident, the body loaded only when relevant. This is the biggest win available for anything task-specific.
- **A doc the agent can find.** "Architecture notes are in `docs/architecture.md`" costs one line and pays for the rest only when needed.

The principle from `SKILL.md` applies unchanged: **a prompt that knows where to look beats a prompt that contains everything.**

## Treat it like code

- **Commit it.** A file that varies per developer produces behavior that varies per developer.
- **When you add a rule, verify the behavior actually changed.** Add it, run the task that motivated it, confirm the difference. Most added rules do nothing, and an unverified rule is indistinguishable from a placebo.
- **Review it on a schedule.** Quarterly, or on every model change. Rules encode capability gaps and gaps close — a rule added to stop over-explaining may be dead weight two model generations later.
- **Auto-generated files are first drafts.** `init`-style commands optimize for comprehensiveness, which is the wrong objective here. Expect to delete most of the output.
- **Agent-written rules need a gate.** Letting the agent append to this file directly is a self-modifying system prompt; see `context-and-memory` for the two-file split and the promotion criteria.

## Pitfalls

**Treating length as thoroughness.** The file's job is to be read and followed, and past a point more lines gets you less of both.

**Restating the README.** If it's in the manifest, the README, or the tree, it costs tokens and goes stale.

**Style rules a formatter enforces.** Free compliance is available; prose gets you less than that at a per-request cost.

**One giant root file for a monorepo.** Every task in every package pays for every other package's conventions.

**Committing the auto-generated draft unedited.** Comprehensiveness is the wrong objective.

**Never pruning.** The file only grows, and the rules you care about get diluted by the ones you forgot.

**Adding a rule without checking whether an existing one contradicts it.** Same failure as any system prompt, and harder to spot here because nobody reads the whole file at once.
