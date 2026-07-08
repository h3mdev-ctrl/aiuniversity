"""Golden-path INTEGRATION exam -- drive the real CLI end-to-end.

The unit tests prove each script in isolation. This proves the thing the product
actually promises: point the runner at a pack, run it against a throwaway
$CLAUDE_HOME, and the whole runbook reaches a real PASS -- including a
*behavioural* check that genuinely fires (a forbidden probe piped through the
freshly-installed hook), not just "the files exist".

Target = the guardrails pack, because it is fully hermetic: every check is local
(no `claude`/network) and it respects $CLAUDE_HOME, so the whole run stays inside
tmp and never touches the real ~/.claude. (The memory/gbrain packs each have one
genuinely-live step -- a `claude -p` recall probe / a live CLI -- that can't run
offline; those stay the recipient's one hand-run gate, as documented.)

WHAT "THE GOLDEN PATH" IS HERE. Each mechanical step carries a runnable `fix:`
(the command) kept separate from `on_fail:` (the human "why", shown when the run
stops). So there are two real end-to-end paths, and this exam drives BOTH through
the CLI: (1) headless `remediate` auto-applies the `fix:` of each red step and
reaches PASS on its own; (2) the agent path -- `verify` (red, names the gap) ->
run the prescribed command -> `verify` (green) -- for when a human is in the loop.
Genuinely-human steps (an interview, "add to your PATH", a live `claude -p` probe)
have no `fix:` and correctly stop with their prose instead of self-healing.

Exercises: runner/cli.py + runner/verify.py (escape hatch) + runner/matcher.py +
packs/guardrails end to end, deterministically and offline.

    python -m pytest tests/test_golden_path_integration.py -q
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GUARDRAILS = "packs/guardrails"
SETUP = "packs/guardrails/files/setup_guardrails.py"
STEPS = ("hook-installed", "registered-in-settings", "guard-actually-blocks")


def _cli(command: str, pack: str, home: Path):
    """Run the REAL CLI (python -m runner.cli <command> <pack>) against a
    throwaway CLAUDE_HOME. Returns (proc, parsed_json_payload)."""
    env = dict(os.environ, CLAUDE_HOME=str(home))
    proc = subprocess.run(
        [sys.executable, "-m", "runner.cli", command, pack],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", env=env,
    )
    payload = json.loads(proc.stdout)  # JSON on stdout is the source of truth
    return proc, payload


def _run_prescribed_fix(home: Path):
    """Apply the prescribed fix the way SKILL.md's agent does: run the setup
    command the failing step's on_fail hands over."""
    env = dict(os.environ, CLAUDE_HOME=str(home))
    return subprocess.run(
        [sys.executable, SETUP],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", env=env,
    )


# --------------------------------------------------------------------------- #
# The exam: verify(red) -> prescribed fix -> verify(green)
# --------------------------------------------------------------------------- #


def test_verify_on_a_fresh_home_is_read_only_and_stops(tmp_path):
    """verify must never mutate. On an empty home it finds the gap at the first
    step, stops there, and leaves NOTHING behind on disk."""
    proc, payload = _cli("verify", GUARDRAILS, tmp_path)

    assert payload["mode"] == "verify"
    assert payload["passed"] is False
    assert payload["stopped_at"] == "hook-installed", payload
    assert proc.returncode == 1
    # read-only: the run created no hook and no settings in the throwaway home
    assert not (tmp_path / "hooks" / "credential_guard.py").exists()
    assert not (tmp_path / "settings.json").exists()


def test_prescribed_fix_closes_the_gap_and_reverify_is_green(tmp_path):
    """The core exam. verify is red on an empty home; running the prescribed
    command (what SKILL.md does on a red step) sets it up; re-verify is GREEN on
    every step -- INCLUDING the behavioural guard-actually-blocks check, which
    pipes a real forbidden probe through the freshly-installed hook."""
    # 1. red, gap named
    _, before = _cli("verify", GUARDRAILS, tmp_path)
    assert before["passed"] is False and before["stopped_at"] == "hook-installed"

    # 2. apply the prescribed fix (agent runs the on_fail command)
    fix = _run_prescribed_fix(tmp_path)
    assert fix.returncode == 0, fix.stderr

    # 3. green -- the whole runbook now passes, read-only
    proc, after = _cli("verify", GUARDRAILS, tmp_path)
    assert proc.returncode == 0
    assert after["passed"] is True, after
    assert after["stopped_at"] is None
    statuses = {o["step_id"]: o["status"] for o in after["outcomes"]}
    assert set(statuses) == set(STEPS), statuses
    assert all(v == "pass" for v in statuses.values()), statuses

    # it operated on the THROWAWAY home, not the real ~/.claude
    assert (tmp_path / "hooks" / "credential_guard.py").exists()
    settings = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert "PreToolUse" in settings.get("hooks", {})


def test_verify_is_idempotent_and_read_only_after_setup(tmp_path):
    """Once set up, verify stays green and changes nothing on re-run."""
    _run_prescribed_fix(tmp_path)
    first = (tmp_path / "settings.json").read_text(encoding="utf-8")

    proc, payload = _cli("verify", GUARDRAILS, tmp_path)
    assert proc.returncode == 0 and payload["passed"] is True, payload

    # verify mutated nothing
    assert (tmp_path / "settings.json").read_text(encoding="utf-8") == first


def test_cli_remediate_auto_applies_the_runnable_fixes_to_pass(tmp_path):
    """Headless `remediate` now drives the whole runbook to PASS on its own,
    because every mechanical step carries a runnable `fix:` (the command, kept
    separate from the human `on_fail` prose). On an empty home the first step is
    red -> its fix runs -> green; the run reaches PASS with the hook really
    installed in the throwaway home. This is the deterministic answer key the exam
    always implied: if we can pose the check, we hand over the fix for the
    mechanical parts. (Genuinely-human steps -- interviews, PATH, live probes --
    have no fix and still stop with their prose, by design.)"""
    proc, payload = _cli("remediate", GUARDRAILS, tmp_path)

    assert payload["mode"] == "remediate"
    assert payload["passed"] is True, payload
    assert proc.returncode == 0
    assert payload["stopped_at"] is None
    statuses = {o["step_id"]: o["status"] for o in payload["outcomes"]}
    assert set(statuses) == set(STEPS), statuses
    for step in STEPS:
        assert statuses[step] in ("pass", "remediated"), (step, statuses)
    # empty home -> the first step was red -> its runnable fix landed it
    assert statuses["hook-installed"] == "remediated", statuses
    assert (tmp_path / "hooks" / "credential_guard.py").exists()
