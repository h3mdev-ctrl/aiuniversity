# Planned: the Knowledge / ingest branch — turn sources into compounding memory

Status: **backlog, captured 2026-07-03.** Two planned pack modules + the memory
pattern that makes them worth more than the sum of their notes. Modeled on Andrew's
own Vault ingest pipeline (`x-weekly-ingest`, `realsimpleariel-video-weekly`,
`distill-weekly`, `cohort-weekly-synthesis`, `cohort-monthly-rollup`) — shoulders of
giants: the student gets the shape of a system that already runs daily.

These sit on the **KNOWLEDGE branch** of the [skill tree](skill-tree.md), downstream
of `memory` (they file INTO memory/gbrain/wiki, so `memory` is a prerequisite).

---

## Module 1 — `x-post-ingest`

**Gives you:** point it at an X/Twitter account you track or a saved thread; it pulls
the posts, distills the durable substance (not the noise), and files structured notes
into your memory / gbrain / wiki with source attribution + backlinks.

**Shape (checkpointed, like every pack):**
- `source-reachable` — the fetch path works (an API/cookie/where-does-content-come-from
  check; this is the fragile step, so it gets its own checkpoint + prescribed fix).
- `distills-not-dumps` — a probe: ingest one thread → confirm the output is a
  *distilled note* (claims, not a raw paste), correctly attributed.
- `files-into-memory` — the note lands as a routable memory/gbrain page, doctor-clean.

**Grounded in a real footgun set:** X ingest breaks on auth/cookies and on
rate/scroll limits far more than on the parsing — so the checkpoints + `on_fail`
fixes live where the real pain is (see Andrew's `x-weekly-ingest` operator notes).

## Module 2 — `youtube-transcriber`

**Gives you:** give it a video (or a channel's new uploads); it transcribes locally
(GPU whisper) or via a transcript source, distills the transcript into notes, files
them, and can enrich an existing subject page with what the video actually covered.

**Shape:**
- `transcriber-ready` — whisper/model present and runnable (the setup step people get
  stuck on; prescribed fix covers the GPU/CPU + model-download path).
- `keeps-transcript-drops-audio` — a discipline check: after transcription the raw
  `.wav`/audio is deleted, the transcript + index kept (disk hygiene, from the real
  video pipeline).
- `distills-into-memory` — transcript → distilled note → routable memory page.

**Two-pass distill (from the real pipeline):** a free first pass (e.g. NotebookLM-style
summary) THEN a depth pass with a stronger model — cheaper than one expensive pass over
a long transcript, and higher quality.

---

## The point: memory turns a pile of notes into subject mastery

Ingesting is the easy half. The value is in **how the notes compound** — the exact
question "how does memory work *with* these?". The pattern, when you're **learning a
subject** (a trading style, a language, a domain):

### The rhythm — atomic → weekly → monthly

```
  ingest (daily / ad-hoc)         weekly routine                monthly routine
  ─────────────────────           ──────────────                ───────────────
  x-post-ingest  ┐                reads the week's raw notes     reads the 4 weeklies
  youtube-transc ┼─► raw notes ─► + last week's wrap-up      ─►  + last month's synthesis
  (a thread,     ┘   subjects/X/  ───────────────────────►       ─────────────────────►
   a video)          raw/<date>   subjects/X/weekly/<YYYY-WW>     subjects/X/monthly/<YYYY-MM>
                                  "what's new · what connects ·  THE durable synthesis of
                                   open questions"               the subject so far
```

- **Atomic (per ingest):** each thread/video files a small, dated, attributed note.
  Cheap, high-volume, disposable once rolled up.
- **Weekly wrap-up (scheduled):** a pass — using the SAME action-plan + deterministic
  gate + git-commit discipline as the [`autolearn`](../packs/autolearn) drain — reads
  the week's raw notes **plus last week's wrap-up**, and writes one `weekly/<YYYY-WW>.md`:
  what's genuinely new, what it connects to (backlinks), what's still open. It can
  `supersede` a raw note it has fully absorbed.
- **Monthly synthesis (scheduled):** rolls the four weeklies (+ last month's synthesis)
  into `monthly/<YYYY-MM>.md` — the compounding artifact. Older raw notes can be pruned
  once captured; the synthesis is what you keep.

### Why this compounds (the whole reason to bother)

The monthly synthesis becomes the **context every future session on that subject starts
from.** Add a resolver row — *"when you're about to work on `<subject>`, read
`subjects/<subject>/monthly/<latest>.md` first"* — and your Claude opens each session
already holding a month of distilled learning, not a blank slate. Month over month the
synthesis deepens: you're not re-reading raw tweets, you're standing on your own prior
understanding. That's the difference between a notes folder and a **compounding brain.**

This is precisely the loop Andrew's Vault runs for the trader cohort
(`cohort-weekly-synthesis` → `cohort-monthly-rollup`): weekly tape-reads triangulated
into a monthly regime narrative. The ingest modules are the front door; the
weekly/monthly memory rhythm is what makes the knowledge stick.

### How it reuses what's already built

- **`memory`** — the raw/weekly/monthly files are just memory files with a resolver
  row; the doctor keeps them reachable.
- **`autolearn`'s drain** — the weekly/monthly rollup is the same primitive pointed at
  raw notes instead of git commits: reflect over a batch, emit an action plan
  (create the wrap-up, `supersede` absorbed notes), gate deterministically, one
  revertible commit. The rollup is a *scheduled drain with a different source*.
- **`gbrain` / `obsidian-wiki`** — the synthesis pages backlink into the brain/wiki so
  the subject graph grows as you learn.

⇒ These modules don't need new memory machinery. They need a **source adapter** (X /
YouTube) on the front and the **weekly/monthly rollup cadence** on the back — both
thin layers over primitives the packs already ship.

---

## Open questions to resolve when we build these

- **Source adapters are the fragile part** — auth/cookies/rate limits. Each needs its
  own checkpoint + prescribed fix, and probably per-source `variant`s (e.g. transcript
  API vs local whisper).
- **Where subject files live** — a `subjects/<name>/` tree inside memory, or their own
  store that memory routes to? (Leaning: inside memory, so the doctor + resolver just
  work.)
- **Rollup trigger** — scheduled (cron/Task Scheduler) vs on-demand skill. Likely both,
  same as the autolearn drain (a `--drain-due`-style depth/time gate).
- **Pruning policy** — when a raw note is `supersede`d into a weekly, keep the stamp or
  delete? (Supersede-in-place keeps provenance; matches the drain's existing behavior.)
