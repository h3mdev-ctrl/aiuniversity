#!/usr/bin/env python3
"""
SOCKET: recall            EVENT: UserPromptSubmit
Hermes equivalent: MemoryProvider.prefetch / queue_prefetch

Retrieve the memories relevant to THIS prompt and inject them before the model
answers. This is the socket that turns a folder of notes into recall.

TWO BRANCHES, ONE SLOT EACH
  lexical   FTS5 + BM25 over ATOMS, gated by absolute floors, weighted by the
            learned trust_score (the same first stage as Hermes' FactRetriever).
            Stdlib only, ~100ms. Always on.
  semantic  OPTIONAL. Cosine over embeddings of each memory's `description:`.
            Off unless <store>/.recall/semantic_index.json exists (build it with
            build_recall_index.py). RECALL_SEMANTIC=0 turns it off again.

CONTRACT
  stdin : JSON {prompt, cwd, session_id}
  stdout: JSON {"hookSpecificOutput": {"hookEventName", "additionalContext"}}
  stderr: with RECALL_TRACE=1, one `trace:` line per branch that EXECUTED
  exit  : ALWAYS 0. A memory system must never block the user's turn.

STORE (per project, next to the notes): <memory>/.recall/
  trust.json     {"<file>.md": trust_score}   written by learn_on_compact.py
  fires.jsonl    one line per injection        read by learn_on_compact.py
  semantic_index.json (+ .npy sidecar)         written by build_recall_index.py
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request

MAX_HITS = 2          # swept on real prompts: 2 beat 3 (75% vs 72% precision)

# TRIVIALITY GATE -- ported from hermes-agent `TRIVIAL_PROMPT_RE`. A whitelist
# anchored to END OF STRING: "ok" is skipped, "ok walk it forwards" is not. A word
# count is wrong both ways (skips "why is CI red?", admits "ok sure thanks mate").
TRIVIAL_PROMPT_RE = re.compile(
    r"^(yes|no|ok|okay|sure|thanks|thank you|thx|ta|y|n|yep|nope|yeah|nah|"
    r"hi|hey|hello|yo|sup|continue|go ahead|go on|do it|proceed|carry on|"
    r"got it|cool|nice|great|done|next|lgtm|k|perfect|awesome|right|exactly)"
    r"[\s!?.:;,\"'~()\[\]{}<>*&^%$#@+=`-]*$",
    re.IGNORECASE,
)

# Harness-generated turns are not user prompts. Measured: 19% of logged firings
# (64/344) fired on these -- a wasted retrieval answering nobody.
HARNESS_PREFIXES = ("<system-reminder", "<task-notification", "<command-name",
                    "<local-command", "<channel", "<function_results",
                    "<user-prompt-submit-hook")

# ---- LEXICAL GATES ----------------------------------------------------------
# BM25 is normalised WITHIN a result set, so the top 2 of a bad match look like
# the top 2 of a good one (measured: positives 0.19-0.40, negatives 0.28-0.39,
# fully overlapping). A rank is a fine RANKER and a useless CLASSIFIER, so two
# ABSOLUTE gates decide "is this prompt about anything we remember at all":
MIN_BM25 = 1.0        # CALIBRATE on your corpus: --calibrate (magnitude scales with it)
MIN_OVERLAP = 0.15    # share of query terms the atom names -- corpus-independent

# ---- TRUST + CONFIDENCE FLOOR ------------------------------------------------
# score = relevance * trust_score   (Hermes: `final_score = relevance * trust`)
# relevance = (0.6 * bm25/best_bm25 + 0.4 * overlap) * atom-kind weight
FTS_WEIGHT, OVERLAP_WEIGHT = 0.6, 0.4
DEFAULT_TRUST = 0.50  # a memory nobody has voted on yet
MIN_TRUST = 0.30      # voted below this: never retrieved (Hermes min_trust)
# MIN_INJECT: below this, inject NOTHING. On the author's store (447 logged hits
# scored against trust votes) the band under 0.40 was right only 25-30% of the
# time -- worse than silence, and ~60% of all volume. But the floor is 0.30, not
# 0.40: a positive control refuted 0.40 at once (two exactly-right memories
# scored 0.348 and 0.357; the MEDIAN hit was 0.382, so 0.40 silenced good hits
# with the bad). Keep coverage; let honest LABELLING in render() carry the rest.
MIN_INJECT = 0.30
STRONG_SCORE = 0.45   # at/above: "act on it" framing is earned (97% precision there)

# ---- SEMANTIC SLOT -----------------------------------------------------------
# Measured by the author (2026-09), paraphrase benchmark n=120: rank-1 lexical
# 15%, semantic 43%. That looks like "lead with semantic" -- it is not. On 30 REAL
# prompts where lexical fired, hand-labelled: lexical top-1 relevant 12/30,
# semantic 14/30, and at least one right 19/30. They win on DIFFERENT prompts
# (lexical: exact tokens; semantic: paraphrase). So: ONE SLOT EACH.
# When lexical is silent, semantic alone was relevant ~3/24 -- so it may inject
# alone ONLY past both bars below (kept 5/7 = 71%). Absolute cosine alone does
# not separate: "ok lets do 1-4" scored 0.607 against real matches ~0.62.
SOLO_MIN_TOP = 0.65   # top-1 cosine
SOLO_MIN_GAP = 0.10   # top-1 minus top-8 cosine: a peak, not a plateau
SEM_TOPN = 8
EMBED_TIMEOUT = 1.5   # s. Exceed -> this prompt goes lexical-only (fail open)
# 127.0.0.1, NOT localhost: on Windows `localhost` tries ::1 first, +0.13s/call.
EMBED_URL = "http://127.0.0.1:11434/api/embed"
EMBED_MODEL = "qwen3-embedding:0.6b"


def trace(msg: str) -> None:
    """RECALL_TRACE=1 -> one stderr line per branch that EXECUTED.

    Why this exists: in production the semantic branch sat behind `except: pass`
    and never ran for three weeks (a NameError) while every health check said
    HEALTHY. A fail-open branch is invisible by design, so it must be able to
    say "I ran" -- socket_doctor.py --probe recall reads these lines.
    """
    if os.environ.get("RECALL_TRACE") == "1":
        print(f"trace: {msg}", file=sys.stderr)


def is_trivial_prompt(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped or stripped.startswith("/"):
        return True          # empty, or a command addressed to the harness
    return bool(TRIVIAL_PROMPT_RE.match(stripped))


def memory_dir(cwd: str) -> pathlib.Path | None:
    """Resolve the memory folder for THIS project -- never one global store, or
    project B is served project A's conclusions as authoritative."""
    if os.environ.get("CLAUDE_MEMORY_HOME"):
        return pathlib.Path(os.environ["CLAUDE_MEMORY_HOME"])
    for base in (pathlib.Path(cwd), *pathlib.Path(cwd).parents):
        if (base / "memory" / "MEMORY.md").is_file():
            return base / "memory"
    return None


