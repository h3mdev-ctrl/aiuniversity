---
name: wrap-up
description: End-of-session close-out. Runs the ship gate (via /ship + /land-and-deploy if gstack is installed, or a fallback commit+push if not), the deploy gate for any publishable artefacts, then the 6-stage autolearn pipeline (Observe → Critique → Generate → Validate → Apply → Consolidate). Fires when the user says "wrap up", "wrap it up", "close out", "let's wrap", or invokes /wrap-up directly.
---

# wrap-up — session close-out procedure

**Fires when:** user says "wrap up", "wrap it up", "close out", "let's wrap",
"call it a wrap", or invokes `/wrap-up`.

**No stage is optional** — but individual steps within a stage may be skipped when
their preconditions genuinely don't apply (see per-stage skip rules).

The autolearn principles this skill applies live in the aiuniversity `autolearn`
pack's workflow guide (`phantom_workflow.md`). Read that file for the bidirectional
success/failure scan, tiered writes, deterministic verification, and type-aware
retirement rules.

---

## Part 1 — Ship gate (MANDATORY when there's a diff)

**Detect the shipping toolchain first.** Two paths:

### Path A — gstack installed (Garry Tan's `/ship` + `/land-and-deploy`)

If `/ship` and `/land-and-deploy` skills are available, use them as a **mandatory
sequential pair**. They are not alternatives. Stopping after `/ship` leaves the work
in PR-limbo, which is the exact failure mode this rule prevents.

1. **Invoke `/ship`.** Handles: detect + merge base branch, run tests, review diff,
   bump VERSION, update CHANGELOG, commit, push, create the PR.
   - Skip only if `git status --short` is empty AND no open PR on this branch.
2. **Immediately invoke `/land-and-deploy`.** Handles: merge the PR, wait for CI,
   wait for the deploy, run canary checks.
   - Skip only if step 1 confirmed there is no PR at all.

### Path B — no gstack (fallback: hand-rolled ship)

If `/ship` isn't available, run the equivalent by hand — but the SAME checkpoints
apply. Do NOT skip verification just because you're doing it manually.

```bash
# 1. Verify tests pass BEFORE committing
<your project's test command>            # e.g. npm test, pytest, cargo test
<your project's typecheck command>       # e.g. npm run typecheck, mypy .

# 2. Review the diff you're about to ship
git diff --stat
git diff                                 # actually read it, don't skip

# 3. Commit + push
git add -A                               # or specific files if you prefer
git commit -m "<meaningful message>"
git push
```

If the project uses a PR workflow (not direct-to-main), open a PR and — critically
— **wait for it to merge and for the deploy to complete** before declaring wrap
done. That's the equivalent of `/land-and-deploy` in the fallback path.

### Failure modes to REFUSE (either path)

| Excuse                                         | Why it's wrong                                                                                                                                     |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| "PR is already open, skip the ship step"       | The ship step is idempotent on a pushed branch; it's where pending VERSION/CHANGELOG/TODOS updates happen.                                         |
| "I committed manually, ship has nothing to do" | Manual commits often skip tests / diff review / VERSION-bump. Either let the shipping workflow do the commit, or accept the wrap-up is incomplete. |
| "Ship done, user can deploy later"             | Wrap-up is NOT complete until the deploy has landed. Both are non-optional Part 1 steps.                                                           |

### When to skip Part 1 entirely

Only when there is literally nothing to ship — `git status --short` empty AND no
open PR on this branch (research-only session with zero code changes). Then go
straight to Part 1.5.

---

## Part 1.5 — Deploy gate for publishable artefacts (CONDITIONAL)

If the session wrote files to a **publishable-artefact directory** (site content,
static explainers, docs that auto-deploy), commit + push them so the deploy runs.

Common cases:

- **Static site content** (`docs/`, `content/`, `public/`) — commit + push; the
  platform (Vercel, Netlify, GitHub Pages) auto-deploys.
- **Explainer HTML** written to a docs directory — same pattern.
- **Design tokens / config files** the deploy consumes.

Some deploy platforms need a manual trigger (`npx vercel --prod`, `netlify deploy
--prod`, `git push` to a specific branch). Know your platform. If push alone
doesn't deploy, the manual trigger is REQUIRED — don't leave the artefact
undeployed just because the commit landed.

**Cross-machine note:** if on a machine without write access to the artefact repo,
skip silently — someone else deploys from the canonical machine later.

---

## Part 2 — Autolearn (MANDATORY)

**Re-run Part 2 if the session EXTENDS past a wrap-up.** Part 2 is autolearn — not
a one-shot. After each deploy completes AND substantive new work has since
happened, re-fire Part 2 over the new work at the true close. Don't wait for the
user to ask "autolearn anything?" — if they have to prompt it, the wrap-up
under-ran.

