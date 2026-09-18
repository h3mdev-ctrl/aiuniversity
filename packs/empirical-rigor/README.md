# empirical-rigor

Three guardrails against a different failure than `agent-honesty`'s reporting
rules: not a false claim, but a **design built on an assumption that was never
checked against reality** -- the real shape of historical data, the real runtime
environment, the real deploy history. It installs the rules as an always-loaded
doc wired into your constitution, the same shape `agent-honesty` uses for its
non-mechanical guardrails.

The three guardrails:

- **distribution-before-statistic** -- look at the real shape of historical data
  before picking a mean/average to size a threshold or buffer. A spiky or
  bimodal distribution (mostly zero, occasional large spikes) needs a max or a
  high percentile instead -- a mean silently understates the recurring risk.
- **environment-parity-for-adhoc-runs** -- a diagnostic or ad-hoc invocation of
  production code must mirror its real mounts/env vars/config exactly, not a
  trimmed-down version "because this script only needs X." A shortened
  environment can silently produce false inputs that look like real ones.
- **continuity-is-not-uptime** -- a gap-free dataset is not proof the process
  that produced it has been running correctly the whole time. Check deploy
  history before citing "N days, zero gaps" as evidence of reliability -- a
  backfill can manufacture that same clean look in one run.

## Contract

- Installs `~/.claude/empirical_rigor.md` carrying all three guardrails, each
  with its trigger, rule, **Why**, and **How to apply**.
- Wires a pointer block into `~/.claude/CLAUDE.md` (marker-wrapped, idempotent),
  coexisting with `agent-honesty`'s own pointer block and your existing
  constitution.
- No linter: none of the three has a clean mechanical surface (each is a
  judgment call about a design decision, not a lintable claim in text) -- they
  stay soft rules, same as `agent-honesty`'s research-before-asserting and
  judge-to-spec.
- Install and wiring are idempotent; re-running never duplicates a block.

## Iron Laws

- **A statistic is a claim about the data's shape, not just its center.** Picking
  a mean without first looking at whether the data is smooth or spiky is itself
  the bug, independent of whether the resulting number happens to work out.
- **An ad-hoc script inherits none of production's safety by default.** If it
  shares a code path with something that writes to a real system, a trimmed
  environment doesn't just risk a wrong number -- it risks a real action taken on
  a false input.
- **Continuity is a fact about the data file, not about the process.** Never
  infer "the job has run correctly for N days" from "the file has N days with no
  gaps" without checking when the job doing the writing was actually deployed.
- **Soft by default, same as agent-honesty's non-mechanical guardrails.** No Stop
  hook, no error state -- always-loaded context is the lever.

## Anti-Patterns

- ❌ Defending a mean-based figure because "it's the standard way to size a
  buffer" without ever looking at whether the underlying data is actually smooth.
- ❌ Trimming an ad-hoc script's environment down to "just what this test needs"
  when it shares a code path with something that can write to a real system.
- ❌ Citing a long, gap-free CSV or log as proof of reliable operation without
  checking the deploy/execution history behind it -- a backfill looks identical
  to genuine day-by-day success on the page.
- ❌ Building a mechanical linter for any of these three to look more rigorous
  than the pack actually is -- none has a clean evidence token to check for, and
  pretending otherwise is the same false confidence `agent-honesty` warns against.

## Related packs

- **agent-honesty** -- the sibling pack for the model's own claims (completion,
  facts, spec-judgment, time). This pack guards what the model *builds things on
  top of* instead of what it *says*; neither substitutes for the other.
- **foundation** -- seeds the constitution this pack wires its pointer into.
- **guardrails** -- the model for a soft-default-in-constitution guardrail.
