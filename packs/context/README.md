# context

**Keep the model oriented across session starts and compaction events.**

### session_start_context

SessionStart hook — on every session open, resume, or compact-triggered restart,
injects into model context:
- Current date/time (UTC)
- Git branch + last 5 commits
- Modified files (git status --short)
- A reminder to read CLAUDE.md if it exists

Claude Code injects `SessionStart` hook stdout directly into the model context, so
everything printed here the model sees on the very first turn. No tokens wasted on
"what branch am I on?" at the start of every session.

### post_compact_reinject

PostCompact hook — after every transcript compaction, injects a reminder to re-read
CLAUDE.md and AGENTS.md before continuing. Finds both files in CWD and the parent
directory.

Closes **post-compaction rule amnesia**: the failure mode where the model forgets
constraints it was following because the compaction summary didn't preserve them
with sufficient detail. Common in long sessions — the model emerges from compaction
and writes code that violates an invariant it had been following for hours.

The 34-star `post_compact_reminder` project on GitHub was built specifically for this
failure mode.

## Contract

- Installs both scripts at `~/.claude/hooks/`
- Registers both in `~/.claude/settings.json`
- Verifies both run without error (these are inject-only hooks, not blocking hooks)

## Iron Laws

- Both hooks are advisory only — they inject context, never block. The model can still
  make mistakes; the hooks reduce the probability.
- `session_start_context` calls `git` — if git isn't available it silently skips the
  git section.

## Anti-Patterns

- ❌ Assuming these replace reading CLAUDE.md. The hooks remind the model to read the
  file; they don't embed its full content. The model still needs the actual file to
  be in context.
- ❌ Using these without `post_compact_reinject` on long sessions — compaction is
  the specific moment rule amnesia happens; `session_start_context` alone only fires
  at session open.

## Related packs

- [`safety`](../safety/) — prompt_injection_scanner (paired defence)
- [`guardrails`](../guardrails/) — credential guard, must run first
- [`foundation`](../foundation/) — seeds CLAUDE.md that these hooks reference
