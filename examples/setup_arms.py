#!/usr/bin/env python3
"""Create the two clean arm workspaces.

Both arms are empty scratch directories with no access to this repository.
The only difference is that arm B has the skills installed.

That isolation is the single most important control in the experiment: if a
session can reach this repo, arm A can read the skills and the comparison is
meaningless. The tasks are "write me code", not "work in this repo", so nothing
is lost by running them somewhere else.

  python3 examples/setup_arms.py                 # default: /tmp/skills-eval
  python3 examples/setup_arms.py --base ~/eval   # somewhere else
  python3 examples/setup_arms.py --force         # wipe and recreate
"""
from __future__ import annotations
import argparse, pathlib, shutil, sys

REPO = pathlib.Path(__file__).resolve().parent.parent


def skill_dirs() -> list[pathlib.Path]:
    return sorted(p.parent for p in REPO.glob("*/SKILL.md"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="/tmp/skills-eval")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    base = pathlib.Path(args.base).expanduser().resolve()
    if base.exists():
        if not args.force:
            print(f"{base} already exists. Re-run with --force to wipe it.", file=sys.stderr)
            return 1
        shutil.rmtree(base)

    a = base / "arm-a"
    b = base / "arm-b"
    a.mkdir(parents=True)
    b.mkdir(parents=True)

    # Arm B gets ALL ten skills, not just the relevant one. The agent has to pick
    # from ten descriptions exactly as a real user's agent would, which makes
    # triggering part of what is measured rather than something we hand it.
    skills_dir = b / ".claude" / "skills"
    skills_dir.mkdir(parents=True)
    for s in skill_dirs():
        shutil.copytree(s, skills_dir / s.name)

    installed = sorted(p.name for p in skills_dir.iterdir())
    print(f"arm A (no skills): {a}")
    print(f"   contents: {sorted(p.name for p in a.iterdir()) or 'empty'}")
    print(f"arm B (skills):    {b}")
    print(f"   contents: {sorted(p.name for p in b.iterdir())}")
    print(f"   {len(installed)} skills installed: {', '.join(installed)}")
    print()
    print("Run every session with its arm directory as the working directory, and")
    print("do NOT pass --add-dir pointing anywhere near this repository.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
