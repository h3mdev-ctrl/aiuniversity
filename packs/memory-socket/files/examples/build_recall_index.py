#!/usr/bin/env python3
"""
build_recall_index.py -- build the OPTIONAL semantic index for recall_on_prompt.py.

WHAT IS EMBEDDED: each memory's `description:` frontmatter (plus its `name:`),
NOT the body. A description written as "when you're about to X" has the same
shape as the situation a user types, so query and document land in the same
space. Embedding a 200-line body averages the signal into mush. A memory with
no description falls back to its first prose paragraph rather than silently
vanishing from the index.

Default embedder: a local ollama server running qwen3-embedding:0.6b (1024 dims,
no network, no cost). Anything that speaks ollama's /api/embed works; point
RECALL_EMBED_URL / RECALL_EMBED_MODEL at it. Use 127.0.0.1, not localhost -- on
Windows `localhost` tries ::1 first and costs ~0.13s per call.

USAGE
  python build_recall_index.py <memory_dir>          build / refresh
  python build_recall_index.py <memory_dir> --check  report staleness only

Writes <memory_dir>/.recall/semantic_index.json (source of truth) and, when
numpy is installed, a .npy sidecar the hook loads in milliseconds. Rebuild after
you add or edit memories; the recall hook only reads.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time
import urllib.request

EMBED_URL = "http://127.0.0.1:11434/api/embed"
EMBED_MODEL = "qwen3-embedding:0.6b"
BATCH = 32

FM = re.compile(r"^---\s*\n(.*?)\n---", re.S)
DESC = re.compile(r'^description:\s*["\']?(.+?)["\']?\s*$', re.M)
NAME = re.compile(r'^name:\s*["\']?(.+?)["\']?\s*$', re.M)
SKIP = {"MEMORY.md", "CATALOG.md"}


def doc_text(p: pathlib.Path) -> str | None:
    txt = p.read_text(encoding="utf-8", errors="replace")
    m = FM.match(txt)
    desc = name = ""
    if m:
        d, n = DESC.search(m.group(1)), NAME.search(m.group(1))
        desc = " ".join(d.group(1).split()) if d else ""
        name = " ".join(n.group(1).split()) if n else ""
    if not desc:
        body = txt[m.end():] if m else txt
        desc = next((" ".join(s.split()) for s in body.split("\n\n")
                     if s.strip() and not s.strip().startswith("#")), "")
    if not desc:
        return None
    return (f"{name}. {desc}" if name else desc)[:600]


def embed(texts: list[str], url: str, model: str) -> list[list[float]]:
    body = json.dumps({"model": model, "input": texts, "keep_alive": "30m"}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:   # a cold load is slow; building is not a hook
        d = json.load(r)
    return d.get("embeddings") or [d["embedding"]]


def unit(v: list[float]) -> list[float]:
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    memdir = pathlib.Path(args[0])
    out = memdir / ".recall" / "semantic_index.json"
    files = [p for p in sorted(memdir.glob("*.md"))
             if p.name not in SKIP and not p.name.startswith(("INDEX_", "_"))]
    if "--check" in sys.argv:
        built = out.stat().st_mtime if out.is_file() else 0
        stale = [p.name for p in files if p.stat().st_mtime > built]
        print(f"{len(stale)} of {len(files)} memories newer than the index"
              + (f" (e.g. {stale[0]})" if stale else ""))
        return 1 if stale else 0

    url = os.environ.get("RECALL_EMBED_URL", EMBED_URL)
    model = os.environ.get("RECALL_EMBED_MODEL", EMBED_MODEL)
    pairs = [(p.name, t) for p in files if (t := doc_text(p))]
    vectors: list[list[float]] = []
    for i in range(0, len(pairs), BATCH):
        vectors += [unit(v) for v in embed([t for _, t in pairs[i:i + BATCH]], url, model)]

    # OUTPUT GATE: never overwrite a good index with a degraded one.
    dims = {len(v) for v in vectors}
    if not pairs or len(vectors) != len(pairs) or len(dims) != 1:
        raise SystemExit(f"refusing to write: {len(pairs)} docs, {len(vectors)} vectors, "
                         f"dims={sorted(dims)}")

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps({"model": model, "built": time.time(),
                               "targets": [n for n, _ in pairs], "vectors": vectors}),
                   encoding="utf-8")
    os.replace(tmp, out)
    try:
        import numpy as np
        npy_tmp = out.with_name("semantic_index.tmp.npy")
        np.save(npy_tmp, np.asarray(vectors, dtype=np.float32))
        os.replace(npy_tmp, out.with_suffix(".npy"))
    except ImportError:
        pass
    print(f"indexed {len(pairs)} of {len(files)} memories, all {dims.pop()}-dim, "
          f"model={model} -> {out}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
