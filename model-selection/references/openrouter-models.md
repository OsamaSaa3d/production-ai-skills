# The `/models` Endpoint

> **Verify before you build.** Parameter names, limits, and model support named below move between releases. Check the provider's current API reference before relying on them, and correct any drift with the smallest possible edit.

Discovery and periodic review, never per-request selection. This file is the response shape, the filters worth writing, and the fields that decide whether a model is usable at all.

## The call

```python
import httpx

r = httpx.get("https://openrouter.ai/api/v1/models", timeout=30)
models = r.json()["data"]
```

Pagination is opt-in: `offset` and `limit` are optional, and omitting both returns the full list with `links.next` as null. Fetch the whole thing, cache it, work offline.

## The response shape

```python
{
    "id": "vendor/model-name",
    "name": "Vendor: Model Name",
    "description": "...",
    "context_length": 200000,
    "architecture": {
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
        "tokenizer": "...",
        "instruct_type": "...",
    },
    "pricing": {                       # USD PER TOKEN, as strings. "0" means free.
        "prompt": "0.000003",
        "completion": "0.000015",
        "request": "0",
        "image": "0",
    },
    "top_provider": {"context_length": 200000, "max_completion_tokens": 64000,
                     "is_moderated": True},
    "per_request_limits": None,
    "supported_parameters": ["tools", "tool_choice", "response_format",
                             "structured_outputs", "reasoning", "temperature", ...],
}
```

Three traps in that object:

**`pricing` values are strings, per token.** `float(p["prompt"]) * 1_000_000` for the per-million figure everyone quotes. Comparing the raw strings sorts lexicographically and will happily tell you `"0.00003"` is cheaper than `"0.000015"`.

**`context_length` at the top level is the model's; `top_provider.context_length` is what the serving endpoint offers.** They differ. Gate on the one you will actually get.

**`supported_parameters` is the only field that answers "will my code work."** Everything else is marketing.

## `supported_parameters` is the gate

It reports which OpenAI-compatible parameters actually work for that model — `tools`, `tool_choice`, `response_format`, `structured_outputs`, `reasoning`, and others.

```python
REQUIRED = {"tools", "structured_outputs"}     # whatever your code actually sends

def usable(m, min_context=32_000):
    params = set(m.get("supported_parameters") or [])
    if not REQUIRED <= params:
        return False
    ctx = (m.get("top_provider") or {}).get("context_length") or m.get("context_length") or 0
    return ctx >= min_context
```

### The failure this prevents

A router will pass `tools` through to providers implementing OpenAI's interface, map them for providers with custom interfaces, and **otherwise transform the tools into a YAML template in the prompt** — the model then responds with an assistant message that has to be parsed back out.

That last path is prompt-engineered tool calling wearing the API's clothes. Your request succeeds. You get something tool-shaped back. And you have silently lost every guarantee `llm-tool-calling` is built on: no constrained decoding, no schema enforcement, no protection against invented tool names or malformed arguments.

**Nothing in the response says "by the way, this was a YAML template."** The only defense is gating on `supported_parameters` before you send.

The same reasoning applies to structured output: a model without `structured_outputs` or `response_format` cannot give you the conformance guarantee, whatever you put in the payload.

## Filters worth writing

```python
def per_million(m):
    p = m["pricing"]
    return {"in": float(p["prompt"]) * 1e6, "out": float(p["completion"]) * 1e6}

def cost_per_task(m, avg_in, avg_out):
    pm = per_million(m)
    return (avg_in / 1e6) * pm["in"] + (avg_out / 1e6) * pm["out"]

def shortlist(models, avg_in=4_000, avg_out=800, **gate):
    candidates = [m for m in models if usable(m, **gate)]
    return sorted(candidates, key=lambda m: cost_per_task(m, avg_in, avg_out))
```

Additional gates worth having as separate predicates, so a rejection says *why*:

