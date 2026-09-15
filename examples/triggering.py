"""One reader for "which skills fired", and the rules for which one *should* have.

Two manifest shapes exist and both have to be read. `record.py` originally wrote
`skill_triggered`: a single string or null. That silently drops the outcome this
eval most wants to see — arm B has all ten skills installed, so the wrong skill
firing, or three firing at once, is a real and interesting result, and a single
string reports the first of them as if it were the whole story. `record.py` now
also writes `skills_triggered`, the full list `run_arm.py` already detects.
Rows written before that change have only the string, so `fired_skills` accepts
either and no caller needs to know which one it got.

The intended skill per task is read from tasks.py, never a second copy of the
map — a duplicated map is a map that drifts.

Controls are the subtle case. There the correct behaviour is *not* to apply the
skill, and every skill has a "when to break the rules" section, so loading the
matching skill and then restraining yourself is a good outcome, and loading
nothing is also a good outcome. Only loading some unrelated skill is a failure.
Scoring a control's no-fire as a missed trigger would make the descriptions look
broken for behaving exactly as intended, so controls are kept out of the
recall denominator and reported on their own terms.
"""
from __future__ import annotations
import pathlib, sys

_ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT / "tasks"))
from tasks import BY_ID  # noqa: E402

# A skill load is required on positives and on traps. Traps count: the trap is
# answered correctly *by* the skill (it is the text that says "that is a
# workflow, not an agent"), so the intended skill firing is the wanted behaviour.
REQUIRED_KINDS = ("positive", "trap")

INTENDED = "intended"            # the task's skill fired, nothing else
INTENDED_PLUS = "intended+other" # it fired, and so did at least one other
WRONG = "wrong"                  # something fired, none of it the task's skill
NONE = "none"                    # nothing fired


def fired_skills(row: dict) -> list[str]:
    """Every skill this run loaded, from whichever field shape the row has."""
    many = row.get("skills_triggered")
    if isinstance(many, str):            # tolerate a hand-written single string
        many = [many]
    if isinstance(many, (list, tuple)):
        out = [str(s) for s in many if s]
        if out:
            return list(dict.fromkeys(out))
    one = row.get("skill_triggered")
    return [str(one)] if one else []


def any_fired(row: dict) -> bool:
    return bool(fired_skills(row))


def expected_skill(task_id: str) -> str:
    return BY_ID[task_id]["skill"]


def trigger_required(task_id: str) -> bool:
    return BY_ID[task_id]["kind"] in REQUIRED_KINDS


def classify_run(row: dict) -> str:
    """Which of the four triggering outcomes this run is. Kind-independent.

    The label describes what happened; whether it was *correct* depends on the
    task kind, which is `verdict`'s job. Keeping those apart is what lets a
    control's no-fire be reported as a pass without distorting the label counts.
    """
    want = expected_skill(row["task"])
    got = fired_skills(row)
    if not got:
        return NONE
    if want not in got:
        return WRONG
    return INTENDED if len(got) == 1 else INTENDED_PLUS


def verdict(task_id: str, label: str) -> str:
    """Was that the right triggering behaviour for this task kind?

    "allowed" on a control is not a dodge: the skill documents its own
    non-application, so reading it is defensible. Whether the agent then stayed
    restrained is a *score* question, and the score column answers it.
    """
    if trigger_required(task_id):
        return "yes" if label in (INTENDED, INTENDED_PLUS) else "no"
    if label == NONE:
        return "yes (none wanted)"
    if label == WRONG:
        return "no (unrelated skill)"
    return "allowed (control)"


def counts(rows: list[dict]) -> dict[str, int]:
    """Label histogram over a set of runs."""
    out = {INTENDED: 0, INTENDED_PLUS: 0, WRONG: 0, NONE: 0}
    for r in rows:
        out[classify_run(r)] += 1
    return out
