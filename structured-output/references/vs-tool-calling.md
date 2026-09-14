# Structured Output vs Tool Calling: The Same Task, Both Ways

> **Verify before you build.** Parameter names, limits, and model support named below move between releases. Check the provider's current API reference before relying on them, and correct any drift with the smallest possible edit.

Both put a JSON Schema in the request and constrain generation against it. The mechanism is nearly identical. What differs is **where the data comes back and what it means** — and that determines which one your code should use.

| | Tool calling | Structured output |
|---|---|---|
| The schema describes | arguments to *your* function | the model's answer to *you* |
| Result arrives in | `tool_calls` / `tool_use` blocks | the message content |
| Implies | an action should be taken | a response has been produced |
| Model may emit | zero, one, or many calls | exactly one object |
| Natural follow-up | execute, return a result, call again | none — you're done |

The provider guidance across vendors is the same one line: **tool calling connects the model to your systems; structured output shapes how it responds.**

## Worked example 1: extraction — structured output

The task: pull fields out of an invoice. No action is taken. The object *is* the answer.

```python
# RIGHT
class Invoice(BaseModel):
    invoice_number: str
    total_amount: float
    customer_name: str

completion = client.chat.completions.parse(
    model=MODEL,
    messages=[{"role": "system", "content": "Extract invoice fields."},
              {"role": "user", "content": invoice_text}],
    response_format=Invoice,
)
invoice = completion.choices[0].message.parsed
```

The same thing done with a forced tool call:

```python
# WRONG — a workaround from before structured output existed
tools = [{"type": "function", "function": {"name": "record_invoice", "strict": True,
                                           "parameters": Invoice.model_json_schema()}}]
completion = client.chat.completions.create(
    model=MODEL, messages=[...], tools=tools,
    tool_choice={"type": "function", "name": "record_invoice"},
)
invoice = Invoice(**json.loads(
    completion.choices[0].message.tool_calls[0].function.arguments))
```

What the second version costs you: a tool named for a function that does not exist, an extra unwrapping step, a `tool_calls[0]` index that assumes exactly one call, and a message the model believes is a request to *act*. The forced call also prefills the assistant turn, which suppresses the natural-language preamble — irrelevant here, but a surprise the first time you reuse the pattern conversationally.

**The tell:** `tool_choice` forcing a single tool that has no implementation behind it. That is always structured output wearing a costume.

## Worked example 2: taking an action — tool calling

The task: a support assistant that can issue refunds. The model decides *whether* to act.

```python
# RIGHT
tools = [{
    "type": "function",
    "function": {
        "name": "issue_refund",
        "description": "Issue a refund for an order. Only call after confirming "
                       "the order exists and the customer is entitled to one.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "amount_usd": {"type": "number"},
                "reason": {"type": "string", "enum": ["damaged", "not_received", "duplicate"]},
            },
            "required": ["order_id", "amount_usd", "reason"],
            "additionalProperties": False,
        },
    },
}]

response = client.chat.completions.create(
    model=MODEL, messages=messages, tools=tools, tool_choice="auto",
)
```

`tool_choice="auto"` is the point: on "where is my order?" the model answers in prose and calls nothing. Structured output cannot express "no action needed" — it would have to return a refund object with null fields, and your code would have to infer intent from nulls. That is a worse contract than the one the API already gives you.

## Worked example 3: both, in one request

The legitimate combination. The agent acts *and* returns a typed result to your application.

```python
class TriageResult(BaseModel):
    resolution: Literal["refunded", "escalated", "answered"]
    summary: str
    follow_up_required: bool

response = client.messages.create(
    model=MODEL,
    max_tokens=4096,
    tools=[issue_refund_tool, lookup_order_tool],          # strict: True on each
    output_config={"format": {"type": "json_schema", "schema": TriageResult.model_json_schema()}},
    messages=messages,
)
```

Strict tools guarantee the arguments your refund function receives. The output config guarantees the shape of the final answer your ticketing system consumes. They constrain different things and do not compete. Anthropic documents this combination explicitly; check your provider before relying on it elsewhere.

## The decision, as a question

Ask: **after the model produces this, does my code call a function with it, or store/return it?**

- Calls a function → tool calling.
- Stores or returns it → structured output.
- Both, in sequence → tool calling for the action, structured output for the final answer.

Two refinements that catch the remaining cases:

**Is "do nothing" a valid outcome?** If yes, you need tool calling — `tool_choice: "auto"` expresses it natively. Structured output always produces an object.

**Could there be more than one of these?** Tool calling handles zero-to-many naturally through parallel calls. Structured output gives you exactly one object, and "many" has to be modeled as a list field inside it — which is fine for extraction and wrong for actions, because a list of intended actions still has to be executed by you.

## Migrating a forced-tool-call pattern

Mechanical, and usually a net deletion:

```python
# before
tools = [{"type": "function", "function": {"name": "extract", "strict": True,
                                           "parameters": SCHEMA}}]
tool_choice = {"type": "function", "name": "extract"}
data = json.loads(resp.choices[0].message.tool_calls[0].function.arguments)

# after
response_format = MyModel                       # the Pydantic model itself
data = resp.choices[0].message.parsed           # already typed
```

Three things change beyond the syntax:

- **The failure signals move.** Refusal was `message.refusal` in both, but truncation now needs `finish_reason == "length"` checked against a parse that returns `None` rather than a malformed `arguments` string. See `failure-handling.md`.
- **The dead tool function goes away**, along with whatever stub was registered for it.
- **The `tool_calls[0]` assumption goes away.** That index was a latent bug the moment parallel calls were enabled.

Re-run the eval suite after migrating. The behavior is usually identical or slightly better — the model is no longer being told it is invoking something — but "usually" is why you have the suite.
