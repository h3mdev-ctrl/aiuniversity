"""Tests for the hooks pack -- liveness (hook_doctor) and correctness (guard_regression).

The load-bearing tests here are the ones that break something on purpose. A
regression harness that only ever reports green is indistinguishable from one
that reports green unconditionally, which is the exact failure GUARD_DESIGN rule 1
is about -- so `test_regression_goes_red_when_a_guard_is_mutated` breaks a matcher
and demands a FAIL, and `test_uninstalled_guard_is_skipped_not_passed` demands
that absence is reported as absence.

    python -m pytest tests/test_hooks_pack.py -q
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GUARDRAILS = REPO / "packs" / "guardrails" / "files"
HOOKS_FILES = REPO / "packs" / "hooks" / "files"
sys.path.insert(0, str(REPO))

from runner.verify import load_pack  # noqa: E402

PACK = REPO / "packs" / "hooks"


def run(script: Path, *args: str, home: Path):
    env = dict(os.environ, CLAUDE_HOME=str(home))
    return subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True, env=env,
                          encoding="utf-8", errors="replace")


def regression(home: Path, *args: str):
    return run(HOOKS_FILES / "guard_regression.py", *args, home=home)


def install_all(home: Path):
    for s in ("setup_guardrails.py", "setup_session_guard.py",
              "setup_recon_build_guard.py", "setup_windows_quirk_guard.py"):
        assert run(GUARDRAILS / s, home=home).returncode == 0, s


# --- pack structure ---------------------------------------------------------


def test_pack_loads_and_validates():
    pack = load_pack(PACK / "pack.yaml")
    assert pack.name == "hooks"


def test_ships_both_layers():
    # liveness and correctness are separate files on purpose; a hook can pass
    # one and fail the other, and the repairs are different.
    assert (HOOKS_FILES / "hook_doctor.py").exists()
    assert (HOOKS_FILES / "guard_regression.py").exists()
    assert (HOOKS_FILES / "GUARD_DESIGN.md").exists()


def test_every_step_hands_over_a_fix():
    for step in load_pack(PACK / "pack.yaml").steps:
        assert step.on_fail and step.on_fail.strip(), f"{step.id} has no on_fail"


def test_guard_correctness_step_exists():
    ids = [s.id for s in load_pack(PACK / "pack.yaml").steps]
    assert "hook-liveness" in ids
    assert "guard-correctness" in ids


# --- guard_regression: honest reporting -------------------------------------


def test_uninstalled_guard_is_skipped_not_passed(tmp_path):
    """An empty home must not produce a green run. Nothing was checked."""
    r = regression(tmp_path, "--json")
    assert r.returncode == 0
    doc = json.loads(r.stdout)
    assert doc["passed"] == 0
    assert doc["skipped"] > 0
    assert all(c["status"] == "skip" for c in doc["results"])


def test_installed_guards_pass_their_own_cases(tmp_path):
    install_all(tmp_path)
    r = regression(tmp_path, "--json")
    doc = json.loads(r.stdout)
    assert doc["verdict"] == "HEALTHY", r.stdout
    assert doc["failed"] == 0
    assert doc["skipped"] == 0
    assert doc["passed"] >= 18
    assert r.returncode == 0


def test_regression_goes_red_when_a_guard_is_mutated(tmp_path):
    """The mutation check. Break one matcher; the harness must FAIL, not pass.

    Without this, a harness that silently stopped exercising anything would look
    identical to a healthy one -- and that is the defect this whole pack exists
    to catch.
    """
    install_all(tmp_path)
    hook = tmp_path / "hooks" / "windows_quirk_guard.py"
    src = hook.read_text(encoding="utf-8")
    assert "if PS_HERESTRING.search(cmd):" in src
    hook.write_text(src.replace("if PS_HERESTRING.search(cmd):",
                                "if False and PS_HERESTRING.search(cmd):"),
                    encoding="utf-8")

    r = regression(tmp_path, "--json")
    doc = json.loads(r.stdout)
    assert r.returncode == 1
    assert doc["verdict"] == "REGRESSED"
    failed = [c["label"] for c in doc["results"] if c["status"] == "fail"]
    assert any("here-string" in lbl for lbl in failed), failed


def test_a_dead_guard_fails_every_one_of_its_cases(tmp_path):
    """A CRASHING guard must fail loudly here even though PreToolUse treats its
    exit as a non-blocking error -- the whole point of the correctness layer."""
    install_all(tmp_path)
    hook = tmp_path / "hooks" / "windows_quirk_guard.py"
    hook.write_text("import sys\nraise SystemExit(1 + int(sys.stdin.read() and 0))\n",
                    encoding="utf-8")
    doc = json.loads(regression(tmp_path, "--json").stdout)
    win = [c for c in doc["results"] if c["guard"] == "windows_quirk_guard.py"]
    assert win and all(c["status"] == "fail" for c in win)


def test_registered_hook_with_no_cases_is_reported_uncovered(tmp_path):
    install_all(tmp_path)
    settings = tmp_path / "settings.json"
    data = json.loads(settings.read_text(encoding="utf-8"))
    data["hooks"]["PreToolUse"].append(
        {"hooks": [{"type": "command", "command": 'python "/x/my_custom_guard.py"'}]})
    settings.write_text(json.dumps(data), encoding="utf-8")

    doc = json.loads(regression(tmp_path, "--json").stdout)
    assert "my_custom_guard.py" in doc["uncovered"]


def test_user_cases_extend_the_builtin_suites(tmp_path):
    install_all(tmp_path)
    (tmp_path / "guard_cases.json").write_text(json.dumps({
        "session_end_guard.py": {"cases": [
            {"label": "my own phrase blocks", "event": "Stop",
             "payload": {"response": "Good night, that's a wrap."}, "expect": "block"},
        ]}
    }), encoding="utf-8")
    doc = json.loads(regression(tmp_path, "--json").stdout)
    labels = [c["label"] for c in doc["results"]]
    assert "my own phrase blocks" in labels


def test_selftest_delegation_runs_for_the_recon_guard(tmp_path):
    install_all(tmp_path)
    doc = json.loads(regression(tmp_path, "--json").stdout)
    sel = [c for c in doc["results"] if c["label"].startswith("selftest:")]
    assert sel and all(c["status"] == "pass" for c in sel), sel


# --- the recon guard's scratch + recon-evidence conditions ------------------


def _recon_pipe(home: Path, payload: dict, selftest: bool):
    env = dict(os.environ, CLAUDE_HOME=str(home))
    if selftest:
        env["CLAUDE_RECON_SELFTEST"] = "1"
    else:
        env.pop("CLAUDE_RECON_SELFTEST", None)
    return subprocess.run(
        [sys.executable, str(home / "hooks" / "recon_before_build_guard.py")],
        input=json.dumps(payload), capture_output=True, text=True, env=env,
        encoding="utf-8", errors="replace").returncode


def _populated_repo(root: Path) -> Path:
    repo = root / "proj"
    (repo / ".git").mkdir(parents=True)
    (repo / "extract.py").write_text("# a\n", encoding="utf-8")
    (repo / "reconcile.py").write_text("# b\n", encoding="utf-8")
    return repo


def test_selftest_flag_can_only_make_the_guard_fire_more(tmp_path):
    """CLAUDE_RECON_SELFTEST disables the OS-temp exclusion so a fixture can be
    built at all. Pin the direction: with the flag ON the guard BLOCKS, with it
    OFF the same payload is allowed. A flag that made it fire LESS would be a
    bypass, and this is the test that would catch one appearing."""
    run(GUARDRAILS / "setup_recon_build_guard.py", home=tmp_path)
    repo = _populated_repo(tmp_path)            # tmp_path IS under the OS temp tree
    payload = {"session_id": "s-1", "tool_name": "Write", "transcript_path": "",
               "tool_input": {"file_path": str(repo / "brand_new.py"), "content": "x"}}
    assert _recon_pipe(tmp_path, payload, selftest=False) == 0
    payload["session_id"] = "s-2"               # fresh: nudge-once must not explain it
    assert _recon_pipe(tmp_path, payload, selftest=True) == 2


def test_recon_evidence_in_the_transcript_silences_the_nudge(tmp_path):
    run(GUARDRAILS / "setup_recon_build_guard.py", home=tmp_path)
    repo = _populated_repo(tmp_path)
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(json.dumps({"message": {"content": [
        {"type": "tool_use", "name": "Read", "input": {"file_path": str(repo)}}]}}) + "\n",
        encoding="utf-8")

    def payload(sess, tp):
        return {"session_id": sess, "tool_name": "Write", "transcript_path": tp,
                "tool_input": {"file_path": str(repo / f"new_{sess}.py"), "content": "x"}}

    # Control first: without the transcript the same shape DOES nudge, so the
    # silence below is attributable to the evidence and not to something else.
    assert _recon_pipe(tmp_path, payload("s-none", ""), selftest=True) == 2
    assert _recon_pipe(tmp_path, payload("s-read", str(transcript)), selftest=True) == 0


def test_scratch_directories_are_excluded(tmp_path):
    run(GUARDRAILS / "setup_recon_build_guard.py", home=tmp_path)
    repo = _populated_repo(tmp_path)
    scratch = repo / "scratchpad"
    scratch.mkdir()
    (scratch / "a.py").write_text("# a\n", encoding="utf-8")
    (scratch / "b.py").write_text("# b\n", encoding="utf-8")
    payload = {"session_id": "s-scr", "tool_name": "Write", "transcript_path": "",
               "tool_input": {"file_path": str(scratch / "probe.py"), "content": "x"}}
    assert _recon_pipe(tmp_path, payload, selftest=True) == 0


# --- the windows guard itself ----------------------------------------------


def test_windows_guard_installs_and_registers(tmp_path):
    setup = GUARDRAILS / "setup_windows_quirk_guard.py"
    assert run(setup, "--check-hook-file", home=tmp_path).returncode == 1
    assert run(setup, home=tmp_path).returncode == 0
    assert run(setup, "--check-hook-file", home=tmp_path).returncode == 0
    assert run(setup, "--check-registered", home=tmp_path).returncode == 0
    assert run(setup, home=tmp_path).returncode == 0          # idempotent


def test_windows_guard_behavioural_selftest_passes(tmp_path):
    setup = GUARDRAILS / "setup_windows_quirk_guard.py"
    run(setup, home=tmp_path)
    r = run(setup, "--test-blocking", home=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_windows_guard_is_inert_without_local_packages(tmp_path):
    """The cwd-is-the-import-path rule discovers package names from the working
    directory. Somewhere with nothing importable it must stay quiet rather than
    guess -- an advisory that fires on an empty directory is noise."""
    setup = GUARDRAILS / "setup_windows_quirk_guard.py"
    run(setup, home=tmp_path)
    env = dict(os.environ, CLAUDE_HOME=str(tmp_path))
    env.pop("CLAUDE_LOCAL_PKGS", None)
    workdir = tmp_path / "empty"
    workdir.mkdir()
    payload = {"tool_name": "Bash",
               "tool_input": {"command": 'cd sub && python -c "import anything"'}}
    p = subprocess.run([sys.executable, str(tmp_path / "hooks" / "windows_quirk_guard.py")],
                       input=json.dumps(payload).encode("utf-8"),
                       capture_output=True, cwd=str(workdir), env=env)
    assert p.returncode == 0
    assert b"local-import" not in p.stdout + p.stderr


def test_windows_guard_fires_on_a_configured_local_package(tmp_path):
    """...and the positive control for the same rule, so the narrowing above is
    pinned rather than merely convenient."""
    setup = GUARDRAILS / "setup_windows_quirk_guard.py"
    run(setup, home=tmp_path)
    env = dict(os.environ, CLAUDE_HOME=str(tmp_path), CLAUDE_LOCAL_PKGS="research,scripts")
    payload = {"tool_name": "Bash",
               "tool_input": {"command": 'cd research && python -c "import research.x"'}}
    p = subprocess.run([sys.executable, str(tmp_path / "hooks" / "windows_quirk_guard.py")],
                       input=json.dumps(payload).encode("utf-8"),
                       capture_output=True, env=env)
    assert p.returncode == 0
    assert b"local-import-needs-repo-root" in p.stdout
