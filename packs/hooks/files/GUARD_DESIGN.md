# Designing a guard that survives contact

Six rules, each paid for with a real defect on a live machine in a single day.
They are ordered by how expensive the lesson was.

The setting: ~30 hooks, 46,857 tool calls across 441 sessions. Two of the hooks
were dead simultaneously for a full day, and a third had a security bypass opened
by a well-intentioned fix. None of it announced itself.

---

## 1. A broken guard and a quiet guard look identical

Silence is both the success signal and the failure signal, so you cannot tell
them apart by watching.

`win11_quirk_guard` crashed on **every** Bash/Write/Edit call for a day:

```
AttributeError: 'function' object has no attribute 'search'
```

A deploy had added callable matchers to a list whose dispatch loop still called
`.search()`. Work continued and nothing looked wrong, because **PreToolUse treats
an unexpected exit as a NON-BLOCKING error — the tool call proceeds unguarded.**

Separately, a `retrieval_count` column had been throwing `no such column` into a
bare `except` for weeks. It read `0`. A counter that reads 0 looks exactly like a
counter for something that never happened.

**Rule:** feed every registered hook a benign payload and assert it answers
allow-or-block. That is `hook_doctor.py` in this pack. Run it after any hook edit
and at every wrap-up.

---

## 2. Narrow a guard. Never blind it. Pin the narrowing with a POSITIVE control

This is the expensive one.

A guard was blocking a `git commit` because the commit **message** contained the
literals `shutil.copy` and `settings.json`. The fix looked obvious: "a heredoc
body is data on a program's stdin, not a command line" — so strip heredoc bodies
before scanning.

That reasoning is true only when the program *consumes* the body as data. When
the heredoc feeds an **interpreter, the body is the program**. Measured against
the live guard afterwards, all of these were **ALLOWED**:

```
python - <<PY     import shutil; shutil.copy("/tmp/x", "<a hook>")     PY
bash -s <<SH      rm <a hook>                                          SH
sh <<EOF          cp /tmp/x ~/.claude/settings.json                    EOF
python3 <<'PY'    pathlib.Path("<a hook>").write_text("x")             PY
```

A prompt injection could now rewrite any hook — including the credential guard —
through a shape the guard had been *taught to ignore*. The exact attack it
existed to stop, opened while fixing a cosmetic false positive.

The tests at the time passed. They pinned the false-positive cases and never
pinned a **positive control** proving the dangerous form still tripped.

**Rule:** every narrowing ships with a control that proves the dangerous case
still blocks. If your test suite only demonstrates that the annoying thing
stopped, it cannot tell you what else stopped with it. Unrecognised input goes to
the SCANNED path: a false positive costs one message, a bypass costs the guard.

---

## 3. A guard that is wrong half the time is already dead

Mining one guard's own block log:

```
16x  'sed'   <- sed -n '150,175p' file  : READ-ONLY
 3x  'ln'    <- matched inside `grep -ln`
 5x  '.write_text('   3x 'cp'   5x 'rm' : genuine
```

**19 of 38 blocks (50%) were on read-only commands.** Nobody disables a noisy
guard; they learn to route around it, which is worse because the guard still
looks installed.

A specific sub-case worth its own line: **guards firing on documentation of the
trap they guard against.** Writing a docs page about these very traps tripped
five false positives, one of which blocked the commit. `powershell_chain_guard`
already solved this and says so in its docstring — "a guard that cries wolf on
its own explanation gets ignored" — by stripping quotes and comments before
matching. Newer guards had not inherited the lesson.

**Rule:** mine your block history for false positives on a schedule, the way you
would mine approval history for an allowlist. Never auto-apply; propose, and
never propose loosening a destructive class.

---

## 4. Fail closed only where a failure is irreversible

`PreToolUse`: `0` = allow, `2` = block, **anything else = the call proceeds.** So
a guard that crashes is a guard that permits. Measured: 6 of 7 malformed payloads
crashed two security guards into exit 1.

But fail-closed is not a blanket policy. Of four guards examined:

| Guard | Correct posture |
|---|---|
| credential guard (blocks reading secrets) | **closed** — disclosure is irreversible |
| self-modification guard (blocks editing hooks) | **closed** — an injection disabling guards is irreversible |
| recon-before-build (an advisory nudge) | **open**, deliberately — blocking on a hook bug breaks every Write |
| solicit guard (a Stop-hook reminder) | **open** — it scans output already produced; no gain |

**Rule:** fail closed where the guard prevents an irreversible disclosure or
privilege change. Everywhere else, a wedged workflow is the bigger harm. Write
the reason in the code, so the next person doesn't "fix" the asymmetry.

---

## 5. Classify with what you control, not with what the OS gives you

A containment check used `Path(p).resolve()` for both sides. `resolve()` anchors
a relative path to the **process's** cwd — but the path in the payload is
relative to the **session's** cwd, which the payload supplies and the function
ignored. Measured:

| session cwd | hook proc cwd | verdict |
|---|---|---|
| protected dir | elsewhere | **allow — bypass** |
| elsewhere | protected dir | block — false positive |

The same function shape failed on another machine for a different reason: on
Linux, a Windows path is not absolute, so `resolve()` folded a foreign path
*into* the managed root.

Note the fixes differ by platform, and copying the other one blindly would be
wrong: on Windows `resolve()` normalizes case, `..`, `//` and trailing dots
correctly — 12 probe cases, 0 misclassifications — so removing it would add risk.
**The bug was the base, not the normalization.**

**Rule:** name the base explicitly. Then pin the normalization cases you are
relying on, so a later "simplification" cannot quietly drop them.

---

## 6. Test the dispatch, not just the matcher

Three of the defects above were in *plumbing*, not in any regex: a loop calling
`.search()` on a callable, a matcher registered for the wrong tools, an exit code
the harness interprets as "proceed".

A regression suite that exercises matchers in isolation would have passed
throughout. Drive the **real hook binary** with a real payload and assert the
exit code.

Two layers, and you need both:

- **liveness** — is it firing at all? (`hook_doctor.py`)
- **correctness** — does it still catch what it was built for, and still ignore
  what it should? One case per footgun you have actually hit, each with its
  negative control.

A hook can pass liveness with a matcher that no longer matches anything. That is
exactly what a dark advisory list looks like from the outside.

---

## The shape underneath all six

Every one is the same failure: **a component that cannot report its own
brokenness.** A dead hook, a dead counter, a dark matcher, a blinded scan, a
guard that cries wolf — none of them raise. They just quietly stop working, and
the system keeps looking fine.

So build the thing that asks. Then run it on a schedule, not on a hunch.
