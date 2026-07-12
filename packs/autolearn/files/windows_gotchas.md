# Windows gotchas when running the autolearn drain (and any pack that shells out)

> These are REAL errors hit while wiring the unattended `--drain` on a Windows 11
> box, each with the fix that worked. If you're on Windows and something in these
> packs "just fails" with an opaque error, it's probably one of these. macOS/Linux
> users can skip this file.

The through-line: **Windows shells (cmd.exe, PowerShell) do helpful things behind
your back that Python's `subprocess` and Task Scheduler do NOT** — PATHEXT
resolution, `.cmd` shim lookup, argument re-parsing. When you cut out the shell,
those conveniences vanish and you get a cryptic failure.

---

## 1. `subprocess.run(["claude", ...])` → `WinError 2` (file not found)

**Symptom:** the drain dies with
`FileNotFoundError: [WinError 2] The system cannot find the file specified`,
even though `claude` works fine when you type it in a terminal.

**Cause:** `claude` (and `gbrain`, `npm`, `npx`, `gh`, ...) installed via npm are
**`.cmd` shim files**, not real `.exe`s. A terminal auto-resolves `claude` →
`claude.CMD` via PATHEXT. Python's `subprocess` with a bare name and no shell does
**not** — CreateProcess needs the real file, extension and all.

**Fix — resolve the real path with `shutil.which` (portable, correct casing):**

```python
import shutil, subprocess
exe = shutil.which("claude")     # -> C:\...\npm\claude.CMD on Windows; the binary on mac/linux
if not exe:
    ...                          # CLI not installed -- handle it, don't crash
subprocess.run([exe, "-p", "--model", model], ...)
```

Do NOT hardcode `C:\Users\<you>\AppData\Roaming\npm\claude.cmd` — `shutil.which`
finds it wherever npm put it and returns the right extension.

## 2. A big / multi-line / JSON prompt as an argv element → mangled

**Symptom:** the model gets a garbled prompt, or the call errors on quotes/braces,
when the prompt spans lines or contains `{ } " |`.

**Cause:** launching a `.cmd` re-runs the arguments through cmd.exe, which re-parses
quotes, `%VAR%`, and special chars. A JSON-laden reflection prompt gets shredded.

**Fix — feed the prompt on STDIN, not as an argument.** `claude -p` reads the
prompt from stdin when no prompt arg is given. **Pin `encoding="utf-8"`** (see
trap 5 for why — the prompt carries non-cp1252 chars):

```python
subprocess.run([exe, "-p", "--model", model], input=prompt,
               capture_output=True, text=True, encoding="utf-8")
```

Same rule for any CLI that accepts stdin: prefer stdin over a giant argv string on
Windows. (If you must pass it as an argument, there's a hard ~8191-char command-line
limit too.)

## 3. Task Scheduler hands your script a MINIMAL PATH

**Symptom:** the drain works when you run it by hand, but the scheduled job files
nothing — `shutil.which("claude")` returns `None` under the scheduler.

**Cause:** a Windows scheduled task doesn't always get your full interactive PATH,
so the npm bin dir (`%AppData%\Roaming\npm`) may be missing.

**Fix — put the npm bin dir on PATH inside the script before you shell out:**

```python
npm_bin = os.path.expanduser(r"~\AppData\Roaming\npm")
if os.path.isdir(npm_bin) and npm_bin.lower() not in env.get("PATH", "").lower():
    env["PATH"] = npm_bin + os.pathsep + env.get("PATH", "")
```

Also run the task with **`pythonw.exe`** (not `python.exe`) so no console window
flashes every time it fires; write your output to a log file instead of stdout.

## 4. PowerShell `2>&1` on a native exe flips success into "failure"

**Symptom:** a scheduled `.ps1` that runs `gbrain`/`claude`/`git` reports failure
(non-zero) even though the command actually succeeded (exit 0).

