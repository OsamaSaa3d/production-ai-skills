"""Deterministic checks over a generated answer.

Each check returns True/False/None (None = not applicable / undetermined).
Everything here is mechanical: AST over fenced python, or regex over prose.
No judge, no API call, no opinion.
"""
from __future__ import annotations
import ast, re
from dataclasses import dataclass

# A fence is 3+ backticks and closes only on a run of the same length (CommonMark).
# The old pattern paired fences positionally: in an answer that also contained
# ```` md or ```` json blocks, a closing fence was read as an opening one, so real
# code fell outside every "python" block and schemas the session wrote were
# invisible to the AST checks.
FENCE = re.compile(r"^(`{3,})(?:python|py)?[ \t]*\n(.*?)^\1[ \t]*$", re.S | re.M)


def _blocks(answer: str) -> list[str]:
    return [body for _, body in FENCE.findall(answer)]

FRAMEWORKS = re.compile(
    r"\b(?:from|import)\s+(langchain\w*|langgraph|llama_index|llamaindex|instructor|crewai|autogen)\b"
    r"|\bAgentExecutor\b|\binitialize_agent\b|\bcreate_react_agent\b", re.I)


def code(answer: str) -> str:
    """All fenced python in the answer, concatenated."""
    return "\n\n".join(_blocks(answer))


def trees(answer: str) -> list[ast.AST]:
    out = []
    for block in _blocks(answer):
        try:
            out.append(ast.parse(block))
        except SyntaxError:
            continue
    return out


def _dict_keys(answer: str) -> set[str]:
    keys = set()
    for t in trees(answer):
        for n in ast.walk(t):
            if isinstance(n, ast.Dict):
                for k in n.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        keys.add(k.value)
    return keys


def _kwargs(answer: str) -> set[str]:
    names = set()
    for t in trees(answer):
        for n in ast.walk(t):
            if isinstance(n, ast.Call):
                names.update(kw.arg for kw in n.keywords if kw.arg)
    return names


def _const_true_for(answer: str, key: str) -> bool:
    """Is <key> set to True anywhere, as a dict entry or a kwarg?"""
    for t in trees(answer):
        for n in ast.walk(t):
            if isinstance(n, ast.Dict):
                for k, v in zip(n.keys, n.values):
                    if (isinstance(k, ast.Constant) and k.value == key
                            and isinstance(v, ast.Constant) and v.value is True):
                        return True
            if isinstance(n, ast.Call):
                for kw in n.keywords:
                    if kw.arg == key and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        return True
    return False


def _const_false_for(answer: str, key: str) -> bool:
    for t in trees(answer):
        for n in ast.walk(t):
            if isinstance(n, ast.Dict):
                for k, v in zip(n.keys, n.values):
                    if (isinstance(k, ast.Constant) and k.value == key
                            and isinstance(v, ast.Constant) and v.value is False):
                        return True
    return False


# ---------------------------------------------------------------- checks

def uses_native_tool_calling(a: str) -> bool:
    """A real, hand-written tool schema exists.

    A bare `tools=` kwarg is not enough: framework constructors take one too
    (AgentExecutor(tools=[...])), and passing a list of framework tool objects is
    the thing this check exists to distinguish from. Require a schema-shaped dict
    literal — name plus parameters/input_schema — which only a native definition has.
    """
    keys = _dict_keys(a)
    return bool("name" in keys and ({"parameters", "input_schema"} & keys))


def strict_mode_on(a: str) -> bool:
    return _const_true_for(a, "strict")


def additional_properties_false(a: str) -> bool:
    """Strict mode requires additionalProperties:false on every object.

    Two legitimate routes: write it in a raw schema, or hand a Pydantic/Zod model
    to the SDK's parse()/structured helper, which injects it during conversion.
    Pydantic does not emit the field itself, so requiring the literal would
    penalise exactly the path structured-output/SKILL.md recommends by default.
    """
    if _const_false_for(a, "additionalProperties"):
        return True
    sdk_injects = re.search(r"\.parse\(", a) and re.search(r"response_format\s*=|BaseModel", a)
    return bool(sdk_injects)


def no_framework(a: str) -> bool:
    return not FRAMEWORKS.search(a)


def keeps_framework(a: str) -> bool:
    """Control t04: the user's load-bearing framework survives *in the code*.

    Mentioning it in prose is not keeping it — "you don't need LangGraph" names it
    while removing it. Require it in an import or a call inside a code block, and
    fail outright on prose that proposes dropping it.
    """
    if re.search(r"(don'?t need|drop(ping)?|remove|rip out|without|replace)\s+"
                 r"(the\s+)?langgraph", a, re.I):
        return False
    return bool(re.search(r"(from|import)\s+langgraph|langgraph\.\w+|StateGraph",
                          code(a), re.I))


def tool_result_role(a: str) -> bool:
    return bool(re.search(r'"tool_call_id"|tool_call_id\s*=|"tool_result"|tool_use_id', a))


def tool_errors_as_data(a: str) -> bool:
    """An except: that returns/appends rather than re-raising."""
    for t in trees(a):
        for n in ast.walk(t):
            if isinstance(n, ast.ExceptHandler):
                body = ast.dump(ast.Module(body=n.body, type_ignores=[]))
                if "Raise" not in body and ("Return" in body or "Call" in body):
                    return True
    return False


