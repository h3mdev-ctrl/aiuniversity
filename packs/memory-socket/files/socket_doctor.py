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
  DEGRADED    it produces output, but a branch it is configured to run did not
              (a fail-open `except: pass` ate it) or it spoke when it should not

A registered-but-silent hook is the worst state: it looks installed on every
audit and does nothing. A DEGRADED one is the second worst, because its output
looks exactly like a healthy hook's. We ran three stacked silent failures in a
recall hook for weeks while every check said HEALTHY -- hence the trace protocol.

USAGE
  python socket_doctor.py --list                 human table of all sockets
  python socket_doctor.py --check                exit 0 iff every REQUIRED socket is wired
  python socket_doctor.py --socket recall        check exactly one socket
  python socket_doctor.py --probe recall         EXECUTE it: per-branch trace + negative control
  python socket_doctor.py --probe learn          prove the PreCompact voter actually VOTES
  python socket_doctor.py --probe restore        salvage under session A, restore under B (the
                                                 compaction re-key): LIVE / DEAD / LEAK
  python socket_doctor.py --json                 machine-readable

TRACE PROTOCOL (recall): the probe runs the hook with RECALL_TRACE=1. A hook that
supports it prints to STDERR `trace: branches=lexical,semantic` (what it is
configured to run) and one line per branch that EXECUTED -- `trace: lexical ran,
1 hit`, `trace: semantic ran, top=0.69 gap=0.12`, or `trace: semantic SKIPPED:
ConnectionRefusedError`. Any SKIPPED/FAILED line, or a configured branch with no
`ran` line, is DEGRADED. A hook that prints no trace lines is judged on output
alone and labelled untraced.

EXIT CODES
  0  asked-for sockets are wired (and, for --probe, live / voting)
  1  a required socket is dark, or the probe is DARK / DEGRADED / NO VOTE
  2  settings.json missing or unreadable
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time

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

# Not a socket of its own (it rides PreCompact), but it has its own probe,
# because "a PreCompact hook is registered" says nothing about whether anything
# ever VOTES -- that check passed for months over a loop with zero votes.
EXTRA_PROBES = ("learn",)

PROBE_TIMEOUT_S = 20
NEGATIVE_PROMPT = "ok"          # carries no signal: a recall hook must stay silent
TRACE_RE = re.compile(r"^trace:\s*(.*)$")


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


def _probe_payload(name: str, **override) -> str:
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
    payload.update(override)
    return json.dumps(payload)


def _run(cmd: str, payload: str, env: dict | None = None, cwd: str | None = None):
    """-> (proc, None) or (None, failure text). Never raises."""
    try:
        return subprocess.run(cmd, shell=True, input=payload, capture_output=True,
                              encoding="utf-8", errors="replace",
                              timeout=PROBE_TIMEOUT_S, env=env, cwd=cwd), None
    except subprocess.TimeoutExpired:
        return None, f"timeout after {PROBE_TIMEOUT_S}s: {cmd[:60]}"
    except OSError as e:
        return None, f"could not run: {e!r}"


def traces(stderr: str) -> list[str]:
    return [m.group(1).strip() for line in (stderr or "").splitlines()
            if (m := TRACE_RE.match(line.strip()))]


def branch_problems(lines: list[str]) -> list[str]:
    """Judge one hook's trace. Empty list = every configured branch ran."""
    configured: set[str] = set()
    ran: set[str] = set()
    problems = []
    for t in lines:
        if t.startswith("branches="):
            configured |= {b.strip() for b in t[len("branches="):].split(",") if b.strip()}
        elif m := re.match(r"(\w+) ran\b", t):
            ran.add(m.group(1))
        if "SKIPPED" in t or "FAILED" in t:
            problems.append(t)
    for b in sorted(configured - ran):
        problems.append(f"{b} is configured but never reported running "
                        f"(an exception swallowed before its trace line?)")
    return problems


