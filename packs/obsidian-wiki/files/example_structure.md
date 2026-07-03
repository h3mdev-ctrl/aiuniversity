# Wiki structure -- EXAMPLE filing guide (learn the STRUCTURE, replace the content)

> Based on a real, published knowledge wiki. Copy the folder layout + conventions;
> the topics here are generic placeholders. The idea: every note has ONE home by
> intent, and everything links by [[wikilink]] regardless of which folder it's in.

## Folders -- content type -> location

| What it is | Folder | Slug pattern |
|---|---|---|
| A person (author, expert, someone you track) | `entities/` | `jane-doe`, `the-daily-brief` |
| A concept / idea / technique / pattern | `concepts/` | `spaced-repetition`, `deep-work` |
| A Map of Content (index page for a theme) | `concepts/` | `learning-techniques-moc` |
| A curated note distilled from one long source (book, talk, essay) | `sources/` | `make-it-stick-summary` |
| Your OWN original thesis (not extracted from a source) | `originals/` | (your first one defines the pattern) |

## Conventions

- **Every note has frontmatter:** `title`, `type` (concept / moc / entity / source),
  `tags` (list), and `sources` (list of `[[wikilinks]]` it draws on).
- **Open with a `**One-liner:**`** -- a single distilled sentence, with `[[wikilinks]]`
  to the concepts it touches. This is what makes the wiki *answerable*: the
  one-liner is the searchable thesis, not the whole note.
- **Link liberally with `[[wikilinks]]`.** Use `[[slug|shown text]]` to alias.
  Links resolve across the whole vault, so filing is about *ownership*, not reach.
- **Maps of Content (MOCs)** are index pages: one anchor per theme that routes to
  the concepts, people, and sources under it. A vault without MOCs is a pile of
  notes; MOCs make it navigable.
- **Publish status:** if you publish (Quartz -> free host), keep anything private
  OUTSIDE the published folder. Filing decides what goes public.

See `_example_concept.md` for a note's shape and `_example_moc.md` for a Map of
Content.
