# memory-socket

**Memory isn't a store. It's a set of sockets on the agent's lifecycle.**

The [`memory`](../memory/README.md) pack builds the store — a `memory/` folder, an
always-loaded resolver index, a doctor that keeps every note reachable. This pack
builds the **wiring**: the points in a session's life where that store gets read
from and written to.

The distinction is the entire lesson. A store with no sockets audits perfectly and
changes nothing — a library nobody walks into. Most people who say "I set up memory
for Claude" have built exactly that: notes on disk, never recalled.

See [pack-structure.md](../../docs/pack-structure.md) for the section conventions.

---

## Where this comes from: hermes-agent

[nousresearch/hermes-agent](https://github.com/nousresearch/hermes-agent) (MIT) is
the reference implementation of this idea, and the reason this pack exists. People
notice that its memory feels markedly more *persistent and appropriately applied*
than a typical Claude setup, and assume the difference is a better algorithm or a
bigger store. It isn't. **The difference is architectural, and you can port it.**

### Why its memory feels more persistent

Two design decisions, neither of which is about retrieval quality:

**1. Memory is an interface the harness CALLS, not a tool the agent may choose.**
Hermes defines `MemoryProvider` (`agent/memory_provider.py`) with one method per
lifecycle point. The harness invokes them at fixed moments — you do not get to
forget. Contrast the common Claude setup where memory is an MCP tool the model
*might* call if the prompt reminds it to; that memory is only as reliable as the
model's inclination in the moment, which is why it feels absent exactly when you
needed it. In Hermes, retrieval on a user turn is gated only by
`is_trivial_prompt()` — the default is to look, and the exception is to skip.

**2. There is a socket at every point where context is DESTROYED.** Compaction,
subagent return, session end. Most setups have a store and one read path; Hermes
also has write paths at each moment information would otherwise be lost. Persistence
is not the store being good, it is nothing escaping.

### How the pieces actually work

**The retriever** (`plugins/memory/holographic/`, 2,108 lines, entirely local — no
embeddings API, no network). `retrieval.py::search` is a four-stage pipeline:

1. **FTS5 candidates** — SQLite full-text search, pulling `limit * 3` for rerank headroom
2. **Jaccard rerank** — token overlap between query and fact
3. **Trust weighting** — `final_score = relevance * trust_score`
4. **Temporal decay** (optional) — `decay = 0.5 ^ (age_days / half_life)`

Default weights are `fts_weight = 0.6`, `jaccard_weight = 0.4`, and — worth
noticing — **`hrr_weight = 0.0`**. The holographic vector machinery the module is
named after is *off by default in their own shipped config*. Read that as
permission: start lexical, measure, and only add semantic scoring if your own
numbers demand it.

**The trust loop** (`store.py`) is the part most home-grown systems lack. Every fact
carries a `trust_score`; feedback moves it by `_HELPFUL_DELTA = +0.05` and
`_UNHELPFUL_DELTA = -0.10`, and `min_trust_threshold = 0.3` filters the floor. The
asymmetry is the design: **punish twice as hard as you promote**, so a memory that
misleads once is demoted faster than a merely-adequate one is elevated. Without a
loop like this a memory corpus only ever grows, and stale entries compete with good
ones forever.

### Honcho — the other half, and a different problem

Hermes ships a second memory provider, `plugins/memory/honcho/`, implementing the
same `MemoryProvider` interface against [Honcho](https://honcho.dev). It is not a
better store; it answers a **different question**.

| | FactRetriever (holographic) | Honcho |
|---|---|---|
| Models | **facts** — things that are true | **the person** — how they work, what they want |
| Scope | this project's store | cross-session, cross-agent |
| Where it runs | local SQLite | hosted service |
| Delivery | retrieved when relevant | always relevant |
| Built from | what you wrote down | inferred from conversation |

Honcho does cross-session *user modeling* — dialectic Q&A, peer cards, persistent
conclusions — exposed as five tools (`profile`, `search`, `reasoning`, `context`,
`conclude`). The insight worth taking: **a model of the user is not a fact, and must
not be delivered by the fact retriever.** Retrieval matches the prompt, so a user
model filed as memory #57 surfaces only when the user happens to talk about
themselves — which is close to never.

That is why this pack has a separate **`identity`** socket. It is the local,
no-service equivalent of Honcho: derive a capped model of the user from your own
transcripts, regenerate it on a schedule, and inject it at `SessionStart` where it
is always present. You lose Honcho's cross-agent sharing and its inference quality;
you keep the part that matters most and pay nothing.

> One detail worth stealing verbatim: the Honcho plugin carries
> `_INTERNAL_GATEWAY_TURN_RE`, filtering compaction notices and delegation-complete
> messages so harness chatter never becomes durable personal memory. Our
> [`salvage`](files/examples/salvage_pre_compact.py) hook needs the same guard for
> the same reason — see its `HARNESS_RE` comment.

### The socket map

| Socket | Claude Code event | Hermes / Honcho equivalent | Required |
|---|---|---|---|
| **recall** | `UserPromptSubmit` | `MemoryProvider.prefetch` / `queue_prefetch` | **yes** |
| **identity** | `SessionStart` | **Honcho** user representation; `USER.md` injection | **yes** |
| **salvage** | `PreCompact` | `on_pre_compress(messages) -> str` | no |
| **restore** | `PostCompact` | (read side of the same) | no |
| **delegate** | `SubagentStop` | `on_delegation` | no |
| **harvest** | `SessionEnd` | `on_session_end(messages)` | no |

Each has a working reference implementation in [`files/examples/`](files/examples/),
one file per socket. They are deliberately **self-contained** — `memory_dir()`
repeats across files so any one can be copied on its own — and each carries, in
comments, the specific defect it cost us to find.

### Why port the sockets instead of adopting Hermes

Hermes is a whole agent harness. Its actual product is **provider independence** —
run Hermes-4, a local model, Bedrock, OpenRouter, and swap without rewriting — plus
an embeddable gateway you can build a product on. Those are good reasons to adopt
it. "I want better memory" is not one of them, because the memory is a plugin you
can read in an afternoon and re-implement against whatever harness you already have.

If you already like your harness, porting wins on three counts:

- **Your harness is probably better at your actual work.** For coding, Claude Code's
  tools and model beat what a second harness would drive them with.
- **Your corpus already exists.** Hermes' store starts empty and has to earn every
  fact. Wiring sockets into notes you already have is the cheap half.
- **No credential question.** The sockets are local files and SQLite — nothing to
  authenticate. Running Hermes against Anthropic means either a metered Console API
  key, or the subscription path in `agent/anthropic_adapter.py`, which works by
  reading Claude Code's own credential file and presenting itself as Claude Code
  (spoofed CLI version, Claude Code's system prompt, `oauth-2025-04-20` beta
  headers). That is outside what a Claude subscription licenses and breaks whenever
  the version check moves. If you want to run Hermes properly, point it at a
  provider that sells you access: Nous Portal, OpenRouter, or a local model.

---

## Contract

- **Six sockets, one audit.** `socket_doctor.py --list` shows every lifecycle point,
  what is plugged in, and what is dark. `--check` exits non-zero if a **required**
  socket (recall, identity) is unwired.
- **Registered ≠ live.** `--probe <socket>` *executes* the registered hook with a
  realistic payload and demands output. A hook that runs clean and emits nothing is
  reported **DARK**, not healthy.
- **The probe reproduces the real call.** It passes the actual `cwd`, because a
  recall hook worth having resolves memory *per project* — a probe with a
  placeholder `cwd` gets correctly refused and then reports a working hook as
  broken.
- **Every example hook exits 0, always.** Memory is an enhancement; it never blocks
  a turn, a compaction, or a shutdown.
- **The store comes first.** Step 1 runs the `memory` module, so this pack works
  from nothing.

## Iron Laws

- **A store without a recall socket is not memory.** It is a folder. `recall` is the
  only non-optional socket besides `identity`, because every other socket exists to
  feed something that must eventually be *read*.
- **Silence is a failure state, not a pass.** The worst outcome is a hook that is
  registered, exits 0, and does nothing — it survives every audit you would think to
  run. This is why the doctor probes rather than trusting registration.
- **Resolve the store per project, and check the key before any cache.** One global
  store served to every directory means session B is handed session A's conclusions
  under a banner saying "treat as authoritative". If you cache the index, verify the
  *directory* before any freshness short-circuit — a TTL that returns early without
  re-checking which project it built for leaks across projects.
- **Never fall back to "the most recent file".** In `restore`, using the newest carry
  file when `session_id` is missing looks like robustness and is a data leak:
  concurrent sessions mean the newest file is often someone else's, and it gets
  printed as established fact of *this* session.
- **Append atomically; rotate with `os.replace`.** Read-modify-write on a log that
  parallel subagents append to destroys records. Measured at 30 concurrent writers:
  one corrupt line, two lost.
- **Bound anything that runs while the user waits.** `salvage` scans the transcript
  during compaction; one pasted build log took an unbounded regex sweep to 3.1s.

## Anti-Patterns

- ❌ **"I set up memory" = created a `memory/` folder.** No socket, no recall. This is
  the default failure and it is invisible, because the folder looks right.
- ❌ **Ranking without an absolute relevance floor.** BM25 scores are normalised
  *within* a result set, so the top 3 of a bad match look identical to the top 3 of a
  good one — measured, positives scored 0.186–0.399 against negatives 0.277–0.385,
  fully overlapping. A relative rank is a fine ranker and a useless classifier. With
  no floor, every prompt fills all slots with noise and the user learns to skip the
  block.
- ❌ **Delivering the user model through retrieval.** It only surfaces when the user
  talks about themselves. Wrong socket: it belongs in `identity`, always-on.
- ❌ **Letting the always-on tier grow.** Append-only user models become
  indistinguishable from the corpus they were meant to summarise, and stale lines
  read as current. Cap it and *regenerate*; let the cap force consolidation.
- ❌ **Calling a model inside `SessionEnd`.** The budget is ~1.5s across all
  SessionEnd hooks and it cannot inject context. Poke your existing pipeline; do the
  work elsewhere.
- ❌ **Trusting `subprocess.run(timeout=)` on Windows.** If the child spawns a
  grandchild inheriting the stdout pipe, the kill path blocks with no timeout — a
  1.0s budget was measured blocking 60s. Use `DEVNULL` on all three streams.
- ❌ **Treating an empty probe as proof the hook is broken.** Run a positive control
  from a project that *has* memory first. An empty result and a genuine absence look
  identical.
- ❌ **Probing on a machine you care about without reading what the hooks do.**
  `--probe` executes the user's real hooks; ones that write logs or kick jobs will do
  so.

## Related

- [`memory`](../memory/README.md) — the store this pack wires. Run it first (step 1
  does).
- [`autolearn`](../autolearn/README.md) — the extraction pipeline the `harvest`
  socket pokes. Without it, `harvest` has nothing to queue into.
- [`identity`](../identity/README.md) — writes the durable `user_profile`; the
  `identity` socket delivers the *derived, current* half alongside it.
- [`hooks`](../hooks/README.md) — the mechanics of registering hooks safely.
- [memory-layers.md](../../docs/memory-layers.md) — the four-layer model by time
  horizon. Sockets are how layers 1, 2 and 4 actually connect to a session.
- [hooks-research.md](../../docs/hooks-research.md) — the lifecycle-event surface
  these sockets attach to.
