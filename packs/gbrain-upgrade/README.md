# gbrain-upgrade

Safely upgrades gbrain to a newer release without a silently half-migrated
database, reverted config overrides, or a wedged job supervisor left behind.

**Skip this pack if:** you're already current, or you're deliberately pinned to a
version for compatibility reasons. This pack doesn't argue you should always
chase the newest release — it exists to make the jump safe once you've decided
to take it.

**Why this exists:** verified 2026-08-28, jumping 66+ commits and 16 schema
migrations in one upgrade (v0.45.18.0 → v0.47.3.0). The built-in `gbrain upgrade`
command's bundled schema migration **stopped 11 of 16 migrations through, with
no error message reaching the terminal** — `gbrain --version` already reported
the new CLI version, which looks exactly like success and says nothing about
whether the database actually finished. Separately, a job-queue worker left
running during the upgrade wrote data that corrupted its own queue's
post-upgrade bookkeeping, needing a second cleanup pass afterward.

See [pack-structure.md](../../docs/pack-structure.md) for section conventions.

## Contract

- **`update-available-confirmed`** — checks there's actually something to
  upgrade to before doing anything.
- **`processes-stopped-first`** — stops the jobs supervisor and its worker
  child (verified separately — stop doesn't reliably kill the worker) before
  any file gets touched.
- **`upgrade-run`** — runs the built-in self-update command.
- **`schema-migration-verified-not-assumed`** — the step that matters most:
  confirms the DATABASE schema actually reached the latest version, since the
  CLI version alone proved nothing in a real, verified incident.
- **`config-overrides-survived`** — confirms any explicit config overrides you
  set (custom reranker, custom embedding provider) survived the upgrade's
  bundled migrations, which can silently change defaults for UNSET keys.
- **`supervisor-restarted`** — the easy-to-forget cleanup step.
- **`doctor-clean-or-explained`** — runs a full health check post-upgrade so
  new WARN/FAIL rows get read, not missed.

## Iron Laws

- **`gbrain --version` reporting the new version is NOT proof the database
  migrated.** Verify the schema version explicitly with `gbrain apply-migrations
  --list` — a real upgrade this session reported the new CLI version while the
  schema sat 6 migrations behind, silently.
- **A stopped process is not necessarily a DEAD process.** The jobs supervisor's
  worker child survives a plain `supervisor stop` in the same way `gbrain
  serve` orphans survive — verify by process list, not by trusting the stop
  command's exit code.
- **Config overrides you explicitly set are supposed to win over a bundled
  migration's new default — but "supposed to" is not "verified."** Check your
  actual load-bearing overrides (reranker model, embedding provider) after
  every upgrade that touches provider defaults, every time.
- **A migration is FORWARD-ONLY.** Record the pre-upgrade commit
  (`git rev-parse HEAD` in the source clone) before starting — rolling the
  binary back does not roll the schema back.

## Anti-Patterns

- ❌ **Trusting `gbrain --version` alone as proof the upgrade fully completed.**
  It only proves the CLI binary changed — the database can be silently behind.
- ❌ **Skipping the "config overrides survived" check because the changelog
  didn't mention your setting.** A migration's stated scope ("new default for
  brains without an override") is easy to misjudge for YOUR specific config —
  verify empirically, don't take the prose's word for whether it applies to you.
- ❌ **Leaving a jobs worker running through the upgrade "because it'll probably
  be fine."** It corrupts its own queue's bookkeeping when it writes mid-
  migration — stop it first, every time, not just when you remember.
- ❌ **Reading `gbrain doctor`'s non-zero exit code as an upgrade failure.**
  Doctor exits non-zero on most real, healthy brains (it surfaces routine
  maintenance backlog, not just regressions) — read the actual printed output.

## Related packs

- [`gbrain-windows`](../gbrain-windows/) — day-2 recovery patterns (stale
  workers, orphaned processes, connection-pool exhaustion) this pack leans on
  throughout.
- [`gbrain-local-reranker`](../gbrain-local-reranker/) and
  [`gbrain-local-embeddings`](../gbrain-local-embeddings/) — if you have either
  wired up, the "config overrides survived" step is specifically checking that
  an upgrade didn't quietly revert them.
