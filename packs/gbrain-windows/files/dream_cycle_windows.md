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

## Two Windows gotchas that cost an hour each

1. **Use the `openai:` provider prefix, NOT `ollama:`, for the chat model.**
   gbrain's native `ollama` recipe is embed-only (its chat column is blank). The
   `openai` recipe is already pointed at your local Ollama (localhost:11434/v1)
   from the embedding setup, so `openai:<local-model>` routes chat to Ollama,
   while `ollama:<model>` silently does nothing for chat. Validate with
   `gbrain providers test --touchpoint chat`.

2. **Route the nightly job's native output through cmd.exe, not PowerShell
   `2>&1`.** On Windows, redirecting a native command's stderr with PowerShell
   `2>&1` wraps each line as a NativeCommandError and can flip a success (exit 0)
   into a reported failure. In a scheduled `nightly.ps1`, invoke the gbrain
   commands so their native output goes through cmd.exe rather than a PS `2>&1`
   redirect, or your nightly "fails" while actually succeeding.

## Bottom line

The dream cycle is optional, and its valuable half (structural consolidation) is
free and model-free. Only reach for the LLM deep-extract if you have a reliable
chat model -- and on Windows the reliable cheap path is a small hosted model, not
a local 8B, and not a dependency on codex. If you don't have codex, you're not
missing anything: run structural-only, or point the extract at a cheap hosted
model.
