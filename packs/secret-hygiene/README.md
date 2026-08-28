# secret-hygiene

**Stop a credential reaching disk, and stop it reaching a remote.**

The `guardrails` pack blocks Claude from *reading* your `.env`. That is one of three
directions. This pack covers the other two — both of which were live defects on the
machine this came from, found on the same morning.

### What's here

**Redaction at write time.** An audit hook was recording raw command text to a
plaintext JSONL: 16 MB of it, containing a Discord webhook. The hook was working
exactly as designed. Nobody had asked what ends up *in* a command line — and a
deploy command routinely carries a token.

The fix is not to stop logging. It is to redact in place, keeping the shape:

```
echo "curl https://api.telegram.org/bot<redacted:telegram-bot-token:4e6c19f44cdb>/getMe"
```

The URL, the verb and the path survive — that is what makes a log worth keeping. The
value is gone, and the digest means you can still tell *"the same secret appeared four
times"* from *"four different secrets"* without holding any of them.

**A pre-commit scanner.** `git add -A` swept a hook debug log into a commit. It
happened to be clean. Three repos had zero pre-commit hooks between them, so nothing
would have caught it if it had not been.

**One pattern list.** This is the part worth the pack. A redactor and a log scanner
each kept their own list. Both were missing Telegram bot tokens. A scan reported
**ALL-CLEAR** while a live bot token sat in plaintext on disk — because the scanner
could not name what the redactor could not name.

> A pattern list is an **allowlist of things you remembered**. "No hits" only ever
> means "no hits for what I thought of".

So `secret_patterns.py` is the single list, and the `no-second-pattern-list` step
**fails** when a second copy drifts from it — the same way `hook-liveness` in the
`hooks` pack makes GUARD_DESIGN rule 1 runnable instead of aspirational.

## Contract

- `files/secret_patterns.py` is the **only** pattern list. Add shapes there; every
  consumer inherits them. It self-tests in both directions with synthetic specimens.
- `files/secret_precommit.py` installs as `.git/hooks/pre-commit`. It scans **staged
  files only** and reports path, line, pattern label and `sha256[:12]` — **never a
  value**, not even partially, in either direction.
- **Fail-closed.** An unreadable pattern file, a crashed scan, or an ambiguous result
  **blocks the commit**. This is the documented exception to GUARD_DESIGN rule 4: a
  secret pushed to a remote is irreversible, and rotation is the only real remedy.
- `git commit --no-verify` remains the override, deliberately. A guard nobody can
  escape is a guard they will uninstall.
- Allowances are **by `sha256[:12]` digest**, in `secret_scan_allow.txt` — never by
  path. Allowing a placeholder in a test fixture must not also allow a real credential
  that later lands in the same file.
- Blocked by name too: `.env`, `*.pem`, `*.key`, `id_rsa`, `audit.jsonl`,
  `history.jsonl`. `.env.example` / `.sample` / `.template` are exempt by design.
- Lines already carrying a `<redacted:…>` marker are not hits.

## Iron Laws

1. **Never emit or solicit any character of a secret** — no partials, no "last 4
   chars", in either direction. `sha256[:12]` is the only form a secret may be
   displayed in. A guard that asks for a secret to prove a secret has already lost.
2. **Redact before you truncate.** Truncating first can slice a secret in half and
   leave its head in the file, matching nothing on the next scan.
3. **One pattern list, imported — never copied.** Two lists is two blind spots that
   drift apart, and the shape that matters is always in the other file.
4. **A clean scan is evidence about coverage, not about absence.** Before reporting
   all-clear, say what the scan *could* have found and how many files it actually
   read. The all-clear that missed the Telegram token covered 11 of 39 log files
   **and** had no Telegram pattern — two independent holes in one sentence.
5. **Scrubbing is not rotation.** Removing a value from disk does not un-leak it. If
   it was ever real, rotate it.
6. **Every new pattern ships with a positive control** using a synthetic specimen.
   That is what caught the Telegram regex failing on `bot<token>` in an API URL:
   `\b` does not match between a letter and a digit.

## Anti-Patterns

❌ **Keeping a second copy of the pattern list "just for this consumer."** This is the
exact defect the pack exists for. Import it.

❌ **Reporting "no secrets found" without stating the scope.** Name the file count and
the shapes searched, or the sentence claims more than the scan did.

❌ **Allowing by path or directory** (`skip tests/`, `skip *.md`). A blanket surface
exemption on a guard whose false negative is irreversible is how the hole gets in.
Allow the specific **digest** you inspected.

❌ **Backing up the dirty file before scrubbing it.** A backup of a leaked credential
is a second copy of the leak, in a less-watched place. Verify the scrubbed output
completely — line count, structure, zero remaining matches, markers added == secrets
removed, every untouched line byte-identical — then replace atomically.

❌ **Deleting a log to remove three matches.** That throws away the whole audit trail
to fix 0.005% of it. Scrub in place; keep every line and every timestamp.

❌ **Making the scanner fail open "so it never blocks work."** Every other guard here
should fail open. This one must not — that is the whole point of it being separate.

❌ **Trying to defeat `--no-verify`.** It is git's design, and the escape hatch is
what keeps the guard installed.

## Related

- `packs/guardrails` — `credential_guard`, which blocks *reading* credential files.
  This pack is the write and commit directions of the same problem.
- `packs/hooks` — `GUARD_DESIGN.md`, especially **rule 7** (every token in a match
  class must carry the danger alone) and the corollary on pattern lists. Read it
  before editing `secret_patterns.py`.
- `packs/audit` — the audit-log hook whose raw-command logging motivated the
  redactor. Point its `_SECRET_PATTERNS` at `secret_patterns.py`; the
  `no-second-pattern-list` step checks that you did.
- `packs/windows-shell` — `windows_gotchas.md`, including the `\b`-vs-`(?<!\d)` and
  quote-masking traps hit while writing these patterns.
