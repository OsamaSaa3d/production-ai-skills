# Cache-Safe Prompt Assembly

## The mechanic

Prompt caching is a **prefix match on exact bytes**. The cache key is derived from the rendered prompt up to each breakpoint. One changed byte at position N invalidates every breakpoint at or after N.

On the Claude API the render order is:

```text
tools  →  system  →  messages
```

A breakpoint on the last `system` block therefore caches **tools + system together**. This is why a new tool appearing in the list invalidates the system prompt cache too.

## Order by volatility, not by topic

```text
[ tool definitions            ]  changes on deploy
[ static system prompt        ]  changes on deploy
[ long stable reference doc   ]  changes rarely
--- breakpoint here ---
[ per-request context         ]  changes every request
[ conversation history        ]  grows every turn
[ current user message        ]  always new
```

Everything above the breakpoint must be byte-identical across the requests you want to share a cache.

## The single most common mistake

```python
# BAD — every request writes a new cache entry and reads none
system = (
    f"You are a support agent for Acme.\n"
    f"Current date: {today}\n"
    f"Customer tier: {tier}\n"
    f"Session ID: {session_id}\n"
    + POLICY_DOCUMENT
)
```

The interpolated values sit at the front of the prefix, so nothing downstream — including the long policy document — can ever hit.

```python
# GOOD
system = [
    {
        "type": "text",
        "text": STATIC_SYSTEM_PROMPT + "\n\n" + POLICY_DOCUMENT,
        "cache_control": {"type": "ephemeral"},
    },
]

messages = [
    {
        "role": "user",
        "content": (
            "<request_context>\n"
            f"date: {today}\n"
            f"customer_tier: {tier}\n"
            "</request_context>\n\n"
            f"{user_message}"
        ),
    },
]
```

A message at turn 5 invalidates nothing before turn 5. That is the whole trick.

Where the provider supports mid-conversation system-role messages, dynamic policy can go there instead of in a user message. Either way it lives after the breakpoint.

## Breakpoint placement

**Put the breakpoint on the last block that stays identical across requests** — the end of the static prefix, not the end of the request.

A breakpoint placed after per-request content never hits, and you have paid the write premium on the stable part for nothing. This is the mirror of the interpolation mistake and it comes from the same instinct: "more coverage is better." It isn't.

For agent loops, the robust combination is:

- One **explicit** breakpoint at the end of the static system prefix. This gives the expensive shared part a guaranteed read point that survives whatever happens later in `messages`.
- Plus **automatic** top-level caching for the growing conversation tail, where available. The system moves that breakpoint forward as the conversation grows.

Constraints worth knowing before you combine them: there are up to 4 explicit breakpoints per request, automatic caching consumes one slot, and an explicit marker on the last block with a TTL differing from the top-level field's is a 400.

## Numbers

Current at time of writing on the Claude API. Verify — these change.

| Property | Value |
|---|---|
| Cache write | 1.25x base input price (5-min TTL) |
| Cache read | 0.1x base input price |
| Default TTL | 5 minutes, refreshed on each hit |
| Extended TTL | 1 hour, at 2x base input price |
| Minimum cacheable length | ~1,024 tokens Sonnet-class; ~4,096 Opus and Haiku 4.5 |
| Explicit breakpoints | 4 per request |

Below the minimum, `cache_control` is **silently ignored**. Measure your system prompt in tokens, not characters, and leave headroom.

If your agent loop has slow steps, check the TTL against the actual interval between requests before assuming the 5-minute default is fine. Some providers expose longer retention explicitly — OpenAI's `prompt_cache_retention` supports keeping prompts cached for up to 24 hours, which matters for coding sessions and help-desk threads that return to the same long context later in the day.

## Silent-miss checklist

Cache misses do not raise. Audit for these:

- **A timestamp, session ID, or random ID anywhere in the prefix.**
- **Non-deterministic JSON serialization.** Reordered dict keys change the bytes. Sort keys, or freeze the rendered string.
- **A tool list built by iterating a set**, or conditionally including tools per request. Tools render first; any change invalidates system too.
- **Trailing whitespace differences** from a template engine.
- **A prompt assembled with `.format()` on a blob**, where an argument that "never changes" occasionally does. Typed parameters make this reviewable.
- **Context editing.** Tool-result clearing invalidates the prefix at the point of the clear. That is expected — use `clear_at_least` so each clear removes enough tokens to be worth the re-write.
- **A different model.** Caches are per-model.

## Instrument it from day one

```python
resp = client.messages.create(...)
u = resp.usage
log.info(
    "cache",
    read=u.cache_read_input_tokens,
    write=u.cache_creation_input_tokens,
    uncached=u.input_tokens,
    hit_rate=u.cache_read_input_tokens / max(1, u.cache_read_input_tokens + u.input_tokens),
)
```

Alert on the hit rate, not the cost. A hit rate that quietly drops to zero after a serialization change is otherwise invisible until the invoice arrives a month later.

Add a test that asserts the rendered prefix is byte-identical across two calls with different request context. It catches the whole class in CI:

```python
def test_prefix_is_stable():
    a = render_prefix(user="alice", now=datetime(2026, 1, 1))
    b = render_prefix(user="bob", now=datetime(2026, 6, 1))
    assert a == b, "dynamic content leaked into the cacheable prefix"
```
