# gbrain-windows

Gets **gbrain installed, connected, and actually LIVE** on Windows — then makes it
*habitual*. Grounded in real footguns: the Supabase pooler-URL trap (the direct
host uses IPv6 and times out on Windows) and the "wasn't even activated" MCP gap
(it looked set up, it wasn't, nothing said so). Every check runs a real executable
(`gbrain` / `claude`) so it works under cmd.exe, not just bash.

Choose where your brain lives with `--variant`: **local** (PGLite file, no signup —
default) or **supabase** (hosted, syncs across machines).

See [pack-structure.md](../../docs/pack-structure.md) for the section conventions.

## Contract

- **`install`** confirms `gbrain --version` runs (PATH includes `~/.bun/bin`).
- **`brain-reachable-{local,supabase}`** — one variant-gated check that covers
  "config valid" + "database connects".
- **`mcp-registered`** — confirms `claude mcp list` shows gbrain, i.e. Claude can
  actually call its tools. This is the check for the failure that used to be silent.
- **`activation-exam`** runs a real question through the full pipeline (embeddings +
  DB + ranking) — proving gbrain is genuinely live, not merely installed.
- **`usage-discipline`** writes a usage block into `CLAUDE.md` so Claude USES the
  brain, and **offers the user a cadence choice** (not a silent default): **lean**
  (search-first + capture-what-matters, ~5–15k tokens/session) vs **eager** (scan
  every message, ~3–5× the tokens for maximal capture). `gbrain_growth_path.md` shows
  what the hub becomes as you climb (entity graph → eager → ingest a corpus → code
  intelligence → automation) + the full cost table.

## Iron Laws

- **Check usability, not a score.** The pack deliberately does NOT gate on
  `gbrain doctor`'s overall status — on a working machine doctor can report
  "unhealthy" from content-sync noise while gbrain is perfectly usable. Every step
  tests a real capability.
- **Installed ≠ activated ≠ used.** Three distinct gates: the binary runs, the MCP
  is registered so Claude can reach it, and a usage discipline tells Claude to
  actually use it. Skipping any leaves gbrain quietly idle.
- **Windows-real checks.** Checks shell out to real executables so they pass under
  cmd.exe (the runner's shell on Windows), not just under bash.
- **On Supabase, use the POOLER URL.** The direct `db.<project>.supabase.co` host
  is IPv6 and times out on most Windows networks — the number-one setup failure.

## Anti-Patterns

- ❌ **Gating setup on `gbrain doctor` being fully green.** Content-sync warnings
  are noise; they'd fail a perfectly usable brain.
- ❌ **Stopping at "installed".** A brain Claude can't reach (no MCP registration)
  or is never told to use (no usage discipline) compounds nothing.
- ❌ **Using the direct Supabase host on Windows.** IPv6 timeout. Pooler only.
- ❌ **Shipping the eager usage cadence to everyone.** Every-message capture is a
  per-turn token tax most users don't want — lean is the default, eager is opt-in.
- ❌ **Running a nightly LLM deep-extract on an unreliable local 8B.** Structural
  dream is free + model-free; the extract needs a reliable chat model (see
  `files/dream_cycle_windows.md`). You do NOT need codex.

## Related packs

- [`memory`](../memory/) — the plain-files memory core; goes hand-in-hand with
  gbrain (searchable layer) but neither depends on the other.
- [`obsidian-wiki`](../obsidian-wiki/) — a wiki gbrain can ingest for semantic
  search; part of the same KNOWLEDGE branch.
- [`foundation`](../foundation/) — threads gbrain-windows as `layer-4-capabilities`.
