# Skill tree — modules as a chooseable, RPG-style progression

Status: **idea captured 2026-07-03, to develop later.** Andrew's concept. This is
a direction, not a spec — recorded so it isn't lost.

## The idea

Instead of a fixed foundation that always pulls the same modules, treat packs like
an **RPG skill tree**: a catalog of available modules, branches you choose, and
prerequisites that gate what unlocks. You pick the loadout that fits you (a trader
takes the trading branch; a dev takes devex) rather than installing everything.

## Where we are today

- Each pack is a self-contained, versioned folder (`packs/<name>/`).
- Composition is the `modules:` primitive: an umbrella pack has a step
  `module: <name>` that runs that pack inline.
- The "tree" is therefore **implicit and hard-coded** — `foundation` always pulls
  `memory` + `gbrain`. No catalog, no chooser, no declared prerequisites.

## The key insight: a loadout is just a pack

An umbrella pack is nothing but a list of `module:` picks. So a player's chosen
loadout ("memory + gbrain + obsidian, not trading") is just an auto-generated
umbrella pack with three module steps — which the engine **already runs**.

⇒ The skill tree is a **presentation + authoring layer** over the existing
composition primitive, NOT new engine machinery. That keeps it cheap.

## What's missing (three additive pieces)

1. **A catalog / manifest.** One file listing every available pack with metadata:
   `name`, `category` (branch), `gives_you` (one line), `cost` (time/tokens),
   `requires` (prereqs). Renders the menu / tree.
2. **Declared prerequisites.** Packs declare `requires: [memory]`. Today `module:`
   is hard inclusion; a tree needs soft prereqs so a branch only unlocks once its
   parent passes `verify`.
3. **A chooser.** Pick modules → it resolves the prereq graph, topologically orders
   the picks + their prerequisites, and rolls a custom umbrella pack. Then the
   normal `teach` / `verify` / `remediate` runs it.

## Sketch

```
                    ┌──────────────────────────┐
                    │   FOUNDATION  (the trunk) │   always — the base every branch needs
                    │   identity · memory ·     │
                    │   constitution · guardrails│
                    └───────────┬──────────────┘
                       memory unlocks ▼ the knowledge branch
        ┌───────────────────────┼────────────────────────┐
        ▼                       ▼                        ▼
   KNOWLEDGE                 TRADING                    DEVEX          branches you choose
   gbrain ✓                 (edge packs) ○              (ship/qa) ○
   obsidian ○
   x-post-ingest ○
   youtube-transcriber ○
                 ✓ built   ○ planned   —   prereqs gate what unlocks
```

The KNOWLEDGE branch grows an **ingest sub-branch** — `x-post-ingest` and
`youtube-transcriber` turn sources into compounding memory via a weekly→monthly
rollup rhythm. Specced in [planned-knowledge-ingest.md](planned-knowledge-ingest.md);
both require `memory` and reuse the `autolearn` drain, so they sit downstream of the
trunk.

## Design decisions to resolve when we develop it

- **Prereq vs. pure choice.** Does the tree *enforce* order (memory before the
  knowledge branch), or is it a flat catalog with soft hints? RPG trees enforce.
- **How "unlock" is defined.** Almost certainly: a prereq is unlocked once its
  pack's `verify` passes. Ties the tree to the checkpoint model we already have —
  you unlock a branch by *actually having* its prerequisite working, not by a flag.
- **Where a loadout lives.** A generated umbrella pack on disk? A saved "profile"?
  (A profile is just a named umbrella pack.)
- **Chooser UX.** CLI menu first (list catalog → pick → resolve → run). A visual
  tree is a later nicety; the data model is the real work.
- **Catalog trust.** Once packs come from many authors, the catalog is also the
  place provenance/signing surfaces (ties into the marketplace security gate).

## Two levels of choice (one already shipped)

There are really two choices in this system:

1. **Which module** — the skill tree above (pick gbrain, pick obsidian, skip
   trading). Not built yet.
2. **How a module is set up** — a choice *inside* a pack. **This ships now** as
   pack **variants**: a step tagged `when: <variant>` runs only for the chosen
   variant, picked with `--variant`. Already live:
   - `gbrain-windows` → `local` (PGLite file) vs `supabase` (hosted).
   - `obsidian-wiki` → `local` (on disk) vs `hosted` (published free).

Variants are the finer grain; the tree is the coarser one. When the chooser gets
built, it selects modules (level 1) *and* their variants (level 2) — and since a
module step can already pin a variant (`module: gbrain-windows` + `variant: supabase`),
a rolled loadout captures both. The engine work for level 2 is done; the tree is
the remaining piece.

## Why it's worth it

It turns "set up your Claude" from a monolithic install into a **progression** — a
newcomer starts at the trunk, gets each branch working and *verified* before the
next unlocks, and ends up with exactly the loadout their work needs. The
checkpoint model already makes each node prove itself; the tree just makes the
path chooseable.
