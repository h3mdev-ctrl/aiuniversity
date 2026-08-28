#!/usr/bin/env python3
"""Trap 1 exam: confirm `gbrain query` (not `search`) exercises the reranker.

Brain-content-agnostic on purpose -- this pack is reused across different
users' brains, so it can't depend on any specific page existing. Instead it
warms the embedding model first (Trap 3/7: a cold/idle Ollama model causes a
6s query-embed timeout that has nothing to do with the reranker and produces
the exact same "no rerank_score" symptom) and retries a couple of times
before concluding failure, so a transient cold-start doesn't masquerade as a
real reranker bug.

Exit 0 = a real `query` call returned a non-null rerank_score at least once.
Exit 1 = it never did across all attempts -- a genuine problem worth the
pack's on_fail diagnosis, not just cold-start noise.
"""
import json
import subprocess
import sys
import time
import urllib.request

# Generic enough to return SOME candidates on any reasonably-populated brain;
# not asserting relevance, only that the mechanism fires end to end.
QUERY = "recent notes"
ATTEMPTS = 3


def warm_embedding_model() -> None:
    """Best-effort warmup. Reads OLLAMA host from the environment the same
    way gbrain does; falls back to localhost. Failure here isn't fatal --
    the retry loop below still covers a cold call."""
    import os
    host = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        req = urllib.request.Request(
            f"{host}/api/embed",
            data=json.dumps({"model": "text-embedding-3-large:latest", "input": "warmup"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=15)
    except Exception:
        pass  # non-fatal -- the retry loop covers this


def run_once() -> bool:
    try:
        proc = subprocess.run(
            ["gbrain", "query", QUERY, "--no-expand", "--limit", "10", "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=90,
        )
    except subprocess.TimeoutExpired:
        print("(timed out)", end=" ")
        return False
    if proc.returncode != 0:
        return False
    start = proc.stdout.find("[")
    if start == -1:
        return False
    try:
        results = json.loads(proc.stdout[start:])
    except json.JSONDecodeError:
        return False
    return any(r.get("rerank_score") is not None for r in results)


def main() -> int:
    warm_embedding_model()
    for attempt in range(1, ATTEMPTS + 1):
        print(f"attempt {attempt}/{ATTEMPTS}...", end=" ")
        if run_once():
            print("PASS (rerank_score present)")
            return 0
        print("no rerank_score yet")
        time.sleep(2)
    print("FAIL: no rerank_score across all attempts -- see on_fail diagnosis")
    return 1


if __name__ == "__main__":
    sys.exit(main())