def probe(name: str, settings: dict) -> tuple[str, str, list[str]]:
    """Actually EXECUTE the socket's hook and prove it emits something.

    -> (state, detail, trace_lines) with state LIVE / DEGRADED / DARK.

    This is the difference between an audit that says "installed" and one that
    says "working". A hook whose script was deleted, whose interpreter path went
    stale, or which silently early-returns is REGISTERED and useless -- and only
    running it tells you that.
    """
    meta = SOCKETS[name]
    cmds = commands_for(settings, meta["event"])
    if not cmds:
        return "DARK", f"nothing registered on {meta['event']}", []

    env = dict(os.environ, RECALL_TRACE="1")
    payload = _probe_payload(name)
    emitted, failures, degraded, shown = [], [], [], []
    traced = False
    for cmd in cmds:
        proc, err = _run(cmd, payload, env)
        if err:
            failures.append(err)
            continue
        # A hook that exits non-zero is broken regardless of output: on most
        # events a non-zero exit is either ignored (wasted) or BLOCKING (worse).
        if proc.returncode != 0:
            failures.append(f"exit {proc.returncode}: "
                            f"{(proc.stderr or '').strip()[:120]}")
            continue
        lines = traces(proc.stderr)
        traced = traced or bool(lines)
        shown += lines
        degraded += branch_problems(lines)
        out = (proc.stdout or "").strip()
        if out:
            emitted.append(cmd)
        # identity: a stale user model is suppressed with a one-line notice.
        # That notice is output, but it is the alarm, not health.
        if "SUPPRESSED" in out:
            degraded.append(out.splitlines()[0][:160])

    # NEGATIVE CONTROL (recall only). A positive probe alone cannot tell a
    # discriminating hook from one that injects on everything.
    if name == "recall" and emitted:
        for cmd in cmds:
            proc, err = _run(cmd, _probe_payload(name, prompt=NEGATIVE_PROMPT), env)
            if proc is not None and proc.returncode == 0 and (proc.stdout or "").strip():
                degraded.append(f"negative control failed: injected on the trivial "
                                f"prompt {NEGATIVE_PROMPT!r} ({cmd[:50]})")

    if degraded:
        return "DEGRADED", "; ".join(degraded[:3]), shown
    if emitted:
        note = "" if traced or name != "recall" else (
            " (untraced: the hook prints no RECALL_TRACE lines, so a swallowed "
            "branch cannot be ruled out)")
        return "LIVE", (f"{len(emitted)}/{len(cmds)} registered hook(s) emitted "
                        f"output{note}"), shown
    if failures:
        return "DARK", "; ".join(failures[:2]), shown
    # Ran clean but said nothing. For a memory socket that is a real failure --
    # silence means the store is empty, the path is wrong, or an exception was
    # swallowed. It is NOT proof of health.
    return "DARK", (f"{len(cmds)} hook(s) ran and exited 0 but emitted NOTHING. "
                    f"Either a silent hook (looks installed, does nothing) OR the "
                    f"probe ran somewhere the store does not resolve -- cwd was "
                    f"{os.getcwd()}. Re-probe from a project that HAS memory "
                    f"before concluding the hook is broken."), shown


# ---- the re-key probe (salvage -> compaction -> restore) --------------------
REKEY_MARKER = "rekeycanary_7731"


