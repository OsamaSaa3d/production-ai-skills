"""The 16 task prompts.

Rules these obey, from tool-design/references/eval-loop.md:
  - phrased the way a user would phrase it
  - never name the technique, the tool, or the skill
  - four are CONTROLs where the correct behaviour is NOT to apply the skill

`skill` is the SKILL.md injected into Arm B's system prompt. Arm A gets none.
"""

TASKS = [
    # ---------------- llm-tool-calling ----------------
    dict(id="t01", skill="llm-tool-calling", kind="positive",
         prompt="We have a Postgres table of customer orders (id, customer_email, "
                "status, total_usd, placed_at). I want users to ask questions about "
                "it in plain English and get answers. Write the Python for this."),
    dict(id="t02", skill="llm-tool-calling", kind="positive",
         prompt="Our support bot needs to look up an order and issue a refund for it. "
                "Write the loop that lets the model do that over several turns."),
    dict(id="t03", skill="llm-tool-calling", kind="positive",
         prompt="Let the model call our two existing Python functions, "
                "get_inventory(sku) and reserve_stock(sku, qty). Write the integration."),
    dict(id="t04", skill="llm-tool-calling", kind="control",
         prompt="We use LangGraph across our pipeline because we need its durable "
                "checkpointing between steps. Add a step that lets the model query "
                "our orders table.",
         control_note="LangGraph is load-bearing and the user said why. "
                      "Ripping it out is the wrong answer."),

    # ---------------- structured-output ----------------
    dict(id="t05", skill="structured-output", kind="positive",
         prompt="We get invoices as plain text. I need invoice number, issue date, "
                "total, customer name, and PO number pulled out and written to our "
                "orders table. Write it."),
    dict(id="t06", skill="structured-output", kind="positive",
         prompt="Classify incoming support emails by urgency so we can route them. "
                "Write the Python."),
    dict(id="t07", skill="structured-output", kind="positive",
         prompt="Pull the party names and the termination clause out of these "
                "contracts. Legal will be auditing the results."),
    dict(id="t08", skill="structured-output", kind="control",
         prompt="Write a function that summarises a meeting transcript into a short "
                "paragraph a manager can skim.",
         control_note="The output genuinely is prose. Forcing a schema onto it is "
                      "the skill's own documented anti-pattern."),

    # ---------------- tool-design ----------------
    dict(id="t09", skill="tool-design", kind="trap",
         prompt="Our ticket system has a search endpoint that takes queries like "
                "`status:open AND team:platform AND created:>2026-01-01`. Let our "
                "agent search tickets with it.",
         trap_note="The tempting answer is describing the grammar in the prompt and "
                   "parsing what the model emits."),
    dict(id="t10", skill="tool-design", kind="positive",
         prompt="We have a REST API with 14 endpoints for our CRM. Expose it to our "
                "agent."),
    dict(id="t11", skill="tool-design", kind="positive",
         prompt="Our agent calls filter_records(field, value, mode) and keeps getting "
                "`mode` backwards — it excludes when it should include. Fix it."),
    dict(id="t12", skill="tool-design", kind="control",
         prompt="Add one tool so the agent can fetch a user by id. That's all it "
                "needs to do.",
         control_note="A trivial tool. Deferred loading, examples and decomposition "
                      "are all cost with no benefit here."),

    # ---------------- agent-vs-workflow-decision ----------------
    dict(id="t13", skill="agent-vs-workflow-decision", kind="trap",
         prompt="Build an agent that reads our daily sales CSV and emails the team a "
                "summary every morning.",
         trap_note="A scheduled script plus one LLM call. No loop is warranted."),
    dict(id="t14", skill="agent-vs-workflow-decision", kind="trap",
         prompt="Build an agent that triages incoming bug reports: read the report, "
                "check whether it duplicates an existing issue, put a severity label "
                "on it, and route it to the right team.",
         trap_note="Every step is known in advance. That is a workflow."),
    dict(id="t15", skill="agent-vs-workflow-decision", kind="positive",
         prompt="I want to research our competitors — their pricing, their funding "
                "history, and their headcount — and get one written brief out of it.",
         positive_note="Genuinely independent directions. Parallel decomposition is "
                       "defensible here."),
    dict(id="t16", skill="agent-vs-workflow-decision", kind="positive",
         prompt="Build something that can take a failing test in our repo and get it "
                "passing.",
         positive_note="Verifiable output, unknowable number of steps. A real agent."),
]

BY_ID = {t["id"]: t for t in TASKS}

if __name__ == "__main__":
    from collections import Counter
    print(f"{len(TASKS)} tasks")
    for k, v in sorted(Counter(t["kind"] for t in TASKS).items()):
        print(f"  {k:<9} {v}")
    for k, v in sorted(Counter(t["skill"] for t in TASKS).items()):
        print(f"  {k:<28} {v}")
