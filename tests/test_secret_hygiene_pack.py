"""secret-hygiene pack: the patterns work in BOTH directions, and the hook fires.

Two layers, deliberately:

  * the pattern list, tested directly -- positives redacted, negatives untouched
  * the pre-commit hook, driven through REAL `git commit` calls in a temp repo

The second layer is the one that matters. A pre-commit hook that passes its unit
tests and never actually fires is indistinguishable from a working one, and that
is the failure this pack exists to prevent.

Specimens are SYNTHETIC: correct shape, never real credentials.

    python -m pytest tests/test_secret_hygiene_pack.py -q
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FILES = REPO / "packs" / "secret-hygiene" / "files"
PATTERNS = FILES / "secret_patterns.py"
SETUP = FILES / "setup_secret_hygiene.py"

FAKE_TELEGRAM = "8112345678:AAF9zQ1x_pLmNbVcXsWq2rTyU3iOpAsDfGh"
FAKE_OPENAI = "sk-proj-AbCdEfGhIjKlMnOpQrStUvWx"


def _load():
    spec = importlib.util.spec_from_file_location("_secret_patterns", PATTERNS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def patterns():
    return _load()


def test_pack_files_exist():
    for f in (PATTERNS, SETUP, FILES / "secret_precommit.py"):
        assert f.is_file(), f"{f} missing"


@pytest.mark.parametrize("label,sample", [
    ("telegram in an API URL",
     f"curl https://api.telegram.org/bot{FAKE_TELEGRAM}/getMe"),
    ("openai key", f"export OPENAI_API_KEY={FAKE_OPENAI}"),
    ("aws access key", "AKIAIOSFODNN7EXAMPLE"),
    ("discord webhook",
     "https://discord.com/api/webhooks/1234567890/AbCdEfGhIjKlMnOpQrStUvWxYz"),
])
def test_positive_shapes_are_redacted(patterns, label, sample):
    out = patterns.redact(sample)
    assert "<redacted:" in out, f"{label} not redacted"
    # and the value itself must be gone, not merely annotated
    for token in (FAKE_TELEGRAM, FAKE_OPENAI, "AKIAIOSFODNN7EXAMPLE"):
        if token in sample:
            assert token not in out, f"{label}: raw value survived redaction"


@pytest.mark.parametrize("label,sample", [
    ("plain timestamp", "run at 20260828 and log it"),
    ("ratio with a colon", "sharpe 12345678:12 across the window"),
    ("prose containing 'key'",
     "giving every row a key and collapsing rows that share it"),
    ("a git sha", "commit 51467b4a9c3d2e1f0b8a7c6d5e4f3a2b1c0d9e8f"),
])
def test_negative_shapes_are_left_alone(patterns, label, sample):
    assert patterns.redact(sample) == sample, f"{label} was wrongly redacted"


def test_telegram_matches_after_letters_not_only_after_a_boundary(patterns):
    """Regression: the first draft used a leading \\b.

    `\\b` does not match between a letter and a digit, so `.../bot<token>` --
    the form the token actually appears in -- was missed entirely while the
    pattern looked correct. Pin the URL form specifically.
    """
    assert "<redacted:" in patterns.redact(f"api.telegram.org/bot{FAKE_TELEGRAM}/getMe")


def test_marker_is_correlatable_and_valueless(patterns):
    a = patterns.redact(f"one {FAKE_OPENAI} here")
    b = patterns.redact(f"two {FAKE_OPENAI} there")
    dig = patterns.digest(FAKE_OPENAI)
    assert dig in a and dig in b, "same secret must yield the same digest"
    assert FAKE_OPENAI not in a and FAKE_OPENAI not in b
    assert len(dig) == 12


def test_redaction_is_idempotent(patterns):
    once = patterns.redact(f"key {FAKE_OPENAI}")
    assert patterns.redact(once) == once, "re-redacting must not rewrite a marker"


def test_patterns_self_test_passes():
    r = subprocess.run([sys.executable, str(PATTERNS)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_precommit_hook_actually_blocks_a_real_commit(tmp_path):
    """Drive real `git commit` calls -- the only honest test of a git hook."""
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, CLAUDE_HOME=str(home))
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)

    r = subprocess.run([sys.executable, str(SETUP), str(repo)],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (repo / ".git" / "hooks" / "pre-commit").is_file()

    def commit(name: str, body: str, extra: list[str] | None = None) -> int:
        (repo / name).write_text(body, encoding="utf-8")
        subprocess.run(["git", "add", "-A", "-f"], cwd=repo, check=True, env=env)
        return subprocess.run(["git", "commit", "-q", "-m", "t"] + (extra or []),
                              cwd=repo, capture_output=True, text=True,
                              env=env).returncode

    assert commit("notes.md", "# just notes\n") == 0, "clean file should commit"
    assert commit("cfg.py", f'BOT = "{FAKE_TELEGRAM}"\n') != 0, \
        "a staged secret must be refused"
    # the escape hatch must keep working -- a guard nobody can escape gets removed
    assert commit("cfg.py", f'BOT = "{FAKE_TELEGRAM}"\n', ["--no-verify"]) == 0


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_setup_test_blocking_mode_reports_healthy(tmp_path):
    env = dict(os.environ, CLAUDE_HOME=str(tmp_path / "home"))
    subprocess.run([sys.executable, str(SETUP), "--files-only"],
                   capture_output=True, env=env)
    r = subprocess.run([sys.executable, str(SETUP), "--test-blocking"],
                       capture_output=True, text=True, env=env)
    assert "VERDICT: HEALTHY" in r.stdout, r.stdout + r.stderr


def test_drift_check_passes_when_there_is_no_second_list(tmp_path):
    """With no audit hook installed there is nothing to drift against."""
    env = dict(os.environ, CLAUDE_HOME=str(tmp_path / "home"))
    subprocess.run([sys.executable, str(SETUP), "--files-only"],
                   capture_output=True, env=env)
    r = subprocess.run([sys.executable, str(SETUP), "--check-drift"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout


def test_drift_check_FAILS_when_a_second_list_disagrees(tmp_path):
    """The control that proves the drift check is not vacuous.

    Without this, `--check-drift` passing means nothing -- it would pass just as
    happily if it never compared anything, which is exactly how the original
    all-clear was produced.
    """
    home = tmp_path / "home"
    (home / "hooks").mkdir(parents=True)
    env = dict(os.environ, CLAUDE_HOME=str(home))
    subprocess.run([sys.executable, str(SETUP), "--files-only"],
                   capture_output=True, env=env)
    # a second list that is missing a shape the canonical list has
    (home / "hooks" / "tool_audit_log.py").write_text(
        "import re\n_SECRET_PATTERNS = [('openai-key', re.compile(r'sk-'))]\n",
        encoding="utf-8")
    r = subprocess.run([sys.executable, str(SETUP), "--check-drift"],
                       capture_output=True, text=True, env=env)
    assert r.returncode != 0, "drift check must FAIL on a disagreeing second list"
    assert "DRIFTED" in r.stdout, r.stdout