def store(memdir: pathlib.Path) -> pathlib.Path:
    return memdir / ".recall"


def load_trust(memdir: pathlib.Path) -> dict:
    p = store(memdir) / "trust.json"
    if not p.is_file():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


# ---- LEXICAL: atoms, not documents ------------------------------------------
# One row per STATEMENT (resolver row, description, slug), never one per file and
# never the body. Measured on a 607-file corpus: document-level 20% precision,
# atom-level 75%, same scoring maths. BM25 over a 200-line file matches every
# query a little; over one sentence a match means something.
ATOM_WEIGHT = {"resolver": 1.00, "description": 0.95, "slug": 0.75}
MIN_ATOM_CHARS = 12
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+\.md)\)")


def description_of(text: str) -> str:
    m = re.search(r"^description:\s*(.+)$", text, re.M)
    return m.group(1).strip().strip('"') if m else ""


def build_index(memdir: pathlib.Path) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE VIRTUAL TABLE m USING fts5(target, kind, content, "
                 "tokenize='porter unicode61')")
    intents: dict[str, list[str]] = {}
    for idx in ("MEMORY.md", *(p.name for p in sorted(memdir.glob("INDEX_*.md")))):
        p = memdir / idx
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            links = _LINK_RE.findall(line) if line.lstrip().startswith("|") else []
            intent = re.sub(r"\s+", " ", _LINK_RE.sub(" ", line).replace("|", " ")).strip()
            for _disp, target in links:       # one atom per row: NEVER merge intents
                if len(intent) >= MIN_ATOM_CHARS:
                    intents.setdefault(target, []).append(intent)
    for f in sorted(memdir.glob("*.md")):
        if f.name in ("MEMORY.md", "CATALOG.md"):
            continue
        desc = description_of(f.read_text(encoding="utf-8", errors="replace"))
        atoms = [("resolver", i) for i in intents.get(f.name, [])]
        if desc:
            atoms.append(("description", desc))
        atoms.append(("slug", f.stem.replace("_", " ")))
        seen = set()
        for kind, content in atoms:
            key = re.sub(r"\W+", " ", content.lower()).strip()
            if len(key) >= MIN_ATOM_CHARS and key not in seen:
                seen.add(key)
                conn.execute("INSERT INTO m VALUES (?,?,?)", (f.name, kind, content))
    return conn


def terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]{3,}", text.lower()))


def sanitize(prompt: str) -> str:
    """OR-join quoted terms: FTS5 AND-joins bare terms, which kills recall."""
    return " OR ".join(f'"{t}"' for t in re.findall(r"[a-z0-9_]{3,}", prompt.lower())[:12])


def overlap(prompt: str, target: str, content: str) -> float:
    q = terms(prompt)
    return len(q & terms(f"{target} {content}")) / len(q) if q else 0.0


def lexical(conn, prompt: str, trust: dict) -> list[dict]:
    q = sanitize(prompt)
    if not q:
        return []
    rows = conn.execute("SELECT target, kind, content, -bm25(m) AS bm FROM m "
                        "WHERE m MATCH ? ORDER BY bm DESC LIMIT ?",
                        (q, MAX_HITS * 12)).fetchall()
    if not rows:
        return []
    top_bm = max(r["bm"] for r in rows) or 1e-6
    best: dict[str, dict] = {}
    for r in rows:
        w = ATOM_WEIGHT.get(r["kind"], 0.9)
        ov = overlap(prompt, r["target"], r["content"])
        if r["bm"] * w < MIN_BM25 or ov < MIN_OVERLAP:
            continue                          # absolute gates: not about this
        t = float(trust.get(r["target"], DEFAULT_TRUST))
        if t < MIN_TRUST:
            continue                          # voted out by the learning loop
        score = (FTS_WEIGHT * r["bm"] / top_bm + OVERLAP_WEIGHT * ov) * w * t
        prev = best.get(r["target"])
        if prev is None or score > prev["score"]:   # collapse atoms by MAX, not sum
            best[r["target"]] = {"target": r["target"], "content": r["content"],
                                 "score": score, "trust": t, "via": "lexical"}
    return sorted(best.values(), key=lambda h: -h["score"])[:MAX_HITS]


# ---- SEMANTIC ---------------------------------------------------------------
def semantic_enabled(memdir: pathlib.Path) -> bool:
    if os.environ.get("RECALL_SEMANTIC") == "0":
        return False
    return (store(memdir) / "semantic_index.json").is_file()


def load_index(memdir: pathlib.Path):
    """(model, targets, vectors). Prefers the .npy sidecar: parsing a 16 MB JSON
    cost ~0.33s on EVERY prompt; the sidecar loads in milliseconds. JSON stays the
    source of truth; the sidecar is used only when newer than it."""
    j = store(memdir) / "semantic_index.json"
    npy = j.with_suffix(".npy")
    meta = json.loads(j.read_text(encoding="utf-8"))
    targets, vecs = meta["targets"], meta.get("vectors")
    try:
        import numpy as np
        if npy.is_file() and npy.stat().st_mtime >= j.stat().st_mtime:
            vecs = np.load(npy)
        else:
            vecs = np.asarray(vecs, dtype=np.float32)
    except ImportError:
        pass
    if vecs is None or len(vecs) != len(targets):
        raise ValueError("semantic index: targets and vectors disagree")
    return meta.get("model", EMBED_MODEL), targets, vecs


def _spawn_warmup(memdir: pathlib.Path) -> None:
    """After an embed timeout, load the model in a DETACHED process.

    Found in production: a cold load took ~3.1s, the hook gave up at 1.5s and
    disconnected -- and the server ABANDONS a load whose client disconnects. So
    the model was never resident and the semantic slot fell back on every single
    prompt. A detached request with a long timeout lets the load finish and
    keep_alive holds it. Throttled to one spawn per 60s; never raises.
    """
    try:
        stamp = store(memdir) / "warmup.stamp"
        if stamp.exists() and time.time() - stamp.stat().st_mtime < 60:
            return
        stamp.write_text(str(time.time()), encoding="utf-8")
        url = os.environ.get("RECALL_EMBED_URL", EMBED_URL)
        model = os.environ.get("RECALL_EMBED_MODEL", EMBED_MODEL)
        code = ("import json,urllib.request;"
                f"b=json.dumps({{'model':{model!r},'input':'warm','keep_alive':'30m'}}).encode();"
                f"urllib.request.urlopen(urllib.request.Request({url!r},data=b,"
                "headers={'Content-Type':'application/json'}),timeout=60).read()")
        flags = 0x00000008 | 0x08000000 if os.name == "nt" else 0  # DETACHED|NO_WINDOW
        subprocess.Popen([sys.executable, "-c", code], creationflags=flags,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True)
    except Exception:
        pass