def sql_is_safe(a: str) -> bool:
    """The model must not be the source of executed SQL.

    Unsafe: a SQL-writing agent (the model emits the query), or interpolated SQL
    with no parameter binding anywhere.
    Safe:   parameter binding present (%s / ? / :named / execute(q, params)), which
            covers the legitimate pattern of an allowlisted clause skeleton
            interpolated into an f-string with values bound separately.
    n/a:    the answer does not touch SQL at all.
    """
    c = code(a)
    # A framework SQL agent means the model writes the SQL. That is the failure.
    if re.search(r"create_sql_agent|SQLDatabaseChain|SQLDatabaseToolkit|text-to-sql", a, re.I):
        return False
    if not re.search(r"\b(SELECT|INSERT|UPDATE|DELETE)\b", c, re.I):
        return None
    interpolated = re.search(r"(f\"[^\"]*\b(SELECT|WHERE|FROM)\b[^\"]*\{|"
                             r"f'[^']*\b(SELECT|WHERE|FROM)\b[^']*\{|"
                             r"\b(SELECT|WHERE|FROM)\b[^\n]*[\"']\s*\+\s*\w)", c, re.I)
    if not interpolated:
        return True
    bound = re.search(r"%s|\?\s*[,)\"']|:\w+\b[^\n]*(?:params|dict)|"
                      r"execute\([^)]+,\s*[\[(]?\w+", c)
    return bool(bound)


def has_stopping_condition(a: str) -> bool:
    c = code(a)
    return bool(re.search(r"max_iter|max_turns|max_steps|MAX_ITER|range\(\s*\w*MAX|"
                          r"for\s+\w+\s+in\s+range\(", c))


def model_driven_loop(a: str) -> bool:
    """A while/for loop whose continuation depends on the model's output."""
    for t in trees(a):
        for n in ast.walk(t):
            if isinstance(n, (ast.While, ast.For)):
                seg = ast.dump(n)
                if re.search(r"tool_call|tool_use|stop_reason|finish_reason", seg):
                    return True
    return False


def enum_for_bounded_fields(a: str) -> bool:
    return '"enum"' in a or "'enum'" in a or "Literal[" in a or "(str, Enum)" in a


def typed_fields_not_grammar(a: str) -> bool:
    """t09: the DSL must not be handed to the model to emit.

    Scoped to string literals inside the code — an answer that argues in prose
    against prompt-described grammars must not be penalised for naming the thing
    it is arguing against.
    """
    grammar = re.compile(r"(field:value|query syntax|AND / OR|AND/OR|emit only the query|"
                         r"query language:|syntax is|you can use the following)", re.I)
    for t in trees(a):
        for n in ast.walk(t):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and grammar.search(n.value):
                return False
    # also catch the model's raw output being fed to the search API
    if re.search(r"message\.content[^\n]*\n?[^\n]*(search|query)\(", code(a), re.I):
        return False
    return True


def query_built_in_code(a: str) -> bool:
    c = code(a)
    return bool(re.search(r"(\.join\(|\bparams\b|\bfilters\b|\bwhere\b\s*=|build_query|"
                          r"construct_query)", c, re.I))


def nullable_optional_fields(a: str) -> bool:
    return bool(re.search(r"\|\s*None|Optional\[|\"null\"|'null'", a))


def handles_refusal_or_truncation(a: str) -> bool:
    return bool(re.search(r"finish_reason|stop_reason|\.refusal|max_tokens\"|"
                          r"incomplete_details", a))


def no_forced_schema_on_prose(a: str) -> bool:
    """Control t08: summarising into a paragraph should not get a JSON schema."""
    # `output_config` alone is not a schema: it also carries `effort`, which a plain
    # prose summary legitimately sets. Only its `format` field forces structure.
    return not re.search(
        r"response_format|output_config\s*=\s*\{[^}]*format|json_schema|BaseModel", a)


def reasoning_before_label(a: str) -> bool:
    """The reasoning field must be declared before the label field."""
    for t in trees(a):
        for n in ast.walk(t):
            if isinstance(n, ast.ClassDef):
                fields = [x.target.id for x in n.body
                          if isinstance(x, ast.AnnAssign) and isinstance(x.target, ast.Name)]
                if any("reason" in f for f in fields) and len(fields) > 1:
                    ri = next(i for i, f in enumerate(fields) if "reason" in f)
                    return ri == 0
    return False


def recommends_workflow_not_agent(a: str) -> bool:
    """t13/t14: says plainly that no agent loop is needed."""
    return bool(re.search(
        r"(don'?t need an agent|not an agent|no agent|a workflow|scheduled (script|job)|"
        r"cron|simple(r)? (script|pipeline)|single (LLM )?call|doesn'?t require an agent)",
        a, re.I))


def consolidates_tools(a: str) -> bool:
    """t10: fewer tools than endpoints, or says so explicitly."""
    if re.search(r"(consolidat|don'?t (just )?wrap|one tool per (task|workflow)|"
                 r"not one[- ]to[- ]one|group(ed)? (them )?by task)", a, re.I):
        return True
    names = re.findall(r'"name"\s*:\s*"([a-z_]+)"', a)
    return bool(names) and len(set(names)) < 14


def measures_before_decomposing(a: str) -> bool:
    """t11: says to measure/eval before splitting the tool."""
    return bool(re.search(r"(eval|measure|test set|before (you )?(split|decompos)|"
                          r"confirm(ed)? (the|this) failure)", a, re.I))


def minimal_for_trivial_tool(a: str) -> bool:
    """Control t12: no tool-search / defer_loading / input_examples ceremony."""
    return not re.search(r"defer_loading|tool_search|input_examples|allowed_callers", a)


def notes_cost_or_tradeoff(a: str) -> bool:
    return bool(re.search(r"(cost|token|cheaper|expensive|tradeoff|trade-off|"
                          r"latency|overhead)", a, re.I))
