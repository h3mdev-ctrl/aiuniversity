# aiuniversity — verified skill packs for Claude Code

**Turn a mentor's words into your machine actually doing the thing.**

A *skill pack* is a mentor's real practice packaged as concrete steps with a
check after each one — so a newcomer's Claude follows the known-good path instead
of guessing, gets the thing genuinely working, proves it did, then goes off and
does its own thing. A teacher, not a script. And like any good teacher, it can
keep mentoring you as it learns more.

> **If you only read one thing:** Content teaches you to *understand*. It doesn't
> make you *able*. This project packages the *able* part — and keeps it current.

---

## The gap this closes

You already follow mentors. You read everything Karpathy posts. You track the
best traders thread by thread, and you jump when they say something. But notice
the ceiling on all of it: you can read every word a great trader has ever written
and **still not have their setup running on your own screen.** Reading transfers
*understanding*. It does not transfer *ability*. That gap — between knowing what
the smart person does and your machine actually doing it — is the whole thing.

### Three ways to "follow" a mentor — and the world only serves the first

| Level | What it is | Where it lives today |
|---|---|---|
| **1 · Consume** | read their content → you *understand* | the entire internet piles up here |
| **2 · Execute** | run their practice → you become *able*, proven by an exam | **almost nobody packages this** |
| **3 · Stay subscribed** | they keep mentoring → you stay *current* as they sharpen it | rare |

The one-line version: the difference between a Karpathy blog post and Karpathy
*sitting next to you* — setting up your training loop, checking your work, and
pinging you when he finds a better way. A pack bottles the second one.

---

## Why a newcomer's Claude gets stuck (the real reason)

