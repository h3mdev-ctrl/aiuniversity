#!/usr/bin/env python3
"""
SOCKET: delegate          EVENT: SubagentStop
Hermes equivalent: MemoryProvider.on_delegation

Capture what a subagent learned before its context is thrown away.

WHY THIS SOCKET IS THE MOST OVERLOOKED
--------------------------------------
A subagent reads twenty files, forms a conclusion, and returns a paragraph. The
twenty files -- and every dead end it ruled out -- are discarded whole when it
returns. Run four search agents a day for a week and you have thrown away most
of the actual investigation, then paid to redo it. This socket is the cheapest
memory you will ever add: the work is already done, you are just keeping it.

THE CONCURRENCY BUG YOU WILL WRITE
----------------------------------
Trimming a log looks trivial: read the lines, keep the last N, write them back.
Under parallel subagents -- which is the entire point of subagents -- another
process appends between your read and your write, and that append is destroyed.
Worse, a partial write splices two JSON records into one corrupt line. Measured
with 30 concurrent writers: one corrupt record, two lost.

The fix is not a lock. It is: append with a single atomic `write`, and ROTATE by
`os.replace()` (atomic on POSIX and Windows) instead of rewriting in place.

CONTRACT
  stdin : JSON {session_id, subagent_type, prompt, result}
  stdout: nothing
  exit  : ALWAYS 0.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time

LOG = pathlib.Path.home() / ".claude" / "state" / "subagent_findings.jsonl"
MAX_BYTES = 2_000_000
MAX_RESULT_CHARS = 4000
SCHEMA = 1


def trim(log: pathlib.Path) -> None:
    """Rotate atomically. NEVER read-modify-write a file others append to."""
    try:
        if log.stat().st_size <= MAX_BYTES:
            return
        os.replace(log, log.with_suffix(".jsonl.1"))
    except OSError:
        pass


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
        if not isinstance(data, dict):
            return 0

        result = str(data.get("result") or "")
        if not result.strip():
            return 0

        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "session": str(data.get("session_id") or "")[:8],
            "agent": str(data.get("subagent_type") or "unknown"),
            "task": str(data.get("prompt") or "")[:300],
            "result": result[:MAX_RESULT_CHARS],
            # Stamp the schema. The exact SubagentStop payload shape is not
            # documented; when you learn the real one, you need to know which
            # records predate that knowledge.
            "_schema": SCHEMA,
        }

        LOG.parent.mkdir(parents=True, exist_ok=True)
        trim(LOG)
        # ONE write call, append mode, newline included. Two writes can be
        # interleaved by another process; one usually cannot.
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
