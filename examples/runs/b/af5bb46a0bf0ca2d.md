Everything checks out. Here's what I built:

**`fix_test.py`** — an agent (not a workflow: the number of edit/test cycles a failing test needs is genuinely unpredictable, and pytest/the test command give real ground truth at every step, so per `agent-vs-workflow-decision` this clears the bar for a loop rather than a fixed script).

It takes `--repo` and `--test-cmd`, gives the model four tools (`read_file`, `search_files`, `edit_file` with unique old/new-string replacement, `run_tests`) plus a `record_plan` tool for visible planning, and loops until the test passes or a stopping condition trips:

- iteration cap, cost cap, wall-clock cap, and stuck-detection (same tool+args 3x) — all four, checked both before and after paying for each response
- edits are sandboxed to the repo root (path-traversal rejected)
- refuses to run on a dirty git tree unless `--allow-dirty`, so every change is trivially revertable
- pass/fail is decided by the harness's own final `run_tests` call, never by the model's say-so
- writes a structured JSON run log (iterations, cost, tool calls, plan revisions, final result)

I verified the mechanics directly (no API key is configured in this environment, so I couldn't run a live model loop): built a demo repo at `demo/` with a real bug (`average()` overwrites instead of accumulating) and a failing test, then drove the tool functions directly — traversal-blocking, ambiguous-edit rejection, the actual fix via `edit_file`, `run_tests` going from fail→pass, and both the stuck and iteration-cap stopping conditions all behaved correctly. I reset `demo/` back to its original failing state (committed, clean tree) so it's ready for a real run.

To actually use it: `export ANTHROPIC_API_KEY=...` then `python fix_test.py --repo demo --test-cmd "python -m pytest tests/test_mathutils.py::test_average_of_three_numbers -q"`. The pricing constants (`--price-in-per-mtok`/`--price-out-per-mtok`) are placeholders — worth checking current rates before relying on the cost cap.

---

## Files written by the session

### `demo/.gitignore`

````
__pycache__/
.fix_test_run.json

````

### `demo/src/mathutils.py`

````py
def average(numbers):
    """Return the arithmetic mean of a non-empty list of numbers."""
    total = 0
    for n in numbers:
        total = n  # bug: overwrites instead of accumulating
    return total / len(numbers)

````

### `demo/tests/test_mathutils.py`

````py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mathutils import average


def test_average_of_three_numbers():
    assert average([1, 2, 3]) == 2

````

### `fix_test.py`

````py
"""Agent that takes one failing test and iterates (read, edit, run) until it passes.

Usage:
    python fix_test.py --repo /path/to/repo --test-cmd "pytest tests/test_foo.py::test_bar -x"

See --help for budget caps, model choice, and pricing overrides.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import os

import anthropic

MAX_TOOL_OUTPUT_CHARS = 4000
MAX_SEARCH_MATCHES = 200


# ---------------------------------------------------------------------------
# Budget / run state — see .claude/skills/agent-vs-workflow-decision
# ---------------------------------------------------------------------------

@dataclass
class Budget:
    max_iterations: int = 15
    max_cost_usd: float = 2.00
    max_wall_clock_s: float = 600.0
    # Placeholder rates — verify against current pricing before relying on the
    # cost cap; override with --price-in-per-mtok / --price-out-per-mtok.
    price_in_per_mtok: float = 3.00
    price_out_per_mtok: float = 15.00


@dataclass
class RunState:
    iterations: int = 0
    cost_usd: float = 0.0
    started: float = field(default_factory=time.monotonic)
    call_signatures: Counter = field(default_factory=Counter)
    tool_call_log: list = field(default_factory=list)
    plan_revisions: int = 0
    last_run_tests_passed: bool | None = None

    def elapsed(self) -> float:
        return time.monotonic() - self.started


def check_budget(state: RunState, budget: Budget) -> str | None:
    if state.iterations >= budget.max_iterations:
        return "max_iterations"
    if state.cost_usd >= budget.max_cost_usd:
        return "budget_exceeded"
    if state.elapsed() >= budget.max_wall_clock_s:
        return "timeout"
    if max(state.call_signatures.values(), default=0) >= 3:
        return "stuck"
    return None


def price(usage, budget: Budget) -> float:
    return (usage.input_tokens / 1e6) * budget.price_in_per_mtok + \
           (usage.output_tokens / 1e6) * budget.price_out_per_mtok


def truncate(text: str, limit: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars; narrow your request]"


# ---------------------------------------------------------------------------
# Sandbox: every tool is confined to the repo root, no path traversal out.
# ---------------------------------------------------------------------------

class Sandbox:
    def __init__(self, repo_root: Path):
        self.root = repo_root.resolve()

    def resolve(self, rel_path: str) -> Path:
        if Path(rel_path).is_absolute() or ".." in Path(rel_path).parts:
            raise ValueError(
                f"path must be relative to the repo root and may not contain '..': {rel_path!r}"
            )
        candidate = (self.root / rel_path).resolve()
        if self.root not in candidate.parents and candidate != self.root:
            raise ValueError(f"path escapes the repo root: {rel_path!r}")
        return candidate


# ---------------------------------------------------------------------------
# Tools. Each returns (result_dict, is_error, ground_truth: bool)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "read_file",
        "description": (
            "Read a text file from the target repo. path is relative to the repo root "
            "(e.g. 'src/util.py') — absolute paths and '..' are rejected. Returns content "
            "with 1-indexed line numbers prefixed, so exact line context is visible for "
            "edit_file calls. Optionally pass start_line/end_line (1-indexed, inclusive) "
            "to read a slice instead of a whole large file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_files",
        "description": (
            "Search file contents across the repo for a regex pattern, optionally restricted "
            "to files matching a glob (e.g. '*.py'). Returns matching file paths with line "
            "numbers and line text, capped at 200 matches. Use this to locate where a symbol, "
            "function, or error string is defined before reading a whole file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "glob": {"type": "string"},
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Replace an exact, unique text match in a file. old_string must match the current "
            "file content exactly, including whitespace, and must appear exactly once — include "
            "enough surrounding context to make it unique. Fails with an error (no partial edit) "
            "if old_string is missing or appears more than once. Always read_file first to see "
            "the exact current content. To insert new content, include an anchor line in both "
            "old_string and new_string."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
            },
            "required": ["path", "old_string", "new_string"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_tests",
        "description": (
            "Run the target test command in the repo and report the result. Returns exit_code, "
            "stdout, and stderr (each truncated with a note if long). This is the ground-truth "
            "signal for whether a fix works — call it after every edit you believe might fix the "
            "failure. Never assert the test passes without calling this and reading exit_code."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "record_plan",
        "description": (
            "Record or update your plan before acting, and again whenever it changes materially. "
            "Stored in the run log for human review; does not affect execution."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "steps": {"type": "array", "items": {"type": "string"}},
                "success_criteria": {"type": "string"},
            },
            "required": ["steps", "success_criteria"],
            "additionalProperties": False,
        },
    },
]


class ToolRunner:
    def __init__(self, sandbox: Sandbox, test_cmd: str, state: RunState):
        self.sandbox = sandbox
        self.test_cmd = test_cmd
        self.state = state

    def dispatch(self, name: str, args: dict) -> tuple[dict, bool]:
        try:
            if name == "read_file":
                return self._read_file(**args), False
            if name == "search_files":
                return self._search_files(**args), False
            if name == "edit_file":
                return self._edit_file(**args), False
            if name == "run_tests":
                return self._run_tests(), False
            if name == "record_plan":
                self.state.plan_revisions += 1
                return {"ok": True, "recorded": args}, False
            return {"error": f"unknown tool {name}"}, True
        except Exception as exc:  # noqa: BLE001 - surfaced to the model as a steerable error
            return {"error": str(exc)}, True

    def _read_file(self, path: str, start_line: int | None = None, end_line: int | None = None) -> dict:
        p = self.sandbox.resolve(path)
        if not p.is_file():
            return {"error": f"no such file: {path}"}
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        lo = (start_line or 1) - 1
        hi = end_line or len(lines)
        numbered = "\n".join(f"{i + 1}\t{line}" for i, line in enumerate(lines[lo:hi], start=lo))
        return {"path": path, "total_lines": len(lines), "content": truncate(numbered)}

    def _search_files(self, pattern: str, glob: str = "*") -> dict:
        try:
            rx = re.compile(pattern)
        except re.error as exc:
            return {"error": f"invalid regex: {exc}"}
        matches = []
        for fp in self.sandbox.root.rglob(glob):
            if not fp.is_file() or ".git" in fp.parts:
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if rx.search(line):
                    matches.append({
                        "path": str(fp.relative_to(self.sandbox.root)).replace("\\", "/"),
                        "line": i,
                        "text": line.strip()[:200],
                    })
                    if len(matches) >= MAX_SEARCH_MATCHES:
                        return {"matches": matches, "truncated": True}
        return {"matches": matches, "truncated": False}

    def _edit_file(self, path: str, old_string: str, new_string: str) -> dict:
        p = self.sandbox.resolve(path)
        if not p.is_file():
            return {"error": f"no such file: {path}"}
        text = p.read_text(encoding="utf-8", errors="replace")
        count = text.count(old_string)
        if count == 0:
            return {"error": "old_string not found — it must match the file exactly, "
                              "including whitespace. Re-read the file to check current content."}
        if count > 1:
            return {"error": f"old_string is not unique ({count} occurrences) — include more "
                              "surrounding context so it matches exactly one location."}
        p.write_text(text.replace(old_string, new_string, 1), encoding="utf-8")
        return {"ok": True, "path": path}

    def _run_tests(self) -> dict:
        try:
            proc = subprocess.run(
                self.test_cmd, shell=True, cwd=self.sandbox.root,
                capture_output=True, text=True, timeout=120,
            )
            passed = proc.returncode == 0
            self.state.last_run_tests_passed = passed
            return {
                "exit_code": proc.returncode,
                "passed": passed,
                "stdout": truncate(proc.stdout),
                "stderr": truncate(proc.stderr),
            }
        except subprocess.TimeoutExpired:
            self.state.last_run_tests_passed = False
            return {"error": "test command timed out after 120s"}


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are fixing one failing test in a real repository. Work autonomously \
using the provided tools until the test passes or you are certain it cannot be fixed within \
scope.

Process:
1. Call record_plan with your initial investigation plan and success criteria.
2. Investigate with search_files / read_file before changing anything — understand why the \
test fails, don't guess from the error string alone.
3. Make the smallest edit_file change that addresses the root cause. Prefer fixing the \
implementation over the test. Only modify the test file itself if you find clear evidence \
the test is wrong (e.g. it contradicts documented behavior) — state that reasoning explicitly \
if you do.
4. Call run_tests after every change that might affect the outcome. Never claim the test \
passes without a run_tests call showing passed: true in this turn or the previous one.
5. If run_tests still fails, read the new stdout/stderr carefully — it usually tells you \
exactly what's still wrong — and revise your plan with record_plan if your approach changed.
6. Once run_tests reports passed: true, stop making tool calls and reply with a short summary \
of the root cause and the fix.

If you get stuck after a genuine attempt, stop and explain what you tried and why it isn't \
working, rather than repeating the same edit."""


def run_agent(repo_root: Path, test_cmd: str, budget: Budget, model: str) -> dict:
    client = anthropic.Anthropic()
    sandbox = Sandbox(repo_root)
    state = RunState()
    runner = ToolRunner(sandbox, test_cmd, state)
    run_id = str(uuid.uuid4())

    baseline = runner._run_tests()
    messages = [{
        "role": "user",
        "content": (
            f"Repo root: {repo_root}\nTest command: {test_cmd}\n\n"
            f"Baseline run_tests result (already executed, do not repeat it as your first "
            f"action):\n{json.dumps(baseline, indent=2)}\n\n"
            "Fix the repo so this test command exits 0."
        ),
    }]

    status = None
    while status is None:
        status = check_budget(state, budget)
        if status:
            break

        response = client.messages.create(
            model=model, max_tokens=4096, system=SYSTEM_PROMPT,
            tools=TOOLS, messages=messages,
        )
        state.iterations += 1
        state.cost_usd += price(response.usage, budget)

        assistant_content = [block.model_dump() for block in response.content]
        messages.append({"role": "assistant", "content": assistant_content})

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_use_blocks:
            break  # model is done talking; verify independently below

        status = check_budget(state, budget)  # re-check after paying for this response
        if status:
            break

        tool_results = []
        for tc in tool_use_blocks:
            sig = (tc.name, json.dumps(tc.input, sort_keys=True))
            state.call_signatures[sig] += 1
            if state.call_signatures[sig] == 2:
                result, is_error = {
                    "error": "You already called this tool with these exact arguments and got "
                             "this same result. Try different arguments, a different tool, or "
                             "stop and explain what you have."
                }, True
            else:
                result, is_error = runner.dispatch(tc.name, tc.input)

            state.tool_call_log.append({
                "i": state.iterations, "name": tc.name, "args": tc.input,
                "ok": not is_error, "result_chars": len(json.dumps(result)),
            })
            tool_results.append({
                "type": "tool_result", "tool_use_id": tc.id,
                "content": json.dumps(result), "is_error": is_error,
            })
        messages.append({"role": "user", "content": tool_results})

    # Ground truth is our own final check, not the model's claim.
    final = runner._run_tests()
    if status is None:
        status = "success" if final["passed"] else "stopped_without_passing"

    outcome = {
        "run_id": run_id, "status": status, "test_passed": final["passed"],
        "iterations": state.iterations, "cost_usd": round(state.cost_usd, 4),
        "elapsed_s": round(state.elapsed(), 1), "plan_revisions": state.plan_revisions,
        "tool_calls": state.tool_call_log, "final_run_tests": final,
    }
    return outcome


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, type=Path, help="repo root to operate in")
    ap.add_argument("--test-cmd", required=True, help="shell command that runs the failing test, e.g. 'pytest tests/test_foo.py::test_bar -x'")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--max-iterations", type=int, default=15)
    ap.add_argument("--max-cost-usd", type=float, default=2.0)
    ap.add_argument("--max-wall-clock-s", type=float, default=600.0)
    ap.add_argument("--price-in-per-mtok", type=float, default=3.0, help="USD per million input tokens; verify against current pricing")
    ap.add_argument("--price-out-per-mtok", type=float, default=15.0, help="USD per million output tokens; verify against current pricing")
    ap.add_argument("--log", type=Path, default=None, help="write the structured run log here (default: <repo>/.fix_test_run.json)")
    ap.add_argument("--allow-dirty", action="store_true", help="skip the check that the repo is a clean git working tree before editing")
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set — export it before running this tool.")

    repo_root = args.repo.resolve()
    if not repo_root.is_dir():
        raise SystemExit(f"not a directory: {repo_root}")

    if not args.allow_dirty:
        git_dir = repo_root / ".git"
        if git_dir.exists():
            status = subprocess.run(
                ["git", "status", "--porcelain"], cwd=repo_root,
                capture_output=True, text=True,
            )
            if status.stdout.strip():
                raise SystemExit(
                    "repo has uncommitted changes — commit or stash first so this run's edits "
                    "are cleanly revertable, or pass --allow-dirty to proceed anyway."
                )
        else:
            print(f"warning: {repo_root} is not a git repo, edits will not be easily revertable")

    budget = Budget(
        max_iterations=args.max_iterations, max_cost_usd=args.max_cost_usd,
        max_wall_clock_s=args.max_wall_clock_s,
        price_in_per_mtok=args.price_in_per_mtok, price_out_per_mtok=args.price_out_per_mtok,
    )

    outcome = run_agent(repo_root, args.test_cmd, budget, args.model)

    log_path = args.log or (repo_root / ".fix_test_run.json")
    log_path.write_text(json.dumps(outcome, indent=2, default=str), encoding="utf-8")

    print(f"status: {outcome['status']}  test_passed: {outcome['test_passed']}")
    print(f"iterations: {outcome['iterations']}  cost_usd: {outcome['cost_usd']}  elapsed_s: {outcome['elapsed_s']}")
    print(f"run log: {log_path}")
    raise SystemExit(0 if outcome["test_passed"] else 1)


if __name__ == "__main__":
    main()

````
