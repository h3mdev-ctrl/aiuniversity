# Windows gotchas — the un-gated traps + copy-paste fixes

Two of the traps this pack knows about can't be turned into an honest check: they
depend on files or state the pack can't assume exist, so a check would either pass
meaninglessly on a clean machine or fire fragile false positives. They're documented
here instead. Plus the HTTPS-via-PowerShell patterns the `python-https` step points
at, and a write-without-a-BOM helper.

---

## 1. The Claude Code plugin `${CLAUDE_PLUGIN_ROOT}` cwd bug (Windows)

**Symptom:** a Claude Code plugin's MCP server shows `connected · N tools` in `/mcp`,
but its actual side-effects never happen (no polling, no file watching, no scheduled
jobs). It *looks* installed. It isn't working.

**Cause:** on Windows, Claude Code does **not** expand `${CLAUDE_PLUGIN_ROOT}` in a
plugin's `.mcp.json` args. The literal string is passed through, so a launcher like
`bun run --cwd ${CLAUDE_PLUGIN_ROOT} …` fails to change directory and runs from
wherever Claude Code was launched (usually your home folder) — it can't find its own
`package.json`, so it starts but never functions.

**Fix:** hardcode the absolute path in the plugin's cached `.mcp.json`:
```json
"args": ["run", "--cwd",
  "C:\\Users\\<you>\\.claude\\plugins\\cache\\<marketplace>\\<plugin>\\<version>",
  "--shell=bun", "--silent", "start"]
```
**Caveat:** a plugin update overwrites this — re-apply after any version bump.

**Diagnostic:** if a plugin is "connected" but silent, open its `.mcp.json` at
`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/` and look for any `${…}`
in `args`/`env`. Replace with an absolute path, kill the plugin's `bun`/`node`
processes, restart, and verify the side-effect actually fires.

---

## 2. The 260-char MAX_PATH limit

**Symptom:** Python `open()` raises `FileNotFoundError` on a file that clearly exists
(`Test-Path` in PowerShell confirms it).

**Cause:** Windows default `MAX_PATH` is 260 characters. Deeply-nested paths (common
under `AppData`) silently exceed it and Python can't open them.

