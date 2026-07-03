"""Tests for the guardrails pack -- install + registered + actually blocks.

Runs against a throwaway CLAUDE_HOME. The behavioural check is deterministic --
we pipe forbidden and allowed inputs through the installed hook and confirm the
right verdict, no live Claude session needed.

    python -m pytest tests/test_guardrails_pack.py -q
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FILES = REPO / "packs" / "guardrails" / "files"
sys.path.insert(0, str(REPO))

from runner.verify import load_pack  # noqa: E402


def run(script: str, *args: str, home: Path, stdin=None):
    env = dict(os.environ, CLAUDE_HOME=str(home))
    return subprocess.run(
        [sys.executable, str(FILES / script), *args],
        input=stdin, capture_output=True, text=True, env=env, encoding="utf-8",
    )


def pipe_guard(home: Path, payload: dict, bypass: bool = False):
    hook = home / "hooks" / "credential_guard.py"
    env = dict(os.environ, CLAUDE_HOME=str(home))
    if bypass:
        env["CLAUDE_CRED_GUARD"] = "off"
    return subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps(payload), capture_output=True, text=True, env=env, encoding="utf-8",
    )


# --- install & check --------------------------------------------------------


def test_install_creates_hook_file_and_registers(tmp_path):
    assert run("setup_guardrails.py", home=tmp_path).returncode == 0
    assert (tmp_path / "hooks" / "credential_guard.py").exists()
    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    entries = data["hooks"]["PreToolUse"]
    assert any("credential_guard.py" in h.get("command", "")
               for e in entries for h in e.get("hooks", []))


def test_check_modes_red_then_green(tmp_path):
    assert run("setup_guardrails.py", "--check-hook-file", home=tmp_path).returncode == 1
    assert run("setup_guardrails.py", "--check-registered", home=tmp_path).returncode == 1
    run("setup_guardrails.py", home=tmp_path)
    assert run("setup_guardrails.py", "--check-hook-file", home=tmp_path).returncode == 0
    assert run("setup_guardrails.py", "--check-registered", home=tmp_path).returncode == 0


def test_install_is_idempotent(tmp_path):
    run("setup_guardrails.py", home=tmp_path)
    run("setup_guardrails.py", home=tmp_path)   # second call must not duplicate
    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    entries = [h for e in data["hooks"]["PreToolUse"] for h in e.get("hooks", [])
               if "credential_guard.py" in h.get("command", "")]
    assert len(entries) == 1


def test_settings_merge_preserves_existing_hooks(tmp_path):
    prior = {"hooks": {"PreToolUse": [{"matcher": "Bash",
             "hooks": [{"type": "command", "command": "echo other-hook"}]}]}}
    (tmp_path).mkdir(parents=True, exist_ok=True)
    (tmp_path / "settings.json").write_text(json.dumps(prior), encoding="utf-8")
    run("setup_guardrails.py", home=tmp_path)
    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    cmds = [h["command"] for e in data["hooks"]["PreToolUse"] for h in e.get("hooks", [])]
    assert any("echo other-hook" in c for c in cmds)          # user's hook kept
    assert any("credential_guard.py" in c for c in cmds)      # ours added


# --- behavioural: the guard actually blocks ---------------------------------


def test_guard_blocks_read_of_dotenv(tmp_path):
    run("setup_guardrails.py", home=tmp_path)
    r = pipe_guard(tmp_path, {"tool_name": "Read", "tool_input": {"file_path": "/x/.env"}})
    assert r.returncode == 2 and "BLOCKED" in r.stderr


def test_guard_blocks_bash_cat_dotenv(tmp_path):
    run("setup_guardrails.py", home=tmp_path)
    r = pipe_guard(tmp_path, {"tool_name": "Bash", "tool_input": {"command": "cat .env && ls"}})
    assert r.returncode == 2 and "BLOCKED" in r.stderr


def test_guard_blocks_ssh_private_key(tmp_path):
    run("setup_guardrails.py", home=tmp_path)
    r = pipe_guard(tmp_path, {"tool_name": "Read", "tool_input": {"file_path": "~/.ssh/id_rsa"}})
    assert r.returncode == 2 and "BLOCKED" in r.stderr


def test_guard_allows_harmless_bash(tmp_path):
    run("setup_guardrails.py", home=tmp_path)
    r = pipe_guard(tmp_path, {"tool_name": "Bash", "tool_input": {"command": "ls -la"}})
    assert r.returncode == 0


def test_bypass_env_var_disables_guard(tmp_path):
    run("setup_guardrails.py", home=tmp_path)
    r = pipe_guard(tmp_path,
                   {"tool_name": "Read", "tool_input": {"file_path": "/x/.env"}},
                   bypass=True)
    assert r.returncode == 0   # explicit bypass


def test_test_blocking_mode_passes_after_install(tmp_path):
    run("setup_guardrails.py", home=tmp_path)
    r = run("setup_guardrails.py", "--test-blocking", home=tmp_path)
    assert r.returncode == 0
    assert "actually blocks" in r.stdout


# --- pack ------------------------------------------------------------------


def test_pack_loads_with_three_steps():
    pack = load_pack(REPO / "packs" / "guardrails" / "pack.yaml")
    assert pack.name == "guardrails"
    assert [s.id for s in pack.steps] == [
        "hook-installed", "registered-in-settings", "guard-actually-blocks",
    ]
