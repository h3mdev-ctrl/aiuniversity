# Pack structure convention

Every aiuniversity pack ships an executable `pack.yaml` (the checkpointed runbook)
plus a `files/` directory (installers, tests, doctors). This document defines the
one extra file every pack should also ship — a **`README.md`** — and the four
sections that go in it, so a reader can understand what a pack promises without
running it.

The structure is adopted from **gbrain's** `SKILL.md` convention
([github.com/garrytan/gbrain](https://github.com/garrytan/gbrain), MIT) — their
skills use a similar Contract / Iron Law / Anti-Patterns / Related pattern that
teaches by naming both what a skill guarantees and the specific ways it goes wrong.
aiuniversity's packs are **setup runbooks** rather than agent-invoked skills, so
the shape is adapted (no `triggers:` frontmatter), but the four teaching sections
transfer cleanly.

## The four sections

Each `packs/<name>/README.md` opens with a one-paragraph description, then:

### `## Contract`

The guarantees the pack makes — the durable, testable promises. If the pack's
tests all pass, these are the properties that hold. Short bullets, no adjectives.

### `## Iron Laws`

The non-negotiables — the rules the pack refuses to break, even at a cost.
Usually 2–5 items. If a user forces one open ("just skip the gate"), they've
turned the pack into something else. Grounded in specific past failures where
possible ("silently picking between memories yields 'audit fine' verdicts against
the wrong project").

### `## Anti-Patterns`

Explicit list of what NOT to do, each with a leading `❌`. These are the failure
modes the pack was built to prevent — naming them here teaches the reader more
than a happy-path description ever will. Keep to 3–6 items.

### `## Related packs`

Cross-references to other aiuniversity packs a reader will need next (or that
this one depends on). One line each.

## Why not adopt gbrain's frontmatter fields too?

gbrain's SKILL.md frontmatter carries `triggers:`, `mutating:`, `writes_pages:`,
`writes_to:`, `tools:` — very useful for **agent-invoked** skills where the model
must decide "does this skill apply here?" and "what's it about to do to my
filesystem?". aiuniversity packs are **user-invoked** setup runbooks — the user
already picked them. `mutating:` and `writes_to:` would still be nice metadata,
but they belong in `pack.yaml` if we add them, not the README. Kept out of scope
until the runner has a reason to consume them.

## Quality checking

We don't ship our own doctor rubric. If you're building a **gbrain-format
skillpack** and need a quality check, use the official one:

```
gbrain skillpack doctor <your-pack-dir>
```

aiuniversity packs pass their own structural test suite (`python -m pytest`); the
per-pack README + Contract section is the human-legible complement to that.

## Reference implementations

- [`packs/memory/README.md`](../packs/memory/README.md) — canonical for setup packs.
- [`packs/autolearn/README.md`](../packs/autolearn/README.md) — canonical for
  packs that ship an unattended pipeline (highest Iron-Law density).
