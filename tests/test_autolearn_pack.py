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


def test_write_learning_strips_doubled_type_prefix(tmp_path):
    # a model often names it 'feedback-foo'; the filename already prefixes the type,
    # so it must land as feedback_foo.md, NOT feedback_feedback-foo.md
    setup_memory(tmp_path)
    r = run("--write-learning", home=tmp_path, stdin=json.dumps(
        {"should_write": True, "type": "feedback", "name": "feedback-foo-bar",
         "description": "when you're about to X", "body": "do Y"}))
    assert r.returncode == 0
    mem = tmp_path / "memory"
    assert (mem / "feedback_foo-bar.md").exists()
    assert not (mem / "feedback_feedback-foo-bar.md").exists()


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


# --- unattended drain: gate + commit (no live model -- fake reflector) -------


def _git_init_memory(home) -> Path:
    """Make the discovered memory folder a git repo so commit-per-drain runs."""
    mem = home / "memory"

    def g(*a):
        return subprocess.run(["git", *a], cwd=mem, capture_output=True, text=True)

    g("init", "-q")
    g("config", "user.email", "t@example.test")
    g("config", "user.name", "t")
    g("add", "-A")
    g("commit", "-q", "-m", "seed memory")
    return mem


def _fake_plan_file(tmp_path, plan: dict) -> Path:
    p = tmp_path / "fake_plan.json"
    p.write_text(json.dumps(plan), encoding="utf-8")
    return p


def _drain(home, fake: Path, **env_over):
    env = dict(os.environ, CLAUDE_HOME=str(home), AUTOLEARN_FAKE_REFLECT=str(fake))
    env.update(env_over)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--drain"],
        capture_output=True, text=True, env=env, encoding="utf-8",
    )


def _create_action(**over):
    a = {"type": "create", "slug": "feedback_drained-lesson.md",
         "frontmatter": {"name": "drained-lesson", "description": "when you're about to X", "type": "feedback"},
         "body": "do Y well. **Why:** because. **How to apply:** thus."}
    a.update(over)
    return a


def test_drain_creates_and_commits(tmp_path):
    setup_memory(tmp_path)
    mem = _git_init_memory(tmp_path)
    _queue_n(tmp_path, 1)
    fake = _fake_plan_file(tmp_path, {"actions": [_create_action()],
                                      "catalog_additions": ["- feedback_drained-lesson.md -- the hook"]})
    r = _drain(tmp_path, fake)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "created feedback_drained-lesson.md" in r.stdout and "committed" in r.stdout
    assert (mem / "feedback_drained-lesson.md").exists()
    # index growth landed in CATALOG, NOT the always-loaded MEMORY.md
    assert "feedback_drained-lesson.md" in (mem / "CATALOG.md").read_text(encoding="utf-8")
    log = subprocess.run(["git", "-C", str(mem), "log", "--oneline"], capture_output=True, text=True).stdout
    assert "unattended drain" in log
    assert not (tmp_path / "autolearn_queue.jsonl").exists()  # queue cleared on success
    # and the whole thing stays reachable -> doctor healthy
    d = doctor(tmp_path)
    assert d.returncode == 0 and "HEALTHY" in d.stdout


def test_drain_update_action_rewrites_existing(tmp_path):
    setup_memory(tmp_path)
    mem = _git_init_memory(tmp_path)
    (mem / "feedback_topic.md").write_text(
        "---\nname: topic\ndescription: old\ntype: feedback\n---\n\nold body\n", encoding="utf-8")
    (mem / "CATALOG.md").write_text("# CATALOG\n\n- feedback_topic.md -- x\n", encoding="utf-8")
    _queue_n(tmp_path, 1)
    new_full = "---\nname: topic\ndescription: refined\ntype: feedback\n---\n\nold body, now with a durable extension line added.\n"
    fake = _fake_plan_file(tmp_path, {"actions": [
        {"type": "update", "slug": "feedback_topic.md", "new_full_content": new_full}]})
    r = _drain(tmp_path, fake)
    assert r.returncode == 0 and "updated feedback_topic.md" in r.stdout
    assert "refined" in (mem / "feedback_topic.md").read_text(encoding="utf-8")


def test_drain_update_clobber_guard_keeps_original(tmp_path):
    setup_memory(tmp_path)
    mem = _git_init_memory(tmp_path)
    big = "---\nname: topic\ndescription: d\ntype: feedback\n---\n\n" + "\n".join(
        f"a substantive durable line number {i} worth keeping" for i in range(20))
    (mem / "feedback_topic.md").write_text(big, encoding="utf-8")
    _queue_n(tmp_path, 1)
    # a much-shorter rewrite that drops the substance -> must be refused
    fake = _fake_plan_file(tmp_path, {"actions": [
        {"type": "update", "slug": "feedback_topic.md",
         "new_full_content": "---\nname: topic\ndescription: d\ntype: feedback\n---\n\ntiny\n"}]})
    r = _drain(tmp_path, fake)
    assert r.returncode == 0 and "would drop existing content" in r.stdout
    assert "line number 19" in (mem / "feedback_topic.md").read_text(encoding="utf-8")  # original kept


