#!/usr/bin/env python
"""
setup_wiki.py -- set up an Obsidian-style LLM wiki, wire it into memory, and
track its free published URL.

A wiki is just a folder of linked markdown notes (that IS an Obsidian vault). It
publishes for free with Quartz -> Vercel Hobby / GitHub Pages, and it becomes
LLM-queryable either by reading notes directly or by ingesting into gbrain.

    <wiki-home>/
      index.md            home note (links out with [[wikilinks]])
      getting-started.md   a real starter note (+ a queryable canary phrase)
      _template.md         copy this to make a new note
      PUBLISHING.md        the free deploy guide (Quartz + Vercel/Pages)
      .obsidian/app.json   marks the folder as an Obsidian vault
      .publish_url         where it's live (set after you deploy)

Modes:
    (no arg) / --install       create the vault if missing (idempotent)
    --check                    exit 0 if the vault exists, else 1
    --link-memory              add a reference_wiki memory + resolver row so the
                               memory index points at the wiki (needs the memory pack)
    --check-memory-link        exit 0 if memory references the wiki, else 1
    --set-url <url>            record the free published URL
    --check-published          exit 0 if the published URL is reachable, else 1

Homes: wiki = $WIKI_HOME or (<$CLAUDE_HOME or ~/.claude>)/wiki ; memory = same base
/memory. (Env overrides let tests/demos run against a throwaway home.)
"""
import os
import pathlib
import sys

WIKI_CANARY = "GREEN-HERON-4820"


def base_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))


def wiki_dir() -> pathlib.Path:
    return pathlib.Path(os.environ["WIKI_HOME"]) if os.environ.get("WIKI_HOME") else base_dir() / "wiki"


def mem_dir() -> pathlib.Path:
    return base_dir() / "memory"


INDEX_MD = """# Home

Welcome to your knowledge wiki -- an Obsidian vault (a folder of linked markdown
notes) that doubles as an LLM-queryable knowledge base.

## Start here
- [[getting-started]] -- how this wiki works
- [[_template]] -- copy this to make a new note

## Learn the structure (worked examples)
- `_example_structure.md` -- how to file notes (folders, slugs, publish status)
- `_example_concept.md` -- what a concept note looks like (frontmatter + One-liner)
- `_example_moc.md` -- a Map of Content (index page that makes the vault navigable)

Write notes as markdown, link them with [[double brackets]]. Publish for free with
Quartz (see `PUBLISHING.md`). Query them by reading directly, or ingest into gbrain
(`gbrain import` this folder).
"""

GETTING_STARTED_MD = """---
title: Getting Started
tags: [meta]
---

# Getting Started

This is your LLM wiki. It does three things:

1. **Notes** -- plain markdown you write and link with [[wikilinks]].
2. **Published** -- Quartz renders it to a static site, hosted free.
3. **Queryable** -- an LLM (Claude, or gbrain) can search and answer from it.

The wiki canary phrase is **{canary}** -- used to prove the wiki is actually
queryable end to end (ingest this note, then ask for the canary).
""".format(canary=WIKI_CANARY)

TEMPLATE_MD = """---
title: <note title>
tags: []
---

# <note title>

<Your note. Link related notes with [[their-slug]].>
"""

PUBLISHING_MD = """# Publishing this wiki for free

This vault publishes as a static site with **Quartz** (free, open-source) on a
**free host** (Vercel Hobby or GitHub Pages). One-time setup:

1. Install Node (https://nodejs.org) -- check: `node --version`.
2. Get Quartz: `git clone https://github.com/jackyzha0/quartz && cd quartz && npm i`
3. Point Quartz's `content` at this vault folder, then build:
   `npx quartz build` -> produces a `public/` folder.
4. Deploy free:
   - Vercel:  `npx vercel --prod`   (Hobby tier, free)
   - GitHub Pages: push and enable Pages on the built `public/` via a workflow.
5. Tell the pack your URL so it can verify it's live:
   `python packs/obsidian-wiki/files/setup_wiki.py --set-url https://your-wiki.vercel.app`
"""

