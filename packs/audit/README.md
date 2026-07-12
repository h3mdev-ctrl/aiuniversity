# audit

**Observability, notification, and rollback safety for autonomous sessions.**

### tool_audit_log

PostToolUse on all tools — appends every tool call to `~/.claude/audit.jsonl`:

```json
{"ts":"2026-07-11T14:30:00Z","tool":"Write","file":"src/api.py","cwd":"/project"}
{"ts":"2026-07-11T14:30:01Z","tool":"Bash","cmd":"pytest -q","exit_code":0,"cwd":"/project"}
```

Append-only, never truncated. Rotate manually. Answers: "what did the overnight
autonomous session actually touch?" Query with `grep`, `jq`, or any JSONL reader.

### notify_discord

Notification hook — when Claude pauses waiting for user input, POSTs a message to
a Discord webhook. Lets you walk away during long autonomous sessions and get pinged
when Claude needs you.

**Requires:** `CLAUDE_DISCORD_NOTIFY_URL` environment variable (Discord webhook URL).
Set in `~/.claude/settings.json` under the `env` key, or in your shell profile.
No-ops silently if the env var is not set — safe to install on every machine.

**Note:** Uses `User-Agent: curl/8.7.1` — required because Discord CDN (Cloudflare)
blocks requests with Python's default urllib user-agent with HTTP 403 error 1010.

### auto_commit_wip

Stop hook — after each Claude turn, if the current branch has uncommitted changes,
stages everything (`git add -A`) and commits:

```
wip: claude turn [skip ci]
```

Gives a rollback point after every turn in long autonomous sessions. The `[skip ci]`
suffix prevents CI from triggering on WIP commits.

**Guards:**
- Only fires on non-protected branches (default pattern blocks main/master/production/staging)
- No-ops outside a git repo
- Set `AUTO_COMMIT_WIP=0` to skip for a turn (e.g. you want to curate the commits)
- Set `AUTO_COMMIT_BRANCH_PATTERN` to override the branch filter regex

## Contract

- Installs three scripts at `~/.claude/hooks/`
- Registers all three in `~/.claude/settings.json`
- Verifies: audit log writes a JSONL entry; auto_commit_wip no-ops gracefully outside git

## Iron Laws

- `tool_audit_log` must NEVER fail loudly — a write error to the audit log should not
  disrupt the main workflow. It wraps all disk I/O in `try/except`.
- `notify_discord` must NEVER block — notification failure is not a reason to prevent
  Claude from responding. It times out after 5s and swallows all errors.
- `auto_commit_wip` only fires on non-protected branches. Verify your branch before
  installing if you work directly on main.

## Anti-Patterns

- ❌ Using `auto_commit_wip` on main/master — the default branch filter blocks this,
  but double-check if you've overridden `AUTO_COMMIT_BRANCH_PATTERN`.
- ❌ Setting `CLAUDE_DISCORD_NOTIFY_URL` to a webhook with rate limits you haven't
  checked — high-activity sessions can fire many Notification events.

## Related packs

- [`code-quality`](../code-quality/) — `stop_verify` pairs naturally with
  `auto_commit_wip` (tests pass → commit the passing state)
- [`guardrails`](../guardrails/) — must run first
