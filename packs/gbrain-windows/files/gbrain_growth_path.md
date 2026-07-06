# Building on the hub: what your brain can become

> The hub starts as a handful of notes. Its value is not in any one page — it's in
> **what accumulates and how it connects.** This is the ladder from "a few notes" to
> a brain that's genuinely load-bearing, and what each rung gives you. You don't
> climb it on day one; you climb it as the payoff earns the next rung.

## The governing principle (and its one caveat)

**The more you give it, the more useful it gets — because recall and *connection*
scale with what's inside.** A 30-page brain answers "what do I know about X." A
3,000-page, well-linked brain answers "who, what, and which past decision connect to
X across everything I do" — and *that* cross-domain link is the thing a notes folder
can never do. Value grows faster than page count, because every new page can link to
the ones already there.

**The caveat: more *signal*, not more *noise*.** A brain full of junk is worse than a
small clean one — a bad page dilutes every search. So "capture more" only pays if
what you capture is worth keeping. That tension is exactly the lean-vs-eager choice
below: eager captures more (more raw context, faster-filling brain) at the cost of
more noise-risk and more tokens; lean captures less but curated. Neither is wrong —
they're different bets on the signal/noise/cost triangle.

## The ladder

**Rung 0 — capture + search-first (the lean default).** A few pages; before you
research anything, search the brain. *Payoff:* you stop re-deriving what you already
figured out last month. This alone is worth it.

**Rung 1 — the entity graph.** `people/`, `companies/`, `concepts/` with back-links.
*Payoff:* the first cross-domain connections surface — a person from one area shows
up when you're working in another. This is where the "hub, not folder" value starts.

**Rung 2 — eager capture.** Scan every message, save ideas/entities as they come up.
*Payoff:* nothing worth keeping slips through; the brain fills fast and its recall
gets dense. *Cost:* a per-message tax (see the token table below) — this is the
"aggressive" cadence, a real choice, not automatic.

**Rung 3 — ingest a corpus.** Pull whole sources in — books, articles, videos, X
threads — as structured pages, and rank concepts by how often they recur.
*Payoff:* a searchable knowledge base you can query instead of re-reading. *Cost:*
real (ingest is expensive; the cross-referencing is the multiplier — see
`../obsidian-wiki/README.md` "Token cost").

**Rung 4 — code intelligence.** Index a codebase into the brain; ask
`code-def` / `code-refs` / `code-callers` instead of grep. *Payoff:* symbol-aware
code search that compounds — "what calls this / where's it defined / what depends on
it" answered semantically, across the whole repo.

**Rung 5 — automation.** A nightly consolidation ("dream": links, embeddings,
dedup), the brain feeding your daily brief, pages materialising to a wiki.
*Payoff:* the brain maintains and surfaces *itself* — you stop tending it by hand.

## What "meaningful to them" looks like at the top

At scale, a single question stops returning one note and starts returning a *web*:
ask about a topic and the brain hands you the person you met who cares about it, the
concept it belongs to, the source where you first read it, and (if you climbed rung
4) the code that implements it — pulled across every area of your life at once. A
mature hub is measured in thousands of pages and thousands of links; a question
becomes a **traversal**, not a lookup. That is the thing you're building toward — and
why the on-ramp (rung 0) is deliberately small: you earn each rung with the payoff of
the last.

## Token cost: lean vs eager (rough, Claude-side only)

The choice is about the **per-message action cost**, not availability (the MCP tools
are there either way). Embedding/chunking runs on gbrain's own embedder (local
Ollama or your configured provider), **off your Claude token budget** — so these are
Claude-side figures only.

| | **Lean** (default) | **Eager** (aggressive) |
|---|---|---|
| Per message | ~0 — no per-turn scan | a "should I capture this?" pass **every** turn |
| When gbrain fires | only when it earns it (search before researching, capture what's clearly worth keeping) | scans + captures on ~every substantive message |
| Rough tokens / session | **~5–15k**, concentrated on the relevant turns | **~30–80k**, plus a little latency on every reply |
| Relative | baseline | **~3–5× lean** |
| On a subscription plan | quota noise | more quota; still not out-of-pocket |
| On pay-per-token API | ~cents | ~10–20¢/session |
| Best for | most people — no tax on trivial turns | power users who want maximal capture and accept the cost |

Rule of thumb: **start lean.** Move to eager when you've felt the brain be useful and
decide you want it capturing everything — by then you'll also have the judgment to
keep the signal high. You can flip cadence any time (`setup_gbrain_usage.py --install`
for lean, `--install --eager` for eager) — it's one idempotent edit to your CLAUDE.md.
