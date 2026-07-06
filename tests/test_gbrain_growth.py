"""Lock the gbrain growth-path doc + the lean/eager cadence being offered as a CHOICE.

The pack must (a) ship the growth-path ladder so a user can see what building on the
hub becomes, and (b) present lean-vs-eager as a choice at install with the token cost
-- not silently default (that's the anti-gatekeeping rule applied to the cadence).

    python -m pytest tests/test_gbrain_growth.py -q
"""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GB = REPO / "packs" / "gbrain-windows"


def test_growth_path_ships_with_the_ladder():
    doc = GB / "files" / "gbrain_growth_path.md"
    assert doc.exists()
    t = doc.read_text(encoding="utf-8").lower()
    # the rungs a user climbs
    for rung in ("entity graph", "eager capture", "ingest", "code intelligence", "automation"):
        assert rung in t, f"growth path missing rung: {rung}"
    # the governing principle + its caveat (signal not noise)
    assert "more" in t and "useful" in t
    assert "signal" in t and "noise" in t


def test_growth_path_has_the_lean_vs_eager_cost_table():
    t = (GB / "files" / "gbrain_growth_path.md").read_text(encoding="utf-8").lower()
    assert "lean" in t and "eager" in t
    assert "token" in t
    assert "3-5x" in t or "3–5x" in t or "3-5×" in t or "3–5×" in t   # the relative multiple
    assert "off your claude token budget" in t   # honest: embedding is off-budget


def test_pack_step_offers_the_cadence_choice_not_a_silent_default():
    pack = (GB / "pack.yaml").read_text(encoding="utf-8").lower()
    # the usage-discipline step must present BOTH and say don't pick for them
    assert "lean" in pack and "eager" in pack
    assert "--install --eager" in pack
    assert "offers the user" in pack or "offer the user" in pack
    assert "don't default silently" in pack or "don't pick for them" in pack or "present the choice" in pack