def test_drain_supersede_stamps_in_place(tmp_path):
    setup_memory(tmp_path)
    mem = _git_init_memory(tmp_path)
    (mem / "feedback_stale.md").write_text(
        "---\nname: stale\ndescription: d\ntype: feedback\n---\n\nold way\n", encoding="utf-8")
    _queue_n(tmp_path, 1)
    fake = _fake_plan_file(tmp_path, {"actions": [
        _create_action(),
        {"type": "supersede", "slug": "feedback_stale.md", "reason": "new way found",
         "superseded_by": "feedback_drained-lesson.md"}],
        "catalog_additions": ["- feedback_drained-lesson.md -- hook"]})
    r = _drain(tmp_path, fake)
    assert r.returncode == 0 and "superseded feedback_stale.md" in r.stdout
    stale = (mem / "feedback_stale.md").read_text(encoding="utf-8")
    assert "status: superseded" in stale and "new way found" in stale
    assert "old way" in stale  # superseded, never deleted


def test_drain_blocks_credential_in_plan(tmp_path):
    setup_memory(tmp_path)
    mem = _git_init_memory(tmp_path)
    _queue_n(tmp_path, 1)
    fake = _fake_plan_file(tmp_path, {"actions": [
        _create_action(slug="feedback_leaky.md", body="key is sk-ant-abcdef123456789 keep it")]})
    r = _drain(tmp_path, fake)
    assert r.returncode == 4 and "credential" in r.stdout.lower()
    assert not (mem / "feedback_leaky.md").exists()
    assert (tmp_path / "autolearn_queue.jsonl").exists()  # queue KEPT on a blocked plan


def test_drain_blocks_create_of_existing_slug(tmp_path):
    setup_memory(tmp_path)
    mem = _git_init_memory(tmp_path)
    (mem / "feedback_dup.md").write_text(
        "---\nname: dup\ndescription: d\ntype: feedback\n---\n\nbody\n", encoding="utf-8")
    _queue_n(tmp_path, 1)
    fake = _fake_plan_file(tmp_path, {"actions": [_create_action(slug="feedback_dup.md")]})
    r = _drain(tmp_path, fake)
    assert r.returncode == 4 and "already exists" in r.stdout


def test_drain_all_skip_clears_queue_no_commit(tmp_path):
    setup_memory(tmp_path)
    _git_init_memory(tmp_path)
    _queue_n(tmp_path, 2)
    fake = _fake_plan_file(tmp_path, {"actions": [{"type": "skip"}]})
    r = _drain(tmp_path, fake)
    assert r.returncode == 0 and "0 change(s)" in r.stdout and "no durable lessons" in r.stdout
    assert not (tmp_path / "autolearn_queue.jsonl").exists()  # success -> cleared


def test_drain_reports_the_model_used(tmp_path):
    setup_memory(tmp_path)
    _git_init_memory(tmp_path)
    _queue_n(tmp_path, 1)
    fake = _fake_plan_file(tmp_path, {"actions": [{"type": "skip"}]})
    r = _drain(tmp_path, fake, AUTOLEARN_DRAIN_MODEL="claude-haiku-4-5")
    assert "with model claude-haiku-4-5" in r.stdout


def test_drain_without_repo_still_writes_but_notes_no_commit(tmp_path):
    setup_memory(tmp_path)  # memory folder is NOT a git repo
    _queue_n(tmp_path, 1)
    fake = _fake_plan_file(tmp_path, {"actions": [_create_action(slug="feedback_norepo.md",
        frontmatter={"name": "norepo", "description": "when X", "type": "feedback"})],
        "catalog_additions": ["- feedback_norepo.md -- hook"]})
    r = _drain(tmp_path, fake)
    assert r.returncode == 0 and "created feedback_norepo.md" in r.stdout and "not a git repo" in r.stdout
    assert (tmp_path / "memory" / "feedback_norepo.md").exists()


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


def test_ships_windows_gotchas_doc():
    # the real Windows errors we hit wiring the drain must travel WITH the pack,
    # so a student on Windows starts from the fix, not the opaque error
    doc = REPO / "packs" / "autolearn" / "files" / "windows_gotchas.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8").lower()
    # the load-bearing traps + their fixes must be present
    assert "winerror 2" in text and "shutil.which" in text        # npm .cmd shim
    assert "stdin" in text                                          # arg mangling fix
    assert "task scheduler" in text and "path" in text             # minimal PATH
    assert "2>&1" in text                                           # powershell native stderr
    assert "git init" in text                                       # rollback prerequisite


def test_pack_header_points_to_windows_gotchas():
    pack = (REPO / "packs" / "autolearn" / "pack.yaml").read_text(encoding="utf-8")
    assert "windows_gotchas.md" in pack


def test_pack_loads_with_four_steps():
    pack = load_pack(REPO / "packs" / "autolearn" / "pack.yaml")
    assert pack.name == "autolearn"
    assert [s.id for s in pack.steps] == [
        "memory-present", "workflow-installed", "hook-installed", "autolearn-works",
    ]
