# recall-discipline

Three guardrails against re-deriving knowledge that already exists somewhere
reachable — the failure mode where a session redoes research a prior session
already did, or scatters findings across many small notes instead of leaving
one place a later session can actually use. Installs as an always-loaded doc
wired into your constitution, same shape as agent-honesty.

The three guardrails:

- **recon-before-research** — before researching an external system's
  behaviour (a web search, a vendor doc lookup), check your own existing
  memory/notes for that system first. A prior session may already have tested
  it directly, which beats a fresh search.
- **consolidate-dont-accumulate** — when several memory files pile up on the
  same external/reference topic, that's the trigger to fold them into one
  canonical reference, not leave them scattered. Individually reachable is not
  the same as usable — answering one question shouldn't require re-reading
  five files.
- **project-framing-is-a-signal** — when the user names something "a
  project," treat that as a request for a durable home (a structured
  index/file) from the first session, not something to backfill once the
  scatter is already a problem.

## Contract

- Installs an always-loaded rules doc + a marker-wrapped CLAUDE.md pointer,
  idempotent, same shape as agent-honesty.
- All three guardrails are soft by design — no clean mechanical surface exists
  for "did you check memory first" or "should this be a project," so there is
  no linter here. Naming the trigger in context is the lever, not code
  enforcement.
- Install and wiring never duplicate a block on re-run.

## Iron Laws

- **A reachable memory is not the same as a consolidated one.** Being listed
  in an index and being usable in one read are different properties — this
  pack's second guardrail exists because the first kind of "healthy" memory
  system can still cause real rework.
- **Checking memory first is cheaper than being wrong externally.** A prior
  session's direct test of a system beats a forum post or a fresh guess —
  check before you search outward, not after.
- **"Project" is a scope word, not a mood word.** Once the user uses it, build
  the structure it implies immediately; treating it as casual framing is how a
  months-old folder ends up holding nothing but stray files.

## Anti-Patterns

- ❌ Researching an external system from scratch without first grepping
  existing memory for it — redoing work a prior session already did,
  sometimes worse (secondhand documentation replacing a good live-tested
  answer).
- ❌ Letting memory files accumulate on one topic indefinitely because each
  one is individually linked from the index and therefore technically not
  "dark."
- ❌ Treating "this is a project" as throwaway framing and letting the actual
  work scatter across repos/notes until someone notices there's no single
  home.
- ❌ Consolidating into a second copy that lives only in the memory system
  when the content is really code/system-adjacent — the canonical home for
  that kind of fact is a version-controlled doc in the relevant repo, with
  memory holding a pointer, not the other way around.

## Related packs

- **memory** — the system this pack's guardrails discipline; recall-discipline
  doesn't replace it, it adds the "don't let it silently fragment" rule the
  memory pack's own routing checks don't cover.
- **agent-honesty** — same soft-guardrail shape (always-loaded doc +
  constitution pointer, no default hard hook); research-before-asserting there
  is the sibling rule to recon-before-research here (check before you assert
  vs. check before you go looking).
- **foundation** — seeds the constitution this pack wires its pointer into.
