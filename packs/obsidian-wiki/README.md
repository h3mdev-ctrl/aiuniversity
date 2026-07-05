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

## Related packs

- [`memory`](../memory/) — prerequisite for the `memory-linked` step.
- [`gbrain-windows`](../gbrain-windows/) — provides the semantic search the
  `gbrain-queryable` step exercises; same KNOWLEDGE branch.
- [`docs/skill-tree.md`](../../docs/skill-tree.md) — where the KNOWLEDGE branch and
  its variants are described.
