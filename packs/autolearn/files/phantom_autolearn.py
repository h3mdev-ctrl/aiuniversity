#!/usr/bin/env python
"""
phantom_autolearn.py -- wrap up every commit and autolearn into memory.

A "phantom-style" close-out: every commit is captured, then a reflection pass
extracts durable lessons and files them into your memory system (a new memory +
a RESOLVER row), so the same mistake isn't repeated next session. This is the
self-improvement companion to the memory pack.

Flow:
    post-commit hook  --> --capture         (append the commit to a queue, instant)
    at wrap-up        --> Claude reads --show-queue, reflects, and files durable
                          lessons via --write-learning; then --clear-queue.
    (or unattended)   --> --drain runs the reflection headless via `claude -p`,
                          filing each learning through the SAME deterministic gate
                          as --write-learning and committing the result so a bad
                          write is a one-command `git revert`.

The 6 phantom stages: Observe (the diff) -> Critique/Generate (the lesson) ->
Validate (skip trivial) -> Apply (--write-learning) -> Consolidate (the doctor).

Unattended drain safety (why this is OK to schedule):
  * Every candidate learning passes validate_learning() before it is written --
    a HARD finding (credential, malformed frontmatter, oversize, dup) is refused,
    exactly like the interactive --write-learning path. No model is trusted to
    self-police; the gate is pure deterministic code.
  * Each drain is one git commit in the memory folder (if it is a repo), so any
    bad autonomous write is `git revert HEAD`, not a manual cleanup.
  * The reflection model is a cheap tier by default -- $AUTOLEARN_DRAIN_MODEL
    (default claude-haiku-4-5); a one-shot structured reflection doesn't need Opus.

On Windows the headless drain + Task Scheduler hit real traps (npm .cmd shims,
cmd.exe arg mangling, minimal scheduler PATH, PowerShell 2>&1). Each one and its
fix is in windows_gotchas.md next to this file -- read it before debugging a
"just fails" on Windows.

Modes:
    --install-hook     install a git post-commit hook (calls --capture) in the cwd repo
    --check-hook       exit 0 if the autolearn hook is installed, else 1
    --capture          append the latest commit (sha/subject/body/stat) to the queue
    --show-queue       print the queued commits as JSON (for Claude to reflect on)
    --write-learning   read ONE learning JSON on stdin, file it into memory
    --clear-queue      empty the queue
    --drain            reflect on the whole queue headless via `claude -p` and apply
                       an ACTION PLAN (create/update/supersede) to memory, then clear
    --selftest         prove the write->memory->doctor path works (isolated), exit 0/1

Queue: <base>/autolearn_queue.jsonl (base = $CLAUDE_HOME or ~/.claude).
Learnings are filed into the DISCOVERED memory (global or project-scoped); if more
than one memory exists it refuses to guess -- pin CLAUDE_MEMORY_HOME.

Learning JSON (for the interactive --write-learning path):
    {"should_write": true, "type": "feedback"|"reference", "name": "kebab-slug",
     "description": "when you're about to ...", "body": "the lesson",
     "resolver_intent": "when you're about to ..."}

Action PLAN (what the unattended --drain asks the model for -- models Andrew's
global-evolution drain: the model sees the EXISTING memory and can create a new
file, UPDATE a close one, or SUPERSEDE a stale one, so lessons evolve instead of
piling up near-dupes):
    {"actions": [
       {"type":"create","slug":"feedback_x.md","frontmatter":{...},"body":"..."},
       {"type":"update","slug":"feedback_y.md","new_full_content":"...full file..."},
       {"type":"supersede","slug":"feedback_z.md","reason":"...","superseded_by":"feedback_x.md"},
       {"type":"skip"}],
     "catalog_additions": ["- feedback_x.md -- hook"]}
Every action is validated deterministically before ANY write; the whole drain is
one revertible git commit.
"""
import json
import os
import pathlib
import shutil
from datetime import datetime, timezone
import subprocess
import sys
import tempfile
import time


def base_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))


def queue_path() -> pathlib.Path:
    return base_dir() / "autolearn_queue.jsonl"


def last_drain_path() -> pathlib.Path:
    return base_dir() / ".autolearn_last_drain"


def _drain_threshold() -> int:
    try:
        return max(1, int(os.environ.get("AUTOLEARN_DRAIN_THRESHOLD", "5")))
    except ValueError:
        return 5


def _nudge_stale_minutes() -> int:
    try:
        return max(1, int(os.environ.get("AUTOLEARN_NUDGE_STALE_MINUTES", "120")))
    except ValueError:
        return 120


def _drain_model() -> str:
    # A one-shot structured reflection -- a cheap tier is plenty. Override with
    # $AUTOLEARN_DRAIN_MODEL if you want Sonnet/Opus for a run.
    return (os.environ.get("AUTOLEARN_DRAIN_MODEL") or "claude-haiku-4-5").strip() or "claude-haiku-4-5"


