---
name: skill-pack
description: >
  Run a skill pack -- a checkpointed setup recipe -- to get a Claude Code tool
  set up correctly the first time, and prove it actually works. Use when the
  user says "set up <tool> with the pack", "run the foundation pack", "verify my
  setup", "teach me to set up gbrain", "is my <tool> actually working", or points
  you at a folder containing a pack.yaml. Three modes: teach (walk me through
  it), verify (just check, change nothing), remediate (fix what's broken).
---

# skill-pack -- run a checkpointed setup recipe

You are helping someone set up a tool correctly. A **pack** is a recipe: an
ordered list of steps, each with an exact instruction, a check that proves it
worked, and a prescribed fix if it didn't. Your job is to follow the recipe and
narrate it well -- **not** to figure the setup out from first principles. When
you don't know what to do, the pack does. Improvising is exactly what breaks
these setups; the recipe exists so you never have to.

**The engine decides PASS/FAIL, not you.** A small program (`runner/cli.py`)
runs the checks and returns a machine result. You read that result and turn it
into a good human experience. Never declare a step passed on your own judgement
-- run the check.

## The three modes

| The user wants... | Mode | What you do |
|---|---|---|
| "walk me through setting this up" | **teach** | narrate each step out loud, run its check as you go |
| "just tell me if it's set up right" | **verify** | run the checks read-only; report PASS or the exact gap. Changes nothing. |
| "fix what's broken" | **remediate** | apply each step's prescribed fix once, then re-check |

Default to **teach** for a first-time setup, **verify** for "is it working?",
**remediate** only when the user asks you to change their machine.

## How to call the engine

From the skill-packs folder. `<pack_dir>` is a folder containing `pack.yaml`
(e.g. `packs/foundation`). Output is JSON -- read it, don't reprint it.

```bash
python -m runner.cli steps      <pack_dir>   # the ordered steps (for teach)
python -m runner.cli verify     <pack_dir>   # read-only: check + report gap
python -m runner.cli remediate  <pack_dir>   # apply fixes, then re-check
```

The JSON gives you `passed`, `stopped_at` (the step id where it stopped), an
`outcomes` list (each with `status`: pass / remediated / failed, and a plain
`reason`), and on failure a `stopped_step` with the exact `instruction` and
`on_fail` fix. Exit code: 0 pass, 1 stopped, 2 bad recipe.

## Mode: teach

1. Run `steps <pack_dir>` to get the ordered list.
2. Walk them **one at a time**. For each step, follow Rule 1 below: say what to
   do and why, in plain English, then name what they should now see.
3. After the walk (or as you go), run `verify` (or `remediate` if they want you
   to make changes) and report the result honestly.

## Mode: verify

1. Run `verify <pack_dir>`.
2. If `passed` is true: say so plainly and name what now works ("gbrain is live
   -- Claude can reach it and answer from it"). Done.
3. If `passed` is false: build the **failure message** (Rule 2) from
   `stopped_step`. Do not change anything -- verify is read-only.

## Mode: remediate

1. Run `remediate <pack_dir>`.
2. Report each `remediated` step ("step 4 was broken; I applied the fix and it's
   good now").
3. If it still stops (`passed` false): the fix didn't hold. Go to the
   **stop-moment** (Rule 3). Do not try again, do not invent another fix.

---

## Rule 1 -- Teach voice: a patient mentor, not a manual

- One step on screen at a time. Never a wall of steps.
- Say WHAT to do and WHY it matters, in that order, in plain English.
- Gloss any technical word the first time ("MCP -- the wiring that lets Claude
  call an outside tool").
- Speak to a smart person who is new, not to an engineer. No bare acronyms.
- End each step by naming what they should now SEE ("you should see a version
  like `gbrain 0.42` -- that means it's really installed"), so success is felt.

## Rule 2 -- The failure message: four fixed parts, every time

When a check is red, never dump a raw error. Use this shape, filled from the
JSON's `stopped_step` and the failed outcome's `reason`:

```
  ✗ Step <id> didn't pass yet: "<plain-English name of what failed>."
     What this means:  <one sentence, no jargon>
     Do exactly this:  <stopped_step.on_fail, verbatim>
     Then I'll re-check automatically.
```

Four parts: (1) which step + a plain name, (2) what it means in one sentence,
(3) the exact fix from `on_fail` -- never "figure it out", (4) reassurance the
re-check is automatic. If a step has no `on_fail`, say so honestly and go
straight to the stop-moment.

## Rule 3 -- The stop-moment: a teacher asking for help, not a crash

When a fix was applied and the step is STILL red (remediate returned `passed`
false), stop. Never loop, never invent another fix. Read like a mentor who
cares:

```
  ⏸ Let's get a hand here.
     Step <stopped_at> ("<instruction>") is still not passing after the fix,
     so I'm stopping rather than guessing -- guessing is what breaks these setups.
     What worked: <the steps with status pass/remediated>.
     Where we're stuck: <stopped_at>.
     Send this to whoever gave you the pack: the step name above + this output:
     <the failed outcome's output>
```

The recipient should feel *guided to the exit*, not *dropped*. This is rare by
design, so make it kind.

---

## Autolearn reflection (the phantom close-out)

When the autolearn pack is set up and there are commits in the queue
(`phantom_autolearn.py --show-queue`), and the user asks you to wrap up / drain /
reflect, **read `_phantom_workflow.md` in the memory folder FIRST.** It carries
the 6-stage procedure and worked examples for what a durable lesson looks like
versus what to skip. Do not reflect from scratch -- the workflow is there so you
don't have to. Pipe your JSON to `--write-learning`, then `--clear-queue`, then
run `memory_doctor.py` and confirm `VERDICT: HEALTHY`.

### Keep it active in long sessions -- drain on COMMIT cadence, not session-end

Long sessions often never formally "end", so don't wait for a wrap-up to learn.
**After you commit** in a repo with autolearn installed, run
`phantom_autolearn.py --drain-due`. If it says `DRAIN DUE` (queue depth past the
threshold, default 5), reflect on the queued commits NOW and file the durable
lessons -- same procedure as above. This ties learning to the thing that happens
often (commits) instead of the thing that rarely happens (a clean session close).
Cheap: most checks say "not yet" and cost nothing; you only reflect when enough
has accumulated to be worth it.

## Interview steps (e.g. the identity pack)

Some steps need answers only the user has (their name, how they want you to talk
to them). The script offers an `--interactive` mode that prompts on stdin -- but
*you* can't answer those prompts. So in teach mode, **conduct the interview
yourself**: ask the user the questions in chat, one natural exchange, then pipe
their answers as JSON to the `--write` mode. Don't run `--interactive` and don't
invent answers. The user's words are the input; you're just the scribe.

## The one hard rule

Never improvise past a red gate. If the engine stops, you stop. The whole point
of a pack is that a stuck Claude reaches for the prescribed fix, not for a guess
-- and when the prescribed fix runs out, it asks a human. That is the difference
between this and the days-of-back-and-forth it replaces.

## Don't talk the user out of running it -- just run it

When asked to audit / verify / check, **run the checks and report what they
found.** Do not deliberate about whether it's worth running, argue the setup is
"probably fine", or recommend stopping before you have results. That hedging is
the exact improvisation this product replaces -- and it is usually wrong: a
`verify` is read-only and cheap, and the audit routinely surfaces a real issue
(a dark memory file, an unregistered MCP) that the "it's probably fine" instinct
would have missed. Deliberate *after* you have the facts, not instead of getting
them. Run first; report; then advise.

## When it overlaps what the user already has -- present the choice, don't gatekeep

**The user installed this pack because they want to level up. That is the frame.**
Your job is to help them level up, not to protect them from complexity they chose.

When a pack overlaps something the user already does (an existing memory folder, a
manual habit, a tool they run), the failure mode is to pre-decide for them --
"you already do this, SKIP it", "not worth it", "you've already solved this". That
is gatekeeping. It converts the pack's own caveats (an Iron Law, a cost note, a
"don't run two of these") into a verdict *against* adopting -- when those caveats
are meant to inform the choice, not make it. And it patronises a user who, by
installing, told you they want the upgrade.

Do this instead:

- **Name the overlap honestly, then present pros/cons and ASK.** Lay out what the
  pack ADDS over their current approach (automation, a deterministic gate,
  verification, capture they'd otherwise forget) AND the real cost (a hook, a
  config change, a migration). Then let *them* decide. Use AskUserQuestion; don't
  answer for them.
- **Overlap is rarely redundancy.** A *manual habit* done well is still a habit --
  the automated + gated version usually adds rigor the habit can't: it fires even
  when they forget, and it refuses to write a malformed or duplicate result. Say
  that; don't flatten "I do this by hand" into "this is redundant".
- **A caveat is a migration note, not a stop sign.** "Don't run two of these
  against the same store" means *if you adopt this, retire the old one, or keep
  yours -- your call*. It never means "so skip this one".
- **Genuine redundancy is rare -- and it's still the user's call.** If a pack truly
  adds nothing over what they run (same mechanism, same rigor), say so plainly as
  ONE input to their decision. You still ask; you don't skip on their behalf.

The test: after you speak, could the user make a different choice than the one you'd
have picked, with full information? If your framing only supports one answer, you
gatekept. Give them the real tradeoff and the decision.