def embed_query(text: str, model: str, memdir: pathlib.Path) -> list[float]:
    """Unit vector for the prompt. RAISES on failure -- the caller traces the
    exception type and falls back, so a dead embedder is visible, not silent."""
    url = os.environ.get("RECALL_EMBED_URL", EMBED_URL)
    body = json.dumps({"model": model, "input": text, "keep_alive": "30m"}).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=EMBED_TIMEOUT) as r:
            d = json.load(r)
    except Exception:
        _spawn_warmup(memdir)
        raise
    v = (d.get("embeddings") or [d.get("embedding")])[0]
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


def semantic(memdir: pathlib.Path, prompt: str) -> list[tuple[float, str]]:
    model, targets, vecs = load_index(memdir)       # local failure before network
    q = embed_query(prompt, model, memdir)
    if hasattr(vecs, "shape"):
        import numpy as np
        sims = [float(s) for s in vecs @ np.asarray(q, dtype=np.float32)]
    else:
        sims = [sum(a * b for a, b in zip(q, v)) for v in vecs]
    return sorted(zip(sims, targets), reverse=True)[:SEM_TOPN]


def materialise(memdir: pathlib.Path, target: str, cos: float, trust: dict):
    t = float(trust.get(target, DEFAULT_TRUST))
    p = memdir / target
    if t < MIN_TRUST or not p.is_file():
        return None
    desc = description_of(p.read_text(encoding="utf-8", errors="replace"))
    # Scored on cosine, not the lexical scale -- so it is always LABELLED low
    # confidence (semantic top-1 was right 14/30), never "act on it".
    return {"target": target, "content": desc or target, "score": None,
            "cosine": cos, "trust": t, "via": "semantic"}


def merge(memdir, lex: list[dict], sem: list[tuple[float, str]], trust) -> list[dict]:
    """ONE SLOT EACH. Our first version re-sorted lexical's 2 hits by cosine --
    it could never REPLACE a wrong lexical hit, which is not what the benchmark
    measured. Rules:
      lexical fired   -> [lexical #1, semantic #1] (lexical #2 if they agree)
      lexical silent  -> semantic #1 alone iff top >= SOLO_MIN_TOP and
                         gap >= SOLO_MIN_GAP; otherwise stay silent
    """
    if not sem:
        return lex
    top, gap, name = sem[0][0], sem[0][0] - sem[-1][0], sem[0][1]
    if lex:
        out = [lex[0]]
        if name != lex[0]["target"] and (d := materialise(memdir, name, top, trust)):
            out.append(d)
        out += [h for h in lex[1:] if h["target"] not in {o["target"] for o in out}]
        return out[:MAX_HITS]
    if top >= SOLO_MIN_TOP and gap >= SOLO_MIN_GAP:
        d = materialise(memdir, name, top, trust)
        return [d] if d else []
    return []


# ---- OUTPUT -----------------------------------------------------------------
def render(hits: list[dict]) -> str:
    """Frame each hit by what its score EARNED. One "treat as authoritative"
    banner for every hit was the defect: right at 0.45+, wrong 3 times in 4
    under 0.40."""
    strong = [h for h in hits if h["score"] is not None and h["score"] >= STRONG_SCORE]
    weak = [h for h in hits if h not in strong]
    lines = ["<system-reminder>"]
    if strong:
        lines.append("Relevant project memory (HIGH confidence). Your own prior "
                     "conclusions -- act on them; verify any specific number first:")
        lines += [f"  - [{h['target'][:-3]}]({h['target']})\n    {h['content'][:200]}"
                  for h in strong]
    if weak:
        lines.append("POSSIBLY relevant memory (LOW confidence -- a lead, not an "
                     "instruction; ignoring it is a valid outcome):")
        for h in weak:
            how = (f"cosine {h['cosine']:.2f}" if h["via"] == "semantic"
                   else f"score {h['score']:.2f}")
            lines.append(f"  - [{h['target'][:-3]}]({h['target']}) ({h['via']}, {how})"
                         f"\n    {h['content'][:200]}")
    lines.append("</system-reminder>")
    return "\n".join(lines)


