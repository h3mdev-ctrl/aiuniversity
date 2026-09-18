<!-- empirical-rigor:start -->
# Empirical rigor -- three guardrails against trusting a convenient assumption over real data

> These are always-loaded behavioural rules. They target a different failure mode
> than `agent-honesty`'s reporting guardrails: not a false claim, but a *design*
> built on an assumption that was never checked against the real shape of the data
> or the real environment it will run in. Each rule names the moment it fires, the
> rule, why it matters, and what to do instead.

## 1. distribution-before-statistic -- look at the real shape of the data before choosing a statistic

**Trigger:** you are about to size a threshold, buffer, or cap from historical data
using a mean or rolling average.

**Rule:** before committing to a mean/average-based figure, look at the actual
distribution of the real values first. If it's spiky or bimodal (mostly a low or
zero value with occasional large spikes) rather than smooth, a mean will understate
the real recurring risk -- a max, or a high percentile over the same window,
usually fits better.

**Why:** a mean answers "what's typical," not "what do I need to cover" -- and
those are different questions whenever the data isn't smooth. Real operational
data (usage, load, failures) is often spiky by nature, and a smoothing statistic
silently drops exactly the tail case the number exists to protect against.

**How to apply:** list or plot the actual daily/period values before picking a
formula. If the value is mostly near zero with occasional large jumps, use a max
or a percentile (e.g. mean + 1.5x stdev, or the 90th percentile) over the same
window instead of a mean -- and sanity-check the result against the single worst
real value on record, not just the summary statistic.

## 2. environment-parity-for-adhoc-runs -- a diagnostic script must mirror production's real environment, not a trimmed copy

**Trigger:** you are about to run an ad-hoc or diagnostic invocation of code that
also runs on a schedule or in production (a manual container run, a local script
import, a one-off test) against real inputs or real systems.

**Rule:** mirror the real job's full environment -- mounts, environment variables,
config files, working directory -- exactly, rather than a shortened version
"because this script only needs X." A trimmed environment can silently produce
false inputs that look like real ones, with no error to flag the difference.

**Why:** the danger isn't that the ad-hoc script fails loudly -- it's that it
succeeds quietly on false data, and if the same code path has write access to
something real, that false data can become a real bad action. This isn't
hypothetical: a missing mount/env var on a diagnostic run has produced a false
"no signal" reading that was indistinguishable from a real one until it was
already acted on.

**How to apply:** before running anything ad-hoc against production code, diff its
invocation against the real cron/deploy invocation (mounts, env vars, working
directory) and copy the real one verbatim, adding only what the diagnostic itself
needs on top -- never trimming what's already there.

## 3. continuity-is-not-uptime -- a gap-free dataset is not proof the process that made it was running correctly

**Trigger:** you are about to cite "N days/rows with no gaps" as evidence that an
automated job has been running reliably over that period.

**Rule:** check the actual deploy/execution history (when was this job actually
turned on, has it been restarted, was any of this backfilled) before treating data
continuity as proof of process continuity. A clean-looking dataset can be a
one-time backfill against cached or historical inputs rather than N days of the
job actually firing.

**Why:** continuity and correctness are independent properties -- a backfill
script can manufacture a perfectly gap-free history in a single run, and that
looks identical to genuine day-by-day success unless you check when the code was
actually deployed.

**How to apply:** before trusting "clean for N days" as proof of reliability,
check the deploy timestamp, git history, or scheduler log for the job that's
supposed to have produced it. If the deploy is more recent than the data range,
some or all of that history is backfilled, not observed.

---

**The through-line:** all three replace a convenient assumption about data or
environment with a direct look at the real thing -- the actual distribution, the
actual runtime environment, the actual deploy history. `agent-honesty` guards what
the model *claims*; this pack guards what the model *builds things on top of*.
Neither substitutes for the other.
<!-- empirical-rigor:end -->
