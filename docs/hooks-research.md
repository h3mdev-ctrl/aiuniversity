# Claude Code Hooks — Best-in-Class Reference

> Research conducted July 2026. Sources listed at the bottom.

## What hooks are

Shell commands (or HTTP endpoints, or single-turn LLM prompts) wired into lifecycle
events in `.claude/settings.json` (or globally at `~/.claude/settings.json`). They fire
**deterministically** — unlike CLAUDE.md instructions which are probabilistic and can be
ignored under pressure. Exit code 0 = allow, exit code 2 = block (PreToolUse only),
stderr = message shown to the model.

As of mid-2026, Claude Code exposes 21+ lifecycle events:

`Setup`, `SessionStart`, `SessionEnd`, `InstructionsLoaded`, `ConfigChange`,
`CwdChanged`, `UserPromptSubmit`, `UserPromptExpansion`, `PreToolUse`,
`PermissionRequest`, `PermissionDenied`, `PostToolUse`, `PostToolUseFailure`,
`PostToolBatch`, `SubagentStart`, `SubagentStop`, `TaskCreated`, `TaskCompleted`,
`Stop`, `PreCompact`, `PostCompact`, `Notification`, `MessageDisplay`, `FileChanged`,
`WorktreeCreate`, `WorktreeRemove`, `Elicitation`, `ElicitationResult`.

**Key facts:**
- Only `PreToolUse`, `Stop`, `UserPromptSubmit`, `ConfigChange`, `WorktreeCreate`,
  `TaskCreated`, `TaskCompleted` can **block** (exit 2). `PostToolUse` cannot undo
  but can inject context.
- Timeout defaults: 30s for `UserPromptSubmit`, 600s for most others.
- Stdout from `SessionStart` and `UserPromptSubmit` hooks is automatically injected
  as model context.
