#!/usr/bin/env python
"""session_end_guard.py -- Claude Code Stop hook: don't tell the user when to stop.

Scans the assistant's most-recent response for end-of-session / "go rest" phrases and
bounces them. A builder mid-flow decides when they're done; a Claude that signs off
with "good night" / "call it a day" / "you've done enough" adds friction (it asks them
to justify continuing). Memory tells; this hook bounces.

Improvement over a naive phrase guard: it SKIPS quoted context -- phrases inside code
spans, fenced code blocks, or blockquote lines don't count. That's where a model
*quotes the rule* ("the guard bans `good night`") rather than *emits* it, so this
won't false-fire when Claude is discussing the rule itself.

Exit codes:
  0 -- clean (or the phrase only appeared quoted)
  2 -- a real (un-quoted) sign-off phrase; stderr shows to Claude next turn
"""
import json
import re
import sys

BANNED = [
    "sleep well", "good night", "goodnight", "go to sleep", "have a good night",
    "have a good rest", "get some rest", "rest well", "call it a day", "call it a night",
    "call it a session", "want to call it", "ready to call it", "wrap up here?",
    "want to wrap up", "stop here?", "stop here or keep going", "you've done plenty",
    "you've done enough", "time to rest", "get some sleep",
]


def strip_quoted(text: str) -> str:
    """Remove the places a model QUOTES the rule rather than signs off: fenced code
    blocks, inline code spans, "double-quoted" prose (straight + curly), and
    blockquote lines. Matching the remainder means a phrase only counts when it's
    genuinely part of the sign-off, not being described.

    Double quotes are the most common way to quote a phrase (`the "good night"
    sign-off`), so skipping them is essential -- reported by a real user (Jason's
    setup) as the first false positive after the backtick/blockquote fix, 2026-07-07.
    Single quotes are deliberately NOT stripped: apostrophes in contractions
    (don't, you've) would mangle the text and could hide a real violation."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)   # fenced blocks
    text = re.sub(r"`[^`]*`", " ", text)                       # inline code
    text = re.sub(r'"[^"]*"', " ", text)                       # straight double quotes
    text = re.sub("“[^”]*”", " ", text)         # curly double quotes
    text = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith(">"))
    return text


def find_violations(text: str) -> "list[str]":
    prose = strip_quoted(text).lower()
    return [p for p in BANNED if p in prose]


def extract_response_text(payload: dict) -> str:
    """Best-effort: the assistant's last response text from the Stop-hook payload.
    Handles the transcript_path shape + a few direct-key variants across versions."""
    out: list[str] = []
    tp = payload.get("transcript_path")
    if tp:
        try:
            last = ""
            with open(tp, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if ev.get("type") == "assistant":
                        for c in (ev.get("message", {}).get("content") or []):
                            if isinstance(c, dict) and c.get("type") == "text":
                                last = c.get("text", "")
            if last:
                out.append(last)
        except OSError:
            pass
    for key in ("response", "assistant_response", "last_message"):
        v = payload.get(key)
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict) and isinstance(v.get("text") or v.get("content"), str):
            out.append(v.get("text") or v.get("content"))
    return "\n".join(out)


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0   # not JSON -> don't risk a false positive
    text = extract_response_text(payload)
    if not text:
        return 0
    hits = find_violations(text)
    if not hits:
        return 0
    sys.stderr.write(
        "session_end_guard: don't tell the user when to stop -- they decide when "
        f"they're done. Detected sign-off phrase(s): {hits}. Drop the 'good night' / "
        "'get some rest' / 'call it a day' sign-off; close with what shipped + what's "
        "unblocked, then say you're ready.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
