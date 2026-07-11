# wrap-up

**The end-of-session close-out skill.** When the user says "wrap up", Claude runs
a mandatory sequence: ship what's shippable, deploy what's deployable, then
autolearn what was durable from the session.

The skill was extracted from Andrew's personal setup, where a 30-line procedure in
CLAUDE.md kept getting under-run because parts of it felt optional. Skillifying it
makes the sequence structural: the skill fires, executes every stage, and reports
a status table where each row must be ✅ before wrap-up is declared complete.

## What's inside

Three parts, in order:

1. **Part 1 — Ship gate.** If there's a diff, ship it. Uses gstack's `/ship` +
   `/land-and-deploy` as a sequential pair if gstack is installed; falls back to a
   documented hand-rolled `test → diff → commit → push → wait-for-deploy` sequence
   if not.
2. **Part 1.5 — Deploy gate.** If the session wrote publishable artefacts (site
   content, docs, explainers), commit + push (and trigger the platform's manual
   deploy if push alone doesn't trigger it).
3. **Part 2 — Autolearn.** The 6-stage phantom pipeline (Observe → Critique →
   Generate → Validate → Apply → Consolidate) with four principles applied
   throughout — see [autolearn pack](../autolearn/) for the full principle set.

## Why gstack-optional

Andrew ships his work via [Garry Tan's gstack](https://garryslist.org/) which
bundles `/ship` and `/land-and-deploy` as first-class skills. Not everyone runs
gstack. The wrap-up skill detects whether those skills are available and adapts
Part 1 accordingly:

- **With gstack**: invokes `/ship` and `/land-and-deploy` as the canonical pair.
- **Without gstack**: falls back to a documented hand-rolled shipping sequence
  that enforces the SAME checkpoints (tests pass, diff reviewed, deploy landed).

Neither path lets you skip verification. The tool changes; the discipline doesn't.

## Why the autolearn pack is a recommended companion

Part 2 (autolearn) is where wrap-up compounds session-over-session. The wrap-up
skill contains a summary of the 6 stages, but the full principle set — bidirectional
success/failure scan, tiered Tier-3-generous/Tier-1-stingy writes, deterministic
verification over model self-judgment, type-aware retirement — lives in the
autolearn pack's `phantom_workflow.md`.

You can install wrap-up standalone. The Part 2 scan still runs. But installing
autolearn alongside gives you:

- Automatic capture of every commit to a queue
- Structured drain (interactive `--write-learning` or unattended `--drain`)
- Deterministic gates (`memory_gate.py` + `memory_doctor.py`) enforced on every
  write
- The full principle set documented in one place instead of summarised in the
  skill

## Contract

- **Installs** `~/.claude/skills/wrap-up/SKILL.md` (idempotent — overwrites with
  new content, preserves the source of truth in this pack).
- **Detects** gstack availability at runtime (not at install time). The same
  installed SKILL.md works on machines that have gstack and machines that don't.
- **Reports** but does not enforce autolearn pack presence. Wrap-up works
  standalone; autolearn makes it durable.

## Iron Laws

- **The ship gate has TWO steps, not one.** Ship AND deploy. Skipping deploy
  leaves work in PR-limbo — the specific failure mode this skill exists to
  prevent. If the deploy is still ⏳, wrap-up is not done.
- **Part 2 is bidirectional.** Codify what went well as aggressively as what went
  wrong. A session with zero success entries is usually a listening failure, not
  a real absence of wins.
- **Deterministic gates always; model judge only for high-stakes.** Run
  `memory_doctor.py` on every memory write. Reserve the LLM judge panel for
  changes to hard invariants, security rules, or hooks.
- **Never time-prune principles.** Zero hits ≠ obsolete. See the type-aware
  retirement matrix in `phantom_workflow.md`.

## Anti-Patterns

- ❌ **Declaring wrap-up complete after `/ship` alone.** The PR is up; the deploy
  hasn't landed. That's PR-limbo, and it's exactly what the sequential pair
  prevents.
- ❌ **Running Part 2 only on session end, not on session extension.** If you wrap
  up and then keep working, Part 2 fires AGAIN over the new work at the true
  close. Autolearn is not one-shot.
- ❌ **Skipping the deploy gate because "push should be enough".** Some platforms
  (Vercel with a branch mismatch, private CI setups) need a manual trigger. Know
  your platform. If push alone doesn't deploy, the manual trigger is REQUIRED.
- ❌ **Filing every commit as a durable lesson.** The autolearn one-rule is: a
  durable lesson beats no lesson beats a trivial lesson. Trivial fixes should
  mark `should_write: false` — that IS a valid answer.

## Related packs

- [`autolearn`](../autolearn/) — recommended companion; provides the workflow
  guide the wrap-up skill's Part 2 references
- [`memory`](../memory/) — required by autolearn; the substrate every lesson
  files into
- [`guardrails`](../guardrails/) — protects credentials during any of the ship
  steps in Part 1 (fallback path especially — hand-rolled `git diff` review can
  otherwise surface secrets to the model)
- [`hooks`](../hooks/) — recon-before-build + session-end guards pair naturally
  with wrap-up's discipline
