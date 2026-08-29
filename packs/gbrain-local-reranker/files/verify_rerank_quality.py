#!/usr/bin/env python3
"""Activation exam for the gbrain-local-reranker pack.

A server answering /v1/rerank proves it's UP. It doesn't prove it's actually
scoring relevance -- a broken tokenizer, a wrong pooling head, or a model
loaded in the wrong mode can all return a well-formed, useless response. This
sends a fixed relevant/irrelevant document triplet and asserts the relevant
one scores highest AND clears a floor -- the same check that first proved
Qwen3-Reranker-4B was wired correctly (2026-08-28: 0.99 vs ~0.00002).

Exit 0 = proof the cross-encoder is actually discriminating. Exit 1 = wired
but not working (fail loud rather than a false "it's fine").
"""
import json
import os
import sys
import urllib.request

PORT = os.environ.get("LLAMA_SERVER_RERANKER_PORT", "8081")
MODEL = os.environ.get("LLAMA_SERVER_RERANKER_ALIAS", "qwen3-reranker-4b")
URL = f"http://127.0.0.1:{PORT}/v1/rerank"

QUERY = "win11 quirk guard advisory"
DOCS = [
    "Dead-Cat Bounce is a stock market pattern where a declining stock partially recovers before resuming its decline.",
    "win11_quirk_guard is a PreToolUse hook that blocks common Windows footguns like PowerShell 2>&1 wrapping stderr.",
    "The recipe for chocolate chip cookies requires flour, sugar, and butter.",
]
RELEVANT_INDEX = 1
MIN_RELEVANT_SCORE = 0.5
MAX_IRRELEVANT_SCORE = 0.1


def main() -> int:
    payload = json.dumps({"model": MODEL, "query": QUERY, "documents": DOCS}).encode("utf-8")
    req = urllib.request.Request(URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"FAIL: could not reach {URL}: {exc}")
        return 1

    results = body.get("results")
    if not results:
        print(f"FAIL: no 'results' in response: {body}")
        return 1

    by_index = {r["index"]: r["relevance_score"] for r in results}
    relevant_score = by_index.get(RELEVANT_INDEX)
    other_scores = [s for i, s in by_index.items() if i != RELEVANT_INDEX]

    if relevant_score is None:
        print(f"FAIL: relevant doc (index {RELEVANT_INDEX}) missing from results: {by_index}")
        return 1
    if relevant_score < MIN_RELEVANT_SCORE:
        print(f"FAIL: relevant doc scored {relevant_score:.4f}, below floor {MIN_RELEVANT_SCORE} — reranker is not discriminating")
        return 1
    if any(s > MAX_IRRELEVANT_SCORE for s in other_scores):
        print(f"FAIL: an irrelevant doc scored above {MAX_IRRELEVANT_SCORE}: {other_scores}")
        return 1

    print(f"PASS: relevant={relevant_score:.4f}  irrelevant={[round(s, 6) for s in other_scores]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
