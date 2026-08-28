# gbrain-local-embeddings

Swaps gbrain's embedding model for a **smaller, free, local** sibling when your
embedding model and a local reranker are fighting over the same GPU's VRAM.

**Skip this pack if:** you're happy with your current embedding cost/speed, your GPU
already has headroom, or you don't run a second local model (reranker or otherwise)
alongside your embedding model — this solves *contention between two local models*,
not embedding speed in general. If you only run one local model, you likely don't
have the problem this pack fixes.

**Why this exists:** verified 2026-08-28 — a 4B-parameter local embedding model
alone consumed 96% of an 8GB GPU's VRAM (4.4GB loaded, including its context
window) before a local reranker or chat model even entered the picture. Real
queries were taking 20-55+ seconds under the resulting model-swap thrashing.
Dropping to a 0.6B sibling from the same model family roughly **halved real
end-to-end latency** in a controlled, same-hardware test, with **no measurable
accuracy loss** across 5 different real content domains.

See [pack-structure.md](../../docs/pack-structure.md) for section conventions.

## Contract

- **`verify-the-actual-bottleneck-first`** — confirms your embedding model actually
  IS the VRAM bottleneck before you do anything destructive. If you have headroom,
  this pack won't help you and says so.
- **`candidate-model-pulled`** — gets a smaller sibling model from the same family
  as your current one onto the machine.
- **`accuracy-verified-before-committing`** — the step that matters most. Tests the
  smaller model against SEVERAL different real content domains from your own
  brain, not one lucky example, before you commit to a destructive migration.
- **`speed-verified-on-real-content`** — confirms the smaller model is actually
  faster on YOUR real (large) documents, not just in theory.
- **`migration-plan-reviewed`** — a dry-run so you see the real scope (chunk
  count, cost, live-worker warnings) before running the destructive operation.
- **`migration-completed-and-verified`** — runs the real migration and verifies
  completion via gbrain's own status command, with a documented recovery path if
  it stops partway on oversized source files.
- **`restart-supervisor`** — the easy-to-forget cleanup step if you stopped the
  jobs supervisor before migrating.

## Iron Laws

- **Accuracy gets verified across MULTIPLE different content domains, not one
  query.** A single relevant/irrelevant pair can pass by luck; a domain-diverse
  test is what actually earns trust before a whole-brain, hours-long, destructive
  operation.
- **This migration is DESTRUCTIVE and gbrain says so explicitly — believe it.**
  Every stored embedding vector gets wiped and rebuilt (dimension change). Search
  degrades to lexical-only until the rebuild finishes. There is no quiet
  config-only path for a real model change — `gbrain migrate embeddings` is the
  only correct tool, not a manual config edit or `gbrain init`.
- **Stop live workers before migrating.** A running jobs worker's writes get
  counted stale by the migration's own census and silently re-embedded — wasted
  time on an already-hours-long operation.
- **The migration is resumable — use that, don't restart from zero.** Completed
  chunks are never re-touched on a re-run. If it stops partway (commonly: a few
  oversized source files exceeding the bulk-embed timeout), fix the specific
  cause and re-run the SAME command rather than starting over.
- **Two different embed timeouts exist — don't confuse them.**
  `GBRAIN_QUERY_EMBED_TIMEOUT_MS` (default 6s) bounds live interactive queries;
  `GBRAIN_AI_EMBED_TIMEOUT_MS` (default 60s) bounds bulk embed/migrate jobs.
  Raising the wrong one fixes nothing.

## Anti-Patterns

- ❌ **Judging a smaller model's accuracy from one query with one relevant and
  one irrelevant document.** That's a coin flip dressed as evidence. Test across
  domains that are actually different from each other.
- ❌ **Running the destructive migration as a blocking foreground command.** It
  can take 1+ hours on a real brain; run it detached and poll for completion.
- ❌ **Assuming a cold-start speed test proves anything.** The first call after
  any model load pays a one-time warmup cost that looks identical to "the swap
  didn't help." Always compare steady-state (2nd+ call) numbers.
- ❌ **Treating gbrain's dollar cost estimate as your real cost when you're
  already on a local/free provider.** The estimator prices against the real
  provider's published rate regardless of where your requests actually route —
  useful for judging scope, not your actual bill if you're local already.

## Related packs

- [`gbrain-windows`](../gbrain-windows/) — run this first if gbrain itself isn't
  set up yet. Covers install, connection, MCP, and day-2 process-recovery
  patterns (stale workers, orphaned processes) this pack also relies on.
- [`gbrain-local-reranker`](../gbrain-local-reranker/) — the sibling pack for the
  OTHER local model usually sharing your GPU. If you're hitting VRAM contention,
  you likely want to read both packs' gotchas together, not just this one.
