# Cost Per Successful Task

Per-token price is the number vendors publish and the wrong number to compare on. This file is the arithmetic that replaces it.

For estimating cost by *architecture* before you build, see `agent-vs-workflow-decision/references/cost-modeling.md`. This one is per-model accounting once a system exists.

## Why per-token price misleads

**Tokenizers differ.** The same text is a different number of tokens across models, and you are billed on the model's own tokenizer. Two models at identical per-token prices can differ materially on the same input — and re-baselining is required whenever you change model families, not just providers. Use the provider's own token counter (Anthropic's `messages.count_tokens`, for instance), never a third-party tokenizer library that guesses.

**Reasoning models emit invisible tokens.** A model that thinks before answering bills those tokens and they do not appear in the answer. A "cheaper" reasoning model can cost more per task than a pricier non-reasoning one.

**Retries and failures are part of the cost.** A cheap model that fails your eval 30% of the time and gets retried is not cheap.

**Cached reads are priced differently.** On a system with a stable prefix, most input tokens may bill at a fraction of the headline rate. Ignoring that overstates cost for cache-friendly designs and hides the savings from stabilizing a prefix.

## The formula

```python
@dataclass
class TokenProfile:
    input_tokens: float          # measured mean per task
    cached_read_tokens: float    # portion of input served from cache
    output_tokens: float         # visible output
    reasoning_tokens: float      # billed, invisible
    pass_rate: float             # from the eval suite
    retries_per_failure: float = 1.0

def cost_per_task(price, p: TokenProfile) -> float:
    fresh_in = max(0.0, p.input_tokens - p.cached_read_tokens)
    raw = (fresh_in / 1e6) * price.in_per_m \
        + (p.cached_read_tokens / 1e6) * price.cache_read_per_m \
        + ((p.output_tokens + p.reasoning_tokens) / 1e6) * price.out_per_m
    attempts = 1 + (1 - p.pass_rate) * p.retries_per_failure
    return raw * attempts

def cost_per_successful_task(price, p: TokenProfile) -> float:
    return cost_per_task(price, p) / p.pass_rate
```

**`cost_per_successful_task` is the number that decides.** It is the only one that makes a cheap-but-unreliable model comparable to an expensive-but-reliable one.

## A worked comparison

Same task, same eval suite, measured numbers:

| | Model A (large) | Model B (mid) | Model C (small) |
|---|---|---|---|
| Price in / out per M | $5.00 / $25.00 | $2.00 / $10.00 | $1.00 / $5.00 |
| Input tokens / task | 4,000 | 4,000 | 4,400 |
| Cached read | 3,000 | 3,000 | 3,000 |
| Output tokens | 600 | 700 | 900 |
| Reasoning tokens | 0 | 1,400 | 0 |
| Pass rate | 0.96 | 0.91 | 0.88 |
| **Raw cost / task** | $0.0200 | $0.0250 | $0.0087 |
| **Cost / successful task** | $0.0208 | $0.0275 | $0.0099 |

Two things fall out that per-token price would not have told you:

**Model B is more expensive than Model A** despite costing 60% less per token, because 1,400 reasoning tokens bill at the output rate and its pass rate is lower. This is the single most common surprise in model comparison.

**Model C is half the cost of A and 8 points worse.** Whether that is a good trade is a question about your accuracy target, not about the models. If your break-even is 85%, C clears it and you take the saving. If it is 95%, C is disqualified and the comparison was between A and B.

## Where the numbers come from

Not estimates. Your eval harness already tracks them if you followed `evals-before-shipping`.

```python
def profile_from_runs(runs) -> TokenProfile:
    n = len(runs)
    return TokenProfile(
        input_tokens=sum(r.usage.input_tokens for r in runs) / n,
        cached_read_tokens=sum(getattr(r.usage, "cache_read_input_tokens", 0)
                               for r in runs) / n,
        output_tokens=sum(r.usage.output_tokens for r in runs) / n,
        reasoning_tokens=sum(getattr(r.usage, "reasoning_tokens", 0) for r in runs) / n,
        pass_rate=sum(r.passed for r in runs) / n,
    )
```

Read `usage` from the response. Do not count characters, do not estimate from word counts, and do not reuse a profile measured on a different model — token counts move with the tokenizer.

**Profile per request class, not globally.** A system whose classification requests are 400 tokens and whose summarization requests are 40,000 has a meaningless average, and routing decisions made on it will be wrong in both directions.

## Model the tail

Averages hide the runs that hit the iteration cap or retried three times.

```python
def percentile_cost(runs, price, q=0.95):
    costs = sorted(cost_of(r, price) for r in runs)
    return costs[int(len(costs) * q)]
```

If 5% of runs cost 4x the mean, that is 20% of your bill and it will not appear in an average-based projection. Budget from the mean; alert on the p95.

## Free wins before trade-offs

Every lever here preserves quality. Exhaust them before paying a tier difference or accepting an accuracy drop.

| Lever | Typical effect |
|---|---|
| **Stabilize the prefix and cache it** | Large. Tools → system → messages; volatile content last. |
| **Shrink tool results** | Large in agent loops — results are re-billed every iteration |
| **Defer tool definitions** | ~72K tokens of definitions → ~8.7K total context, with accuracy improving |
| **Batch the non-latency-sensitive work** | Roughly half price on batch APIs |
| **Trim the system prompt** | Small per request, charged forever |
| **Lower `effort` where quality holds** | Fewer reasoning tokens; measure per route |

Verify caching actually works: if `cache_read_input_tokens` is zero across repeated requests, a silent invalidator is at work — a timestamp in the system prompt, an unsorted JSON dump, a tool list that reorders between processes.

**Measure the simpler alternative before building a cascade.** The most capable model at lower effort often matches or beats a cheaper model at high effort, and it keeps one cache namespace. Caches are model-scoped, so a two-model cascade forfeits cache reuse across its models — a real cost that cascade proposals rarely account for.

## Then the trade-offs

1. **Route by request class.** Easy inputs to the small model. See `routing.md`.
2. **Descend the ladder** on the class that dominates your bill. See `escalation-ladder.md`.
3. **Fix the interface before escalating** when a small model fails — sharpen descriptions, add examples, decompose the confusing tool. Escalating first buys a permanent per-request cost to hide an ambiguity you could have removed once.

## Two places routing pays especially well

**Subagents.** They inherit the parent's model by default, so a triage subagent left on the default costs the same per token as the orchestrator. Set `model` explicitly per subagent — bounded, format-specified work is exactly what small models handle well.

**LLM judges in evals.** Judge quality matters, but judging a binary assertion does not need your most expensive model. Calibrate a cheaper judge against human labels once, then keep it. On a suite that runs on every PR, this is a recurring saving.

## What to log

```python
{"request_id": ..., "request_class": "classify", "model": "...",
 "input_tokens": 4_012, "cache_read_input_tokens": 3_001,
 "output_tokens": 611, "reasoning_tokens": 0,
 "cost_usd": 0.0203, "passed": True, "attempt": 1, "latency_ms": 840}
```

With `request_class` and `attempt` in there, every question this file answers becomes a query: cost per class, cache hit rate by class, retry overhead, and the p95 tail. Without them you are re-deriving the profile by hand every time someone asks about the bill.

## Pitfalls

**Comparing per-token prices across tokenizers.** Compare cost per task on your actual traffic.

**Ignoring reasoning tokens.** They bill and do not appear in the answer.

**Not counting retries.** Cost per *successful* task.

**A global token profile.** Profile per request class.

**Assuming cache hits.** Verify with the provider's cache field before modeling the discount.

**Optimizing the wrong thing.** Find the class that dominates the bill before optimizing anything. The most-discussed request class is rarely the most expensive one.
