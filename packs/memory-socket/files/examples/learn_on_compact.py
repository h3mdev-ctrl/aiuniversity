#!/usr/bin/env python3
"""
SOCKET: learn             EVENT: PreCompact (and again at wrap-up)
Hermes equivalent: the `fact_feedback` tool + `trust_score` in
                   plugins/memory/holographic/store.py

Close the loop: learn which memories are actually earning their place in
context, and demote the ones that are not.

WHY THIS IS THE SOCKET PEOPLE SKIP
----------------------------------
It is easy to port the trust MODEL -- `score = relevance * trust_score`, a
`min_trust` floor, +0.05 helpful / -0.10 unhelpful -- and never wire anything
that VOTES. We did exactly that. Measured on a live 607-memory store months
later: two distinct trust values, zero votes, zero prunes. The model was
decoration.

It matters because trust is how Hermes answers "should this memory fire at all".
It has NO per-query relevance gate -- `turn_context.py:1391` prefetches on every
non-trivial turn and injects whatever comes back. What stops a useless fact
reappearing forever is that repeated negative votes push it under `min_trust`.
Without votes, every false fire recurs for the life of the corpus.

WHERE THE VOTES COME FROM
-------------------------
Hermes has the model call `fact_feedback`. If you cannot rely on that, you can
INFER votes -- but only if you have both halves of the evidence:

    the log of what memory fired   +   the transcript of what happened next

Compaction is the one moment both exist together. Afterwards the second half is
gone. That is why this hangs off PreCompact.

FOUR WAYS THIS SIGNAL LIES (all four cost us a rewrite)
------------------------------------------------------
1. BENCHMARK CONTAMINATION. Anything that invokes the recall hook writes to the
   fire log, including a tuning sweep. Ours held 82 firings of one synthetic
   prompt. Scoring those punishes real memories for being ignored by a "turn"
   that had no conversation attached. Fix: only score firings that match a real
   user message in the transcript.
2. COMMON WORDS AS EVIDENCE. "Did the reply mention this memory's words?" voted
   a vendor-parity memory HELPFUL for containing "already", "first", "gate".
3. CORPUS-RARITY IS NOT INFORMATIVENESS. Filtering by document frequency looks
   like the fix, but a memory store is technical, so ordinary English comes out
   rare and scores as distinctive. It voted a memory helpful on "distinctive" --
   a word being used about something else entirely.
4. TIMEZONE. Transcript stamps were UTC, the fire log was local. A 10-hour skew
   silently misaligned every window and the whole thing still "worked". This
   version matches firings to turns by prompt TEXT, which has no clock at all.

So real evidence must look like an IDENTIFIER, not a word: it carries a digit or
underscore, or is the memory's own slug (`pgrst204`, `bm25`, `memory_recall`).
Those do not appear by coincidence.

FIVE: SCORE EACH FIRING ONCE
----------------------------
PreCompact fires more than once in a long session, and wrap-up runs this again.
Without a ledger of already-scored firings the same fire is voted on every run --
ours double-scored until the counters meant nothing. `scored.json` records each
firing's id, so a re-run over the same transcript is a no-op.

BE TIMID, AND BE REVERSIBLE
---------------------------
This is an automated writer into a hand-curated store.
  * positive votes need identifier-grade evidence
  * negative votes need N consecutive ignored firings, not one
  * never drive trust to zero -- `min_trust` already makes it unretrievable, and
    a floor of 0 means a later genuine hit can never rescue it
  * journal every run so a bad night is one `--revert` away

CONTRACT
  stdin : JSON {session_id, transcript_path, cwd}     (a PreCompact payload)
  store : <memory>/.recall/  -- the store recall_on_prompt.py writes
            fires.jsonl          read    (what fired, per prompt)
            trust.json           WRITTEN (target -> trust_score)
            misses.json          WRITTEN (consecutive ignored firings)
            scored.json          WRITTEN (firing ids already voted on)
            learn_journal.jsonl  appended: every vote's old/new, per run
  stdout: nothing. stderr: one summary line when RECALL_TRACE=1.
  exit  : ALWAYS 0 -- exit 2 on PreCompact would BLOCK compaction.
  also  : python learn_on_compact.py --revert <memory_dir>   undo the last run

`socket_doctor.py --probe learn` runs whatever is registered on PreCompact
against a synthetic store + transcript and demands that a trust value MOVED. A
voter that is wired but never votes fails it.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sys
import time

HELPFUL_DELTA = 0.05
UNHELPFUL_DELTA = -0.10
DEFAULT_TRUST = 0.50      # must match recall_on_prompt.DEFAULT_TRUST
TRUST_FLOOR = 0.05        # never 0: min_trust already hides it; 0 = no rescue
MISS_THRESHOLD = 3        # ignored firings before ONE negative vote
MAX_VOTES_PER_RUN = 40    # blast radius -- counts MUTATIONS, not observations

_IDENT_RE = re.compile(r"(?:\d|_)")


def trace(msg: str) -> None:
    if os.environ.get("RECALL_TRACE") == "1":
        print(f"trace: {msg}", file=sys.stderr)


def memory_dir(cwd: str) -> pathlib.Path | None:
    if os.environ.get("CLAUDE_MEMORY_HOME"):
        return pathlib.Path(os.environ["CLAUDE_MEMORY_HOME"])
    for base in (pathlib.Path(cwd), *pathlib.Path(cwd).parents):
        if (base / "memory" / "MEMORY.md").is_file():
            return base / "memory"
    return None


def _read_json(p: pathlib.Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else default
    except (OSError, ValueError):
        return default


def _write_json(p: pathlib.Path, data) -> None:
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, p)       # atomic: a crash mid-write never truncates the store


def prompt_key(text: str) -> str:
    """The same normalisation recall_on_prompt.log_fire applies."""
    return re.sub(r"\s+", " ", text or "").strip()[:60].lower()


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text")
    return ""


def turns(transcript: pathlib.Path) -> dict[str, str]:
    """prompt_key -> the assistant text that FOLLOWED that real user prompt.

    Only messages the user typed open a turn -- that is the anti-contamination
    filter: a firing whose prompt is not here (a benchmark, a doctor probe) is
    never scored. Matching on prompt TEXT rather than timestamps or session id
    sidesteps both the timezone skew and the re-key compaction performs.
    """
    out: dict[str, str] = {}
    current = None
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if not isinstance(o, dict) or o.get("isMeta") or o.get("isSidechain"):
            continue
        txt = _text((o.get("message") or {}).get("content"))
        if o.get("type") == "user" and txt.strip() and not txt.lstrip().startswith("<"):
            current = prompt_key(txt)
            out[current] = ""
        elif o.get("type") == "assistant" and current is not None:
            out[current] += "\n" + txt
    return out


def evidence(memdir: pathlib.Path, target: str) -> set[str]:
    """Identifier-grade terms only: the memory's own slug, or a description term
    carrying a digit or underscore. Ordinary words are never evidence."""
    ev = {target[:-3].lower() if target.endswith(".md") else target.lower()}
    p = memdir / target
    if p.is_file():
        m = re.search(r"^description:\s*(.+)$",
                      p.read_text(encoding="utf-8", errors="replace"), re.M)
        if m:
            ev |= {t for t in re.findall(r"[a-z0-9_]{4,}", m.group(1).lower())
                   if _IDENT_RE.search(t)}
    return ev


def learn(memdir: pathlib.Path, transcript: pathlib.Path) -> list[dict]:
    st = memdir / ".recall"
    fires = st / "fires.jsonl"
    if not fires.is_file() or not transcript.is_file():
        return []
    replies = turns(transcript)
    trust = _read_json(st / "trust.json", {})
    misses = _read_json(st / "misses.json", {})
    scored = set(_read_json(st / "scored.json", []))
    votes: list[dict] = []
    for line in fires.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            f = json.loads(line)
        except ValueError:
            continue
        fid = hashlib.sha1(line.encode("utf-8")).hexdigest()[:16]
        if fid in scored or f.get("prompt") not in replies:
            continue                         # already voted, or not a real turn
        scored.add(fid)
        reply = replies[f["prompt"]].lower()
        for h in f.get("hits", []):
            t = h.get("target", "")
            if not t or len(votes) >= MAX_VOTES_PER_RUN:
                continue
            if any(e in reply for e in evidence(memdir, t)):
                helpful, misses[t] = True, 0
            else:
                misses[t] = misses.get(t, 0) + 1
                if misses[t] < MISS_THRESHOLD:
                    continue                 # one ignored firing is not a verdict
                helpful, misses[t] = False, 0
            old = float(trust.get(t, DEFAULT_TRUST))
            delta = HELPFUL_DELTA if helpful else UNHELPFUL_DELTA
            new = round(max(TRUST_FLOOR, min(1.0, old + delta)), 4)
            trust[t] = new
            votes.append({"target": t, "helpful": helpful, "old": old, "new": new})
    _write_json(st / "trust.json", trust)
    _write_json(st / "misses.json", misses)
    _write_json(st / "scored.json", sorted(scored))
    if not votes:
        return votes     # journal only runs that changed something, or --revert
                         # would undo an empty re-run instead of the real one
    with open(st / "learn_journal.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": time.time(), "transcript": str(transcript),
                             "votes": votes}) + "\n")
    return votes


def revert(memdir: pathlib.Path) -> int:
    """Undo the LAST run -- but only where nothing has moved the value since.
    Restoring `old` unconditionally would destroy a newer, correct vote."""
    st = memdir / ".recall"
    journal = st / "learn_journal.jsonl"
    lines = journal.read_text(encoding="utf-8").splitlines() if journal.is_file() else []
    if not lines:
        print("nothing to revert")
        return 0
    run = json.loads(lines[-1])
    trust = _read_json(st / "trust.json", {})
    n = 0
    for v in run["votes"]:
        if abs(float(trust.get(v["target"], -1)) - v["new"]) < 1e-9:
            trust[v["target"]] = v["old"]
            n += 1
    _write_json(st / "trust.json", trust)
    journal.write_text("".join(ln + "\n" for ln in lines[:-1]), encoding="utf-8")
    print(f"reverted {n} of {len(run['votes'])} votes "
          f"({len(run['votes']) - n} skipped: moved by a later run)")
    return 0


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--revert":
        return revert(pathlib.Path(sys.argv[2]))
    try:
        data = json.loads(sys.stdin.read() or "{}")
        if not isinstance(data, dict):
            return 0
        memdir = memory_dir(str(data.get("cwd") or os.getcwd()))
        tp = str(data.get("transcript_path") or "")
        if not memdir or not tp:
            trace("learn: no store or no transcript, nothing to score")
            return 0
        votes = learn(memdir, pathlib.Path(tp))
        up = sum(v["helpful"] for v in votes)
        trace(f"learn ran, {len(votes)} votes ({up} helpful, {len(votes) - up} unhelpful)")
    except Exception as e:
        trace(f"learn FAILED: {type(e).__name__}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
