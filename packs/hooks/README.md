# hooks

**Opt-in behavioural guards** — the levers you pull when a soft principle in your
CLAUDE.md constitution keeps getting ignored and you want a hard backstop that fires
at the moment of the tool call.

The foundation's `guardrails` pack installs the mandatory baseline: `credential_guard`
blocks Claude from reading `.env` / private keys. This pack surfaces everything else
that ships alongside it — proven, opt-in, each one explained so you can decide whether
it fits your workflow before you install it.

### What's here

**recon-before-build** — a `PreToolUse(Write)` hook that fires when Claude's first
Write in a session would create a **new source file** in a repo that already has code.
It exits non-zero with a nudge to read the neighbouring files before building a
parallel version of them. Fires once per session per repo, then gets out of the way.

> The motivating case: a Claude re-derived a whole subset-sum matcher that already
> lived ~40 lines away in the same folder, over hours, because it never read the file
> — then wrote a memory titled "read existing code first" and *still* had to be asked
> three times before it opened the file. A memory hopes to be recalled; a hook fires
> on the action.

The **soft version** — the constitution principle "Recon before build" — ships in
foundation `layer-2-constitution`. Install this hard hook only if that principle keeps
getting skipped and you want the nudge to fire at the moment of the Write.

**session-end** — a `Stop` hook that fires when Claude's response contains phrases
like "good night", "get some rest", or "want to wrap up?" — and exits non-zero to flag
it. The builder decides when they're done; Claude pre-empting that is friction.

The **soft version** — "Don't tell the user when to stop" — also ships in the
foundation constitution. Same trade-off applies: opt-in if the soft principle keeps
getting ignored.

### Why opt-in

Both are shipped in `packs/guardrails/files/` but not default steps, for the same
reason: a `Stop` hook can only nudge by exiting non-zero, which the desktop surfaces
as an "Error" badge. That's the right signal for a security block; it's the wrong
first impression for a QoL nudge. And both are common-language guards — they react
whenever Claude *mentions* the phrases, not just when it acts on them. On by default,
error-badging would be constant.

The hard hooks earn their place when the soft principles have already been in your
constitution for a while and still get skipped. That's the signal to install.

## Contract

- **Installs each hook script** at `~/.claude/hooks/<name>.py` (idempotent).
- **Registers each hook in `settings.json`** under the right event + matcher, merging
  safely with any hooks already there.
- **Blocking is behavioural AND deterministic** — each `--test-blocking` run pipes a
  known-forbidden action through the installed hook and confirms it exits non-zero.
- **Not walls** — each hook also confirms that a harmless action still passes, so the
  gate is proven selective.

## Iron Laws

- **Prove it fires; don't assume presence.** A hook file on disk that isn't
  registered, or is registered but doesn't actually block, is false security. Run
  `--test-blocking` after every install.
- **Fail open on unexpected errors.** A guard that exits non-zero on bad input silently
  breaks every matched tool call. All hooks here wrap logic in `try/except Exception:
  return 0`.
- **Write the script first, register it second.** If `settings.json` points at a hook
  file that doesn't exist yet, every matched tool call fails until you create it. The
  installers here always write the hook file before merging the registration.

## Anti-Patterns

- ❌ **Installing because it sounds useful without understanding what it blocks.** Read
  the description, run `--test-blocking` dry, then decide.
- ❌ **Shipping the hook file without registering it.** "Installed" ≠ "active". The
  two-step check (file present, registered in settings) exists because both can silently
  fail independently.
- ❌ **Leaving opt-in hooks in place after they've done their job.** If the soft
  principle is now reliably followed, uninstall the hard hook — remove the file and
  the settings.json entry — so it doesn't create noise.

## Related packs

- [`guardrails`](../guardrails/) — the mandatory baseline; run this first.
- [`foundation`](../foundation/) — runs guardrails as layer 3 and seeds the soft
  versions of these principles in the constitution.
