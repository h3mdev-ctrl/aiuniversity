# Scheduled nudge -- catch learnings between sessions

The commit hook captures every commit, and in-session you drain on commit cadence
(`--drain-due`). But if you stop working with commits still queued, those lessons
sit unlearned until you next open the repo. A scheduled **nudge** closes that gap.

## What the nudge does (and deliberately does NOT do)

`phantom_autolearn.py --nudge`:
- **exits 0 and prints a reminder** when the queue is deep (>= threshold) AND has
  gone stale (no drain in the last N minutes), otherwise
- **exits 1 and prints nothing**.

It NEVER reflects or writes memory on its own. It only reminds a human/Claude to
run the drain. That is the deliberate design: reflection stays in the loop, so
there is no unattended write to guard against (no snapshot/rollback needed).

Thresholds (env vars):
- `AUTOLEARN_DRAIN_THRESHOLD` -- queue depth that counts as "worth draining" (default 5)
- `AUTOLEARN_NUDGE_STALE_MINUTES` -- how long the queue may sit before nudging (default 120)

## Wiring it to a scheduler

The nudge prints to stdout; deliver that however you like. Point your scheduler at:

```
python <repo>/packs/autolearn/files/phantom_autolearn.py --nudge
```

**Windows (Task Scheduler)** -- run every 2 hours; only surfaces output when a
drain is due:

```powershell
schtasks /Create /TN "autolearn-nudge" /SC HOURLY /MO 2 ^
  /TR "python C:\path\to\packs\autolearn\files\phantom_autolearn.py --nudge" /F
```

**cron (macOS / Linux)** -- every 2 hours:

```
0 */2 * * *  cd /path/to/repo && python packs/autolearn/files/phantom_autolearn.py --nudge
```

**Route the reminder somewhere you'll see it.** The bare task above just logs to
the scheduler. To actually get pinged, pipe the output into your own channel --
a desktop notification, a Slack/Telegram webhook, an email, a file you watch:

```sh
MSG=$(python packs/autolearn/files/phantom_autolearn.py --nudge) && [ -n "$MSG" ] && notify-send "$MSG"
```

## Why a nudge, not an autonomous drain

Phantom (the inspiration) runs an unattended reflection subprocess on a cron and
needs snapshot + byte-invariant rollback to make unattended writes safe. We do
NOT work autonomously -- a human or an in-session Claude is present for the
reflection -- so we keep the write human-supervised and skip that whole safety
layer. The nudge is the smallest thing that makes autolearn *active* between
sessions without turning it autonomous.
