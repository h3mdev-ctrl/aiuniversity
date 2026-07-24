# agent-honesty

Four guardrails against the failure mode a weak or hurried model falls into most:
**reporting confidently instead of truthfully.** It installs the rules as an
always-loaded doc wired into your constitution, and gives the one guardrail with a
mechanical surface -- `no-phantom-done` -- a deterministic, model-free linter that
proves an unevidenced completion claim is catchable.

The four guardrails:

- **no-phantom-done** -- never claim a side-effect (done / committed / pushed /
  logged / saved / deployed) or a verification result ("all tests pass") unless the
  tool call ran *this turn* and you show the receipt.
- **research-before-asserting** -- check the source before stating a load-bearing
  fact or constraint; don't complete a plausible pattern from memory and assert it.
- **judge-to-spec** -- grade an output against the actual spec (ticket, plan step,
  acceptance criteria), not a remembered or drifted copy of it.
- **no-vague-time-claims** -- check the clock before naming a time of day or date;
  don't infer "tonight"/"this morning" from message order or how a long
  conversation feels.

## Contract

- Installs `~/.claude/agent_honesty.md` carrying all three guardrails, each with its
  trigger, rule, **Why**, and **How to apply**.
- Wires a pointer block into `~/.claude/CLAUDE.md` (marker-wrapped, idempotent) so
  the guardrails load every session and coexist with your existing constitution.
- Ships `phantom_claim_lint.py` -- a model-free linter that flags unevidenced
  completion claims and clears evidenced / future-tense / neutral text.
- The behavioural check is deterministic: known phantom claims flag, evidenced ones
  don't -- no live model needed, same as every other aiuniversity check.
- Install and wiring are idempotent; re-running never duplicates a block.

## Iron Laws

- **A completion claim without a receipt is a bug, not a style choice.** The linter
  treats "Done -- pushed" with no commit SHA / exit code / test tally as a finding.
  This is the exact failure the pack exists to catch (claiming "logged" when the
  call never ran, and the user builds on work that isn't there).
- **The rules are soft by default; enforcement is opt-in.** Behavioural guardrails
  ship as always-loaded context (no error state), never as an on-by-default Stop
  hook -- a self-improvement pack that error-badges on every turn is worse than the
  problem. Enforcement is a documented opt-in.
- **Only claims are linted, never plain descriptions of work.** "I added a helper"
  is not flagged; "I committed the helper" (an external side-effect) is. Widening
  the linter to all past-tense verbs would make it a wall and get it disabled.
- **Deterministic check over model self-judgment.** The verdict comes from
  `phantom_claim_lint.lint()`, pure code -- never from a model deciding whether its
  own claim was honest.

## Anti-Patterns

- ❌ Turning the linter on as a default Stop hook -- it would nudge constantly and
  train the user to ignore it. Ship the soft rule; make enforcement opt-in.
- ❌ Flagging every past-tense verb ("I wrote", "I updated") -- floods findings and
  buries the two categories that actually matter (external side-effects,
  verification results).
- ❌ Duplicating what already exists: the code-quality pack's `stop_verify.py` is the
  hard backstop for "tests pass" claims, and autolearn's `phantom_workflow.md`
  carries the bidirectional-honesty principle. This pack points at them, doesn't
  re-implement them.
- ❌ Claiming this pack *guarantees* honesty. It's a lint plus always-loaded rules --
  it forces the model to pair a claim with evidence; it cannot read the model's mind.
- ❌ Letting `research-before-asserting` / `judge-to-spec` / `no-vague-time-claims`
  masquerade as code-enforced. They have no clean mechanical surface and stay soft
  rules by design; pretending otherwise is exactly the kind of false confidence the
  pack warns against.

## Related packs

- **code-quality** -- `stop_verify.py` is the hard, opt-in Stop-hook backstop for the
  no-phantom-done "tests pass" case (runs the suite before Claude may Stop).
- **autolearn** -- `phantom_workflow.md` carries the bidirectional-honesty principle
  (codify wins as aggressively as failures); a natural companion to these rules.
- **foundation** -- seeds the constitution this pack wires its pointer into.
- **guardrails** -- the model for a soft-default-in-constitution + opt-in-hard-hook
  guardrail.
