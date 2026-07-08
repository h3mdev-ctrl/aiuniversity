"""Tests for the windows-shell pack -- general Windows shell-hardening footguns.

The steps shell out to real executables (python / pwsh) and depend on the host
environment, so we don't run them here. What we prove structurally: the pack loads
and validates, it targets the three known traps, and -- because it's a footgun pack
-- every step ships a prescribed fix (on_fail) so a red check never dead-ends.

    python -m pytest tests/test_windows_shell_pack.py -q
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from runner.verify import load_pack  # noqa: E402

PACK = REPO / "packs" / "windows-shell"


def test_pack_loads_and_validates():
    pack = load_pack(PACK / "pack.yaml")
    assert pack.name == "windows-shell"
    # a general shell pack has no local/hosted split
    assert pack.variants == []


def test_targets_the_three_traps():
    ids = [s.id for s in load_pack(PACK / "pack.yaml").steps]
    assert ids == ["python-utf8", "python-https", "powershell-utf8-safe"]


def test_every_step_hands_over_a_fix():
    # a footgun pack must never leave a red check without a prescribed fix
    for step in load_pack(PACK / "pack.yaml").steps:
        assert step.on_fail and step.on_fail.strip(), f"{step.id} has no on_fail"


def test_readme_and_gotchas_ship():
    assert (PACK / "README.md").exists()
    assert (PACK / "files" / "windows_gotchas.md").exists()
