"""Per-task rubrics. PRE-REGISTERED: committed before any generation exists.

Each entry is (check_fn_name, cites) where `cites` names the line of the skill
the check is testing. A check that cannot cite a skill line does not belong here
— that is the rule that stops the grader being written to flatter the result.
"""
from __future__ import annotations
import re
import checks

R = lambda *rows: list(rows)

RUBRICS: dict[str, list[tuple[str, str]]] = {

"t01": R(
 ("uses_native_tool_calling", "llm-tool-calling: pass tool definitions in the API request payload"),
 ("strict_mode_on",           "llm-tool-calling: Set strict: true explicitly"),
 ("additional_properties_false","llm-tool-calling: Every object needs additionalProperties: false"),
 ("no_framework",             "llm-tool-calling: Don't do this — framework agent abstractions"),
 ("tool_result_role",         "llm-tool-calling: result goes in a message with role tool"),
 ("tool_errors_as_data",      "llm-tool-calling: return errors as data — the model can recover"),
 ("sql_is_safe",              "tool-design: a model emitting executable query text is an injection surface"),
),
"t02": R(
 ("uses_native_tool_calling", "llm-tool-calling: native tool calling"),
 ("strict_mode_on",           "llm-tool-calling: Set strict: true explicitly"),
 ("tool_result_role",         "llm-tool-calling: role tool, tool_call_id matching"),
 ("tool_errors_as_data",      "llm-tool-calling: Letting tool execution errors raise"),
 ("has_stopping_condition",   "llm-tool-calling/agent-loop: an iteration cap is the minimum"),
 ("no_framework",             "llm-tool-calling: write the call directly"),
),
"t03": R(
 ("uses_native_tool_calling", "llm-tool-calling: native tool calling"),
 ("strict_mode_on",           "llm-tool-calling: Set strict: true explicitly"),
 ("additional_properties_false","llm-tool-calling: strict-mode requirements"),
 ("no_framework",             "llm-tool-calling: reach for native before framework"),
 ("tool_result_role",         "llm-tool-calling: send tool results back"),
),
"t04": R(  # CONTROL
 ("keeps_framework",          "llm-tool-calling: a framework already load-bearing — don't remove it"),
 ("strict_mode_on",           "llm-tool-calling: strict applies regardless of harness"),
),

"t05": R(
 ("nullable_optional_fields", "structured-output: a field is nullable if a real document might not contain it"),
 ("handles_refusal_or_truncation","structured-output: the two failure modes you must handle"),
 ("additional_properties_false","structured-output: additionalProperties false on every object"),
 ("no_framework",             "structured-output: don't use Instructor / output parsers"),
),
"t06": R(
 ("enum_for_bounded_fields",  "structured-output: enum is the one value constraint genuinely enforced"),
 ("reasoning_before_label",   "structured-output: put reasoning before the label"),
 ("handles_refusal_or_truncation","structured-output: check before parsing"),
 ("no_framework",             "structured-output: no output-parser abstractions"),
),
"t07": R(
 ("nullable_optional_fields", "structured-output: no 'not found' path forces invention"),
 ("handles_refusal_or_truncation","structured-output: refusal and truncation"),
 ("notes_cost_or_tradeoff",   "structured-output/extraction: provenance costs tokens, say so"),
),
"t08": R(  # CONTROL
 ("no_forced_schema_on_prose","structured-output: the output genuinely is prose — don't force a schema"),
),

"t09": R(  # TRAP
 ("typed_fields_not_grammar", "tool-design: never make the agent write a query language"),
 ("enum_for_bounded_fields",  "tool-design: invalid states stop being representable"),
 ("query_built_in_code",      "tool-design: your code owns the grammar"),
 ("uses_native_tool_calling", "tool-design: a tool schema is validated at generation time"),
),
"t10": R(
 ("consolidates_tools",       "tool-design: build tools for tasks, not for API endpoints"),
 ("uses_native_tool_calling", "tool-design: tool definitions in the payload"),
),
"t11": R(
 ("measures_before_decomposing","tool-design: Do not apply this by default — measure first"),
 ("notes_cost_or_tradeoff",   "tool-design: decomposition buys clarity at the cost of tool count"),
),
"t12": R(  # CONTROL
 ("minimal_for_trivial_tool", "tool-design: Skip when fewer than 10 tools; these are remedies not defaults"),
 ("uses_native_tool_calling", "tool-design: still a real tool definition"),
),

"t13": R(  # TRAP
 ("recommends_workflow_not_agent","agent-vs-workflow: can you write down the steps? then it's a workflow"),
 ("model_driven_loop",        "agent-vs-workflow: agent loops over fixed procedures (INVERTED — should be False)"),
),
"t14": R(  # TRAP
 ("recommends_workflow_not_agent","agent-vs-workflow: if the steps are known, your code should contain them"),
 ("model_driven_loop",        "agent-vs-workflow: INVERTED — should be False"),
),
"t15": R(
 ("notes_cost_or_tradeoff",   "agent-vs-workflow: multi-agent runs ~15x a chat interaction"),
 ("has_stopping_condition",   "agent-vs-workflow: include stopping conditions"),
),
"t16": R(
 ("model_driven_loop",        "agent-vs-workflow: steps genuinely unknowable — an agent is right"),
 ("has_stopping_condition",   "agent-vs-workflow: no stopping condition is a pitfall"),
 ("notes_cost_or_tradeoff",   "agent-vs-workflow: can you afford it"),
),
}

# Checks whose PASSING value is False for that task.
INVERTED = {("t13", "model_driven_loop"), ("t14", "model_driven_loop")}


# Sessions often echo their own working directory, e.g. /tmp/skills-eval/arm-b/t11-r2.
# Left in, it names the arm (breaking blind grading) and its "eval" satisfied
# measures_before_decomposing on answers that never mentioned measuring.
RUN_PATH = re.compile(r"[^\s`'\"()]*skills-eval[\\/]+(?:arm-[ab]|_records)[\\/]*[^\s`'\"()]*", re.I)


def redact(answer: str) -> str:
    return RUN_PATH.sub("<run-dir>", answer)


def grade(task_id: str, answer: str) -> dict:
    answer = redact(answer)
    rows = {}
    for fn_name, cite in RUBRICS[task_id]:
        raw = getattr(checks, fn_name)(answer)
        if raw is None:
            rows[fn_name] = dict(result=None, passed=None, cites=cite)
            continue
        passed = (not raw) if (task_id, fn_name) in INVERTED else bool(raw)
        rows[fn_name] = dict(result=bool(raw), passed=passed, cites=cite)
    scored = [r["passed"] for r in rows.values() if r["passed"] is not None]
    return dict(task=task_id, checks=rows,
                score=sum(scored) / len(scored) if scored else None,
                n_checks=len(scored))
