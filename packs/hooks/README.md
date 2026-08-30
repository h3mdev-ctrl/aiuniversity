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

Two conditions keep it honest, both added after partitioning **246 measured fires
across 156 sessions** — a partition an aggregate hit-rate could never have shown:

- **Scratch and temp directories are excluded.** 93 of 246 (38%) targeted a throwaway
  dir, 86 of them the session scratchpad the system prompt *tells* Claude to use. "Grep
  the neighbours first" is meaningless advice about a throwaway script, and a guard that
  bounces you for following your own instructions trains you to dismiss it — which costs
  it authority on the 62% that matter.
- **Recon evidence silences it.** The remaining 153 weren't measuring the behaviour at
  all: the guard fired on the Write regardless of whether recon had happened, so its
  "hit rate" was really "how often does Claude create a new source file", which for an
  active builder should be *often*. It could never trend to zero, **and a metric that
  cannot improve cannot be managed.** It now reads the session transcript and stays
  silent if this session already Read/Grep/Glob'd inside the target directory. A fire
  now means something falsifiable: a new source file went into an established directory
  this session has never looked at.

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

**hook-liveness** — `hook_doctor.py`. Feeds every hook you have registered a
deliberately benign payload for its event and fails if it crashes or answers with
anything other than allow/block. This is the step people skip and the one that pays
off most: a hook that crashes and a hook with nothing to say are **identical** from
the outside, and `PreToolUse` treats an unexpected exit as a *non-blocking* error —
so a crashed guard permits while everything still looks normal.

**guard-correctness** — `guard_regression.py`. The other half. The doctor asks "is it
alive?"; this asks "does it still catch the thing it was built for, and still ignore
the near-miss?" A hook can pass liveness with a matcher that no longer matches
anything — which is exactly what a dark advisory list looks like from the outside.
Ships cases for every guard in this framework, delegates to a guard's own selftest
where a fixture is needed, and takes your own cases from
`$CLAUDE_HOME/guard_cases.json`.

**windows-composition-guard** *(Windows only)* — `windows_quirk_guard.py`. The
enforcement half of the [`windows-shell`](../windows-shell/) pack, which documents
these traps but cannot reach them: they are mistakes made **while composing a tool
call**, mid-turn, where a rule read at the start of the turn has no attachment point.
Blocks three compositions that are already broken before they run (a PowerShell
here-string pasted into bash, a Python heredoc that won't parse, `$_` pre-expanded by
bash before PowerShell sees it) and advises on four code patterns that bite later.

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
- **Never write a regression case for a hook whose job is a side effect.** A case for
  a notifier posts a real message; one for an auto-committer makes a real commit; one
  for a brain-writer leaves synthetic pages behind. Declare those in `_EXCLUDE` with the
  reason. On the machine this came from, 16 of 34 registered hooks are in that class —
  they are plumbing or effects, not judgements, and `hook_doctor` already proves they run.
- **A skipped case is not a passing case.** `guard_regression.py` reports a guard you
  haven't installed as SKIPPED and a hook you *have* registered with no cases as
  UNCOVERED. Read the verdict line, not the colour — an all-green run made entirely
  of skips checked nothing at all.
- **Write the script first, register it second.** If `settings.json` points at a hook
  file that doesn't exist yet, every matched tool call fails until you create it. The
  installers here always write the hook file before merging the registration.

## Anti-Patterns

- ❌ **Installing because it sounds useful without understanding what it blocks.** Read
  the description, run `--test-blocking` dry, then decide.
- ❌ **Shipping the hook file without registering it.** "Installed" ≠ "active". The
  two-step check (file present, registered in settings) exists because both can silently
  fail independently.
- ❌ **Deleting a regression case to get back to green.** A FAIL means a footgun you
  have already hit is no longer caught. Decide whether the rule or the case is wrong
  and fix *that* — removing the case is how a guard goes dark with nobody noticing.
- ❌ **Running only the doctor.** Liveness and correctness fail independently and need
  different repairs. HEALTHY from `hook_doctor.py` on a guard whose matcher has gone
  dark is a true statement about the wrong question.
- ❌ **Leaving opt-in hooks in place after they've done their job.** If the soft
  principle is now reliably followed, uninstall the hard hook — remove the file and
  the settings.json entry — so it doesn't create noise.

## Related packs

- [`guardrails`](../guardrails/) — the mandatory baseline; run this first.
- [`foundation`](../foundation/) — runs guardrails as layer 3 and seeds the soft
  versions of these principles in the constitution.
