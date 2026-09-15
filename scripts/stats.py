#!/usr/bin/env python3
"""Measure this repo so the README never has to assert a number it cannot prove.

A repo about engineering discipline that hand-writes "~11,000 lines" in its own
README is asserting a benchmark instead of measuring one. Every number this
prints is derived: skills come from the same glob the linter uses, eval facts are
imported from the real task and rubric definitions rather than copied out of
them, and run counts come from the published manifests. When a number here is
wrong, the repo is wrong — that is the point.

Usage:  python3 scripts/stats.py [--markdown] [--write-readme]
`--write-readme` rewrites the region between the <!-- stats:start --> and
<!-- stats:end --> markers in README.md, and refreshes the counts embedded in the
badge URLs between the <!-- badges:start --> and <!-- badges:end --> markers. A
badge is a number too, and a badge that disagrees with the table underneath it is
worse than no badge. Exit code 1 if the stats markers are absent.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"

# The linter keeps discovery inline in main(), so there is nothing importable to
# reuse. Mirrored verbatim instead: if one of these two ever changes, the other
# has to change with it.
SKILL_GLOB = "*/SKILL.md"

START = "<!-- stats:start -->"
END = "<!-- stats:end -->"
BADGE_START = "<!-- badges:start -->"
BADGE_END = "<!-- badges:end -->"

# Shields.io encodes the label and value into the path, so the count is a literal
# in the URL. Keyed by the measure that has to agree with it.
BADGE_COUNTS = {
    "skills": r"(badge/skills-)\d+(-)",
    "references": r"(badge/reference%20files-)\d+(-)",
}


def skill_dirs() -> list[Path]:
    return sorted(
        p.parent for p in ROOT.glob(SKILL_GLOB) if not p.parent.name.startswith(".")
    )


def lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def human(n: int) -> str:
    """The README wants '~11k lines', not '11043 lines'."""
    if n < 1000:
        return str(n)
    if n < 10_000:
        return f"~{n / 1000:.1f}k".replace(".0k", "k")
    return f"~{round(n / 1000)}k"


def markdown_counts() -> dict[str, int]:
    skills = skill_dirs()
    refs = [md for d in skills for md in sorted((d / "references").glob("*.md"))]
    skill_lines = sum(lines(d / "SKILL.md") for d in skills)
    ref_lines = sum(lines(md) for md in refs)
    return {
        "skills": len(skills),
        "references": len(refs),
        "files": len(skills) + len(refs),
        "skill_lines": skill_lines,
        "ref_lines": ref_lines,
        "total_lines": skill_lines + ref_lines,
    }


def eval_counts() -> dict[str, object]:
    """Import the real definitions. A copied-out number is a number that rots."""
    if not (EXAMPLES / "graders" / "rubrics.py").is_file():
        return {}
    for sub in ("graders", "tasks"):
        sys.path.insert(0, str(EXAMPLES / sub))
    import checks  # noqa: E402
    import rubrics  # noqa: E402
    from tasks import TASKS  # noqa: E402

    kinds: dict[str, int] = {}
    for t in TASKS:
        kinds[t["kind"]] = kinds.get(t["kind"], 0) + 1

    # A check is a public module-level function returning bool; `code` and
    # `trees` are AST helpers and are annotated accordingly, which is what keeps
    # this from having to name them.
    check_names = {
        name
        for name, fn in vars(checks).items()
        if callable(fn)
        and getattr(fn, "__module__", "") == "checks"
        and not name.startswith("_")
        and getattr(fn, "__annotations__", {}).get("return") in (bool, "bool")
    }
    used = {fn for rows in rubrics.RUBRICS.values() for fn, _ in rows}
    return {
        "tasks": len(TASKS),
        "kinds": dict(sorted(kinds.items())),
        "skills_covered": len({t["skill"] for t in TASKS}),
        "checks": len(check_names),
        "checks_used": len(used & check_names),
        "rubrics": len(rubrics.RUBRICS),
        "assignments": sum(len(rows) for rows in rubrics.RUBRICS.values()),
        "inverted": len(rubrics.INVERTED),
    }


def run_counts() -> dict[str, int]:
    """Published generations per arm. The manifests are gitignored, so 0 is a
    normal answer on a fresh clone and does not mean the harness never ran."""
    out = {}
    for arm in ("a", "b"):
        path = EXAMPLES / "runs" / f"manifest_{arm}.jsonl"
        out[arm] = (
            sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
            if path.is_file()
            else 0
        )
    return out


def render_text(md: dict, ev: dict, runs: dict) -> str:
    out = [
        "Production AI Skills - project status",
        "",
        f"  skills                    {md['skills']}",
        f"  reference files           {md['references']}",
        f"  markdown files            {md['files']}",
        "",
        f"  skill markdown            {md['total_lines']:,} lines ({human(md['total_lines'])})",
        f"    SKILL.md                {md['skill_lines']:,}",
        f"    references/             {md['ref_lines']:,}",
    ]
    if ev:
        kinds = ", ".join(f"{n} {k}" for k, n in ev["kinds"].items())
        out += [
            "",
            f"  eval tasks                {ev['tasks']} ({kinds})",
            f"  skills under eval         {ev['skills_covered']} of {md['skills']}",
            f"  deterministic checks      {ev['checks']} ({ev['checks_used']} wired into rubrics)",
            f"  validated rubrics         {ev['rubrics']}",
            f"  rubric check assignments  {ev['assignments']}",
        ]
    out += [
        "",
        f"  recorded runs, arm A      {runs['a']}",
        f"  recorded runs, arm B      {runs['b']}",
    ]
    return "\n".join(out)


def render_markdown(md: dict, ev: dict, runs: dict) -> str:
    rows = [
        ("Skills", f"{md['skills']}"),
        ("Reference files", f"{md['references']}"),
        ("Markdown files", f"{md['files']}"),
        (
            "Skill markdown",
            f"{human(md['total_lines'])} lines "
            f"({md['skill_lines']:,} in `SKILL.md` + {md['ref_lines']:,} in `references/`)",
        ),
    ]
    if ev:
        kinds = ", ".join(f"{n} {k}" for k, n in ev["kinds"].items())
        rows += [
            ("Eval tasks", f"{ev['tasks']} ({kinds})"),
            ("Deterministic checks", f"{ev['checks']}"),
            ("Validated rubrics", f"{ev['rubrics']}"),
            ("Rubric check assignments", f"{ev['assignments']}"),
        ]
    rows.append(("Recorded runs", f"arm A {runs['a']}, arm B {runs['b']}"))

    body = "\n".join(f"| {k} | {v} |" for k, v in rows)
    return (
        "| Measure | Value |\n| --- | --- |\n"
        f"{body}\n\n"
        "<sub>Generated by `python3 scripts/stats.py --markdown`. "
        "Refresh in place with `python3 scripts/stats.py --write-readme`.</sub>"
    )


def refresh_badges(text: str, md: dict) -> str:
    """Rewrite the counts inside the badge URLs, and only inside that region, so a
    stray '10' elsewhere in the README is never touched."""
    if BADGE_START not in text or BADGE_END not in text:
        return text
    head, rest = text.split(BADGE_START, 1)
    region, tail = rest.split(BADGE_END, 1)
    for measure, pattern in BADGE_COUNTS.items():
        region = re.sub(pattern, lambda m: f"{m.group(1)}{md[measure]}{m.group(2)}", region)
    return f"{head}{BADGE_START}{region}{BADGE_END}{tail}"


def write_readme(block: str, md: dict) -> int:
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    if START not in text or END not in text:
        print(
            f"error: {readme.name} has no {START} / {END} markers - add them around "
            f"the stat block first; this script will not guess where they belong",
            file=sys.stderr,
        )
        return 1
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    new = refresh_badges(f"{head}{START}\n{block}\n{END}{tail}", md)
    if new == text:
        print("README.md already up to date")
        return 0
    readme.write_text(new, encoding="utf-8")
    print("README.md updated")
    return 0


def main() -> int:
    md, ev, runs = markdown_counts(), eval_counts(), run_counts()
    if not md["skills"]:
        print("no skills found - expected <skill-name>/SKILL.md at the repo root")
        return 1

    if "--write-readme" in sys.argv:
        return write_readme(render_markdown(md, ev, runs), md)

    if "--markdown" in sys.argv:
        print(render_markdown(md, ev, runs))
    else:
        print(render_text(md, ev, runs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