The four principles below govern every stage that follows. **Read the autolearn
pack's `phantom_workflow.md` for full detail** — this section is the summary.

### Autolearn principles (apply throughout every stage)

1. **Bidirectional — codify success as aggressively as failure.** Corrections are
   loud; confirmations are quiet. Save both or grow overly cautious.
2. **Write generously to cold storage (Tier 3); be ruthless about hot promotion
   (Tier 1).** Bloat is a hot-tier problem, not a total-volume problem.
3. **Deterministic verification beats model self-judgment.** Run the check; don't
   feel confident. `memory_gate.py` + `memory_doctor.py` are the gate.
4. **Retirement is TYPE-AWARE.** Never time-prune principles or user facts. Quiet
   ≠ obsolete. Only project-state memories time-cap. See the table in
   `phantom_workflow.md` for the full type/retirement matrix.

### Stage 1 — Observe (BIDIRECTIONAL)

Scan the session for BOTH:

**Failure signals** — user corrections, quirky failures that took ≥2 tries, rules
already known but ignored.

**Success signals** — user confirmations of non-obvious choices, clean first-shot
ships, correct escalation calls, approaches that worked immediately.

**Neutral signals** — preferences expressed, new domain facts, new entities.

Bucket: **(a)** new memory · **(b)** extend existing · **(c)** long-term store
(if using gbrain or similar) · **(d)** ignore (one-off, no durable lesson).

### Stage 1.5 — Process retro (what went wrong AND what went well)

Stage 1 catches user-flagged signals. Stage 1.5 catches things the user never saw
because they were internal:

- **What went wrong** → anti-pattern → correct workflow → one-line hit log
- **What went well** → validated pattern → when to reach for it → one-line hit log

Success entries live in the same `feedback_workflow_*.md` files as failures —
they're two halves of the same lesson.

### Stage 2 — Critique

For each observation, `grep -l` the existing memory for the topic. Read what
already exists. Ask: does this session contradict, extend, or duplicate the
existing rule? If a rule was IGNORED, that's an ENFORCEMENT signal — consider a
hook over another memory.

### Stage 3 — Generate (with filing discipline)

Memory naming:

- `feedback_<topic>.md` — behaviour rules (include **Why:** + **How to apply:**)
- `reference_<topic>.md` — where the answer lives
- `project_<topic>.md` — durable project state
- `user_<topic>.md` — facts about the operator

Frontmatter (mandatory):

```yaml
---
name: kebab-slug
description: When you're about to <triggering moment> (intent, not topic)
type: feedback | reference | project | user
---
```

**Filing checklist:**

- [ ] Resolver row in `MEMORY.md`, intent-phrased, under correct subsection
- [ ] Entry in `CATALOG.md` (alphabetical)
- [ ] `[[other-slug]]` cross-links to related memories
- [ ] `memory_doctor` returns `VERDICT: HEALTHY`

### Stage 4 — Validate (deterministic gates first, always)

```bash
python packs/autolearn/files/phantom_autolearn.py --validate < proposal.json
python packs/memory/files/memory_doctor.py
```

Both clean = pass. HARD block if either fails.

5-gate author self-check:

| Gate         | Question                                                 | Block if NO |
| ------------ | -------------------------------------------------------- | ----------- |
| Constitution | Contradicts any hard invariant?                          | YES         |
| Regression   | Would this catch a specific named past failure?          | YES         |
| Size         | Smallest possible change? Extension > rewrite > new file | YES         |
| Drift        | Any existing memory contradict this?                     | YES         |
| Safety       | Relaxes credential/security invariant?                   | HARD STOP   |

**Model judge panel:** high-stakes only (hard invariant / security / hook changes).
For routine memory writes, skip — deterministic gates + your judgment are the gate.

### Stage 5 — Apply

Pipe the validated JSON to `--write-learning`:

```bash
echo '<the JSON>' | python packs/autolearn/files/phantom_autolearn.py --write-learning
```

Tick every checklist item before declaring applied.

### Stage 6 — Consolidate (conditional)

Run consolidation ONLY when:

- A memory file exceeds ~100 lines, OR
- The same topic has spawned 3+ separate memory files

Extract the principle (one paragraph) at top; move incident logs below as evidence;
cross-link related memories.

**Do NOT time-prune based on quiet-ness.** See principle #4.

---

## Final wrap-up message format

```
Wrap-up status:
  Part 1 ship          ✅ v0.4.2.16 pushed, PR #445
  Part 1 land+deploy   ✅ merged, deploy green
  Part 1.5 artefacts   ✅ (or ⏭ not applicable)
  Part 2 Observe       ✅ 2 new memories drafted (1 success, 1 failure)
  Part 2 Apply         ✅ memory_doctor VERDICT: HEALTHY
```

If any row is ⏳ or ❌, the wrap-up is NOT done. Finish it before declaring
complete.
