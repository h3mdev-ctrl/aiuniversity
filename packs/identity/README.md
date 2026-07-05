# identity

Layer 0 of the foundation — an **interview pack**. Asks a short set of questions
once, then writes the answers into three context files (`me` / `work` / current
priorities), a `user_profile` memory (with a canary), and a "who you're speaking
to" block in `CLAUDE.md`. After it, every session starts with Claude actually
knowing who you are instead of improvising against a stranger.

See [pack-structure.md](../../docs/pack-structure.md) for the section conventions.

## Contract

- **Two ways to answer** — `--interactive` (you answer prompts on stdin) or
  `--write` (Claude conducts the interview in teach mode and pipes JSON answers).
- **Writes three context files** to your Claude home: identity, work, current
  priorities.
- **Files a `user_profile` memory** so "who am I speaking to" routes back to your
  identity from any moment in a session — depends on the memory pack existing.
- **Wire step is idempotent** — points `CLAUDE.md` at the context files so they're
  read every session.
- **Identity probe is behavioural** — a fresh `claude -p` must surface the seeded
  canary (`PURPLE-KANGAROO-9271`); passes only if identity is genuinely loaded.

## Iron Laws

- **Identity is worthless unless it's loaded.** Context files on disk that
  `CLAUDE.md` doesn't point at are dead files — the `wired-to-constitution` step
  is a hard check, and the probe proves the wiring works, not just that files exist.
- **Sequence after memory.** Identity files a `user_profile` INTO the memory
  system, so the memory pack must run first. The foundation deliberately orders
  memory (layer 1) before identity (layer 0) for this reason.
- **Behavioural proof over presence.** "The file exists" is not "Claude knows who
  you are." The canary probe is the difference.

## Anti-Patterns

- ❌ **Running identity before memory exists.** `profile-memory` will fail with
  "no memory system found" — set up the memory pack first.
- ❌ **Hand-writing context files and skipping the wire step.** Unwired context is
  functionally dark; a fresh session never reads it.
- ❌ **Treating the interview as one-and-done forever.** Current priorities drift;
  re-run to refresh them (me/work are durable, priorities are not).
- ❌ **Assuming the probe passing once means it's permanently live.** If you later
  restructure `CLAUDE.md` and drop the pointer, identity goes dark silently.

## Related packs

- [`memory`](../memory/) — prerequisite; identity files `user_profile` into it.
- [`foundation`](../foundation/) — runs identity as layer 0, sequenced after the
  memory layer.
