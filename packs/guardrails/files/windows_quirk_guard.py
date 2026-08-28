#!/usr/bin/env python
"""windows_quirk_guard.py -- PreToolUse hook for the Windows shell-composition traps.

`packs/windows-shell/files/windows_gotchas.md` documents these in prose. Prose is
not enough for any of them, and the reason is structural: they are mistakes you
make WHILE COMPOSING A TOOL CALL, mid-turn. A memory or a constitution rule is
read at the start of a turn, long before the mistake is typed. Only a hook has an
attachment point at the moment of the error.

So this is the enforcement half of the windows-shell pack. Each rule below maps
to a numbered gotcha in that file, and each was measured on a real machine
(441 sessions, 46,857 tool calls) rather than imagined.

TWO MODES
    BLOCK  (exit 2)  -- the composition is ALREADY broken; running it can only
                        waste a turn. There is always a correct alternative
                        (Write/Edit, `-F <file>`, the PowerShell tool), so these
                        have no bypass.
    ADVISE (exit 0)   -- a code pattern that will bite later. One line of JSON on
                        stdout; the tool call proceeds.

CONFIGURATION
    CLAUDE_LOCAL_PKGS   comma-separated top-level package names for the
                        cwd-is-the-import-path rule. Defaults to whatever looks
                        like a local package in the current directory.

Exit codes: 0 allow (advisory JSON on stdout), 2 block (reason on stderr).
"""
from __future__ import annotations

import ast
import json
import os
import pathlib
import re
import sys

DOCS = "packs/windows-shell/files/windows_gotchas.md"


# ---------------------------------------------------------------------------
# BLOCK 1 -- PowerShell here-string syntax inside a BASH command.  (gotcha 5)
#
# bash has no `@'...'@` operator, so BOTH delimiter lines survive as literal
# CONTENT: the string is silently corrupted at both ends. Commit messages and PR
# bodies written this way ship with a stray `@'` first line and `'@` last line.
# Anchored to whole lines so an @ inside prose, an email address or a decorator
# cannot match.
# ---------------------------------------------------------------------------
PS_HERESTRING = re.compile(r"""^[ \t]*(?:@['\"]|['\"]@)[ \t]*$""", re.M)

PS_HERESTRING_MSG = (
    "BLOCKED by windows_quirk_guard: PowerShell here-string syntax (@'...'@) inside a "
    "BASH command.\n"
    "bash has no such operator, so both delimiter lines survive as literal content -- "
    "the string is corrupted at both ends, silently, with exit 0.\n\n"
    "Do this instead:\n"
    "  * commit / PR body -> write the text to a file, then `git commit -F <file>`\n"
    "  * inline text      -> a real bash heredoc:  cmd <<'EOF' ... EOF\n"
    "  * file content     -> the Write tool\n"
    "  * you genuinely want a here-string -> use the PowerShell tool, not Bash\n"
    f"See {DOCS} (gotcha 5)."
)


# ---------------------------------------------------------------------------
# BLOCK 2 -- PowerShell pipeline vars ($_ / $PSItem) invoked THROUGH bash.
#
# bash expands `$_` itself -- its own "last argument of the previous command"
# special variable -- before powershell.exe ever sees the string. The result is
# silent corruption, not a syntax error: `$_.TaskName` became `extglob.TaskName`
# on one measured occasion, because bash's `$_` happened to hold "extglob" from a
# prior `shopt`. It reliably breaks whenever the outer command is double-quoted,
# which PowerShell script blocks force (their own literals are single-quoted).
# ---------------------------------------------------------------------------
PS_INVOKE = re.compile(r"\b(?:powershell(?:\.exe)?|pwsh(?:\.exe)?)\b", re.IGNORECASE)
PS_DOLLAR_UNDERSCORE = re.compile(r"(?<!\\)\$(?:_\b|PSItem\b)")

