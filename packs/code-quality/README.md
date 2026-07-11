# code-quality

**Close the gap between "Claude wrote code" and "the code actually works."**

### auto_format

PostToolUse(Write|Edit) — immediately after every file write, runs the project
formatter. Formatter is detected from file extension:

| Extension | Formatter |
|-----------|-----------|
| `.py` | `ruff format` → `black` → `autopep8` (first available) |
| `.ts` `.tsx` `.js` `.jsx` `.json` `.yaml` `.yml` | `prettier` (via npx or bunx) |
| `.md` | `prettier --prose-wrap preserve` |
| `.go` | `gofmt` |
| `.rs` | `rustfmt` |

Silently skips if no formatter is found for the extension. Never fails loudly —
a formatter error should not interrupt the write workflow.

Cited by Thomas Wiegold as the single **highest-ROI hook he ships**.

### stop_verify

Stop hook — before Claude can declare "done", runs the project's test suite and type
checker. Blocks (exit 2) if they fail. Project type is auto-detected from CWD:

| Marker | What runs |
|--------|-----------|
| `pytest.ini` / `pyproject.toml` | `python -m pytest -q -x` |
| `package.json` with `"typecheck"` script | `npm run typecheck` (or bun) |
| `package.json` with `"test"` script | `npm test --passWithNoTests` |
| `go.mod` | `go test ./...` |
| `Cargo.toml` | `cargo test --quiet` |

A per-session sentinel (`/tmp/stop_verify_<hash>.done`) means it only runs once per
directory per session — not on every turn. Set `STOP_VERIFY_SKIP=1` to bypass for a
turn (e.g. mid-refactor where tests are intentionally broken).

Closes the **"Claude says it's done but tests are red"** failure mode.

## Contract

- Installs both scripts at `~/.claude/hooks/`
- Registers both in `~/.claude/settings.json`
- Verifies `stop_verify` passes on a project with no test suite (shouldn't block where
  nothing is configured)

## Iron Laws

- `stop_verify` must be idempotent — running multiple `Stop` calls in one session only
  runs tests once (the sentinel handles this).
- `auto_format` fails open. A broken formatter config should not stop Claude from
  writing code; the user can fix formatting separately.

## Anti-Patterns

- ❌ Installing `stop_verify` on a project with a slow test suite without understanding
  the impact — it will add the full test runtime before every Stop event. Use
  `STOP_VERIFY_SKIP=1` or tune the project's test command to run only fast tests.
- ❌ Expecting `auto_format` to catch logic errors. It formats; it doesn't verify.
  Pair with `stop_verify`.

## Related packs

- [`audit`](../audit/) — auto_commit_wip gives per-turn rollback points to pair with
  stop_verify's "tests must pass before done"
- [`guardrails`](../guardrails/) — must run first
