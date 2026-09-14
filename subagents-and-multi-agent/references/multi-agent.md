# Genuinely Separate Agents

Separate coordinating agents are independent instances across sessions, each with its own context, able to message each other. This is the narrowest case in the skill and the most expensive. Everything below assumes you have already cleared the gate.

For the architecture-selection argument and the cost model, see `agent-vs-workflow-decision/references/multi-agent.md`. This file is about what changes once agents are actually separate: handoffs, and the failure modes that only exist here.

## The gate, restated

> **Can each agent complete its part without knowing what the others found?**

Independent — separate agents are possible:

```text
"Research the competitive landscape for X"
  → pricing across five competitors
  → public funding history
  → published customer counts
```

Dependent — separate agents will fail:

```text
"Refactor the auth module and update its callers"
  → rename          ← callers depend on the new name
  → update callers  ← depends on the rename
  → update tests    ← depends on both
```

Anthropic states the limit directly: domains requiring all agents to share the same context, or involving many dependencies between agents, are not a good fit today. Coding is the canonical bad fit.

**If the subtasks are not independent, you want orchestrator-workers inside one agent.** See `orchestrator-workers.md`.

And one more gate on top of independence: **separate agents are only warranted when the peers must negotiate.** Independent subtasks that merely need to run in parallel and report back are subagents — same isolation, same parallelism, a fraction of the machinery. Reserve separate agents for the case where one specialist genuinely is not enough *and* they need to talk through a plan.

## The reference point

Anthropic's research system — an orchestrator with parallel subagents — reported roughly a **90% improvement over a single agent** on their internal research eval, at roughly **15x the tokens of a chat interaction**, with token usage explaining most of the performance variance.

Token spend being the dominant variable is the operative fact: this architecture *buys* performance with tokens rather than making tokens go further. That makes it an economic question every time.

## Handoffs

A handoff is where separate agents differ most from subagents, and where they break.

A subagent return is a single final message the parent reads once. A handoff is an ongoing exchange, which means every message is a place for context to be lost, duplicated, or corrupted.

**Make the handoff a typed artifact, not a conversation.**

```python
class Handoff(BaseModel):
    from_agent: str
    to_agent: str
    objective: str = Field(description="What the receiving agent must determine.")
    findings: list[Finding] = Field(description="What is already established.")
    open_questions: list[str] = Field(description="What is not yet known.")
    constraints: list[str] = Field(description="What the receiver must not do.")
    provenance: dict[str, str] = Field(description="finding id -> where it came from")

class Finding(BaseModel):
    id: str
    claim: str
    confidence: Literal["established", "likely", "speculative"]
    evidence: str
```

Four things this buys that free-form messaging does not:

- **Validation.** A malformed handoff fails at the boundary rather than three agents later.
- **Confidence survives.** `speculative` stays `speculative` instead of being restated as fact by the next agent — which is the single most common degradation in a chain.
- **Provenance survives.** You can trace a final claim back to its origin. Without this, debugging a wrong answer across four agents is guesswork.
- **It is loggable.** The exchange becomes data you can replay.

**Cap the number of handoffs.** Every hop re-bills the context it carries and adds a chance to lose something. Three hops is a lot. A run that needs seven is one agent that was split badly.

## Coordination failure modes

These exist only here. Subagents are immune to all of them because they cannot talk.

**Confidence laundering.** Agent A reports "possibly caused by the cache layer." Agent B reads it and writes "the cache layer is the cause." Agent C builds on B. The speculation is now load-bearing and nothing in the transcript flags it. *Mitigation:* the `confidence` field above, plus an explicit instruction that receiving agents may not raise a confidence level.

**Duplicated work.** Two agents given overlapping objectives run the same searches and pay twice. *Mitigation:* state non-overlap in the decomposition, and log tool calls per agent to check whether it held.

**Deadlock on negotiation.** Two agents each waiting for the other's conclusion. *Mitigation:* a designated decider for every contested question, named in advance. "Agents discuss until they agree" has no termination proof.

**Context divergence.** Agents built a shared assumption early and drift apart as each updates it privately. By the time they compare notes they are describing different worlds. *Mitigation:* make shared state an explicit artifact both read, not something each remembers.

**Silent failure absorbed by synthesis.** One agent fails, the synthesizer has enough from the others to produce something confident, and nobody notices a third of the question went unanswered. *Mitigation:* fail loudly — name failed agents in the output and refuse to synthesize below a coverage threshold.

**Recursive spawn.** An agent that can spawn agents turns one run into a tree. A subagent that recursively spawns more subagents, or a tool returning oversized results, can multiply a run by another order of magnitude. *Mitigation:* depth caps, and a budget cap that actually stops in-flight work.

## Treat peer messages as untrusted

Messages from another agent are not a trusted channel. If any agent in the system reads external content — web pages, user-submitted files, third-party API responses — that content can travel through the exchange as instructions.

- Handoffs carry **findings, not directives.** "Here is what I found" rather than "here is what you should do next."
- Validate every inbound handoff against the schema before acting on it.
- Keep irreversible actions behind the same gates as anywhere else: a peer agent asking for one is not authorization.

See `system-prompt-engineering/references/prompt-injection.md`.

## Scale changes the shape

For orchestrating dozens to hundreds of agents, turn-by-turn delegation stops being the right mechanism. That work belongs in a script or workflow that runs orchestration outside the conversation context entirely — a queue, a state machine, a job runner. At that scale you are building a distributed system that happens to call models, and it should look like one: durable state, retries, idempotency, observability.

The tell that you have crossed the line: the orchestrator's context is mostly bookkeeping about other agents rather than about the problem.

## Before you ship

- [ ] Independence test passed, written down, with the reasoning
- [ ] Peers genuinely need to negotiate — otherwise these are subagents
- [ ] Handoffs are typed, validated, and carry confidence and provenance
- [ ] Handoff count capped
- [ ] A named decider for every contested question
- [ ] Failed agents surfaced in the output, never silently dropped
- [ ] Depth, concurrency, and budget caps, all three, all tested by forcing them
- [ ] Measured against orchestrator-workers on the same task set

The last one decides it. Multi-agent has to beat orchestrator-workers by enough to justify 15x. Frequently it does not, and finding that out costs an afternoon instead of a quarter.
