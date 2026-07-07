"""Tests for the recon-before-build guard -- 'read the existing code before you
build a parallel version of it' backstop.

Proves the guard (a) bounces the FIRST Write of a new source file into a repo that
already has source files, (b) is nudge-once (the second Write in the same session
passes), (c) ignores existing-file overwrites, doc files, and fresh/sparse dirs.
Plus the installer wiring, PreToolUse(Write) registration, coexistence with the
other guards, and the constitution principle.

    python -m pytest tests/test_recon_before_build_guard.py -q
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FILES = REPO / "packs" / "guardrails" / "files"
sys.path.insert(0, str(FILES))

import recon_before_build_guard as guard  # noqa: E402


def _payload(fp, session="s1"):
    return {"session_id": session, "tool_name": "Write",
            "tool_input": {"file_path": str(fp), "content": "x"}}


def _pipe(payload, home):
    env = dict(os.environ, CLAUDE_HOME=str(home))
    return subprocess.run([sys.executable, str(FILES / "recon_before_build_guard.py")],
                          input=json.dumps(payload), capture_output=True, text=True,
                          env=env, encoding="utf-8")


def _repo(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".git").mkdir()
    (tmp_path / "extract.py").write_text("# a\n")
    (tmp_path / "reconcile.py").write_text("# b\n")
    return tmp_path


def test_new_source_file_in_populated_repo_bounces(tmp_path):
    home = tmp_path / "home"
    repo = _repo(tmp_path / "repo")
    r = _pipe(_payload(repo / "crosscheck3.py"), home)
    assert r.returncode == 2
    assert "recon before build" in r.stderr.lower()


def test_nudge_is_once_per_session_per_repo(tmp_path):
    home = tmp_path / "home"
    repo = _repo(tmp_path / "repo")
    assert _pipe(_payload(repo / "crosscheck3.py"), home).returncode == 2   # first
    assert _pipe(_payload(repo / "another_new.py"), home).returncode == 0   # second: quiet


def test_existing_file_overwrite_passes(tmp_path):
    home = tmp_path / "home"
    repo = _repo(tmp_path / "repo")
    assert _pipe(_payload(repo / "extract.py"), home).returncode == 0


def test_doc_file_passes(tmp_path):
    home = tmp_path / "home"
    repo = _repo(tmp_path / "repo")
    assert _pipe(_payload(repo / "NOTES.md"), home).returncode == 0


def test_fresh_sparse_dir_passes(tmp_path):
    home = tmp_path / "home"
    repo = _repo(tmp_path / "repo")
    (repo / "fresh").mkdir()
    assert _pipe(_payload(repo / "fresh" / "brand_new.py"), home).returncode == 0


def run(script, *args, home):
    env = dict(os.environ, CLAUDE_HOME=str(home))
    return subprocess.run([sys.executable, str(FILES / script), *args],
                          capture_output=True, text=True, env=env, encoding="utf-8")


def test_install_check_and_behavioural_block(tmp_path):
    assert run("setup_recon_build_guard.py", "--check-hook-file", home=tmp_path).returncode == 1
    assert run("setup_recon_build_guard.py", "--install", home=tmp_path).returncode == 0
    assert run("setup_recon_build_guard.py", "--check-hook-file", home=tmp_path).returncode == 0
    assert run("setup_recon_build_guard.py", "--check-registered", home=tmp_path).returncode == 0
    r = run("setup_recon_build_guard.py", "--test-blocking", home=tmp_path)
    assert r.returncode == 0, r.stdout


def test_registered_as_pretooluse_write_hook(tmp_path):
    run("setup_recon_build_guard.py", "--install", home=tmp_path)
    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    pre = data["hooks"]["PreToolUse"]
    assert any("recon_before_build_guard.py" in h.get("command", "")
               for e in pre for h in e.get("hooks", []))
    assert any(e.get("matcher") == "Write" for e in pre)


def test_coexists_with_credential_and_session_guards(tmp_path):
    run("setup_recon_build_guard.py", "--install", home=tmp_path)
    run("setup_session_guard.py", "--install", home=tmp_path)
    cred = subprocess.run(
        [sys.executable, str(FILES / "setup_guardrails.py"), "--install"],
        capture_output=True, text=True, env=dict(os.environ, CLAUDE_HOME=str(tmp_path)),
        encoding="utf-8",
    )
    assert cred.returncode == 0
    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert data["hooks"].get("Stop") and data["hooks"].get("PreToolUse")
    # both PreToolUse guards present (credential + recon)
    cmds = [h.get("command", "") for e in data["hooks"]["PreToolUse"] for h in e.get("hooks", [])]
    assert any("credential_guard.py" in c for c in cmds)
    assert any("recon_before_build_guard.py" in c for c in cmds)


def test_constitution_seeds_the_recon_principle():
    import re
    raw = (REPO / "packs" / "foundation" / "files" / "setup_constitution.py").read_text(encoding="utf-8").lower()
    text = re.sub(r"\s+", " ", raw)
    assert "recon before build" in text
    assert "building first and reading later is reinventing" in text
