# Memory as four layers by time horizon (and the one we're missing)

An external practitioner (Matt Gunnin, running two coordinated agents in production for
6 months) independently published almost exactly the architecture these packs teach —
same primitives, **same gbrain** (garrytan/gbrain). That's strong convergence: it says
the shape is right, not idiosyncratic. His framing — **memory as layers with different
time horizons** — is a clean way to organise what the packs already do, and it surfaces
the one layer we don't yet ship.

Source: Matt Gunnin, "The 4-layer memory architecture I run across 2 AI agents in
production" (X, 2026-07-02). Captured in gbrain: `concepts/four-layer-agent-memory-architecture`.

## The four layers → our packs

| Layer (time horizon) | What it is | Our pack(s) |
|---|---|---|
| **1. In-session context** | identity file + an always-loaded memory *index* pointing to per-fact files (name/description/type/body), read on demand | **identity** + **memory** (this is exactly `MEMORY.md` + `<type>_<topic>.md`) + **context** (SessionStart orientation, PostCompact re-read) + **memory-socket** (the *recall* socket that pulls the relevant files into each prompt, and the *identity* socket) |
| **2. Post-session retention** | end-of-session: curated facts (decisions, failure+fix, confirmed prefs) pushed to a store, then **fact → human/gate review → index entry** | **autolearn** (the drain: capture → deterministic gate → memory entry — the same "approval gate before permanent") + **wrap-up** (the close-out that runs it) + **episodes** (the failure+fix *instance*, recalled on identifiers; the generalised lesson still goes to memory) + **memory-socket** (salvage before compaction, trust votes after) |
| **3. Shared long-term state** | a shared, append-only **live-context log** + decisions log both/every agent reads before replying and appends after each turn | **— not shipped —** (see below) |
| **4. Searchable knowledge** | a compiled wiki / semantic search over everything written down; "recall", not "carry" | **gbrain-windows** (+ **obsidian-wiki** as the vault it indexes) |

Three of the four are things these packs already set up and verify. The convergence is
the validation; the gap is the lesson.

## Cutting across all four: liveness (added 2026-09-30)

The layers describe *where* memory lives. They say nothing about whether the
machinery that moves it is **running**. On the author's own system, four parts
failed silently at once, and every health check reported HEALTHY the whole time:

| What failed | For how long | Why every check still passed |
|---|---|---|
| The recall hook's semantic branch | 3 weeks | a `NameError` inside a fail-open `try/except: pass`; the lexical branch kept printing, so "the hook produced output" stayed true |
| …and behind it, the embed call | same | a 1.5s client timeout against a 3.1s cold model load; the disconnect aborted the load, so the model was never resident |
| The nightly identity refresh | 1 month | a stale file kept being injected; nothing checked its age |
| The post-session scanner (layer 2's producer) | 2 weeks | one duplicate row rolled back every batch; the backlog check counted an *empty queue* as "OK" |

The generalisable rule: **a check must be able to tell the two states apart.**
"Registered" is not "running"; "printed something" is not "every branch ran";
"nothing pending" is not "the producer is alive". The memory-socket pack's
branch-level probe, the episodes pack's trace, and "time since the producer last
*committed*" are the concrete forms. If a check would pass on the broken system,
it is decoration.

## Layer 3 — a shared live-context log (planned `shared-context` module)

*Status 2026-09-30:* running in production on the author's box as a signed,
append-only activity log (one line per ship/decision, last 12 injected at
SessionStart, rotated past 120 lines). Not yet packaged; the design below stands.

Layer 3 is what makes memory work across **more than one agent/session at a time**. A
single Claude doesn't need it; the moment you run several — a Telegram bridge, a cloud
Claude, scheduled tasks, parallel worktrees — they **drift**: one thinks the project state
is X, another thinks Y, and within a week they contradict each other.

The fix isn't message-passing or an inter-agent API. It's **one shared append-only file**
with an invariant:

> **Before every reply, read the live-context log. After every meaningful turn, append to it.**

Entry discipline (the cross-agent sync invariant that makes it safe):
- Each entry is **signed**: who (session/agent), channel, kind, one-line summary, timestamp.
- **Append-only** — never edit another session's entry.
- If a prior entry is relevant, **acknowledge it explicitly** in the next turn.
- Significant decisions also land in a **decisions log** with rationale.

### Shape of the pack (checkpointed, like the rest)

- `log-present` — a `live-context.md` (+ `decisions.md`) exists in the shared store
  (memory folder or the wiki/vault), with the invariant written at the top.
- `entries-are-signed` — a probe: append a test entry → confirm it carries
  who/channel/kind/summary/timestamp and is append-only (the writer never rewrites prior lines).
- `read-before-reply wired` — the invariant is in the constitution (CLAUDE.md), so every
  session actually reads the log at start. Verifiable: the rule is present + a session
  demonstrably references a prior entry.

### Why it reuses what's here

- It's a **memory file** (or a wiki page) — the doctor + resolver already keep it reachable.
- The append discipline is the same **append-only + provenance** rule the autolearn drain
  already follows (signed, never clobber).
- gbrain indexes it for Layer 4, so "what did the other agent decide last week" is a query.

⇒ Like the ingest modules, this needs no new engine — a shared file + an invariant in the
constitution + a signed-append helper. It's the highest-value missing piece because it's
the layer that turns "several Claudes" from a drift risk into a coordinated team.

## For our own box (not just the product)

Andrew already runs multiple Claude instances (bridge butler, cloud `@claude`, scheduled
tasks, worktrees) against one memory. We have `decisions/log.md` (close to the decisions
log) but **no real-time live-context handshake** — so a worktree session and the bridge
can each act without seeing what the other just did. Adopting a signed, append-only
`live-context.md` with the read-before-reply invariant is the concrete thing to try. See
the personal-workflow note that accompanies this doc.
