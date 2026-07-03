# skill-packs

A **checkpointed runbook** for setting up Claude Code tools correctly the first
time. A pack is a recipe: an ordered list of steps, each with a concrete
instruction, a check that proves it worked, and a prescribed fix if it didn't.
Follow the recipe instead of improvising, and "it looked set up but wasn't"
becomes impossible.

North star: **can a newcomer get the right outcome from a pack, on their own
machine, without days of back-and-forth?**

## Architecture (locked)

Data + deterministic matcher + thin agent wrapper:

- `pack.yaml` -- inert data: the steps, checks, fixes. Readable before you run it.
- `runner/` -- the only thing that decides PASS/FAIL, so the answer is the same
  every time.
  - `matcher.py` -- pure PASS/FAIL for one check (the deterministic core).
  - `verify.py` -- *(next)* reads a pack, runs each check, escape-hatch loop.
- `SKILL.md` -- *(next)* the teach / verify / remediate wrapper (all the talking).

Full plan: `~/.gstack/projects/h3mdev-ctrl-PathofTrading/2026-07-03-skill-packs-eng-plan.md`

## Build status

- [x] Matcher core + unit tests (5 check types, bad-recipe guards)
- [x] Runner loop: validate-first, run steps, escape-hatch state machine
- [x] pack.yaml schema + validation (fail up front on a bad recipe)
- [x] modules: recursion (one level, id-prefixed, depth-guarded)
- [x] CLI (steps / verify / remediate, JSON output) -- the command SKILL.md calls
- [x] SKILL.md teach / verify / remediate (three interaction-design rules baked in)
- [x] Real gbrain-on-Windows pack threaded through the foundation umbrella
- [x] Golden-path run on the reference machine -> PASS (all 6 checkpoints green)

**v1 engine + first pack: COMPLETE.** Next: hand foundation + gbrain to a friend
(zero-help setup = wedge proven), then the Obsidian module, then durability polish.

## Run the tests

```bash
python -m pytest tests/ -q
```
