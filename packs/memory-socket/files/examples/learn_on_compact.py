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
   silently misaligned every window and the whole thing still "worked".

So real evidence must look like an IDENTIFIER, not a word: it carries a digit or
underscore, or is the memory's own slug (`pgrst204`, `bm25`, `memory_recall`).
Those do not appear by coincidence.

BE TIMID, AND BE REVERSIBLE
---------------------------
This is an automated writer into a hand-curated store.
  * positive votes need identifier-grade evidence
  * negative votes need N consecutive ignored firings, not one
  * never drive trust to zero -- `min_trust` already makes it unretrievable, and
    a floor of 0 means a later genuine hit can never rescue it
  * journal every run so a bad night is one `--revert` away

CONTRACT
  Not a hook itself. Invoked by the PreCompact hook with the transcript path,
  and again by the wrap-up routine for sessions that never compact.
"""
from __future__ import annotations

import calendar
import json
import pathlib
import re
import sqlite3
import sys
import time

HELPFUL_DELTA = 0.05
UNHELPFUL_DELTA = -0.10
TRUST_FLOOR = 0.05
MISS_THRESHOLD = 3        # ignored firings before ONE negative vote
STRONG_DF = 2             # a term in <= this many memories can identify one
MAX_DF_FRAC = 0.04        # ...but the cut scales with corpus size
MAX_VOTES_PER_RUN = 40    # blast radius

_IDENT_RE = re.compile(r"(?:\d|_)")


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]{4,}", (text or "").lower()))


def is_identifier(term: str, target: str) -> bool:
    """Identifier-grade evidence: a digit, an underscore, or the memory's slug."""
    if _IDENT_RE.search(term):
        return True
    slug = set(re.split(r"[^a-z0-9]+", target.lower().replace(".md", "")))
    return term in slug and len(term) >= 5


def parse_utc(stamp: str) -> float:
    """Transcript timestamps are UTC. `time.mktime` would read them as LOCAL.

    That mistake is invisible: everything still runs, the windows are just
    silently wrong by your UTC offset (10-11h here). Always be explicit about
    which clock a timestamp is on.
    """
    return calendar.timegm(time.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S"))


def real_user_prompts(transcript: pathlib.Path) -> set[str]:
    """Prompts the USER actually typed -- the anti-contamination filter."""
    out: set[str] = set()
    with transcript.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("type") != "user" or o.get("isMeta") or o.get("isSidechain"):
                continue
            c = (o.get("message") or {}).get("content")
            txt = c if isinstance(c, str) else ""
            txt = re.sub(r"\s+", " ", txt).strip()
            if txt:
                out.add(txt[:60].lower())
    return out


def doc_freq(conn: sqlite3.Connection) -> tuple[dict[str, int], int]:
    """term -> how many MEMORIES use it, plus the cut for 'distinctive'."""
    per_target: dict[str, set[str]] = {}
    for r in conn.execute("SELECT target, content FROM facts"):
        per_target.setdefault(r["target"], set()).update(_terms(r["content"]))
    df: dict[str, int] = {}
    for terms in per_target.values():
        for t in terms:
            df[t] = df.get(t, 0) + 1
    return df, max(5, int(len(per_target) * MAX_DF_FRAC))


def apply_vote(conn: sqlite3.Connection, target: str, helpful: bool):
    row = conn.execute("SELECT trust_score FROM trust WHERE target=?", (target,)).fetchone()
    if row is None:
        return None
    old = row["trust_score"]
    new = max(TRUST_FLOOR, min(1.0, old + (HELPFUL_DELTA if helpful else UNHELPFUL_DELTA)))
    conn.execute("UPDATE trust SET trust_score=? WHERE target=?", (new, target))
    return old, new


def revert(conn: sqlite3.Connection, run: dict) -> int:
    """Undo a run -- but ONLY where nothing has moved the value since.

    Restoring `old` unconditionally is wrong: if a later legitimate run also
    moved that memory, this would silently destroy the newer, correct value.
    Skip and report those instead.
    """
    n = 0
    for v in run.get("votes", []):
        cur = conn.execute("SELECT trust_score FROM trust WHERE target=?",
                           (v["target"],)).fetchone()
        if cur and abs(cur["trust_score"] - v["new"]) < 1e-9:
            conn.execute("UPDATE trust SET trust_score=? WHERE target=?",
                         (v["old"], v["target"]))
            n += 1
    return n


# The blast-radius cap must count MUTATIONS, not records. Counting every
# observation (including the "watched but unchanged" ones) meant a handful of
# harmless observations could silently suppress every real vote behind them.
def cap_reached(n_mutations: int) -> bool:
    return n_mutations >= MAX_VOTES_PER_RUN


if __name__ == "__main__":
    print(__doc__)
    print("This is a teaching reference, not a runnable drop-in: the store "
          "schema is yours.\nThe parts worth copying are the four failure modes "
          "in the docstring and the\nfour guards above them.")
