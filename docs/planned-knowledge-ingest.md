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

## Patterns adopted from gbrain's ingest skills (attributed)

gbrain ([github.com/garrytan/gbrain](https://github.com/garrytan/gbrain), MIT) ships
a set of production ingest skills (`ingest`, `media-ingest`, `article-enrichment`,
`voice-note-ingest`) covering the exact ground both modules do. aiuniversity does
**not** adopt gbrain's distribution channel (skillpack + scaffold) — those stay
separate — but adopts the **content patterns** that make those skills work in
production, with attribution. Both planned modules bake these in from day one.

### Iron Laws (non-negotiables — every module gets a "Contract" section listing these)

1. **File by primary subject, not by format.** A video *about a person* files to
   `people/<name>` (+ back-links); it does NOT live in `media/videos/` just because
   it's a video. Filing by format is the classic anti-pattern that turns a brain into
   a chronological dump.
2. **Entity back-links — a media item is NOT fully ingested until entity
   propagation is complete.** Every person / company mentioned gets a back-link
   *from their page to this one*. An unlinked mention is a broken brain.
3. **Verbatim quotes only.** Paraphrasing a quote demotes it to prose — "the author
   argues that…" is not a quote. Quotes go in a **`## Quotable Lines`** section, exact
   wording, ≥3 per article.
4. **Preserve the raw source.** For every ingest, the original (transcript, thread,
   PDF, screenshot) lives on disk *and* is linked from the page in a collapsed
   `<details>` block. A page without provenance is unverifiable.
5. **Speaker-diarised transcripts** for video / podcast — plain whisper gives you a
   wall of text with no attribution. Diarised (word-level speaker labels, e.g.
   Diarize.io / pyannote) is the bar; quotes need real names, not `speaker_0`.

### The canonical structured page format (adopted for both modules)

Every enriched ingest page ends up in this shape — atomic notes, weekly wrap-ups,
and monthly syntheses all inherit it:

```markdown
# {Title — a compelling headline, NOT "This video discusses…"}

## Executive Summary        # 2-3 sentences, the ONE thing worth remembering
## Why It Matters           # tied to specific brain context (query'd, not generic)
## Quotable Lines           # ≥3 VERBATIM, with speaker attribution when applicable
## Key Insights             # ≥3 real insights (not topic labels)
## Surprising / Counterintuitive
## See Also                 # standard markdown links, not [[wiki-links]]

<details><summary>Raw source</summary>
{original transcript / thread / article text — never lost}
</details>
```

### Discipline patterns (module checkpoints must test these)

- **Idempotency via a frontmatter flag** — a `needs_enrichment: true` (or
  `needs_rollup: true`) flag on the raw page. Enrichment / rollup clears it. Re-running
  the module skips already-enriched pages instead of clobbering them. Cheap correctness.
- **Test-3-before-bulk.** When processing a batch (a channel's new uploads, a week's
  threads), do 3–5 first, *read the output*, fix the approach, then run the rest. The
  cost of testing 3 is near-zero; the cost of cleaning up 100 bad pages is enormous.
  Explicit anti-pattern to name in every ingest module's docs.
- **Two-pass model routing.** Draft on **Haiku / Sonnet** (cheap); spot-check 5 with a
  quality bar (verbatim-quote fidelity, entity coverage, "Why It Matters" specificity).
  If quotes paraphrase or entities miss, promote *the failing batch* to **Opus** and
  re-run — don't blanket-upgrade the model.
- **Anti-Patterns section, explicit and named.** Every module SKILL.md ships an
  `## Anti-Patterns` list — the specific failure modes users hit — with a leading ❌
  and one line of what to do instead. Teaching by naming the ways it goes wrong.
- **Cost-aware cross-referencing.** Ingest is expensive and the entity/cross-ref
  pass is the multiplier — roughly O(entities), a read + back-link + timeline write
  per notable entity. Budget ~20–30k tokens for a modest ingest, ~50k+ for a dense
  one, ~250–500k for a week's batch (the cross-ref pass ~half). Three levers, all
  of which each module must support: **(a)** delegate bulk page-writing to
  Sonnet/Haiku sub-agents off the main context (orchestrator synthesises, workers
  write); **(b)** a **notability gate** so cross-links only fire for entities worth
  tracking — this directly caps the multiplier; **(c)** test-3-before-bulk. A module
  that back-links every passing mention with no notability gate will surprise the
  user with the bill.

### Worked example: the deterministic cross-link helper (why we chose a script over a model)

Full reference implementation: [`examples/vault_crosslink.py`](examples/vault_crosslink.py).
It's the concrete answer to "script the deterministic 80%" — and it earned its place
by being run on a real wiki, not argued for on a whiteboard.

**The decision.** Cross-referencing during an ingest *looks* like an LLM job, so the
instinct is to route it to a cheap model (Haiku) to save tokens. But when you break
it down, the expensive part — the **O(entities) backlink grind** (open each connected
entity's page, append the reciprocal link) — is **pure string manipulation**. It has
no judgment in it. So the right move isn't "use a cheaper model", it's **use no model**:
a script does the plumbing (the links), and the model is reserved for the synthesis
(the prose that explains *why* two entities relate). Deterministic-first: before
reaching for Haiku/Sonnet/Opus, ask whether the task is actually string work.

**Why not just use Haiku for it?** Two reasons that only became clear from the real
data: (1) a sub-agent's spawn overhead (~8–15K tokens) exceeds the ~100-token cost of
a single append, so delegating small mechanical ops to a model *loses*; (2) the
mechanical output is verifiable deterministically (did the link land? is it reciprocal
now?), so a model adds cost without adding safety. A script is both cheaper and safer.

**What it does** (each mode dry-runs by default; `--apply` writes; all idempotent):
- `--audit` — broken wikilinks + missing entity↔entity backlink reciprocity.
- `--fix` — add the missing reciprocal backlinks (bare `- [[A]]`, asserting no
  directional claim, since mentor/mentee-style relationships are asymmetric).
- `--fix-bugs` — de-link namespace leaks (`[[project_x]]` → `project_x`) that render
  broken in the published site.
- `--broken` — triage the dangling links into **bug / should-exist / intentional**,
  so a human knows which missing pages are worth creating (synthesis) vs. leaving.

**The evidence (why it's in here at all).** Run once on a real 119-entity, 853-page,
18,000-wikilink wiki, it found **121 missing backlinks** and added them, and surfaced
~1,150 dangling links (incl. namespace-leak bugs the manual pass never caught). Cost:
**0 model tokens.** The same 121 backlinks by hand would have been ~150–350k tokens of
a top-tier model — for zero judgment. That's the whole thesis in one number.

**The reusable lesson for these packs:** *installing a capability isn't using it, and
the mechanical half of using it shouldn't spend model tokens.* Every ingest module's
cross-ref step should call a helper shaped like this and keep the model on the prose.

### Where these land in the module checkpoints

Fold into the checkpoints already sketched above:

- `x-post-ingest / distills-not-dumps` — the check *becomes* "output contains
  Executive Summary + Quotable Lines (verbatim) + Why It Matters + entity back-links"
  (not just "not a raw paste").
- `x-post-ingest / files-into-memory` — check adds "filed under the primary subject's
  path, not `media/x/`" and "`<details>` block preserves raw thread".
- `youtube-transcriber / distills-into-memory` — check adds "diarised transcript
  present + linked + speakers have real names" and "entity back-links propagated".
- All ingest checkpoints inherit an **idempotency probe** (re-run on an already-processed
  page is a no-op).

Nothing about this depends on gbrain's tools specifically — it's the *shape* of a
useful ingest page. If we ever ship a variant that files into an obsidian-wiki + memory
combo instead of gbrain, the same contract applies.

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
