#!/usr/bin/env python
"""episodes.py -- structured episodic memory: what was tried, what happened, why.

WHY THIS EXISTS
A memory system usually has two kinds of store, and neither answers "last time we
hit this, what went wrong and what fixed it?":
  * raw transcripts  -- exact, but unstructured and expensive to search.
  * curated lessons  -- feedback notes that hold the GENERALISED rule
                        ("validate every patch anchor before writing").
An episode holds the INSTANCE -- the concrete file, symbol, version, symptom, cause
and fix -- so the next session can skip straight to it. The lesson graduates to a
feedback memory; the episode stays as the searchable evidence.

What it is NOT:
  * not a rule store -- a lesson that should change behaviour belongs in a memory note
  * not a transcript  -- one record per dead end / near-miss / non-obvious fix
  * not rotated       -- episodes are small; the file stays greppable forever

Usage:
  python episodes.py --log --task "..." --tried "..." --outcome fail|partial|success \
        --why "..." [--fix "..."] [--tags a,b] [--who label]
  python episodes.py --search "<prompt or keywords>" [--k 3]
  python episodes.py --recent [N]
  python episodes.py --count            # exit 0 if >=1 real (non-probe) episode

Store: one JSON object per line in <CLAUDE_HOME>/state/episodes.jsonl
       (CLAUDE_HOME defaults to ~/.claude; EPISODES_STORE overrides the file path).
Record: {id, ts, who, task, tried, outcome, why, fix, tags}

Stdlib only. Adapted from Andrew's personal Claude setup.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
from datetime import datetime

OUTCOMES = ("fail", "partial", "success")
FIELDS = ("task", "tried", "why", "fix")
PROBE_TAG = "probe"

# Retrieval is lexical on purpose. The "didn't we already hit that?" lookup is almost
# always an exact token -- a filename, `PGRST204`, `_SCALES`, `v0.5.23.13`,
# `parser.py:344`. Identifier-shaped tokens carry the signal; ordinary English
# ("changed", "failing") coincides by accident. So identifiers weigh 3, words weigh 1,
# and a hit needs at least one identifier (or, for an explicit --search only, two
# distinctive words).
_IDENT_RE = re.compile(r"[\d_./:]")
STOP = set("""about after again also another before being could does doing done during each
every first found going having into just like made make maybe more most much need other over
really same should since some still such than that their them then there these they thing
think this those through under until very want were what when where which while will with
would your ok yes lets check fixed issue problem error work working""".split())
IDENT_WEIGHT = 3
MIN_SCORE = 2

# Episodes get injected into future prompts, so a secret written here would be
# replayed into every matching session. Refuse secret-shaped values on write.
_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{20,}"             # OpenAI/Anthropic-style keys
    r"|gh[pousr]_[A-Za-z0-9]{30,}"         # GitHub tokens
    r"|AKIA[0-9A-Z]{16}"                   # AWS access key id
    r"|xox[abprs]-[A-Za-z0-9\-]{10,}"      # Slack tokens
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"  # JWT
    r"|(?:password|passwd|secret|api[_-]?key|token)\s*[=:]\s*\S{6,})",
    re.IGNORECASE,
)


def claude_home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))


def store_path() -> pathlib.Path:
    """Resolved per call (not at import) so EPISODES_STORE / CLAUDE_HOME set later apply."""
    override = os.environ.get("EPISODES_STORE")
    if override:
        return pathlib.Path(override)
    return claude_home() / "state" / "episodes.jsonl"


def _now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")


def _who(explicit: str | None) -> str:
    if explicit:
        return explicit.strip()
    return (os.environ.get("CLAUDE_CHANNEL") or pathlib.Path.cwd().name or "claude").strip()


def tokens(text: str) -> tuple[set[str], set[str]]:
    """-> (identifier tokens, distinctive words)."""
    idents, words = set(), set()
    for tok in re.findall(r"[A-Za-z0-9_./:\-]{3,}", text or ""):
        low = tok.lower().strip("./:-")
        if len(low) < 3 or low in STOP:
            continue
        if _IDENT_RE.search(low) and len(low) >= 4:
            idents.add(low)
            # `module._SCALES` should also match a bare `_scales` mention.
            for part in re.split(r"[./:]", low):
                if len(part) >= 4 and part not in STOP:
                    idents.add(part)
        elif low.isalpha() and len(low) >= 5:
            words.add(low)
    return idents, words


def load() -> list[dict]:
    store = store_path()
    if not store.exists():
        return []
    out = []
    for line in store.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def secret_fields(values: dict) -> list[str]:
    return [k for k, v in values.items() if v and _SECRET_RE.search(str(v))]


def do_log(a: argparse.Namespace) -> int:
    missing = [f for f in ("task", "tried", "why") if not (getattr(a, f) or "").strip()]
    if missing:
        print(f"refusing to log: required field(s) empty: {', '.join(missing)}")
        return 1
    if a.outcome not in OUTCOMES:
        print(f"refusing to log: --outcome must be one of {OUTCOMES}")
        return 1
    leaked = secret_fields({f: getattr(a, f) for f in (*FIELDS, "tags")})
    if leaked:
        # Name the field, never echo the value.
        print(f"refusing to log: secret-shaped value in field(s): {', '.join(leaked)} "
              "-- describe the credential by name, not by value")
        return 1
    existing = load()
    rec = {
        "id": f"ep-{len(existing) + 1:04d}",
        "ts": _now(),
        "who": _who(a.who),
        "task": a.task.strip(),
        "tried": a.tried.strip(),
        "outcome": a.outcome,
        "why": a.why.strip(),
        "fix": (a.fix or "").strip(),
        "tags": [t.strip().lower() for t in (a.tags or "").split(",") if t.strip()],
    }
    store = store_path()
    store.parent.mkdir(parents=True, exist_ok=True)
    with store.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"logged {rec['id']} [{rec['outcome']}] {rec['task'][:80]}")
    return 0


def search(query: str, k: int = 3, episodes: list[dict] | None = None,
           require_ident: bool = False) -> list[tuple[int, dict]]:
    """require_ident=True is the mode for AUTOMATIC injection (every prompt): only an
    identifier match counts. Word-only overlap is allowed for an explicit --search,
    where a person chose to look."""
    q_id, q_w = tokens(query)
    if not q_id and not q_w:
        return []
    scored = []
    for ep in (load() if episodes is None else episodes):
        blob = " ".join(str(ep.get(f, "")) for f in FIELDS) + " " + " ".join(ep.get("tags", []))
        e_id, e_w = tokens(blob)
        id_hits = q_id & e_id
        w_hits = q_w & e_w
        score = IDENT_WEIGHT * len(id_hits) + len(w_hits)
        if id_hits or (not require_ident and len(w_hits) >= 2):
            if score >= MIN_SCORE:
                scored.append((score, ep))
    scored.sort(key=lambda x: x[1].get("ts", ""), reverse=True)   # newest first on ties
    scored.sort(key=lambda x: -x[0])                              # stable: best score first
    return scored[:k]


def render(ep: dict) -> str:
    lines = [f"[{ep.get('id')} | {str(ep.get('ts', ''))[:10]} | {ep.get('outcome')}] {ep.get('task')}",
             f"    tried: {ep.get('tried')}",
             f"    why:   {ep.get('why')}"]
    if ep.get("fix"):
        lines.append(f"    fix:   {ep.get('fix')}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="structured episodic memory")
    ap.add_argument("--log", action="store_true")
    ap.add_argument("--task")
    ap.add_argument("--tried")
    ap.add_argument("--outcome", default="fail")
    ap.add_argument("--why")
    ap.add_argument("--fix")
    ap.add_argument("--tags")
    ap.add_argument("--who")
    ap.add_argument("--search")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--recent", nargs="?", type=int, const=10)
    ap.add_argument("--count", action="store_true",
                    help="print the number of real episodes; exit 0 if >=1")
    a = ap.parse_args(argv)
    if a.log:
        return do_log(a)
    if a.count:
        real = [e for e in load() if PROBE_TAG not in (e.get("tags") or [])]
        print(f"{len(real)} episode(s) in {store_path()}")
        return 0 if real else 1
    if a.search is not None:
        hits = search(a.search, a.k)
        if not hits:
            print("(no matching episode)")
        for score, ep in hits:
            print(f"score={score}  " + render(ep))
        return 0
    eps = load()
    for ep in eps[-(a.recent or 10):]:
        print(render(ep))
    if not eps:
        print("(no episodes logged yet)")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main(sys.argv[1:]))
