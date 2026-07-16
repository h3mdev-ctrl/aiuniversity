# `gbrain autopilot` silently never runs anything on Windows -- diagnose + fix

> Grounded in a real find (gbrain 0.42.53.0, Windows 11, git-bash): `gbrain
> autopilot` (and `gbrain autopilot --install`) starts, logs "Autopilot
> starting", and appears fine -- but **every job it dispatches sits in
> `waiting` forever.** No sync, no embed, no dream cycle, structural or not.
> This is a DIFFERENT bug from the `propose_takes`/Anthropic trap covered in
> `dream_cycle_windows.md` -- this one blocks the free, structural, model-free
> half too, because it breaks the worker that runs ALL jobs, not just the LLM
> ones.

## The symptom (how you'll notice this)

- `gbrain autopilot` (foreground) or the installed daemon runs, but nothing
  ever changes: sources stay stale, `gbrain doctor` keeps repeating the same
  "N unresolved sync failures" / "source X last synced Nd ago" warnings no
  matter how many cycles pass.
- `gbrain jobs list --status waiting` (or the equivalent MCP `list_jobs` call)
  shows jobs sitting `waiting` with `attempts_made: 0` for hours or days --
  including jobs created long before your most recent restart.
- Manually running `gbrain sync --all` or `gbrain extract --stale` **works
  fine** -- this is specifically an autopilot/background-worker problem, not
  a general gbrain problem. That contrast is the tell: if manual commands
  work but the daemon does nothing, look here first.

## Confirm the root cause

Run autopilot in the foreground (not `--install`, so you see the raw log) and
read the first 10-15 lines:

```bash
gbrain autopilot --repo <your-brain-repo-path> --interval 300
```

Look for this exact line:

```
[autopilot] worker spawn failed (async): ENOENT: no such file or directory, uv_spawn '<some path with no extension>'
```

If you see that, the diagnosis is confirmed: autopilot resolved a path for
its own CLI binary (to spawn as a child worker process) that doesn't
actually exist on disk, so the worker process never starts and every job it
queues just sits there forever with nothing to drain it.

### Why this happens (for your own understanding, not required to fix it)

Autopilot finds its own CLI path by shelling out to `which gbrain` and
trusting the output directly as something it can hand straight to a raw
process-spawn call (no shell involved on that second step). On Windows, if
`which` resolves through git-bash/MSYS's own `which.exe` (very common --
anyone with Git for Windows installed has this on PATH), it prints a
**POSIX-style path** like `/c/Users/you/.bun/bin/gbrain`, with **no file
extension**. Two things go wrong with that string for a raw Windows process
spawn:

1. Windows doesn't understand `/c/...` paths -- it needs `C:\...` or `C:/...`.
2. Even a converted `C:/Users/you/.bun/bin/gbrain` (no extension) still
   doesn't exist -- the real file on disk is `gbrain.exe`.

A shell (bash, cmd.exe) would auto-resolve either of these gaps for you when
you type a bare command. A raw, non-shell process spawn (what a worker
supervisor uses so it can track the child's exact PID) does neither -- it
needs the literal, correct, existing path.

## Fix path A -- you have a local gbrain source checkout

If you cloned `gbrain` yourself to build or contribute to it (not just
`bun install -g`'d the published package), you can patch this directly.

1. Find `resolveGbrainCliPath()` in `src/commands/autopilot.ts`. It currently
   does roughly:
   ```ts
   const which = execSync('which gbrain', {...}).trim();
   if (which) return which;
   ```
2. Add a small helper that verifies the path is actually spawnable before
   trusting it, and on `win32` translates the POSIX-style path and probes
   for the real extension:
   ```ts
   function resolveSpawnablePath(rawPath: string): string | null {
     if (existsSync(rawPath)) return rawPath;
     if (process.platform !== 'win32') return null;

     const posixDrive = rawPath.match(/^\/([a-zA-Z])\/(.*)$/);
     const winStyle = posixDrive ? `${posixDrive[1].toUpperCase()}:/${posixDrive[2]}` : rawPath;

     for (const candidate of [winStyle, ...['.exe', '.bunx', '.cmd'].map((ext) => `${winStyle}${ext}`)]) {
       if (existsSync(candidate)) return candidate;
     }
     return null;
   }
   ```
3. Call it around the `which` result instead of trusting the raw string:
   ```ts
   const which = execSync('which gbrain', {...}).trim();
   if (which) {
     const spawnable = resolveSpawnablePath(which);
     if (spawnable) return spawnable;
   }
   ```
4. Verify:
   - `bun run typecheck` -- should stay clean (no new errors).
   - Then the REAL proof, not just "it compiles" -- clear any stale
     `~/.gbrain/autopilot.lock` (delete it if the PID inside is no longer
     running -- check with `tasklist /FI "PID eq <pid>"` on Windows or
     `ps -p <pid>` elsewhere), then run `gbrain autopilot --repo <path>
     --interval 300` again and confirm the log now shows
     `[autopilot] Minions worker spawned (pid: <a real number>, ...)` instead
     of the ENOENT failure, and that a previously-`waiting` job's status
     flips to `completed` within that run (check with
     `gbrain jobs list --status completed` or list a specific job by id).
     A clean typecheck proves the code compiles; only a job actually
     transitioning to `completed` proves the fix works.

## Fix path B -- you installed the published package (no source to patch)

Most recipients will be in this position. You can't edit a compiled/linked
binary, so don't fight the daemon -- route around it until the fix ships
upstream:

1. **Don't rely on `gbrain autopilot --install`** for now. It'll silently do
   nothing on an affected install, and because it doesn't error loudly,
   you'll only notice via the stale-sync symptoms above -- easy to miss.
2. **Get the same value with a scheduled task instead.** Everything
   autopilot's structural half does for you, you can do directly and it
   works today regardless of this bug:
   ```bash
   gbrain sync --all --parallel 4 --workers 4 --skip-failed
   gbrain extract --stale
   ```
   Wire those two lines into a Windows Task Scheduler job (a `.ps1` or
   `.bat` on a daily/nightly trigger) instead of the autopilot daemon. This
   covers sync freshness + link/timeline extraction -- the free, model-free
   majority of what dream/autopilot would otherwise give you. See
   `dream_cycle_windows.md` for the LLM deep-extract half, which has its own
   separate (unrelated) Windows considerations.
3. **Re-check after any gbrain upgrade.** Run `gbrain autopilot --repo
   <path> --interval 300` in the foreground for ~30 seconds after upgrading
   and look for the same `worker spawn failed` line. Once it's gone
   upstream, you can switch to the real `--install` daemon and retire the
   scheduled-task workaround.

## Bottom line

If `gbrain doctor` or the status snapshot keeps reporting stale sources and
`cycle.last_full: null` no matter how long autopilot has supposedly been
running, don't assume it's a config or content problem -- check the
autopilot foreground log for `worker spawn failed ... ENOENT ... uv_spawn`
first. On Windows this is a spawn-path bug, not a you-did-something-wrong
problem, and it has a clear source-level fix (path A) or a zero-source
workaround that works today (path B).
