# gbrain-local-reranker

Replaces gbrain's hosted ZeroEntropy reranker with a **free, local** `llama-server`
+ Qwen3-Reranker instance — GPU time instead of a paid API, and no dependency on
ZeroEntropy's hosted endpoints (shutting down 2026-09-04). The reranker is
**fail-open by design**: a dead key or a shut-down endpoint doesn't error, it
silently returns unranked results. `RETRIEVAL.md` documents it as the single
biggest ranking lever in the default pipeline — 60% of top-1 results reshuffle
when it runs — so "silently off" quietly guts most of the pipeline's value with
no signal anywhere a normal session would look.

This is a **follow-on pack**, not part of `gbrain-windows` core: it needs an
external multi-GB download, a second long-lived local server with its own
lifecycle, and **a GPU — required for interactive use, not just "for good
performance."** Confirmed on a second install (CPU-only, integrated graphics):
a realistic candidate pool simply doesn't complete within 3 minutes, at any
model size. If you don't have a free NVIDIA GPU, skip this pack. Run
`gbrain-windows` first either way.

See [pack-structure.md](../../docs/pack-structure.md) for the section
conventions, and [files/windows_local_stack_gotchas.md](files/windows_local_stack_gotchas.md)
for the 11 real traps hit standing this up — read it first if Ollama also runs
on this box. **The one that actually mattered (Trap 2b):** llama-server clamps
its batch size to 512 tokens by default. A synthetic test with 2-3 short
sentences never gets close to that limit and looks perfect; every real query
(20-30 real chunks) exceeds it and fails. The fix needs BOTH `--batch-size`/
`--ubatch-size` raised AND `--parallel 1` — the default 4 slots divide batch
capacity, so raising just the batch size alone still fails intermittently
under real, repeated use. This single bug, undiagnosed, looks exactly like
"the reranker doesn't work" with zero indication of the real cause anywhere
except the fail-open audit log.

## Contract

- **`server-running`** — confirms `llama-server` answers on its configured port
  in reranking mode (default 8081). Proves the process is alive, not yet that
  it reranks correctly.
- **`gbrain-wired`** — confirms gbrain's `search.reranker.model` config points
  at the local server, not the (dead) hosted ZeroEntropy API.
- **`reachability-confirmed`** — confirms gbrain's own model registry can reach
  it (`gbrain models doctor`), not just that the raw HTTP endpoint answers.
- **`actually-reranks`** — the real test. Sends a fixed relevant/irrelevant
  document triplet and asserts the genuinely relevant one scores highest by a
  wide margin. A server returning HTTP 200 is not a server discriminating
  relevance — a wrong pooling head or truncated model file can both return a
  well-formed, useless response.
- **`verify-in-real-usage`** — confirms the CLI verb you'll actually call
  (`gbrain query`, not `gbrain search`) exercises the reranker end to end
  with a realistic candidate pool, not a toy 2-3 document test.
- **`stability-confirmed`** — runs the same real query 5 times in a row and
  requires a non-null `rerank_score` on every single run. A single pass does
  NOT prove Trap 2b's slot-contention half is fixed — it's intermittent by
  nature, and one lucky run looks identical to a genuinely stable setup.

## Iron Laws

- **A server that answers is not a server that reranks, and one successful
  rerank is not a stable setup.** Every step up to `actually-reranks` can pass
  on a broken model; `actually-reranks` itself can pass once and then fail on
  the very next real call if launched with default parallel slots (Trap 2b).
  Only `stability-confirmed`'s 5-run check earns real trust.
- **`--batch-size` alone does not fix the 512-token clamp.** You also need
  `--parallel 1` — the default 4 slots divide/contend for batch capacity, so
  a raised batch size can still silently serve an undersized slot under real,
  repeated load. Both flags, every launch, no exceptions.
- **`gbrain search` never fires the reranker — only `gbrain query` does.**
  Regardless of `search.reranker.enabled` or `--mode tokenmax`. Verifying with
  the wrong verb produces a false "it's not working" every time.
- **Fail-open means the audit log is the fastest diagnostic, not a guess.**
  Every rerank failure — auth, network, timeout, malformed response — is
  logged to `~/.gbrain/audit/rerank-failures-*.jsonl` with the exact error
  class. Read it before touching config.
- **Verify the byte count, not the exit code, on the GGUF download.** A flaky
  connection can produce a "successful" multi-GB download that's silently
  truncated by hundreds of megabytes; it loads far enough to look promising
  before failing deep into model init.
- **This is a long-lived daemon — give it its own directory, never a git
  worktree.** Worktrees get deleted out from under running processes.
- **Pull the GGUF from a named, verified repo — "search HuggingFace for a
  Qwen3-Reranker conversion" is not safe generic guidance.** A popular
  auto-conversion (`mradermacher/Qwen3-Reranker-4B-GGUF`) is missing its
  classifier-head tensor and produces near-zero, order-scrambled scores that
  look like a config bug but are a broken file (Trap 10).
- **CPU-only is not a slower fallback — it's not viable for a real candidate
  pool.** Verified: 25 realistic-length documents didn't complete reranking
  within 3 minutes at any model size tried, on CPU (Trap 11). Don't set up
  this pack expecting CPU to "just be slower."

## Anti-Patterns

- ❌ **Trusting `gbrain models doctor` alone as proof the reranker works.** It
  confirms reachability, not correctness — always run the `actually-reranks`
  relevance check too.
- ❌ **Testing with `gbrain search` and concluding the reranker is broken.**
  That verb structurally never invokes it; test with `query`.
- ❌ **Picking the newest CUDA build without checking your driver's reported
  version.** A build newer than your driver supports can fail to load; match
  `nvidia-smi`'s reported CUDA version, prefer the older broadly-compatible
  line when in doubt.
- ❌ **Judging throughput or correctness in the first few minutes after any
  Ollama/server restart.** Cold-start and cache-warming costs look identical
  to "the change didn't help" — take two clean measurement windows.
- ❌ **Killing `ollama.exe` and assuming its GPU memory is freed.** Its
  internal `llama-server.exe` child can survive as an orphan holding VRAM;
  check for orphans explicitly (Trap 4 in the gotchas file).
- ❌ **Setting `OLLAMA_NUM_PARALLEL` without checking `ollama ps` afterward.**
  It can silently shrink the model's context window to fit VRAM — fine for
  short embeds, a silent truncation risk for anything longer.
- ❌ **Reading gbrain's TypeScript source to debug "the reranker won't fire"
  before checking the audit log's most recent entries.** 2026-08-28: a real
  session spent an hour tracing `resolveSearchMode`/`hybridSearchCached`
  through gbrain's config-resolution code (all of it correct) before finding
  the actual cause was a llama-server launch flag, visible the whole time in
  `~/.gbrain/audit/rerank-failures-*.jsonl`. Exhaust the tool's own
  diagnostics before reading a dependency's internals.
- ❌ **Debugging "near-zero, scrambled scores" as a pooling or config problem
  before checking which GGUF repo you pulled.** That exact symptom (irrelevant
  document outscoring the relevant one, both scores ~1e-25) is Trap 10's
  signature — a specific popular repo missing its classifier head — not
  something a config change fixes.
- ❌ **Setting this pack up on a CPU-only machine expecting "slower but
  usable."** It isn't, for a real candidate pool (Trap 11) — check for a free
  NVIDIA GPU before starting, not after.

## Related packs

- [`gbrain-windows`](../gbrain-windows/) — run this first. Covers gbrain
  install, connection, MCP registration, and day-2 recovery (including the
  connection-pool exhaustion this pack's activation exam can also trip if run
  during heavy concurrent load).
