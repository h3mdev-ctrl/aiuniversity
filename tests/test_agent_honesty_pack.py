"""Tests for the agent-honesty pack -- doc install + constitution wiring + the
deterministic phantom-claim linter.

Runs against a throwaway CLAUDE_HOME. The behavioural check is model-free: we lint
known phantom / evidenced / neutral text and assert the verdict, no live Claude
session needed.

    python -m pytest tests/test_agent_honesty_pack.py -q
"""

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FILES = REPO / "packs" / "agent-honesty" / "files"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(FILES))

from runner.verify import load_pack  # noqa: E402
import phantom_claim_lint as lint  # noqa: E402


def run(*args: str, home: Path):
    env = dict(os.environ, CLAUDE_HOME=str(home))
    return subprocess.run(
        [sys.executable, str(FILES / "setup_agent_honesty.py"), *args],
        capture_output=True, text=True, env=env, encoding="utf-8",
    )


# --- install & check --------------------------------------------------------


def test_install_writes_doc_and_wires_constitution(tmp_path):
    assert run(home=tmp_path).returncode == 0
    doc = tmp_path / "agent_honesty.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    for marker in ("## 1. no-phantom-done", "## 2. research-before-asserting",
                   "## 3. judge-to-spec", "## 4. no-vague-time-claims"):
        assert marker in text
    claude_md = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "agent-honesty-pointer:start" in claude_md


def test_check_modes_red_then_green(tmp_path):
    assert run("--check-doc", home=tmp_path).returncode == 1
    assert run("--check-wired", home=tmp_path).returncode == 1
    run(home=tmp_path)
    assert run("--check-doc", home=tmp_path).returncode == 0
    assert run("--check-wired", home=tmp_path).returncode == 0


def test_install_is_idempotent(tmp_path):
    run(home=tmp_path)
    run(home=tmp_path)  # second call must not duplicate the pointer block
    claude_md = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert claude_md.count("agent-honesty-pointer:start") == 1


def test_wiring_preserves_existing_constitution(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "CLAUDE.md").write_text("# My rules\n\nDo not touch prod.\n", encoding="utf-8")
    run(home=tmp_path)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Do not touch prod." in text            # user's content kept
    assert "agent-honesty-pointer:start" in text   # ours added


def test_test_linter_mode_passes_after_install(tmp_path):
    r = run("--test-linter", home=tmp_path)
    assert r.returncode == 0
    assert "flags unevidenced claims" in r.stdout


# --- the linter itself (deterministic) --------------------------------------


def test_linter_flags_phantom_side_effect():
    assert lint.lint("Done -- pushed the fix to main.")
    assert lint.lint("Logged the run into memory.")
    assert lint.lint("Saved your profile to the memory folder.")


def test_linter_flags_phantom_verification():
    assert lint.lint("All tests pass.")
    assert lint.lint("It works now.")


def test_linter_clears_evidenced_claims():
    assert not lint.lint("Pushed the fix (commit a1b2c3d, CI green).")
    assert not lint.lint("All tests pass -- ran pytest: 219 passed, 0 failed.")


def test_linter_ignores_future_tense_and_neutral():
    assert not lint.lint("I'll push once you confirm.")
    assert not lint.lint("Here's the plan for the refactor and the tradeoffs.")


def test_linter_cli_exit_codes(tmp_path):
    phantom = subprocess.run(
        [sys.executable, str(FILES / "phantom_claim_lint.py"), "--text", "Done -- pushed it."],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert phantom.returncode == 1
    clean = subprocess.run(
        [sys.executable, str(FILES / "phantom_claim_lint.py"), "--text",
         "Pushed it (commit a1b2c3d)."],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert clean.returncode == 0


# --- pack -------------------------------------------------------------------


def test_pack_loads_with_its_steps():
    pack = load_pack(REPO / "packs" / "agent-honesty" / "pack.yaml")
    assert pack.name == "agent-honesty"
    assert [s.id for s in pack.steps] == [
        "rules-installed", "wired-into-constitution",
        "phantom-claim-linter-fires", "enforcement-note",
    ]