Here's the failure that started this. You download a genuinely powerful tool —
say [gbrain](https://github.com), a knowledge brain that plugs into Claude — and
getting it working turns into a multi-day grind. Worse: sometimes it *looks* set
up but **isn't even switched on**, and nothing tells you.

The root cause isn't that any single step is hard. It's this: **when a Claude
doesn't know exactly what to do, it reasons from scratch and invents a path — and
improvising is where it wanders off.** Give it a concrete instruction and it's
fine. Leave a gap, and it guesses. On a fiddly setup, one wrong guess cascades
into hours of back-and-forth. And there's no scoreboard, so you never know if
you're 40% done or 95% done.

> It's the same reason a new trader loses money holding a great setup: not
> because the idea is wrong, but because in the moment of doubt they improvise
> instead of following the rule. The fix isn't "be smarter." It's having a
> concrete thing to follow.

---

## The fix: a pack is a teacher on rails

A skill pack turns that fiddly setup into a **checkpointed runbook** — a list of
concrete steps, where every step has three parts:

1. **The exact instruction** — do *this*, word for word. Not "figure out how."
2. **A check** — a quick test that confirms the step actually worked.
3. **A prescribed fix if the check fails** — the concrete next move is handed
   over, so the Claude never has to guess its way out.

Because there's a checkpoint after every step, the AI *can't* quietly wander off.

```
   ┌─────────┐     ┌───────┐   PASS    ┌───────────┐          ┌──────────┐
   │  Step   │ ──▶ │ check │ ────────▶ │ next step │ ─ ··· ──▶│   PASS   │
   │ (exact  │     └───┬───┘           └───────────┘          └──────────┘
   │  instr) │         │ FAIL
   └─────────┘         ▼
                 ┌──────────────┐   re-check
                 │ prescribed   │ ─────────────▶ (back to the check)
                 │ fix (given)  │
                 └──────┬───────┘
                        │ fix also fails
                        ▼
                 ┌────────────────────────────┐
                 │ STOP — get a human          │
                 │ never loop, never improvise │
                 └────────────────────────────┘

   What we're banishing:  "the AI figures it out from scratch"
   — that's where it drifts, so we never let it.
```

**The exam is a diagnosis, not an IQ test.** If everything's set up properly, a
Claude should get every answer right. So a *wrong* answer doesn't mean the AI is
dim — it means a setup step is broken, and it tells you *which* one. That's the
scoreboard the old grind never had.

### Teach → verify → release → mentor

A good teacher gives you the skill, makes sure you can use it, then **lets you go
do your own thing.** The rails are *training wheels, not a cage.* Once the exam
passes, the pack gets out of the way. Three modes off the same steps:

- **teach** — walk a newcomer through it, explaining as it goes (no hunting YouTube).
- **verify** — read-only: silently return *PASS* or the exact gap. Changes nothing.
- **remediate** — apply each prescribed fix once, then re-check.

And it doesn't end at graduation: a pack can push sharpened best practice as its
author learns more, which you pull when you want their latest. Following a mentor
whose guidance keeps getting better.

---

## Where it starts: the foundation pack

The most valuable pack isn't a single tool — it's the **foundation**: getting a
newcomer's Claude set up *properly* for the long run. Six layers, each with a
concrete check:

- **Identity** — who you are and how Claude should talk to you.
- **Memory that compounds** — notes that persist *and* surface at the right moment.
- **The rulebook & the map** — what's always true, kept separate from where to look.
- **Guardrails** — automatic backstops that catch mistakes by code, not by hoping.
- **Capabilities, actually switched on** — tools verified *live*, not just "installed."
- **Durability** — backups, a decision log, a maintenance habit.

Specific tools go stale fast — swappable pieces that plug into that foundation.
But the **principles are timeless**. Package those once, well, and you've given a
friend in an afternoon what took you months to work out by hand.

---

## Try it in 60 seconds

Requirements: Python 3.9+, `pip install pyyaml`. The gbrain pack additionally
needs the `gbrain` and `claude` CLIs on your PATH.

**Double-check a gbrain you already have** (read-only — changes nothing):

```bash
python -m runner.cli verify packs/gbrain-windows
```

You'll get a PASS, or the exact step that's broken plus its prescribed fix. This
works on *any* existing gbrain — it answers "is it actually live right now?", not
just "did I install it."

**Set up the whole foundation** (runs the gbrain module inside it):

```bash
python -m runner.cli steps      packs/foundation   # teach: see the ordered steps
python -m runner.cli verify     packs/foundation   # check everything, read-only
python -m runner.cli remediate  packs/foundation   # apply fixes for anything broken
```

**For a friend setting up from scratch:** clone this repo, then in Claude Code
point it at `SKILL.md` and say *"teach me the foundation pack."* Claude walks each
step in plain English, checks as it goes, and stops to ask for help rather than
guessing if a fix doesn't hold.

**Run the tests:**

```bash
python -m pytest tests/ -q      # 41 tests, all green
```

---

## What's in here

```
aiuniversity/
  SKILL.md              the teach / verify / remediate wrapper (all the talking)
  runner/
    matcher.py          pure PASS/FAIL for one check (the deterministic core)
    verify.py           reads a pack, runs each check, escape-hatch state machine
    cli.py              the command SKILL.md calls (JSON out)
  packs/
    foundation/         the umbrella: 6 layers, layer 4 pulls in a module
    gbrain-windows/     the first real pack — gbrain set up + proven live on Windows
  tests/                41 tests
  docs/                 the thinking trail (below)
```

**Architecture (locked):** data + deterministic matcher + thin agent wrapper. The
`pack.yaml` is inert, human-readable data (you can read it before you run it —
that's the safety check). `verify.py` is the *only* thing that decides PASS/FAIL,
so the answer is the same every time. `SKILL.md` does all the talking. Packs can
include packs (`modules:`), so the foundation composes the gbrain pack inline.

The thinking trail lives in [`docs/`](docs/): [design](docs/design.md) (what & why)
→ [ceo-plan](docs/ceo-plan.md) (scope) → [eng-plan](docs/eng-plan.md) (architecture
+ build order).

---

## Status & roadmap

**v1 engine + first pack: complete.** Matcher, runner, escape hatch, validation,
`modules:` composition, CLI, and the teach/verify/remediate skill — 41 tests
green, and the foundation+gbrain golden path passes on a real machine.

Next, in order:
- **Hand it to a friend.** Zero-help setup = the wedge is proven. This is the real
  test; everything so far just makes it possible.
- **Per-OS `cmd:` variants** in `pack.yaml` (the runner uses cmd.exe on Windows;
  bash-only checks need per-OS forms).
- **The Obsidian module** — adding it should be *filling in a `pack.yaml`*, no new code.
- **Before any public/third-party marketplace:** pack signing + "review before you
  run" + sandboxing. A pack is executable instructions on your machine — safe among
  friends, a hard gate before strangers.

---

*Windows-first, friends-first. A side project about making Claude genuinely useful
the first time — and keeping it that way.*
