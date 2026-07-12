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
