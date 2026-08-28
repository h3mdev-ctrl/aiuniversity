# Local reranker on Windows — the gotchas that cost real time

Distilled from a live 2026-08-28 session: standing up a local `llama-server`
reranker for gbrain, then discovering it was silently inert, then tuning
`OLLAMA_NUM_PARALLEL` for a concurrent reindex on the same GPU. Every trap
below wasted real diagnostic time before the cause was found.

---

## Trap 1: `gbrain search` never calls the reranker — only `query` does

`gbrain search` is documented as "cheap hybrid search... no LLM expansion."
That's about query expansion, not reranking — but in practice the reranker
also never fires on `search`, regardless of `--mode tokenmax`. It only fires
on `gbrain query` (the default search mode in gbrain's own CLI help says
"autocut is the SMART DEFAULT... when the reranker runs, which it does in the
default search mode").

**Symptom:** you wire the reranker, `gbrain models doctor` shows it reachable,
but `gbrain search "..." --json | grep rerank_score` comes back empty, and
`llama-server`'s own request log shows zero incoming requests.

**Fix:** test with `gbrain query`, not `gbrain search`, when verifying a
reranker end-to-end. If your actual usage goes through `search`, the reranker
you just built will never be exercised — check which verb your callers use.

## Trap 2: the fail-open audit log is the fastest diagnostic, and it's not obvious

Per `docs/ai-providers/llama-server-reranker.md`, `applyReranker` fails open:
any error (auth, network, timeout, malformed response) logs to
`~/.gbrain/audit/rerank-failures-*.jsonl` and returns unranked results with
**no error surfaced to the caller**. Before guessing at config, read this file
— it names the exact model, doc_count, and error class of every failed call:

```bash
tail -20 ~/.gbrain/audit/rerank-failures-2026-W35.jsonl
```

## Trap 2b: the 512-token batch cap is a HARD BLOCKER on real queries, and `--batch-size` alone does not fix it

This is the trap that matters most — it silently defeats the entire reranker
on real corpus data while looking perfect in a synthetic 3-document test.

**Symptom:** `gbrain models doctor` shows the reranker reachable, a hand-built
`curl` test against `/v1/rerank` with 2-3 short sentences scores correctly —
but real `gbrain query` calls (20-30+ real chunk_text candidates, each a few
hundred tokens) fail with:
```
rerank HTTP 500: input (648 tokens) is too large to process. increase the
physical batch size (current batch size: 512)
```
`llama-server` auto-clamps `n_batch`/`n_ubatch` to **512** at launch when it
detects reranking mode (the same code path as its embeddings-batch guard).
A synthetic few-sentence test never comes close to 512 tokens, so this is
invisible until real, larger candidate pools hit it — by which point it looks
like the reranker is "randomly" broken.

**The fix has two parts, and skipping either one leaves it intermittently
broken:**

1. **Pass explicit batch sizes at launch:**
   ```
   --batch-size 4096 --ubatch-size 4096
   ```
   Size these to comfortably exceed your largest real candidate-pool token
   count (30 chunks × a few hundred tokens each can exceed 2000 easily).

2. **Also pass `--parallel 1` (default `-np` is 4).** This is the part that's
   easy to miss and causes genuinely intermittent failures even AFTER fixing
   (1): the default 4 parallel slots divide/contend for batch capacity, so a
   `--batch-size 4096` launch can still silently serve a request out of an
   effectively-undersized slot under concurrent load. Verified 2026-08-28:
   with 4 default slots, the SAME query (648 tokens, deterministic) failed on
   some calls and succeeded on others within a two-minute window with no
   config change — a flaky-looking bug that vanished completely once relaunched
   with `--parallel 1`. Reranking is a single local pipeline stage; it doesn't
   need to serve concurrent users, so there's no downside to forcing one slot.

**Full corrected launch command:**
```bash
llama-server --model <gguf-path> --alias <alias> --reranking --port 8081 \
  --n-gpu-layers 99 --batch-size 4096 --ubatch-size 4096 --parallel 1
```

**Verify the fix actually held** — run the SAME real query 3-5 times in a row
and confirm identical, non-null `rerank_score` every time. A single successful
run is not proof; the slot-contention half of this bug only shows up under
repeated/concurrent calls.

## Trap 3: query embeddings and the reranker share one GPU — expansion can starve first

`gbrain query`'s multi-query expansion embeds through the SAME Ollama instance
the reranker's candidate pool depends on. Under load (e.g. a concurrent
`reindex`), embed calls can hit `deadline 6000ms exceeded` and gbrain silently
salvages a lexical-only fallback — the reranker never even gets a proper
candidate set, and this produces the SAME symptom as Trap 1 (no
`rerank_score`) for a completely different reason. Check
`[gbrain] N/N query embeds failed (salvaging survivors)` in stderr before
concluding the reranker itself is broken.

## Trap 4: killing `ollama.exe` does NOT kill its `llama-server.exe` child