def log_fire(memdir: pathlib.Path, session_id: str, prompt: str, hits) -> None:
    """One line per injection. You cannot tune what you do not log, and the
    learning loop cannot vote without it. Append-only, one write per line."""
    try:
        store(memdir).mkdir(exist_ok=True)
        line = json.dumps({"ts": time.time(), "session_id": session_id,
                           "prompt": re.sub(r"\s+", " ", prompt).strip()[:60].lower(),
                           "hits": [{"target": h["target"], "via": h["via"]} for h in hits]})
        with open(store(memdir) / "fires.jsonl", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def recall(data: dict) -> str:
    prompt = data.get("prompt") or data.get("user_prompt") or ""
    if not isinstance(prompt, str) or is_trivial_prompt(prompt) \
            or prompt.lstrip().startswith(HARNESS_PREFIXES):
        trace("trivial or harness prompt, no branch ran")
        return ""
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else os.getcwd()
    memdir = memory_dir(cwd)
    if not memdir:
        trace(f"no memory store resolves from cwd={cwd}")
        return ""
    sem_on = semantic_enabled(memdir)
    trace("branches=" + ("lexical,semantic" if sem_on else "lexical"))

    try:
        trust = load_trust(memdir)
    except Exception as e:                  # a corrupt vote file must not kill recall
        trace(f"trust store unreadable ({type(e).__name__}), using defaults")
        trust = {}
    lex = [h for h in lexical(build_index(memdir), prompt, trust)
           if h["score"] >= MIN_INJECT]                 # the confidence floor
    trace(f"lexical ran, {len(lex)} hit{'s' if len(lex) != 1 else ''}")

    hits, sem = lex, []
    if sem_on:
        try:
            sem = semantic(memdir, prompt)
            top = sem[0][0] if sem else 0.0
            gap = top - sem[-1][0] if sem else 0.0
            trace(f"semantic ran, top={top:.2f} gap={gap:.2f}")
            hits = merge(memdir, lex, sem, trust)
        except Exception as e:                          # fail OPEN, but out loud
            trace(f"semantic SKIPPED: {type(e).__name__}")
            hits = lex
    if not hits:
        return ""
    log_fire(memdir, str(data.get("session_id") or ""), prompt, hits)
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit", "additionalContext": render(hits)}})


def calibrate(memdir: pathlib.Path, positive: str, negative: str) -> None:
    """Print what YOUR corpus scores for a should-hit and a should-miss. Without
    both controls a correctly-silent hook and a broken one look identical.
        python recall_on_prompt.py --calibrate <memory_dir> "<hit>" "<miss>" """
    conn, trust = build_index(memdir), load_trust(memdir)
    for label, prompt in (("SHOULD HIT ", positive), ("SHOULD MISS", negative)):
        q = sanitize(prompt)
        rows = conn.execute("SELECT target, kind, content, -bm25(m) AS bm FROM m WHERE "
                            "m MATCH ? ORDER BY bm DESC LIMIT 4", (q,)).fetchall() if q else []
        print(f"\n{label}: {prompt!r}")
        for r in rows or []:
            print(f"   {r['target'][:30]:30s} <{r['kind']:11s}> bm25={r['bm']:6.3f} "
                  f"overlap={overlap(prompt, r['target'], r['content']):.2f}")
        print(f"   gated hits: {[(h['target'], round(h['score'], 3)) for h in lexical(conn, prompt, trust)]}")
    print(f"\ngates: MIN_BM25={MIN_BM25} MIN_OVERLAP={MIN_OVERLAP} MIN_INJECT={MIN_INJECT}")


def main() -> int:
    if "--calibrate" in sys.argv:
        rest = sys.argv[sys.argv.index("--calibrate") + 1:]
        if len(rest) < 3:
            print('usage: --calibrate <memory_dir> "<should-hit>" "<should-miss>"')
            return 2
        calibrate(pathlib.Path(rest[0]), rest[1], rest[2])
        return 0
    try:
        data = json.loads(sys.stdin.read() or "{}")
        if isinstance(data, dict) and (out := recall(data)):
            print(out)
    except Exception as e:
        # Swallow -- a crash would surface as a broken prompt -- but never silently.
        trace(f"recall FAILED: {type(e).__name__}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
