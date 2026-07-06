# The gbrain mental model: one hub, many spokes

> Read this BEFORE you try to explain "how would gbrain help me?" — because the
> single most common mistake is framing gbrain as the *mirror of one project* when
> it's the opposite: **gbrain is the hub, and each area of your life is a spoke that
> feeds it.** Getting the direction right is what makes the whole thing click.

## The model in one line

**gbrain is the single brain you talk to. Everything you do — work, your business
(clients, network, deals), your hobbies, your side projects, the people you know —
is a spoke that feeds the same hub.** You don't spin up a brain per area; you have
ONE brain, and each area is a namespace inside it.

```
                         ┌─────────────────────┐
        work ──────────► │                     │ ◄────────── side projects
                         │       gbrain        │
   clients / network ──► │   (the ONE hub you  │ ◄────────── hobbies / interests
                         │      talk to)       │
   people you know ────► │                     │ ◄────────── whatever else you do
                         └─────────────────────┘
        every area writes to it + reads from it; it connects across them
```

The payoff is the *connections across spokes*: a lesson from one side project shows
up in another; a person you met through a client turns out to matter for a hobby
group. A per-area notes folder can never surface that. One hub can.

## The mistake to avoid (the "mirror" trap)

If someone asks "how is gbrain useful for my hobby / my side project?" the wrong
instinct is to describe a brain that *mirrors that one thing* — a store for just the
hobby. That makes gbrain sound like a fancy notes app for one area, and it's
underwhelming, so the person shrugs.

The right answer: "gbrain isn't your hobby brain — it's your **one** brain, and the
hobby is one thing it holds, next to your work, your business, your other projects,
and the people you know. The value is that it remembers across all of them and
connects them."

## How the spokes are namespaced (so one hub stays organised)

Each area is a slug prefix — a spoke — inside the single brain:

| Spoke (area of your life) | Slug prefix |
|---|---|
| Work / your job | `work/…` |
| Your business — clients, network, deals | `business/…` (or `clients/…`) |
| A specific side project | `projects/<name>/…` |
| A hobby / interest | `hobbies/<name>/…` |
| A person, company, or tool (crosses every spoke) | `people/<name>`, `companies/<slug>`, `concepts/<slug>` |
| Your own original ideas / theses | `originals/<slug>` or `ideas/<slug>` |
| Daily logs / session notes | `daily/<YYYY-MM-DD>` |

The **entity layer** (`people/`, `companies/`, `concepts/`) is deliberately NOT under
an area — those are the shared nouns that connect spokes. A person you met through a
client lives at `people/<name>`, and both `business/` and whatever project they touch
back-link to them. That cross-spoke link is the whole point.

(Filing *mechanics* — slug rules, attribution, back-linking — are in
`example_brain_filing.md`; the shape of a good page is in `example_brain_page.md`.
This file is the mental model those two sit inside.)

## Explaining it to a newcomer (the script)

When someone asks what gbrain does for them, answer in this order:

1. **It's one brain, not one-per-area.** "You talk to a single brain; everything you
   do feeds it."
2. **Name their spokes back to them.** "So your work, your clients, your side
   projects, your hobbies — those are all just areas inside the one brain."
3. **Sell the connection, not the storage.** "The value isn't that it stores each
   area — it's that it remembers across them and links them, which a folder of notes
   never does."
4. **Make it concrete.** Pick two of their areas and name a real bridge — a person, a
   lesson, a contact — that matters to both.

If you can do step 4 for a real person, they get it instantly. That's the tutor's
job: don't define gbrain, *show them their own hub.*