Ollama runs its own internal `llama-server.exe` (from
`...\Ollama\lib\ollama\llama-server.exe`) as its actual inference backend, one
per loaded model. `Stop-Process` on the parent `ollama.exe` orphans this
child — it survives, keeps its GPU memory allocation, and answers nothing
(traffic routes through whatever instance is currently alive). This is
invisible in `nvidia-smi` unless you check `ParentProcessId` per process; VRAM
just looks "used" with no explanation.

**Check for orphans:**
```powershell
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'llama-server.exe' } |
  ForEach-Object {
    $parentAlive = Get-Process -Id $_.ParentProcessId -ErrorAction SilentlyContinue
    [pscustomobject]@{ PID=$_.ProcessId; ParentPID=$_.ParentProcessId; ParentAlive=[bool]$parentAlive }
  }
```
Any row with `ParentAlive: False` is an orphan burning GPU memory for nothing
— kill it directly by its own PID. (Real measurement: one orphan held ~3.1GB
of an 8GB card silently for ~10 minutes before being caught.)

## Trap 5: Ollama's desktop tray app respawns an unconfigured server

`ollama app.exe` (the tray/desktop wrapper) watches its `ollama.exe serve`
child and relaunches it if killed — **without any environment variables you
just set**. Killing only the child to apply `OLLAMA_NUM_PARALLEL` (or any
other env var) just gets you a fresh unconfigured instance seconds later.

**Fix:** kill the tray app too (`ollama app.exe`, not just `ollama.exe`),
confirm both are gone, then launch `ollama serve` yourself with the env var
set on that process directly. Cost: the system-tray icon disappears since
you're no longer running the managed instance — functionally identical,
purely cosmetic, but worth knowing so it doesn't read as broken.

## Trap 6: `OLLAMA_NUM_PARALLEL > 1` silently shrinks context to fit VRAM

Ollama auto-sizes context length from free VRAM at model load
(`vram-based default context` in its own startup log). Doubling parallel
slots roughly doubles KV-cache reservation per loaded model, so on a tight
card it compensates by shrinking `num_ctx` — observed: **16384 → 4096** on an
8GB card just from setting `OLLAMA_NUM_PARALLEL=2`. Fine for short inputs
(markdown chunk embedding), a real risk if anything you embed can exceed the
new ceiling — it will silently truncate, not error.

**Check what actually landed** after any Ollama restart:
```bash
ollama ps   # CONTEXT column shows the effective post-shrink value
```

## Trap 7: don't judge throughput from the first few minutes after any Ollama restart

Measured on this session: a reindex job ran at ~17.6s/page for its first
clean 10-minute window after an Ollama restart, then jumped to ~3.6s/page
(a ~5x improvement) in the very next window with no configuration change in
between. The first window included model reload + JIT/cache warm-up costs
that look identical to "the tuning didn't work." Take at least two clean
measurement windows post-restart before concluding a change helped, hurt, or
did nothing.

## Trap 8: HuggingFace downloads over 1GB fail silently mid-transfer — verify the byte count, not the exit code

A `curl -L -o file url` on a large GGUF can report a misleadingly clean exit
in some tool-call wrappers even when the transfer was interrupted; separately,
`curl` itself can return **exit 18** (partial transfer) partway through a
multi-GB file on a flaky connection, sometimes after appearing to progress
past 70%. Retrying blind (`curl -L -o file url` again, no resume flag)
restarts from zero and can loop indefinitely on the same flaky window.

**Fix — loop resumable downloads and check the actual byte count, not the
exit code:**
```bash
EXPECTED=<content-length from a HEAD request>
while [ "$(stat -c%s "$FILE" 2>/dev/null || echo 0)" -lt "$EXPECTED" ]; do
  curl -L --max-time 200 --speed-limit 1024 --speed-time 30 -C - -o "$FILE" "$URL"
done
[ "$(stat -c%s "$FILE")" -eq "$EXPECTED" ] || { echo "SIZE MISMATCH — do not use this file"; exit 1; }
```
`-C -` resumes from the existing partial file instead of restarting; the
`stat` check after the loop is the real proof, not curl's exit code. A
corrupted/truncated GGUF loads far enough into `llama-server` to look
promising, then fails with `tensor '...' data is not within the file bounds,
model is corrupted or incomplete` deep into model load — after the download
already "succeeded."

## Trap 9: pick the CUDA build that matches your DRIVER's reported CUDA version, not the newest

`nvidia-smi` reports a max-supported CUDA runtime version (e.g. `13.2`).
Prebuilt llama.cpp releases often ship both an older (12.x) and a newer
(13.x) CUDA build. The newer number is not automatically the right choice —
if it exceeds what your driver reports, prefer the older, more broadly
compatible CUDA build line. Verified: `cuda-12.4-x64` loaded and ran cleanly
on a driver reporting CUDA 13.2 support.
