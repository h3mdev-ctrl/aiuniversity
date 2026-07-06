# The gbrain mental model: one hub, many spokes

> Read this BEFORE you try to explain "how would gbrain help me?" — because the
> single most common mistake is framing gbrain as the *mirror of one project*
> when it's the opposite: **gbrain is the hub, and each project is a spoke that
> feeds it.** Getting the direction right is what makes the whole thing click.

## The model in one line

**gbrain is the single brain you talk to. Everything you do — work, trading, a
solar project, an electricity project, running, a side business — is a spoke that
feeds the same hub.** You don't spin up a brain per project; you have ONE brain,
and projects are namespaces inside it.

```
                         ┌─────────────────────┐
        work ──────────► │                     │ ◄────────── trading
                         │       gbrain        │
   solar project ──────► │   (the ONE hub you  │ ◄────────── running / health
                         │      talk to)       │
   electricity project ►│                     │ ◄────────── people you know
                         └─────────────────────┘
        every domain writes to it + reads from it; it connects across them
```

The payoff is the *connections across spokes*: the discipline you learn in trading
shows up in how you run a project; a person you met via the solar job turns out to
matter for work. A per-project notes folder can never surface that. One hub can.

## The mistake to avoid (the "mirror" trap)

If someone asks "how is gbrain useful for my running?" the wrong instinct is to
describe a *running brain* — a store that mirrors the running project. That makes
gbrain sound like a fancy notes app for one thing, and it's underwhelming, so the
person shrugs.

The right answer: "gbrain isn't your running brain — it's your **one** brain, and
running is one thing it holds, next to your work, your projects, and the people you
know. The value is that it remembers across all of them and connects them."

## How the spokes are namespaced (so one hub stays organised)

Each domain is a slug prefix — a spoke — inside the single brain:

| Spoke (life/work domain) | Slug prefix |
|---|---|
| A specific project | `projects/<name>/…` (e.g. `projects/solar/…`, `projects/electricity/…`) |
| Work / your job | `work/…` |
| Trading / investing | `trading/…` |
| Health / running / training | `health/…` or `running/…` |
| A person, company, or tool (crosses every spoke) | `people/<name>`, `companies/<slug>`, `concepts/<slug>` |
| Your own original ideas / theses | `originals/<slug>` or `ideas/<slug>` |
| Daily logs / session notes | `daily/<YYYY-MM-DD>` |

The **entity layer** (`people/`, `companies/`, `concepts/`) is deliberately NOT
under a project — those are the shared nouns that connect spokes. The person you
met on the solar job lives at `people/<name>`, and both `projects/solar/` and
`work/` back-link to them. That cross-spoke link is the whole point.

(Filing *mechanics* — slug rules, attribution, back-linking — are in
`example_brain_filing.md`; the shape of a good page is in `example_brain_page.md`.
This file is the mental model those two sit inside.)

## Explaining it to a newcomer (the script)

When someone asks what gbrain does for them, answer in this order:

1. **It's one brain, not one-per-project.** "You talk to a single brain; everything
   you do feeds it."
2. **Name their spokes back to them.** "So your electricity project, your solar
   project, your trading, your work, your running — those are all just areas inside
   the one brain."
3. **Sell the connection, not the storage.** "The value isn't that it stores each
   area — it's that it remembers across them and links them, which a folder of notes
   never does."
4. **Make it concrete.** Pick two of their spokes and name a real bridge — a person,
   a lesson, a supplier — that matters to both.

If you can do step 4 for a real person, they get it instantly. That's the tutor's
job: don't define gbrain, *show them their own hub.*
