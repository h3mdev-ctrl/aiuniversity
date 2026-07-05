#!/usr/bin/env python
"""vault_crosslink.py -- deterministic cross-link maintenance for an LLM wiki.

WORKED EXAMPLE for aiuniversity. This is the reference implementation of the
"script the deterministic 80%" lever the knowledge-ingest modules should use (see
docs/planned-knowledge-ingest.md). It was validated live on a real 853-page,
18,000-wikilink Obsidian wiki -- it added 121 missing backlinks and de-linked 25
namespace leaks for ZERO model tokens (the same work by hand was ~150-350k tokens
of a top-tier model).

The point it proves: cross-referencing in an ingest looks like an LLM job, but its
expensive part -- the O(entities) backlink grind (open each target page, append a
line) -- is pure string manipulation. It needs no model at all. Reserve the model
for the synthesis (the prose that explains *why* two entities relate); let a script
do the plumbing (the links themselves).

Modes (every mutating mode is DRY-RUN by default; pass --apply to write):
  --audit     READ-ONLY. Broken wikilinks (target page missing) + missing
              entity<->entity backlink reciprocity (A lists [[B]] under a
              "Connected Entities" section but B doesn't list [[A]] back).
  --broken    Triage the dangling links into bug / should-exist / intentional.
  --fix       Add the missing reciprocal backlinks (bare `- [[A]]` lines).
  --fix-bugs  De-link namespace leaks (`[[project_x]]` -> `project_x`) -- links to
              a different namespace (a memory/notes slug) that can never resolve as
              a wiki page and render broken in the published site.

Point $WIKI_DIR at your wiki root (a folder of `entities/`, `sources/`, `concepts/`
markdown), or run from a dir that has a `wiki/` subfolder.

    WIKI_DIR=~/my-wiki python vault_crosslink.py --audit
    WIKI_DIR=~/my-wiki python vault_crosslink.py --fix          # dry-run
    WIKI_DIR=~/my-wiki python vault_crosslink.py --fix --apply   # write
"""
import argparse
import collections
import os
import pathlib
import re
import sys

WIKI = pathlib.Path(os.environ.get("WIKI_DIR") or "wiki")
DIRS = ["entities", "sources", "concepts"]
LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]")
CONNECTED = "Connected Entities"   # the section that should be reciprocal between entities


def _norm(target: str) -> str:
    """Normalize a wikilink target to a bare slug (wiki/entities/foo -> foo), so
    path-style and bare-slug links resolve the same."""
    return target.strip().rstrip("/").split("/")[-1]


def load():
    slug2path, text = {}, {}
    for d in DIRS:
        for p in (WIKI / d).glob("*.md"):
            slug2path[p.stem] = p
            text[p.stem] = p.read_text(encoding="utf-8", errors="replace")
    return slug2path, text


def links_in(body: str):
    return [_norm(m.group(1)) for m in LINK_RE.finditer(body)]


def section_span(body: str, name: str):
    """Return (start, end) char offsets of a '## <name>' section body, or None."""
    m = re.search(rf"(?m)^##\s+{re.escape(name)}\s*$", body)
    if not m:
        return None
    start = m.end()
    nxt = re.search(r"(?m)^##\s+", body[start:])
    end = start + nxt.start() if nxt else len(body)
    return (start, end)


def section_text(body: str, name: str) -> str:
    span = section_span(body, name)
    return body[span[0]: span[1]] if span else ""


def entity_slugs():
    return {p.stem for p in (WIKI / "entities").glob("*.md")}


def compute(text):
    """broken: slug -> [source pages]; missing_back: [(A, B)] where A lists B but
    B doesn't list A back."""
    all_slugs = set(text)
    ents = entity_slugs()
    broken = collections.defaultdict(list)
    for slug, body in text.items():
        for tgt in links_in(body):
            if tgt not in all_slugs:
                broken[tgt].append(slug)
    conn = {e: {t for t in links_in(section_text(text[e], CONNECTED)) if t in ents} for e in ents}
    missing_back = [(a, b) for a, tgts in conn.items() for b in tgts if a not in conn.get(b, set())]
    return broken, missing_back, conn


