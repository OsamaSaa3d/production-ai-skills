#!/usr/bin/env python3
"""Drive every task for one arm through fresh headless Claude Code sessions.

This is the orchestration step PROMPT.md describes, scripted so it is
reproducible. For each (task, run):

  - a brand-new empty directory is created: <base>/arm-<x>/<task>-r<run>/
    (arm B also gets all ten skills copied into .claude/skills/). One directory
    per run means no session ever sees files written by an earlier one.
  - `claude -p "<prompt verbatim>"` runs with that directory as cwd and with
      --setting-sources project   no user settings: no plugins, no global CLAUDE.md
      --strict-mcp-config         no MCP servers
      ENABLE_CLAUDEAI_MCP_SERVERS=false
    so the only thing that differs between arms is the skills on disk.
  - the answer is the session's final message, plus the contents of any files
    it wrote into its directory (sessions often write the code to disk and
    reply with a summary; grading only the summary would grade the wrong thing).
  - which repo skills fired is read from the transcript: a Skill tool call
    naming one of the ten, or a Read of its SKILL.md. Every one is recorded, not
    just the first — with all ten installed, a second skill firing alongside the
    right one is a result rather than noise.
  - the run is recorded with record.py.

Runs already in the manifest are skipped, so the script is resumable.

  python examples/run_arm.py --arm a --runs 3 --parallel 4
"""
from __future__ import annotations
import argparse, concurrent.futures as cf, json, os, pathlib, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / "tasks"))
from tasks import TASKS  # noqa: E402

SKILL_NAMES = sorted(p.parent.name for p in REPO.glob("*/SKILL.md"))
MAX_FILE_BYTES = 200_000

# Appended identically in both arms. Without it, a headless session in an empty
# directory often replies with clarifying questions and no code, which nobody
# can answer — the eval would then measure question-asking, not the skills.
# It names no technique and no skill; the task prompt itself stays verbatim.
NONINTERACTIVE_NOTE = (
    "This is a non-interactive session: nobody can answer questions. "
    "Make reasonable assumptions, state them briefly, and deliver working code."
)


def claude_exe() -> str:
    """The real binary. On Windows, going through claude.cmd would let cmd.exe
    reinterpret prompt characters like `>` and quotes — the prompt must arrive verbatim."""
    found = shutil.which("claude") or "claude"
    if found.lower().endswith(".cmd"):
        exe = pathlib.Path(found).parent / "node_modules/@anthropic-ai/claude-code/bin/claude.exe"
        if exe.exists():
            return str(exe)
    return found


def done_runs(arm: str) -> set[tuple[str, int]]:
    mf = ROOT / "runs" / f"manifest_{arm}.jsonl"
    if not mf.exists():
        return set()
    return {(r["task"], r["run"]) for r in map(json.loads, mf.read_text().splitlines()) if r}


def prepare_dir(base: pathlib.Path, arm: str, tid: str, run: int) -> pathlib.Path:
    d = base / f"arm-{arm}" / f"{tid}-r{run}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    if arm == "b":
        sk = d / ".claude" / "skills"
        sk.mkdir(parents=True)
        for name in SKILL_NAMES:
            shutil.copytree(REPO / name, sk / name)
    return d


def parse_stream(lines: list[str]) -> dict:
    result, turns, cost, in_tok, out_tok, model = "", None, None, None, None, None
    tools, fired, transcript = [], [], []
    for line in lines:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            model = ev.get("model")
            transcript.append(f"[init] cwd={ev.get('cwd')} model={model} "
                              f"mcp={ev.get('mcp_servers')} plugins={ev.get('plugins')} "
                              f"skills={ev.get('skills')}")
        elif t in ("assistant", "user"):
            for block in (ev.get("message") or {}).get("content") or []:
                if not isinstance(block, dict):
                    continue
                bt = block.get("type")
                if bt == "text":
                    transcript.append(f"[{t}] {block.get('text', '')}")
                elif bt == "tool_use":
                    name, inp = block.get("name"), block.get("input") or {}
                    tools.append(name)
                    transcript.append(f"[tool_use] {name} {json.dumps(inp, ensure_ascii=False)}")
                    cand = ""
                    if name == "Skill":
                        cand = str(inp.get("skill", "")).split(":")[-1]
                    elif name == "Read":
                        p = str(inp.get("file_path", "")).replace("\\", "/")
                        if "/.claude/skills/" in p:
                            cand = p.split("/.claude/skills/")[1].split("/")[0]
                    if cand in SKILL_NAMES and cand not in fired:
                        fired.append(cand)
                elif bt == "tool_result":
                    c = block.get("content")
                    if isinstance(c, list):
                        c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
                    transcript.append(f"[tool_result] {c}")
        elif t == "result":
            result = ev.get("result") or ""
            turns = ev.get("num_turns")
            cost = ev.get("total_cost_usd")
            u = ev.get("usage") or {}
            in_tok = (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) \
                + (u.get("cache_creation_input_tokens") or 0)
            out_tok = u.get("output_tokens")
            if ev.get("is_error"):
                result = ""
    return dict(result=result, turns=turns, cost=cost, in_tok=in_tok, out_tok=out_tok,
                model=model, tools=tools, fired=fired, transcript="\n".join(transcript))


# Directories a session creates by installing or building, not by writing code.
# Capturing them once put a 40 MB virtualenv into an answer, where the graders
# would have scored third-party library source as if the session wrote it.
SKIP_DIRS = {".claude", ".git", "__pycache__", "node_modules", "venv", ".venv", "env",
             ".env", "site-packages", ".mypy_cache", ".pytest_cache", ".ruff_cache",
             ".tox", "dist", "build"}


