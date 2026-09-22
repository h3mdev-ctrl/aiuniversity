"""Tests for the recall-discipline pack -- doc install + constitution wiring.

Runs against a throwaway CLAUDE_HOME. All three guardrails are soft by design
(no mechanical linter), so this covers install/check/wire idempotency and the
pack's own step list, same shape as test_agent_honesty_pack.py minus the
linter-specific tests.

    python -m pytest tests/test_recall_discipline_pack.py -q
"""

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FILES = REPO / "packs" / "recall-discipline" / "files"
sys.path.insert(0, str(REPO))

from runner.verify import load_pack  # noqa: E402


def run(*args: str, home: Path):
    env = dict(os.environ, CLAUDE_HOME=str(home))
    return subprocess.run(
        [sys.executable, str(FILES / "setup_recall_discipline.py"), *args],
        capture_output=True, text=True, env=env, encoding="utf-8",
    )


# --- install & check --------------------------------------------------------


def test_install_writes_doc_and_wires_constitution(tmp_path):
    assert run(home=tmp_path).returncode == 0
    doc = tmp_path / "recall_discipline.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    for marker in ("## 1. recon-before-research", "## 2. consolidate-dont-accumulate",
                   "## 3. project-framing-is-a-signal"):
        assert marker in text
    claude_md = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "recall-discipline-pointer:start" in claude_md


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
    assert claude_md.count("recall-discipline-pointer:start") == 1


def test_wiring_preserves_existing_constitution(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "CLAUDE.md").write_text("# My rules\n\nDo not touch prod.\n", encoding="utf-8")
    run(home=tmp_path)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Do not touch prod." in text                 # user's content kept
    assert "recall-discipline-pointer:start" in text    # ours added


# --- pack -------------------------------------------------------------------


def test_pack_loads_with_its_steps():
    pack = load_pack(REPO / "packs" / "recall-discipline" / "pack.yaml")
    assert pack.name == "recall-discipline"
    assert [s.id for s in pack.steps] == [
        "rules-installed", "wired-into-constitution", "enforcement-note",
    ]
