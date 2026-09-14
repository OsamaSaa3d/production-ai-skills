# Production AI Skills

Agent skills that make coding agents write **production-grade LLM integration code** — instead of the framework spaghetti they reach for by default.

Ask an agent to "build me an agent that can query our database" and you usually get `AgentExecutor`, a ReAct prompt, a regex parser, and a retry loop wrapped around a call that already had a schema guarantee. Not because the agent is bad, but because that pattern dominates the training data. These skills replace that default with the one a senior engineer would pick: call the API directly, turn on strict mode, measure it, and add complexity only where a measurement says it helps.

Every skill is written to be **argued with**. Each one states its defaults, the evidence behind them, the pitfalls, and — explicitly — *when to break the rules*.

## Install

Skills are directories. Drop the ones you want where your agent looks for them.

**Claude Code** — project-scoped (checked in, shared with your team):

```bash
git clone https://github.com/OsamaSaa3d/production-ai-skills-temp
mkdir -p .claude/skills
cp -r production-ai-skills-temp/{llm-tool-calling,structured-output,tool-design} .claude/skills/
```

Or user-scoped, available in every project:

```bash
cp -r production-ai-skills-temp/* ~/.claude/skills/
```

**Anything else** — the skills are plain markdown with YAML frontmatter and no runtime dependency. Point your harness at the directories, or paste a `SKILL.md` into a system prompt.

Take the whole set or a few. They cross-reference each other but each stands alone.

## The skills

| Skill | Use it when | Covers |
|---|---|---|
| [**agent-vs-workflow-decision**](agent-vs-workflow-decision/) | Before writing any code for an "agent" | Single call vs workflow vs agent vs multi-agent; the five workflow patterns; the cost multipliers |
| [**llm-tool-calling**](llm-tool-calling/) | The model needs to invoke functions | Native tool calling, strict mode, the agent loop, why not frameworks |
| [**tool-design**](tool-design/) | Designing, naming, or refactoring agent tools | Naming and decomposition, typed fields over query strings, tool use examples, tool search, programmatic calling |
| [**structured-output**](structured-output/) | You need data back, not prose | JSON Schema + strict mode, extraction and classification patterns, refusal and truncation handling |
| [**system-prompt-engineering**](system-prompt-engineering/) | Writing or debugging a system prompt | Altitude, contradiction debugging, metaprompting, cache-safe assembly, trust boundaries, versioning |
| [**context-and-memory**](context-and-memory/) | A task outruns the context window, or must survive a reset | Compaction, tool-result clearing, the four memory types, self-updating rules files |
| [**rag-pipeline-standard**](rag-pipeline-standard/) | Retrieval over private data | RAG vs tools vs direct context, chunking, contextual retrieval, hybrid search, reranking |
| [**subagents-and-multi-agent**](subagents-and-multi-agent/) | Someone proposes splitting into multiple agents | Context isolation, delegation prompts, orchestrator-workers, cost caps |
| [**model-selection**](model-selection/) | Choosing a model, or the bill is too high | Capability gating, cost per *successful* task, eval-driven escalation |
| [**evals-before-shipping**](evals-before-shipping/) | Any change to a prompt, model, tool, or retriever | Tool-call and RAG suites, trajectory metrics, judge calibration, CI |

Rough order if you're starting cold: **agent-vs-workflow-decision** to pick the architecture, **llm-tool-calling** or **structured-output** to build it, **evals-before-shipping** to find out whether it works.

## How a skill is laid out

```
skill-name/
├── SKILL.md            # the whole practice, loaded when the skill triggers
└── references/         # loaded only when SKILL.md points at them
    └── topic.md
```

`SKILL.md` carries the decisions. References carry the detail — full payload shapes, worked examples, complete harnesses — and cost nothing until something reads them. This is progressive disclosure: the metadata is always resident, the body loads on trigger, the references load on demand.

## Two conventions, enforced in CI

**Provider-neutral.** These skills are not about one vendor. Code samples name a provider's syntax to stay concrete, but no skill assumes you're on a particular API, and vendor model ids never appear hardcoded in a sample — they're placeholders you pin yourself. Genuinely provider-specific features (`defer_loading`, `input_examples`, server-side context editing) are labelled as such where they appear, with the portable alternative named.

**Verify before you build.** Endpoint shapes, parameter names, limits, and model support all move, and a skill that quietly goes stale is worse than no skill. Every file naming an API surface carries a banner telling the agent to check the provider's live reference first — and to correct any drift it finds with the *smallest possible edit*, so the surrounding argument survives.

`scripts/lint_skills.py` enforces both, plus frontmatter validity, name/directory agreement, description length, and link integrity in both directions.

```bash
python3 scripts/lint_skills.py
```

No dependencies — standard-library Python 3. It runs on every push and pull request.

## Contributing

Same bar the skills set for themselves:

- **Every claim earns its place.** A number needs a source; a rule needs the failure it prevents. Run the deletion test — if removing a line changes no behavior, it shouldn't be there.
- **Defaults, not laws.** Say when the rule is wrong, not just when it's right.
- **Add the "when to break the rules" case.** If you can't think of one, you probably don't understand the rule yet.
- **Run the linter before opening a PR.**

## License

MIT — see [LICENSE](LICENSE).