# A dangling target whose slug is in another namespace (a memory / notes file) leaked
# into a wiki page -- it can never resolve as a wikilink and renders broken in the
# published site. That's a real bug (safe to de-link). Everything else dangling is
# either a page that SHOULD exist (high frequency) or an intentional passing mention.
MEM_PREFIXES = ("project_", "feedback_", "reference_", "user_", "index_")
MEM_EXACT = {"memory", "catalog"}
SHOULD_EXIST_MIN = 8   # dangled this many times -> a real page is probably missing


def classify(slug: str, freq: int) -> str:
    s = slug.lower()
    if s.startswith(MEM_PREFIXES) or s in MEM_EXACT:
        return "bug"
    return "should-exist" if freq >= SHOULD_EXIST_MIN else "intentional"


def do_broken(text) -> int:
    broken, _, _ = compute(text)
    buckets = collections.defaultdict(list)
    for slug, srcs in broken.items():
        buckets[classify(slug, len(srcs))].append((slug, len(srcs), srcs))
    for name in ("bug", "should-exist", "intentional"):
        rows = sorted(buckets[name], key=lambda r: -r[1])
        n_links = sum(r[1] for r in rows)
        print(f"\n=== {name.upper()} : {len(rows)} target(s), {n_links} link(s) ===")
        if name == "bug":
            print("  (namespace slugs leaked into wiki pages -- --fix-bugs de-links these)")
        if name == "should-exist":
            print(f"  (dangled >= {SHOULD_EXIST_MIN}x -- a real page is probably missing; NOT auto-fixable)")
        limit = None if name == "bug" else 15
        for slug, freq, srcs in (rows if limit is None else rows[:limit]):
            print(f"  [[{slug}]]  x{freq}   e.g. {', '.join(sorted(set(srcs))[:3])}")
        if limit and len(rows) > limit:
            print(f"  ... +{len(rows) - limit} more")
    return 0


def do_fix_bugs(slug2path, text, apply: bool) -> int:
    """De-link namespace leaks: [[project_x]] -> project_x (strip brackets, keep the
    text; keep the alias if it was [[project_x|Alias]]). Dry-run unless --apply."""
    broken, _, _ = compute(text)
    bug_slugs = {s for s in broken if classify(s, len(broken[s])) == "bug"}
    print(f"{'APPLYING' if apply else 'DRY-RUN'}: de-link {len(bug_slugs)} namespace leak target(s)\n")
    edited_files = delinked = shown = 0
    for slug, body in text.items():
        new = body
        for bug in bug_slugs:
            def repl(m):
                return m.group(2) if m.group(2) else m.group(1)   # alias, else the slug text
            pat = re.compile(r"\[\[(" + re.escape(bug) + r")(?:\|([^\]]*))?\]\]")
            new2, n = pat.subn(repl, new)
            if n:
                new = new2
                delinked += n
                if shown < 8:
                    print(f"  {slug}.md  --  de-linked [[{bug}]] ({n}x)")
                    shown += 1
        if new != body:
            edited_files += 1
            if apply:
                slug2path[slug].write_text(new, encoding="utf-8")
    print(f"\n{'DE-LINKED' if apply else 'WOULD DE-LINK'}: {delinked} link(s) across {edited_files} page(s).")
    if not apply:
        print("Re-run with --apply to write.")
    return 0


