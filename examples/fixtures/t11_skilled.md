Before splitting, confirm the failure. Decomposition buys per-call clarity at the cost of tool count, and tool count degrades selection accuracy on its own — applied preemptively it can trade one failure mode for a worse one.

Build a task set covering both polarities, phrased as a user would, and **assert the arguments, not just the tool name** — a name-only assertion reports 100% on an agent that picks the right tool and sets the flag backwards.

```python
expected_tools=[ToolCall(name="filter_records",
                         input_parameters={"field":"team","value":"platform","mode":"exclude"})]
metrics=[ToolCorrectnessMetric(threshold=1.0,
                               evaluation_params=[ToolCallParams.INPUT_PARAMETERS])]
```

If the eval confirms the flag is set wrong intermittently, then split — polarity is exactly the semantics worth spending a tool slot to eliminate, because a wrong value is structurally valid, raises no error, and returns confidently wrong results:

```python
{"name": "filter_records_including_value", "description": "Return only records where <field> equals <value>."},
{"name": "filter_records_excluding_value", "description": "Return all records except those where <field> equals <value>."},
```

If it does not reproduce on your model and phrasing, the second tool is pure cost.