**Fix:** copy the file somewhere short (e.g. `C:\Users\<you>\Downloads\`) before
opening, or enable long-path support (admin): set
`HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled` to `1`.

---

## 3. HTTPS via PowerShell (the `python-https` fallback)

When Python 3.14 can't verify certs, do the HTTPS from PowerShell instead.

**Simple JSON POST/GET:**
```powershell
$body = @{ key = 'value' } | ConvertTo-Json -Compress
Invoke-RestMethod -Uri $url -Method POST `
  -ContentType 'application/json; charset=utf-8' `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

**Multipart file upload** (PS 5.1's `Invoke-RestMethod` has no `-Form`, use .NET):
```powershell
Add-Type -AssemblyName System.Net.Http
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
$client = New-Object System.Net.Http.HttpClient
$form   = New-Object System.Net.Http.MultipartFormDataContent
$bytes  = [System.IO.File]::ReadAllBytes($path)
$file   = New-Object System.Net.Http.ByteArrayContent(,$bytes)
$file.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse('application/pdf')
$form.Add($file, '"document"', '"filename.pdf"')
$client.PostAsync($url, $form).Result.Content.ReadAsStringAsync().Result
```
Field-name quoting (`'"document"'`) matters — without the inner quotes the multipart
header is malformed.

---

## 4. Writing a config file WITHOUT a BOM

PowerShell `Out-File` and `Set-Content` prepend an invisible UTF-8 BOM (even with
`-Encoding ascii`) that breaks `.env` / `.json` / `.yaml` parsers. Write the file the
BOM-free way instead:
```powershell
[System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))
```
The `$false` means "no BOM." Confirm a file is clean: the first bytes should NOT be
`EF BB BF`.

---

## 5. PowerShell 5.1 parser traps in commands you hand the user

A Claude Code answer often ends with a shell block the user clicks Run on. On
Windows that block executes in **Windows PowerShell 5.1**, not bash. Three bash
habits are *parser errors* there — they fail BEFORE the command runs, so the
user sees "your tool is broken" rather than "your invocation is wrong."

| Don't write | What 5.1 says | Write instead |
|---|---|---|
| `A && B` | `not a valid statement separator in this version` | `A; B` or `A; if ($?) { B }` |
| `--flag <placeholder>` | `The '<' operator is reserved for future use` | a real path, or make the arg optional |
| `python ~/x.py` | *no error* — `~` is passed literally to the exe, which then can't open `C:\Users\you\~\x.py` | `python $HOME\x.py` |

The third is the nastiest because it produces a plausible-looking
`No such file or directory` naming a path with a literal `~` segment in the
middle. All three were hit in a single session on a machine that already had a
guard for the first one — the guard was written for `&&` alone and nobody had
told it about the other two.

`>` is fine — output redirection genuinely works in PowerShell. Bash heredocs
(`<<'EOF'`) are not PowerShell syntax and fail on the same `<` rule.

## 6. `subprocess(..., text=True)` with no `encoding=`

Text mode encodes stdin and decodes stdout through the **locale** codec (cp1252
here). One non-ASCII byte raises `UnicodeEncodeError` *inside subprocess's writer
thread*. The child then gets no stdin and hangs until timeout — which reads as
"the child program is broken" rather than "the pipe never opened."

```python
subprocess.run(cmd, input=data.encode("utf-8"), capture_output=True)  # bytes: safe
subprocess.run(cmd, text=True, encoding="utf-8")                      # or pin it
```

Measured on one machine: encoding failures of this family appeared in **45 of 441
sessions (10%)**.

> Measure before you claim a rate. An earlier note here said 25% — that summed
> per-signature session counts (38 + 35 + 45) instead of taking the distinct
> union. Don't inflate a justification inside the thing it justifies.

## 7. `sys.stdout.reconfigure()` without a guard

`reconfigure` exists on a real console but not on every stream a child process
inherits, so it raises `AttributeError` under Task Scheduler or when the script
is invoked by another script.

```python
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
```

## 8. Your repo root is the Python import path — and `cd` breaks it

If the project has no `PYTHONPATH` carrying the repo root, then **cwd IS the
import path**:

```
from repo root : python -c "import research"  ->  OK
from a subdir  : python -c "import research"  ->  ModuleNotFoundError
```

So `cd research && python -c "import research.backtest"` fails, and the error
names a *module*, which sends you hunting for a missing dependency that was never
missing. Measured on one machine: **94 `ModuleNotFoundError`s, 96% of them local
packages, only 4% genuinely absent third-party deps** — and the same handful of
modules over and over (one appeared 17 times).

Fix: don't `cd` before running python — use absolute paths for file arguments and
let cwd stay at the repo root. Or prefix `PYTHONPATH=.`.

Related: an entry-point script invoked as `python scripts/thing.py` gets
`__package__ = None`, so `from . import x` fails. Use absolute imports plus a
`sys.path` insert.

## 9. Heredocs mangle Python string literals

A `\n` inside a string in a shell heredoc becomes a **real newline** and splits
the literal; a Windows path in a Python string (`"C:\Users\..."`) raises
`SyntaxError: (unicode error) 'unicodeescape' codec can't decode bytes`.

Measured: of ~105 `SyntaxError`s on one machine, **50 were string-literal
mangling** — essentially none were ordinary code errors, because a real `.py`
file gets caught by the editor. They were all artifacts of *how the command was
composed*.

Write files with the Write/Edit tool, not by heredoc-ing Python into a shell.

## 10. `shutil.copy2` preserves mtime — so `ls -t` misorders your backups

`copy2` copies metadata including mtime. A backup made with it carries the mtime
of the **content it holds**, not the moment it was created, so `ls -t` sorts your
backups by the age of what's inside them.

This bites during a rollback: `ls -t *.bak | head -1` returns the wrong file, and
you "restore" something that was never the previous state. Sort by filename if
you timestamp them (`.bak-<name>-YYYYmmdd-HHMMSS`), or use `copy` instead of
`copy2` when creation order is what matters.
