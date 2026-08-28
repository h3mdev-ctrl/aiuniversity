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

## 7. Every token in a match class must carry the danger ALONE

Rule 3 says a noisy guard is already dead. This is *why* they get noisy, and it
is almost always the same thing: **a generic English word sitting in a danger
class as a bare alternative.**

A credential-solicitation guard had this noun class:

```
token|api_key|key|keys|password|pass|secret|...|pin|license|...
```

and this verb class:

```
paste|share|send|give|tell|type|enter|provide|drop|put|...
```

Both are defensible read one at a time. Together they mean ordinary prose fires
the guard:

> "…giving every row a **key** and collapsing rows that **share it**"

`key` within 120 characters of `share it`. Nothing to do with credentials. Its
own block log showed **~50% false positives across 40 events** — including one
that blocked a commit, and one that fired on a *read-only grep* whose search
pattern happened to contain `json.dump`.

**The test, applied to each token on its own:** does its presence carry the
danger, or does it need the rest of the sentence to be dangerous? If it needs
context, it does not belong as a bare alternative.

Three ways to fix it, in preference order:

1. **Split STRONG from WEAK.** `api key`, `client_secret`, `AWS_*_KEY` stand
   alone. Bare `key`, `pass`, `pin` do not — admit them only with a qualifier,
   and keep them out of proximity rules entirely.
2. **Scope to the region where the pattern would actually execute.** A
   PowerShell-operator guard matches only inside *shell-tagged* fences and
   strips quotes and comments first, so `echo "use ; not &&"` stays silent. Its
   docstring says why: *a guard that cries wolf on its own explanation gets
   ignored.* Newer guards on the same machine had not inherited it.
3. **Require the discriminating token the danger actually needs.** For
   solicitation that is an **addressee** — `your`, `me`, a destination like
   "here"/"in chat", or a clause-initial imperative. It cleanly separates
   *"paste your token **here**"* (a request) from *"Both **share** the same bot
   **token**"* (a description), and from *"drop the token **into a .env
   file**"* (correct advice, wrong destination).

After all three: **22/22 controls**, historical firings 42 → 19.

**Do NOT reach for a blanket surface exemption** — "skip `.md` files", "skip
tests" — on a guard whose false negative is irreversible. Narrow the *pattern*.
When you genuinely must allow a specific value, allow it **by `sha256[:12]`
digest**, never by path: allowing a placeholder in a test fixture should not
also allow a real credential that later lands in the same file.

And note what happened while writing the fixes: **both were caught by their own
positive controls first.** One replacement silently deleted the anchor line it
matched; the other split the command on `|` before masking quotes, shattering
the very grep pattern it was written to ignore. Neither was visible on reading.

---

## A corollary: a pattern list is an allowlist of things you remembered

A redactor and a log scanner were maintained as two separate pattern lists.
Both were missing Telegram bot tokens. The scan reported **all-clear** while a
live bot token sat in plaintext on disk — because the scanner could not name
what the redactor could not name.

"No hits" only ever means "no hits for what I thought of".

- **One list, imported** — never a second copy. Adding a shape in one place
  should protect every consumer.
- Treat a clean scan as evidence about *coverage*, not about *absence*.
- When you add a shape, add a **positive control** with a synthetic specimen of
  it. That is what caught the Telegram pattern failing to match `bot<token>` in
  an API URL — `\b` does not match between a letter and a digit.

---

## The shape underneath all seven

Every one is the same failure: **a component that cannot report its own
brokenness.** A dead hook, a dead counter, a dark matcher, a blinded scan, a
guard that cries wolf, a pattern list with a hole in it — none of them raise.
They just quietly stop working, and the system keeps looking fine.

So build the thing that asks. Then run it on a schedule, not on a hunch.
