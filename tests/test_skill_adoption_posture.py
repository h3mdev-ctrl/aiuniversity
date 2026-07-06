"""Lock the SKILL.md interaction rules that stop a recipient Claude from gatekeeping.

A real failure we saw: a newcomer's Claude, evaluating the packs against an existing
setup, pre-decided "SKIP for you / not worth it" instead of presenting pros/cons and
asking -- gatekeeping a user who, by installing, signalled they want to level up.
These assertions keep the corrective guidance present.

    python -m pytest tests/test_skill_adoption_posture.py -q
"""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = (REPO / "SKILL.md").read_text(encoding="utf-8").lower()


def test_skill_has_adoption_posture_section():
    assert "present the choice" in SKILL or "don't gatekeep" in SKILL


def test_names_the_level_up_frame():
    # installing the pack = wanting the upgrade; that's the frame
    assert "level up" in SKILL and "installed this pack" in SKILL


def test_says_ask_not_decide_for_them():
    assert "askuserquestion" in SKILL
    assert "pros/cons" in SKILL or "pros / cons" in SKILL


def test_caveat_is_a_migration_note_not_a_stop_sign():
    assert "migration note" in SKILL and "stop sign" in SKILL


def test_overlap_is_not_redundancy():
    assert "overlap is rarely redundancy" in SKILL or "overlap with an existing" in SKILL
