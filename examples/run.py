#!/usr/bin/env python3
"""Generate one arm of the A/B. Requires ANTHROPIC_API_KEY.

  python3 examples/run.py --arm a --n 5
  python3 examples/run.py --arm b --n 5

Arm A: neutral system prompt only.
Arm B: identical, plus the task's SKILL.md appended.
Outputs are written under runs/<arm>/ with hashed filenames so the grader
cannot tell which arm produced a file.
"""
from __future__ import annotations
import argparse, hashlib, json, os, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / "tasks"))
from tasks import TASKS, BY_ID  # noqa: E402

MODEL = os.environ.get("EVAL_MODEL", "claude-sonnet-5")
NEUTRAL = ("You are a senior engineer. Write production-quality Python for the "
           "user's request. Show the code and briefly explain the key decisions.")

# Sonnet 5 list price, $/MTok. Override if you are on different terms.
PRICE_IN, PRICE_OUT = 2.00, 10.00


def system_for(task: dict, arm: str) -> str:
    if arm == "a":
        return NEUTRAL
    skill = (REPO / task["skill"] / "SKILL.md").read_text()
    return f"{NEUTRAL}\n\n<skill>\n{skill}\n</skill>"


def blind_name(task_id: str, arm: str, run: int) -> str:
    salt = os.environ.get("EVAL_SALT", "prod-ai-skills")
    h = hashlib.sha256(f"{salt}|{task_id}|{arm}|{run}".encode()).hexdigest()[:16]
    return f"{h}.md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["a", "b"], required=True)
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--tasks", default="", help="comma-separated ids; default all")
    ap.add_argument("--dry-run", action="store_true", help="no API calls; print the plan")
    args = ap.parse_args()

    ids = args.tasks.split(",") if args.tasks else [t["id"] for t in TASKS]
    outdir = ROOT / "runs" / args.arm
    outdir.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / "runs" / f"manifest_{args.arm}.jsonl"

    if args.dry_run:
        for tid in ids:
            t = BY_ID[tid]
            sysmsg = system_for(t, args.arm)
            print(f"{tid}  arm={args.arm}  n={args.n}  system_chars={len(sysmsg):>7,}  "
                  f"skill={t['skill'] if args.arm=='b' else '-'}")
        print(f"\n{len(ids) * args.n} generations planned. No API calls made.")
        return 0

    try:
        import anthropic
    except ImportError:
        print("pip install anthropic", file=sys.stderr); return 1
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("No credentials. Set ANTHROPIC_API_KEY.", file=sys.stderr); return 1

    client = anthropic.Anthropic()
    tot_in = tot_out = 0
    with manifest_path.open("a") as mf:
        for tid in ids:
            t = BY_ID[tid]
            for run in range(args.n):
                r = client.messages.create(
                    model=MODEL, max_tokens=4096,
                    system=system_for(t, args.arm),
                    messages=[{"role": "user", "content": t["prompt"]}],
                )
                text = "".join(b.text for b in r.content if b.type == "text")
                fn = blind_name(tid, args.arm, run)
                (outdir / fn).write_text(text)
                tot_in += r.usage.input_tokens
                tot_out += r.usage.output_tokens
                mf.write(json.dumps(dict(file=fn, task=tid, arm=args.arm, run=run,
                                         input_tokens=r.usage.input_tokens,
                                         output_tokens=r.usage.output_tokens,
                                         model=MODEL, ts=time.time())) + "\n")
                print(f"  {tid} run{run}  in={r.usage.input_tokens:>6}  out={r.usage.output_tokens:>5}  -> {fn}")

    cost = tot_in / 1e6 * PRICE_IN + tot_out / 1e6 * PRICE_OUT
    print(f"\narm {args.arm}: {tot_in:,} in / {tot_out:,} out  ~${cost:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
