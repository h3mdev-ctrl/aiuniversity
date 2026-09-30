#!/usr/bin/env python
"""recall_episodes_hook.py -- UserPromptSubmit hook: surface a known dead end BEFORE work starts.

Reads the hook payload ({"prompt": ..., "cwd": ...}) on stdin. If the prompt names an
IDENTIFIER (a filename, a symbol like `_SCALES`, a version like `v1.4.2`, `parser.py:344`)
that also appears in a logged episode, it injects up to 2 matching episodes as
additionalContext, wrapped in a system-reminder that says they may be stale.

It runs on EVERY prompt -- a past failure is most useful before the approach is
repeated, not only when the user asks "did we hit this before?" -- which is exactly
why it must stay quiet on ordinary English: word overlap alone never fires
(require_ident=True).

Contract as a hook:
  * ALWAYS exits 0 and never blocks the prompt (fail open).
  * Prints nothing when nothing matches.

EPISODES_TRACE=1 prints one line to STDERR per branch that executed
(`trace: episodes.search ran, 2 hits`). Why: a fail-open hook swallows its own bugs.
The original version of this integration once raised NameError inside its
`except: pass` for three weeks while every health check said HEALTHY -- the checks
proved the hook RAN and printed, not that the search branch did. The trace line is
what a probe asserts on, so "the branch ran" is proven rather than assumed.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys

K = 2
TRACE = os.environ.get("EPISODES_TRACE") == "1"


def trace(msg: str) -> None:
    if TRACE:
        try:
            print(f"trace: {msg}", file=sys.stderr)
        except Exception:
            pass


def _load_episodes_module():
    """Look beside this file first (repo copy / hooks dir), then <CLAUDE_HOME>/episodes.py."""
    here = pathlib.Path(__file__).resolve().parent
    home = pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))
    for cand in (here / "episodes.py", home / "episodes.py"):
        if cand.is_file():
            spec = importlib.util.spec_from_file_location("episodes", cand)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            trace(f"episodes module loaded from {cand}")
            return mod
    trace("episodes module NOT FOUND")
    return None


def _sanitise(text: str) -> str:
    """An episode must not be able to close the reminder and speak as the system."""
    return (text.replace("<system-reminder>", "<system_reminder>")
                .replace("</system-reminder>", "</system_reminder>"))


def build_context(prompt: str) -> str:
    eps = _load_episodes_module()
    if eps is None:
        return ""
    hits = eps.search(prompt, k=K, require_ident=True)
    trace(f"episodes.search ran, {len(hits)} hits")
    if not hits:
        return ""
    return "\n".join(
        ["<system-reminder>",
         "Structured episodes matching an identifier in this request (episodes.py). "
         "A past dead end or non-obvious fix -- check whether it applies before "
         "repeating the approach; it may be stale:",
         ""]
        + [_sanitise(eps.render(e)) for _, e in hits]
        + ["</system-reminder>"])


def main() -> int:
    trace("hook start")
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        if not isinstance(data, dict):
            trace(f"payload is {type(data).__name__}, not an object -- skipping")
            return 0
        prompt = data.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            trace("no prompt in payload -- skipping")
            return 0
        trace(f"payload parsed, prompt {len(prompt)} chars")
        ctx = build_context(prompt)
        if not ctx:
            trace("no injection")
            return 0
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": ctx,
        }}))
        trace("injected additionalContext")
    except Exception as exc:  # fail open -- but never silently under trace
        trace(f"EXCEPTION {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass
    try:
        main()
    except BaseException:
        pass
    sys.exit(0)
