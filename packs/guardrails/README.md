# guardrails

Layer 3 of the foundation — **automatic backstops that catch mistakes by CODE, not
by hoping**. Ships two guards, each proven by a behavioural check (a real gate, not a
present file):
- **credential guard** — a PreToolUse hook that blocks Claude reading credential files
  (`.env`, private keys, `.aws/credentials`) via `Read` OR `Bash`
  (`cat`/`less`/`head`/`tail`/`type`/`Get-Content`).
- **session-end guard** — a Stop hook that bounces Claude when it signs off with "go
  rest / call it a day / you've done enough" (a builder decides when they're done).
  Smarter than a naive phrase guard: it SKIPS quoted context (a phrase in code or a
  blockquote is Claude *quoting the rule*, not signing off), so it won't false-fire
  when discussing the rule itself.

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
