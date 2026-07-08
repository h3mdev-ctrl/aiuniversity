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

WHAT "THE GOLDEN PATH" IS HERE. Remediation is AGENT-driven: SKILL.md runs a
check, and on a red result reads the step's prescribed `on_fail` and runs the
command inside it. The packs write `on_fail` as human/agent prose (it explains
*why*, then gives the command), so the headless `python -m runner.cli remediate`
-- which shell-execs `on_fail` verbatim -- can NOT auto-apply it (see
test_cli_remediate_cannot_auto_apply_prose_on_fail, which pins that). So the true
end-to-end loop a recipient goes through is: verify (red, names the gap) -> run
the prescribed command -> verify (green). This exam drives exactly that through
the real CLI.

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


def test_cli_remediate_cannot_auto_apply_prose_on_fail(tmp_path):
    """Pins a known limitation so it stays visible. The packs write `on_fail` as
    agent prose ("Hook file missing. Install it: python ..."), and headless
    `remediate` shell-execs that verbatim -> it is not a runnable command, so the
    fix cannot land and the run stops at the first step. Remediation is therefore
    AGENT-driven (SKILL.md reads on_fail and runs the command), NOT something the
    bare CLI does. If a future change makes on_fail command-runnable (or adds a
    dedicated runnable `fix:` field), this test should flip to a full PASS -- and
    that's the reminder to update it."""
    proc, payload = _cli("remediate", GUARDRAILS, tmp_path)
    assert payload["mode"] == "remediate"
    assert payload["passed"] is False, payload
    assert payload["stopped_at"] == "hook-installed", payload
    assert proc.returncode == 1
