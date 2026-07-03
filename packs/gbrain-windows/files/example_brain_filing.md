# Filing rules for your brain -- EXAMPLE (learn the STRUCTURE)

> Based on a real personal knowledge brain. A brain with no filing rules becomes a
> junk drawer; a `resolver` page like this keeps every page findable. Copy the
> slug conventions; replace the topics. (Inspired by Garry Tan's brain
> filing-rules pattern.)
>
> Tip: save a page like this into your own brain at slug `resolver`, and consult
> it before writing a new page.

## Slug conventions -- intent -> slug

| What you're saving | Slug pattern |
|---|---|
| A person (author, expert, someone you track) | `people/<name>` e.g. `people/jane-doe` |
| A concept / idea / technique / pattern | `concepts/<slug>` e.g. `concepts/spaced-repetition` |
| A Map of Content (index page for a theme) | `concepts/<slug>-moc` |
| A company / product / organisation | `companies/<slug>` |
| A curated note from one long source (book, talk) | `sources/<slug>` |
| Your OWN original idea or thesis (not extracted) | `originals/<slug>` or `ideas/<slug>` |
| A daily log / session note | `daily/<YYYY-MM-DD>` |

## Conventions

- **Attribute sources inline:** `[Source: <who>, <YYYY-MM-DD>]`, so every claim
  carries where it came from.
- **Back-link entities:** when a page mentions a person/company/concept that has
  its own page, link it -- that's what keeps the graph connected and queryable.
- **One page per thing.** Don't scatter the same entity across five pages; update
  the one canonical page.
- **The `resolver` page IS the filing map.** Consult it before writing a new page;
  if your intent has no row, that's a gap -- add a row.

See `example_brain_page.md` for a well-structured page.
