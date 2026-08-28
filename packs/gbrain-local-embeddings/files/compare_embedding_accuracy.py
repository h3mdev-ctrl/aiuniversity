#!/usr/bin/env python3
"""Compare two embedding models' ranking accuracy across several DIFFERENT real
content domains before committing to a destructive whole-brain migration.

One query with two distractor docs is not enough evidence for a whole-brain
decision -- a lucky pass on one topic can hide a real accuracy gap on another.
This runs several query/relevant-doc pairs spanning different domains and
requires the smaller model to get every one right, with a confidence margin
that doesn't collapse relative to the current model.

EDIT CURRENT_MODEL / CANDIDATE_MODEL and the CORPUS/QUERIES below to use your
own brain's real content before running -- the defaults are placeholders.

Exit 0 = candidate model matched the current model on every query, margins
within tolerance. Exit 1 = a wrong top-match, or a margin collapse >20%.
"""
import json
import math
import sys
import urllib.request

HOST = "http://localhost:11434"
CURRENT_MODEL = "qwen3-embedding:4b"       # EDIT: your current embedding model
CANDIDATE_MODEL = "qwen3-embedding:0.6b"   # EDIT: the smaller model you're testing
MARGIN_TOLERANCE = 0.20  # candidate's margin must stay within 20% of current's

# EDIT: replace with real chunks from YOUR brain, spanning DIFFERENT domains.
# Placeholder pairs below only prove the harness runs, not that your content
# is safe to migrate -- get_page/query a few real chunks from your own brain
# before trusting this check.
CORPUS = {
    "example_domain_a": "Replace with a real ~100-300 word chunk from your brain, domain A.",
    "example_domain_b": "Replace with a real ~100-300 word chunk from your brain, domain B.",
    "example_domain_c": "Replace with a real ~100-300 word chunk from your brain, domain C.",
}
QUERIES = {
    "a query whose answer is clearly domain A": "example_domain_a",
    "a query whose answer is clearly domain B": "example_domain_b",
    "a query whose answer is clearly domain C": "example_domain_c",
}


def embed(model: str, text: str) -> list[float]:
    req = urllib.request.Request(
        f"{HOST}/api/embed",
        data=json.dumps({"model": model, "input": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read())["embeddings"][0]


def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb)


def run(model: str) -> dict:
    corpus_vecs = {k: embed(model, v) for k, v in CORPUS.items()}
    out = {}
    for query, true_key in QUERIES.items():
        qvec = embed(model, query)
        scores = {k: cosine(qvec, v) for k, v in corpus_vecs.items()}
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        top_key = ranked[0][0]
        others = [s for k, s in scores.items() if k != true_key]
        margin = scores[true_key] - max(others)
        out[query] = {"correct": top_key == true_key, "margin": margin}
    return out


def main() -> int:
    if any(v.startswith("Replace with") for v in CORPUS.values()):
        print("EDIT the CORPUS/QUERIES constants with real content from your brain first.")
        return 1
    current = run(CURRENT_MODEL)
    candidate = run(CANDIDATE_MODEL)
    ok = True
    for query in QUERIES:
        c, cand = current[query], candidate[query]
        status = "OK"
        if not cand["correct"]:
            status = "WRONG TOP MATCH"
            ok = False
        elif c["margin"] > 0 and cand["margin"] < c["margin"] * (1 - MARGIN_TOLERANCE):
            status = f"MARGIN COLLAPSED ({cand['margin']:.3f} vs {c['margin']:.3f})"
            ok = False
        print(f"[{status}] '{query[:50]}' current_margin={c['margin']:+.4f} candidate_margin={cand['margin']:+.4f}")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
