# Phantom close-out workflow -- how to autolearn from a commit properly

> When you're processing the autolearn queue (`phantom_autolearn.py --show-queue`
> and `--write-learning`), follow this. It is the concrete procedure so you never
> have to derive one. Six stages, each with concrete questions and a worked example.

## When to run this (cadence, not session-end)

Don't wait for a session to "end" -- long sessions often never do. Run this on
**commit cadence**: after a commit, check `phantom_autolearn.py --drain-due`. If a
drain is DUE (queue depth past the threshold, default 5), reflect now. Between
sessions, a scheduled `--nudge` (see `scheduled_nudge.md`) reminds you when the
queue has piled up. Either way, a human/Claude does the actual reflection -- the
tool never writes memory unattended.

## The one rule

**A durable lesson beats no lesson beats a trivial lesson.** Better to mark
`should_write: false` than to file noise. Every filed lesson lives in the
always-loaded MEMORY.md scan forever, so noise dilutes the whole system.

## The 6 stages

### 1. Observe -- what to actually look at

Read three things:
- **The commit subject + body** -- what did we intend?
- **The `--stat` diff summary** -- what actually changed, at a glance.
- **The queue context** -- was this the tail of a struggle (2+ commits fixing the
  same thing), or a one-off?

**Stop here (write nothing) when:**
- Pure formatting, whitespace, or typo fixes.
- Revert commits.
- Merge commits with no manual edits.
- Trivial version / changelog bumps.
- Doc-only commits that don't encode a new rule.

### 2. Critique -- what surprised us?

