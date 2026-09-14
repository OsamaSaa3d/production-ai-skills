# Maintaining a Capability Matrix

> **Verify before you build.** Parameter names, limits, and model support named below move between releases. Check the provider's current API reference before relying on them, and correct any drift with the smallest possible edit.

Most OpenAI-compatible providers return only `{id, created, owned_by}` from `GET /v1/models`. You cannot gate on that, so the matrix becomes yours to own. This is how to build one that stays true, because a stale matrix is worse than none — it gives you the confidence of a gate with none of the protection.

## What goes in it

Only what your code actually depends on. A matrix tracking twelve capabilities you never use is twelve columns that rot.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Capabilities:
    model_id: str
    provider: str

    # what your code sends
    tools: bool
    strict_tools: bool            # constrained decoding, not best-effort
    structured_outputs: bool
    parallel_tool_calls: bool

    # limits
    context_window: int
    max_output_tokens: int

    # economics
    price_in_per_m: float
    price_out_per_m: float
    reasoning_tokens_billed: bool

    # provenance — the part that keeps it honest
    verified_on: str              # ISO date
    verified_how: str             # "probe" | "docs" | "vendor claim"
    notes: str = ""
```

`strict_tools` separate from `tools` is the important split. "Supports tools" is nearly universal and nearly meaningless. "Enforces the schema during generation" is the thing your code relies on, and it is far from universal.

`verified_how` is what stops the matrix drifting into folklore. A row sourced from a vendor claim and a row sourced from a probe you ran are different kinds of fact, and six months later nobody remembers which was which.

## Probe rather than trust

Vendor docs describe intent. Probes describe behavior. Write them once and run them on a schedule.

```python
ADVERSARIAL_TOOL = {
    "type": "function",
    "function": {
        "name": "set_status",
        "description": "Set a record's status.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "record_id": {"type": "string"},
                "status": {"type": "string", "enum": ["open", "closed"]},
            },
            "required": ["record_id", "status"],
            "additionalProperties": False,
        },
    },
}

def probe_strict_tools(client, model) -> tuple[bool, str]:
    """Push the model off the enum. Strict mode makes that impossible."""
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user",
                       "content": "Set record ABC to status 'archived-pending-review'."}],
            tools=[ADVERSARIAL_TOOL],
            tool_choice="required",
        )
    except Exception as e:
        return False, f"rejected: {type(e).__name__}"

    calls = r.choices[0].message.tool_calls
    if not calls:
        return False, "no tool call under tool_choice=required"
    args = json.loads(calls[0].function.arguments)
    if args.get("status") not in ("open", "closed"):
        return False, f"enum violated: {args.get('status')!r}"
    return True, "enum held under pressure"
```

The prompt asks for a value outside the enum. Under genuine constrained decoding the model *cannot* produce it. A model that returns `"archived-pending-review"` has best-effort tool calling and the `strict` flag was decorative.

Two more probes worth having:

```python
def probe_structured_outputs(client, model):
    """Same idea, on the response rather than the arguments."""
    ...

def probe_tool_templating(client, model):
    """Does a tool call come back as a real tool_calls entry, or as text
    the gateway parsed? Check the response shape, not just the content."""
    ...
```

The third is the YAML-template detector: a router that renders tools into the prompt for a model without native support produces something tool-shaped with none of the guarantees. Check that `tool_calls` is populated and `message.content` is not carrying a parsed blob.

## Store it as data

```yaml
# models.yaml
- model_id: vendor/big-model
  provider: vendor
  tools: true
  strict_tools: true
  structured_outputs: true
  parallel_tool_calls: true
  context_window: 200000
  max_output_tokens: 64000
  price_in_per_m: 3.00
  price_out_per_m: 15.00
  reasoning_tokens_billed: false
  verified_on: "2026-09-01"
  verified_how: probe
  notes: "enum held under adversarial prompt"

- model_id: vendor/small-model
  provider: vendor
  tools: true
  strict_tools: false
  structured_outputs: false
  context_window: 32768
  max_output_tokens: 8192
  price_in_per_m: 0.20
  price_out_per_m: 0.60
  reasoning_tokens_billed: false
  verified_on: "2026-09-01"
  verified_how: probe
  notes: "accepts strict:true, ignores it — returned a value outside the enum"
```

YAML, in the repository, reviewed in PRs. Not a wiki page, not a spreadsheet, not someone's notes. It is a dependency of your routing code and it should live next to it and change with it.

That `small-model` note is the kind of entry that pays for the whole exercise.

## Gate against it

```python
REQUIRED = {"strict_tools", "structured_outputs"}

def usable(caps: Capabilities, min_context: int = 32_000) -> bool:
    return (all(getattr(caps, r) for r in REQUIRED)
            and caps.context_window >= min_context)

def select(matrix, avg_in, avg_out, min_context=32_000):
    usable_models = [c for c in matrix if usable(c, min_context)]
    return sorted(usable_models,
                  key=lambda c: (avg_in / 1e6) * c.price_in_per_m
                              + (avg_out / 1e6) * c.price_out_per_m)
```

Capability first, price second, always. A cheaper model that cannot do strict tool calling is not a cheaper option — it is a broken one.

## Keeping it from rotting

**Staleness check in CI.** A row nobody has verified in 90 days is a claim, not a fact:

```python
def test_matrix_is_fresh():
    stale = [c.model_id for c in MATRIX
             if (date.today() - date.fromisoformat(c.verified_on)).days > 90]
    assert not stale, f"unverified for 90+ days: {stale}"
```

**Probe on a schedule.** A nightly or weekly job that runs the probes against every model in the matrix and opens an issue on a mismatch. Providers change behavior without announcing it, and silent capability regressions are the exact failure this whole file exists to prevent.

**Gate the fallback chain in CI.**

```python
def test_fallback_chain_is_usable():
    for model_id in FALLBACK_CHAIN:
        assert usable(by_id(MATRIX, model_id)), f"{model_id} fails the capability gate"
```

A fallback to a model without strict tool support is the templating failure again, triggered by an outage rather than a config change — at the worst possible moment, with nothing in your logs saying so.

**One matrix, one place.** The moment there are two sources of truth, one of them is wrong and nobody knows which.

## Use a live endpoint where one exists

Don't hand-maintain what a provider will tell you. Anthropic's Models API returns `id`, `display_name`, `created_at`, and — since March 2026 — `max_input_tokens` (the context window), `max_tokens` (the output cap), and `capabilities`:

```python
model = client.models.retrieve(MODEL_ID)
model.max_input_tokens
model.capabilities
```

Note there is no `context_window` field; `max_input_tokens` is the one. Prefer live lookup for these; keep the hand-maintained matrix for what the API does not expose — your probe results, and anything about a provider that has no such endpoint.

## Probe cost

Each probe is one small request. Ten models, three probes, a few hundred tokens each: negligible, and far cheaper than one production incident caused by a model that accepted `strict: true` and ignored it.

Run probes against the specific serving endpoint you will use in production, not a default. One model ID can be served with different quantization and different parameter support depending on which endpoint you land on.