def _stamp_drain() -> None:
    try:
        last_drain_path().write_text(str(int(time.time())), encoding="utf-8")
    except Exception:
        pass


def _minutes_since_last_drain() -> "float | None":
    p = last_drain_path()
    if not p.exists():
        return None
    try:
        return (time.time() - int(p.read_text(encoding="utf-8").strip())) / 60.0
    except (ValueError, OSError):
        return None


# --- memory discovery (mirror of the memory pack -- self-contained on purpose) --
def _candidate_mem_dirs() -> "list[pathlib.Path]":
    env = os.environ.get("CLAUDE_MEMORY_HOME")
    if env:
        return [pathlib.Path(env)]
    dirs = [base_dir() / "memory"]
    proj = base_dir() / "projects"
    if proj.exists():
        dirs += sorted(proj.glob("*/memory"))
    return dirs


def discover_memories() -> "list[pathlib.Path]":
    found: list[pathlib.Path] = []
    seen: set = set()
    for d in _candidate_mem_dirs():
        key = str(d).lower()
        if (d / "MEMORY.md").exists() and key not in seen:
            seen.add(key)
            found.append(d)
    return found


def resolve_memory() -> "pathlib.Path | None":
    found = discover_memories()
    return found[0] if len(found) == 1 else None


# --- git hook ---------------------------------------------------------------

HOOK_TEXT = """#!/bin/sh
# aiuniversity autolearn -- capture each commit for a wrap-up reflection
python "{script}" --capture >/dev/null 2>&1 || true
"""


def _git_dir() -> "pathlib.Path | None":
    r = subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True, text=True)
    return pathlib.Path(r.stdout.strip()) if r.returncode == 0 else None


def install_hook() -> int:
    gd = _git_dir()
    if gd is None:
        print("not inside a git repo -- run --install-hook from your project")
        return 1
    hooks = gd / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "post-commit"
    hook.write_text(HOOK_TEXT.format(script=pathlib.Path(__file__).resolve()), encoding="utf-8")
    try:
        os.chmod(hook, 0o755)
    except Exception:
        pass
    print(f"installed post-commit hook at {hook}")
    return 0


def check_hook() -> int:
    gd = _git_dir()
    if gd is None:
        return 1
    hook = gd / "hooks" / "post-commit"
    if not hook.exists():
        return 1
    return 0 if "autolearn" in hook.read_text(encoding="utf-8") else 1


# --- queue ------------------------------------------------------------------


def capture() -> int:
    log = subprocess.run(
        ["git", "log", "-1", "--format=%H%x00%s%x00%b"], capture_output=True, text=True
    )
    if log.returncode != 0 or not log.stdout.strip():
        return 1
    parts = (log.stdout.split("\x00") + ["", ""])[:3]
    sha, subject, body = parts[0].strip(), parts[1].strip(), parts[2].strip()
    stat = subprocess.run(
        ["git", "show", "--stat", "--format=", sha], capture_output=True, text=True
    ).stdout.strip()
    entry = {"sha": sha, "subject": subject, "body": body, "stat": stat}
    q = queue_path()
    q.parent.mkdir(parents=True, exist_ok=True)
    with q.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return 0


def _read_queue() -> "list[dict]":
    q = queue_path()
    entries: list[dict] = []
    if q.exists():
        for line in q.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def show_queue() -> int:
    entries = _read_queue()
    print(json.dumps({"count": len(entries), "commits": entries}, indent=2))
    return 0


def clear_queue() -> int:
    q = queue_path()
    if q.exists():
        q.unlink()
    _stamp_drain()
    print("queue cleared")
    return 0


def queue_depth() -> int:
    n = len(_read_queue())
    print(f"queue depth: {n}")
    return 0


def drain_due() -> int:
    """Exit 0 if a drain is DUE (queue depth >= threshold), else 1.

    The in-session cadence trigger: check this after a commit -- if due, reflect
    on the queue NOW rather than waiting for a session end that may never come.
    """
    n = len(_read_queue())
    t = _drain_threshold()
    due = n >= t
    print(f"queue depth {n} / threshold {t}: {'DRAIN DUE' if due else 'not yet'}")
    return 0 if due else 1


def nudge() -> int:
    """For a scheduled task: print a nudge (exit 0) when a drain is due AND the
    queue has gone stale; else exit 1 (nothing to say). Never writes memory --
    it only reminds a human/Claude to run the drain, so it stays in the loop.
    """
    n = len(_read_queue())
    t = _drain_threshold()
    if n < t:
        return 1
    mins = _minutes_since_last_drain()
    stale = mins is None or mins >= _nudge_stale_minutes()
    if not stale:
        return 1
    print(
        f"autolearn: {n} commit(s) queued and undrained"
        + (f" for ~{int(mins)} min" if mins is not None else "")
        + " -- worth a wrap-up reflection (--show-queue, then --write-learning)."
    )
    return 0


