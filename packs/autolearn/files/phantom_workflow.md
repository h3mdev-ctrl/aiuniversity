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

### 4. Validate -- the durability test

Before setting `should_write: true`, ask:
- **Is this a RULE or an EPISODE?** Rules ("in situation Y, always X") are
  durable; episodes ("we did X this one time") are not.
- **Would a fresh Claude in a new session actually hit the trigger?** If the
  trigger is impossibly narrow, the memory is dark on arrival.
- **Do we already have a similar memory?** Check MEMORY.md and the "Learned"
  section. If there's a near-duplicate, prefer UPDATING that memory over
  adding a new one (`should_write: false`, do the update by hand instead).

If any answer is no, set `should_write: false`. That is a real answer, not a
failure.

### 5. Apply -- pipe the JSON to --write-learning

Only after Validate passes. The command:

```
echo '<the JSON>' | python packs/autolearn/files/phantom_autolearn.py --write-learning
```

If it prints `filed <name>.md into <path>` you're through.

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
