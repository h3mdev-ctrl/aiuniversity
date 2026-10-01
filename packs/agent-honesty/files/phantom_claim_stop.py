#!/usr/bin/env python3
"""
phantom_claim_stop.py -- Stop-hook adapter for phantom_claim_lint.py (opt-in).

THE GAP THIS CLOSES
-------------------
phantom_claim_lint.py lints TEXT ("Done -- pushed the fix."). A Stop hook does not
receive the reply text: Claude Code passes JSON such as
    {"session_id": "...", "transcript_path": ".../session.jsonl",
     "stop_hook_active": false}
Register the linter on Stop directly and it lints that JSON envelope, not what the
model said -- it never fires on a real claim. This adapter reads the transcript,
pulls out the reply the user actually sees, and hands THAT to the linter.

WHAT COUNTS AS "THE REPLY"
--------------------------
Every assistant text block AFTER the last tool result in the transcript. A final
reply is often split by tool calls ("Checking..." -> tool -> "Done: ..."); taking
only the last text block misses the claim, and taking the whole session would let
evidence from an hour ago clear a fresh, unbacked claim. Subagent (sidechain)
entries are skipped -- they are not the reply.

CONTRACT
  stdin : Stop-hook JSON
  exit 0: no unevidenced claim, OR anything unexpected (fail OPEN -- a broken
          adapter must never trap a session)
  exit 2: (block mode only) unevidenced completion claim; the reason goes to
          stderr, which Claude Code feeds back to the model so it revises
  If stop_hook_active is true (Claude is already continuing because of a Stop
  hook) it exits 0 -- one nudge per reply, never a loop.

TWO MODES -- WARN IS THE DEFAULT, AND THAT IS MEASURED, NOT CAUTION
---------------------------------------------------------------------
Replayed over 633 real final replies from 40 sessions, the linter flagged 67
(10.6%), and a hand-check of a sample found most of them false alarms: "the
microphone is released" with PIDs listed, "a published study", "Merged PRs: 94"
as a table label. Blocking at that rate interrupts about one reply in ten, mostly
wrongly -- and a guard that is wrong that often gets switched off (GUARD_DESIGN
rule 3). So:
  warn  (default) never blocks: prints a one-line systemMessage for the USER and
        appends the finding to <home>/state/phantom_claim_stop.jsonl, so its real
        precision can be measured before anyone turns it up
  block           exit 2 as above; opt in with PHANTOM_STOP_MODE=block once the
                  log shows the flags are mostly real

Env: PHANTOM_STOP_MODE=warn|block, PHANTOM_STOP_DISABLE=1 (off without
unregistering). Home = $CLAUDE_HOME or ~/.claude.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


def _is_tool_result(entry: dict) -> bool:
    content = (entry.get("message") or {}).get("content")
    return isinstance(content, list) and any(
        isinstance(c, dict) and c.get("type") == "tool_result" for c in content)


def final_reply_text(transcript_path: str) -> str:
    """Assistant text after the last tool result (or after the last user turn)."""
    blocks: list[str] = []
    with open(transcript_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict) or entry.get("isSidechain"):
                continue
            kind = entry.get("type")
            if kind == "user":
                # A tool result OR a new user prompt both end the previous run of
                # reply text; only text written after it is the final reply.
                blocks = []
            elif kind == "assistant":
                content = (entry.get("message") or {}).get("content")
                if isinstance(content, str):
                    blocks.append(content)
                elif isinstance(content, list):
                    blocks += [c.get("text", "") for c in content
                               if isinstance(c, dict) and c.get("type") == "text"]
    return "\n".join(b for b in blocks if b).strip()


def _log(payload: dict, findings: list, text: str) -> None:
    """Append one line per flag, so warn mode builds its own precision data."""
    try:
        import time
        home = pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))
        p = home / "state" / "phantom_claim_stop.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "session_id": payload.get("session_id"),
                                "mode": os.environ.get("PHANTOM_STOP_MODE", "warn"),
                                "findings": findings[:6], "excerpt": text[:300]},
                               ensure_ascii=False) + "\n")
    except Exception:
        pass


def main() -> int:
    if os.environ.get("PHANTOM_STOP_DISABLE", "").strip() in ("1", "true", "yes"):
        return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict) or payload.get("stop_hook_active"):
            return 0
        tp = payload.get("transcript_path")
        if not (isinstance(tp, str) and tp and os.path.isfile(tp)):
            return 0
        text = final_reply_text(tp)
        if not text:
            return 0
        import phantom_claim_lint as lint
        findings = lint.lint(text)
    except Exception:
        return 0                                  # fail open, always
    if not findings:
        return 0
    claims = "; ".join(f"{label}: \"{phrase}\"" for label, phrase in findings[:4])
    _log(payload, findings, text)
    if os.environ.get("PHANTOM_STOP_MODE", "warn").strip().lower() != "block":
        # warn: visible to the user, never blocks, never re-prompts the model.
        print(json.dumps({"systemMessage":
                          f"phantom-claim (warn): unevidenced claim(s) -- {claims}"}))
        return 0
    sys.stderr.write(
        "agent-honesty (no-phantom-done): your reply claims something happened but "
        f"shows no receipt -- {claims}. Either show the evidence (the command's output, "
        "an exit code, a commit SHA, a test tally, a PR/run link) or reword the claim "
        "to what you actually verified. If it really is verified, add the receipt.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
