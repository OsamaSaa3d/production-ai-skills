#!/usr/bin/env bash
# Reproduce the whole comparison. Requires ANTHROPIC_API_KEY.
set -euo pipefail
cd "$(dirname "$0")/.."
N="${N:-5}"
echo "== plan =="
python3 examples/run.py --arm a --n "$N" --dry-run
echo "== arm A (no skills) =="
python3 examples/run.py --arm a --n "$N"
echo "== arm B (skills) =="
python3 examples/run.py --arm b --n "$N"
echo "== grading (blind) =="
python3 examples/grade.py
