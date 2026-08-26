#!/usr/bin/env python3
"""
SOCKET: harvest           EVENT: SessionEnd
Hermes equivalent: MemoryProvider.on_session_end(messages)

Queue the finished session for memory extraction at the moment it ends.

WHAT THIS IS *NOT*
------------------
It is not the extractor. Do NOT call a model here. SessionEnd runs with a budget
of roughly 1.5 seconds shared across every SessionEnd hook, and it cannot inject
context, so there is nothing to gain by doing work inline -- you would just delay
the user's shutdown. This hook's whole job is to POKE the pipeline you already
have, so a session that ends at 09:00 is queued at 09:00 instead of whenever the
batch sweep next notices it.

If you do not already have an extraction pipeline, build that first; this socket
is worth nothing on its own.

THE WINDOWS TRAP
----------------
`subprocess.run(timeout=...)` is not the guarantee it looks like. If the child
spawns a grandchild that inherits the stdout PIPE, run()'s kill path calls
communicate() a second time with NO timeout and blocks until that handle closes.
A 1.0s budget was measured blocking for 60s that way. Pass DEVNULL on all three
streams: no pipes, no inheritance, no block.

CONTRACT
  stdin : JSON {session_id, reason}   reason: clear|resume|logout|other
  stdout: nothing (SessionEnd cannot inject context)
  exit  : ALWAYS 0.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time

# Point this at YOUR extraction queue's scanner.
SCAN = pathlib.Path.home() / ".claude" / "global-evolution" / "bin" / "scan.py"
LOG = pathlib.Path.home() / ".claude" / "logs" / "harvest.log"
TIMEOUT_S = 1.0

# A session that ended to be RESUMED is still a live conversation. Queueing it
# as "finished" extracts half a thought.
SKIP_REASONS = {"resume"}


def _log(msg: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n")
    except Exception:
        pass


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
        if not isinstance(data, dict):
            return 0
        reason = str(data.get("reason") or "other")
        sid = str(data.get("session_id") or "")[:8]

        if reason in SKIP_REASONS:
            _log(f"skip session={sid} reason={reason}")
            return 0
        if not SCAN.is_file():
            _log(f"scanner missing at {SCAN}")
            return 0

        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                [sys.executable, str(SCAN), "--commit"],
                stdin=subprocess.DEVNULL,      # all three DEVNULL -- see docstring
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=TIMEOUT_S,
            )
            _log(f"session={sid} reason={reason} rc={proc.returncode} "
                 f"{(time.perf_counter() - t0) * 1000:.0f}ms")
        except subprocess.TimeoutExpired:
            # The budget wins. Your scheduled sweep is the backstop -- this hook
            # is an optimisation, never the only path.
            _log(f"session={sid} TIMEOUT after {TIMEOUT_S}s - leaving it to the sweep")
    except Exception as e:
        _log(f"error: {e!r}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
