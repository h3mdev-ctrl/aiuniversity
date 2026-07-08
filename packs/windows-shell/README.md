# windows-shell

Hardens a **Windows dev shell** so Python and PowerShell tooling doesn't silently
misfire. Windows has a cluster of traps that make a setup *look* fine while quietly
breaking — Python defaulting to a legacy code page, Python 3.14 failing every HTTPS
call, PowerShell 5.1 mangling scripts that contain a single non-ASCII character.
Each one fails with an error that never names the real cause, so a newcomer's Claude
burns hours chasing ghosts. This pack detects each and hands over the exact,
already-proven fix. Tool-agnostic: it's about the shell, not any one app.

See [pack-structure.md](../../docs/pack-structure.md) for the section conventions
this README follows, and [files/windows_gotchas.md](files/windows_gotchas.md) for
the two traps that can't be gated by a check (plugin cwd, MAX_PATH) plus copy-paste
HTTPS-via-PowerShell patterns.

## Contract

- **`python-utf8`** — confirms Python defaults to UTF-8 I/O (`sys.stdout.encoding`
  is `utf-8`), not the Windows ANSI code page that mojibakes text and crashes on
  UTF-8 files. Fix: `setx PYTHONUTF8 1`.
- **`python-https`** — confirms Python can actually complete an HTTPS request, i.e.
  it isn't hitting the Python-3.14-on-Windows certificate-verification failure. On
  red, routes the caller to PowerShell-native HTTPS instead of a dead cert chase.
- **`powershell-utf8-safe`** — confirms a UTF-8-safe PowerShell 7 (`pwsh`) is
  present, so `.ps1` files with non-ASCII bytes aren't silently half-executed by
  PowerShell 5.1's ANSI reader.
- **Every check runs a real executable** (`python` / `pwsh`) under cmd.exe — it
  passes for the same reason on any Windows machine, not just in bash.

## Iron Laws

- **Detect, then hand over the proven fix — never guess.** Each of these traps
  wasted real hours (Python SSL on the solar brief, 19 May; `.ps1` silent-skip on a
  scraper install, 2 Jul). The on_fail is the workaround that actually worked, not a
  fresh diagnosis.
- **Don't fight the Python 3.14 SSL trap in Python.** `REQUESTS_CA_BUNDLE`,
  `SSL_CERT_FILE`, and `curl` all fail on this machine class. The prescribed fix is
  PowerShell-native HTTPS (or a 3.12/3.13 interpreter) — the pack refuses to send you
  down the cert-bundle rabbit hole.
- **A silent no-op is a failure, not a pass.** A `.ps1` that exits 0 having skipped
  its middle block is the exact "looks fine, isn't" failure this project exists to
  kill. The pack treats "no UTF-8-safe shell" as red, because 5.1 can lie with exit 0.
- **Only gate what a check can honestly prove.** Traps that depend on files this pack
  can't assume (a plugin's `.mcp.json`, a specific deep path) are *documented*, not
  turned into a flaky check that passes on a clean machine and means nothing.

## Anti-Patterns

- ❌ **Chasing `certifi` / CA-bundle env vars for the Python 3.14 SSL error.** They
  don't fix this trap on Windows; you'll lose an afternoon. Use PowerShell HTTPS.
- ❌ **Assuming a `.ps1` that printed *some* output ran fully.** 5.1 can skip an
  entire block on one stray non-ASCII byte and still exit 0. Scan for bytes > 127
  before debugging the logic.
- ❌ **Editing config files (`.env`/`.json`/`.yaml`) with PowerShell `Out-File` /
  `Set-Content`.** They prepend an invisible UTF-8 BOM that breaks parsers. Write
  without a BOM (helper in files/windows_gotchas.md).
- ❌ **Trusting a plugin that shows "connected · N tools" as working.** On Windows,
  `${CLAUDE_PLUGIN_ROOT}` in a plugin's `.mcp.json` args doesn't expand — the server
  runs in the wrong cwd and never functions. See files/windows_gotchas.md.
- ❌ **Leaving deeply-nested working paths in place.** Over 260 chars, Python's
  `open()` fails with FileNotFoundError even though the file exists. Keep paths short
  or enable long paths.

## Related packs

- [`gbrain-windows`](../gbrain-windows/) — sets up gbrain on Windows; shares this
  pack's cmd.exe-real-checks philosophy. gbrain's own footguns (PGLite/WASM, BOM in
  config) live there; the *general* shell traps live here.
- [`foundation`](../foundation/) — the umbrella pack. windows-shell is a sensible
  pre-flight for any Windows user before the tool-specific packs run.
