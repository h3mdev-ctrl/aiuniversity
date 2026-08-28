#!/usr/bin/env python3
"""Measure real embed latency for two models against YOUR real (large) brain
content -- not a synthetic test string. A model that's faster on a 2-sentence
test can be no faster (or slower) on your actual largest documents.

EDIT DOC_TEXTS below with real large chunks from your brain (the biggest ones
you have -- that's where a slow model shows it) before running.

Prints steady-state (post-warmup) timing for both models. Does not fail/pass
automatically -- speed-vs-not-worth-it is a judgment call for the operator,
not something to hard-gate. Read the numbers and decide.
"""
import json
import time
import urllib.request

HOST = "http://localhost:11434"
CURRENT_MODEL = "qwen3-embedding:4b"       # EDIT: your current embedding model
CANDIDATE_MODEL = "qwen3-embedding:0.6b"   # EDIT: the smaller model you're testing
ROUNDS = 3

# EDIT: replace with 3-5 of your LARGEST real chunks/pages -- the documents
# most likely to expose a real speed difference. A short placeholder proves
# nothing about your real workload.
DOC_TEXTS = [
    "Replace with a real, large (many-hundred-word) chunk from your brain.",
]


def embed(model: str, text: str) -> float:
    req = urllib.request.Request(
        f"{HOST}/api/embed",
        data=json.dumps({"model": model, "input": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=90) as resp:
        resp.read()
    return time.time() - t0


def run(model: str):
    print(f"\n=== {model} ===")
    for i in range(1, ROUNDS + 1):
        total = sum(embed(model, t) for t in DOC_TEXTS)
        tag = "(cold/warming)" if i == 1 else "(steady-state)"
        print(f"  round {i}: {total:.2f}s for {len(DOC_TEXTS)} doc(s) {tag}")


if __name__ == "__main__":
    if any(t.startswith("Replace with") for t in DOC_TEXTS):
        print("EDIT DOC_TEXTS with real large content from your brain first.")
        raise SystemExit(1)
    run(CURRENT_MODEL)
    run(CANDIDATE_MODEL)
    print("\nCompare steady-state (round 2+) numbers -- ignore round 1, cold-start")
    print("cost looks identical to 'the change didn't help' (see gbrain-local-")
    print("reranker's Trap 7). Judge worth-it yourself; this script doesn't gate.")