# --- apply a learning into memory -------------------------------------------


def _slugify(name: str) -> str:
    s = "".join(c if (c.isalnum() or c == "-") else "-" for c in (name or "").strip().lower())
    return s.strip("-") or "learning"


def _slug_for(name: str, ltype: str) -> str:
    """Slug for a learning, minus a doubled type prefix. A reflecting model often
    proposes a name like 'feedback-foo'; the filename already prefixes the type,
    so keep it 'feedback_foo.md', not 'feedback_feedback-foo.md'."""
    ltype = ltype if ltype in ("feedback", "reference") else "feedback"
    slug = _slugify(name)
    if slug.startswith(f"{ltype}-"):
        slug = slug[len(ltype) + 1:] or "learning"
    return slug


# --- deterministic validation gates (NO model needed) -----------------------
# Phantom deleted their LLM judge panel ("cost, no signal") in favour of
# deterministic invariants. We do the same: these gates are pure code, so the
# pack has zero local-model dependency. The SEMANTIC judgment (is this durable,
# a rule not an episode) is done by the Claude that's reflecting -- it has the
# session context the gates never will. A cross-model second opinion is optional
# and only worth it for high-stakes edits (see phantom_workflow.md).

import re as _re  # noqa: E402

_CRED_PATTERNS = [
    r"sk-ant-[A-Za-z0-9_\-]{8,}",                 # Anthropic keys
    r"AKIA[0-9A-Z]{16}",                          # AWS access key id
    r"gh[pousr]_[A-Za-z0-9]{20,}",                # GitHub tokens
    r"xox[baprs]-[A-Za-z0-9-]{10,}",              # Slack tokens
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",        # private key blocks
    r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{6,}",  # JWTs
    r"(?i:\b(?:api[_-]?key|secret|password|passwd|bearer|access[_-]?token)\b)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}",
]
_CRED_RE = _re.compile("|".join(_CRED_PATTERNS))

MAX_BODY_LINES = 40
MAX_BODY_CHARS = 3000
_PLACEHOLDER_BODIES = {"", "(add the lesson)"}


def validate_learning(learning: dict, mem: pathlib.Path) -> "list[tuple[str, str]]":
    """Return a list of (severity, message). severity is 'HARD' (block) or 'SOFT'
    (warn). Pure, deterministic, model-free."""
    issues: list[tuple[str, str]] = []
    name = (learning.get("name") or "").strip()
    desc = (learning.get("description") or "").strip()
    body = (learning.get("body") or "").strip()
    ltype = learning.get("type", "feedback")

    if not name:
        issues.append(("HARD", "missing `name`"))
    if not desc:
        issues.append(("HARD", "missing `description` (the triggering moment)"))
    if body in _PLACEHOLDER_BODIES:
        issues.append(("HARD", "body is empty/placeholder -- nothing durable to file"))
    if ltype not in ("feedback", "reference"):
        issues.append(("SOFT", f"type {ltype!r} not feedback/reference (coerced to feedback)"))

    # credential leak -- scan everything that would land on disk
    blob = f"{name}\n{desc}\n{body}"
    if _CRED_RE.search(blob):
        issues.append(("HARD", "looks like it contains a credential/secret -- refusing to write it into memory"))

    # size bounds -- keep memory files small, bound index growth
    if len(body.splitlines()) > MAX_BODY_LINES or len(body) > MAX_BODY_CHARS:
        issues.append(("HARD", f"body too long ({len(body.splitlines())} lines) -- distil to the rule (<= {MAX_BODY_LINES} lines)"))

    # balanced code fences (an odd count breaks rendering + the doctor)
    if blob.count("```") % 2 != 0:
        issues.append(("HARD", "unbalanced ``` code fences"))

    # duplicate -- the file already exists; updating by hand beats overwriting
    if name:
        slug = _slug_for(name, ltype)
        norm_type = ltype if ltype in ("feedback", "reference") else "feedback"
        if (mem / f"{norm_type}_{slug}.md").exists():
            issues.append(("HARD", f"a memory named {slug!r} already exists -- update it by hand instead of overwriting"))
        elif slug in (mem / "MEMORY.md").read_text(encoding="utf-8") if (mem / "MEMORY.md").exists() else False:
            issues.append(("SOFT", f"{slug!r} already appears in MEMORY.md -- possible near-duplicate"))

    return issues


def _print_issues(issues: "list[tuple[str, str]]") -> None:
    for sev, msg in issues:
        print(f"  [{sev}] {msg}")


