# episodes

Keeps a structured record of **failed or non-obvious attempts**: what the task
was, what was tried, whether it failed, why, and what fixed it. A small hook then
brings the right one back **before** the same approach is tried again.

Every record is one JSON line in `<CLAUDE_HOME>/state/episodes.jsonl`
(`CLAUDE_HOME` defaults to `~/.claude`). An episode has these fields:
`{id: ep-NNNN, ts, who, task, tried, outcome: fail|partial|success, why, fix, tags}`.

See [pack-structure.md](../../docs/pack-structure.md) for the section conventions
this README follows.

## Why episodes, when you already have memory notes

A memory note holds the **general lesson**, for example "validate every patch
anchor before writing any file". That kind of rule changes behaviour, but it
drops the details: which file it was, what the symptom looked like, what the
misleading first fix was. An episode keeps those details:

```
[ep-0007 | 2026-03-14 | fail] config_loader.py:88 rejects the new schema
    tried: bumped the schema version only
    why:   the loader caches the old schema under _SCHEMA_CACHE
    fix:   clear _SCHEMA_CACHE on version change
```

The two stores work together. The episode is the evidence and the note is the
rule. If the same kind of episode shows up twice, write the lesson as a note.

## Why recall matches on identifiers, not prose

The recall hook runs on **every** prompt. It can't wait until you ask "did we hit
this before?", because by then you have already repeated the approach. A hook
that runs on every prompt has to stay quiet most of the time, so it matches on
**identifiers**: tokens containing a digit, `_`, `.`, `/` or `:`, such as
`config_loader.py`, `_SCHEMA_CACHE`, `v1.4.2` or `parser.py:344`.

Ordinary English overlaps by accident. "The build keeps failing" shares words
with half the episodes you will ever log. An identifier only overlaps when you
are working on the same thing again. In practice, "have we been here before?"
almost always comes down to one exact token.

So the hook calls `search(prompt, k=2, require_ident=True)`. With that flag, a
match on words alone never fires. It injects at most 2 episodes, inside a
`<system-reminder>` that says they may be stale. An explicit
`episodes.py --search` from a person is looser: two distinctive shared words are
enough there, because someone chose to look.

## Why the hook has a branch trace

A hook has to **fail open**: a bug in it must never block your prompt. That means
it swallows its own errors. The integration this pack was ported from had a
`NameError` inside its search branch. The error went into `except: pass` for
three weeks. The hook still ran and exited 0, and the health checks showed
HEALTHY the whole time, because they checked that the hook ran and never checked
that the recall branch did.

With `EPISODES_TRACE=1`, the hook prints one stderr line for each branch that
actually ran, such as `trace: episodes.search ran, 1 hits`. A swallowed error
shows up as `trace: EXCEPTION NameError: ...`. The `--probe` check requires that
trace line. The probe is therefore proof that the recall branch ran, not just
that the hook was installed.

## Contract

- **Append-only, never rotated.** `--log` appends one JSON line with the next
  `ep-NNNN` id. Nothing ever rewrites or trims the store.
- **Required fields are enforced.** `--log` refuses an empty task, tried or why,
  and any `--outcome` other than fail, partial or success.
- **Secrets are refused on write.** A value that looks like a credential (API
  key, token, private key, `password=...`) makes `--log` fail. The error names
  the field and never repeats the value. Episodes are replayed into future
  prompts, so a stored secret would leak every time it matched.
- **Recall needs an identifier match.** A prompt that shares only ordinary words
  with an episode injects nothing. At most 2 episodes are injected, wrapped in a
  stale-warning system-reminder. An episode can't close that wrapper early.
- **The hook always exits 0.** Null, a number, a bare string, invalid JSON or an
  empty stdin all produce exit 0 and no output.
- **Install is idempotent and additive.** It adds exactly one UserPromptSubmit
  entry, keeps every other hook, and refuses to overwrite a `settings.json` it
  can't parse.
- **The probe checks both directions.** `--probe` passes only when three things
  all hold: the canary is recalled on its identifier, the branch trace is
  present, and the word-overlap control stays silent. It uses a temporary store
  (`EPISODES_STORE`), so your real episodes are never touched.

## Iron Laws

- **A check must prove the branch ran, not just that the hook printed.** A
  fail-open hook passes every "did it exit 0" check even when its search branch
  is broken. Assert the trace line.
- **Automatic recall fires only on identifiers.** Loosen `require_ident` and the
  hook starts injecting unrelated dead ends into every prompt. Soon it is noise
  that everyone learns to ignore.
- **Every positive check needs a negative control.** A probe that only asks "did
  the canary come back?" also passes a hook that injects everything. The control
  prompt is what shows the hook can tell the two cases apart.
- **Episodes record instances, and notes hold the rule.** Don't promote an
  episode's prose into a rule store, and don't delete an episode once its lesson
  has become a note.

## Anti-Patterns

- ❌ **Logging an episode without the identifier.** "The build failed after the
  refactor" can never be recalled. Put `file.py:line`, the symbol or the version
  in `--task`.
- ❌ **Treating "the hook exited 0" as proof it works.** That is the exact
  three-week silent failure. Use `--probe`.
- ❌ **Word-overlap recall on every prompt.** It feels like better recall, but
  in practice it floods the context with irrelevant episodes.
- ❌ **Pasting a secret into `--why` "for context".** The write gate refuses it.
  Refer to the credential by name instead (for example, "the STAGING_API_KEY was
  expired").
- ❌ **Logging every turn.** An episode is one dead end, near-miss or
  non-obvious fix. Everything else belongs in the transcript.

## Related packs

- [`memory`](../memory/): holds the generalised lessons that episodes feed.
  When a kind of episode repeats, write it up there as a note.
- [`memory-socket`](../memory-socket/): maps the lifecycle sockets. This pack
  fills a second consumer on the **recall** (UserPromptSubmit) socket.
- [`autolearn`](../autolearn/): turns commits into lessons. Episodes capture the
  failures that never became a commit.
- [`hooks`](../hooks/): the general hook doctor and regression harness. Its
  guard-design notes apply to this hook too.

Credit: adapted from Andrew's personal Claude setup.
