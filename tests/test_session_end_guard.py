"""Tests for the session-end guard -- the 'don't tell the user to stop' backstop.

Proves the guard (a) bounces a real sign-off, (b) does NOT bounce a phrase that only
appears QUOTED (in code / a blockquote -- the false-positive class we hit twice while
discussing the rule), and (c) lets a clean close through. Plus the installer wiring +
the constitution principle.

    python -m pytest tests/test_session_end_guard.py -q
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FILES = REPO / "packs" / "guardrails" / "files"
sys.path.insert(0, str(FILES))

import session_end_guard as guard  # noqa: E402


def test_prose_signoff_is_a_violation():
    assert guard.find_violations("Nice work. Good night, get some rest!")


def test_quoted_phrase_is_skipped():
    # inline code
    assert not guard.find_violations("The guard bans `good night` and `call it a day`.")
    # blockquote
    assert not guard.find_violations("> call it a day\n\nHere's the summary.")
    # fenced block
    assert not guard.find_violations("Banned list:\n```\ngood night\nsleep well\n```\nok.")
    # plain double-quoted prose (Jason's real-world false positive, 2026-07-07)
    assert not guard.find_violations('My last message quoted the phrases "good night" / "want to wrap up".')
    assert not guard.find_violations('the "good night" and "you\'ve done enough" sign-offs are banned')
    # curly double quotes (what markdown/smart-quotes render)
    assert not guard.find_violations("it flagged “good night” as a sign-off")


def test_single_quotes_are_NOT_stripped_apostrophe_safety():
    # contractions must survive -- a real prose sign-off with an apostrophe still fires
    assert guard.find_violations("You've done enough for today, good night!")


def test_clean_close_passes():
    assert not guard.find_violations("Shipped X; Y is now unblocked. Ready for the next one.")


def run(script, *args, home):
    env = dict(os.environ, CLAUDE_HOME=str(home))
    return subprocess.run([sys.executable, str(FILES / script), *args],
                          capture_output=True, text=True, env=env, encoding="utf-8")


def test_install_check_and_behavioural_block(tmp_path):
    assert run("setup_session_guard.py", "--check-hook-file", home=tmp_path).returncode == 1
    assert run("setup_session_guard.py", "--install", home=tmp_path).returncode == 0
    assert run("setup_session_guard.py", "--check-hook-file", home=tmp_path).returncode == 0
    assert run("setup_session_guard.py", "--check-registered", home=tmp_path).returncode == 0
    # the behavioural test covers prose-blocks / quoted-passes / clean-passes
    r = run("setup_session_guard.py", "--test-blocking", home=tmp_path)
    assert r.returncode == 0, r.stdout


def test_registered_as_stop_hook_not_pretooluse(tmp_path):
    run("setup_session_guard.py", "--install", home=tmp_path)
    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    stop = data["hooks"]["Stop"]
    assert any("session_end_guard.py" in h.get("command", "")
               for e in stop for h in e.get("hooks", []))


def test_coexists_with_credential_guard(tmp_path):
    # installing both guards must not clobber each other
    run("setup_session_guard.py", "--install", home=tmp_path)
    cred = subprocess.run(
        [sys.executable, str(FILES / "setup_guardrails.py"), "--install"],
        capture_output=True, text=True, env=dict(os.environ, CLAUDE_HOME=str(tmp_path)),
        encoding="utf-8",
    )
    assert cred.returncode == 0
    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert data["hooks"].get("Stop") and data["hooks"].get("PreToolUse")


def test_constitution_seeds_the_dont_stop_principle():
    import re
    raw = (REPO / "packs" / "foundation" / "files" / "setup_constitution.py").read_text(encoding="utf-8").lower()
    text = re.sub(r"\s+", " ", raw)   # collapse line-wraps so phrases match regardless of wrapping
    assert "don't tell the user when to stop" in text
    assert "get some rest" in text and "call it a day" in text
