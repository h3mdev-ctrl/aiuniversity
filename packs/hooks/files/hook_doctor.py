#!/usr/bin/env python
"""hook_doctor -- is every registered hook actually alive?

    python ~/.claude/hook_doctor.py            # check every registered hook
    python ~/.claude/hook_doctor.py --verbose  # show each probe's result
    python ~/.claude/hook_doctor.py --json

WHY THIS EXISTS
---------------
On 2026-08-27/28 two hooks were dead at once and neither announced it:

  * memory_recall's `retrieval_count` update had been throwing
    `no such column: fact_id` into a bare `except` for WEEKS. The counter read
    0, which is exactly what a counter for something that never happened reads.
  * windows_quirk_guard crashed with `AttributeError: 'function' object has no
    attribute 'search'` on EVERY Bash/Write/Edit call, because a deploy claimed
    to patch the dispatch loop and silently missed its anchor. PreToolUse treats
    the resulting exit 1 as a non-blocking error, so work continued and nothing
    looked wrong. Found by accident, reading an unrelated line.

Both are the same defect class: **a broken hook and a hook with nothing to say
are indistinguishable from the outside.** Silence is the success signal AND the
failure signal. The only way to tell them apart is to feed the hook an input you
KNOW should produce a reaction, and check that it reacts.

WHAT IT CHECKS (in order, cheapest first)
-----------------------------------------
  1. REGISTERED  -- the command in settings.json parses to a real script path
  2. EXISTS      -- that file is on disk
  3. COMPILES    -- it is valid python (catches a half-applied patch)
  4. RESPONDS    -- fed a BENIGN synthetic payload for its event, it exits 0 or
                    2 and prints no traceback

Step 4 is the one that would have caught both bugs. A hook that crashes on a
payload with nothing wrong in it is broken, whatever its exit code claims.

WHAT IT DOES NOT CHECK
----------------------
That a guard BLOCKS what it should block. That needs a per-hook positive
control, which belongs in each hook's own selftest -- the doctor is the
liveness layer, not the correctness layer. A hook can pass the doctor and still
have a useless matcher. Both matter; this is the cheap one you can run every
time.
"""
from __future__ import annotations
import json, pathlib, re, subprocess, sys, shlex

HOME = pathlib.Path.home()
SETTINGS = HOME / ".claude" / "settings.json"
VERBOSE = "--verbose" in sys.argv
AS_JSON = "--json" in sys.argv

# A deliberately BENIGN payload per event. Nothing here should trip any guard,
# so a non-zero-and-not-2 exit, or any traceback, is the hook's own fault.
PROBES: dict[str, list[dict]] = {
    "PreToolUse": [
        {"tool_name": "Bash", "tool_input": {"command": "git status --short"}},
        {"tool_name": "Read", "tool_input": {"file_path": str(HOME / "README.md")}},
        {"tool_name": "Write", "tool_input": {"file_path": str(HOME / "notes.md"),
                                              "content": "hello\n"}},
        {"tool_name": "Edit", "tool_input": {"file_path": str(HOME / "notes.md"),
                                             "old_string": "a", "new_string": "b"}},
    ],
    "PostToolUse": [
        {"tool_name": "Bash", "tool_input": {"command": "git status --short"},
         "tool_response": {"stdout": "", "exit_code": 0}},
    ],
    "UserPromptSubmit": [{"prompt": "what is the status of the build"}],
    "Stop":            [{"stop_hook_active": False}],
    "SubagentStop":    [{"stop_hook_active": False}],
    "SessionStart":    [{"source": "startup"}],
    "SessionEnd":      [{"reason": "clear"}],
    "PreCompact":      [{"trigger": "manual"}],
    "PostCompact":     [{"trigger": "manual"}],
    "Notification":    [{"message": "probe"}],
    "PreToolBatch":    [{"tool_calls": []}],
    "PostToolBatch":   [{"tool_calls": []}],
}

OK, WARN, BAD = "ok", "warn", "BROKEN"


def script_path(command: str) -> pathlib.Path | None:
    """Pull the .py out of a hook command line, however it is quoted."""
    try:
        parts = shlex.split(command, posix=False)
    except ValueError:
        parts = command.split()
    for p in parts:
        q = p.strip('"').strip("'")
        if q.lower().endswith(".py"):
            return pathlib.Path(q).expanduser()
    return None


