# Sample resolver rows for gbrain operations — EXAMPLE (learn the STRUCTURE)

> A manual only helps if the AI *finds* it at the moment of the problem. That's what
> a **resolver** does: it maps a plain-English symptom → the exact page/manual that
> fixes it. Without a row, a fresh Claude re-derives the fix from scratch (the
> expensive wandering the whole project exists to prevent). Copy the STRUCTURE —
> intent-phrased rows that point at where the answer lives — replace the targets
> with your own.

## The shape of a resolver row

A good row is triggered by the **moment**, not the topic — phrased as "when you're
about to…" / "when you see…", so it fires *before* the AI guesses:

| When you're about to / when you see…                                            | Consult                          |
| ------------------------------------------------------------------------------- | -------------------------------- |
| Run a 2nd/3rd command to fix a misbehaving tool                                 | *read its full `--help` + its own `doctor`/`stats`/`status` FIRST* |

That single row would have saved the hour that produced `gbrain_recovery_windows.md`.

## Sample rows — gbrain day-2 operations

Drop these into your always-loaded resolver index (the memory pack sets one up).
Each points at the recovery manual and names the *fix in one clause* so the AI acts
even before opening the page:

| When you're about to / when you see…                                                              | Consult |
| ------------------------------------------------------------------------------------------------- | ------- |
| gbrain background maintenance stalled — `jobs stats` shows WEDGED, doctor score sinking            | [gbrain_recovery_windows] — restart the supervisor **detached from git-bash**; the queue drains itself |
| Restart the gbrain supervisor / it crashed and nothing brought it back                             | [gbrain_recovery_windows §Fix] — `nohup gbrain jobs supervisor start … & disown` from **bash, not PowerShell** (`/tmp/.gbrain` trap) |
| See `EMAXCONNSESSION` / "max clients reached in session mode"                                       | [gbrain_recovery_windows §pool] — stop the burst; raise `pool_size` only if steady-state; **never** switch to the transaction pooler (breaks session locks) |
| `gbrain doctor` shows `<head>` sync_failures that `--skip-failed`/`--retry-failed` won't clear      | [gbrain_recovery_windows §sync_failures] — back up + acknowledge them directly in `~/.gbrain/sync-failures.jsonl` |
| About to `kill` a "worker pid" gbrain reported                                                      | *verify the PID is actually gbrain first — PIDs recycle* (a reported worker pid was once a recycled Edge process) |

## Conventions (the same three that make any resolver work)

- **Trigger on the moment, not the noun.** "when you see `EMAXCONNSESSION`" fires;
  "database stuff" doesn't.
- **Name the fix in the row.** The `Consult` cell carries the one-clause action, so a
  row is useful even if the AI never opens the target. Point at the section
  (`§pool`) when the manual is long.
- **A missing row is a gap, not a dead end.** Hit a symptom with no row? Add the row
  *in the same session you solved it* — that's how the resolver compounds instead of
  the same hour being re-spent next month.

See `example_brain_filing.md` for the *content*-filing resolver (intent → slug);
this file is its operational sibling (symptom → fix-manual).
