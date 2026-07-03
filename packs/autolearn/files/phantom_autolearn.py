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
    (or unattended)   --> --drain runs the reflection headless via `claude -p`.

The 6 phantom stages: Observe (the diff) -> Critique/Generate (the lesson) ->
Validate (skip trivial) -> Apply (--write-learning) -> Consolidate (the doctor).

Modes:
    --install-hook     install a git post-commit hook (calls --capture) in the cwd repo
    --check-hook       exit 0 if the autolearn hook is installed, else 1
    --capture          append the latest commit (sha/subject/body/stat) to the queue
    --show-queue       print the queued commits as JSON (for Claude to reflect on)
    --write-learning   read ONE learning JSON on stdin, file it into memory
    --clear-queue      empty the queue
    --drain            reflect on the queue headless via `claude -p`, then clear it
    --selftest         prove the write->memory->doctor path works (isolated), exit 0/1

Queue: <base>/autolearn_queue.jsonl (base = $CLAUDE_HOME or ~/.claude).
Learnings are filed into the DISCOVERED memory (global or project-scoped); if more
than one memory exists it refuses to guess -- pin CLAUDE_MEMORY_HOME.

Learning JSON (for --write-learning / what --drain expects back from claude):
    {"should_write": true, "type": "feedback"|"reference", "name": "kebab-slug",
     "description": "when you're about to ...", "body": "the lesson",
     "resolver_intent": "when you're about to ..."}
"""
import json
import os
import pathlib
import shutil
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
        slug = _slugify(name)
        if (mem / f"{ltype if ltype in ('feedback', 'reference') else 'feedback'}_{slug}.md").exists():
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
    slug = _slugify(learning.get("name", "learning"))
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


# --- unattended reflection (headless) ---------------------------------------

REFLECT_PROMPT = (
    "You are doing a wrap-up reflection (a 'phantom' close-out) on a git commit. "
    "From the commit below, extract AT MOST ONE durable, reusable lesson worth "
    "remembering across future sessions -- a behaviour rule, a gotcha, or where an "
    "answer lives. Skip trivial or one-off changes. Respond with ONLY JSON: "
    '{"should_write": bool, "type": "feedback"|"reference", "name": "kebab-slug", '
    '"description": "when you\'re about to ...", "body": "the lesson", '
    '"resolver_intent": "when you\'re about to ..."}. '
    'If nothing is durable, {"should_write": false}.\n\nCOMMIT:\n'
)


def drain() -> int:
    mem = resolve_memory()
    if mem is None:
        print("no single memory to file into (missing or ambiguous) -- fix that first")
        return 1
    entries = _read_queue()
    if not entries:
        print("queue empty -- nothing to drain")
        return 0
    written = 0
    for e in entries:
        prompt = REFLECT_PROMPT + f"{e.get('subject','')}\n{e.get('body','')}\n{e.get('stat','')}"
        r = subprocess.run(["claude", "-p", prompt], capture_output=True, text=True)
        if r.returncode != 0:
            continue
        out = r.stdout.strip()
        try:
            learning = json.loads(out[out.find("{"): out.rfind("}") + 1])
        except (json.JSONDecodeError, ValueError):
            continue
        if learning.get("should_write"):
            write_learning_to(mem, learning)
            written += 1
    queue_path().unlink(missing_ok=True)
    _stamp_drain()
    print(f"drained {len(entries)} commit(s), filed {written} learning(s) into {mem}")
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
    # Prove the apply->consolidate path against an isolated throwaway memory.
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="autolearn_selftest_"))
    try:
        (tmp / "MEMORY.md").write_text(
            "# Memory\n\n## RESOLVER\n\n| When you're about to... | Consult |\n|---|---|\n",
            encoding="utf-8",
        )
        fname = write_learning_to(
            tmp,
            {
                "type": "feedback",
                "name": "autolearn-selftest",
                "description": "when you're about to test autolearn",
                "body": "selftest OK",
                "resolver_intent": "when testing autolearn",
            },
        )
        text = (tmp / "MEMORY.md").read_text(encoding="utf-8")
        ok = (tmp / fname).exists() and "autolearn-selftest" in text
        print("autolearn write path: OK" if ok else "autolearn write path: FAILED")
        return 0 if ok else 1
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
