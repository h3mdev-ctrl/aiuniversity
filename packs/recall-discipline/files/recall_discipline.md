<!-- recall-discipline:start -->
# Recall discipline -- three guardrails against re-deriving knowledge that already exists

> These are always-loaded behavioural rules. They target a different failure mode
> than agent-honesty: not a false claim, but real, avoidable rework -- redoing
> research a prior session already did, letting findings scatter across too many
> small notes to be useful, or letting a long-term effort start without the
> structure it needs. Each rule names the moment it fires, the rule, why it
> matters, and what to do instead.

## 1. recon-before-research -- check memory before researching an external system

**Trigger:** you are about to look something up externally (a web search, a
vendor doc, a forum) about how an external system, API, or tool behaves.

**Rule:** before going outside, check your own existing memory/notes for that
system's name. A prior session may have already tested it directly against the
real thing -- that beats a forum post or a fresh guess every time.

**Why:** external research that duplicates a prior session's direct test is pure
waste, and it can be a downgrade: a live test result is better evidence than
secondhand documentation, so skipping the memory check can mean replacing a good
answer with a worse one.

**How to apply:** grep your memory store for the system/API/topic name before
calling out. If something relevant turns up, read it and treat it as the
starting point, not a thing to re-derive. If it's genuinely absent, research
outward as normal -- this rule is a cheap check, not a ban on research.

## 2. consolidate-dont-accumulate -- fold scattered topic files into one reference

**Trigger:** you're about to write a new memory note on a topic that already has
two or more existing notes about it.

**Rule:** when 3+ memory files accumulate on the same external system or
reference topic, that's the trigger to consolidate them into one canonical
reference rather than adding a fourth scattered note. If the topic is code- or
system-adjacent, the canonical home is a version-controlled doc in the relevant
repo (greppable by a future session doing normal recon), not another memory
file -- memory then holds a pointer to it, not a duplicate.

**Why:** a memory file that's linked from an index is "reachable," but reachable
is not the same as usable. Answering one question by re-reading five scattered
files is real, recurring overhead -- and it compounds, since each new session
is tempted to add a sixth file rather than notice the pile.

**How to apply:** before writing a new note, check how many existing ones cover
the same topic. At three or more, stop and consolidate instead: pull the real
facts out of all of them into one file, in the place a future session would
naturally look for it, and leave pointers behind in the old notes (or the
index) rather than deleting the incident history if it's still useful.

## 3. project-framing-is-a-signal -- build the durable home when the user says "project"

**Trigger:** the user names or frames a new piece of work as "a project" (not
"can you check X" or "help me with Y" -- specifically the word "project," or
an equivalent long-term framing).

**Rule:** treat that word as a request to set up a durable home for the work --
a structured folder/index/file the work will keep living in -- in that same
session, not as a mood word to note and move past. If a matching structure
doesn't exist yet, create it before the work starts accumulating elsewhere.

**Why:** "project" signals recurring, long-term effort. Treating it as casual
framing is how work quietly scatters across whatever files/notes/repos happen
to be open in each session, until nobody -- including the agent -- can find the
answer to "what do we actually know about this" without re-deriving it.

**How to apply:** when the word lands, check whether a durable home already
exists for this effort. If not, build the minimal version immediately (an
index file is enough to start) before doing the requested work, so the next
session -- and this one, later -- has somewhere to look first.
<!-- recall-discipline:end -->
