# guardrails

Layer 3 of the foundation — **automatic backstops that catch mistakes by CODE, not
by hoping**. The **default** guard is proven by a behavioural check (a real gate, not
a present file):
- **credential guard** (default) — a PreToolUse hook that blocks Claude reading
  credential files (`.env`, private keys, `.aws/credentials`) via `Read` OR `Bash`
  (`cat`/`less`/`head`/`tail`/`type`/`Get-Content`). Fires rarely (only on a real
  secret read), so it doesn't get in your way.

### The session-end guard is opt-in

Also shipped, but **NOT installed by default**: a Stop hook that bounces Claude when
it signs off with "go rest / call it a day / you've done enough" (a builder decides
when they're done). Two reasons it's opt-in, not default:

- **A Stop hook can only nudge by exiting non-zero**, which the desktop surfaces as an
  **"Error" badge**. That's tolerable for a rare security block; it's the wrong first
  impression for a QoL nudge.
- **It's a common-language guard** — it reacts whenever Claude *mentions* the phrases,
  not just when it signs off. On by default it would error-badge constantly, including
  on the install summary itself. Installing a *self-improvement* pack should not make
  your session throw errors.

So the **default is the soft version**: the constitution principle "don't tell the
user when to stop" (foundation `layer-2-constitution`) — always-loaded, no error
state. Install the hard hook only if that keeps getting ignored and you want
enforcement: `python packs/guardrails/files/setup_session_guard.py`. It's built
smart — it SKIPS quoted context (code spans, fenced blocks, blockquotes, and
double-quoted prose) so it won't fire when Claude is *quoting* the rule rather than
signing off — but even a perfect quote-skip can't make a Stop hook stop error-badging
when it legitimately fires, which is why it's your choice, not the default.

### The recon-before-build guard is opt-in

Also shipped, **NOT installed by default**: a PreToolUse(`Write`) hook that bounces the
**first Write of a NEW source file into a repo that already has source files** — the
exact moment Claude is most likely to build a *parallel* module instead of reading and
extending the one that's already there. It fires **once per session per repo**, then
gets out of the way (a nudge, not a wall): read the neighbours, say what exists and the
gap, Write again, done.

Why a hook and not just the principle: *"stand on the shoulders of giants — don't
reinvent"* is always loaded and **still gets skipped**, because when a task says "build
X" and there's enough context to start typing, acting feels like progress and reading
feels like delay. A memory *hopes to be recalled*; a PreToolUse hook fires **on the
action** — same reason the session-end Stop hook beats the stop-phrase memory. The
motivating case: a Claude re-derived a whole subset-sum matcher and its edge cases that
already lived ~40 lines away in the same folder, over hours, because it never read the
file — then wrote a memory titled "read existing code first" and *still* had to be asked
three times before it opened the file. Passive artifacts lose to an active impulse.

Opt-in for the same reason as the session guard: fired on every new file it would be
noisy, and the **soft default already ships** — the constitution principle "Recon before
build" (foundation `layer-2-constitution`), always-loaded, no error state. It's tuned to
stay quiet on genuine new work (ignores existing-file overwrites, doc/config/data files,
and fresh/sparse directories — only an *established* codebase triggers it). Install the
hard nudge only if the soft principle keeps getting ignored:
`python packs/guardrails/files/setup_recon_build_guard.py`.

See [pack-structure.md](../../docs/pack-structure.md) for the section conventions.

## Contract

- **Installs the hook script** at `~/.claude/hooks/credential_guard.py` (idempotent).
- **Registers it in `settings.json`** as a PreToolUse guard on `Bash`+`Read`,
  merging safely with any hooks you already have.
- **Blocking is behavioural AND deterministic** — `--test-blocking` pipes forbidden
  probes (Read `.env`, `cat .env`, reading an SSH private key) through the INSTALLED
  hook and confirms each exits non-zero with a `BLOCKED` message.
- **Not a wall** — a harmless `ls` still passes, so the gate is proven selective,
  not blanket-deny.

## Iron Laws

- **Prove it fires; don't assume presence.** A hook file on disk that isn't
  registered, or is registered but doesn't actually block, is false security. The
  behavioural check runs a real forbidden action through the real hook.
- **Fail closed on credentials.** The guard blocks reads that would leak a secret
  into the transcript — Read and shell-cat alike. A partial block (Read only, shell
  open) is a hole.
- **Selective, not blanket.** A guard that blocks everything is unusable and gets
  turned off. Harmless actions must still pass — that's part of the contract.

## Anti-Patterns

- ❌ **Shipping the hook file without registering it.** Two separate checks
  (`--check-hook-file`, `--check-registered`) exist precisely because "installed"
  ≠ "active".
- ❌ **Testing the guard by reading its source instead of running a probe.** Only a
  real forbidden action through the installed hook proves it blocks.
- ❌ **Overwriting existing hooks in `settings.json`.** The installer merges; a
  naive write would clobber other guards.
- ❌ **Assuming a green check today survives a settings.json edit tomorrow.** If a
  later change drops the registration, the guard silently stops firing.

## Related packs

- [`foundation`](../foundation/) — runs guardrails as layer 3, after identity +
  memory + constitution.
- [`memory`](../memory/) / [`identity`](../identity/) — earlier foundation layers;
  guardrails protects the environment they write into.
