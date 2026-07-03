"""Unit tests for the matcher -- the deterministic core of the runner.

If the matcher is wrong, every pack lies, so this is the heaviest-covered file.
Each of the 5 check types gets a should-pass and a should-fail case, plus the
edge cases that protect against bad recipes (unknown type, missing `expect`,
invalid regex) and a drift guard that every declared type is actually handled.

Run from the skill-packs/ root:
    python -m pytest tests/test_matcher.py -q
"""

import sys
from pathlib import Path

import pytest

# Make `runner` importable when tests run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runner.matcher import (  # noqa: E402
    KNOWN_CHECK_TYPES,
    MatchResult,
    UnknownCheckType,
    match,
)


# --- command_succeeds -------------------------------------------------------


def test_command_succeeds_passes_on_exit_zero():
    result = match("command_succeeds", None, "any output", 0)
    assert result.passed


def test_command_succeeds_fails_on_nonzero_exit():
    result = match("command_succeeds", None, "boom", 1)
    assert not result.passed
    assert "1" in result.reason


# --- endpoint_reachable -----------------------------------------------------


def test_endpoint_reachable_passes_on_exit_zero():
    assert match("endpoint_reachable", None, "", 0).passed


def test_endpoint_reachable_fails_on_nonzero_exit():
    result = match("endpoint_reachable", None, "", 7)
    assert not result.passed
    assert "answering" in result.reason  # human-facing wording, not "exit 7"


# --- contains ---------------------------------------------------------------


def test_contains_passes_when_substring_present():
    assert match("contains", "gbrain", "gbrain 0.42.53.0", 0).passed


def test_contains_fails_when_substring_absent():
    assert not match("contains", "HEALTHY", "VERDICT: DEGRADED", 0).passed


# --- exact ------------------------------------------------------------------


def test_exact_passes_ignoring_trailing_newline():
    # Commands usually append a newline; "exact" must still pass.
    assert match("exact", "ready", "ready\n", 0).passed


def test_exact_fails_when_different():
    assert not match("exact", "ready", "not ready", 0).passed


# --- regex ------------------------------------------------------------------


def test_regex_passes_on_match():
    assert match("regex", r"gbrain \d+\.\d+", "gbrain 0.42 live", 0).passed


def test_regex_fails_on_no_match():
    assert not match("regex", r"^\d+$", "v1.2.3", 0).passed


# --- bad recipes fail loudly ------------------------------------------------


def test_unknown_check_type_raises():
    with pytest.raises(UnknownCheckType):
        match("containz", "x", "x", 0)


@pytest.mark.parametrize("ctype", ["contains", "exact", "regex"])
def test_content_checks_require_expect(ctype):
    with pytest.raises(ValueError):
        match(ctype, None, "output", 0)


def test_invalid_regex_raises_clear_error():
    with pytest.raises(ValueError):
        match("regex", "(unclosed", "output", 0)


# --- drift guard ------------------------------------------------------------


def test_all_known_types_are_handled():
    # Every declared type must return a MatchResult for a trivial input and
    # never raise UnknownCheckType. Guards against KNOWN_CHECK_TYPES and the
    # match() branches drifting out of sync.
    for ctype in KNOWN_CHECK_TYPES:
        expect = None if ctype in {"command_succeeds", "endpoint_reachable"} else "x"
        result = match(ctype, expect, "x", 0)
        assert isinstance(result, MatchResult)
