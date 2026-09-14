# The Five Workflow Patterns, Implemented

Each of these is orchestration code you write, not a framework feature. That is the point: the control flow is in your repository, readable in a diff, and debuggable with a breakpoint.

All five are shown with direct API calls. Swap the provider; the shape does not change.

## 1. Prompt chaining

Fixed sequential steps, each call consuming the last output, with **programmatic gates between them**. The gates are the pattern — without them you have a pipeline, not a chain.

```python
def draft_and_localize(brief: str, locale: str) -> str:
    copy = call(SYSTEM_COPYWRITER, brief)

    # the gate: cheap, deterministic, in your code
    if not (50 <= word_count(copy) <= 200):
        copy = call(SYSTEM_TRIM, copy, target="120 words")
    if contains_banned_terms(copy):
        raise ContentRejected(copy)

    return call(SYSTEM_TRANSLATOR.format(locale=locale), copy)
```

**Use when** the task decomposes cleanly into fixed subtasks. It trades latency for accuracy by making each individual call easier — each model call is doing one thing with a narrower prompt.

**The gate options**, cheapest first: a regex or length check, a schema validation (`structured-output`), a deterministic rule, and only then a model-based check. Reach for the model only when nothing cheaper expresses the condition.

**Failure mode:** silent degradation when an early step produces something plausible but wrong. Log each intermediate output with a run id, or you will be debugging the last step forever.

## 2. Routing

Classify the input, dispatch to a specialized prompt, model, or pipeline.

```python
class Route(BaseModel):
    category: Literal["refund", "technical", "sales", "general"]
    reasoning: str

def handle(message: str) -> str:
    route = classify(message, Route, model=SMALL_MODEL)   # structured output
    return HANDLERS[route.category](message)
```

**Use when** there are distinct input categories better handled separately *and* classification is reliable. Both halves matter — routing on a 70%-accurate classifier makes the system worse, because 30% of traffic now hits a prompt written for something else.

This is also the primary cost-control pattern: easy inputs to a small fast model, hard ones to a large one. See `model-selection`.

**Classify with code where you can.** A regex on an order-id format beats a model call. If the classification needs a model, use the small one — a cheap classifier in front of an expensive generator usually pays for itself.

**Failure mode:** no fallback route. Every taxonomy needs a `general` arm, and you should count how often it fires. A rising rate means the taxonomy no longer matches the traffic.

## 3. Parallelization

Two distinct variants people conflate.

**Sectioning** — independent subtasks, run concurrently, results combined:

```python
async def moderated_reply(message: str) -> Reply:
    reply, screen = await asyncio.gather(
        acall(SYSTEM_ASSISTANT, message),
        acall(SYSTEM_POLICY_SCREEN, message),      # separate call, separate attention
    )
    return Reply(text=reply) if screen.ok else Reply(text=POLICY_REFUSAL)
```

Asking one call to both answer and screen is worse than two calls, because the two objectives compete for attention within a single generation. Splitting them lets each prompt be about one thing.

**Voting** — same task several times, aggregate:

```python
async def flag_content(text: str, threshold: int = 2, n: int = 3) -> bool:
    votes = await asyncio.gather(*[acall(SYSTEM_MODERATE, text) for _ in range(n)])
    return sum(v.violates for v in votes) >= threshold
```

The threshold is the knob: `threshold=1` maximizes recall (catch everything, more false positives), `threshold=n` maximizes precision. Pick it from what a miss costs versus what a false positive costs — the same unit-economics math as an accuracy target.

Vary the prompts across voters if you want diversity rather than just sampling noise; identical prompts at temperature 0 give you one opinion three times at three times the price.

## 4. Orchestrator-workers

A model breaks the task into subtasks **determined at runtime**, delegates them, and synthesizes.

```python
class Plan(BaseModel):
    subtasks: list[str] = Field(description="Independent subtasks, at most 6.")

async def research(question: str) -> str:
    plan = call(SYSTEM_PLANNER, question, schema=Plan)          # runtime decomposition
    findings = await asyncio.gather(*[
        acall(SYSTEM_WORKER, t) for t in plan.subtasks[:MAX_WORKERS]
    ])
    return call(SYSTEM_SYNTHESIZER, question=question, findings=findings)
```

**Use when you cannot know the subtasks in advance.** That is the entire distinction from parallelization — topologically they are the same graph, but here the shape of the graph is decided by the model.

This is the pattern most "multi-agent" proposals actually want. It keeps one agent's control flow, gets parallelism and context isolation, and has no inter-agent negotiation to go wrong. See `multi-agent.md` for the narrow case where separate agents beat it.

**The cap is not optional.** `plan.subtasks[:MAX_WORKERS]` is doing real work — an unbounded planner will occasionally return forty subtasks and you will pay for all of them.

## 5. Evaluator-optimizer

Generate, critique, repeat.

```python
def refine(task: str, max_rounds: int = 3) -> str:
    draft = call(SYSTEM_WRITER, task)
    for _ in range(max_rounds):
        critique = call(SYSTEM_CRITIC, task=task, draft=draft, schema=Critique)
        if critique.acceptable:
            break
        draft = call(SYSTEM_WRITER_REVISE, task=task, draft=draft,
                     feedback=critique.feedback)
    return draft
```

**Use when** you have clear evaluation criteria *and* iterative refinement measurably helps. Two signs of fit, both required: a human articulating feedback would improve the output, and a model can produce that feedback.

**Failure modes, both common:**

- **The critic always finds something.** Without an explicit `acceptable` field and a round cap, this loop runs forever, getting worse. Make approval a first-class output.
- **Round two is worse than round one.** Measure it. Log every round's output and score them; if the curve is flat after the first revision, one round is the pattern.

Literary translation and complex search are the documented good fits — domains with nuance a first pass misses and a reviewer can name.

## Composition

They compose, and most real systems are two or three of them:

```text
route ──> refund path:    chain (verify → compute → issue)
      └─> technical path: orchestrator-workers (search logs, docs, tickets) → synthesize
```

Keep the composition in code. The moment the composition itself is decided by a model, you have moved down a rung on the escalation ladder — which may be correct, but it should be a decision, not a drift.

## Choosing between them

| Situation | Pattern |
|---|---|
| Fixed steps, each needs the previous output | Prompt chaining |
| Distinct input categories, reliable classification | Routing |
| Independent subtasks known ahead of time | Parallelization (sectioning) |
| Same task, want confidence or a tunable threshold | Parallelization (voting) |
| Subtasks only knowable at runtime | Orchestrator-workers |
| Clear criteria, iteration measurably helps | Evaluator-optimizer |
| None of the above; steps genuinely unknowable | You may need an agent — go back to the skill |

Note that the last two patterns already contain model-driven decisions. The line between a complex workflow and an agent is a gradient, not a wall. What matters is how much of the control flow lives in your code, and for all five of these, most of it does.
