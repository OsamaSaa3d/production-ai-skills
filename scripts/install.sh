#!/bin/sh
# Install the skills in this repo into an agent's skills directory.
#
# `cp -r repo/* ~/.claude/skills/` also ships scripts/, examples/ and .github/
# into the skills folder, where every one of them becomes a directory the agent
# has to consider and none of them is a skill. This copies the skill directories
# and nothing else, discovered by globbing */SKILL.md so the list cannot go stale
# when a skill is added or removed.
#
# Usage:  ./scripts/install.sh --target <agent> [--user|--project] [--dry-run]
#         ./scripts/install.sh --target <agent> --dest DIR
#         ./scripts/install.sh --list
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)

TARGET=""
SCOPE="user"
DEST=""
DRY_RUN=0
LIST=0

usage() {
    cat <<'EOF'
Install the Production AI Skills into an agent's skills directory.

Usage:
  ./scripts/install.sh --target <agent> [--user|--project] [--dry-run]
  ./scripts/install.sh --target <agent> --dest DIR [--dry-run]
  ./scripts/install.sh --list

Options:
  --target <agent>  claude-code | codex | cursor | opencode | copilot | agents
  --user            Install for your user, across all projects (default).
  --project         Install into the current directory's project config.
  --dest DIR        Copy into DIR instead of a resolved agent path.
  --list            Print the resolved destination for every target and exit.
  --dry-run         Print what would be copied without copying it.
  -h, --help        This text.

Destinations (verified against vendor docs, 2026):
  claude-code  user ~/.claude/skills            project ./.claude/skills
  codex        user ~/.agents/skills            project ./.agents/skills
               (~/.codex/skills is still scanned but is the deprecated path)
  cursor       user ~/.cursor/skills            project ./.cursor/skills
  opencode     user ~/.config/opencode/skills   project ./.opencode/skills
               (UNVERIFIED EDGE: some opencode builds only load the singular
                'skill/' directory - if the skills do not appear, re-run with
                --dest ~/.config/opencode/skill)
  copilot      user ~/.copilot/skills           project ./.github/skills
  agents       user ~/.agents/skills            project ./.agents/skills
               (cross-agent convention read by Codex, Cursor, opencode and
                Copilot; Claude Code does not read it)

Project scope installs into the current working directory, not into this repo.
EOF
}

resolve() {
    # resolve <target> <scope>
    config_home=${XDG_CONFIG_HOME:-$HOME/.config}
    case "$1:$2" in
        claude-code:user)    echo "$HOME/.claude/skills" ;;
        claude-code:project) echo "$PWD/.claude/skills" ;;
        codex:user)          echo "$HOME/.agents/skills" ;;
        codex:project)       echo "$PWD/.agents/skills" ;;
        cursor:user)         echo "$HOME/.cursor/skills" ;;
        cursor:project)      echo "$PWD/.cursor/skills" ;;
        opencode:user)       echo "$config_home/opencode/skills" ;;
        opencode:project)    echo "$PWD/.opencode/skills" ;;
        copilot:user)        echo "$HOME/.copilot/skills" ;;
        copilot:project)     echo "$PWD/.github/skills" ;;
        agents:user)         echo "$HOME/.agents/skills" ;;
        agents:project)      echo "$PWD/.agents/skills" ;;
        *) echo "install.sh: unknown target '$1'" >&2; exit 2 ;;
    esac
}

skills() {
    for skill_md in "$ROOT"/*/SKILL.md; do
        [ -f "$skill_md" ] || continue
        dir=$(dirname -- "$skill_md")
        case $(basename -- "$dir") in .*) continue ;; esac
        echo "$dir"
    done
}

while [ $# -gt 0 ]; do
    case "$1" in
        --target) [ $# -ge 2 ] || { echo "install.sh: --target needs a value" >&2; exit 2; }
                  TARGET=$2; shift 2 ;;
        --target=*) TARGET=${1#--target=}; shift ;;
        --dest)   [ $# -ge 2 ] || { echo "install.sh: --dest needs a value" >&2; exit 2; }
                  DEST=$2; shift 2 ;;
        --dest=*) DEST=${1#--dest=}; shift ;;
        --user)    SCOPE=user; shift ;;
        --project) SCOPE=project; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --list)    LIST=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "install.sh: unknown argument '$1'" >&2; usage >&2; exit 2 ;;
    esac
done

count=$(skills | wc -l | tr -d ' ')
if [ "$count" -eq 0 ]; then
    echo "install.sh: no skills found - expected <skill-name>/SKILL.md under $ROOT" >&2
    exit 1
fi

if [ "$LIST" -eq 1 ]; then
    echo "source: $ROOT ($count skills)"
    skills | while read -r dir; do echo "  $(basename -- "$dir")"; done
    echo
    echo "destinations:"
    for t in claude-code codex cursor opencode copilot agents; do
        printf '  %-12s user     %s\n' "$t" "$(resolve "$t" user)"
        printf '  %-12s project  %s\n' "$t" "$(resolve "$t" project)"
    done
    exit 0
fi

if [ -z "$TARGET" ] && [ -z "$DEST" ]; then
    echo "install.sh: --target is required (or --dest DIR)" >&2
    echo >&2
    usage >&2
    exit 2
fi

if [ -n "$DEST" ]; then
    destination=$DEST
else
    destination=$(resolve "$TARGET" "$SCOPE")
fi

echo "installing $count skills"
echo "  from  $ROOT"
echo "  into  $destination"
if [ "$DRY_RUN" -eq 1 ]; then
    echo "  (dry run - nothing will be written)"
fi
echo

if [ "$DRY_RUN" -eq 0 ]; then
    mkdir -p "$destination"
fi

skills | while read -r dir; do
    name=$(basename -- "$dir")
    if [ -e "$destination/$name" ]; then
        action="replace"
    else
        action="copy   "
    fi
    echo "  $action $name/"
    if [ "$DRY_RUN" -eq 0 ]; then
        rm -rf -- "$destination/$name"
        cp -R -- "$dir" "$destination/$name"
    fi
done

echo
if [ "$DRY_RUN" -eq 1 ]; then
    echo "dry run complete - no files written"
else
    echo "installed $count skills into $destination"
fi
