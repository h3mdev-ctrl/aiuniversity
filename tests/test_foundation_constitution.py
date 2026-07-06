"""Tests for the foundation constitution seeder + the gbrain hub model.

The constitution core (operating principle + skill routing) is the thing that stops
a newcomer's Claude improvising; the hub model is the thing that stops it framing
gbrain as a per-project notes app. Both are load-bearing teaching artifacts, so we
lock their presence + the seeder's install/check/idempotency on a throwaway home.

    python -m pytest tests/test_foundation_constitution.py -q
"""

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FOUND = REPO / "packs" / "foundation" / "files"
sys.path.insert(0, str(REPO))

from runner.verify import load_pack  # noqa: E402


def run(script_dir: Path, script: str, *args: str, home: Path):
    env = dict(os.environ, CLAUDE_HOME=str(home))
    return subprocess.run(
        [sys.executable, str(script_dir / script), *args],
        capture_output=True, text=True, env=env, encoding="utf-8",
    )


def test_check_red_then_install_then_green(tmp_path):
    assert run(FOUND, "setup_constitution.py", "--check", home=tmp_path).returncode == 1
    assert run(FOUND, "setup_constitution.py", "--install", home=tmp_path).returncode == 0
    assert run(FOUND, "setup_constitution.py", "--check", home=tmp_path).returncode == 0


def test_block_has_the_load_bearing_sections(tmp_path):
    run(FOUND, "setup_constitution.py", "--install", home=tmp_path)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "## Operating principle" in text
    assert "shoulders of giants" in text.lower()        # the ethos
    assert "verify" in text.lower() and "plan" in text.lower()
    assert "## Skill routing" in text
    assert "invoke" in text.lower() and "| Trigger | Skill |" in text  # the example table
    assert "gbrain_hub_model" in text                    # points at the mental model
    # present-the-choice / don't-defer (feedback_dont_reflex_defer, generalised)
    low = text.lower()
    assert "present decisions" in low or "don't pre-make" in low
    assert "gatekept" in low or "let the user choose" in low


def test_install_is_idempotent_and_preserves_existing(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# My rules\n\nrun on Windows\n", encoding="utf-8")
    run(FOUND, "setup_constitution.py", "--install", home=tmp_path)
    run(FOUND, "setup_constitution.py", "--install", home=tmp_path)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.count("<!-- constitution-core:start -->") == 1   # no duplication
    assert "run on Windows" in text                              # existing content survives


def test_gbrain_ships_hub_model_with_the_fix():
    doc = REPO / "packs" / "gbrain-windows" / "files" / "gbrain_hub_model.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8").lower()
    assert "hub" in text and "spoke" in text
    assert "mirror" in text                       # names the mistake to avoid
    assert "how is gbrain useful" in text or "explaining it to a newcomer" in text


def test_foundation_layer2_runs_the_seeder():
    pack = load_pack(REPO / "packs" / "foundation" / "pack.yaml")
    step = next(s for s in pack.steps if s.id == "layer-2-constitution")
    assert "setup_constitution.py --check" in step.check.cmd