def _strip_quoted_heredoc_bodies(cmd: str) -> str:
    """Blank out the bodies of QUOTED-delimiter heredocs, for the `$_` rule only.

    Why this narrowing is safe, and why it is not the one GUARD_DESIGN rule 2
    warns about. That bypass came from ignoring a heredoc body fed to an
    INTERPRETER, where the body IS the program. This is a different claim, and a
    mechanical one: `<<'EOF'` suppresses shell expansion entirely, so a `$_`
    inside such a body is never expanded by anything, whoever consumes it. The
    trap needs bash to substitute; with a quoted delimiter bash does not.

    Paid for immediately: the commit message describing this very guard contains
    the words `$_` and `powershell`, and the guard blocked its own commit. Rule 3
    -- a guard that cries wolf on its own explanation gets ignored.

    Deliberately NOT applied to the here-string rule: an `@'...'@` inside a
    commit-message heredoc is precisely the real bug (the delimiters survive as
    content and corrupt the message), so that one must still see the body.
    """
    out, pos = [], 0
    for m in HEREDOC_Q.finditer(cmd):
        rest = cmd[m.end():]
        end = re.search(rf"^\s*{re.escape(m.group(2))}\s*$", rest, re.MULTILINE)
        body_end = m.end() + (end.start() if end else len(rest))
        out.append(cmd[pos:m.end()])
        pos = body_end
    out.append(cmd[pos:])
    return "".join(out)


PS_VAR_MSG = (
    "BLOCKED by windows_quirk_guard: PowerShell pipeline syntax ($_ / $PSItem) invoked "
    "via the Bash tool.\n"
    "bash pre-expands `$_` (its OWN special var) before powershell.exe sees the string, "
    "so the script is silently corrupted rather than failing loudly.\n"
    "No bypass -- run it through a PowerShell tool/shell directly, same syntax, no bash "
    "re-interpretation:\n"
    "  Get-ScheduledTask | Where-Object { $_.TaskName -like '*macro*' }\n"
    f"See {DOCS} (gotcha 5)."
)


# ---------------------------------------------------------------------------
# BLOCK 3 -- a python heredoc that is ALREADY BROKEN before it runs. (gotcha 9)
#
# DETECT THE SYMPTOM, NOT THE CAUSE. The cause is a `\n` inside a string literal
# being turned into a REAL newline by the shell -- but by the time a hook sees the
# command that has ALREADY happened, so a regex hunting for a backslash-n finds
# nothing. Parsing the body catches it, and catches every other way heredoc'd
# python arrives broken.
#
# QUOTED DELIMITERS ONLY (`<<'EOF'` / `<<"EOF"`). An unquoted heredoc is shell-
# expanded, so its body need not be valid python as written; checking it would
# false-positive.
# ---------------------------------------------------------------------------
HEREDOC_Q = re.compile(r"<<-?\s*(['\"])(\w+)\1")


def _heredoc_bodies(cmd: str, interpreter_only: bool = False):
    """Yield (delim, body) for each quoted heredoc that carries PYTHON.

    Two narrowings, both paid for by real false positives:

    * Only the FINAL command in a chain receives the heredoc. Testing the whole
      opener line blocked `python -m pytest x.py && git commit -F - <<'MSG'`,
      where the interpreter runs first and `git commit` is what reads stdin.
    * A heredoc feeding `git commit -F -`, `mail`, `jq` or `cat > notes.md` is
      DATA, not a program. Only an interpreter running it -- or a redirect
      writing it to a .py file -- makes it code. An early version accepted any
      opener containing `.py` anywhere and blocked a commit whose only sin was
      `git add tests/test_x.py` earlier in the chain.
    """
    for m in HEREDOC_Q.finditer(cmd):
        delim = m.group(2)
        line_start = cmd.rfind("\n", 0, m.start()) + 1
        tail = re.split(r"(?:&&|\|\||[;|&])", cmd[line_start:m.start()])[-1]
        interp = re.search(r"^\s*(?:sudo\s+)?python[0-9.]*(?:\.exe)?\b", tail)
        writes_py = re.search(r"(?:>>?\s*\S*\.py\b|\btee\s+(?:-a\s+)?\S*\.py\b)", tail)
        if not (interp or (writes_py and not interpreter_only)):
            continue
        rest = cmd[m.end():]
        end = re.search(rf"^\s*{re.escape(delim)}\s*$", rest, re.MULTILINE)
        yield delim, (rest[:end.start()] if end else rest).lstrip("\n")


def _broken_python_heredoc(cmd: str):
    """(delim, SyntaxError) for the first quoted python heredoc that won't parse."""
    for delim, body in _heredoc_bodies(cmd):
        if not body.strip():
            continue
        try:
            ast.parse(body)
        except SyntaxError as e:
            return delim, e
        except Exception:
            continue          # never let the guard itself break a legitimate command
    return None