def probe_rekey(settings: dict) -> tuple[str, str]:
    """Prove a salvaged carry survives the session-id change at compaction,
    and does not leak into another directory.

    -> (LIVE | DEAD | LEAK | DARK, detail)

    Replaces the old `--probe restore`, which executed only the PostCompact hook
    and reported LIVE on any output -- and the example restore hook ALWAYS
    prints boilerplate ("CONTEXT COMPACTED ..."), so it passed with the carry
    chain completely dead. Output is not evidence; the MARKER coming back is.

    Real sequence reproduced, in an isolated home (CLAUDE_HOME, HOME and
    USERPROFILE all point at a temp dir, so a hook that hard-codes
    Path.home() still cannot touch the real one):
      1. every PreCompact hook, session A, cwd = projA, transcript holds MARKER
      2. every PostCompact hook, session B (the re-key), cwd = projA
         -> MARKER must appear                          else DEAD
      3. every PostCompact hook, session C, cwd = projB (another worktree)
         -> MARKER must NOT appear                      else LEAK
    """
    pre = commands_for(settings, "PreCompact")
    post = commands_for(settings, "PostCompact")
    if not (pre and post):
        missing = " and ".join(e for e, c in (("PreCompact", pre), ("PostCompact", post)) if not c)
        return "DARK", f"nothing registered on {missing}; salvage and restore are one mechanism"
    with tempfile.TemporaryDirectory(prefix="socket_rekey_") as td:
        root = pathlib.Path(td)
        proj_a, proj_b, home, uhome = (root / n for n in ("projA", "projB", "home", "userhome"))
        for d in (proj_a, proj_b, home, uhome):
            d.mkdir()
        transcript = root / "transcript.jsonl"
        transcript.write_text("\n".join(json.dumps(o) for o in (
            {"type": "user", "message": {"role": "user", "content":
                f"measure the {REKEY_MARKER} latency and keep the number"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": f"Measured {REKEY_MARKER} at 412 ms, verified on "
                                         f"3 runs; the cold path is the root cause."}]}},
        )) + "\n", encoding="utf-8")
        env = dict(os.environ, CLAUDE_HOME=str(home), HOME=str(uhome), USERPROFILE=str(uhome))

        for cmd in pre:
            _run(cmd, json.dumps({"session_id": "probe-rekey-A", "trigger": "manual",
                                  "transcript_path": str(transcript), "cwd": str(proj_a),
                                  "hook_event_name": "PreCompact"}), env, cwd=str(proj_a))

        def restored(session: str, cwd: pathlib.Path) -> bool:
            for cmd in post:
                proc, _ = _run(cmd, json.dumps({"session_id": session, "cwd": str(cwd),
                                                "hook_event_name": "PostCompact"}),
                               env, cwd=str(cwd))
                if proc is not None and REKEY_MARKER in (proc.stdout or ""):
                    return True
            return False

        survived = restored("probe-rekey-B", proj_a)
        leaked = restored("probe-rekey-C", proj_b)

    if leaked:
        return "LEAK", ("a carry salvaged in one directory was restored into ANOTHER "
                        "(session C, different cwd). The restore hook is falling back to "
                        "a key that is not scoped to the working directory -- e.g. "
                        "'newest carry file'. That prints someone else's findings as "
                        "this session's facts. Scope the lookup to cwd.")
    if not survived:
        return "DEAD", ("salvaged under session A, restored under session B in the SAME "
                        "directory, and the carry did not come back. Claude Code "
                        "re-keys the session at compaction, so a lookup keyed only on "
                        "session_id never hits. Key it on the working directory too "
                        "(see files/examples/restore_post_compact.py).")
    return "LIVE", (f"carry survived the session re-key (A -> B, same cwd) and did not "
                    f"leak to another directory ({len(pre)} PreCompact, "
                    f"{len(post)} PostCompact hook(s))")


# ---- the learning-loop probe ------------------------------------------------
CANARY = "reference_probe_canary.md"
CANARY_ID = "probe_canary_4417"
CANARY_PROMPT = "probe: how does probe_canary_4417 work"


