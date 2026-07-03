"""Tests for the identity pack -- the interview layer (layer 0).

Runs against a throwaway CLAUDE_HOME. The interview is driven via --write (JSON on
stdin), the mode Claude uses in teach mode. The live identity-probe step (claude
-p) isn't exercised here -- it's the one behavioural check, like memory's recall.

    python -m pytest tests/test_identity_pack.py -q
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FILES = REPO / "packs" / "identity" / "files"
MEM = REPO / "packs" / "memory" / "files"
sys.path.insert(0, str(REPO))

from runner.verify import load_pack  # noqa: E402

PAYLOAD = json.dumps(
    {
        "name": "Jane", "role": "trader", "technical_level": "not a developer",
        "communication_style": "plain, concrete, one recommendation not menus",
        "building": "a personal butler", "priorities": ["ship X", "learn Y"],
        "environment": "Windows 11 + PowerShell", "timezone": "Australia/Sydney",
    }
)


def run(files: Path, script: str, *args: str, home: Path, stdin=None):
    env = dict(os.environ, CLAUDE_HOME=str(home))
    return subprocess.run(
        [sys.executable, str(files / script), *args],
        input=stdin, capture_output=True, text=True, env=env, encoding="utf-8",
    )


def test_write_creates_context_files(tmp_path):
    r = run(FILES, "setup_identity.py", "--write", home=tmp_path, stdin=PAYLOAD)
    assert r.returncode == 0
    ctx = tmp_path / "context"
    for f in ("me.md", "work.md", "current_priorities.md"):
        assert (ctx / f).exists(), f"missing {f}"
    assert "Jane" in (ctx / "me.md").read_text(encoding="utf-8")


def test_write_requires_a_name(tmp_path):
    r = run(FILES, "setup_identity.py", "--write", home=tmp_path, stdin=json.dumps({"role": "x"}))
    assert r.returncode != 0


def test_check_red_then_green(tmp_path):
    assert run(FILES, "setup_identity.py", "--check", home=tmp_path).returncode == 1
    run(FILES, "setup_identity.py", "--write", home=tmp_path, stdin=PAYLOAD)
    assert run(FILES, "setup_identity.py", "--check", home=tmp_path).returncode == 0


def test_link_memory_requires_memory_first(tmp_path):
    run(FILES, "setup_identity.py", "--write", home=tmp_path, stdin=PAYLOAD)
    r = run(FILES, "setup_identity.py", "--link-memory", home=tmp_path)
    assert r.returncode == 1 and "memory" in r.stdout


def test_link_memory_then_doctor_stays_healthy(tmp_path):
    run(MEM, "setup_memory.py", home=tmp_path)
    run(FILES, "setup_identity.py", "--write", home=tmp_path, stdin=PAYLOAD)
    assert run(FILES, "setup_identity.py", "--link-memory", home=tmp_path).returncode == 0
    assert run(FILES, "setup_identity.py", "--check-memory", home=tmp_path).returncode == 0
    assert (tmp_path / "memory" / "user_profile.md").exists()
    r = run(MEM, "memory_doctor.py", home=tmp_path)  # user_profile must be reachable
    assert r.returncode == 0 and "HEALTHY" in r.stdout


def test_wire_and_check_wire(tmp_path):
    run(FILES, "setup_identity.py", "--write", home=tmp_path, stdin=PAYLOAD)
    assert run(FILES, "setup_identity.py", "--check-wire", home=tmp_path).returncode == 1
    assert run(FILES, "setup_identity.py", "--wire", home=tmp_path).returncode == 0
    assert run(FILES, "setup_identity.py", "--check-wire", home=tmp_path).returncode == 0
    assert "context/me.md" in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")


def test_link_memory_refuses_when_ambiguous(tmp_path):
    for name in ("C--Users-x-brain", "C--Users-x-ClaudeCode"):
        d = tmp_path / "projects" / name / "memory"
        d.mkdir(parents=True)
        (d / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
    run(FILES, "setup_identity.py", "--write", home=tmp_path, stdin=PAYLOAD)
    r = run(FILES, "setup_identity.py", "--link-memory", home=tmp_path)
    assert r.returncode != 0 and "AMBIGUOUS" in r.stdout


def test_pack_loads_with_four_steps():
    pack = load_pack(REPO / "packs" / "identity" / "pack.yaml")
    assert pack.name == "identity"
    assert [s.id for s in pack.steps] == [
        "context", "profile-memory", "wired-to-constitution", "identity-probe",
    ]
