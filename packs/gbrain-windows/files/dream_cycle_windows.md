# gbrain's nightly "dream" cycle on Windows -- what to know

> gbrain can run a nightly **dream** job that consolidates your brain: builds
> links, updates the timeline, dedups, embeds stale pages, recomputes salience,
> and (optionally) does an LLM **deep-extract** of facts from recent content.
> This is OPTIONAL -- gbrain works fine without it. But if you set it up on
> Windows, these are the traps that cost hours. Grounded in a real setup.

## The big decision: do you even need the LLM deep-extract?

The dream cycle has two halves, and they have very different requirements:

1. **Structural (free, no model needed):** links, timeline, dedup, embeddings,
   salience. This is MOST of dream's value, costs nothing, and needs no chat model.
2. **LLM deep-extract (needs a chat model):** pulling structured facts out of
   recent pages with an LLM driving a multi-turn agentic loop. This is the
   expensive, optional half.

**If you don't have a strong local model, don't have codex, and don't want a
hosted API key: just run structural-only dream.** You lose the deep-extract, not
the consolidation. Never block your whole nightly on the one part that needs a
model -- most people should start structural-only and add the extract later, if
ever.

## What the deep-extract actually does, in plain terms

Think of your brain's pages as a pile of raw notes -- meeting recaps, journal
entries, code files, article summaries. The deep-extract is the step that reads
through recent pages and pulls out **standalone, reusable claims** ("takes"):
short, atomic facts/opinions that are worth surfacing again later, separated
from the surrounding narrative they were buried in.

Concrete example: say yesterday's daily note says

> "Spent an hour on the breadth divergence script. Turns out the 200-day MA
> lookback was silently including delisted tickers, which skewed the whole
> stage count high. Fixed by filtering on `is_active` before the rolling calc.
> Also chatted with Sam about the Q3 roadmap -- probably slipping two weeks."

Structural-only dream will link this page into your graph and make it
searchable by keyword/embedding -- useful, but you only "find" the lesson if
you already know to search for it. The deep-extract instead lifts out:

- *take:* "Breadth divergence stage counts were skewed high because the 200-day
  MA lookback wasn't filtering delisted tickers -- always filter on `is_active`
  before rolling calcs on ticker universes."
- *take:* "Q3 roadmap is trending ~2 weeks late per a conversation with Sam."

Those get graded (`grade_takes`), and if they clear a confidence bar, promoted
into your brain as their own retrievable facts -- so next time you (or an
agent) touch anything roadmap- or breadth-calc-related, the lesson surfaces
even if you never think to search "delisted tickers." That's the benefit over
not running it: **your notes stop being just an archive and start actively
resurfacing lessons you didn't know to look for.**

The cost of *not* running it: nothing breaks. You keep 100% of structural
dream (links, embeddings, search, dedup) for free. You just don't get this
"lesson resurfacing" layer -- you have to remember to search for things
yourself, the way you always have.

## The "which model powers the extract" trap

The deep-extract drives a multi-turn agentic subagent loop, which is much harder
than one-shot chat. So the model that's "good enough to chat" often isn't good
enough here:

- **A small local model (an 8B like qwen3:8b) works for simple one-shot chat but
  is unreliable driving the dream agentic loop** -- tried and failed on a real
  Windows setup (it stalls or produces low-quality extraction). Don't assume
  "it chats fine" means "it can dream."
- **codex or another external LLM CLI** can back the chat model, but **you do NOT
  need one** -- and you may not have it. Do not treat codex as a required piece.
- **The reliable cheap path:** point the chat model at a small *hosted* model,
  e.g. `gbrain config set chat_model anthropic:claude-haiku-4-5` plus an API key.
  Small per-token cost, reliable for the agentic loop.

The ladder, in order: **structural-only (free) -> a small hosted model for the
extract -> a strong local model if/when one fits your GPU.** The deep-extract does
NOT have to run locally, and it does NOT require codex.

## Confirmed: `propose_takes` is hardcoded to Anthropic, not your `chat_model`

Tested live (gbrain 0.42.53.0): the actual expensive phase of the deep-extract
is called `propose_takes` -- it's the one that runs long (50s+ per cycle) and
does the multi-turn "read a page, decide if there's a standalone take in it"
loop described above. We pointed `chat_model` at a local Ollama model
(`openai:llama3.1:8b-instruct-q4_K_M`, already installed and already proven
reliable on other batch tasks) and re-ran `gbrain dream --dry-run`. Every one
of `propose_takes`'s page attempts failed identically:

```
"extractor failed on daily/2026-07-03: Anthropic chat requires ANTHROPIC_API_KEY."
```

We also probed for a separate override (`gbrain config set takes_model ...`,
`propose_model`, `ensemble_model`) -- none exist; gbrain rejected all three as
unknown keys. **So as of this version, `propose_takes` ignores `chat_model`
entirely and always calls Anthropic's API directly.** There is currently no
way to run the real deep-extract on a local model, or on a non-Anthropic
hosted model -- it's Anthropic-or-nothing for this specific phase. (A separate,
lighter phase, `extract_facts`, DID honor the `chat_model` swap in testing --
but it's not the expensive multi-turn one, and the doc's "deep-extract" advice
below is about `propose_takes`.)

This may change in a future gbrain release if a dedicated config key ships --
worth re-checking after an upgrade rather than assuming this is permanent.

## The cost/access trade-off, plainly