- As of July 2026, `Notification` does NOT fire for rate-limit pauses (open issue:
  anthropics/claude-code #34817).

---

## Tier 1 — Widely cited, high signal-to-noise, broadly applicable

These appear in literally every curated list and collection. Ship these first.

---

### 1. Dangerous Bash Blocker

**Event:** `PreToolUse` (matcher: `Bash`)  
**What it does:** Regex-blocks `rm -rf /`, `rm -rf ~`, `rm -rf *`, `git push --force`
to main/master, `curl | bash`, `eval $(...)`, fork bombs, `chmod -R 777 /`.  
**Why:** The single most-cited hook across every collection. Enforces at the
deterministic layer what the model might accidentally do when told to "clean up" or
when a prompt injection tries to run destructive commands.  
**Sources:** paddo.dev, thomas-wiegold.com, karanb192/claude-code-hooks, official
Anthropic docs.

```bash
#!/bin/sh
python3 - <<'EOF'
import sys, json, re
data = json.load(sys.stdin)
cmd = data.get("input", {}).get("command", "")
patterns = [
    r"rm\s+-rf\s+[/~*]",
    r"git\s+push\s+.*(--force|-f)\s+.*(main|master)",
    r"curl\s+.*\|\s*(ba)?sh",
    r":\(\)\s*\{.*\}",           # fork bomb
    r"chmod\s+-R\s+777\s+/",
    r"eval\s+\$\(",
    r"git\s+(reset|checkout)\s+--hard\s+HEAD",
]
for p in patterns:
    if re.search(p, cmd):
        print(f"BLOCKED: dangerous command pattern matched: {p}", file=sys.stderr)
        sys.exit(2)
EOF
```

---

### 2. Credential / Secrets Blocker

**Event:** `PreToolUse` (matcher: `Bash|Read`)  
**What it does:** Blocks any tool call whose input matches patterns for AWS keys
(`AKIA`), OpenAI keys (`sk-`), GitHub tokens (`ghp_`), private key headers, JWT
tokens, or accesses `.env`/`.pem`/`.key`/`~/.ssh/`/`~/.aws/` paths.  
**Why:** Makes credential leakage structurally impossible rather than relying on model
behaviour. Works even under `--dangerously-skip-permissions`. One of the two hooks
every team ships first.  
**Sources:** slavaspitsyn/claude-code-security-hooks (7-layer defence),
karanb192/claude-code-hooks, JalelTounsi/claude-code-skills, official Anthropic docs.  
**Note:** Already shipped in aiuniversity's `guardrails` pack.

---

### 3. Auto-Format on File Write

**Event:** `PostToolUse` (matcher: `Edit|Write`)  
**What it does:** After every file write, runs the project formatter — `prettier` for
JS/TS/JSON/YAML/MD, `black`/`ruff` for Python, `gofmt` for Go — with autofix
enabled.  
**Why:** Eliminates an entire class of review comments. Zero token cost vs prompting
Claude to format. Thomas Wiegold specifically cites this as the **highest-ROI single
hook he ships**.  
**Sources:** thomas-wiegold.com, karanb192/claude-code-hooks, ayautomate.com 15-hook
list.

```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Write|Edit",
      "hooks": [{
        "type": "command",
        "command": "python3 -c \"\nimport sys, json, subprocess, os\ndata = json.load(sys.stdin)\nf = data.get('tool_input', {}).get('file_path', '')\nif not f or not os.path.exists(f): sys.exit(0)\next = f.rsplit('.', 1)[-1] if '.' in f else ''\nif ext in ('ts', 'tsx', 'js', 'jsx', 'json', 'yaml', 'yml', 'md'): subprocess.run(['npx', 'prettier', '--write', f], capture_output=True)\nelif ext == 'py': subprocess.run(['ruff', 'format', f], capture_output=True)\nelif ext == 'go': subprocess.run(['gofmt', '-w', f], capture_output=True)\n\""
      }]
    }]
  }
}
```

---

### 4. Stop Verification Guard

**Event:** `Stop`  
**What it does:** Before Claude is allowed to declare it's done, runs `tsc --noEmit`
and the test suite (or checks a `.claude/verified` sentinel file written by the last
test run). If either fails, returns exit 2 with an error message, forcing Claude back
into the loop to fix it.  
**Why:** Closes the gap between "Claude says it's done" and "it actually builds and
passes tests". Highest "why didn't I have this earlier" sentiment in the community.
Critical for autonomous/headless runs where you're not watching.  
**Sources:** ianymu/awesome-claude-code-hooks (verify-before-stop),
thomas-wiegold.com, ayautomate.com.

```bash
#!/bin/bash
# Run before Claude stops — blocks if build or tests fail
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [ -f "package.json" ] && grep -q '"typecheck"' package.json 2>/dev/null; then
    if ! npm run typecheck 2>/dev/null; then
        echo "TypeScript errors — fix before stopping" >&2
        exit 2
    fi
fi
if [ -f "package.json" ] && grep -q '"test"' package.json 2>/dev/null; then
    if ! npm test -- --passWithNoTests 2>/dev/null; then
        echo "Tests failing — fix before stopping" >&2
        exit 2
    fi
fi
if [ -f "pytest.ini" ] || [ -f "pyproject.toml" ]; then
    if ! python -m pytest -q --tb=no 2>/dev/null; then
        echo "Python tests failing — fix before stopping" >&2
        exit 2
    fi
fi
exit 0
```

---

### 5. Notification → Desktop / Slack / Discord

**Event:** `Notification`  
**What it does:** When Claude pauses waiting for input, fires an OS notification
(macOS: `osascript`, Linux: `notify-send`) or POSTs to a Slack/Discord webhook. Lets
you work on other things during long runs.  
**Why:** Extremely low-effort implementation, high quality-of-life gain for long
autonomous sessions. claude-code-toast has 16 stars, aily has 6.  
**Sources:** ithiria894/awesome-claude-code-hooks (claude-code-toast, aily),
ayautomate.com, official Anthropic docs.

```bash
# macOS
MSG=$(echo "$HOOK_NOTIFICATION_MESSAGE" | head -c 100)
osascript -e "display notification \"$MSG\" with title \"Claude Code\" sound name \"Glass\""

# Linux
notify-send "Claude Code" "$MSG"

# Discord/Slack webhook — same pattern used in nexus post-commit hook
python3 -c "
import os, json, urllib.request
msg = os.environ.get('HOOK_NOTIFICATION_MESSAGE', 'Claude needs input')[:200]
url = os.environ.get('DISCORD_WEBHOOK_URL', '')
if url:
    data = json.dumps({'content': f'**Claude needs input:** {msg}'}).encode()
    req = urllib.request.Request(url, data=data,
          headers={'Content-Type': 'application/json', 'User-Agent': 'curl/8.7.1'})
    try: urllib.request.urlopen(req, timeout=5)
    except: pass
"
```

---

### 6. PostCompact — Re-inject Critical Context

**Event:** `PostCompact`  
**What it does:** After the transcript is compacted (summarised), injects a reminder
to re-read `CLAUDE.md`, `AGENTS.md`, or any project rules file. Prevents
**post-compaction rule amnesia** where the model forgets constraints it had been
following.  
**Why:** Solves a real observed failure mode in long sessions. 34-star repo,
widely cited.  
**Sources:** ithiria894/awesome-claude-code-hooks (post_compact_reminder, 34 stars),
hidekazu-konishi.com.

```json
{
  "hooks": {
    "PostCompact": [{
      "hooks": [{
        "type": "command",
        "command": "echo 'Context was just compacted. Re-read CLAUDE.md and any AGENTS.md files in the project before proceeding. Your rules and constraints are unchanged.'"
      }]
    }]
  }
}
```

---

### 7. SessionStart — Inject Project Context

**Event:** `SessionStart`  
**What it does:** On session open/resume, stdout of the hook is injected as context
into the model. Used to load git status, last 3 commits, open TODOs, active branch,
env var state, and project-specific reminders.  
**Why:** Replaces fragile "always read X first" prompts in CLAUDE.md with a
deterministic context injection. Works on `startup`, `resume`, and `compact`
sub-events.  
**Sources:** disler/claude-code-hooks-mastery (`session_start.py`), ayautomate.com,
hidekazu-konishi.com.

```bash
#!/bin/bash
echo "=== Session Context $(date '+%Y-%m-%d %H:%M') ==="
echo "Branch: $(git branch --show-current 2>/dev/null || echo 'not a git repo')"
echo "Last commits:"
git log --oneline -3 2>/dev/null || true
echo "Modified files:"
git status --short 2>/dev/null | head -10 || true
echo "========================================"
```

---

### 8. Audit Log — JSONL Tool Call Ledger

**Event:** `PostToolUse` (no matcher = all tools)  
**What it does:** Appends `{timestamp, tool_name, file_path, command, exit_code}` to
`~/.claude/audit.jsonl` for every tool call. Enables post-hoc queries: "what did
Claude touch during the overnight refactor?"  
**Why:** Cited repeatedly for team/enterprise use where you need to know exactly what
an autonomous session changed. Tamper-evident when written to append-only storage.  
**Sources:** thomas-wiegold.com, ayautomate.com (tool-call logger),
ithiria894/awesome-claude-code-hooks.

```python
#!/usr/bin/env python3
import sys, json, os
from datetime import datetime, timezone

data = json.load(sys.stdin)
entry = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "tool": data.get("tool_name"),
    "input": data.get("tool_input", {}),
    "exit_code": data.get("tool_response", {}).get("exit_code"),
}
log_path = os.path.expanduser("~/.claude/audit.jsonl")
os.makedirs(os.path.dirname(log_path), exist_ok=True)
with open(log_path, "a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

---

### 9. Auto-Commit WIP on Stop

**Event:** `Stop`  
**What it does:** After each Claude turn completes, runs `git add -A && git commit -m
"wip: claude turn [skip ci]"` so every turn has a rollback point. GitButler's hook
variant creates per-session branches for even finer granularity.  
**Why:** Eliminates "Claude broke something and I can't get back" regrets in long
autonomous runs. The `[skip ci]` suffix prevents spurious CI triggers.  
**Caution:** Don't use on the main branch. Pair with the branch protection hook.  
**Sources:** ayautomate.com, GitButler claude-code hooks integration.

---

### 10. Prompt Injection Scanner

**Event:** `PostToolUse` (matcher: `Bash|Read|WebFetch`)  
**What it does:** After reading external content (web pages, files, API responses),
scans for prompt injection patterns — "ignore previous instructions", "you are now",
base64-encoded payloads, Unicode directional overrides. Two-stage: fast regex first,
local LLM (Ollama) escalation for uncertain cases. CloneGuard uses an ONNX embedding
classifier — not exploitable via the injection itself.  
**Why:** Addresses the real threat surface for agents reading untrusted content from
the web, emails, or PDFs.  
**Sources:** ithiria894 list (Lasso Claude-Hooks 50+ patterns; claude-injection-guard;
CloneGuard ONNX variant), slavaspitsyn/claude-code-security-hooks.

---

## Tier 2 — Solid, more situational

### 11. Protect Config Files / Self-Modification Guard

**Event:** `PreToolUse` (matcher: `Write|Edit`)  
**What it does:** Blocks writes to `.env`, `.env.*`, `settings.json`,
`~/.claude/settings.json`, `*.pem`, `*.key`. slavaspitsyn's variant also blocks edits
to `~/.claude/hooks/` itself — **preventing the model from disabling its own guards**.  
**Sources:** paddo.dev, slavaspitsyn/claude-code-security-hooks.

---

### 12. Branch Protection Guard

**Event:** `PreToolUse` (matcher: `Bash`)  
**What it does:** Blocks any git operation targeting `main` or `master` (commits,
force-pushes, resets). Enforces working-branch discipline regardless of what the
prompt says.  
**Sources:** wangbooth/Claude-Code-Guardrails, karanb192/claude-code-hooks,
ChrisWiles/claude-code-showcase.

---

### 13. Auto-Stage on Edit

**Event:** `PostToolUse` (matcher: `Write|Edit`)  
**What it does:** `git add "$FILE_PATH"` after every write so git status stays
current and diff-based hooks have accurate input.  
**Sources:** karanb192/claude-code-hooks.

---

### 14. Cost Tracker

**Event:** `Stop`  
**What it does:** Reads token usage from the session transcript, appends
`{date, session_id, model, input_tokens, output_tokens, estimated_cost_usd}` to
`~/.claude/costs.csv`. Some variants alert to Slack when a session crosses a
threshold.  
**Sources:** ayautomate.com, ithiria894 list, disler/claude-code-hooks-mastery.

---

### 15. Dependency Vulnerability Check

**Event:** `SessionStart`  
**What it does:** Runs `npm audit --audit-level=high` or `pip-audit` at session open
and surfaces any critical CVEs as injected context so the model is aware from the
first message.  
**Sources:** ayautomate.com.

---

### 16. PreCompact — Transcript Backup

**Event:** `PreCompact`  
**What it does:** Copies the full transcript to
`~/.claude/transcripts/YYYY-MM-DD-HH.jsonl` before compaction destroys it. Dead
simple, irreversible data otherwise.  
**Sources:** disler/claude-code-hooks-mastery (`pre_compact.py`), claudefa.st.

---

### 17. UserPromptSubmit — Per-Prompt Context Injection

**Event:** `UserPromptSubmit`  
**What it does:** Before the model sees each user message, appends relevant
context — scans the prompt for file names and injects their current content, adds
"today is DATE, branch is X" boilerplate, or rejects prompts matching a blocklist.  
**Note:** 30-second default timeout (shorter than other events). Stdout is injected;
exit 2 blocks the prompt entirely.  
**Sources:** disler/claude-code-hooks-mastery, hidekazu-konishi.com.

---

### 18. Auto-TODO Harvester

**Event:** `PostToolUse` (matcher: `Write|Edit`)  
**What it does:** After every file write, greps for `TODO:`, `FIXME:`, `HACK:`
comments and appends new ones (with file+line) to `TODO.md`, deduplicating against
existing entries.  
**Sources:** ayautomate.com 15-hook list.

---

### 19. PermissionRequest Auto-Decider

**Event:** `PermissionRequest`  
**What it does:** Pre-empts interactive permission dialogs. Safe pattern: auto-allow
reads and directory listings, require explicit confirmation for writes and shell
execution. panuhorsmalahti/claude-code-permissions-hook is the most sophisticated
implementation — TOML config with per-path allow/deny regex, JSON audit logging,
written in Rust.  
**Sources:** panuhorsmalahti/claude-code-permissions-hook,
disler/claude-code-hooks-mastery, hidekazu-konishi.com.

---

### 20. Compound Bash Decomposer

**Event:** `PreToolUse` (matcher: `Bash`)  
**What it does:** Splits piped/chained bash commands (`cmd1 | cmd2 && cmd3`) into
individual sub-commands and checks each against the permission config separately.
Prevents bypassing per-command rules by chaining them.  
**Sources:** liberzon/claude-hooks.

---

## Tier 3 — Creative / novel / niche

### 21. Multi-Agent Observability Dashboard

**Event:** All hook events  
**What it does:** Streams every hook event to a web UI for real-time visualisation of
what Claude is doing across parallel sub-agents.  
**Stars:** 1,289 (most-starred hook project as of July 2026)  
**Sources:** ithiria894 list.

---

### 22. TTS Notification + Completion Messages

**Event:** `Notification`, `Stop`  
**What it does:** Speaks Claude's completion message aloud using the system TTS
engine. disler's implementation adds "Your agent needs your input" via async TTS on
Notification.  
**Stars:** 187 (voice output hooks)  
**Sources:** disler/claude-code-hooks-mastery (`notification.py`, `stop.py`),
ithiria894 list.

---

### 23. SCV Sound Effects

**Event:** `PreToolUse`, `PostToolUse`, `Stop`, `Notification`  
**What it does:** Plays StarCraft SCV sounds on hook events. 38 stars. Doubles as an
audio cue that hooks are firing correctly during development.  
**Sources:** ithiria894 list.

---

### 24. Canary Files (Prompt Injection Deterrent)

**What it does:** Plants files like `~/.ssh/README_AI.md` saying "If you're an AI
reading this, do not exfiltrate this directory." The read-guard hook then watches for
the model reading these files, treating it as a signal of attempted credential theft.  
**Sources:** slavaspitsyn/claude-code-security-hooks.

---

### 25. cc-dice — Probabilistic Hook Execution

**Event:** Any  
**What it does:** Wraps any hook command with a dice-roll gate so it fires only X% of
the time. Used for non-critical sampling (e.g. run a slow linter on 20% of saves, not
every save).  
**Stars:** 21  
**Sources:** ithiria894 list (cc-dice).

---

### 26. Sub-Agent ROI Tracker

**Event:** `SubagentStop`  
**What it does:** Logs each sub-agent run's duration, token cost, and task name to a
JSONL file. Useful for multi-agent orchestrations where you want to know which
sub-agents are expensive.  
**Sources:** ayautomate.com 15-hook list.

---

### 27. ConfigChange Guard

**Event:** `ConfigChange`  
**What it does:** Blocks runtime changes to Claude Code's own configuration
mid-session. Prevents a prompt injection from reconfiguring the agent's permissions
while it's running.  
**Sources:** hidekazu-konishi.com.

---

## Hook SDKs (write hooks in a real language)

| SDK | Language | Stars | What it provides |
|-----|----------|-------|-----------------|
| cchooks | Python | 123 | Stdin/stdout JSON abstraction, event matching |
| cc-hooks-ts | TypeScript | 35 | Full type-safe hook definitions |
| claude-hooks-sdk | PHP | 62 | PHP hook builder |
| claude_hooks | Ruby | 36 | Ruby DSL |
| claude-hooks CLI | Any | 73 | Add/remove/toggle hooks without editing JSON |

---

## What aiuniversity already ships

| Hook | Pack | Status |
|------|------|--------|
| Credential / secrets blocker | `guardrails` | ✅ default |
| Recon-before-build guard | `guardrails` + `hooks` | ✅ opt-in |
| Session-end guard | `guardrails` + `hooks` | ✅ opt-in |

## Gaps and pack opportunities

| Gap | Suggested pack | Priority |
|-----|---------------|----------|
| Dangerous bash blocker + branch protection | `safety` | High — most universal |
| Auto-format on write | `code-quality` | High — highest ROI per Thomas Wiegold |
| Stop verification guard | extend `guardrails` or new `quality-gate` | High |
| PostCompact re-inject | extend `guardrails` | Medium — real failure mode |
| Notification → desktop / Discord | `notifications` | Medium — high QoL |
| Audit log (JSONL tool ledger) | extend `guardrails` or `audit` | Medium |
| SessionStart context injector | `context` | Medium |
| Prompt injection scanner | extend `guardrails` or `security` | Medium |
| PreCompact transcript backup | `context` or `audit` | Low |

---

## Most-cited hooks by community signal

1. **Block dangerous bash** — appears in every single collection
2. **Auto-format on write** — second most universal
3. **Credential/secret scanner** — especially cited for team use
4. **Stop verification guard** — highest "why didn't I have this earlier" sentiment
5. **PostCompact re-inject** — solves a specific painful failure mode in long sessions

---

## Sources

- [awesome-claude-code-hooks (ithiria894)](https://github.com/ithiria894/awesome-claude-code-hooks) — most comprehensive curated list, 1,289-star observability dashboard
- [10 Best Claude Code Hooks — ayautomate.com](https://www.ayautomate.com/blog/best-claude-code-hooks)
- [15 Best Claude Code Hook Examples — ayautomate.com](https://www.ayautomate.com/blog/best-claude-code-hooks-examples)
- [awesome-claude-code-hooks (ianymu)](https://github.com/ianymu/awesome-claude-code-hooks) — verify-before-stop
- [Claude Code Hooks: Guardrails That Actually Work — paddo.dev](https://paddo.dev/blog/claude-code-hooks-guardrails/)
- [claude-code-hooks-mastery (disler)](https://github.com/disler/claude-code-hooks-mastery) — session_start.py, pre_compact.py, TTS hooks
- [Claude Code Hooks Complete Guide — hidekazu-konishi.com](https://hidekazu-konishi.com/entry/claude_code_hooks_complete_guide.html) — ConfigChange, WorktreeCreate, PermissionRequest patterns
- [claude-code-security-hooks (slavaspitsyn)](https://github.com/slavaspitsyn/claude-code-security-hooks) — 7-layer defence, canary files, self-modification guard
- [Claude Code Hooks: From Linting to Hardened Workflows — thomas-wiegold.com](https://thomas-wiegold.com/blog/claude-code-hooks/) — highest-ROI analysis, auto-format claim
- [awesome-claude-code (hesreallyhim)](https://github.com/hesreallyhim/awesome-claude-code)
- [claude-code-hooks (karanb192)](https://github.com/karanb192/claude-code-hooks) — branch protection, auto-stage
- [Claude Code Hooks: Complete Guide to All 12 Lifecycle Events — claudefa.st](https://claudefa.st/blog/tools/hooks/hooks-guide) — pre_compact transcript backup
- [Hooks reference — Claude Code official docs](https://code.claude.com/docs/en/hooks)
- [Claude-Code-Guardrails (wangbooth)](https://github.com/wangbooth/Claude-Code-Guardrails)
- [claude-code-permissions-hook (panuhorsmalahti)](https://github.com/panuhorsmalahti/claude-code-permissions-hook) — Rust TOML-config PermissionRequest handler
- [liberzon/claude-hooks](https://github.com/liberzon/claude-hooks) — compound bash decomposer