Ask:
- What did we CORRECT in this commit? (bug fixes are the richest source of lessons)
- What almost tripped a future Claude that this commit avoids?
- Is there a rule in this fix that would apply to *other* situations, not just
  this one? (If yes, that's a durable rule.)

If you can't answer these, `should_write: false` is the honest answer.

### 3. Generate -- shape a candidate lesson

The JSON shape:

```json
{
  "should_write": true,
  "type": "feedback",
  "name": "kebab-slug",
  "description": "when you're about to <the triggering moment>",
  "body": "The lesson in one paragraph. **Why:** why it matters. **How to apply:** what to do next time.",
  "resolver_intent": "when you're about to <the triggering moment>"
}
```

Rules of thumb:
- **type**: `feedback` for behaviour rules ("do X" / "avoid Y"); `reference` for
  where-answers-live ("this pattern lives here").
- **description AND resolver_intent** phrase the TRIGGER -- the moment the lesson
  should surface. Not a topic ("Windows quirks") but a moment ("when you're
  about to run a bash command that contains a colon on Windows").
- **body** carries the rule + a `**Why:**` and `**How to apply:**` line.
- **name** is short, kebab-slug, distinct enough to eyeball.
- **Only ONE lesson per commit at most.** If a commit taught two things, pick the
  one whose trigger fires more often.

### 4. Validate -- two layers, and NO model required

Validation is split by what each layer is actually good at. This is the deliberate
lesson from phantom, which deleted its LLM judge panel ("cost, no signal") for
deterministic checks. You need no local model for any of this.

**Layer 1 -- deterministic gates (automatic, pure code).** `--write-learning`
runs these for you and REFUSES the write on any HARD failure:
- credential/secret scan (won't let a key from a diff land in memory),
- size bound (body <= 40 lines -- distil to the rule),
- duplicate slug (a memory by that name exists -> update by hand, don't overwrite),
- balanced code fences + required fields.
You can dry-run them: `... --validate` (same JSON on stdin, writes nothing).

**Layer 2 -- your semantic judgment (you have the context; a judge model does not).**
This is the part only the reflecting Claude can do well, because you were in the
session. Ask:
- **Is this a RULE or an EPISODE?** Rules ("in situation Y, always X") are durable;
  episodes ("we did X once") are not.
- **Would a fresh Claude actually hit the trigger?** Impossibly narrow -> dark on
  arrival.
- **Near-duplicate of an existing memory?** Prefer UPDATING it (`should_write:
  false`, edit by hand) over adding a rival.

If any Layer-2 answer is no, set `should_write: false`. That is a real answer.

**Optional -- cross-model second opinion.** ONLY for high-stakes edits (a change
to a hard rule, a security/guardrail memory) AND only if you happen to have a
second model handy (a local Ollama panel, another API). It is NOT part of the
normal flow and NOT required -- for routine lessons the deterministic gates plus
your own judgment are the whole gate.

### 5. Apply -- pipe the JSON to --write-learning

Only after Validate passes. The command:

```
echo '<the JSON>' | python packs/autolearn/files/phantom_autolearn.py --write-learning
```

If it prints `filed <name>.md into <path>` you're through. If it prints `REFUSED`,
a deterministic gate blocked it (a secret in the body, a duplicate name, an
oversized body, unbalanced fences). Fix the named issue and retry -- never force
past a HARD gate.

### 6. Consolidate -- confirm and clear

Run the doctor to confirm the filed lesson is reachable and the index is still
under budget:

```
python packs/memory/files/memory_doctor.py
```

Expect `VERDICT: HEALTHY`. Then clear the queue for processed items:

```
python packs/autolearn/files/phantom_autolearn.py --clear-queue
```

The queue is a rolling capture, not a to-do list -- if you leave items behind,
the next drain re-processes them.

---

## The unattended drain -- an action PLAN, not just "create" (models global-evolution)

The 6 stages above are the **interactive** path: a Claude in a live session
reflects on one commit and pipes a single `create` to `--write-learning`. That's
great for "I just learned this, file it now."

For the **unattended** path (`--drain`, run headless on a cadence), we model a more
capable design borrowed from a mature, proven system (Andrew's `global-evolution`
drain). Instead of only ever *creating*, the drain reflects over the WHOLE queue at
once, is shown the EXISTING memory (routing index + every slug), and returns a
**plan of actions**:

- **create** -- a genuinely new lesson (slug must not already exist)
- **update** -- refines an existing memory; returns its FULL new content
- **supersede** -- an existing memory is stale/wrong; stamp it (in place, never
  deleted) with a banner + `status: superseded` frontmatter, optionally pointing to
  its replacement
- **skip** -- nothing durable

Why this matters: a create-only drain slowly fills memory with near-duplicates and
never retires anything stale. Giving the model the existing memory + update/supersede
lets the memory **evolve** -- the same discipline you'd apply by hand.

What keeps it safe (the same "no model is trusted" principle):

- **`validate_plan` is a deterministic gate** over every action -- slug shape,
  create-not-existing, update-must-exist, supersede rules, no credentials, size
  caps, balanced fences. A single HARD finding blocks the WHOLE drain; the queue is
  kept, nothing is written. Model-free, exactly like `validate_learning`.
- **`--tools=""`** on the headless call -- the model can only emit text, never touch
  the filesystem. Python applies the validated plan. That's the safety boundary.
- **clobber-guard on `update`** -- the model never saw the file's current body, so an
  `update` that is both much shorter AND drops most of the old substantive lines is
  refused (original kept). A genuine extension passes.
- **index growth -> CATALOG.md** (on-demand), never the always-loaded MEMORY.md; a
  safety net guarantees every created file is routable so the doctor never goes dark.
- **one git commit per drain** -> a bad autonomous write is `git revert HEAD`.

Run it (needs the `claude` CLI + a cheap model; ~cents-equivalent, or plan quota):

```
AUTOLEARN_DRAIN_MODEL=claude-haiku-4-5 python packs/autolearn/files/phantom_autolearn.py --drain
```

A one-shot structured reflection doesn't need a top-tier model -- Haiku is the right
draw. See `windows_gotchas.md` if you're on Windows (npm `.cmd` shim, Task Scheduler
PATH, etc.).

---

## Worked examples

### Example A -- durable feedback (SHOULD WRITE)

**Commit:** `fix(memory): fail loudly on multiple memory systems, never silently pick`
**Stat:** setup_memory.py + memory_doctor.py + tests updated.

**Reflection:**
- **Observe:** discovery used sorted-glob; silently picked one on ambiguity.
- **Critique:** the rule is broader than memory -- *any* tool that finds >1
  candidate should refuse to guess.
- **Generate:**
  ```json
  {"should_write": true, "type": "feedback",
   "name": "fail-loud-on-ambiguity",
   "description": "when you're about to auto-resolve a lookup that has more than one plausible match",
   "body": "If a tool finds >1 candidate, refuse to guess -- list every candidate and require an explicit pin (env var, argument). **Why:** silent guessing on ambiguity produces false-positive 'it's fine' verdicts against the wrong data. **How to apply:** on len(candidates)>1, print all, exit non-zero, and name the exact pin mechanism.",
   "resolver_intent": "when you're about to auto-resolve a lookup with more than one candidate"}
  ```
- **Validate:** durable rule ✓; trigger fires on any lookup, not just memory ✓;
  no near-duplicate ✓ -> write.

### Example B -- durable reference (SHOULD WRITE)

**Commit:** `docs: guardrails README + rephrase to avoid tripping our own guard`
**Stat:** README.md.

**Reflection:**
- **Observe:** a real guardrail fired on the commit message itself when a shell
  command echoed a credential pattern literally.
- **Critique:** the rule is "when writing shell prose (echo/commit/here-doc)
  that would name a credential file pattern literally, expect the guard to
  trip -- phrase around it or bypass explicitly."
- **Generate:**
  ```json
  {"should_write": true, "type": "reference",
   "name": "credential-guard-trigger-in-prose",
   "description": "when you're about to write a shell command whose text would literally name a credential file pattern",
   "body": "PreToolUse credential guards match the literal text of Bash commands -- including echo/here-doc/commit-message text that only *mentions* a pattern. Phrase around it (say 'dot-env variants' instead of the literal name), or set CLAUDE_CRED_GUARD=off explicitly for that one call.",
   "resolver_intent": "when writing shell prose that would literally name credential file patterns"}
  ```
- **Validate:** durable ✓; recurring trigger (any doc/commit describing a
  guard) ✓ -> write.

### Example C -- non-durable (SHOULD_WRITE FALSE)

**Commit:** `chore: bump VERSION to 0.3.4.2`
**Stat:** VERSION file, one line.

**Reflection:**
- **Observe:** version bump, no code change.
- **Critique:** no rule embedded here.
- `{"should_write": false}` -- honest and correct. Nothing to file.

### Example D -- looks durable but isn't (SHOULD_WRITE FALSE)

**Commit:** `fix: correct typo in helper docstring`
**Stat:** one comment line.

**Reflection:**
- **Observe:** docstring typo.
- **Critique:** "check docstrings for typos" is a rule, but it's near-universal,
  never triggered by a specific moment -- a memory nothing routes to.
- `{"should_write": false}` -- valid rule, wrong grain for a resolver row.

---

## Common failure modes

- **Filing an episode as a rule.** "We fixed X once" is not "always Y in
  situation Z". If the body starts with "we", suspect an episode.
- **Trigger too narrow.** If the resolver_intent names one file path or one
  script, no future situation will match. Widen the trigger or don't file.
- **Duplicates.** Two memories with different names but the same trigger dilute
  routing. Check MEMORY.md first; update instead of adding.
- **Filing everything.** The queue is not a checklist. Most commits teach
  nothing durable, and that is fine. Aim for maybe 1 in 5 commits producing a
  lesson.
