"""Tests for variants -- local/hosted style choices within a pack.

A step tagged `when: <variant>` runs only for the active variant; untagged steps
always run. The active variant is the explicit choice, else the pack's default.

    python -m pytest tests/test_variants.py -q
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runner.verify import (  # noqa: E402
    PackValidationError,
    build_pack,
    expand_steps,
    run_pack,
)
from tests.test_verify import FakeExecutor  # noqa: E402


def variant_pack():
    return build_pack(
        {
            "name": "p",
            "version": "1",
            "variants": ["local", "hosted"],
            "default_variant": "local",
            "steps": [
                {"id": "always", "instruction": "x", "check": {"type": "command_succeeds", "cmd": "c_always"}},
                {"id": "only-local", "when": "local", "instruction": "x", "check": {"type": "command_succeeds", "cmd": "c_local"}},
                {"id": "only-hosted", "when": "hosted", "instruction": "x", "check": {"type": "command_succeeds", "cmd": "c_hosted"}},
            ],
        }
    )


# --- run-time filtering -----------------------------------------------------


def test_local_variant_runs_shared_plus_local():
    r = run_pack(variant_pack(), FakeExecutor(), variant="local")
    assert [o.step_id for o in r.outcomes] == ["always", "only-local"]


def test_hosted_variant_runs_shared_plus_hosted():
    r = run_pack(variant_pack(), FakeExecutor(), variant="hosted")
    assert [o.step_id for o in r.outcomes] == ["always", "only-hosted"]


def test_default_variant_used_when_none_given():
    r = run_pack(variant_pack(), FakeExecutor())  # default_variant == local
    assert [o.step_id for o in r.outcomes] == ["always", "only-local"]


def test_expand_steps_respects_variant():
    assert [s["id"] for s in expand_steps(variant_pack(), variant="hosted")] == ["always", "only-hosted"]


def test_module_step_can_pin_a_variant():
    umbrella = build_pack(
        {
            "name": "u",
            "version": "1",
            "steps": [{"id": "m", "instruction": "x", "module": "p", "variant": "hosted"}],
        }
    )
    r = run_pack(umbrella, FakeExecutor(), resolver=lambda ref: variant_pack())
    assert [o.step_id for o in r.outcomes] == ["p/always", "p/only-hosted"]


# --- validation -------------------------------------------------------------


def test_when_not_in_variants_rejected():
    with pytest.raises(PackValidationError):
        build_pack(
            {
                "name": "p", "version": "1", "variants": ["local"],
                "steps": [{"id": "a", "instruction": "x", "when": "nope", "check": {"type": "command_succeeds", "cmd": "c"}}],
            }
        )


def test_when_without_declared_variants_rejected():
    with pytest.raises(PackValidationError):
        build_pack(
            {
                "name": "p", "version": "1",
                "steps": [{"id": "a", "instruction": "x", "when": "local", "check": {"type": "command_succeeds", "cmd": "c"}}],
            }
        )


def test_bad_default_variant_rejected():
    with pytest.raises(PackValidationError):
        build_pack(
            {
                "name": "p", "version": "1", "variants": ["local"], "default_variant": "hosted",
                "steps": [{"id": "a", "instruction": "x", "check": {"type": "command_succeeds", "cmd": "c"}}],
            }
        )


def test_default_variant_defaults_to_first_declared():
    pack = build_pack(
        {
            "name": "p", "version": "1", "variants": ["local", "hosted"],
            "steps": [{"id": "a", "instruction": "x", "check": {"type": "command_succeeds", "cmd": "c"}}],
        }
    )
    assert pack.default_variant == "local"