**Cause:** in PowerShell, redirecting a **native** command's stderr with `2>&1`
wraps each stderr line as a `NativeCommandError` record and can flip `$?` to false.

**Fix:** don't `2>&1` a native exe in PowerShell. Let its streams flow, or route
through `cmd.exe /c` if you need combined output. (Bash — including this repo's
Bash tooling — is normal POSIX and doesn't have this trap.)

## 5. `text=True` without `encoding=` crashes on non-cp1252 chars

**Symptom:** the drain dies with
`UnicodeEncodeError: 'charmap' codec can't encode character '→'` **before the
model is ever called** — and because it's inside a piped subprocess, the traceback
shows up in stderr while the wrapper just logs "no usable plan". Every drain
silently no-ops; the queue never empties.

**Cause:** `subprocess.run(..., input=prompt, text=True)` with **no `encoding=`**
encodes stdin using the process locale — on Windows that's **cp1252**, which cannot
represent `→` (U+2192), `—` (em dash), smart quotes, or any non-Latin-1 char. Your
reflection prompt embeds MEMORY.md's routing table, which is full of `→` arrows, so
the very first drain against a real memory index crashes on encode.

**Fix — always pin `encoding="utf-8"` on any `subprocess.run` with `text=True`:**

```python
subprocess.run([exe, "-p", "--model", model], input=prompt,
               capture_output=True, text=True, encoding="utf-8")
```

This is the single most common Windows subprocess footgun in this repo. `text=True`
alone is a latent cp1252 bomb — grep your code for `text=True` and confirm each one
that touches user/memory content also sets `encoding="utf-8"`.

## 6. The model's OUTPUT window truncates a big batch → unparseable JSON

**Symptom:** with the encoding fixed, the drain reaches the model but still logs
"no usable plan" once the queue gets large (tens of commits). Small queues work.

**Cause:** the drain reflects over the **whole queue at once**. A cheap reflection
model (e.g. Haiku, ~8k output tokens) can't emit a complete JSON plan for 30+
commits — the response is cut off mid-object, so `json.loads` fails and the plan is
discarded. The queue is kept (good — nothing lost) but never shrinks (bad — it can
never drain).

**Fix — cap the per-run batch and keep the remainder for the next run:**

```python
DRAIN_BATCH = int(os.environ.get("AUTOLEARN_DRAIN_BATCH", "10"))
batch = entries[:DRAIN_BATCH]
# ... reflect on `batch` only ...
remaining = entries[DRAIN_BATCH:]
if remaining:
    queue_path().write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in remaining) + "\n",
        encoding="utf-8")
else:
    queue_path().unlink(missing_ok=True)
```

A deep backlog then drains over several scheduled runs instead of choking on one
oversized prompt. Tune `AUTOLEARN_DRAIN_BATCH` down for smaller models.

## 7. Your memory folder needs to be a git repo for rollback to work

The drain makes **one git commit per run** in your memory folder so a bad
autonomous write is a one-command `git revert HEAD`. That only works if the memory
folder is a git repo. If it isn't, the drain still files + gates learnings, but
prints `(memory folder is not a git repo -- no per-drain commit)` and you lose the
easy undo. **Fix once:**

```
cd <your memory folder>
git init && git add -A && git commit -m "seed: version memory for autolearn rollback"
```

## 8. (Related) the credential guard can block your _commit message_

If you run a credential-blocking hook (see the guardrails pack), note it scans the
**text of the command**, including `git commit -m "..."`. A commit message that
literally contains a secret-shaped string (`.env`, `ghp_...`, `sk-ant-...`) gets
blocked — that's the guard working, not a bug. Reword the message ("dot-env
variants", "GitHub tokens") and commit again.

---

**Meta-lesson for your own memory:** every one of these cost real minutes to
diagnose the first time. That's exactly what autolearn is for — when you hit a
Windows quirk and find the fix, file it as a `reference_*` memory so your future
sessions (and your Claude) start from the answer, not the error.
