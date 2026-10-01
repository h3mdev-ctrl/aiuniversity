# agent-honesty

Six guardrails against the failure mode a weak or hurried model falls into most:
**reporting confidently instead of truthfully.** It installs the rules as an
always-loaded doc wired into your constitution, and gives the one guardrail with a
mechanical surface -- `no-phantom-done` -- a deterministic, model-free linter that
proves an unevidenced completion claim is catchable.

The six guardrails:

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
- **verify-mechanism-before-acting** -- before a live system takes a new or bigger
  real-world action, check that exact path has actually run successfully under
  comparable conditions; a plausible, sourced mechanism (docs, a vendor forum) is
  not the same as a proven one.
- **verify-effect-not-acknowledgment** -- a write returning success (200 OK, no
  exception) is not proof the intended effect happened; confirm with an
  independent read, and when it doesn't match, diff the full payload shape, not
  just the field you meant to change.

## Contract

- Installs `~/.claude/agent_honesty.md` carrying all six guardrails, each with its
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
- ❌ Letting `research-before-asserting` / `judge-to-spec` / `no-vague-time-claims` /
  `verify-mechanism-before-acting` / `verify-effect-not-acknowledgment` masquerade
  as code-enforced. They have no clean mechanical surface and stay soft rules by
  design; pretending otherwise is exactly the kind of false confidence the pack
  warns against.

## Enforcement (opt-in)

The always-loaded rules are the default. If a guardrail keeps slipping and you
want a hard backstop:

- **no-phantom-done for CODE** -- the code-quality pack's `stop_verify.py` already
  runs your test suite before Claude may Stop:
  `python -m runner.cli remediate packs/code-quality`
- **no-phantom-done for CLAIMS** -- `phantom_claim_lint.py` lints *text* (stdin or
  `--text`), exit 1 on an unevidenced claim. A Stop hook receives *JSON* with a
  `transcript_path`, not text, so wiring it as a hook needs a small adapter that
  reads the transcript and pipes the last assistant message into the linter. That
  adapter is not shipped here; don't register the linter on Stop directly -- it
  would lint the JSON envelope, not the reply.
- research-before-asserting, judge-to-spec, no-vague-time-claims,
  verify-mechanism-before-acting and verify-effect-not-acknowledgment have no
  clean mechanical surface -- they stay soft rules by design.

(This used to be a pack step whose check was `python -c "exit(0)"`. A check that
cannot fail reads as verified while testing nothing, so the guidance lives here.)

## Related packs

- **code-quality** -- `stop_verify.py` is the hard, opt-in Stop-hook backstop for the
  no-phantom-done "tests pass" case (runs the suite before Claude may Stop).
- **autolearn** -- `phantom_workflow.md` carries the bidirectional-honesty principle
  (codify wins as aggressively as failures); a natural companion to these rules.
- **foundation** -- seeds the constitution this pack wires its pointer into.
- **guardrails** -- the model for a soft-default-in-constitution + opt-in-hard-hook
  guardrail.
