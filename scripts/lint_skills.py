#!/usr/bin/env python3
"""Lint the skills in this repository.

Checks structure, frontmatter, link integrity, and the repo's two standing
conventions: skills stay provider-neutral, and anything naming an API surface
tells the agent to verify it against the live reference.

Usage:  python3 scripts/lint_skills.py [--quiet]
Exit code 1 if any error is found. Warnings never fail the build.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# Both limits are the tightest across the agents these skills claim to support,
# not the most generous. Codex caps description at 500; Cursor and Copilot cap
# name at 64. Exceeding a limit does not raise an error at install time — the
# agent drops the skill and says nothing, so it is installed, looks fine, and
# never fires. Since the description is the only thing an agent sees before
# deciding to load a skill, that failure is silent and total. Hence a hard check.
DESCRIPTION_MAX = 500
NAME_MAX = 64

# Reference-style links in either style the repo uses:
#   `references/foo.md`  or  [references/foo.md](references/foo.md)
LOCAL_REF_RE = re.compile(r"(?<![\w/])references/([a-z0-9][a-z0-9-]*\.md)")
# Cross-skill: `other-skill/references/foo.md`
CROSS_REF_RE = re.compile(r"([a-z0-9][a-z0-9-]*)/references/([a-z0-9][a-z0-9-]*\.md)")
# Prose of the form `other-skill`'s `references/foo.md`. Always wrong: an agent
# resolves the bare references/ path against the file it is already reading. When
# both skills happen to own a file of that name it resolves silently to the wrong
# one, which is why this needs its own rule rather than relying on link checking.
POSSESSIVE_REF_RE = re.compile(
    r"`([a-z0-9][a-z0-9-]*)`'s\s+`references/([a-z0-9][a-z0-9-]*\.md)`"
)

# Vendor model ids must not be hardcoded in samples; use a placeholder instead.
VENDOR_MODEL_RE = re.compile(
    r"\b("
    r"gpt-[0-9][\w.-]*"
    r"|claude-(?:opus|sonnet|haiku|fable|mythos)-[\w.-]+"
    r"|gemini-[0-9][\w.-]*"
    r"|o[1-9]-(?:mini|preview)"
    r")\b"
)

# A ```python fence holding box-drawing or arrow glyphs *and* failing to parse
# is a diagram or table that was tagged as code. Both conditions are required:
# many valid samples put an arrow in a comment, and many valid samples are
# deliberate fragments that do not parse.
PY_FENCE_RE = re.compile(r"```python\n(.*?)```", re.S)
NOT_CODE_RE = re.compile(r"[─│└├┌┐┘→←↔⇒]")

VERIFY_MARKER = "Verify before you build"
# Anything naming a concrete wire contract must carry the verify banner.
API_SURFACE_RE = re.compile(
    r"output_config|response_format|input_schema|defer_loading|cache_control"
    r"|allowed_callers|input_examples|tool_choice|_2025\d{4}|_2026\d{4}"
    r"|CLAUDE_CODE_|client\.(?:messages|chat|responses|models|beta)"
    r"|api\.(?:openai|anthropic)\.com|openrouter\.ai"
    r"|max_tokens|stop_reason|finish_reason"
)

# Every finding is filed under one of these so a clean run can report which
# classes of check actually passed, rather than a bare count that proves nothing.
FRONTMATTER = "frontmatter"
NAMING = "skill naming"
LOCAL_REFS = "local references"
CROSS_REFS = "cross-skill references"
NEUTRALITY = "provider neutrality"
VERIFY = "API-surface verify banners"
FENCES = "code-fence integrity"
CHECK_CLASSES = (
    FRONTMATTER,
    NAMING,
    LOCAL_REFS,
    CROSS_REFS,
    NEUTRALITY,
    VERIFY,
    FENCES,
)

errors: list[tuple[str, str]] = []
warnings: list[tuple[str, str]] = []


def err(cls: str, path: Path, msg: str) -> None:
    errors.append((cls, f"{path.relative_to(ROOT)}: {msg}"))


def warn(cls: str, path: Path, msg: str) -> None:
    warnings.append((cls, f"{path.relative_to(ROOT)}: {msg}"))


def parse_frontmatter(path: Path, text: str) -> dict[str, str] | None:
    if not text.startswith("---\n"):
        err(FRONTMATTER, path, "missing YAML frontmatter (file must start with '---')")
        return None
    end = text.find("\n---\n", 3)
    if end == -1:
        err(FRONTMATTER, path, "frontmatter is not closed with '---'")
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
            err(FRONTMATTER, skill_md, f"frontmatter is missing a non-empty '{required}'")

    name = fields.get("name", "")
    if name:
        if name != skill_dir.name:
            err(NAMING, skill_md, f"frontmatter name {name!r} != directory {skill_dir.name!r}")
        if not NAME_RE.match(name):
            err(NAMING, skill_md, f"name {name!r} must be lowercase alphanumeric with single hyphens")
        if len(name) > NAME_MAX:
            err(NAMING, skill_md, f"name is {len(name)} chars (max {NAME_MAX})")

    desc = fields.get("description", "")
    if desc and len(desc) > DESCRIPTION_MAX:
        err(FRONTMATTER, skill_md, f"description is {len(desc)} chars (max {DESCRIPTION_MAX})")

    unexpected = set(fields) - {"name", "description", "license", "allowed-tools", "version"}
    if unexpected:
        warn(FRONTMATTER, skill_md, f"unrecognized frontmatter keys: {sorted(unexpected)}")


def check_links(md: Path, skill_dir: Path, skill_names: set[str]) -> None:
    text = md.read_text(encoding="utf-8")

    for name in set(CROSS_REF_RE.findall(text)):
        other, ref = name
        if other not in skill_names:
            continue  # not a cross-skill path, e.g. a directory in prose
        if not (ROOT / other / "references" / ref).is_file():
            err(CROSS_REFS, md, f"cross-skill reference does not exist: {other}/references/{ref}")

    for other, ref in POSSESSIVE_REF_RE.findall(text):
        err(
            CROSS_REFS,
            md,
            f"cross-skill reference written as `{other}`'s `references/{ref}` - an "
            f"agent resolves that against its own directory; write "
            f"`{other}/references/{ref}`",
        )

    # Strip cross-skill matches so they aren't re-flagged as local.
    local_text = CROSS_REF_RE.sub("", text)
    for ref in set(LOCAL_REF_RE.findall(local_text)):
        if not (skill_dir / "references" / ref).is_file():
            err(LOCAL_REFS, md, f"reference does not exist: references/{ref}")


def check_conventions(md: Path, text: str, is_skill_root: bool) -> None:
    for model in sorted(set(VENDOR_MODEL_RE.findall(text))):
        err(
            NEUTRALITY,
            md,
            f"hardcoded vendor model id {model!r} - skills are provider-neutral; "
            f"use a MODEL placeholder instead",
        )

    for block in PY_FENCE_RE.findall(text):
        glyph = NOT_CODE_RE.search(block)
        if not glyph:
            continue
        try:
            ast.parse(block)
        except SyntaxError:
            err(
                FENCES,
                md,
                # ascii(): the offending glyph is by definition outside cp1252's
                # comfort zone, and a UnicodeEncodeError while reporting a lint
                # error would bury the lint error.
                f"a ```python fence contains {ascii(glyph.group())} and does not parse - "
                f"it is a diagram or table, not code; tag it ```text",
            )

    if is_skill_root or API_SURFACE_RE.search(text):
        if VERIFY_MARKER not in text:
            err(
                VERIFY,
                md,
                f"names an API surface but has no {VERIFY_MARKER!r} banner - "
                f"add one so the agent checks the live contract",
            )


def main() -> int:
    quiet = "--quiet" in sys.argv

    skill_dirs = sorted(
        p.parent for p in ROOT.glob("*/SKILL.md") if not p.parent.name.startswith(".")
    )
    if not skill_dirs:
        print("no skills found - expected <skill-name>/SKILL.md at the repo root")
        return 1

    skill_names = {d.name for d in skill_dirs}

    # A directory with references/ but no SKILL.md is a mistake.
    for refs in ROOT.glob("*/references"):
        if refs.parent.name not in skill_names and not refs.parent.name.startswith("."):
            err(LOCAL_REFS, refs, "references/ directory with no SKILL.md beside it")

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
                warn(LOCAL_REFS, md, "not linked from its SKILL.md - it will never be discovered")

    summary = (
        f"{len(skill_dirs)} skills checked - "
        f"{len(errors)} error(s), {len(warnings)} warning(s)"
    )

    if quiet:
        for _, w in warnings:
            print(f"warning: {w}")
        for _, e in errors:
            print(f"error: {e}")
        if errors:
            print()
            print(summary)
        return 1 if errors else 0

    print("Production AI Skills - skill validation")
    print()
    # Anything filed under a class this file does not declare is a bug in the
    # filing, not a reason to drop the finding on the floor.
    classes = list(CHECK_CLASSES) + [
        c for c, _ in errors + warnings if c not in CHECK_CLASSES
    ]
    for cls in dict.fromkeys(classes):
        errs = [m for c, m in errors if c == cls]
        warns = [m for c, m in warnings if c == cls]
        status = "FAIL" if errs else "warn" if warns else "ok"
        print(f"  {status:<6}{cls}")
        for m in errs:
            print(f"        error: {m}")
        for m in warns:
            print(f"        warning: {m}")

    print()
    print(summary)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
