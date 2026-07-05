# foundation

The flagship umbrella pack — **set up Claude properly the first time**. Threads the
real setup packs through as `module:` steps in a deliberate order, so a newcomer
with nothing ends up with a durable, useful Claude instead of one that works once.
Layer 4 declares a module slot and runs the real `gbrain-windows` pack through it,
which proves composition against a real module — the whole reason this pack exists.

See [pack-structure.md](../../docs/pack-structure.md) for the section conventions.

## Contract

- **Runs real modules end to end** — `layer-1-memory` → `memory` pack,
  `layer-0-identity` → `identity` pack, `layer-3-guardrails` → `guardrails` pack,
  `layer-4-capabilities` → `gbrain-windows` pack.
- **Inline checks for the file-only layers** — `layer-2-constitution` (a global
  `CLAUDE.md` exists) and `layer-5-durability` (a `~/.claude/projects` folder exists).
- **Ordering is load-bearing** — memory runs BEFORE identity because identity files
  a `user_profile` INTO the memory system the memory step created.
- **v1 is a working slice**, not all six layers at full depth — it proves the
  umbrella + a real composed module run end to end.

## Iron Laws

- **Memory before identity.** Identity writes a profile into memory; reverse the
  order and it has nowhere to file. The step ids read layer-1 then layer-0 on
  purpose — the sequence, not the number, is what matters.
- **Compose real modules, don't re-describe them.** A layer that should run a pack
  uses `module:` to run that exact pack, so there's one source of truth per
  capability. The foundation never forks a module's checks.
- **Each layer proves itself before the next unlocks.** The checkpoint model means
  a branch depends on its prerequisite actually working, not a flag being set.

## Anti-Patterns

- ❌ **Re-implementing a module's checks inline** instead of `module:`-including it.
  That's two sources of truth that drift.
- ❌ **Reordering the layers by their numbers.** The ids are historical; the
  dependency order (memory → identity) is the real constraint.
- ❌ **Treating v1's slice as the finished design.** Identity/memory/guardrails
  behavioural cold-recall probes are the next authoring pass, not a regression.
- ❌ **Forcing optional branches into the trunk.** KNOWLEDGE (obsidian-wiki) and
  future branches are chooseable, not part of the base foundation.

## Related packs

- [`memory`](../memory/), [`identity`](../identity/), [`guardrails`](../guardrails/),
  [`gbrain-windows`](../gbrain-windows/) — the modules this pack threads together.
- [`autolearn`](../autolearn/) — the durability companion (layer-5 direction).
- [`docs/skill-tree.md`](../../docs/skill-tree.md) — how the trunk + chooseable
  branches are meant to grow.