def probe(cmd: str, payload: dict, timeout: int = 25):
    """Run the real hook command with a payload on stdin. Bytes in, bytes out --
    text mode would route stdin through cp1252 on this box and hang the writer
    thread on any non-ASCII, which is itself one of the bugs this box has."""
    try:
        parts = shlex.split(cmd, posix=False)
        parts = [p.strip('"') for p in parts]
        r = subprocess.run(parts, input=json.dumps(payload).encode("utf-8"),
                           capture_output=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return None, f"TIMEOUT after {timeout}s"
    except Exception as exc:                                  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def main() -> int:
    if not SETTINGS.is_file():
        print(f"! no settings.json at {SETTINGS}")
        return 1
    try:
        doc = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"! settings.json is not valid JSON: {exc}")
        return 1

    findings, rows = [], []
    for event, entries in (doc.get("hooks") or {}).items():
        for entry in entries or []:
            matcher = entry.get("matcher")
            for h in entry.get("hooks", []) or []:
                cmd = str(h.get("command") or "")
                sp = script_path(cmd)
                name = sp.name if sp else (cmd.split()[0][:36] if cmd else "?")
                rec = {"event": event, "matcher": matcher, "hook": name,
                       "command": cmd, "status": OK, "detail": ""}

                if sp is None:
                    rec.update(status=WARN, detail="no .py in command (not probed)")
                    rows.append(rec); continue
                if not sp.is_file():
                    rec.update(status=BAD, detail=f"file missing: {sp}")
                    rows.append(rec); continue
                try:
                    compile(sp.read_text(encoding="utf-8", errors="replace"),
                            str(sp), "exec")
                except SyntaxError as exc:
                    rec.update(status=BAD, detail=f"does not compile: {exc}")
                    rows.append(rec); continue

                probes = PROBES.get(event)
                if not probes:
                    rec.update(status=WARN, detail=f"no probe defined for {event}")
                    rows.append(rec); continue

                bad = []
                for pl in probes:
                    payload = dict(pl)
                    payload.setdefault("session_id", "hook-doctor-probe")
                    payload.setdefault("transcript_path", "")
                    payload.setdefault("cwd", str(pathlib.Path.cwd()))
                    payload.setdefault("hook_event_name", event)
                    rc, out = probe(cmd, payload)
                    label = payload.get("tool_name") or event
                    if rc is None:
                        bad.append(f"{label}: {out}")
                    elif "Traceback" in out:
                        last = [l for l in out.strip().splitlines() if l.strip()][-1:]
                        bad.append(f"{label}: CRASH rc={rc} {last[0][:70] if last else ''}")
                    elif rc not in (0, 2):
                        bad.append(f"{label}: unexpected rc={rc}")
                    elif VERBOSE:
                        print(f"    · {event}/{label}: rc={rc}")
                if bad:
                    rec.update(status=BAD, detail="; ".join(bad[:3]))
                rows.append(rec)

    if AS_JSON:
        print(json.dumps(rows, indent=2))
        return 1 if any(r["status"] == BAD for r in rows) else 0

    width = max((len(r["hook"]) for r in rows), default=10)
    print("=" * 78)
    print("HOOK DOCTOR")
    print("=" * 78)
    cur = None
    for r in sorted(rows, key=lambda r: (r["event"], r["hook"])):
        if r["event"] != cur:
            cur = r["event"]
            print(f"\n{cur}")
        mark = {OK: "  ok  ", WARN: " warn ", BAD: "BROKEN"}[r["status"]]
        m = f" [{r['matcher']}]" if r["matcher"] else ""
        print(f"  {mark}  {r['hook']:<{width}}{m}")
        if r["detail"]:
            print(f"          {r['detail'][:150]}")

    n_bad = sum(1 for r in rows if r["status"] == BAD)
    n_warn = sum(1 for r in rows if r["status"] == WARN)
    print()
    print("-" * 78)
    print(f"{len(rows)} registered hooks: {len(rows)-n_bad-n_warn} ok, "
          f"{n_warn} not probed, {n_bad} BROKEN")
    if n_bad:
        print("\nA BROKEN hook is not merely silent -- for PreToolUse an unexpected exit")
        print("is a NON-BLOCKING error, so the tool call proceeds unguarded.")
    print("VERDICT:", "HEALTHY" if not n_bad else "BROKEN")
    return 1 if n_bad else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
