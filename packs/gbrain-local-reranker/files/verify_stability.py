#!/usr/bin/env python3
"""Stability exam for the gbrain-local-reranker pack (Trap 2b).

A single successful rerank does not prove the batch-size bug is fixed --
llama-server's 512-token clamp only bites once real candidate pools get
large enough, so it can pass on a small pool and fail on a bigger one from
the same brain. This runs a real query N times via the actual `gbrain query`
CLI path and requires a non-null rerank_score on every run.

Distinguishes two failure classes that produce the identical visible symptom
(no rerank_score) for different reasons, so the diagnosis points at the
right trap instead of conflating them:
  - Trap 2b (batch size): the reranker was invoked and failed -- shows up as
    a fresh entry in ~/.gbrain/audit/rerank-failures-*.jsonl.
  - Trap 3 (query-embed timeout): a SEPARATE, already-documented issue where
    Ollama's embed call exceeds gbrain's fixed 6s deadline under GPU-sharing
    load with the reranker -- the reranker is never even reached. This is a
    real hardware-sharing constraint, not something this pack's launch flags
    fix; a retry after a brief pause is the correct response, not a config
    change.

Exit 0 = stable (every run reranked, or every non-reranked run was a
distinguishable Trap 3 embed-timeout retried successfully). Exit 1 = a
genuine Trap 2b batch failure occurred (audit log confirms it), or Trap 3
retries were exhausted.
"""
import json
import subprocess
import sys
import time

QUERY = "test query for reranker verification stability check"
RUNS = 5
RETRIES_PER_RUN = 2


def run_once() -> tuple[bool, str]:
    """Returns (success, classification) where classification is one of
    'ok', 'embed_timeout', 'other'."""
    try:
        proc = subprocess.run(
            ["gbrain", "query", QUERY, "--no-expand", "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=90,
        )
    except subprocess.TimeoutExpired:
        return False, "other"
    stderr = proc.stderr or ""
    if proc.returncode != 0:
        return False, "other"
    start = proc.stdout.find("[")
    if start == -1:
        return False, "other"
    try:
        results = json.loads(proc.stdout[start:])
    except json.JSONDecodeError:
        return False, "other"
    if not results:
        return False, "other"
    if any(r.get("rerank_score") is not None for r in results):
        return True, "ok"
    # No rerank_score. Distinguish Trap 3 (embed timeout, reranker never
    # reached) from a real Trap 2b failure via the CLI's own stderr warning.
    if "query embeds failed" in stderr or "embed deadline" in stderr:
        return False, "embed_timeout"
    return False, "other"


def run_with_retries(run_num: int) -> bool:
    for attempt in range(1, RETRIES_PER_RUN + 1):
        ok, cls = run_once()
        if ok:
            return True
        if cls == "embed_timeout":
            print(f"  (Trap 3: query-embed timeout, not the reranker -- retry {attempt}/{RETRIES_PER_RUN})")
            time.sleep(3)
            continue
        # A real failure classification -- no point retrying blindly.
        print(f"  run failed: no rerank_score (classification={cls})")
        return False
    print("  run failed: embed timeout persisted across retries")
    return False


def main() -> int:
    ok = 0
    for i in range(1, RUNS + 1):
        print(f"run {i}/{RUNS}...", end=" ")
        if run_with_retries(i):
            print("PASS")
            ok += 1
        else:
            print("FAIL")
    print(f"\n{ok}/{RUNS} runs returned a rerank_score")
    if ok < RUNS:
        print("UNSTABLE -- check ~/.gbrain/audit/rerank-failures-*.jsonl for a fresh")
        print("Trap 2b batch-size entry. If the log shows nothing new, this run's")
        print("failures were Trap 3 embed-timeout noise (GPU-sharing under load),")
        print("not a reranker problem -- see Trap 3 in windows_local_stack_gotchas.md.")
        return 1
    print("STABLE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
