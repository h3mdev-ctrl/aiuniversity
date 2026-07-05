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

Most packs set up *one tool*. The foundation pack sets up **Claude itself,
properly, the first time** — the base layer everything else sits on. It's the
"umbrella" pack you run *before* any specific tool, so a newcomer's Claude is
durable and useful over months, not just working once.

Why it's the most valuable pack: specific tools go stale fast (this month's brain,
this week's helper), but the foundation is *timeless*. Get it right once and every
session after benefits. It's the pack that captures what took you months to work
out by hand.

The full vision is **six layers**, each with a concrete check:

- **Identity** — who you are and how Claude should talk to you.
- **Memory that compounds** — notes that persist *and* surface at the right moment.
- **The rulebook & the map** — what's always true, kept separate from where to look.
- **Guardrails** — automatic backstops that catch mistakes by code, not by hoping.
- **Capabilities, actually switched on** — tools verified *live*, not just "installed."
- **Durability** — backups, a decision log, a maintenance habit.

### What it checks today

Honest picture: the v1 foundation is a **working slice**, not all six layers at
full depth. It runs four real checkpoints — and pulls two whole packs (memory,
gbrain) in as modules:

1. **Memory that compounds** — *run the memory pack right here* (a **module**).
   Unlike the others, it doesn't just verify — it **sets up** the structure from
   scratch: a `memory/` folder, an always-loaded resolver index, wired to load
   every session, then a recall check that proves it's actually working.
2. **Constitution** — is your global `CLAUDE.md` there? (the file that stops
   Claude improvising against your setup)
3. **Capabilities** — *run the gbrain pack right here* (a **module**).
4. **Durability** — is your `~/.claude/projects` folder there? (where per-project
   memory compounds)

Identity (layer 0) and Guardrails (layer 3) are now built too. Foundation now
threads all five: memory → identity → constitution → guardrails → capabilities →
durability.

### How it runs — a pack that contains packs

A step like this isn't a check, it's a pointer to another pack:

```yaml
  - id: layer-1-memory
    instruction: set up a compounding memory with an always-loaded resolver index
    module: memory              # run this whole pack right here
```

When the engine hits that line it **opens that pack and runs its steps inline**,
then comes back and continues. So one run of the foundation walks this whole
sequence (the gbrain half is real output from the golden-path run; memory's last
step is the one live behavioural check):

```
run: remediate packs/foundation
│
├─ layer-1-memory        "run the memory pack here"
│     └─ opens memory, runs its steps inline:
│          memory/structure               set up memory/ + resolver index
│          memory/index-healthy           doctor: VERDICT HEALTHY
│          memory/wired-to-constitution   pointed at from CLAUDE.md (loads it)
│          memory/recall-probe            fresh session surfaces the canary  ← live
│
├─ layer-2-constitution  is ~/.claude/CLAUDE.md there?
│
├─ layer-4-capabilities  "run the gbrain pack here"
│     └─ opens gbrain-windows, runs its 4 steps inline:
│          gbrain-windows/install          gbrain --version           ✓
│          gbrain-windows/brain-reachable  gbrain list -n 1           ✓
│          gbrain-windows/mcp-registered   claude mcp list            ✓
│          gbrain-windows/activation-exam  gbrain query "…"           ✓
│
└─ layer-5-durability    is ~/.claude/projects there?
       ▼
     PASS
```

The steps come back labelled `memory/…` and `gbrain-windows/…`, so if anything
breaks you know **both which pack and which step** — the foundation doesn't just
say "capabilities failed," it says `gbrain-windows/mcp-registered failed, here's
the fix.` And it *stops right there* — later checks never run — because there's no
point checking on past a broken foundation piece.

That's the one idea that makes the foundation special: **it's a pack that contains
packs.** The umbrella declares slots; real tool-packs (gbrain today, Obsidian
next) drop in. Adding a capability is *filling in a `pack.yaml`* — no new code —
while the timeless six-layer frame stays stable underneath.

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
python -m pytest tests/ -q      # 98 tests, all green
```

**Set up a compounding memory** (creates the structure, wires it, proves recall):

```bash
python -m runner.cli remediate packs/memory
```

**Local or hosted — your choice.** Some packs offer a `--variant`. The steps
adapt to what you pick (and the fixes are tailored to it):

```bash
# gbrain: a local file, or hosted in the cloud
python -m runner.cli remediate packs/gbrain-windows --variant local     # PGLite, no account
python -m runner.cli remediate packs/gbrain-windows --variant supabase   # hosted, syncs machines

