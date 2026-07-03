# Memory -- EXAMPLE of a mature index (learn the STRUCTURE from this, not the content)

> This is a worked example based on a real, heavily-used memory system. Copy the
> shape, replace the content. It shows the three moves that keep a large memory
> usable while the always-loaded index stays small:
>   1. **Intent-phrased RESOLVER rows** -- "when you're about to X", not a topic.
>   2. **Sections** -- always-on guardrails, and a user section, loaded every time.
>   3. **A ROUTER** that hands whole domains off to Tier-2 INDEX_*.md files, so
>      this index never has to list them itself.

## RESOLVER -- intent -> memory

### Always-on guardrails

| When you're about to... | Consult |
|---|---|
| quote a stale claim or row count from a memory file | [reference_memory_freshness](reference_memory_freshness.md) |
| quote library / framework syntax (APIs, SDK calls, config) | [reference_context7_mcp](reference_context7_mcp.md) |
| propose a fix, claim a tool's behaviour, or state a root cause | [feedback_verify_against_source](feedback_verify_against_source.md) |
| take a known-quirky, OS-specific action | [feedback_check_memory_first](feedback_check_memory_first.md) |
| reference today's date / a weekday / any temporal claim | [feedback_ground_temporal_claims](feedback_ground_temporal_claims.md) |
| write a new memory file | [feedback_skillify_memory](feedback_skillify_memory.md) |

### The user (always loaded)

| When you're about to... | Consult |
|---|---|
| speak to the user / set tone + depth | [user_profile](user_profile.md), [user_technical_level](user_technical_level.md) |
| estimate scope / timeline / capacity | [user_velocity](user_velocity.md), [feedback_no_timeline_inflation](feedback_no_timeline_inflation.md) |
| display a date / handle timezone | [feedback_timezone_default](feedback_timezone_default.md) |
| offer a multi-option menu | [feedback_ask_dont_stall](feedback_ask_dont_stall.md) |
| wrap up / close out a session | [feedback_wrap_up](feedback_wrap_up.md) |

## ROUTER -- open the matching Tier-2 sub-index BEFORE working in that domain

These tables are NOT loaded every session. When a task enters a domain below,
open the linked INDEX_*.md first -- it holds the full intent->memory routing for
that domain, so THIS index never has to carry it.

| When the task touches... | Open (Tier-2, on demand) |
|---|---|
| shipping / PR / deploy / CI / cron / worktrees | [INDEX_shipping.md](INDEX_shipping.md) |
| the OS's quirks -- paths / shell / encoding / subprocess | [INDEX_windows.md](INDEX_windows.md) |
| credentials / hooks / MCP / plugins / tool setup | [INDEX_tooling.md](INDEX_tooling.md) |
| a specific project subsystem or strategy | [INDEX_project.md](INDEX_project.md) |

## Catalog

The full alphabetical file list lives in `CATALOG.md` (opened on demand), so this
always-loaded index stays a thin map. Durable project-state files are catalogued
there too -- never inline them here.

---

> Why this scales: the always-loaded cost is just the RESOLVER + ROUTER above (a
> map). Everything else (domain detail, the full file list) is Tier-2 -- present,
> reachable, but only loaded when the situation calls for it. When a domain's
> rows pile up here, that's the signal to spin them out into a new INDEX_*.md and
> replace them with a single router row.
