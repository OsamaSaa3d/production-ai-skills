#!/usr/bin/env python3
"""Lint the skills in this repository.

Checks structure, frontmatter, link integrity, and the repo's two standing
conventions: skills stay provider-neutral, and anything naming an API surface
tells the agent to verify it against the live reference.

Usage:  python3 scripts/lint_skills.py [--quiet]
Exit code 1 if any error is found. Warnings never fail the build.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DESCRIPTION_MAX = 1024
NAME_MAX = 64

# Reference-style links in either style the repo uses:
#   `references/foo.md`  or  [references/foo.md](references/foo.md)
LOCAL_REF_RE = re.compile(r"(?<![\w/])references/([a-z0-9][a-z0-9-]*\.md)")
# Cross-skill: `other-skill/references/foo.md`
CROSS_REF_RE = re.compile(r"([a-z0-9][a-z0-9-]*)/references/([a-z0-9][a-z0-9-]*\.md)")

# Vendor model ids must not be hardcoded in samples; use a placeholder instead.
VENDOR_MODEL_RE = re.compile(
    r"\b("
    r"gpt-[0-9][\w.-]*"
    r"|claude-(?:opus|sonnet|haiku|fable|mythos)-[\w.-]+"
    r"|gemini-[0-9][\w.-]*"
    r"|o[1-9]-(?:mini|preview)"
    r")\b"
)

VERIFY_MARKER = "Verify before you build"
# Anything naming a concrete wire contract must carry the verify banner.
API_SURFACE_RE = re.compile(
    r"output_config|response_format|input_schema|defer_loading|cache_control"
    r"|allowed_callers|input_examples|tool_choice|_2025\d{4}|_2026\d{4}"
    r"|CLAUDE_CODE_|client\.(?:messages|chat|responses|models|beta)"
    r"|api\.(?:openai|anthropic)\.com|openrouter\.ai"
    r"|max_tokens|stop_reason|finish_reason"
)

errors: list[str] = []
warnings: list[str] = []


def err(path: Path, msg: str) -> None:
    errors.append(f"{path.relative_to(ROOT)}: {msg}")


def warn(path: Path, msg: str) -> None:
    warnings.append(f"{path.relative_to(ROOT)}: {msg}")


def parse_frontmatter(path: Path, text: str) -> dict[str, str] | None:
    if not text.startswith("---\n"):
        err(path, "missing YAML frontmatter (file must start with '---')")
        return None
    end = text.find("\n---\n", 3)
    if end == -1:
        err(path, "frontmatter is not closed with '---'")
        return None
    fields: dict[str, str] = {}
    key = None
    for line in text[4:end].split("\n"):
        m = re.match(r"^([a-zA-Z][\w-]*):\s*(.*)$", line)
        if m:
            key = m.group(1)
            fields[key] = m.group(2).strip()
        elif key and line.startswith((" ", "\t")):
            fields[key] += " " + line.strip()
    return fields


def check_frontmatter(skill_dir: Path, skill_md: Path, text: str) -> None:
    fields = parse_frontmatter(skill_md, text)
    if fields is None:
        return

    for required in ("name", "description"):
        if required not in fields or not fields[required]:
            err(skill_md, f"frontmatter is missing a non-empty '{required}'")

    name = fields.get("name", "")
    if name:
        if name != skill_dir.name:
            err(skill_md, f"frontmatter name {name!r} != directory {skill_dir.name!r}")
        if not NAME_RE.match(name):
            err(skill_md, f"name {name!r} must be lowercase alphanumeric with single hyphens")
        if len(name) > NAME_MAX:
            err(skill_md, f"name is {len(name)} chars (max {NAME_MAX})")

    desc = fields.get("description", "")
    if desc and len(desc) > DESCRIPTION_MAX:
        err(skill_md, f"description is {len(desc)} chars (max {DESCRIPTION_MAX})")

    unexpected = set(fields) - {"name", "description", "license", "allowed-tools", "version"}
    if unexpected:
        warn(skill_md, f"unrecognized frontmatter keys: {sorted(unexpected)}")


def check_links(md: Path, skill_dir: Path, skill_names: set[str]) -> None:
    text = md.read_text(encoding="utf-8")

    for name in set(CROSS_REF_RE.findall(text)):
        other, ref = name
        if other not in skill_names:
            continue  # not a cross-skill path, e.g. a directory in prose
        if not (ROOT / other / "references" / ref).is_file():
            err(md, f"cross-skill reference does not exist: {other}/references/{ref}")

    # Strip cross-skill matches so they aren't re-flagged as local.
    local_text = CROSS_REF_RE.sub("", text)
    for ref in set(LOCAL_REF_RE.findall(local_text)):
        if not (skill_dir / "references" / ref).is_file():
            err(md, f"reference does not exist: references/{ref}")


def check_conventions(md: Path, text: str, is_skill_root: bool) -> None:
    for model in sorted(set(VENDOR_MODEL_RE.findall(text))):
        err(
            md,
            f"hardcoded vendor model id {model!r} — skills are provider-neutral; "
            f"use a MODEL placeholder instead",
        )

    if is_skill_root or API_SURFACE_RE.search(text):
        if VERIFY_MARKER not in text:
            err(
                md,
                f"names an API surface but has no {VERIFY_MARKER!r} banner — "
                f"add one so the agent checks the live contract",
            )


def main() -> int:
    quiet = "--quiet" in sys.argv

    skill_dirs = sorted(
        p.parent for p in ROOT.glob("*/SKILL.md") if not p.parent.name.startswith(".")
    )
    if not skill_dirs:
        print("no skills found — expected <skill-name>/SKILL.md at the repo root")
        return 1

    skill_names = {d.name for d in skill_dirs}

    # A directory with references/ but no SKILL.md is a mistake.
    for refs in ROOT.glob("*/references"):
        if refs.parent.name not in skill_names and not refs.parent.name.startswith("."):
            err(refs, "references/ directory with no SKILL.md beside it")

    for skill_dir in skill_dirs:
        skill_md = skill_dir / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8")

        check_frontmatter(skill_dir, skill_md, text)
        check_links(skill_md, skill_dir, skill_names)
        check_conventions(skill_md, text, is_skill_root=True)

        refs_dir = skill_dir / "references"
        if not refs_dir.is_dir():
            continue

        linked: set[str] = set()
        for md in sorted(refs_dir.glob("*.md")):
            ref_text = md.read_text(encoding="utf-8")
            check_links(md, skill_dir, skill_names)
            check_conventions(md, ref_text, is_skill_root=False)
            if f"references/{md.name}" in text:
                linked.add(md.name)

        for md in sorted(refs_dir.glob("*.md")):
            if md.name not in linked:
                warn(md, "not linked from its SKILL.md — it will never be discovered")

    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")

    if not quiet or errors:
        print()
        print(
            f"{len(skill_dirs)} skills checked — "
            f"{len(errors)} error(s), {len(warnings)} warning(s)"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
