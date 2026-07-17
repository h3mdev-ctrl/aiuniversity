# gbrain recovery — when a LIVE gbrain wedges (Windows)

The setup pack gets gbrain *live*. This manual is **day-2**: what to do when a
gbrain that *was* working stops doing its background maintenance — pages stay
stale, `gbrain doctor`'s score sinks, and nothing tells you why. It's grounded in
a real ~1-hour incident, distilled to the ~5-minute path. Every symptom below is
**symptom → check (the tool's own dashboard) → root cause → prescribed fix**.

> **The one rule that saves the hour: go to gbrain's own diagnostics FIRST.**
> `gbrain jobs stats` and `gbrain jobs supervisor status` print the root cause and
> often the exact fix. Reading them beats guessing flags — every flag guessed
> before reading them in the original incident was wasted.

---

## Symptom: background maintenance has stalled

Auto-linking / dream / extract / embed-backfill / sync-retry all quietly stop.
Live reads (`search`, `query`, `put`) still work — which is why nothing *feels*
broken — but the brain stops improving.

**Check:**
```bash
gbrain jobs stats
```
Look for: `⚠ WEDGED QUEUE 'default': N waiting, 0 active (live-lock), Xm since last completion`.
That line IS the diagnosis: the job queue is live-locked and nothing is draining.

```bash
gbrain jobs supervisor status
```
`Supervisor: not running` + a crash count = it died and **nothing restarted it**
(the nightly does NOT self-heal this).

> ⚠️ **PID-recycle trap.** The status/stats output may name a "worker pid". PIDs
> get recycled — verify a PID is *actually gbrain* before you kill anything. In the
> real incident the reported worker PID had recycled to `msedgewebview2.exe`;
> blindly killing it would have killed an unrelated Edge process. Confirm with
> `Get-CimInstance Win32_Process -Filter "ProcessId=<pid>"` first.

---

## Fix: restart the supervisor — DETACHED, FROM GIT-BASH

This is the fix for the wedge. Two things matter and both bite:

```bash
nohup gbrain jobs supervisor start > ~/.gbrain/supervisor-manual.log 2>&1 &
disown
```

1. **From git-bash, NOT PowerShell.** Under PowerShell, gbrain resolves its home to
   `/tmp/.gbrain` (wrong) and the spawned supervisor dies with
   *"Could not resolve the gbrain CLI path."* git-bash gives `HOME=/c/Users/<you>`,
   `gbrain` on PATH, and the real pidfile `~/.gbrain/supervisor-*.pid`.
2. **`supervisor start` runs AS the supervisor loop** (it stays in the
   foreground) — so background it (`& disown`). Wrapping it in `timeout` kills it.

Confirm: `gbrain jobs supervisor status` → `Supervisor: running`, with a real
worker pid. From there the queue **drains itself** — the worker's watchdog reaps
the hung `autopilot-cycle` duplicates that piled up during the outage.

> **Do NOT mass-`gbrain jobs cancel` in a tight loop** to "help it along." Each
> cancel opens a database connection; a rapid loop trips the connection-pool limit
> (next section) and starts *failing* mid-loop. A couple of targeted cancels of a
> genuinely-stuck active job are fine; a 28-item loop is not.

---

## Symptom: `Cannot connect to database: (EMAXCONNSESSION)`

Full text: `max clients reached in session mode - max clients are limited to
pool_size: N`. gbrain (Supabase variant) uses a **session-mode** connection pool.
In session mode each persistent client holds a server slot for its whole life, so
several `gbrain serve` instances (one per open Claude session — and any *other*
tool using the same brain, e.g. a second AI app) plus the supervisor/worker sit
near the ceiling. A burst (like the cancel loop above) tips it over.

**Do NOT "fix" this by switching the connection URL to the transaction-mode pooler
(port 6543).**

> **Iron law:** gbrain's job queue coordinates with **session-scoped Postgres
> advisory locks** (`gbrain-sync:<source_id>`). Transaction-mode pooling recycles
> the connection after every transaction and **breaks session-scoped locks and
> LISTEN/NOTIFY** — you'd trade a pool error for broken job locking across every
> session. gbrain is on session mode *deliberately*.

**Prescribed fixes, in order:**
1. **Stop the burst.** The exhaustion is usually self-inflicted (a CLI loop). Stop
   hammering and the pool recovers on its own — confirm with any light read.
2. **If it's genuinely steady-state too small:** raise `pool_size` (KEEP session
   mode) on the Supabase dashboard (Database → Connection Pooling), bounded by your
   plan's `max_connections`. A *modest* bump — set it above the ceiling and you
   trade this error for a worse one.
3. Fewer standing consumers — close Claude sessions / other apps you don't need
   pointed at the brain.

> `~/.gbrain/config.json` holds the connection URL **with a password** — don't
> `cat` it. The port/mode question rarely needs the file; the error text already
> tells you it's session mode.

---

## Symptom: `gbrain doctor` shows N unacknowledged sync_failures that won't clear

`gbrain doctor` counts unacknowledged rows in `~/.gbrain/sync-failures.jsonl`. The
stubborn ones have `path: "<head>"` (per-source git-HEAD-verification timeouts —
one per source, usually from transient git slowness during pool thrash).

**Why no command clears them:** `gbrain sync --skip-failed` / `--retry-failed` /
`--all` all filter *file-path* failures and **skip the `<head>` pseudo-entries** —
so every sync flag no-ops on them. This is a real gap, not user error.

**Prescribed fix — acknowledge them directly, in gbrain's own format.** It's a
plain JSONL log (no secrets):

```bash
cp ~/.gbrain/sync-failures.jsonl ~/.gbrain/sync-failures.jsonl.bak-<date>   # back up FIRST
```
Then, for each record where `path == "<head>"` and `acknowledged == false`, set the
same fields gbrain sets when it acknowledges a failure:
```
  state          = "acknowledged"
  acknowledged   = true
  acknowledged_at = <now, ISO-8601 Z>
  resolved_at    = <now, ISO-8601 Z>
```
Write to a `.tmp`, `os.replace` it, **assert the exact expected number changed**
(fail loud if not — don't touch rows you didn't mean to), and keep every other
line byte-for-byte. Verify:
```bash
gbrain doctor --fast    # → sync_failures: [OK] … all acknowledged
```

`git rev-parse HEAD` is ~0.1s on a healthy repo, so once the machine is calm these
`<head>` timeouts don't recur.

---

## The 5-minute runbook (all of the above, in order)

1. `gbrain jobs stats` — WEDGED? `gbrain jobs supervisor status` — not running?
2. `nohup gbrain jobs supervisor start > ~/.gbrain/supervisor-manual.log 2>&1 & disown`
   — **from git-bash**. Confirm `Supervisor: running`.
3. Let the queue drain (watchdog reaps the debris). Don't loop-cancel.
4. If `EMAXCONNSESSION` appears: stop hammering; raise `pool_size` *only* if
   steady-state; **never switch to the transaction pooler**.
5. Stale `<head>` sync_failures: back up + ack them in `sync-failures.jsonl`; verify
   with `gbrain doctor`.

See `example_gbrain_ops_resolver.md` for the resolver rows that make this manual
discoverable from a plain-English symptom.