def _seed_learn_fixture(root: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """A throwaway store in which exactly ONE vote is owed: a memory fired on a
    real user prompt and the reply cited its identifier. Any working voter moves
    its trust. Returns (memory_dir, transcript)."""
    mem = root / "memory"
    (mem / ".recall").mkdir(parents=True)
    (mem / "MEMORY.md").write_text(f"| probe | [{CANARY}]({CANARY}) |\n", encoding="utf-8")
    (mem / CANARY).write_text(
        f"---\nname: probe-canary\ndescription: when you touch {CANARY_ID}, read this\n"
        f"type: reference\n---\nSynthetic memory written by socket_doctor --probe learn.\n",
        encoding="utf-8")
    (mem / ".recall" / "trust.json").write_text(json.dumps({CANARY: 0.5}), encoding="utf-8")
    (mem / ".recall" / "fires.jsonl").write_text(json.dumps({
        "ts": time.time(), "session_id": "probe-learn", "prompt": CANARY_PROMPT,
        "hits": [{"target": CANARY, "via": "lexical"}]}) + "\n", encoding="utf-8")
    transcript = root / "transcript.jsonl"
    transcript.write_text("\n".join(json.dumps(o) for o in (
        {"type": "user", "message": {"role": "user", "content": CANARY_PROMPT}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": f"Per the memory, {CANARY_ID} is configured by ..."}]}},
    )) + "\n", encoding="utf-8")
    return mem, transcript


def probe_learn(settings: dict) -> tuple[str, str]:
    """Run every PreCompact hook against a synthetic store and demand a VOTE.

    Registration of a PreCompact hook proves nothing about learning -- that is
    the check this replaced, and it passed over a loop with zero votes. Here the
    evidence for one helpful vote is planted; a voter that runs and moves nothing
    FAILS. The fixture lives in a temp dir (CLAUDE_MEMORY_HOME and CLAUDE_HOME
    point there), so a hook that honours them never touches your real store.
    """
    cmds = commands_for(settings, "PreCompact")
    if not cmds:
        return "NO VOTE", "nothing registered on PreCompact, so nothing can vote"
    with tempfile.TemporaryDirectory(prefix="socket_learn_") as td:
        root = pathlib.Path(td)
        mem, transcript = _seed_learn_fixture(root)
        (root / "home").mkdir()
        (root / "userhome").mkdir()
        # The probe runs the USER'S OWN PreCompact hooks, which may ignore
        # CLAUDE_HOME and write via Path.home() (measured: one did, leaving a
        # 'probe-learn' carry file in the real ~/.claude). Point HOME and
        # USERPROFILE at the temp dir too, so a hard-coded home lands here.
        env = dict(os.environ, CLAUDE_MEMORY_HOME=str(mem),
                   CLAUDE_HOME=str(root / "home"), RECALL_TRACE="1",
                   HOME=str(root / "userhome"), USERPROFILE=str(root / "userhome"))
        payload = json.dumps({"session_id": "probe-learn", "trigger": "manual",
                              "transcript_path": str(transcript), "cwd": str(root),
                              "hook_event_name": "PreCompact"})
        notes = []
        for cmd in cmds:
            proc, err = _run(cmd, payload, env)
            notes += [err] if err else traces(proc.stderr)
        try:
            after = json.loads((mem / ".recall" / "trust.json").read_text(encoding="utf-8"))
            new = float(after.get(CANARY, 0.5))
        except (OSError, ValueError) as e:
            return "NO VOTE", f"trust store unreadable after the run: {type(e).__name__}"
    if abs(new - 0.5) > 1e-9:
        return "VOTED", (f"trust on the planted helpful firing moved 0.50 -> {new:.2f} "
                         f"({len(cmds)} PreCompact hook(s) ran)")
    return "NO VOTE", (f"{len(cmds)} PreCompact hook(s) ran and no trust value moved, "
                       f"though one helpful vote was owed. The loop is decoration. "
                       + ("Trace: " + "; ".join(notes[:3]) if notes else
                          "No hook printed a learn trace line."))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--socket")
    ap.add_argument("--probe")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.socket and a.socket not in SOCKETS:
        print(f"unknown socket {a.socket!r}; known: {', '.join(SOCKETS)}")
        return 2
    if a.probe and a.probe not in (*SOCKETS, *EXTRA_PROBES):
        print(f"unknown probe {a.probe!r}; known: {', '.join((*SOCKETS, *EXTRA_PROBES))}")
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

    if a.probe == "restore":
        # A generic "did it print?" probe passes the example restore hook on
        # boilerplate alone. Restore is only meaningful as the second half of
        # salvage, across the re-key, so that is what gets probed.
        verdict, detail = probe_rekey(settings)
        print(f"{verdict}  restore (PreCompact -> PostCompact, re-keyed): {detail}")
        return 0 if verdict == "LIVE" else 1

    if a.probe == "learn":
        verdict, detail = probe_learn(settings)
        print(f"{verdict}  learn (PreCompact): {detail}")
        return 0 if verdict == "VOTED" else 1

    if a.probe:
        verdict, detail, lines = probe(a.probe, settings)
        print(f"{verdict}  {a.probe} ({SOCKETS[a.probe]['event']}): {detail}")
        for t in lines:
            print(f"    trace: {t}")
        return 0 if verdict == "LIVE" else 1

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
              "passes every registration audit.\n--probe learn proves the trust "
              "loop votes; a registered PreCompact hook does not.")
    return 1 if (a.check and missing_required) else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