# wiki: just on your machine, or also published free
python -m runner.cli remediate packs/obsidian-wiki --variant local       # vault + memory link
python -m runner.cli remediate packs/obsidian-wiki --variant hosted      # also published (Quartz)
```

`steps --variant <x>` shows exactly what that choice will run before you commit.
Leave `--variant` off to use the pack's default (the simpler, no-account option).

**Autolearn from every commit** (a git hook captures commits; lessons get filed
into memory at wrap-up — run from inside a git repo):

```bash
python -m runner.cli remediate packs/autolearn
```

**Set up a free, publishable knowledge wiki** (Obsidian vault → Quartz → free host,
linked into memory):

```bash
python -m runner.cli remediate packs/obsidian-wiki
```

---

## What it costs

Setup is a one-time, guided run. Re-checking it later is basically free, and it
costs nothing when you're not running it.

| | Time | Tokens | Rough $ (pay-as-you-go API) |
|---|---|---|---|
| **Set up foundation + gbrain** (one guided `teach` run) | ~15–45 min\* | ~40k–100k | ~$0.50–$3 |
| **Re-check later** (`verify`) | seconds | ~2–6k | a few cents |
| **Idle** (not running) | — | 0 | $0 |

\* Most of that time is *you* doing the real steps — creating a Supabase project,
setting your PATH. The pack removes the guessing, not the typing. The same setup
unguided took a friend **days**.

Two things keep it cheap:

- **The checks cost ~zero tokens.** They're local shell commands (`gbrain
  --version`, `claude mcp list`) that run on your machine — not agent reasoning.
  Tokens are spent only on the teaching narration and reading results back. A
  `verify` is a single command round-trip (~3KB of output).
- **There's no background cost.** The pack does nothing unless you run it — no
  daemon, no polling, no idle spend.

What it replaces is the expensive part: an unguided Claude re-deriving a fiddly
setup from scratch wanders across multiple sessions and can burn **hundreds of
thousands of tokens** — and still leave you "not even activated." The pack turns
that open-ended grind into a bounded run.

Numbers vary with your model tier (Haiku < Sonnet < Opus), how many steps need a
fix, and how chatty the checks are. On a Claude Pro/Max subscription there's no
per-run charge — it's a rounding error against your monthly quota. And gbrain's
own running costs (its database, embeddings) are separate — the pack just gets it
live.

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
    foundation/         the umbrella: pulls in the memory + gbrain packs as modules
    memory/             sets up a compounding memory + always-loaded resolver index
    gbrain-windows/     gbrain set up + proven live on Windows
    obsidian-wiki/      a free-publishable LLM wiki, linked into memory
  tests/                58 tests
  docs/                 the thinking trail (below)
```

