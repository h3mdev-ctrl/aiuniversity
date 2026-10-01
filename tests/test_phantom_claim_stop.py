"""Tests for the opt-in phantom-claim Stop-hook adapter and its installer.

The adapter exists because phantom_claim_lint.py lints TEXT while a Stop hook
receives JSON with a transcript_path. These tests pin: the reply it extracts is
the text after the last tool result (not one block, not the whole session); warn
mode never blocks; block mode exits 2; it never loops on stop_hook_active; it
fails open on anything unexpected; and the installer is idempotent and refuses a
settings.json it cannot parse.

    python -m pytest tests/test_phantom_claim_stop.py -q
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FILES = REPO / "packs" / "agent-honesty" / "files"
ADAPTER = FILES / "phantom_claim_stop.py"
SETUP = FILES / "setup_agent_honesty.py"

PHANTOM = "Done -- pushed the fix to main."
EVIDENCED = "Pushed the fix (commit a1b2c3d, CI green)."


def _load_adapter():
    spec = importlib.util.spec_from_file_location("phantom_claim_stop_t", ADAPTER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def transcript(tmp_path, entries):
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return p


def user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def tool_result():
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "x", "content": "ok"}]}}


def assistant(*texts, tool=False, sidechain=False):
    content = [{"type": "text", "text": t} for t in texts]
    if tool:
        content.append({"type": "tool_use", "id": "x", "name": "Bash", "input": {}})
    e = {"type": "assistant", "message": {"role": "assistant", "content": content}}
    if sidechain:
        e["isSidechain"] = True
    return e


def run(payload, tmp_path, mode="warn", **env_extra):
    env = dict(os.environ, PHANTOM_STOP_MODE=mode, CLAUDE_HOME=str(tmp_path / "home"))
    env.pop("PHANTOM_STOP_DISABLE", None)
    env.update(env_extra)
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, str(ADAPTER)], input=stdin, capture_output=True,
                          text=True, encoding="utf-8", env=env, timeout=30)


# --- what counts as the reply ---------------------------------------------------


def test_reply_is_the_text_after_the_last_tool_result(tmp_path):
    t = transcript(tmp_path, [
        user("ship it"),
        assistant("Checking the branch first.", tool=True),
        tool_result(),
        # Claude Code often writes each content block as its OWN transcript entry,
        # so the reply spans entries. Taking only the last block/entry (what the
        # old stop_phrase_guard did) would miss "Done -- pushed ..." here.
        assistant("Done -- pushed the fix to main."),
        assistant("Anything else you want changed?"),
    ])
    reply = _load_adapter().final_reply_text(str(t))
    assert reply == "Done -- pushed the fix to main.\nAnything else you want changed?"
    assert "Checking the branch" not in reply


def test_old_evidence_does_not_clear_a_fresh_claim(tmp_path):
    # A SHA shown before the last tool call must not launder the final claim.
    t = transcript(tmp_path, [
        user("ship it"),
        assistant("Earlier: commit a1b2c3d.", tool=True),
        tool_result(),
        assistant(PHANTOM),
    ])
    assert run({"transcript_path": str(t)}, tmp_path, mode="block").returncode == 2


def test_sidechain_text_is_ignored(tmp_path):
    t = transcript(tmp_path, [user("go"), assistant("Sure."), assistant(PHANTOM, sidechain=True)])
    assert _load_adapter().final_reply_text(str(t)) == "Sure."


# --- modes ----------------------------------------------------------------------


def test_block_mode_exits_2_with_a_reason(tmp_path):
    t = transcript(tmp_path, [user("go"), assistant(PHANTOM)])
    r = run({"transcript_path": str(t)}, tmp_path, mode="block")
    assert r.returncode == 2 and "no-phantom-done" in r.stderr and "pushed" in r.stderr


def test_warn_mode_never_blocks_and_tells_the_user(tmp_path):
    t = transcript(tmp_path, [user("go"), assistant(PHANTOM)])
    r = run({"transcript_path": str(t)}, tmp_path, mode="warn")
    assert r.returncode == 0
    assert json.loads(r.stdout)["systemMessage"].startswith("phantom-claim (warn)")


def test_warn_is_the_default(tmp_path):
    t = transcript(tmp_path, [user("go"), assistant(PHANTOM)])
    env = dict(os.environ, CLAUDE_HOME=str(tmp_path / "home"))
    env.pop("PHANTOM_STOP_MODE", None)
    r = subprocess.run([sys.executable, str(ADAPTER)], input=json.dumps({"transcript_path": str(t)}),
                       capture_output=True, text=True, encoding="utf-8", env=env, timeout=30)
    assert r.returncode == 0 and "phantom-claim (warn)" in r.stdout


def test_every_flag_is_logged_for_precision(tmp_path):
    t = transcript(tmp_path, [user("go"), assistant(PHANTOM)])
    run({"transcript_path": str(t), "session_id": "s1"}, tmp_path, mode="warn")
    log = tmp_path / "home" / "state" / "phantom_claim_stop.jsonl"
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1 and rows[0]["session_id"] == "s1" and rows[0]["findings"]


def test_evidenced_claim_is_silent(tmp_path):
    t = transcript(tmp_path, [user("go"), assistant(EVIDENCED)])
    r = run({"transcript_path": str(t)}, tmp_path, mode="block")
    assert r.returncode == 0 and r.stdout == ""


def test_never_loops_when_stop_hook_active(tmp_path):
    t = transcript(tmp_path, [user("go"), assistant(PHANTOM)])
    assert run({"transcript_path": str(t), "stop_hook_active": True},
               tmp_path, mode="block").returncode == 0


def test_disable_switch(tmp_path):
    t = transcript(tmp_path, [user("go"), assistant(PHANTOM)])
    assert run({"transcript_path": str(t)}, tmp_path, mode="block",
               PHANTOM_STOP_DISABLE="1").returncode == 0


@pytest.mark.parametrize("payload", ["", "not json", "null", "42", "[]",
                                     '{"transcript_path": "C:/nope/missing.jsonl"}'])
def test_fails_open_on_anything_unexpected(tmp_path, payload):
    assert run(payload, tmp_path, mode="block").returncode == 0


# --- installer ------------------------------------------------------------------


def setup(home, *args):
    env = dict(os.environ, CLAUDE_HOME=str(home))
    return subprocess.run([sys.executable, str(SETUP), *args], capture_output=True,
                          text=True, encoding="utf-8", env=env, timeout=60)


def stop_cmds(home):
    data = json.loads((home / "settings.json").read_text(encoding="utf-8"))
    return [h["hooks"][0]["command"] for h in data["hooks"]["Stop"]]


def test_installer_is_idempotent_and_keeps_other_hooks(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"hooks": {"Stop": [
        {"hooks": [{"type": "command", "command": "python other_guard.py"}]}]}}), encoding="utf-8")
    assert setup(tmp_path, "--check-stop-hook").returncode == 1        # red before
    assert setup(tmp_path, "--install-stop-hook").returncode == 0
    assert setup(tmp_path, "--install-stop-hook").returncode == 0
    cmds = stop_cmds(tmp_path)
    assert len(cmds) == 2 and "other_guard.py" in cmds[0]
    assert sum("phantom_claim_stop.py" in c for c in cmds) == 1
    r = setup(tmp_path, "--check-stop-hook")                            # green after
    assert r.returncode == 0 and "5/5" in r.stdout, r.stdout


def test_installer_refuses_unparseable_settings(tmp_path):
    (tmp_path / "settings.json").write_text("{bad", encoding="utf-8")
    r = setup(tmp_path, "--install-stop-hook")
    assert r.returncode == 1 and "refusing" in r.stdout
    assert (tmp_path / "settings.json").read_text(encoding="utf-8") == "{bad"


def test_check_goes_red_if_the_adapter_misbehaves(tmp_path):
    setup(tmp_path, "--install-stop-hook")
    adapter = tmp_path / "hooks" / "agent_honesty" / "phantom_claim_stop.py"
    adapter.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")  # a do-nothing hook
    r = setup(tmp_path, "--check-stop-hook")
    assert r.returncode == 1 and "FAIL" in r.stdout