def do_audit(text) -> int:
    broken, missing_back, _ = compute(text)
    n_broken_links = sum(len(v) for v in broken.values())
    print(f"WIKI: {len(entity_slugs())} entities, {len(text)} pages, "
          f"{sum(len(links_in(b)) for b in text.values())} wikilinks\n")
    print(f"[1] BROKEN WIKILINKS: {n_broken_links} link(s) -> {len(broken)} missing target(s)")
    for tgt, srcs in sorted(broken.items(), key=lambda kv: -len(kv[1]))[:12]:
        print(f"    [[{tgt}]]  <- {len(srcs)}x")
    print(f"\n[2] MISSING BACKLINKS (entity<->entity reciprocity): {len(missing_back)} one-way link(s)")
    for a, b in missing_back[:12]:
        print(f"    [[{a}]] -> [[{b}]]   (add [[{a}]] to {b})")
    if len(missing_back) > 12:
        print(f"    ... +{len(missing_back) - 12} more")
    return 0


def _append_to_connected(body: str, line: str) -> str:
    """Append `line` to the Connected Entities section, creating it at EOF if absent.
    Preserves the original trailing blank line(s) so a following '## heading' keeps
    its blank-line separation (markdown needs it)."""
    span = section_span(body, CONNECTED)
    if span is None:
        sep = "" if body.endswith("\n") else "\n"
        return f"{body}{sep}\n## {CONNECTED}\n{line}\n"
    start, end = span
    chunk = body[start:end]
    stripped = chunk.rstrip("\n")
    trailing = chunk[len(stripped):] or "\n"   # keep the original blank-line run
    return body[:start] + stripped + "\n" + line + trailing + body[end:]


def do_fix(slug2path, text, apply: bool) -> int:
    _, missing_back, _ = compute(text)
    by_target = collections.defaultdict(list)   # group by page needing the backlink, so each opens once
    for a, b in missing_back:
        by_target[b].append(a)

    edits = created_section = 0
    print(f"{'APPLYING' if apply else 'DRY-RUN'}: {len(missing_back)} reciprocal backlink(s) "
          f"across {len(by_target)} page(s)\n")
    for b, adders in sorted(by_target.items()):
        body = text[b]
        had_section = section_span(body, CONNECTED) is not None
        new_body = body
        for a in sorted(set(adders)):
            if a in set(links_in(section_text(new_body, CONNECTED))):   # idempotent
                continue
            line = f"- [[{a}]]"   # bare link -- asserts no directional claim; enrich later if wanted
            new_body = _append_to_connected(new_body, line)
            edits += 1
            if edits <= 6:
                print(f"  {b}.md  +=  {line}")
        if not had_section and new_body != body:
            created_section += 1
        if apply and new_body != body:
            slug2path[b].write_text(new_body, encoding="utf-8")

    if edits > 6:
        print(f"  ... +{edits - 6} more appends")
    print(f"\n{'WROTE' if apply else 'WOULD WRITE'}: {edits} backlink line(s); "
          f"{created_section} page(s) get a new '## {CONNECTED}' section.")
    if not apply:
        print("Re-run with --apply to write. (Idempotent -- safe to run again.)")
    return 0


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="deterministic wiki cross-link maintenance")
    ap.add_argument("--audit", action="store_true", help="read-only overview report")
    ap.add_argument("--broken", action="store_true", help="triage dangling links: bug / should-exist / intentional")
    ap.add_argument("--fix", action="store_true", help="add missing reciprocal backlinks (dry-run unless --apply)")
    ap.add_argument("--fix-bugs", action="store_true", help="de-link namespace leaks (dry-run unless --apply)")
    ap.add_argument("--apply", action="store_true", help="actually write (with --fix / --fix-bugs)")
    a = ap.parse_args(argv)
    if not WIKI.exists():
        print(f"wiki not found at {WIKI} (set $WIKI_DIR)")
        return 1
    slug2path, text = load()
    if a.fix_bugs:
        return do_fix_bugs(slug2path, text, apply=a.apply)
    if a.fix:
        return do_fix(slug2path, text, apply=a.apply)
    if a.broken:
        return do_broken(text)
    return do_audit(text)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main(sys.argv[1:]))