REFERENCE_WIKI_MD = """---
name: reference-wiki
description: When you need background knowledge, notes, or context you've written down -- the LLM wiki has it.
type: reference
---

Your knowledge wiki (an Obsidian vault) lives at `{vault}` and is published at
`{url}`. It's an LLM-queryable knowledge base: read notes directly, or query gbrain
if you've ingested it (`gbrain import {vault}`). The wiki canary is `{canary}`.
"""

MEMORY_WIKI_BLOCK = """
### Knowledge wiki

| When you're about to... | Consult |
|---|---|
| look up background knowledge or notes you've written down | [reference_wiki](reference_wiki.md) |
"""


def install() -> int:
    w = wiki_dir()
    (w / ".obsidian").mkdir(parents=True, exist_ok=True)
    wrote: list[str] = []
    for name, content in (
        ("index.md", INDEX_MD),
        ("getting-started.md", GETTING_STARTED_MD),
        ("_template.md", TEMPLATE_MD),
        ("PUBLISHING.md", PUBLISHING_MD),
    ):
        p = w / name
        if not p.exists():
            p.write_text(content, encoding="utf-8")
            wrote.append(name)
    app = w / ".obsidian" / "app.json"
    if not app.exists():
        app.write_text("{}\n", encoding="utf-8")
        wrote.append(".obsidian/app.json")

    # Ship worked examples (a filing guide + a concept note + a Map of Content) so
    # Claude has a concrete structure to copy. Prefixed "_" so Quartz/tools treat
    # them as drafts, not published pages.
    here = pathlib.Path(__file__).resolve().parent
    for src in sorted(here.glob("example_*.md")):
        dst = w / ("_" + src.name)
        if not dst.exists():
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            wrote.append(dst.name)

    print(f"wiki home: {w}")
    print("created: " + (", ".join(wrote) if wrote else "(nothing -- already set up)"))
    return 0


def check() -> int:
    return 0 if (wiki_dir() / "index.md").exists() else 1


def read_url() -> str:
    p = wiki_dir() / ".publish_url"
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def set_url(url: str) -> int:
    w = wiki_dir()
    w.mkdir(parents=True, exist_ok=True)
    (w / ".publish_url").write_text(url.strip() + "\n", encoding="utf-8")
    print(f"recorded published URL: {url.strip()}")
    return 0


def check_published() -> int:
    import urllib.request

    url = read_url()
    if not url:
        print("no published URL set yet (run --set-url after you deploy)")
        return 1
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:  # noqa: S310
            ok = 200 <= resp.status < 400
        print(f"{'reachable' if ok else 'unreachable'}: {url}")
        return 0 if ok else 1
    except Exception as exc:  # noqa: BLE001
        print(f"unreachable: {url} ({exc})")
        return 1


def link_memory() -> int:
    mem = mem_dir()
    index = mem / "MEMORY.md"
    if not index.exists():
        print("no memory system found -- run the memory pack first (packs/memory)")
        return 1
    ref = mem / "reference_wiki.md"
    if not ref.exists():
        ref.write_text(
            REFERENCE_WIKI_MD.format(
                vault=wiki_dir(), url=read_url() or "not published yet", canary=WIKI_CANARY
            ),
            encoding="utf-8",
        )
    text = index.read_text(encoding="utf-8")
    if "reference_wiki" not in text:
        index.write_text(text.rstrip() + "\n" + MEMORY_WIKI_BLOCK, encoding="utf-8")
    print(f"linked wiki into {index}")
    return 0


def check_memory_link() -> int:
    index = mem_dir() / "MEMORY.md"
    ok = (
        index.exists()
        and "reference_wiki" in index.read_text(encoding="utf-8")
        and (mem_dir() / "reference_wiki.md").exists()
    )
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--install"
    if mode == "--install":
        return install()
    if mode == "--check":
        return check()
    if mode == "--link-memory":
        return link_memory()
    if mode == "--check-memory-link":
        return check_memory_link()
    if mode == "--check-published":
        return check_published()
    if mode == "--set-url":
        if len(argv) < 3:
            print("usage: --set-url <url>")
            return 2
        return set_url(argv[2])
    print(f"unknown mode {mode!r}")
    return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main(sys.argv))