```python
def supports_vision(m):
    return "image" in (m.get("architecture") or {}).get("input_modalities", [])

def is_free(m):
    return float(m["pricing"]["prompt"]) == 0 and float(m["pricing"]["completion"]) == 0

def long_enough_output(m, need=16_000):
    return ((m.get("top_provider") or {}).get("max_completion_tokens") or 0) >= need
```

`max_completion_tokens` is the one people forget until an extraction task truncates in production. If your outputs are long, gate on it.

## Per-endpoint detail

One model ID can be served by several endpoints with different quantization, context limits, supported parameters, and prices. The aggregate row hides that.

Where the provider exposes per-endpoint detail, check it before assuming a model ID behaves identically everywhere — a quantized endpoint at half the price is a different model for your purposes, and it is not always the one you will be routed to.

This matters most when: you depend on `structured_outputs`, your context requirement is near the limit, or reproducibility matters. It matters least for high-volume classification where a quality dip is measurable and tolerable.

## Providers with a bare endpoint

Most OpenAI-compatible providers expose `GET /v1/models` returning only:

```json
{"id": "...", "created": 1700000000, "owned_by": "..."}
```

No pricing, no capabilities, no context length. You cannot gate on that, so you maintain the capability matrix yourself — see `capability-matrix.md`.

Anthropic's Models API sits in between: `GET /v1/models` and `GET /v1/models/{id}` return `id`, `display_name`, `created_at`, and — since March 2026 — `max_input_tokens` (the context window), `max_tokens` (the output cap), and `capabilities`. Note there is no `context_window` field; `max_input_tokens` is the one you want.

```python
model = client.models.retrieve(MODEL_ID)
model.max_input_tokens      # context window
model.max_tokens            # output cap
model.capabilities          # feature support
```

Use it for live capability lookup rather than a hardcoded table that goes stale.

## The review cadence

Discovery, not dispatch.

```python
def monthly_review(current_pin, eval_suite):
    models = fetch_models()
    ranked = shortlist(models, avg_in=MEASURED_IN, avg_out=MEASURED_OUT)
    current_cost = cost_per_task(by_id(models, current_pin), MEASURED_IN, MEASURED_OUT)

    for m in ranked:
        if cost_per_task(m, MEASURED_IN, MEASURED_OUT) >= current_cost:
            break                                   # nothing cheaper left
        if eval_suite(m["id"]).pass_rate >= TARGET:
            return m["id"]                          # switch only on a pass
    return current_pin
```

Monthly is a reasonable cadence: re-pull, re-gate, re-rank by cost per task, re-run the eval suite against anything now cheaper than your pin. Switch only if it passes.

**Never route to "whatever is cheapest right now."** The cheapest model changes without warning, and you will be running an unevaluated model in production the moment it does.

## Automatic routers and fallback chains

If you use a provider's automatic router or a fallback chain, **know which models it can reach and confirm every one clears your capability gate.** A fallback to a model without `tools` support is the YAML-template failure again, triggered by an outage rather than a config error — and it will happen at the worst time, with no signal in your logs.

```python
FALLBACK_CHAIN = ["primary-model", "secondary-model"]
assert all(usable(by_id(models, m)) for m in FALLBACK_CHAIN), \
    "a fallback target does not meet the capability gate"
```

Put that assertion in CI. It is two lines and it catches a class of incident that is otherwise invisible until it fires.

Anthropic's own server-side fallbacks are a different mechanism worth knowing: `betas: ["server-side-fallback-2026-07-01"]` with `fallbacks: "default"` routes by refusal category without you maintaining a model list at all.

## Caching the catalog

```python
@lru_cache(maxsize=1)
def catalog(date_key: str) -> list[dict]:
    return httpx.get(MODELS_URL, timeout=30).json()["data"]

models = catalog(date.today().isoformat())      # one fetch per day
```

Never call `/models` in a request path. It is a discovery endpoint, it adds latency and a failure mode to every request, and the answer does not change between two requests a second apart.
