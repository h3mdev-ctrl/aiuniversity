"""
verify.py -- reads a pack, runs each step's check, and drives the escape hatch.

Flow (see eng plan "The escape hatch -- state machine"):

    load + validate the WHOLE pack     bad recipe -> fail up front, run nothing
        │
        for each step:
          run check -> (output, rc) -> match()
            ├─ green -> next step
            └─ red   -> apply on_fail ONCE -> re-check
                          ├─ green -> next step (remediated)
                          └─ red   -> STOP "human needed at step N"
        │
        all green -> PASS

Two deliberate design points:

- Validate the whole pack before running a single command. A typo in the recipe
  must fail loudly and immediately, never halfway through a half-applied setup
  (this is the "wasn't even activated" scar, killed at the source).
- The command executor is INJECTABLE. The real one shells out; tests pass a fake
  that returns recorded outputs (fixtures), so the same pack yields the same
  verdict on any machine, offline.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from runner.matcher import (
    KNOWN_CHECK_TYPES,
    UnknownCheckType,
    match,
)

# An executor takes a command string and returns (combined_output, returncode).
Executor = Callable[[str], "tuple[str, int]"]

# A resolver turns a module ref (e.g. "gbrain-windows") into a loaded Pack.
# Injectable so tests resolve from a dict and the real one loads from disk.
PackResolver = Callable[[str], "Pack"]


class PackValidationError(ValueError):
    """Raised when a pack.yaml is malformed. Fail up front, run nothing."""


class PackCompositionError(RuntimeError):
    """Raised when modules can't compose: no resolver, or nested too deep.

    v1 allows exactly ONE level of nesting (a pack may include modules; a
    module may not include modules). Deeper nesting is a YAGNI line, not a
    real limit -- lift it only when a real pack needs it.
    """


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Check:
    type: str
    cmd: str
    expect: Optional[str] = None
    # A recorded response the check runs against instead of a live command
    # (correctness packs). When set, the runner does NOT execute `cmd`.
    fixture: Optional[str] = None


@dataclass(frozen=True)
class Step:
    id: str
    instruction: str
    # Exactly one of `check` or `module` is set. A check step proves a state;
    # a module step runs another pack's runbook inline at this position (the
    # composition primitive).
    check: Optional[Check] = None
    module: Optional[str] = None  # ref to another pack, e.g. "gbrain-windows"
    on_fail: Optional[str] = None  # concrete prescribed fix; None -> stop on red
    teach: Optional[str] = None


@dataclass(frozen=True)
class Pack:
    name: str
    version: str
    steps: "list[Step]"


# --------------------------------------------------------------------------- #
# Run results
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class StepOutcome:
    step_id: str
    # "pass"       -> green first try
    # "remediated" -> red, on_fail applied, green on re-check
    # "failed"     -> still red after remediation (or no on_fail) -> stop point
    status: str
    reason: str
    output: str


@dataclass(frozen=True)
class RunResult:
    passed: bool
    outcomes: "list[StepOutcome]" = field(default_factory=list)
    stopped_at: Optional[str] = None  # step id where the run stopped, if failed


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def build_pack(data: dict) -> Pack:
    """Turn parsed YAML into a validated Pack, or raise PackValidationError.

    Validates the whole thing before anything runs: required fields, known
    check types, content checks have `expect`, regexes compile, ids are unique.
    """
    if not isinstance(data, dict):
        raise PackValidationError("pack must be a mapping (name/version/steps)")

    name = data.get("name")
    version = data.get("version")
    if not name or not isinstance(name, str):
        raise PackValidationError("pack is missing a string `name`")
    if not version or not isinstance(version, str):
        raise PackValidationError(f"pack {name!r} is missing a string `version`")

    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise PackValidationError(f"pack {name!r} must have a non-empty `steps` list")

    steps: list[Step] = []
    seen_ids: set[str] = set()
    for i, raw in enumerate(raw_steps):
        step = _build_step(raw, index=i, pack_name=name)
        if step.id in seen_ids:
            raise PackValidationError(
                f"pack {name!r}: duplicate step id {step.id!r}"
            )
        seen_ids.add(step.id)
        steps.append(step)

    return Pack(name=name, version=version, steps=steps)


def _build_step(raw: object, index: int, pack_name: str) -> Step:
    where = f"pack {pack_name!r} step #{index + 1}"
    if not isinstance(raw, dict):
        raise PackValidationError(f"{where}: each step must be a mapping")

    step_id = raw.get("id")
    if not step_id or not isinstance(step_id, str):
        raise PackValidationError(f"{where}: missing a string `id`")

    instruction = raw.get("instruction")
    if not instruction or not isinstance(instruction, str):
        raise PackValidationError(f"{where} ({step_id!r}): missing a string `instruction`")

    # A step is EITHER a check step or a module step -- exactly one.
    has_check = "check" in raw
    has_module = "module" in raw
    if has_check == has_module:
        raise PackValidationError(
            f"{where} ({step_id!r}): a step must have exactly one of "
            f"`check` or `module`"
        )

    if has_module:
        module_ref = raw.get("module")
        if not module_ref or not isinstance(module_ref, str):
            raise PackValidationError(
                f"{where} ({step_id!r}): `module` must be a non-empty string"
            )
        return Step(
            id=step_id,
            instruction=instruction,
            module=module_ref,
            teach=raw.get("teach"),
        )

    raw_check = raw.get("check")
    if not isinstance(raw_check, dict):
        raise PackValidationError(f"{where} ({step_id!r}): `check` must be a mapping")

    check = _build_check(raw_check, where=f"{where} ({step_id!r})")

    return Step(
        id=step_id,
        instruction=instruction,
        check=check,
        on_fail=raw.get("on_fail"),
        teach=raw.get("teach"),
    )


def _build_check(raw: dict, where: str) -> Check:
    ctype = raw.get("type")
    if ctype not in KNOWN_CHECK_TYPES:
        raise PackValidationError(
            f"{where}: check type {ctype!r} is not one of {sorted(KNOWN_CHECK_TYPES)}"
        )

    fixture = raw.get("fixture")
    cmd = raw.get("cmd")
    # A live check needs a command; a fixture check supplies output directly.
    if fixture is None and (not cmd or not isinstance(cmd, str)):
        raise PackValidationError(f"{where}: check needs a `cmd` (or a `fixture`)")

    expect = raw.get("expect")
    # Content checks must have something to match against. Reuse the matcher's
    # own rule by doing a dry validation match against empty output; it raises
    # ValueError (missing expect / bad regex) which we surface as a recipe error.
    try:
        match(ctype, expect, "", 0)
    except UnknownCheckType:  # pragma: no cover -- already guarded above
        raise
    except ValueError as exc:
        raise PackValidationError(f"{where}: {exc}") from exc

    return Check(type=ctype, cmd=cmd or "", expect=expect, fixture=fixture)


def load_pack(path: "str | Path") -> Pack:
    """Load and validate a pack.yaml from disk."""
    import yaml  # local import: keeps matcher/runner import-light for tests

    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return build_pack(data)


def make_disk_resolver(registry_root: "str | Path") -> PackResolver:
    """A resolver that loads modules from ``<registry_root>/<ref>/pack.yaml``."""
    root = Path(registry_root)

    def resolve(ref: str) -> Pack:
        return load_pack(root / ref / "pack.yaml")

    return resolve


# --------------------------------------------------------------------------- #
# The run loop (escape hatch)
# --------------------------------------------------------------------------- #


def _shell_executor(cmd: str) -> "tuple[str, int]":
    """Default executor: run a command, capture stdout+stderr, return (out, rc)."""
    proc = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return (proc.stdout + proc.stderr), proc.returncode


def _run_check(check: Check, executor: Executor) -> "tuple[str, int]":
    """Get the output+rc for a check: a fixture short-circuits the command."""
    if check.fixture is not None:
        return check.fixture, 0
    return executor(check.cmd)


def run_pack(
    pack: Pack,
    executor: Executor = _shell_executor,
    resolver: Optional[PackResolver] = None,
    apply_fixes: bool = True,
    _depth: int = 0,
    _id_prefix: str = "",
) -> RunResult:
    """Run every step; stop at the first step that stays red after remediation.

    `apply_fixes` is the verify/remediate distinction:
      - True  (remediate): a red check applies its on_fail ONCE, then re-checks.
      - False (verify): read-only -- a red check stops immediately, nothing on
        the machine is changed. `verify` must never mutate your system.

    Escape hatch (apply_fixes=True): a step is remediated at most ONCE. Still red
    after that (or no on_fail to try) -> stop with "human needed at step N".
    Never loops, never improvises past a red gate -- that would reintroduce the
    exact drift the product exists to prevent.

    Modules: a module step loads the referenced pack (via `resolver`) and runs
    its steps inline, id-prefixed with "<ref>/". One level of nesting only
    (v1); a module that itself contains a module raises PackCompositionError.

    The `_depth` / `_id_prefix` args are internal recursion state -- callers
    pass only pack / executor / resolver / apply_fixes.
    """
    outcomes: list[StepOutcome] = []

    for step in pack.steps:
        if step.module is not None:
            sub_result = _run_module(step, executor, resolver, apply_fixes, _depth)
            outcomes.extend(sub_result.outcomes)  # already id-prefixed
            if not sub_result.passed:
                return RunResult(False, outcomes, stopped_at=sub_result.stopped_at)
            continue

        full_id = f"{_id_prefix}{step.id}"
        assert step.check is not None  # validation guarantees check xor module
        output, rc = _run_check(step.check, executor)
        result = match(step.check.type, step.check.expect, output, rc)

        if result.passed:
            outcomes.append(StepOutcome(full_id, "pass", result.reason, output))
            continue

        # Red. Try the one prescribed fix, if any -- but only in remediate mode.
        if apply_fixes and step.on_fail:
            executor(step.on_fail)  # apply the fix
            output, rc = _run_check(step.check, executor)  # re-check
            result = match(step.check.type, step.check.expect, output, rc)
            if result.passed:
                outcomes.append(
                    StepOutcome(full_id, "remediated", result.reason, output)
                )
                continue

        # Still red (or nothing to try, or read-only verify) -> STOP.
        outcomes.append(StepOutcome(full_id, "failed", result.reason, output))
        return RunResult(passed=False, outcomes=outcomes, stopped_at=full_id)

    return RunResult(passed=True, outcomes=outcomes, stopped_at=None)


def _run_module(
    step: Step,
    executor: Executor,
    resolver: Optional[PackResolver],
    apply_fixes: bool,
    depth: int,
) -> RunResult:
    """Load and run a module step's referenced pack inline (one level deep)."""
    if depth >= 1:
        raise PackCompositionError(
            f"module {step.module!r} is nested too deep; v1 allows one level "
            f"(a module may not include modules)"
        )
    if resolver is None:
        raise PackCompositionError(
            f"step {step.id!r} references module {step.module!r}, but run_pack "
            f"was called without a resolver to load it"
        )
    sub_pack = resolver(step.module)  # may raise (missing pack) -> surfaces loudly
    return run_pack(
        sub_pack,
        executor,
        resolver,
        apply_fixes=apply_fixes,
        _depth=depth + 1,
        _id_prefix=f"{step.module}/",
    )


