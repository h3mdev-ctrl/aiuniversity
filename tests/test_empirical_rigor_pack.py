"""Tests for the empirical-rigor pack -- doc install + constitution wiring.

Runs against a throwaway CLAUDE_HOME. All three guardrails are soft (no
mechanical linter, same as agent-honesty's research-before-asserting /
judge-to-spec) so there's no behavioural-check surface to test beyond
install/wiring, mirroring how those non-mechanical guardrails are covered.

    python -m pytest tests/test_empirical_rigor_pack.py -q
"""

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FILES = REPO / "packs" / "empirical-rigor" / "files"
sys.path.insert(0, str(REPO))

from runner.verify import load_pack  # noqa: E402


def run(*args: str, home: Path):
    env = dict(os.environ, CLAUDE_HOME=str(home))
    return subprocess.run(
        [sys.executable, str(FILES / "setup_empirical_rigor.py"), *args],
        capture_output=True, text=True, env=env, encoding="utf-8",
    )


# --- install & check --------------------------------------------------------


def test_install_writes_doc_and_wires_constitution(tmp_path):
    assert run(home=tmp_path).returncode == 0
    doc = tmp_path / "empirical_rigor.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    for marker in ("## 1. distribution-before-statistic",
                   "## 2. environment-parity-for-adhoc-runs",
                   "## 3. continuity-is-not-uptime"):
        assert marker in text
    claude_md = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "empirical-rigor-pointer:start" in claude_md


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
    assert claude_md.count("empirical-rigor-pointer:start") == 1


def test_wiring_preserves_existing_constitution(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "CLAUDE.md").write_text("# My rules\n\nDo not touch prod.\n", encoding="utf-8")
    run(home=tmp_path)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Do not touch prod." in text              # user's content kept
    assert "empirical-rigor-pointer:start" in text   # ours added


def test_wiring_coexists_with_agent_honesty_pointer(tmp_path):
    """The two sibling packs' pointer blocks must not clobber each other."""
    agent_honesty_files = REPO / "packs" / "agent-honesty" / "files"
    subprocess.run(
        [sys.executable, str(agent_honesty_files / "setup_agent_honesty.py")],
        capture_output=True, text=True,
        env=dict(os.environ, CLAUDE_HOME=str(tmp_path)), encoding="utf-8",
    )
    run(home=tmp_path)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "agent-honesty-pointer:start" in text
    assert "empirical-rigor-pointer:start" in text


# --- pack -------------------------------------------------------------------


def test_pack_loads_with_its_steps():
    pack = load_pack(REPO / "packs" / "empirical-rigor" / "pack.yaml")
    assert pack.name == "empirical-rigor"
    assert [s.id for s in pack.steps] == [
        "rules-installed", "wired-into-constitution",
    ]


def test_every_check_can_fail(tmp_path):
    # Each step's check must go RED on an empty CLAUDE_HOME -- a step that passes
    # where nothing is installed (the old soft-by-design-note, `exit(0)`) proves
    # nothing.
    import shlex
    pack = load_pack(REPO / "packs" / "empirical-rigor" / "pack.yaml")
    env = dict(os.environ, CLAUDE_HOME=str(tmp_path))
    for step in pack.steps:
        r = subprocess.run(shlex.split(step.check.cmd), cwd=REPO, env=env,
                           capture_output=True, text=True, encoding="utf-8")
        assert r.returncode != 0, f"{step.id} passes on an empty home"
