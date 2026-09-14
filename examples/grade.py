#!/usr/bin/env python3
"""Grade every generated file, blind, and emit results.tsv.

The grader reads runs/*/ plus the manifests. Filenames are hashes; the task id
comes from the manifest, the arm is never passed into the rubric. No API calls.
"""
from __future__ import annotations
import json, pathlib, sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "graders"))
sys.path.insert(0, str(ROOT / "tasks"))
import rubrics  # noqa: E402
from tasks import BY_ID  # noqa: E402


def load_manifest() -> list[dict]:
    rows = []
    for mf in sorted((ROOT / "runs").glob("manifest_*.jsonl")):
        rows += [json.loads(l) for l in mf.read_text().splitlines() if l.strip()]
    return rows


def main() -> int:
    manifest = load_manifest()
    if not manifest:
        print("no manifests under examples/runs/ — nothing generated yet", file=sys.stderr)
        return 1

    out = [("task", "kind", "skill", "arm", "run", "check", "raw", "passed", "cites")]
    per_arm_task = defaultdict(list)

    for row in manifest:
        path = ROOT / "runs" / row["arm"] / row["file"]
        if not path.exists():
            print(f"missing {path}", file=sys.stderr); continue
        answer = path.read_text()
        g = rubrics.grade(row["task"], answer)       # arm not passed in
        t = BY_ID[row["task"]]
        for name, c in g["checks"].items():
            out.append((row["task"], t["kind"], t["skill"], row["arm"], row["run"],
                        name, c["result"], c["passed"], c["cites"]))
        if g["score"] is not None:
            per_arm_task[(row["task"], row["arm"])].append(g["score"])

    tsv = ROOT / "results.tsv"
    tsv.write_text("\n".join("\t".join(map(str, r)) for r in out))
    print(f"wrote {tsv} ({len(out)-1} check results)")

    print(f"\n{'task':<6}{'kind':<10}{'A':>7}{'B':>7}{'delta':>8}  n")
    for tid in sorted({k[0] for k in per_arm_task}):
        a = per_arm_task.get((tid, "a"), [])
        b = per_arm_task.get((tid, "b"), [])
        ma = sum(a)/len(a) if a else float("nan")
        mb = sum(b)/len(b) if b else float("nan")
        print(f"{tid:<6}{BY_ID[tid]['kind']:<10}{ma:>7.2f}{mb:>7.2f}{mb-ma:>+8.2f}  {len(a)}/{len(b)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