def write_learning_to(mem: pathlib.Path, learning: dict) -> str:
    ltype = learning.get("type", "feedback")
    if ltype not in ("feedback", "reference"):
        ltype = "feedback"
    slug = _slug_for(learning.get("name", "learning"), ltype)
    desc = (learning.get("description") or "(add a triggering moment)").strip()
    body = (learning.get("body") or "").strip() or "(add the lesson)"
    fname = f"{ltype}_{slug}.md"
    (mem / fname).write_text(
        f"---\nname: {slug}\ndescription: {desc}\ntype: {ltype}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    # add a RESOLVER row under a single "Learned (autolearn)" section at the end
    intent = (learning.get("resolver_intent") or desc).strip()
    index = mem / "MEMORY.md"
    text = index.read_text(encoding="utf-8")
    if slug not in text:
        if "## Learned (autolearn)" not in text:
            text = (
                text.rstrip()
                + "\n\n## Learned (autolearn)\n\n| When you're about to... | Consult |\n|---|---|\n"
            )
        text = text.rstrip() + f"\n| {intent} | [{ltype}_{slug}]({fname}) |\n"
        index.write_text(text, encoding="utf-8")
    return fname


def write_learning() -> int:
    mem = resolve_memory()
    if mem is None:
        if len(discover_memories()) > 1:
            print("AMBIGUOUS: multiple memory systems -- pin CLAUDE_MEMORY_HOME")
            return 3
        print("no memory system found -- run the memory pack first (packs/memory)")
        return 1
    try:
        learning = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        print(f"--write-learning expects one learning JSON on stdin: {exc}")
        return 2
    if not learning.get("should_write", True):
        print("learning marked should_write=false -- nothing filed")
        return 0
    issues = validate_learning(learning, mem)
    hard = [i for i in issues if i[0] == "HARD"]
    if issues:
        _print_issues(issues)
    if hard:
        print("REFUSED: deterministic gate blocked this write (fix the HARD issues above)")
        return 4
    fname = write_learning_to(mem, learning)
    print(f"filed {fname} into {mem}")
    return 0


def validate() -> int:
    """Run the deterministic gates on a learning (stdin JSON) without writing.
    Exit 0 if it would be accepted, 4 if a HARD gate blocks it."""
    mem = resolve_memory()
    if mem is None:
        if len(discover_memories()) > 1:
            print("AMBIGUOUS: multiple memory systems -- pin CLAUDE_MEMORY_HOME")
            return 3
        print("no memory system found -- run the memory pack first (packs/memory)")
        return 1
    try:
        learning = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        print(f"--validate expects one learning JSON on stdin: {exc}")
        return 2
    issues = validate_learning(learning, mem)
    if not issues:
        print("OK: passes the deterministic gates")
        return 0
    _print_issues(issues)
    return 4 if any(sev == "HARD" for sev, _ in issues) else 0


# --- unattended reflection: an ACTION PLAN (models global-evolution) ---------
# Instead of one create-only learning per commit, the drain asks the model for a
# PLAN over the WHOLE queue at once, GIVEN the existing memory: create a new file,
# UPDATE a close one, or SUPERSEDE a stale one -- so lessons dedup and evolve
# rather than piling up near-duplicates. Ported from Andrew's global-evolution
# drain. Every action is validated deterministically before any write; index
# growth lands in CATALOG.md (on-demand), never the always-loaded MEMORY.md.

MAX_PLAN_BODY_LINES = 150
MAX_CATALOG_ADDITIONS = 4
_VALID_TYPES = ("feedback", "reference", "project", "user")
_SLUG_RE = _re.compile(r"^[a-z0-9][a-z0-9_\-]*\.md$")

PLAN_PROMPT = """You are doing a wrap-up reflection (a 'phantom' close-out) over a BATCH of git commits, deciding how to evolve a file-based memory system so the same mistakes aren't repeated.

You are given: (1) the routing index (MEMORY.md), (2) the list of EXISTING memory slugs, (3) the commits. Extract only DURABLE, reusable lessons -- behaviour rules, gotchas, where-an-answer-lives. Skip trivial or one-off changes. Prefer FEW high-signal memories over many. A durable lesson beats no lesson beats a trivial one.

For each lesson choose ONE action:
- create   : a genuinely NEW lesson (slug must NOT already exist)
- update   : refines an EXISTING memory -> return its FULL new content (don't drop what's already there)
- supersede: an existing memory is now stale/wrong -> mark it, optionally point to a replacement
- skip     : nothing durable here

Respond with ONLY this JSON (no prose, no code fence):
{"actions":[
  {"type":"create","slug":"feedback_x.md","frontmatter":{"name":"x","description":"when you're about to ...","type":"feedback"},"body":"the lesson (<=150 lines)"},
  {"type":"update","slug":"feedback_y.md","new_full_content":"---\\nname: y\\ndescription: ...\\ntype: feedback\\n---\\n\\n...full file..."},
  {"type":"supersede","slug":"feedback_stale.md","reason":"why it's stale","superseded_by":"feedback_x.md"},
  {"type":"skip"}
],"catalog_additions":["- feedback_x.md -- one-line hook"]}

Rules: slug is <type>_<kebab>.md ; type in feedback|reference|project|user ; NEVER put a credential/secret/.env value in any field ; index growth goes ONLY in catalog_additions (<=4 lines) -- never edit the routing index yourself."""


# A test/dry-run seam: point $AUTOLEARN_FAKE_REFLECT at a JSON PLAN object (or a
# list whose first element is the plan) and the reflector returns it instead of
# calling `claude -p`. Lets the validate + apply + commit path run with no model.
_FAKE_REFLECT_ENV = "AUTOLEARN_FAKE_REFLECT"
_fake_iter = None


def _next_fake(path: str) -> "dict | None":
    global _fake_iter
    if _fake_iter is None:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        _fake_iter = iter(data if isinstance(data, list) else [data])
    return next(_fake_iter, None)


def _extract_json_object(text: str) -> "dict | None":
    s = (text or "").strip()
    i, j = s.find("{"), s.rfind("}")
    if i == -1 or j == -1 or j < i:
        return None
    try:
        return json.loads(s[i:j + 1])
    except (json.JSONDecodeError, ValueError):
        return None


def _is_memory_filename(name: str) -> bool:
    if name in ("MEMORY.md", "CATALOG.md") or name.startswith("_"):
        return False
    if name.startswith("INDEX_") and name.endswith(".md"):
        return False
    return name.endswith(".md")


def _existing_slugs(mem: pathlib.Path) -> "list[str]":
    return sorted(p.name for p in mem.glob("*.md") if _is_memory_filename(p.name))


def _plan_reflect(entries: "list[dict]", mem: pathlib.Path, model: str) -> "dict | None":
    """Ask the model for ONE action-plan over the whole queue (or None on failure)."""
    fake = os.environ.get(_FAKE_REFLECT_ENV)
    if fake:
        return _next_fake(fake)
    # Resolve the CLI via shutil.which -- on Windows `claude` is an npm `.cmd` shim
    # and bare subprocess.run(["claude", ...]) can't find it (no PATHEXT).
    exe = shutil.which("claude")
    if not exe:
        return None
    routing = (mem / "MEMORY.md").read_text(encoding="utf-8") if (mem / "MEMORY.md").exists() else ""
    commits = "\n\n".join(
        f"### {e.get('subject','')}\n{e.get('body','')}\n{e.get('stat','')}" for e in entries
    )
    prompt = (
        PLAN_PROMPT
        + "\n\n## Routing index (MEMORY.md)\n" + routing[:6000]
        + "\n\n## Existing memory slugs\n" + "\n".join(_existing_slugs(mem))
        + "\n\n## Commits to reflect on\n" + commits
    )
    # --tools="" so the model can ONLY emit text -- it cannot touch the filesystem;
    # Python applies the validated plan. That model/filesystem boundary is the
    # safety line. Prompt goes on STDIN (a .cmd would mangle it as an argv string).
    r = subprocess.run(
        [exe, "-p", "--model", model, "--tools", ""], input=prompt, capture_output=True, text=True
    )
    if r.returncode != 0:
        return None
    return _extract_json_object(r.stdout)


# --- deterministic plan validation (port of global-evolution's invariants) ---


def _check_slug(slug: str) -> "list[str]":
    errs: list[str] = []
    if not _SLUG_RE.match(slug or ""):
        errs.append(f"slug {slug!r} invalid (must be <type>_<kebab>.md, lowercase)")
    if ".." in (slug or "") or "/" in (slug or "") or "\\" in (slug or ""):
        errs.append(f"slug {slug!r} contains path traversal")
    return errs


def _check_body(body: str) -> "list[str]":
    errs: list[str] = []
    if _CRED_RE.search(body or ""):
        errs.append("body looks like it contains a credential/secret -- refusing")
    n = len((body or "").splitlines())
    if n > MAX_PLAN_BODY_LINES:
        errs.append(f"body has {n} lines, max {MAX_PLAN_BODY_LINES}")
    if (body or "").count("```") % 2 != 0:
        errs.append("unbalanced ``` code fences")
    return errs


def _check_frontmatter(fm: dict) -> "list[str]":
    if not isinstance(fm, dict):
        return ["frontmatter is not an object"]
    errs = [f"frontmatter missing {k}" for k in ("name", "description", "type") if not fm.get(k)]
    if fm.get("type") not in _VALID_TYPES:
        errs.append(f"frontmatter type {fm.get('type')!r} invalid (feedback|reference|project|user)")
    return errs


def validate_plan(plan: dict, existing_slugs: "list[str]") -> "list[str]":
    """Deterministic gate over the whole plan. Returns [] if every action is safe
    to apply, else a list of reasons. Pure, model-free -- the safety floor for an
    unattended drain, exactly like validate_learning is for --write-learning."""
    if not isinstance(plan, dict):
        return ["plan is not a JSON object"]
    actions = plan.get("actions", [])
    if not isinstance(actions, list):
        return ["actions is not a list"]
    errors: list[str] = []
    adds = plan.get("catalog_additions", [])
    if not isinstance(adds, list):
        errors.append("catalog_additions is not a list")
    elif len(adds) > MAX_CATALOG_ADDITIONS:
        errors.append(f"catalog_additions has {len(adds)}, max {MAX_CATALOG_ADDITIONS}")

    existing_lower = {s.lower() for s in existing_slugs}
    created_lower = {a.get("slug", "").lower() for a in actions if a.get("type") == "create"}
    seen: set = set()
    for a in actions:
        t = a.get("type")
        if t == "create":
            slug = a.get("slug", "")
            errors += _check_slug(slug)
            if slug.lower() in existing_lower:
                errors.append(f"create slug {slug!r} already exists -- use update")
            if slug.lower() in seen:
                errors.append(f"duplicate create slug {slug!r} in the same plan")
            seen.add(slug.lower())
            errors += _check_body(a.get("body", ""))
            errors += _check_frontmatter(a.get("frontmatter", {}))
        elif t == "update":
            slug = a.get("slug", "")
            errors += _check_slug(slug)
            if slug.lower() not in existing_lower:
                errors.append(f"update slug {slug!r} does not exist -- use create")
            errors += _check_body(a.get("new_full_content", ""))
        elif t == "supersede":
            slug = a.get("slug", "")
            errors += _check_slug(slug)
            if slug.lower() not in existing_lower:
                errors.append(f"supersede slug {slug!r} does not exist")
            if not (a.get("reason", "") or "").strip():
                errors.append(f"supersede {slug!r} missing a reason")
            sb = a.get("superseded_by", "")
            if sb:
                errors += _check_slug(sb)
                if sb.lower() not in existing_lower and sb.lower() not in created_lower:
                    errors.append(f"supersede superseded_by {sb!r} neither exists nor is created here")
        elif t == "skip":
            pass
        else:
            errors.append(f"unknown action type {t!r}")
    return errors


# --- apply a validated plan (port of global-evolution's apply layer) ---------

_BANNER_MARK = "<!-- superseded-banner -->"
_SUPERSEDE_KEYS = ("status", "superseded_at", "superseded_by", "supersede_reason")


def _split_frontmatter(content: str) -> "tuple[list[str], str]":
    if not content.startswith("---\n"):
        return [], content
    rest = content[4:]
    end = rest.find("\n---\n")
    if end == -1:
        return [], content
    return rest[:end].split("\n"), rest[end + 5:]


def _apply_supersede(mem: pathlib.Path, slug: str, superseded_by: str, reason: str) -> str:
    """Stamp a memory file as superseded IN PLACE (never deletes). Idempotent."""
    path = mem / slug
    content = path.read_text(encoding="utf-8")
    fm_lines, body = _split_frontmatter(content)
    fm_lines = [ln for ln in fm_lines if ln.split(":", 1)[0].strip() not in _SUPERSEDE_KEYS]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fm_lines += [
        "status: superseded",
        f"superseded_at: {ts}",
        f"superseded_by: {superseded_by}",
        f"supersede_reason: {json.dumps(reason)}",
    ]
    if _BANNER_MARK in body:
        body = body.split(_BANNER_MARK, 1)[1].lstrip("\n")
    ref = f" See [[{superseded_by[:-3]}]]." if superseded_by.endswith(".md") else ""
    banner = f"> [SUPERSEDED {ts[:10]}] {reason}{ref}\n{_BANNER_MARK}\n\n"
    new = "---\n" + "\n".join(fm_lines) + "\n---\n\n" + banner + body
    if not new.endswith("\n"):
        new += "\n"
    path.write_text(new, encoding="utf-8")
    return f"superseded {slug}" + (f" (by {superseded_by})" if superseded_by else "")


def _update_drops_content(old: str, new: str) -> bool:
    """Guard: an `update` blind-writes the model's new_full_content, but the model
    never saw the file's current BODY (only the routing index + slugs). So a drain
    that 'remembers' an old version can clobber content added since. Return True
    (=> SKIP, keep original) only on the clear clobber signature: the new content is
    BOTH much shorter AND loses most of the old file's substantive lines. A genuine
    extension keeps the old lines or grows the file, so it always passes."""
    def sig(t: str) -> set:
        out = set()
        for ln in t.splitlines():
            s = ln.strip()
            if len(s) >= 20 and not s.startswith(("---", ">", "#", "name:", "description:", "type:", "kind:")):
                out.add(s)
        return out
    old_sig = sig(old)
    if not old_sig:
        return False
    retained = len(old_sig & sig(new)) / len(old_sig)
    return len(new) < 0.5 * len(old) and retained < 0.5


def apply_plan(mem: pathlib.Path, plan: dict) -> "list[str]":
    """Apply a plan already passed by validate_plan. Returns human-readable changes."""
    changes: list[str] = []
    for a in plan.get("actions", []):
        t = a.get("type")
        if t == "create":
            slug = a["slug"]
            fm = a["frontmatter"]
            fm_yaml = "\n".join(f"{k}: {v}" for k, v in fm.items())
            (mem / slug).write_text(f"---\n{fm_yaml}\n---\n\n{a.get('body','').rstrip()}\n", encoding="utf-8")
            changes.append(f"created {slug}")
        elif t == "update":
            slug = a["slug"]
            new = a.get("new_full_content", "")
            path = mem / slug
            old = path.read_text(encoding="utf-8") if path.exists() else ""
            if _update_drops_content(old, new):
                changes.append(f"SKIPPED update {slug} -- would drop existing content (kept original)")
                continue
            path.write_text(new if new.endswith("\n") else new + "\n", encoding="utf-8")
            changes.append(f"updated {slug}")
        elif t == "supersede":
            changes.append(_apply_supersede(mem, a["slug"], a.get("superseded_by", ""), a.get("reason", "")))
        # skip -> nothing
    return changes


def _catalog_text(mem: pathlib.Path) -> str:
    cat = mem / "CATALOG.md"
    if cat.exists():
        return cat.read_text(encoding="utf-8")
    return "# CATALOG\n\n> Full memory file list (Tier-2, on demand). One line per file.\n"


def _apply_catalog_additions(mem: pathlib.Path, plan: dict) -> None:
    adds = [ln.strip() for ln in plan.get("catalog_additions", []) if isinstance(ln, str) and ln.strip()]
    adds = adds[:MAX_CATALOG_ADDITIONS]
    if not adds:
        return
    text = _catalog_text(mem)
    for ln in adds:
        if ln not in text:
            text = text.rstrip() + "\n" + ln + "\n"
    (mem / "CATALOG.md").write_text(text, encoding="utf-8")


def _ensure_reachable(mem: pathlib.Path, created_slugs: "list[str]") -> None:
    """Safety net: every CREATED memory must be routable (MEMORY.md / INDEX_*.md /
    CATALOG.md) or the doctor flags it dark. Append a CATALOG line for any the
    model's catalog_additions didn't cover."""
    if not created_slugs:
        return
    routing_parts: list[str] = []
    for name in ("MEMORY.md", "CATALOG.md"):
        p = mem / name
        if p.exists():
            routing_parts.append(p.read_text(encoding="utf-8"))
    for p in mem.glob("INDEX_*.md"):
        routing_parts.append(p.read_text(encoding="utf-8"))
    blob = "\n".join(routing_parts)
    text = _catalog_text(mem)
    changed = False
    for slug in created_slugs:
        stem = slug[:-3] if slug.endswith(".md") else slug
        if slug not in blob and stem not in blob and slug not in text:
            text = text.rstrip() + f"\n- {slug} -- (autolearn)\n"
            changed = True
    if changed:
        (mem / "CATALOG.md").write_text(text, encoding="utf-8")


def _commit_drain(mem: pathlib.Path, n_changes: int) -> "str | None":
    """Commit everything the drain touched (created/updated/superseded + CATALOG)
    into the memory folder's git repo, so a bad unattended write is a one-command
    `git revert HEAD`. No-op if the folder isn't a git work tree or nothing changed."""
    if not n_changes:
        return None
    inside = subprocess.run(
        ["git", "-C", str(mem), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True
    )
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return None
    subprocess.run(["git", "-C", str(mem), "add", "-A"], capture_output=True, text=True)
    msg = f"autolearn: apply {n_changes} memory change(s) via unattended drain"
    commit = subprocess.run(["git", "-C", str(mem), "commit", "-m", msg], capture_output=True, text=True)
    if commit.returncode != 0:
        return None
    sha = subprocess.run(
        ["git", "-C", str(mem), "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    return sha or "HEAD"


def drain() -> int:
    mem = resolve_memory()
    if mem is None:
        print("no single memory to file into (missing or ambiguous) -- fix that first")
        return 1
    entries = _read_queue()
    if not entries:
        print("queue empty -- nothing to drain")
        return 0
    model = _drain_model()
    plan = _plan_reflect(entries, mem, model)
    if plan is None:
        # Keep the queue so the next drain retries -- never lose the commits to a
        # model hiccup or a missing CLI.
        print(f"drain: no usable plan from the model (model {model}) -- queue KEPT, nothing written")
        return 1
    errors = validate_plan(plan, _existing_slugs(mem))
    if errors:
        print("[blocked] plan failed the deterministic gate -- nothing written (queue KEPT):")
        for e in errors:
            print(f"  - {e}")
        return 4
    changes = apply_plan(mem, plan)
    _apply_catalog_additions(mem, plan)
    created = [a["slug"] for a in plan.get("actions", []) if a.get("type") == "create"]
    _ensure_reachable(mem, created)
    queue_path().unlink(missing_ok=True)
    _stamp_drain()
    committed = _commit_drain(mem, len(changes))
    tail = (
        f"; committed {committed}" if committed
        else ("; (memory folder is not a git repo -- no per-drain commit)" if changes else "")
    )
    detail = ("; " + "; ".join(changes)) if changes else " (no durable lessons)"
    print(
        f"drained {len(entries)} commit(s) with model {model}: "
        f"{len(changes)} change(s){detail} -> {mem}{tail}"
    )
    return 0


def install_workflow() -> int:
    """Drop phantom_workflow.md into the memory folder as _phantom_workflow.md
    so the recipient's Claude has a concrete procedure to follow when reflecting.
    """
    mem = resolve_memory()
    if mem is None:
        if len(discover_memories()) > 1:
            print("AMBIGUOUS: multiple memory systems -- pin CLAUDE_MEMORY_HOME")
            return 3
        print("no memory system found -- run the memory pack first (packs/memory)")
        return 1
    src = pathlib.Path(__file__).resolve().parent / "phantom_workflow.md"
    if not src.exists():
        print(f"missing source workflow doc at {src}")
        return 1
    dst = mem / "_phantom_workflow.md"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"installed workflow guide at {dst}")
    return 0


def check_workflow() -> int:
    mem = resolve_memory()
    if mem is None:
        return 1
    return 0 if (mem / "_phantom_workflow.md").exists() else 1


def selftest() -> int:
    """Behavioural exam of the whole write -> gate -> memory -> doctor path against
    an ISOLATED throwaway memory (never the recipient's real one). Like guardrails'
    --test-blocking, it proves the safety gate both BLOCKS the forbidden and ALLOWS
    the good -- a gate that never refuses is an empty check. Stages:
      1. the deterministic gate REFUSES a credential-bearing learning (HARD);
      2. the gate ACCEPTS a clean, well-formed one;
      3. that learning WRITES to disk AND is routed from the index;
      4. the written memory PASSES the doctor (reachable + valid) -- the consolidate
         stage, proven not just claimed.
    """
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="autolearn_selftest_"))
    try:
        (tmp / "MEMORY.md").write_text(
            "# Memory\n\n## RESOLVER\n\n| When you're about to... | Consult |\n|---|---|\n",
            encoding="utf-8",
        )
        # 1. the gate MUST block a forbidden write (a credential in the body). This
        #    is the pack's headline guarantee; without this line --selftest would
        #    only prove the write function runs, not that the gate actually guards.
        bad = {"type": "feedback", "name": "leaky-selftest",
               "description": "when you're about to leak a secret",
               "body": "the api key is sk-ant-abc12345deadbeef99 and it works"}
        if not any(sev == "HARD" for sev, _ in validate_learning(bad, tmp)):
            print("autolearn selftest: FAILED -- gate did NOT block a credential-bearing learning")
            return 1
        # 2. the gate MUST accept a clean, well-formed learning.
        good = {"type": "feedback", "name": "autolearn-selftest",
                "description": "when you're about to test autolearn",
                "body": "selftest OK", "resolver_intent": "when testing autolearn"}
        if any(sev == "HARD" for sev, _ in validate_learning(good, tmp)):
            print("autolearn selftest: FAILED -- gate wrongly blocked a clean learning")
            return 1
        # 3. it writes AND is routed from the index.
        fname = write_learning_to(tmp, good)
        if not ((tmp / fname).exists() and "autolearn-selftest" in (tmp / "MEMORY.md").read_text(encoding="utf-8")):
            print("autolearn selftest: FAILED -- write did not land / not routed from the index")
            return 1
        # 4. the written memory survives the doctor (the consolidate stage).
        doctor = pathlib.Path(__file__).resolve().parent.parent.parent / "memory" / "files" / "memory_doctor.py"
        if doctor.exists():
            r = subprocess.run(
                [sys.executable, str(doctor)],
                capture_output=True, text=True, encoding="utf-8",
                env=dict(os.environ, CLAUDE_MEMORY_HOME=str(tmp)),
            )
            if r.returncode != 0 or "HEALTHY" not in r.stdout:
                print("autolearn selftest: FAILED -- doctor did not pass on the written memory")
                print((r.stdout or r.stderr).strip()[-300:])
                return 1
            print("autolearn write->gate->memory->doctor: OK (gate blocks bad + allows good; doctor HEALTHY)")
        else:
            print("autolearn write->gate->memory: OK (gate blocks bad + allows good; doctor script not found, skipped)")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--show-queue"
    dispatch = {
        "--install-hook": install_hook,
        "--check-hook": check_hook,
        "--install-workflow": install_workflow,
        "--check-workflow": check_workflow,
        "--capture": capture,
        "--show-queue": show_queue,
        "--queue-depth": queue_depth,
        "--drain-due": drain_due,
        "--nudge": nudge,
        "--write-learning": write_learning,
        "--validate": validate,
        "--clear-queue": clear_queue,
        "--drain": drain,
        "--selftest": selftest,
    }
    fn = dispatch.get(mode)
    if fn is None:
        print(f"unknown mode {mode!r}; see --help in the file header")
        return 2
    return fn()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main(sys.argv))
