"""Tests for the autolearn pack -- capture commits + file lessons into memory.

Uses a throwaway git repo and CLAUDE_HOME. The headless --drain (real `claude -p`)
isn't exercised; its write path is covered via --write-learning + --selftest.

    python -m pytest tests/test_autolearn_pack.py -q
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "packs" / "autolearn" / "files" / "phantom_autolearn.py"
MEM = REPO / "packs" / "memory" / "files"
sys.path.insert(0, str(REPO))

from runner.verify import load_pack  # noqa: E402


def run(*args, home, cwd=None, stdin=None):
    env = dict(os.environ, CLAUDE_HOME=str(home))
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd, input=stdin, capture_output=True, text=True, env=env, encoding="utf-8",
    )


def git_repo(tmp_path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    def g(*a):
        return subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True)

    g("init", "-q")
    g("config", "user.email", "t@example.test")
    g("config", "user.name", "t")
    (repo / "f.txt").write_text("hi", encoding="utf-8")
    g("add", "-A")
    g("commit", "-q", "-m", "initial commit: add f")
    return repo


def setup_memory(home):
    subprocess.run(
        [sys.executable, str(MEM / "setup_memory.py")],
        env=dict(os.environ, CLAUDE_HOME=str(home)), capture_output=True, text=True,
    )


def doctor(home):
    return subprocess.run(
        [sys.executable, str(MEM / "memory_doctor.py")],
        env=dict(os.environ, CLAUDE_HOME=str(home)), capture_output=True, text=True, encoding="utf-8",
    )


# --- hook -------------------------------------------------------------------


def test_install_and_check_hook(tmp_path):
    repo = git_repo(tmp_path)
    assert run("--check-hook", home=tmp_path, cwd=repo).returncode == 1
    assert run("--install-hook", home=tmp_path, cwd=repo).returncode == 0
    assert run("--check-hook", home=tmp_path, cwd=repo).returncode == 0
    assert (repo / ".git" / "hooks" / "post-commit").exists()


def test_install_hook_outside_repo_fails(tmp_path):
    (tmp_path / "notrepo").mkdir()
    assert run("--install-hook", home=tmp_path, cwd=tmp_path / "notrepo").returncode == 1


# --- queue ------------------------------------------------------------------


def test_capture_show_and_clear_queue(tmp_path):
    repo = git_repo(tmp_path)
    assert run("--capture", home=tmp_path, cwd=repo).returncode == 0
    q = tmp_path / "autolearn_queue.jsonl"
    assert q.exists()

    data = json.loads(run("--show-queue", home=tmp_path, cwd=repo).stdout)
    assert data["count"] == 1
    assert "initial commit" in data["commits"][0]["subject"]

    assert run("--clear-queue", home=tmp_path, cwd=repo).returncode == 0
    assert not q.exists()


# --- apply a learning -------------------------------------------------------


def test_write_learning_files_into_memory_and_doctor_healthy(tmp_path):
    setup_memory(tmp_path)
    learning = json.dumps(
        {"should_write": True, "type": "feedback", "name": "test-lesson",
         "description": "when you're about to X", "body": "do Y",
         "resolver_intent": "when you're about to X"}
    )
    r = run("--write-learning", home=tmp_path, stdin=learning)
    assert r.returncode == 0
    mem = tmp_path / "memory"
    assert (mem / "feedback_test-lesson.md").exists()
    assert "test-lesson" in (mem / "MEMORY.md").read_text(encoding="utf-8")
    d = doctor(tmp_path)  # the filed lesson must be reachable
    assert d.returncode == 0 and "HEALTHY" in d.stdout


def test_write_learning_should_write_false_files_nothing(tmp_path):
    setup_memory(tmp_path)
    r = run("--write-learning", home=tmp_path, stdin=json.dumps({"should_write": False, "name": "x"}))
    assert r.returncode == 0
    assert "nothing filed" in r.stdout
    assert not (tmp_path / "memory" / "feedback_x.md").exists()


def _good_learning(**over):
    base = {"should_write": True, "type": "feedback", "name": "a-good-lesson",
            "description": "when you're about to X", "body": "do Y. **Why:** Z. **How to apply:** W."}
    base.update(over)
    return json.dumps(base)


def test_gate_blocks_a_credential_in_the_body(tmp_path):
    setup_memory(tmp_path)
    r = run("--write-learning", home=tmp_path,
            stdin=_good_learning(body="use this key: sk-ant-abcdef123456789 to auth"))
    assert r.returncode == 4 and "credential" in r.stdout.lower()
    assert not (tmp_path / "memory" / "feedback_a-good-lesson.md").exists()


def test_gate_blocks_oversized_body(tmp_path):
    setup_memory(tmp_path)
    big = "\n".join(f"line {i}" for i in range(60))
    r = run("--write-learning", home=tmp_path, stdin=_good_learning(body=big))
    assert r.returncode == 4 and "too long" in r.stdout


def test_gate_blocks_placeholder_body(tmp_path):
    setup_memory(tmp_path)
    r = run("--write-learning", home=tmp_path, stdin=_good_learning(body="(add the lesson)"))
    assert r.returncode == 4


def test_gate_blocks_duplicate_slug(tmp_path):
    setup_memory(tmp_path)
    assert run("--write-learning", home=tmp_path, stdin=_good_learning()).returncode == 0
    r = run("--write-learning", home=tmp_path, stdin=_good_learning())  # again, same name
    assert r.returncode == 4 and "already exists" in r.stdout


def test_gate_blocks_unbalanced_fences(tmp_path):
    setup_memory(tmp_path)
    r = run("--write-learning", home=tmp_path, stdin=_good_learning(body="do X\n```\nunclosed"))
    assert r.returncode == 4 and "fence" in r.stdout


def test_validate_mode_passes_a_good_learning(tmp_path):
    setup_memory(tmp_path)
    r = run("--validate", home=tmp_path, stdin=_good_learning())
    assert r.returncode == 0 and "OK" in r.stdout
    assert not (tmp_path / "memory" / "feedback_a-good-lesson.md").exists()  # dry run: no write


def test_gate_does_not_block_a_normal_lesson(tmp_path):
    # regression: the kind of lesson we actually file must sail through
    setup_memory(tmp_path)
    r = run("--write-learning", home=tmp_path, stdin=json.dumps(
        {"should_write": True, "type": "feedback", "name": "fail-loud-on-ambiguity",
         "description": "when you're about to auto-resolve a lookup with more than one match",
         "body": "If a tool finds >1 candidate, refuse to guess -- list all, exit non-zero, name the pin. "
                 "**Why:** silent guessing yields false 'it's fine' verdicts. **How to apply:** on len>1, "
                 "print all and require an explicit pin."}))
    assert r.returncode == 0


def test_write_learning_requires_memory(tmp_path):
    r = run("--write-learning", home=tmp_path, stdin=json.dumps({"should_write": True, "name": "x", "body": "y"}))
    assert r.returncode == 1 and "no memory" in r.stdout


def test_write_learning_refuses_when_ambiguous(tmp_path):
    for name in ("C--a", "C--b"):
        d = tmp_path / "projects" / name / "memory"
        d.mkdir(parents=True)
        (d / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
    r = run("--write-learning", home=tmp_path, stdin=json.dumps({"should_write": True, "name": "x", "body": "y"}))
    assert r.returncode != 0 and "AMBIGUOUS" in r.stdout


# --- selftest + pack --------------------------------------------------------


def test_selftest_passes(tmp_path):
    assert run("--selftest", home=tmp_path).returncode == 0


def _queue_n(tmp_path, n: int):
    q = tmp_path / "autolearn_queue.jsonl"
    q.write_text("".join(json.dumps({"sha": str(i), "subject": f"c{i}"}) + "\n" for i in range(n)),
                 encoding="utf-8")


def test_drain_due_false_below_threshold_true_at(tmp_path):
    _queue_n(tmp_path, 4)  # default threshold 5
    assert run("--drain-due", home=tmp_path).returncode == 1
    _queue_n(tmp_path, 5)
    assert run("--drain-due", home=tmp_path).returncode == 0


def test_drain_due_respects_env_threshold(tmp_path):
    _queue_n(tmp_path, 2)
    env = dict(os.environ, CLAUDE_HOME=str(tmp_path), AUTOLEARN_DRAIN_THRESHOLD="2")
    r = subprocess.run([sys.executable, str(SCRIPT), "--drain-due"],
                       capture_output=True, text=True, env=env, encoding="utf-8")
    assert r.returncode == 0


def test_queue_depth_reports_count(tmp_path):
    _queue_n(tmp_path, 3)
    r = run("--queue-depth", home=tmp_path)
    assert r.returncode == 0 and "queue depth: 3" in r.stdout


def test_nudge_silent_below_threshold(tmp_path):
    _queue_n(tmp_path, 2)
    r = run("--nudge", home=tmp_path)
    assert r.returncode == 1 and r.stdout.strip() == ""


def test_nudge_fires_when_deep_and_stale(tmp_path):
    _queue_n(tmp_path, 6)   # >= threshold, no last-drain stamp -> stale
    r = run("--nudge", home=tmp_path)
    assert r.returncode == 0 and "queued" in r.stdout


def test_nudge_silent_right_after_a_drain(tmp_path):
    _queue_n(tmp_path, 6)
    run("--clear-queue", home=tmp_path)   # stamps last-drain = now
    _queue_n(tmp_path, 6)                  # queue deep again immediately
    r = run("--nudge", home=tmp_path)      # but not stale -> stay quiet
    assert r.returncode == 1


def test_install_workflow_ships_the_guide(tmp_path):
    setup_memory(tmp_path)
    r = run("--install-workflow", home=tmp_path)
    assert r.returncode == 0
    dst = tmp_path / "memory" / "_phantom_workflow.md"
    assert dst.exists()
    # confirm the deep procedure landed, not an empty stub
    text = dst.read_text(encoding="utf-8")
    assert "The 6 stages" in text and "Worked examples" in text
    assert run("--check-workflow", home=tmp_path).returncode == 0


def test_install_workflow_refuses_when_ambiguous(tmp_path):
    for name in ("C--a", "C--b"):
        d = tmp_path / "projects" / name / "memory"
        d.mkdir(parents=True)
        (d / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
    r = run("--install-workflow", home=tmp_path)
    assert r.returncode != 0 and "AMBIGUOUS" in r.stdout


def test_pack_loads_with_four_steps():
    pack = load_pack(REPO / "packs" / "autolearn" / "pack.yaml")
    assert pack.name == "autolearn"
    assert [s.id for s in pack.steps] == [
        "memory-present", "workflow-installed", "hook-installed", "autolearn-works",
    ]