def _skipped(d: pathlib.Path, p: pathlib.Path) -> bool:
    rel = p.relative_to(d)
    for i, part in enumerate(rel.parts[:-1]):
        if part in SKIP_DIRS or part.endswith(".egg-info"):
            return True
        if (d.joinpath(*rel.parts[:i + 1]) / "pyvenv.cfg").exists():
            return True
    return False


def collect_files(d: pathlib.Path) -> str:
    parts = []
    for p in sorted(d.rglob("*")):
        rel = p.relative_to(d).as_posix()
        if not p.is_file() or _skipped(d, p):
            continue
        if p.stat().st_size > MAX_FILE_BYTES:
            parts.append(f"### `{rel}`\n\n(omitted: {p.stat().st_size} bytes)\n")
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lang = p.suffix.lstrip(".")
        parts.append(f"### `{rel}`\n\n````{lang}\n{text}\n````\n")
    if not parts:
        return ""
    return "\n\n---\n\n## Files written by the session\n\n" + "\n".join(parts)


def run_one(base, arm, task, run, model, effort, timeout):
    tid = task["id"]
    d = prepare_dir(base, arm, tid, run)
    env = dict(os.environ, ENABLE_CLAUDEAI_MCP_SERVERS="false", PYTHONUTF8="1")
    env.pop("CLAUDECODE", None)
    cmd = [claude_exe(), "-p", task["prompt"], "--model", model, "--effort", effort,
           "--append-system-prompt", NONINTERACTIVE_NOTE,
           "--setting-sources", "project", "--strict-mcp-config",
           "--dangerously-skip-permissions", "--output-format", "stream-json", "--verbose"]
    try:
        proc = subprocess.run(cmd, cwd=d, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
        out, err = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return dict(ok=False, tid=tid, run=run, why=f"timeout after {timeout}s")
    parsed = parse_stream(out.splitlines())
    if not parsed["result"].strip():
        tail = " ".join(l for l in out.splitlines()[-3:])[-300:]
        limited = "limit" in out.lower() and parsed["turns"] in (None, 0, 1)
        return dict(ok=False, tid=tid, run=run, limited=limited,
                    why=f"empty result; stdout tail={tail!r} stderr={err[-300:]!r}")
    parsed.update(ok=True, tid=tid, run=run, dir=d,
                  answer=parsed["result"] + collect_files(d))
    return parsed


def record(arm, r, scratch: pathlib.Path) -> None:
    scratch.mkdir(parents=True, exist_ok=True)
    ans = scratch / f"{arm}-{r['tid']}-{r['run']}.md"
    tr = scratch / f"{arm}-{r['tid']}-{r['run']}.transcript.txt"
    ans.write_text(r["answer"], encoding="utf-8")
    tr.write_text(r["transcript"], encoding="utf-8")
    cmd = [sys.executable, str(ROOT / "record.py"), "--arm", arm, "--task", r["tid"],
           "--run", str(r["run"]), "--answer-file", str(ans), "--transcript-file", str(tr),
           "--model", r["model"] or "unknown", "--tools-used", ",".join(r["tools"]),
           "--skill-triggered", r["fired"][0] if r["fired"] else "",
           "--skills-triggered", ",".join(r["fired"])]
    if r["turns"] is not None:
        cmd += ["--turns", str(r["turns"])]
    if r["in_tok"] is not None:
        cmd += ["--input-tokens", str(r["in_tok"])]
    if r["out_tok"] is not None:
        cmd += ["--output-tokens", str(r["out_tok"])]
    if r["cost"] is not None:
        cmd += ["--cost-usd", str(r["cost"])]
    subprocess.run(cmd, check=True, env=dict(os.environ, PYTHONUTF8="1"))
    if len(r["fired"]) > 1:
        print(f"    note: multiple skills fired: {r['fired']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["a", "b"], required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--tasks", default="", help="comma-separated ids; default all")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--base", default="/tmp/skills-eval")
    ap.add_argument("--scratch", default="/tmp/skills-eval/_records")
    args = ap.parse_args()

    base = pathlib.Path(args.base).expanduser().resolve()
    if REPO in base.parents or base == REPO:
        print("refusing: --base is inside the repository", file=sys.stderr); return 1
    wanted = set(args.tasks.split(",")) if args.tasks else None
    done = done_runs(args.arm)
    jobs = [(t, k) for t in TASKS for k in range(args.runs)
            if (wanted is None or t["id"] in wanted) and (t["id"], k) not in done]
    print(f"arm {args.arm}: {len(jobs)} runs to do ({len(done)} already recorded)")

    failures = []
    with cf.ThreadPoolExecutor(max_workers=args.parallel) as ex:
        futs = [ex.submit(run_one, base, args.arm, t, k, args.model, args.effort, args.timeout)
                for t, k in jobs]
        for f in cf.as_completed(futs):
            if f.cancelled():
                continue
            r = f.result()
            if not r["ok"]:
                print(f"  FAILED {r['tid']} run{r['run']}: {r['why']}")
                failures.append(r)
                # A usage limit fails every queued run instantly. Stop instead of
                # draining the queue; re-running the script resumes from the manifest.
                if r.get("limited"):
                    print("  usage limit hit: cancelling queued runs")
                    for pending in futs:
                        pending.cancel()
                continue
            record(args.arm, r, pathlib.Path(args.scratch).expanduser().resolve())
    print(f"done. {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
