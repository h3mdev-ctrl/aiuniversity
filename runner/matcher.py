"""
matcher.py -- the deterministic heart of the skill-pack runner.

Given a check's declared type, its expected value, and the actual result of
running the check's command (captured output + exit code), decide PASS / FAIL.

This module is PURE: it runs nothing itself. The runner captures command output
and hands it here. That keeps every decision reproducible and lets the tests
feed recorded ("fixture") outputs instead of really shelling out -- the same
input always yields the same verdict, on any machine, offline.

Five v1 check types (see eng plan "The 5 v1 check types"):

    command_succeeds    the command exited 0 (it ran without error)
    contains            the output includes an expected substring
    exact               the output equals an expected string (trailing
                        newlines ignored)
    regex               the output matches a regular-expression pattern
    endpoint_reachable  a service answered (exit 0 from a reachability probe)

command_succeeds and endpoint_reachable share the same rule (exit 0) on
purpose: they mean different things to a human ("the command failed" vs. "the
service isn't answering"), so they stay separate types to drive different,
plain-English failure messages (interaction-design Rule 2) -- even though the
pass/fail test is identical.

    match(check_type, expect, output, returncode)
        │
        ├─ unknown type?      -> raise UnknownCheckType   (bad recipe, fail loud)
        ├─ content check with
        │   no `expect`?      -> raise ValueError         (bad recipe, fail loud)
        └─ else               -> MatchResult(passed, reason)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# The check types this v1 runner understands. Unknown types are rejected up
# front: a bad recipe must fail loudly, never limp along half-applied (that is
# the exact "wasn't even activated" failure the product exists to prevent).
KNOWN_CHECK_TYPES = frozenset(
    {
        "command_succeeds",
        "contains",
        "exact",
        "regex",
        "endpoint_reachable",
    }
)

# Content checks read the command's output and therefore need an `expect:`.
# The exit-code-only checks (command_succeeds / endpoint_reachable) do not.
_CONTENT_CHECKS = frozenset({"contains", "exact", "regex"})


class UnknownCheckType(ValueError):
    """Raised when a pack declares a check type this runner does not know."""


@dataclass(frozen=True)
class MatchResult:
    """The verdict for a single check.

    `reason` is plain English on purpose: it feeds the failure-message layer
    (interaction-design Rule 2), which shows the recipient what failed in words
    a newcomer understands, not a raw error dump.
    """

    passed: bool
    reason: str


def match(
    check_type: str,
    expect: Optional[str],
    output: str,
    returncode: int,
) -> MatchResult:
    """Decide whether one check passed.

    Args:
        check_type: one of KNOWN_CHECK_TYPES.
        expect: the expected value; meaning depends on check_type. May be None
            for the exit-code-only types (command_succeeds, endpoint_reachable).
        output: everything the command printed (stdout), already captured.
        returncode: the command's exit code (0 == success).

    Returns:
        MatchResult(passed, reason).

    Raises:
        UnknownCheckType: check_type is not recognised.
        ValueError: a content check was given no `expect`, or a regex pattern
            is invalid. Both are malformed-recipe errors -- fail loudly.
    """
    if check_type not in KNOWN_CHECK_TYPES:
        raise UnknownCheckType(
            f"unknown check type {check_type!r}; "
            f"expected one of {sorted(KNOWN_CHECK_TYPES)}"
        )

    if check_type in _CONTENT_CHECKS:
        _require_expect(check_type, expect)

    if check_type == "command_succeeds":
        if returncode == 0:
            return MatchResult(True, "command ran without error")
        return MatchResult(False, f"command exited with code {returncode}")

    if check_type == "endpoint_reachable":
        if returncode == 0:
            return MatchResult(True, "service answered")
        return MatchResult(False, "service isn't answering")

    if check_type == "contains":
        if expect in output:  # type: ignore[operator]  # _require_expect ensured not None
            return MatchResult(True, f"output contains {expect!r}")
        return MatchResult(False, f"output does not contain {expect!r}")

    if check_type == "exact":
        # Trailing newlines are a footgun: most commands append one. Ignore
        # trailing newlines on both sides so "exact" means what a human means.
        if output.rstrip("\n") == expect.rstrip("\n"):  # type: ignore[union-attr]
            return MatchResult(True, "output matches exactly")
        return MatchResult(False, "output does not match exactly")

    if check_type == "regex":
        try:
            matched = re.search(expect, output) is not None  # type: ignore[arg-type]
        except re.error as exc:
            raise ValueError(f"invalid regex pattern {expect!r}: {exc}") from exc
        if matched:
            return MatchResult(True, f"output matches pattern {expect!r}")
        return MatchResult(False, f"output does not match pattern {expect!r}")

    # Unreachable: KNOWN_CHECK_TYPES and the branches above must stay in sync.
    # The test_all_known_types_are_handled test guards against drift here.
    raise UnknownCheckType(check_type)  # pragma: no cover


def _require_expect(check_type: str, expect: Optional[str]) -> None:
    """A content check with no `expect:` is a malformed recipe -- fail loudly."""
    if expect is None:
        raise ValueError(
            f"check type {check_type!r} requires an `expect:` value, "
            f"but none was given"
        )
