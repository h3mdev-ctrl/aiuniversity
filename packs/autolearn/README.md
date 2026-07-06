# autolearn

A **phantom-style wrap-up companion to the memory pack**: a git post-commit hook
captures each commit to a queue; a reflection pass (interactive `--write-learning`
or unattended `--drain`) extracts durable lessons and files them into memory, so
the same mistake isn't repeated next session. The unattended `--drain` models
Andrew's mature `global-evolution` pipeline — plan of actions
(`create` / `update` / `supersede` / `skip`) over the whole queue, deterministic
gate, one revertible git commit.

See [pack-structure.md](../../docs/pack-structure.md) for the section conventions.

## Contract

- **Every commit is captured** via a git post-commit hook (append-only JSONL queue
  at `<CLAUDE_HOME>/autolearn_queue.jsonl`, no dedup needed).
- **`--write-learning` files ONE learning** through the deterministic gate:
  slug shape, size, credential scan, fence balance, duplicate check.
- **`--drain` files a PLAN of actions** for the whole queue: `create` (net-new),
  `update` (refine an existing memory in place — with a clobber-guard that refuses
  updates that shrink AND drop most substantive lines), `supersede` (stamp a stale
  memory with a banner + `status: superseded` frontmatter, never delete), `skip`.
- **`--tools=""`** on the headless reflection — the model can only emit text; the
  filesystem is Python's, applied only after the plan passes the gate.
- **One git commit per drain** in the memory folder; a bad autonomous write is
  `git revert HEAD`.
- **Index growth lands in `CATALOG.md`** (Tier-2, on-demand), never `MEMORY.md`
  (always-loaded); a reachability safety net auto-appends a `CATALOG` line for any
  created slug not covered by the model's `catalog_additions`.

## Iron Laws

- **Every write passes the deterministic gate.** No model output writes to memory
  without `validate_learning` (interactive) or `validate_plan` (drain) first. A
  HARD finding (credential / malformed frontmatter / oversize / dup / unbalanced
  fences) blocks the write; on the drain, the queue is KEPT — the commits are
  never lost to a bad plan.
- **The model can only emit text.** `claude -p --tools ""` — the reflection model
  cannot touch the filesystem. Python applies the validated plan.
- **`update` never silently clobbers.** If the proposed `new_full_content` is both
  much shorter AND drops most substantive lines of the existing file, the update
  is refused; the original is kept. A genuine extension passes.
- **`supersede` stamps in place; it does NOT delete.** Provenance is preserved
  behind a `<!-- superseded-banner -->` and `status: superseded` frontmatter.
- **Don't run two drains against the same memory -- pick one (a migration note,
  not a "skip").** If you already run a memory-drain, adopting this one means
  retiring the other, OR keeping yours -- your call. Running both writes
  near-duplicates into the same folder. This is a choice to put to the user (what
  does this add over what you run?), never a reason to skip the pack on their
  behalf. Overlap with an existing habit is usually not redundancy: a manual
  "write a memory when I find a fix" discipline is real, but this adds capture on
  every commit + a deterministic gate + rollback, so it fires when you forget and
  refuses to file a malformed or duplicate lesson.

## Anti-Patterns

- ❌ **Draining before the memory folder is a git repo.** Rollback becomes a
  manual cleanup rather than `git revert HEAD`. Run `git init` in the memory
  folder as a prerequisite.
- ❌ **Appending resolver rows to `MEMORY.md`** with every learning. That's the
  always-loaded index; bloats every session. Use `catalog_additions` in the plan.
- ❌ **Using a top-tier model** for the reflection. A one-shot structured
  reflection is a Haiku-class job; the plan quality is set by the prompt + gate,
  not the model tier. Default `AUTOLEARN_DRAIN_MODEL=claude-haiku-4-5`.
- ❌ **Trusting the `--drain` before the gate is in it.** Earlier versions of
  the drain bypassed `validate_plan`; that's fixed, but the same-shape mistake
  would recur in any future variant that skips the gate.
- ❌ **Filing "lesson learned: made a commit" trivialities.** The reflection
  prompt tells the model to prefer few high-signal lessons over many trivial
  ones; a durable lesson beats no lesson beats a trivial lesson.

## Related packs

- [`memory`](../memory/) — the memory system this pack files INTO; prerequisite
  (`memory-present` is the first check).
- [`foundation`](../foundation/) — threads `autolearn` as `layer-5-durability`,
  the self-improvement companion.
- [`gbrain-windows`](../gbrain-windows/) — a separate searchable-knowledge layer;
  independent of autolearn, but both compose on top of the memory pack.
