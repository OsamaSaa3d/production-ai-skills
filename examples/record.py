#!/usr/bin/env python3
"""Record one generation into the manifest, with the schema enforced.

The orchestrator calls this after each session instead of hand-writing JSONL,
so a typo cannot silently corrupt a run. Writes the answer to the blinded
filename the grader expects.

  python3 examples/record.py --arm b --task t09 --run 0 \
      --answer-file /tmp/out.md --turns 4 --skill-triggered tool-design
"""
from __future__ import annotations
import argparse, hashlib, json, os, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tasks"))
from tasks import BY_ID  # noqa: E402


def blind_name(task_id: str, arm: str, run: int) -> str:
    """Salted hash so the grader cannot infer the arm from the filename."""
    salt = os.environ.get("EVAL_SALT", "prod-ai-skills")
    return hashlib.sha256(f"{salt}|{task_id}|{arm}|{run}".encode()).hexdigest()[:16] + ".md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["a", "b"], required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--run", type=int, required=True)
    ap.add_argument("--answer-file", required=True)
    ap.add_argument("--model", default="unknown")
    ap.add_argument("--turns", type=int, default=None)
    ap.add_argument("--input-tokens", type=int, default=None)
    ap.add_argument("--output-tokens", type=int, default=None)
    ap.add_argument("--cost-usd", type=float, default=None)
    ap.add_argument("--tools-used", default="", help="comma-separated")
    ap.add_argument("--skill-triggered", default="",
                    help="name of the skill the session actually loaded; empty = none")
    ap.add_argument("--transcript-file", default="",
                    help="session transcript, used by check_contamination.py")
    args = ap.parse_args()

    if args.task not in BY_ID:
        print(f"unknown task {args.task!r}", file=sys.stderr); return 1
    src = pathlib.Path(args.answer_file)
    if not src.is_file():
        print(f"no such answer file: {src}", file=sys.stderr); return 1
    answer = src.read_text()
    if not answer.strip():
        print(f"answer file is empty: {src}", file=sys.stderr); return 1

    outdir = ROOT / "runs" / args.arm
    outdir.mkdir(parents=True, exist_ok=True)
    fn = blind_name(args.task, args.arm, args.run)
    (outdir / fn).write_text(answer)

    if args.transcript_file:
        tdir = ROOT / "runs" / "transcripts" / args.arm
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / fn).write_text(pathlib.Path(args.transcript_file).read_text())

    row = dict(
        file=fn, task=args.task, arm=args.arm, run=args.run,
        model=args.model, turns=args.turns,
        input_tokens=args.input_tokens, output_tokens=args.output_tokens,
        cost_usd=args.cost_usd,
        tools_used=[t for t in args.tools_used.split(",") if t],
        skill_triggered=args.skill_triggered or None,
        ts=time.time(),
    )
    with (ROOT / "runs" / f"manifest_{args.arm}.jsonl").open("a") as f:
        f.write(json.dumps(row) + "\n")

    trig = args.skill_triggered or "none"
    print(f"recorded {args.task} arm={args.arm} run={args.run} -> {fn}  (skill: {trig})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