Because `propose_takes` only speaks to Anthropic, turning on the deep-extract
today means an **`ANTHROPIC_API_KEY` with pay-per-token API billing** -- this is
a *separate* thing from a Claude.ai/Claude Code subscription (Free/Pro/Max
plans do not include API access; API keys bill per token on their own metered
account, typically at console.anthropic.com). Concretely:

- **If you already pay for a Claude Code or Claude.ai plan:** that subscription
  does NOT cover this. You'd need to separately create an API key and expect a
  metered bill on top, sized to how much content dream chews through each
  night (small dollars for a personal-scale brain doing an 8B-ish equivalent
  model like Haiku, but not zero, and it compounds nightly).
- **If you don't want a second, metered account:** skip the deep-extract.
  Structural-only dream costs nothing and needs no key at all.

The ladder, in order: **structural-only (free, no key needed) -> a small
hosted model + pay-per-use API key for the extract (only real option today)
-> a strong local model, if/when gbrain adds a way to route `propose_takes`
away from Anthropic.** The deep-extract does NOT have to run locally in
principle, and it does NOT require codex -- but in practice, right now, it
does require an Anthropic API key and its associated spend.

## Run these once before your first dream (missing setup steps)

gbrain has setup steps that are NOT run automatically on install. Skip them
and dream runs silently -- no errors, but nothing useful happens because the
structural data the cycle depends on doesn't exist yet.

```bash
gbrain extract links --source db      # entity links (free, no LLM, ~minutes on large brains)
gbrain extract timeline --source db   # timeline coverage (free, no LLM)
gbrain onboard --check                # shows everything still missing
```

Run `gbrain onboard --check` first -- it lists what's outstanding. The link +
timeline steps are free (no model call), idempotent, and safe to re-run. Without
them, `propose_takes` has nothing to propose and all dream phases show zero
coverage.

## Getting a local model to work for chat (the alias trick)

gbrain only whitelists specific model IDs for the `openai:` provider (e.g.
`gpt-4o-mini`). `openai:gemma-4:something` gets rejected. `ollama:model` has no
chat touchpoint and silently does nothing.

The working path, when `OPENAI_BASE_URL=http://localhost:11434/v1` is set
(automatically true if you followed the embedding setup):

```bash
# alias your local model under the whitelisted name
ollama cp "hf.co/unsloth/gemma-4-E4B-it-GGUF:Q4_K_M" gpt-4o-mini
```

Then set `chat_model: openai:gpt-4o-mini` in config. Because `OPENAI_BASE_URL`
points at Ollama, the call goes to your local Gemma -- for free. `gbrain think`
and query expansion both work this way.

Validate: `gbrain providers test --touchpoint chat` -- should return a real
response, not an API error.

**File-plane config fields** can't be set via `gbrain config set` -- it rejects
them with "file-plane field that sizes the schema." Edit `~/.gbrain/config.json`
directly for:

- `embedding_model` -- which model powers embeddings
- `embedding_dimensions` -- must match the model's actual output size
- `takes.bootstrap_enabled` -- must be `true` before `gbrain takes extract` will run

## Before any of this: confirm autopilot's worker actually spawns

Everything below assumes dream jobs get to RUN. On a separate, more
fundamental Windows bug, `gbrain autopilot`'s own worker process can fail to
spawn at all (`ENOENT ... uv_spawn`), so every job -- structural or
LLM-driven -- sits `waiting` forever with no error surfaced anywhere except
the autopilot foreground log. If your sources stay stale no matter how long
autopilot has "been running," check that FIRST: see
`autopilot_worker_spawn_windows.md` for the diagnostic + fix. Don't debug
dream/deep-extract config on a daemon whose worker never even started.

## Two Windows gotchas that cost an hour each

1. **Use the `openai:` provider prefix, NOT `ollama:`, for the chat model.**
   gbrain's native `ollama` recipe is embed-only (its chat column is blank). The
   `openai` recipe routes to your local Ollama if `OPENAI_BASE_URL` is set to
   `http://localhost:11434/v1` (set automatically by the embedding setup), so
   `openai:<alias>` routes chat to Ollama, while `ollama:<model>` silently does
   nothing for chat. Validate with `gbrain providers test --touchpoint chat`.

2. **Route the nightly job's native output through cmd.exe, not PowerShell
   `2>&1`.** On Windows, redirecting a native command's stderr with PowerShell
   `2>&1` wraps each line as a NativeCommandError and can flip a success (exit 0)
   into a reported failure. In a scheduled `nightly.ps1`, invoke the gbrain
   commands so their native output goes through cmd.exe rather than a PS `2>&1`
   redirect, or your nightly "fails" while actually succeeding.

## Bottom line

The dream cycle is optional, and its valuable half (structural consolidation) is
free and model-free. The LLM deep-extract's payoff is real -- it turns buried
one-off lessons in your notes into standalone facts that resurface later
without you having to remember to search for them -- but as of gbrain
0.42.53.0, unlocking it means an `ANTHROPIC_API_KEY` on a pay-per-use billing
account (not covered by a Claude Code/Claude.ai subscription), because
`propose_takes` is hardcoded to Anthropic and ignores `chat_model`. If you
don't want that second metered account, you're not missing structural value --
run structural-only. If a few cents/night of API spend is fine for
"lessons find me instead of me finding them," add the key and point
`chat_model` at `anthropic:claude-haiku-4-5`.
