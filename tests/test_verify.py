"""Tests for the runner loop and pack validation.

The escape hatch (T1 in the eng plan) is the most important behaviour to pin
down: fix once, and if it's still red, STOP with the right step -- never loop.
Validation tests prove a bad recipe fails up front, before anything runs.

Runs use a FakeExecutor so nothing really shells out -- same pack, same verdict,
offline. Validation tests use build_pack (dicts), so no YAML dependency here.

    python -m pytest tests/test_verify.py -q
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runner.verify import (  # noqa: E402
    PackValidationError,
    build_pack,
    run_pack,
)


class FakeExecutor:
    """Records calls and returns canned (output, rc) per command.

    when_run_set(trigger, target, out, rc) models a working fix: when the fix
    command runs, it flips the target check command's future response.
    """

    def __init__(self):
        self.calls: list[str] = []
        self.responses: dict[str, tuple[str, int]] = {}
        self._side_effects: dict[str, tuple[str, str, int]] = {}

    def set(self, cmd: str, out: str, rc: int) -> None:
        self.responses[cmd] = (out, rc)

    def when_run_set(self, trigger: str, target: str, out: str, rc: int) -> None:
        self._side_effects[trigger] = (target, out, rc)

    def __call__(self, cmd: str) -> "tuple[str, int]":
        self.calls.append(cmd)
        if cmd in self._side_effects:
            target, out, rc = self._side_effects[cmd]
            self.responses[target] = (out, rc)
            return ("applied fix", 0)
        return self.responses.get(cmd, ("", 0))


# --- happy path -------------------------------------------------------------


def test_all_green_passes():
    pack = build_pack(
        {
            "name": "p",
            "version": "1",
            "steps": [
                {"id": "a", "instruction": "do a", "check": {"type": "command_succeeds", "cmd": "cmd_a"}},
                {"id": "b", "instruction": "do b", "check": {"type": "contains", "cmd": "cmd_b", "expect": "ok"}},
            ],
        }
    )
    ex = FakeExecutor()
    ex.set("cmd_a", "", 0)
    ex.set("cmd_b", "all ok here", 0)

    result = run_pack(pack, ex)

    assert result.passed
    assert result.stopped_at is None
    assert [o.status for o in result.outcomes] == ["pass", "pass"]


# --- escape hatch (T1) ------------------------------------------------------


def test_remediation_fixes_then_continues():
    pack = build_pack(
        {
            "name": "p",
            "version": "1",
            "steps": [
                {
                    "id": "connect",
                    "instruction": "connect the thing",
                    "check": {"type": "contains", "cmd": "check_x", "expect": "live"},
                    "fix": "fix_x",
                }
            ],
        }
    )
    ex = FakeExecutor()
    ex.set("check_x", "not yet", 0)          # red first try
    ex.when_run_set("fix_x", "check_x", "now live", 0)  # the fix works

    result = run_pack(pack, ex)

    assert result.passed
    assert result.outcomes[0].status == "remediated"
    assert "fix_x" in ex.calls               # the fix was actually applied


def test_stops_when_fix_does_not_work():
    # The core escape-hatch case: fix applied ONCE, still red -> STOP.
    pack = build_pack(
        {
            "name": "p",
            "version": "1",
            "steps": [
                {"id": "ok1", "instruction": "step 1", "check": {"type": "command_succeeds", "cmd": "c1"}},
                {
                    "id": "stuck",
                    "instruction": "the broken one",
                    "check": {"type": "contains", "cmd": "check_x", "expect": "live"},
                    "fix": "fix_x",  # this fix does nothing to check_x
                },
                {"id": "never", "instruction": "should not run", "check": {"type": "command_succeeds", "cmd": "c3"}},
            ],
        }
    )
    ex = FakeExecutor()
    ex.set("c1", "", 0)
    ex.set("check_x", "still broken", 0)     # stays red even after the fix

    result = run_pack(pack, ex)

    assert not result.passed
    assert result.stopped_at == "stuck"
    assert result.outcomes[-1].status == "failed"
    assert [o.step_id for o in result.outcomes] == ["ok1", "stuck"]  # stopped, "never" never ran
    # fix was attempted exactly once: fix_x appears once, check_x runs twice (initial + re-check)
    assert ex.calls.count("fix_x") == 1
    assert ex.calls.count("check_x") == 2


def test_verify_mode_is_read_only_and_does_not_apply_fix():
    # apply_fixes=False (verify): a red check must NOT run its fix. verify
    # never mutates the machine, even when a fix that would work exists.
    pack = build_pack(
        {
            "name": "p",
            "version": "1",
            "steps": [
                {
                    "id": "s",
                    "instruction": "read-only check",
                    "check": {"type": "contains", "cmd": "check_x", "expect": "live"},
                    "fix": "fix_x",
                }
            ],
        }
    )
    ex = FakeExecutor()
    ex.set("check_x", "not yet", 0)
    ex.when_run_set("fix_x", "check_x", "now live", 0)  # fix WOULD work if run

    result = run_pack(pack, ex, apply_fixes=False)

    assert not result.passed
    assert result.stopped_at == "s"
    assert "fix_x" not in ex.calls  # read-only: the fix was never applied


# --- fix vs on_fail: runnable command vs human prose ------------------------


def test_prose_on_fail_is_never_executed():
    # A genuinely-human step has on_fail (guidance) but NO fix. remediate must
    # NOT shell-run the prose at the machine -- it stops with the guidance. This
    # is the footgun the fix/on_fail split kills: English is not a command.
    pack = build_pack(
        {
            "name": "p",
            "version": "1",
            "steps": [
                {
                    "id": "human",
                    "instruction": "needs a person",
                    "check": {"type": "contains", "cmd": "check_x", "expect": "live"},
                    "on_fail": "Create a Supabase account, then set DATABASE_URL.",
                }
            ],
        }
    )
    ex = FakeExecutor()
    ex.set("check_x", "not yet", 0)

    result = run_pack(pack, ex)  # remediate mode

    assert not result.passed
    assert result.stopped_at == "human"
    # the prose was never run as a command; only the check ran (once)
    assert ex.calls == ["check_x"]


def test_fix_runs_and_on_fail_is_not_run_when_both_present():
    # A step may carry BOTH: fix (runnable) + on_fail (why, for the failure
    # message). remediate runs only fix.
    pack = build_pack(
        {
            "name": "p",
            "version": "1",
            "steps": [
                {
                    "id": "both",
                    "instruction": "has both",
                    "check": {"type": "contains", "cmd": "check_x", "expect": "live"},
                    "fix": "fix_x",
                    "on_fail": "If the fix didn't take, check your PATH and retry.",
                }
            ],
        }
    )
    ex = FakeExecutor()
    ex.set("check_x", "not yet", 0)
    ex.when_run_set("fix_x", "check_x", "now live", 0)

    result = run_pack(pack, ex)

    assert result.passed
    assert result.outcomes[0].status == "remediated"
    assert "fix_x" in ex.calls
    assert "If the fix didn't take, check your PATH and retry." not in ex.calls


def test_non_string_fix_rejected():
    with pytest.raises(PackValidationError):
        build_pack(
            {
                "name": "p",
                "version": "1",
                "steps": [
                    {
                        "id": "a",
                        "instruction": "x",
                        "check": {"type": "command_succeeds", "cmd": "c"},
                        "fix": 123,
                    }
                ],
            }
        )


def test_stops_immediately_without_on_fail():
    pack = build_pack(
        {
            "name": "p",
            "version": "1",
            "steps": [
                {
                    "id": "s1",
                    "instruction": "no fix provided",
                    "check": {"type": "contains", "cmd": "c", "expect": "ok"},
                }
            ],
        }
    )
    ex = FakeExecutor()
    ex.set("c", "nope", 0)

    result = run_pack(pack, ex)

    assert not result.passed
    assert result.stopped_at == "s1"
    assert ex.calls.count("c") == 1          # no remediation attempted


# --- fixtures ---------------------------------------------------------------


def test_fixture_short_circuits_the_command():
    pack = build_pack(
        {
            "name": "p",
            "version": "1",
            "steps": [
                {
                    "id": "recorded",
                    "instruction": "check against a recorded answer",
                    "check": {"type": "contains", "expect": "42", "fixture": "the answer is 42"},
                }
            ],
        }
    )
    ex = FakeExecutor()

    result = run_pack(pack, ex)

    assert result.passed
    assert ex.calls == []                    # command never ran; fixture was used


# --- validation: bad recipes fail up front ----------------------------------


def test_missing_name_rejected():
    with pytest.raises(PackValidationError):
        build_pack({"version": "1", "steps": [{"id": "a", "instruction": "x", "check": {"type": "command_succeeds", "cmd": "c"}}]})


def test_empty_steps_rejected():
    with pytest.raises(PackValidationError):
        build_pack({"name": "p", "version": "1", "steps": []})


def test_unknown_check_type_rejected():
    with pytest.raises(PackValidationError):
        build_pack({"name": "p", "version": "1", "steps": [{"id": "a", "instruction": "x", "check": {"type": "containz", "cmd": "c", "expect": "y"}}]})


def test_content_check_without_expect_rejected():
    with pytest.raises(PackValidationError):
        build_pack({"name": "p", "version": "1", "steps": [{"id": "a", "instruction": "x", "check": {"type": "contains", "cmd": "c"}}]})


def test_duplicate_step_ids_rejected():
    with pytest.raises(PackValidationError):
        build_pack(
            {
                "name": "p",
                "version": "1",
                "steps": [
                    {"id": "dup", "instruction": "x", "check": {"type": "command_succeeds", "cmd": "c1"}},
                    {"id": "dup", "instruction": "y", "check": {"type": "command_succeeds", "cmd": "c2"}},
                ],
            }
        )


def test_step_without_instruction_rejected():
    with pytest.raises(PackValidationError):
        build_pack({"name": "p", "version": "1", "steps": [{"id": "a", "check": {"type": "command_succeeds", "cmd": "c"}}]})


def test_check_without_cmd_or_fixture_rejected():
    with pytest.raises(PackValidationError):
        build_pack({"name": "p", "version": "1", "steps": [{"id": "a", "instruction": "x", "check": {"type": "command_succeeds"}}]})
