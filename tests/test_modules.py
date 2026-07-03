"""Tests for modules -- packs-including-packs (the composition primitive).

Covers: a module runs inline with id-prefixed outcomes; a failure inside a
module stops the whole run and reports "<ref>/<step>"; steps after the module
don't run on failure; the one-level depth guard; and the missing-resolver
error. Plus validation of check-xor-module.

    python -m pytest tests/test_modules.py -q
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runner.verify import (  # noqa: E402
    PackCompositionError,
    PackResolver,
    PackValidationError,
    build_pack,
    expand_steps,
    run_pack,
)
from tests.test_verify import FakeExecutor  # reuse the fake executor


def make_resolver(packs: dict) -> PackResolver:
    def resolve(ref: str):
        return packs[ref]
    return resolve


def _foundation_with_module():
    return build_pack(
        {
            "name": "foundation",
            "version": "1",
            "steps": [
                {"id": "layer0", "instruction": "identity", "check": {"type": "command_succeeds", "cmd": "id_ok"}},
                {"id": "layer4", "instruction": "set up your tools", "module": "gbrain-windows"},
                {"id": "layer5", "instruction": "durability", "check": {"type": "command_succeeds", "cmd": "backup_ok"}},
            ],
        }
    )


def _gbrain(connect_output="live"):
    return build_pack(
        {
            "name": "gbrain-windows",
            "version": "1",
            "steps": [
                {"id": "install", "instruction": "install gbrain", "check": {"type": "command_succeeds", "cmd": "g_install"}},
                {"id": "connect", "instruction": "connect gbrain", "check": {"type": "contains", "cmd": "g_connect", "expect": "live"}},
            ],
        }
    )


# --- happy path -------------------------------------------------------------


def test_module_runs_inline_with_prefixed_ids():
    resolver = make_resolver({"gbrain-windows": _gbrain()})
    ex = FakeExecutor()
    ex.set("id_ok", "", 0)
    ex.set("g_install", "", 0)
    ex.set("g_connect", "gbrain is live", 0)
    ex.set("backup_ok", "", 0)

    result = run_pack(_foundation_with_module(), ex, resolver)

    assert result.passed
    assert [o.step_id for o in result.outcomes] == [
        "layer0",
        "gbrain-windows/install",
        "gbrain-windows/connect",
        "layer5",
    ]


# --- failure inside a module ------------------------------------------------


def test_failure_inside_module_stops_and_reports_prefixed_step():
    resolver = make_resolver({"gbrain-windows": _gbrain()})
    ex = FakeExecutor()
    ex.set("id_ok", "", 0)
    ex.set("g_install", "", 0)
    ex.set("g_connect", "not connected", 0)  # red, no on_fail -> stop
    ex.set("backup_ok", "", 0)

    result = run_pack(_foundation_with_module(), ex, resolver)

    assert not result.passed
    assert result.stopped_at == "gbrain-windows/connect"
    # layer5 (after the module) never ran
    assert [o.step_id for o in result.outcomes] == [
        "layer0",
        "gbrain-windows/install",
        "gbrain-windows/connect",
    ]
    assert result.outcomes[-1].status == "failed"
    assert "backup_ok" not in ex.calls


# --- guards -----------------------------------------------------------------


def test_expand_steps_flattens_modules_for_teach():
    resolver = make_resolver({"gbrain-windows": _gbrain()})
    flat = expand_steps(_foundation_with_module(), resolver)
    assert [s["id"] for s in flat] == [
        "layer0",
        "layer4",  # the module container step itself
        "gbrain-windows/install",
        "gbrain-windows/connect",
        "layer5",
    ]
    assert flat[1]["kind"] == "module"
    assert flat[1]["module"] == "gbrain-windows"


def test_module_step_without_resolver_raises():
    ex = FakeExecutor()
    ex.set("id_ok", "", 0)
    with pytest.raises(PackCompositionError):
        run_pack(_foundation_with_module(), ex, resolver=None)


def test_modules_cannot_nest_two_levels():
    # gbrain (a module) itself contains a module step -> depth guard fires.
    nested_gbrain = build_pack(
        {
            "name": "gbrain-windows",
            "version": "1",
            "steps": [
                {"id": "install", "instruction": "install", "check": {"type": "command_succeeds", "cmd": "g_install"}},
                {"id": "deeper", "instruction": "should not be allowed", "module": "something-else"},
            ],
        }
    )
    resolver = make_resolver({"gbrain-windows": nested_gbrain, "something-else": _gbrain()})
    ex = FakeExecutor()
    ex.set("id_ok", "", 0)
    ex.set("g_install", "", 0)

    with pytest.raises(PackCompositionError):
        run_pack(_foundation_with_module(), ex, resolver)


# --- validation: check XOR module -------------------------------------------


def test_step_with_both_check_and_module_rejected():
    with pytest.raises(PackValidationError):
        build_pack(
            {
                "name": "p",
                "version": "1",
                "steps": [
                    {"id": "a", "instruction": "x", "check": {"type": "command_succeeds", "cmd": "c"}, "module": "m"}
                ],
            }
        )


def test_step_with_neither_check_nor_module_rejected():
    with pytest.raises(PackValidationError):
        build_pack({"name": "p", "version": "1", "steps": [{"id": "a", "instruction": "x"}]})


def test_module_ref_must_be_nonempty_string():
    with pytest.raises(PackValidationError):
        build_pack({"name": "p", "version": "1", "steps": [{"id": "a", "instruction": "x", "module": ""}]})