HEREDOC_BLOCK_MSG = (
    "BLOCKED by windows_quirk_guard: this python heredoc is ALREADY BROKEN -- it would "
    "fail the moment it ran.\n"
    "  {kind}: {msg} (line {line}) inside the <<'{delim}' body\n\n"
    "Almost always the known mangling: a `\\n` inside a string or f-string becomes a REAL "
    "newline and splits the literal. Of ~105 SyntaxErrors measured on one machine, ~50 "
    "were exactly this -- artifacts of how the command was COMPOSED, not code errors.\n\n"
    "Do this instead:\n"
    "  * single-site change   -> the Edit tool (it verifies uniqueness)\n"
    "  * new / rewritten file -> the Write tool\n"
    "  * multi-site patch     -> Write a patch .py to a scratch dir, then run it\n"
    f"See {DOCS} (gotcha 9)."
)


# ---------------------------------------------------------------------------
# ADVISE -- code patterns that bite later. High precision: better to miss than to
# nag. GUARD_DESIGN rule 3 -- a guard that is wrong half the time is already dead.
# ---------------------------------------------------------------------------

# gotcha 6: subprocess text mode encodes stdin / decodes stdout through the
# LOCALE codec (cp1252 on Windows), so ONE non-ASCII byte raises
# UnicodeEncodeError inside subprocess's WRITER THREAD. The child then gets no
# stdin and hangs until timeout -- which reads as "the program is broken" rather
# than "the pipe never opened".
SUBPROC_TEXT = re.compile(r"subprocess\.(?:run|Popen|check_output|check_call|call)\b")
TEXT_MODE = re.compile(r"\b(?:text\s*=\s*True|universal_newlines\s*=\s*True)")
HAS_ENCODING = re.compile(r"\bencoding\s*=\s*['\"]")

# gotcha 7: reconfigure() exists on a real console but NOT on every stream a
# child inherits; unguarded it raises AttributeError under Task Scheduler and
# when invoked from another script.
RECONFIGURE = re.compile(r"sys\.(?:stdout|stderr)\.reconfigure\s*\(")
HAS_HASATTR = re.compile(r"hasattr\s*\(\s*sys\.(?:stdout|stderr)\s*,\s*['\"]reconfigure")

# gotcha in pack.yaml note 5: PowerShell 5.1 wraps each stderr line of a NATIVE
# exe as a NativeCommandError and flips $? to false even on exit 0.
PS_NATIVE_REDIR = re.compile(
    r"\b(git|npm|node|python[0-9.]*|cargo|go|docker|pnpm|yarn|gh|dotnet)\b[^\n]*2>&1",
    re.IGNORECASE)


def _subprocess_text_without_encoding(cmd: str) -> bool:
    return bool(SUBPROC_TEXT.search(cmd) and TEXT_MODE.search(cmd)
                and not HAS_ENCODING.search(cmd))


def _reconfigure_unguarded(cmd: str) -> bool:
    return bool(RECONFIGURE.search(cmd) and not HAS_HASATTR.search(cmd))


def _ps_native_redirect(cmd: str) -> bool:
    """Only in a PowerShell context. `2>&1` in bash is ordinary and correct, so
    firing on every bash redirect would make this guard noise within a day."""
    if not PS_NATIVE_REDIR.search(cmd):
        return False
    return bool(PS_INVOKE.search(cmd)) or _POWERSHELL_TOOL[0]


# gotcha 8: cwd IS the python import path (there is no PYTHONPATH carrying the
# repo), so `cd subdir && python -c "import mypkg"` raises ModuleNotFoundError
# and blames a dependency that was never missing. Measured 94 times on one
# machine, 96% of them LOCAL packages rather than absent third-party ones.
#
# The package names cannot be hardcoded in a framework, so they are discovered:
# a top-level directory holding at least one .py file looks importable from the
# repo root and not from a subdirectory. Discovery is one listdir, cached.
_IGNORE_DIRS = {"node_modules", "venv", ".venv", "env", "build", "dist",
                "site-packages", "__pycache__", "htmlcov"}


def _local_packages() -> tuple[str, ...]:
    env = os.environ.get("CLAUDE_LOCAL_PKGS")
    if env:
        return tuple(p.strip() for p in env.split(",") if p.strip())
    try:
        root = pathlib.Path.cwd()
        out = []
        for d in root.iterdir():
            if not d.is_dir() or d.name.startswith(".") or d.name in _IGNORE_DIRS:
                continue
            try:
                if any(f.suffix == ".py" for f in d.iterdir()):
                    out.append(d.name)
            except OSError:
                continue
        return tuple(out)
    except OSError:
        return ()