**Architecture (locked):** data + deterministic matcher + thin agent wrapper. The
`pack.yaml` is inert, human-readable data (you can read it before you run it —
that's the safety check). `verify.py` is the *only* thing that decides PASS/FAIL,
so the answer is the same every time. `SKILL.md` does all the talking. Packs can
include packs (`modules:`), so the foundation composes the memory and gbrain packs
inline.

The thinking trail lives in [`docs/`](docs/): [design](docs/design.md) (what & why)
→ [ceo-plan](docs/ceo-plan.md) (scope) → [eng-plan](docs/eng-plan.md) (architecture
+ build order).

---

## Status & roadmap

**v1 engine + four packs: complete.** Matcher, runner, escape hatch, validation,
`modules:` composition, per-pack **variants** (local/hosted choices), CLI, and the
teach/verify/remediate skill — 98 tests green.

Packs:
- **identity** — an interview (layer 0): who you are + how Claude should talk to
  you; writes context files + a user_profile memory.
- **memory** — set up a compounding memory + resolver index from scratch.
- **guardrails** — layer 3: install a PreToolUse hook that blocks reads of
  credential files (.env, private keys) and *proves* it fires by piping a
  forbidden probe through the installed hook.
- **gbrain-windows** — verify a tool is installed *and live*; choose **local**
  (PGLite) or **supabase** (hosted). Also wires a **usage discipline** into CLAUDE.md
  so Claude *uses* the brain instead of only when asked — **lean by default**
  (search-first before researching, capture only what's clearly worth keeping, no
  per-turn token tax), with an opt-in **`--eager`** cadence for power users who want
  every-message capture.
- **obsidian-wiki** — an LLM wiki linked into memory; choose **local** (on disk)
  or **hosted** (published free via Quartz → Vercel/Pages). Knowledge branch.
- **autolearn** — a phantom-style wrap-up: a git post-commit hook captures every
  commit, and a reflection pass files durable lessons into memory (new memory +
  resolver row). Self-improvement companion to the memory pack.
- **foundation** — the umbrella; threads memory + gbrain through as modules.

Every setup pack ships **worked examples modeled on a real, heavily-used system**
(a mature memory index, a wiki filing guide + concept note + MOC, a brain filing
map) — so a newcomer's Claude learns the structure by copying a proven one instead
of inventing it. Setup golden paths pass on a real machine.

Next, in order:
- **A skill tree** — modules as a chooseable, RPG-style progression with
  prerequisites and branches, instead of a hard-coded foundation. Captured in
  [`docs/skill-tree.md`](docs/skill-tree.md); a presentation layer over the
  `modules:` primitive, not new engine machinery.
- **Knowledge / ingest branch** — planned pack modules that turn sources into
  compounding memory (specced in
  [`docs/planned-knowledge-ingest.md`](docs/planned-knowledge-ingest.md)):
  - **`x-post-ingest`** — pull a tracked X account / saved thread → distilled,
    attributed notes filed into memory/gbrain/wiki.
  - **`youtube-transcriber`** — transcribe a video (local whisper or transcript
    source) → distilled notes → memory, keeping the transcript, dropping the audio.
  - The payoff isn't the ingest, it's the **weekly → monthly rollup rhythm**: when
    you're learning a subject, atomic notes roll into `weekly/` wrap-ups and then a
    `monthly/` synthesis that every future session starts from — a compounding brain,
    not a notes folder. Reuses the `autolearn` drain (a scheduled rollup is just the
    drain pointed at notes instead of commits) — no new memory machinery.
  - **Worked example — [`docs/examples/vault_crosslink.py`](docs/examples/vault_crosslink.py):**
    the mechanical half of cross-linking (backlink reciprocity, broken-link + leak
    detection) done as a **model-free script**. Validated on a real 853-page wiki: it
    added 121 missing backlinks for **0 model tokens** (vs ~150–350k by hand). The
    lesson the ingest modules inherit: *script the plumbing, keep the model on the
    prose.* See [`docs/planned-knowledge-ingest.md`](docs/planned-knowledge-ingest.md).
- **`shared-context` module (Layer 3)** — a shared, append-only **live-context log**
  with a read-before-reply / append-after-turn invariant, so multiple Claude instances
  (bridge, cloud, scheduled tasks, worktrees) coordinate instead of drifting. The one
  memory layer we don't yet ship; specced in
  [`docs/memory-layers.md`](docs/memory-layers.md), which also maps every existing pack
  to the four memory time-horizons (independent convergence with a production 2-agent
  stack that runs the same gbrain — strong validation the shape is right).
- **Hand it to a friend.** Zero-help setup = the wedge is proven. This is the real
  test; everything so far just makes it possible.
- **Live behavioural probes end-to-end** — memory's `recall-probe` and the wiki's
  `gbrain-queryable` step each spawn a real tool call; today they're the one live
  step per pack (unit-tested, run by hand).
- **Per-OS `cmd:` variants** in `pack.yaml` (the runner uses cmd.exe on Windows;
  bash-only checks need per-OS forms).
- **Before any public/third-party marketplace:** pack signing + "review before you
  run" + sandboxing. A pack is executable instructions on your machine — safe among
  friends, a hard gate before strangers.

---

## Attribution + related projects

- **[gbrain](https://github.com/garrytan/gbrain)** (Garry Tan, MIT) — a personal
  knowledge brain with its own excellent **skillpack system**. aiuniversity does
  not adopt gbrain's distribution channel (`skillpack.json` + `gbrain skillpack
  scaffold`), but adopts its **structural conventions** — the per-skill
  Contract / Iron Laws / Anti-Patterns / Related pattern, the file-by-subject-not-
  format ingest rule, verbatim-quote discipline, and retrieval-reflex depth.
  See [`docs/pack-structure.md`](docs/pack-structure.md) for the section
  conventions each aiuniversity pack follows.
- **Quality checking a gbrain-format skillpack?** Use the official doctor —
  `gbrain skillpack doctor <dir>`. aiuniversity does not ship its own; each pack's
  correctness is covered by its own test suite (`python -m pytest`), and the
  human-legible per-pack `README.md` covers what the tests can't.

---

*Windows-first, friends-first. A side project about making Claude genuinely useful
the first time — and keeping it that way.*
