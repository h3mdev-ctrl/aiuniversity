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

> **Sharpened 2026-09-09 — "under load" is too narrow, and that framing costs
> hours.** On an idle single-user box with nothing else running, EVERY
> `gbrain query` starved its own embeds. The real mechanism is structural, not
> contention: the expansion LLM loads onto the GPU per query (**Trap 13**) and
> Ollama then evicts the embedder because it sizes models by `num_ctx` rather
> than actual use (**Trap 12**). Read those two before assuming you need load
> to reproduce this.

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

## Trap 10: "pull a community GGUF conversion" is not safe generic guidance — one specific popular repo is silently broken

Found on a second install (2026-08-28, different machine, CPU-only). The
`mradermacher/Qwen3-Reranker-4B-GGUF` repo — a "static quants" automatic
conversion, one of the first results for a generic "Qwen3 Reranker GGUF"
search — is missing the `cls.output.weight` tensor: the actual yes/no
classifier head Qwen3-Reranker needs to produce a meaningful score at all.

**Symptom:** the server answers HTTP 200, `gbrain models doctor` shows it
reachable, but scores are near-zero and effectively random — measured: the
*irrelevant* document outscored the relevant one, both around `1e-25`. This
LOOKS like a pooling/config bug (wrong pooling head, tokenizer mismatch) but
is actually a broken source file — confirmed against a known upstream issue,
[ggml-org/llama.cpp#16407](https://github.com/ggml-org/llama.cpp/issues/16407).

**Fix — use a conversion confirmed to include the classifier head.** Two
repos exist specifically because of this failure mode (their own READMEs
name it):
- 4B: `huggingface.co/gscoppino/Qwen3-Reranker-4B-GGUF-llama_cpp`
- 0.6B: `huggingface.co/Voodisss/Qwen3-Reranker-0.6B-GGUF-llama_cpp`

Verified working (relevant=0.9869–0.9999 vs irrelevant<0.0001, both model
sizes). If you already have a GGUF from a different repo and see near-zero,
order-scrambled scores, don't debug pooling config first — switch the model
file.

## Trap 11: CPU-only is not a slower fallback for real candidate pools — it's not viable at all

The original guidance in this pack ("much slower on first call, 8-15s cold
start vs <1s on GPU") was measured against a tiny synthetic test and never
validated against a real gbrain candidate pool. Corrected 2026-08-28 on a
CPU-only machine (Intel integrated graphics, no NVIDIA card), using the
Trap 10 fixed GGUFs so this isn't the broken-file symptom:

25 candidates at realistic gbrain chunk length (~800 tokens/doc) **did not
complete within 3 minutes**, at either model size (4B or 0.6B). 25 SHORT
synthetic docs (~150 tokens each) completed in 29.5s on the 0.6B model — the
same 25 docs at realistic length again exceeded 180s. **Token volume, not
document count, drives the cost, and it scales worse than linearly**
(5.3× more tokens produced at least 6×+ more elapsed time before the test
was stopped — consistent with quadratic attention cost inside one batched
rerank call).

**If you don't have an NVIDIA GPU with free VRAM, skip this pack entirely.**
Raising `search.reranker.timeout_ms` or shrinking `search.reranker.top_n_in`
buys some headroom but does not fix the underlying throughput gap — a local
CPU reranker will make gbrain feel broken (queries that never return) rather
than merely slow.

## Trap 12: Ollama sizes VRAM from `num_ctx`, not actual use — an unpinned model evicts itself on every call

Verified 2026-09-09. This is the root cause behind most of Trap 3, and it is
invisible unless you read Ollama's own server log.

Ollama decides whether a model fits by **predicting** memory from its context
length, not by measuring what the model needs. A 0.6B embedding model
(`qwen3-embedding:0.6b`, ~600MB of weights) loaded at Ollama's default
`num_ctx=16384` is predicted at **6.6 GiB**:

```
msg="llama-server model predicted to exceed available memory, evicting"
predicted="6.6 GiB"  predicted_num_ctx=16384  available="3.4 GiB"
```

On an 8GB card that means the embedder is evicted and cold-reloaded **on every
single embed call**. Each cold load costs ~2.6s; a warm one costs ~50ms. Since
`gbrain query` issues **3** query embeds against **one** 6000ms deadline,
3 × 2.6s blows it every time, gbrain drops the vector arm, and search silently
degrades to keyword-only — with a reranker that is up, healthy and never called.

**The tell:** `ollama ps` is EMPTY right after a gbrain call but populated after
a hand-rolled `curl` to the same endpoint. Same server, same model, different
caller, opposite behaviour. `OLLAMA_KEEP_ALIVE=2h` does NOT prevent this — the
eviction is a fit decision, not a keep-alive expiry, so keep-alive looks
correctly set while the model is evicted anyway.

**Fix — pin `num_ctx` per model via a Modelfile, keeping the SAME tag** so the
brain's existing embeddings stay valid (same weights, same vectors, only a
runtime parameter added):

```bash
ollama show --modelfile qwen3-embedding:0.6b > modelfile.bak   # restore path
printf 'FROM <blob-path-from-the-backup>\nTEMPLATE {{ .Prompt }}\nPARAMETER num_ctx 8192\n' > Modelfile
ollama create qwen3-embedding:0.6b -f Modelfile
```

Measured effect: predicted 6.6 GiB → **1.0 GiB**, reserved size 3.8GB → 2.9GB,
model stays resident, embeds drop to 30–50ms.

**Do NOT reach for `OLLAMA_CONTEXT_LENGTH`** to fix this — it is global and
would shrink every chat model on the box too (see Trap 6 for why a silently
shrunk context is a truncation risk on long content). Pin per model.

Pick the context from your real chunk size, not the model's native max: 8192
covers any realistic gbrain chunk with headroom. 4096 also worked and saved
another 500MB, but leaves less margin for a long chunk on a re-embed.

## Trap 13: gbrain's expansion LLM shares the GPU and loads PER QUERY — it, not the reranker, is usually what starves the embedder

Verified 2026-09-09. Trap 3 says embeds can starve "under load, e.g. a
concurrent reindex". That framing is too narrow and sent a whole session
chasing the wrong thing: on a single-user idle box, with nothing else running,
**every** `gbrain query` starved its own embeds.

Cause: gbrain's `models.default` is the LLM used for multi-query expansion, and
it is called on EVERY search. Check what it actually resolves to:

```bash
gbrain config get models.default
```

On this box it was `openai:gpt-4o-mini` — which, with `OPENAI_BASE_URL` pointed
at local Ollama, is served by a local Ollama tag of the same name that pointed
at **llama3.1:8b**. So each query loaded a ~5.4GB chat model onto the GPU,
`available` dropped to 1.1 GiB, and the embedder was evicted per Trap 12. The
reranker (370MB) was never the problem.

**Confirm it is the expansion call**, not the reranker, before changing
anything — the log shows the ordering plainly:

```
POST "/v1/responses"          <- expansion LLM loads (5-6s)
available="1.1 GiB"           <- GPU now full
"...predicted to exceed available memory, evicting"
POST "/v1/embeddings"  499    <- embed gives up
```

**Fix:** point `models.default` at a small, context-pinned local model. Do NOT
re-point the shared `gpt-4o-mini` Ollama tag — that silently changes every
consumer of the alias on the box:

```bash
ollama pull llama3.2:1b
printf 'FROM llama3.2:1b\nPARAMETER num_ctx 4096\n' > Modelfile
ollama create llama3.2-1b-4k -f Modelfile
gbrain config set models.default openai:llama3.2-1b-4k
```

Use the `openai:` prefix, never `ollama:` — gbrain's native ollama recipe is
embed-only and silently will not serve chat.

**Is a 1B good enough?** For expansion it is a utility-tier task (gbrain's own
help calls it "a Haiku call per search"). The heavyweight local paths are
already off: dream's deep extract is structural-only and `propose_takes` is
Anthropic-only, so `models.default` is in practice the expansion model and
little else. Expansion *quality* on a 1B is untested — the variants it writes
are weaker than an 8B's; measure with `gbrain eval` if it matters to you.

Measured effect, 6-run gate at the DEFAULT 6000ms embed deadline:
**0/5 PASS → 6/6 PASS**, query wall-clock 85s → 13–16s, all three models
resident simultaneously, no evictions.

## Trap 14: reranker VRAM is dominated by batch/context buffers, not the model — but never trim below your real chunk length

Verified 2026-09-09. Trap 2b tells you to launch with
`--batch-size 4096 --ubatch-size 4096`. That is correct, but know what it costs,
because on a shared 8GB card it is the difference between everything fitting and
nothing fitting:

| Launch flags (same 609MB Q8_0 model) | VRAM |
|---|---|
| `--ubatch-size 2048 -c 4096` | **~4,000 MiB** |
| `--ubatch-size 1536 -c 2048` | **370 MiB** |

A ~600MB model reserving 4GB is all compute buffers and KV cache. Scores were
**byte-identical** across both configs, so trimming costs no quality — only
capacity.

**But there is a hard floor: `--ubatch-size` must exceed your largest real
chunk's token count.** Trimming to 1536 reintroduced Trap 2b on exactly the
chunks big enough to matter:

```
rerank HTTP 500: input (1540 tokens) is too large to process ... (current batch size: 1536)
rerank HTTP 500: input (1625 tokens) is too large ...
```

Real gbrain chunks measured **1540–1625 tokens** — well above the
few-hundred-token figure a synthetic test suggests. `--ubatch-size 4096` with
`-c 4096` cleared it and still left headroom alongside a pinned embedder and
expansion model.

**Budget the whole GPU, not one process.** Three things want the card and all
three must be pinned or they will fight: the embedder (Trap 12), the expansion
LLM (Trap 13), and the reranker's buffers (this trap). A working 8GB split:

```
qwen3-embedding:0.6b   ctx 8192          2.9 GB
llama3.2-1b-4k         ctx 4096          1.5 GB
reranker 0.6B Q8_0     ubatch/-c 4096   ~1.3 GB
                                        -------
                                        ~5.7 GB of 8 GB, ~2.3 GB headroom
```

## Trap 15: two gbrain config surfaces that report success and do nothing

Both verified 2026-09-09; both cost real time because the tool prints "Set ...".

1. **`gbrain config set <key>` can be silently shadowed by the file plane.**
   `gbrain config set expansion_model ...` printed `Set expansion_model = ...`,
   but `config get` still returned the OLD value with the note
   `source: file/env plane (... or env) — a DB-plane value also exists and is
   shadowed at runtime`. `set` writes the DB plane; the on-disk gbrain config
   file wins. **Always `config get` after `config set`** and read the `source:`
   line. To change a file-plane key you must edit that config file — it holds
   API keys, so back it up, edit the single key, and never dump it to a
   transcript.

2. **`search.expansion=false` does not suppress expansion; only `--no-expand`
   does.** The config resolves and displays correctly
   (`expansion = false [config: search.expansion]`) but the `/v1/responses`
   expansion call still fires. Measured: config-off = embed failure on 5/5 runs
   and the reranker never fired; flag-off = 0/3 failures and the reranker fired
   every time. Use the flag; do not trust the knob.

## Measured payoff — is the local reranker actually worth it?

Verified 2026-09-09 on a real 7,600-page brain (58,676 chunks). 20 qrels built
mechanically (a distinctive sentence lifted from each of 20 sampled chunks;
ground truth = the page it came from), `gbrain eval --qrels ... --k 5`, same
queries both arms, reranker toggled between runs:

| Metric | Reranker OFF | Reranker ON | Δ |
|---|---|---|---|
| P@5 | 0.16 | 0.18 | +0.02 |
| R@5 | 0.80 | 0.90 | +0.10 |
| **MRR** | 0.49 | **0.82** | **+0.33 (+67%)** |
| **nDCG@5** | 0.56 | **0.84** | **+0.28 (+50%)** |

MRR 0.49 → 0.82 means the correct page moves from about rank 2 to about rank
1.2. R@5 rising is consistent, not suspect: reranking cannot change the
candidate pool, but it pulls relevant docs *into* the top 5, which is what R@5
measures.

**Limits, stated honestly:** n=20, single run, no repeats, and queries lifted
verbatim from chunks favour lexical matching — so treat the direction and
magnitude as solid, the absolute values as optimistic. Both arms saw identical
queries, so the comparison itself is fair.

This independently confirms the pack's headline claim (gbrain's own docs cite a
60% top-1 reshuffle). Run it on your own brain before and after — it is the only
way to know the reranker is earning its GPU.
