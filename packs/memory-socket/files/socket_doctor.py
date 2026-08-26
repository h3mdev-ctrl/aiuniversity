#!/usr/bin/env python3
"""
socket_doctor.py -- audit which MEMORY SOCKETS are wired on this machine.

A "socket" is a point in the agent lifecycle where memory attaches. The store
(files, index, doctor) is what the `memory` pack builds. This audits the WIRING:
whether anything is actually plugged into each lifecycle point, and -- more
importantly -- whether what IS plugged in still WORKS.

The distinction that matters:
  REGISTERED  a hook command is listed in settings.json          (cheap, weak)
  LIVE        that command runs and produces output on a probe   (real proof)

A registered-but-silent hook is the worst state: it looks installed on every
audit and does nothing. This tool separates the two on purpose.

USAGE
  python socket_doctor.py --list                 human table of all sockets
  python socket_doctor.py --check                exit 0 iff every REQUIRED socket is wired
  python socket_doctor.py --socket recall        check exactly one socket
  python socket_doctor.py --probe recall         EXECUTE it and prove it emits
  python socket_doctor.py --json                 machine-readable

EXIT CODES
  0  asked-for sockets are wired (and, for --probe, live)
  1  a required socket is dark
  2  settings.json missing or unreadable
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

# --------------------------------------------------------------------------
# The socket table. This IS the teaching content: the lifecycle points a memory
# system attaches to, what each is for, and why you would care.
#
# `hermes` names the equivalent MemoryProvider method in nousresearch/hermes-agent,
# so you can read their implementation of the same idea.
# --------------------------------------------------------------------------
SOCKETS = {
    "recall": {
        "event": "UserPromptSubmit",
        "hermes": "prefetch / queue_prefetch",
        "required": True,
        "why": "Retrieve memories relevant to THIS prompt, before the model answers. "
               "Without it your memory is a library nobody walks into.",
        # `cwd` is filled in at runtime -- see _probe_payload(). A recall hook
        # worth having resolves memory PER PROJECT, so a probe that passes a
        # placeholder cwd gets correctly refused and then reports the hook as
        # dark. That is the probe lying, not the hook failing.
        "probe_stdin": {"prompt": "how do I set up the memory index",
                        "session_id": "probe"},
    },
    "identity": {
        "event": "SessionStart",
        "hermes": "USER.md injection",
        "required": True,
        "why": "Inject the always-on user model. A model of the user is relevant to "
               "EVERY turn, so retrieval is the wrong delivery mechanism -- it would "
               "only fire when the user happened to talk about themselves.",
        "probe_stdin": {"session_id": "probe", "source": "startup"},
    },
    "salvage": {
        "event": "PreCompact",
        "hermes": "on_pre_compress(messages) -> str",
        "required": False,
        "why": "Distil the messages compaction is about to DISCARD. Static rules "
               "survive compaction; the session's measurements and decisions do not, "
               "unless something salvages them first.",
        "probe_stdin": {"session_id": "probe", "transcript_path": "",
                        "trigger": "manual"},
    },
    "restore": {
        "event": "PostCompact",
        "hermes": "(paired with on_pre_compress)",
        "required": False,
        "why": "Re-inject what salvage saved. Salvage without restore writes a file "
               "nobody reads.",
        "probe_stdin": {"session_id": "probe"},
    },
    "delegate": {
        "event": "SubagentStop",
        "hermes": "on_delegation",
        "required": False,
        "why": "Capture what a subagent learned. Subagent context is discarded whole "
               "when it returns -- whatever it discovered dies with it.",
        "probe_stdin": {"session_id": "probe", "subagent_type": "probe",
                        "prompt": "probe task", "result": "probe result"},
    },
    "harvest": {
        "event": "SessionEnd",
        "hermes": "on_session_end(messages)",
        "required": False,
        "why": "Queue the finished session for memory extraction at the boundary, "
               "instead of waiting for a batch sweep to notice it hours later.",
        "probe_stdin": {"session_id": "probe", "reason": "clear"},
    },
}

PROBE_TIMEOUT_S = 20


def claude_home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CLAUDE_HOME")
                        or (pathlib.Path.home() / ".claude"))


def load_settings() -> dict | None:
    p = claude_home() / "settings.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def commands_for(settings: dict, event: str) -> list[str]:
    """Every hook command registered on an event, flattened across matcher groups."""
    out = []
    for grp in (settings.get("hooks") or {}).get(event, []) or []:
        for entry in (grp.get("hooks") or []):
            cmd = entry.get("command")
            if cmd:
                out.append(cmd)
    return out


def audit(settings: dict) -> dict:
    return {
        name: {**meta, "commands": commands_for(settings, meta["event"])}
        for name, meta in SOCKETS.items()
    }


def _probe_payload(name: str) -> str:
    """Build the probe's stdin, reproducing the REAL invocation conditions.

    THE LESSON THIS ENCODES: a probe that does not match how the harness really
    calls the hook produces a confident wrong answer. The first version of this
    file sent `cwd: "."`; the recall hook correctly refused to serve one
    project's memories to another directory, emitted nothing, and the doctor
    reported a healthy hook as DARK. A probe must reproduce the real call, or it
    is measuring itself.
    """
    payload = dict(SOCKETS[name].get("probe_stdin") or {})
    payload.setdefault("cwd", os.getcwd())
    return json.dumps(payload)


def probe(name: str, settings: dict) -> tuple[bool, str]:
    """Actually EXECUTE the socket's hook and prove it emits something.

    This is the difference between an audit that says "installed" and one that
    says "working". A hook whose script was deleted, whose interpreter path went
    stale, or which silently early-returns is REGISTERED and useless -- and only
    running it tells you that.
    """
    meta = SOCKETS[name]
    cmds = commands_for(settings, meta["event"])
    if not cmds:
        return False, f"nothing registered on {meta['event']}"

    payload = _probe_payload(name)
    emitted, failures = [], []
    for cmd in cmds:
        try:
            proc = subprocess.run(cmd, shell=True, input=payload,
                                  capture_output=True, encoding="utf-8",
                                  errors="replace", timeout=PROBE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            failures.append(f"timeout after {PROBE_TIMEOUT_S}s: {cmd[:60]}")
            continue
        except OSError as e:
            failures.append(f"could not run: {e!r}")
            continue
        # A hook that exits non-zero is broken regardless of output: on most
        # events a non-zero exit is either ignored (wasted) or BLOCKING (worse).
        if proc.returncode != 0:
            failures.append(f"exit {proc.returncode}: "
                            f"{(proc.stderr or '').strip()[:120]}")
            continue
        if (proc.stdout or "").strip():
            emitted.append(cmd)

    if emitted:
        return True, f"{len(emitted)}/{len(cmds)} registered hook(s) emitted output"
    if failures:
        return False, "; ".join(failures[:2])
    # Ran clean but said nothing. For a memory socket that is a real failure --
    # silence means the store is empty, the path is wrong, or an exception was
    # swallowed. It is NOT proof of health.
    return False, (f"{len(cmds)} hook(s) ran and exited 0 but emitted NOTHING. "
                   f"Either a silent hook (looks installed, does nothing) OR the "
                   f"probe ran somewhere the store does not resolve -- cwd was "
                   f"{os.getcwd()}. Re-probe from a project that HAS memory "
                   f"before concluding the hook is broken.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--socket")
    ap.add_argument("--probe")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    for n in (a.socket, a.probe):
        if n and n not in SOCKETS:
            print(f"unknown socket {n!r}; known: {', '.join(SOCKETS)}")
            return 2

    settings = load_settings()
    if settings is None:
        print(f"FATAL: cannot read {claude_home() / 'settings.json'}")
        return 2

    state = audit(settings)

    if a.json:
        print(json.dumps({k: {"event": v["event"], "required": v["required"],
                              "wired": bool(v["commands"]),
                              "n": len(v["commands"])}
                          for k, v in state.items()}, indent=2))
        return 0

    if a.probe:
        ok, detail = probe(a.probe, settings)
        print(f"{'LIVE' if ok else 'DARK'}  {a.probe} "
              f"({SOCKETS[a.probe]['event']}): {detail}")
        return 0 if ok else 1

    if a.socket:
        wired = bool(state[a.socket]["commands"])
        print(f"{'WIRED' if wired else 'DARK '} {a.socket} "
              f"({SOCKETS[a.socket]['event']}): "
              f"{len(state[a.socket]['commands'])} hook(s)")
        if not wired:
            print(f"  why it matters: {SOCKETS[a.socket]['why']}")
        return 0 if wired else 1

    # --list / --check share the table; only the exit code differs.
    print(f"{'SOCKET':10s} {'EVENT':17s} {'REQ':4s} {'STATE':6s} HOOKS")
    print("-" * 62)
    missing_required = 0
    for name, v in state.items():
        wired = bool(v["commands"])
        if v["required"] and not wired:
            missing_required += 1
        print(f"{name:10s} {v['event']:17s} "
              f"{'yes' if v['required'] else 'no':4s} "
              f"{'wired' if wired else 'DARK':6s} {len(v['commands'])}")
    wired_n = sum(1 for v in state.values() if v["commands"])
    print("-" * 62)
    print(f"{wired_n}/{len(state)} sockets wired; "
          f"{missing_required} required socket(s) dark")
    if not a.check:
        print("\nNote: 'wired' means REGISTERED, not proven. Run --probe <socket> "
              "to execute one and\nconfirm it actually emits -- a silent hook "
              "passes every registration audit.")
    return 1 if (a.check and missing_required) else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