_PKGS = _local_packages()
_PKG_ALT = "|".join(re.escape(p) for p in _PKGS) if _PKGS else None

# The `cd` is what moves cwd off the repo root; without it the import resolves.
CD_THEN_PY = re.compile(r"\bcd\s+[^\s;&|]+[^\n]*?(?:&&|;)\s*[^\n]*?\bpython[0-9.]*\b", re.S)
LOCAL_IMPORT = (re.compile(r"(?:^|[\s'\"(])(?:import|from)\s+(?:" + _PKG_ALT + r")(?:\.|[\s'\")])")
                if _PKG_ALT else None)
DASH_M_LOCAL = (re.compile(r"\bpython[0-9.]*\s+(?:-\w+\s+)*-m\s+(?:" + _PKG_ALT + r")\b")
                if _PKG_ALT else None)


def _local_import_off_root(cmd: str) -> bool:
    if LOCAL_IMPORT is None:
        return False                       # nothing importable here; rule is inert
    if not LOCAL_IMPORT.search(cmd) and not DASH_M_LOCAL.search(cmd):
        return False
    return bool(CD_THEN_PY.search(cmd))


# gotcha 9, second shape: a python heredoc carrying a CODE PAYLOAD.
#
# The BLOCK rule above ast.parse()s the heredoc BODY, so it catches a heredoc
# whose own python is broken. It is blind BY CONSTRUCTION to this one: the body
# is VALID python, and what gets mangled is a triple-quoted PAYLOAD inside it --
# code on its way into another file. ast.parse(body) succeeds, the script runs,
# and the file it WRITES is what fails to parse, one step removed from the
# command you are reading.
#
# Same principle as the rule above: detect the SYMPTOM. The first draft of this
# rule hunted for a backslash-n inside the payload and fired on nothing, for the
# reason written in the comment directly above it. Parse the payload instead.
#
# Prose payloads (commit bodies, notes) and SQL do not look like python, so they
# are skipped before parsing -- and both are negative controls in the test suite,
# not assumptions.
_TRIPLE_Q = re.compile(r"('''|\"\"\")(.*?)\1", re.DOTALL)
# A python STATEMENT at the start of some line. `SELECT a FROM t WHERE x = 1`
# does not match (its `=` is mid-line); `Dear user,` does not match.
_LOOKS_PY = re.compile(
    r"^\s*(?:import\s|from\s+\w|def\s|class\s|print\(|[\w.]+\s*=\s*\S)", re.MULTILINE)


def _dedent(text: str) -> str:
    """Strip the common leading indent. Inlined rather than importing textwrap --
    a hook should add as little import surface as possible -- so that an indented
    but otherwise VALID payload is not mistaken for a broken one."""
    lines = text.splitlines()
    pads = [len(ln) - len(ln.lstrip()) for ln in lines if ln.strip()]
    pad = min(pads) if pads else 0
    return "\n".join(ln[pad:] if len(ln) >= pad else ln for ln in lines)


def _heredoc_code_payload(cmd: str) -> bool:
    for _delim, body in _heredoc_bodies(cmd, interpreter_only=True):
        for t in _TRIPLE_Q.finditer(body):
            payload = t.group(2)
            if len(payload.strip()) < 12 or not _LOOKS_PY.search(payload):
                continue
            try:
                ast.parse(_dedent(payload))
            except SyntaxError:
                return True
            except Exception:
                continue          # never let an odd payload break the guard
    return False


