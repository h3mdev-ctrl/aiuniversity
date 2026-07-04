# memory

Sets up a **file-based memory system that compounds** — a `memory/` folder with
an always-loaded `MEMORY.md` routing index, per-topic notes with frontmatter, and
a doctor that keeps the whole thing reachable. Tool-agnostic (works with or without
gbrain). This is the layer that stops Claude starting from zero every session.

See [pack-structure.md](../../docs/pack-structure.md) for the section conventions
this README follows.

## Contract

- **Finds an existing memory before creating one.** Searches `$CLAUDE_MEMORY_HOME`,
  then `<home>/memory`, then any project-scoped `<home>/projects/*/memory`.
- **Refuses to guess** if it finds more than one — exits non-zero with all candidates
  listed, requiring an explicit `CLAUDE_MEMORY_HOME` pin.
- **Doctor scores structural reachability** — every memory file must be linked from
  a routing tier (`MEMORY.md`, `INDEX_*.md`, or `CATALOG.md`); a "dark" file flips
  the verdict to `ISSUES`. Frontmatter and index-size are advisory only.
- **Wire step is idempotent** — points the recipient's `CLAUDE.md` at
  `memory/MEMORY.md` so the index is auto-loaded every session.
- **Recall probe is behavioural** — spawns a real fresh `claude -p` and asks for a
  seeded canary phrase; passes only if recall actually works, not just presence.

## Iron Laws

- **Fail loud on ambiguity.** If discovery finds more than one memory system,
  refuse to pick one. Silent picking is exactly how an audit ends up saying "it's
  fine" against the wrong project's memory (Jason's real bug, 2026-07-03).
- **Routing before recall.** A memory file that isn't reachable from any routing
  tier is invisible in practice — the doctor treats it as broken and fails.
- **The always-loaded index stays lean.** `MEMORY.md` is routing rows only.
  Domain content splits into `INDEX_<domain>.md` sub-indexes (Tier-2, on demand);
  the full alphabetical list lives in `CATALOG.md`. Never trim routing to save
  space — that turns memories dark.
- **Wiring is not optional.** `memory/` on disk without `CLAUDE.md` pointing at
  `MEMORY.md` is dead files. The `wired-to-constitution` step is a hard check.

## Anti-Patterns

- ❌ **Auto-picking when discovery returns >1.** Case-folded sort is not a fix;
  it's the bug.
- ❌ **Appending every autolearn'd resolver row to `MEMORY.md`.** Bloats the
  always-loaded index; new lessons file to `CATALOG.md` on-demand instead.
- ❌ **Adding memory files without a resolver row anywhere.** Creates dark files.
- ❌ **Editing `MEMORY.md` by hand for routine capture.** That's what the
  `autolearn` pack automates; hand edits are for structural changes only.
- ❌ **Treating frontmatter or size warnings as blockers.** They are advisory —
  a mature memory has older untagged files and must stay `HEALTHY`. Only dark
  files fail the audit.

## Related packs

- [`autolearn`](../autolearn/) — files new lessons into the memory this pack sets
  up, via a deterministically-gated drain that appends to `CATALOG.md` (not
  `MEMORY.md`).
- [`gbrain-windows`](../gbrain-windows/) — complementary searchable-knowledge
  layer; goes hand-in-hand but neither depends on the other.
- [`foundation`](../foundation/) — the umbrella pack; `memory` is layer 1 (the
  prerequisite the rest of the tree depends on).