def expand_steps(
    pack: Pack,
    resolver: Optional[PackResolver] = None,
    _depth: int = 0,
    _id_prefix: str = "",
) -> "list[dict]":
    """Flatten a pack's steps into an ordered narration list for teach mode.

    Module steps expand into their sub-steps (id-prefixed), so teach walks the
    full sequence a recipient will actually go through. Read-only: runs nothing.
    """
    out: list[dict] = []
    for step in pack.steps:
        if step.module is not None:
            if _depth >= 1:
                raise PackCompositionError(
                    f"module {step.module!r} is nested too deep; v1 allows one level"
                )
            if resolver is None:
                raise PackCompositionError(
                    f"step {step.id!r} references module {step.module!r}, but no "
                    f"resolver was given"
                )
            out.append(
                {
                    "id": f"{_id_prefix}{step.id}",
                    "instruction": step.instruction,
                    "kind": "module",
                    "module": step.module,
                }
            )
            out.extend(
                expand_steps(
                    resolver(step.module),
                    resolver,
                    _depth=_depth + 1,
                    _id_prefix=f"{step.module}/",
                )
            )
            continue
        out.append(
            {
                "id": f"{_id_prefix}{step.id}",
                "instruction": step.instruction,
                "kind": "check",
                "teach": step.teach,
                "on_fail": step.on_fail,
            }
        )
    return out