ADVISORIES = [
    ("subprocess-text-encoding", {"Bash", "PowerShell", "Write", "Edit"},
     _subprocess_text_without_encoding,
     "Windows: subprocess with text=True and no encoding= runs stdin/stdout through the "
     "locale codec (cp1252), so one non-ASCII char raises UnicodeEncodeError in the "
     "WRITER THREAD -- the child gets no stdin and hangs until timeout, which looks like "
     f"the child is broken. Pass encoding=\"utf-8\". [{DOCS} #6]"),
    ("reconfigure-unguarded", {"Bash", "PowerShell", "Write", "Edit"},
     _reconfigure_unguarded,
     "sys.stdout.reconfigure() raises AttributeError when stdout is not a real console "
     "(Task Scheduler, or invoked from another script). Guard it: "
     "if hasattr(sys.stdout, \"reconfigure\"): sys.stdout.reconfigure(encoding=\"utf-8\") "
     f"[{DOCS} #7]"),
    ("ps-native-redirect", {"Bash", "PowerShell"}, _ps_native_redirect,
     "Windows PowerShell 5.1: `2>&1` on a NATIVE exe wraps each stderr line as a "
     "NativeCommandError and flips $? to false even on exit 0. Don't redirect native "
     "stderr -- it is already captured."),
    ("local-import-needs-repo-root", {"Bash", "PowerShell"}, _local_import_off_root,
     "This `cd` moves cwd off the repo root, and cwd IS the python import path here: the "
     "same import works from the root and raises ModuleNotFoundError from a "
     "subdirectory. Measured 94 times on one machine, 96% of them local packages rather "
     f"than missing deps. Drop the cd and use absolute paths, or prefix `PYTHONPATH=. `. [{DOCS} #8]"),
    ("heredoc-code-payload", {"Bash"}, _heredoc_code_payload,
     "This heredoc carries CODE inside a triple-quoted payload. The heredoc body itself "
     "parses, so the BLOCK rule cannot see it -- but the shell mangles escapes in that "
     "payload, and the file you write ends up broken one step removed from this command. "
     f"Write the patch script with the Write tool, then run it. [{DOCS} #9]"),
]

# Set once in main() so _ps_native_redirect can tell a PowerShell tool call from
# a bash one without threading the tool name through every predicate signature.
_POWERSHELL_TOOL = [False]

# Write/Edit carry the code itself, and a rule about code belongs at the moment
# the code is AUTHORED, not when a filename is later executed. But only when the
# target IS code: a .md/.txt/.rst file is PROSE, and prose about these traps
# necessarily quotes them. Measured -- writing a docs page about the Windows
# traps fired two of these advisories three times on the text describing them.
# A guard that cries wolf on its own explanation gets ignored.
_CODE_SUFFIXES = (".py", ".ps1", ".psm1", ".sh", ".bash", ".js", ".mjs",
                  ".ts", ".tsx", ".jsx", ".rb", ".pl", ".bat", ".cmd")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception as e:                                          # noqa: BLE001
        print(f"[windows_quirk_guard] failed to parse stdin: {e}", file=sys.stderr)
        return 0

    tool = payload.get("tool_name") or payload.get("tool") or ""
    inp = payload.get("tool_input") or {}
    if not isinstance(inp, dict):
        return 0
    cmd = inp.get("command") or ""
    if not isinstance(cmd, str):
        cmd = ""
    _POWERSHELL_TOOL[0] = tool == "PowerShell"

    fp = inp.get("file_path") or inp.get("path") or ""
    fp = str(fp) if isinstance(fp, (str, bytes)) else ""
    is_code = fp.lower().endswith(_CODE_SUFFIXES) if fp else True
    if is_code:
        for key in ("content", "new_string"):
            v = inp.get(key)
            if isinstance(v, str) and v:
                cmd = cmd + "\n" + v

    if tool == "Bash" and cmd:
        if PS_HERESTRING.search(cmd):
            print(PS_HERESTRING_MSG, file=sys.stderr)
            return 2
        expandable = _strip_quoted_heredoc_bodies(cmd)
        if PS_INVOKE.search(expandable) and PS_DOLLAR_UNDERSCORE.search(expandable):
            print(PS_VAR_MSG, file=sys.stderr)
            return 2
        broken = _broken_python_heredoc(cmd)
        if broken:
            delim, err = broken
            print(HEREDOC_BLOCK_MSG.format(kind=type(err).__name__, msg=err.msg,
                                           line=err.lineno, delim=delim), file=sys.stderr)
            return 2

    notes = []
    for name, tools, matcher, msg in ADVISORIES:
        if tool not in tools:
            continue
        # `matcher` may be a predicate OR a compiled regex. This branch is why
        # the original went dark for a day: predicates were added while the loop
        # still called `.search()`, so EVERY matched call raised AttributeError
        # and the guard exited 1 -- which PreToolUse treats as a NON-BLOCKING
        # error. A guard cannot report that it is broken; it just goes quiet.
        # Test the DISPATCH, not just the matcher (GUARD_DESIGN rule 6).
        try:
            hit = matcher(cmd) if callable(matcher) else bool(matcher.search(cmd))
        except Exception:                                           # noqa: BLE001
            continue          # one bad matcher must never silence the others
        if hit:
            notes.append(f"[{name}] {msg}")

    if notes:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": "Windows shell reminder (non-blocking):\n" + "\n".join(notes),
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
