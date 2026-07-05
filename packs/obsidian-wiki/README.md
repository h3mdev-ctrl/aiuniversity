# obsidian-wiki

Sets up an **Obsidian-style LLM wiki** (a folder of linked markdown notes),
optionally **publishes it free**, and makes it **referenceable from memory** and
**queryable via gbrain**. Part of the KNOWLEDGE branch — not forced into the
foundation; add it when you want a knowledge base.

Choose with `--variant`: **local** (vault + memory link, nothing published —
default) or **hosted** (also published free via Quartz → Vercel Hobby / GitHub
Pages). The vault, memory-link, and gbrain steps run either way; only the publish
steps (which need Node + a free host) are hosted-only.

See [pack-structure.md](../../docs/pack-structure.md) for the section conventions.

## Contract

- **`vault`** creates the wiki: a home note, a starter note, a template, and a
  free-publishing guide (`PUBLISHING.md`).
- **`memory-linked`** points the memory index at the wiki so Claude knows the
  knowledge base exists and when to consult it — depends on the memory pack.
- **`node-present` / `published-free`** (hosted only) — confirm Node, then publish
  free via Quartz → Vercel/Pages and record the live URL.
- **`gbrain-queryable`** is behavioural — ingests the vault into gbrain and confirms
  a query surfaces the wiki's canary (`GREEN-HERON-4820`), proving it's genuinely
  searchable, not just present. Optional (needs gbrain).

## Iron Laws

- **A wiki memory can't reach is invisible.** The `memory-linked` step is what tells
  Claude the knowledge base exists; an unlinked vault is a folder nobody opens.
- **Prove searchable, don't assume.** "The notes exist" ≠ "Claude can find them".
  The canary query is the proof the wiki is actually queryable.
- **Free publishing is a first-class path.** The hosted variant deliberately routes
  through free tiers (Vercel Hobby / GitHub Pages) — publishing shouldn't cost money.
- **Standard markdown links, not `[[wiki-links]]`.** `[[...]]` doesn't render on
  GitHub/Quartz output; cross-references use `[Title](path.md)`.

## Anti-Patterns

- ❌ **Creating the vault and skipping the memory link.** Claude never learns the
  wiki exists, so it never consults it.
- ❌ **Running the hosted variant without Node.** `node-present` gates
  `published-free` for exactly this reason.
- ❌ **Assuming presence means searchable.** Skipping the gbrain ingest leaves the
  wiki unqueryable; the canary step catches it.
- ❌ **Using `[[wiki-links]]`** in notes you intend to publish — they break on
  GitHub-rendered output.

## Token cost (caveat — read before bulk ingest)

Setting up the vault is cheap. **Filling it is not.** A wiki ingest isn't one
write — it's one main page **plus N entity updates**, and the cross-referencing
pass is roughly **O(entities)**: each notable entity means *read its existing page
+ write a back-link + a timeline entry*. Ballpark:

- **One modest ingest** (~6 entities): **~20–30k tokens.**
- **One dense longread / 30-min video** (~15 entities, timeline-merge onto every
  page): **~50k+.**
- **A week's batch of ~10 items:** **~250–500k tokens.** The entity/cross-ref pass
  is typically ~half of that — it's the part that "uses up a lot".

**Keep it affordable:**
- **Delegate the bulk page-writing to Sonnet/Haiku sub-agents, off the main
  (Opus) context** — cheaper per token AND keeps your window clean. This is how a
  production ingest is built (orchestrator synthesises hubs; workers write pages).
- **Cap cross-links to genuinely notable entities.** The "back-link every mention"
  Iron Law is thorough but it's the multiplier; a notability gate cuts the entity
  count that drives cost.
- **Test 3 items before a batch.** The marginal cost of testing 3 is near zero;
  re-cleaning 100 bad pages (and paying for them twice) is not.

## Related packs

- [`memory`](../memory/) — prerequisite for the `memory-linked` step.
- [`gbrain-windows`](../gbrain-windows/) — provides the semantic search the
  `gbrain-queryable` step exercises; same KNOWLEDGE branch.
- [`docs/skill-tree.md`](../../docs/skill-tree.md) — where the KNOWLEDGE branch and
  its variants are described.
