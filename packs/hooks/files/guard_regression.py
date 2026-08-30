#!/usr/bin/env python
"""guard_regression -- does each guard still CATCH what it was built for?

    python packs/hooks/files/guard_regression.py
    python packs/hooks/files/guard_regression.py --verbose
    python packs/hooks/files/guard_regression.py --json

WHY THIS EXISTS
---------------
`hook_doctor.py` answers "is this hook alive?" -- it feeds every registered hook
a BENIGN payload and fails if it crashes. That is the liveness layer, and its
own docstring names the gap it leaves:

    "That a guard BLOCKS what it should block ... needs a per-hook positive
     control. The doctor is the liveness layer, not the correctness layer."

This is that correctness layer. GUARD_DESIGN rule 6 argues for both:

    liveness    -- is it firing at all?               (hook_doctor.py)
    correctness -- does it still catch what it was    (this file)
                   built for, and still ignore what
                   it should?

A hook can pass liveness with a matcher that no longer matches ANYTHING. That
is exactly what a dark advisory list looks like from the outside: alive, quiet,
useless. On the machine this came from, a guard's whole advisory list went dark
for a day because predicates were added to a list the dispatch loop still called
`.search()` on. The doctor said HEALTHY. It was, and it caught nothing.

WHAT "SKIPPED" MEANS -- READ THIS ONE
-------------------------------------
A guard you have not installed produces SKIPPED cases, never passing ones. An
all-green run with nine skips is not a green run, and the verdict line says so.
The same applies in reverse: a hook you have registered with NO cases here is
reported as UNCOVERED. Neither is a failure -- both are things you cannot claim
you checked.

ADDING YOUR OWN CASES
---------------------
Drop a `guard_cases.json` in your Claude home ($CLAUDE_HOME or ~/.claude) to
extend or override the built-in suites:

    {
      "my_guard.py": {
        "cases": [
          {"label": "footgun X is blocked", "event": "PreToolUse",
           "tool": "Bash", "input": {"command": "..."}, "expect": "block"},
          {"label": "the near-miss is allowed", "event": "PreToolUse",
           "tool": "Bash", "input": {"command": "..."}, "expect": "allow"}
        ]
      }
    }

One case per footgun you have ACTUALLY hit, each with its negative control --
the near-miss that must stay silent. A suite of positives alone will happily
pass a guard that blocks everything, which GUARD_DESIGN rule 3 says is already
dead.

A case may also pin `"cwd"`, for a hook that resolves its inputs from the process
working directory rather than the payload. Without it such a hook is untestable
and gets excluded -- which is exactly how a retriever going dark stays invisible.

DECLARING WHAT YOU ARE *NOT* COVERING
-------------------------------------
`"_EXCLUDE": {"<hook>.py": "<reason>"}` moves a hook out of UNCOVERED and prints
the reason instead. This is not a way to make the list shorter: UNCOVERED should
mean "nobody has decided about this", so a real gap cannot hide among hooks that
were deliberately left alone. A guard that has cases is still exercised even if
someone also lists it here.

The reason that matters most: **a hook whose job IS a side effect must never be
driven by a harness.** A case for a notifier posts a real message; a case for an
auto-committer makes a real commit. Say that, and move on.

`expect` is one of:
    block   -- exit 2
    allow   -- exit 0 and nothing said
    advise  -- exit 0 and `contains` appears in the output (a non-blocking
               reminder; advisories are JSON on STDOUT, which is why this
               harness reads both streams)

EXIT: 0 = every case that could run behaved; 1 = at least one regression.
"""
from __future__ import annotations

import json
import os
import pathlib
import shlex
import subprocess
import sys

BLOCK, ALLOW = 2, 0
VERBOSE = "--verbose" in sys.argv
AS_JSON = "--json" in sys.argv


def base_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))


def hooks_dir() -> pathlib.Path:
    return base_dir() / "hooks"


def settings_path() -> pathlib.Path:
    return base_dir() / "settings.json"


def setup_dir() -> pathlib.Path | None:
    """Where the `setup_*.py` selftests live, for suites that delegate.

    Some guards cannot be exercised with a bare payload -- the recon guard needs
    a populated fake repo and a fresh session id, and builds one in its own
    setup script. Rather than duplicate that fixture (and let the copy rot), a
    suite may point at the guard's own selftest. It is resolved from, in order:
    $AIU_GUARD_SETUP_DIR, the guardrails pack next to this file, or None -- and
    None means SKIP, never pass.
    """
    env = os.environ.get("AIU_GUARD_SETUP_DIR")
    if env and pathlib.Path(env).is_dir():
        return pathlib.Path(env)
    here = pathlib.Path(__file__).resolve().parent          # packs/hooks/files
    cand = here.parent.parent / "guardrails" / "files"      # packs/guardrails/files
    return cand if cand.is_dir() else None


# ---------------------------------------------------------------------------
# Built-in suites, one per guard this framework ships.
#
# Every case below is a footgun that was actually hit on a real machine, with
# the near-miss that must stay silent sitting next to it. Where a guard needs a
# fixture, the suite delegates to that guard's own selftest instead of forking a
# second copy of the fixture.
# ---------------------------------------------------------------------------
SUITES: dict[str, dict] = {
    "credential_guard.py": {
        "cases": [
            {"label": "Read of a .env is BLOCKED", "event": "PreToolUse",
             "tool": "Read", "input": {"file_path": "/x/.env"}, "expect": "block"},
            {"label": "cat .env through Bash is BLOCKED", "event": "PreToolUse",
             "tool": "Bash", "input": {"command": "cat .env && ls"}, "expect": "block"},
            {"label": "a private key is BLOCKED", "event": "PreToolUse",
             "tool": "Read", "input": {"file_path": "~/.ssh/id_rsa"}, "expect": "block"},
            # Fail-closed: a payload it cannot understand must not become a pass.
            {"label": "malformed payload FAILS CLOSED", "event": "PreToolUse",
             "tool": "Read", "input": {"file_path": {"a": 1}}, "expect": "block"},
            # Negative controls -- without these, "blocks everything" scores 4/4.
            {"label": "an ordinary command is silent", "event": "PreToolUse",
             "tool": "Bash", "input": {"command": "git status --short"}, "expect": "allow"},
            {"label": "reading a normal file is silent", "event": "PreToolUse",
             "tool": "Read", "input": {"file_path": "README.md"}, "expect": "allow"},
        ],
    },
    "session_end_guard.py": {
        "cases": [
            {"label": "a real sign-off is BLOCKED", "event": "Stop",
             "payload": {"response": "Great work. Good night, get some rest!"},
             "expect": "block"},
            # The narrowing, pinned: quoting the phrase is not saying it.
            {"label": "the phrase merely QUOTED is silent", "event": "Stop",
             "payload": {"response": "The guard bans `good night` and similar."},
             "expect": "allow"},
            {"label": "a clean close is silent", "event": "Stop",
             "payload": {"response": "Shipped X; Y is unblocked. Ready for the next one."},
             "expect": "allow"},
        ],
    },
    "recon_before_build_guard.py": {
        # Needs a populated fake repo and a fresh session id -- see setup_dir().
        "selftest": ("setup_recon_build_guard.py", "--test-blocking"),
        "cases": [
            {"label": "a .md write is silent", "event": "PreToolUse",
             "tool": "Write", "input": {"file_path": "NOTES.md", "content": "x"},
             "expect": "allow"},
        ],
    },
    "windows_quirk_guard.py": {
        "cases": [
            {"label": "PowerShell here-string inside bash is BLOCKED",
             "event": "PreToolUse", "tool": "Bash",
             "input": {"command": "git commit -m @'\nSubject\n\nBody\n'@"},
             "expect": "block", "contains": "here-string"},
            {"label": "a broken python heredoc is BLOCKED",
             "event": "PreToolUse", "tool": "Bash",
             "input": {"command": "python - <<'PY'\nprint('a\\nb'\nPY"},
             "expect": "block"},
            {"label": "$_ piped to powershell from bash is BLOCKED",
             "event": "PreToolUse", "tool": "Bash",
             "input": {"command": "powershell -c \"Get-Process | ? { $_.Name -like 'x*' }\""},
             "expect": "block"},
            {"label": "prose naming the $_ trap in a quoted heredoc is silent",
             "event": "PreToolUse", "tool": "Bash",
             "input": {"command": "git commit -F - <<'MSG'\nfix: $_ pre-expanded by "
                                  "bash before powershell sees it\nMSG"},
             "expect": "allow"},
            {"label": "text=True without encoding= advises (on WRITE)",
             "event": "PreToolUse", "tool": "Write",
             "input": {"file_path": "x.py",
                       "content": "import subprocess\nsubprocess.run(cmd, text=True)\n"},
             "expect": "advise", "contains": "subprocess-text-encoding"},
            {"label": "an unguarded reconfigure advises",
             "event": "PreToolUse", "tool": "Bash",
             "input": {"command": 'python -c "sys.stdout.reconfigure(encoding=chr(34))"'},
             "expect": "advise", "contains": "reconfigure-unguarded"},
            {"label": "a heredoc carrying broken CODE advises",
             "event": "PreToolUse", "tool": "Bash",
             "input": {"command": "python - <<'PY'\nimport io\nnew = '''x = 1\n"
                                  "print(f\"\n===== run \" + s)\n'''\nio.open(p,'w').write(new)\nPY"},
             "expect": "advise", "contains": "heredoc-code-payload"},
            # Negative controls. The .md one is load-bearing: an earlier version
            # of this guard scanned prose the same way it scanned code, and fired
            # three times on a docs page DESCRIBING these very traps.
            {"label": "a plain command is silent", "event": "PreToolUse",
             "tool": "Bash", "input": {"command": "git status --short"}, "expect": "allow"},
            {"label": "a valid heredoc is silent", "event": "PreToolUse",
             "tool": "Bash", "input": {"command": "python - <<'PY'\nprint('hello')\nPY"},
             "expect": "allow"},
            {"label": "prose ABOUT the traps is silent (.md)",
             "event": "PreToolUse", "tool": "Write",
             "input": {"file_path": "gotchas.md",
                       "content": "Avoid subprocess.run(cmd, text=True) with no encoding.\n"},
             "expect": "allow"},
        ],
    },
}

# Payload skeletons per event, so a case only has to state what matters.
EVENT_DEFAULTS = {
    "PreToolUse": {"session_id": "guard-regression", "transcript_path": "",
                   "hook_event_name": "PreToolUse"},
    "PostToolUse": {"session_id": "guard-regression", "transcript_path": "",
                    "hook_event_name": "PostToolUse"},
    "Stop": {"transcript_path": "", "stop_hook_active": False},
}


def load_user_file() -> dict:
    p = base_dir() / "guard_cases.json"
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"! {p} is not readable JSON: {exc} -- ignoring", file=sys.stderr)
        return {}
    return data if isinstance(data, dict) else {}


def load_exclusions(raw: dict) -> dict:
    """`_EXCLUDE`: {hook: reason} -- hooks deliberately left uncovered.

    A hook with no cases is reported UNCOVERED, which is the right default: you
    cannot claim to have checked it. But some SHOULD stay uncovered, and lumping
    those in with the genuinely-unexamined ones makes the list noise that gets
    skimmed -- at which point a real gap hides in it.

    Declaring a reason is not the same as excusing it. The reason is PRINTED, so
    "no case for this" stays a decision someone made and can be argued with,
    rather than an omission nobody noticed.

    The reason that matters most: a hook whose job IS a side effect must never be
    driven by a test harness. A regression case for a notifier posts a real
    message; one for an auto-committer makes a real commit.
    """
    ex = raw.get("_EXCLUDE")
    if not isinstance(ex, dict):
        return {}
    return {k: str(v) for k, v in ex.items() if isinstance(k, str)}


def load_user_suites(data: dict) -> dict:
    if not data:
        return {}
    # JSON has no comments, and a cases file needs them badly: which guards are
    # deliberately NOT covered, and why, is the most useful thing in it -- an absent
    # suite otherwise reads as an oversight rather than a decision. `_`-prefixed keys
    # are notes, not suites.
    return {k: v for k, v in data.items()
            if not k.startswith("_") and isinstance(v, dict)}


def registered_guards() -> set[str]:
    """Guard filenames that settings.json actually registers."""
    p = settings_path()
    if not p.is_file():
        return set()
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    names = set()
    for entries in (doc.get("hooks") or {}).values():
        for entry in entries or []:
            for h in entry.get("hooks", []) or []:
                try:
                    parts = shlex.split(str(h.get("command") or ""), posix=False)
                except ValueError:
                    parts = str(h.get("command") or "").split()
                for tok in parts:
                    q = tok.strip('"').strip("'")
                    if q.lower().endswith(".py"):
                        names.add(pathlib.Path(q).name)
    return names


def build_payload(case: dict) -> dict:
    if "payload" in case:
        payload = dict(case["payload"])
    else:
        payload = {"tool_name": case.get("tool", "Bash"),
                   "tool_input": case.get("input", {})}
    base = dict(EVENT_DEFAULTS.get(case.get("event", "PreToolUse"), {}))
    base.update(payload)
    return base


def run_hook(guard: pathlib.Path, payload: dict, timeout: int = 25, cwd: str | None = None):
    """Bytes in, bytes out. Text mode would route stdin through the locale codec
    on Windows and hang the writer thread on the first non-ASCII byte -- itself
    one of the footguns these guards exist to catch."""
    # A case may pin `cwd`: some hooks resolve their inputs from the PROCESS working
    # directory rather than the payload -- a memory retriever that finds its store by
    # hashing cwd, for instance, is correctly silent when run from anywhere else. Without
    # this, such a hook is untestable and gets excluded, which is how a retriever going
    # dark stays invisible.
    p = subprocess.run([sys.executable, str(guard)],
                       input=json.dumps(payload).encode("utf-8"),
                       capture_output=True, timeout=timeout, cwd=cwd)
    # Advisories are JSON on STDOUT; blocks write to STDERR. Read both -- an
    # earlier harness read only stderr, scored every advisory as silent, and
    # made a perfectly good detector look dead.
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")


def judge(case: dict, rc: int, out: str) -> tuple[bool, str]:
    want = case.get("expect", "allow")
    want_txt = case.get("contains")
    event = case.get("event", "PreToolUse")
    if "Traceback" in out:
        return False, f"CRASHED (rc={rc})"

    # A DEAD guard must fail its silent cases too, and this is the one place that
    # can tell. PreToolUse defines exactly two answers -- 0 allow, 2 block -- and
    # treats anything else as a NON-BLOCKING error, so a guard that crashes with
    # rc=1 and says nothing is indistinguishable from a guard that had nothing to
    # say. Scoring that as a pass is the same bug this harness exists to catch,
    # one level up; it was caught by the mutation test in tests/test_hooks_pack.py
    # (`test_a_dead_guard_fails_every_one_of_its_cases`), not by reading the code.
    #
    # Only PreToolUse has that contract. A Stop hook signals by exiting non-zero,
    # so `rc != 0` is its block, and pinning it to 2 would fail a healthy one.
    if event == "PreToolUse":
        if rc not in (ALLOW, BLOCK):
            return False, (f"rc={rc} -- PreToolUse allows on 0 and blocks on 2; anything "
                           f"else is a non-blocking ERROR, so this guard is BROKEN, not quiet")
        blocked = rc == BLOCK
    else:
        blocked = rc != ALLOW

    if want == "block":
        if not blocked:
            return False, f"rc={rc}, expected a BLOCK"
    elif want == "allow":
        if blocked:
            return False, f"rc={rc}, expected silence but it BLOCKED"
        if out.strip():
            return False, f"rc={rc}, expected silence but it said: {out.strip()[:90]}"
    elif want == "advise":
        if blocked:
            return False, f"rc={rc}, expected an advisory but it BLOCKED"
        if not out.strip():
            return False, f"rc={rc}, expected an advisory but it was silent"
    else:
        return False, f"unknown expect={want!r}"
    if want_txt and want_txt not in out:
        return False, f"rc={rc}, missing {want_txt!r}"
    return True, f"rc={rc}"


def run_selftest(spec, results: list, guard_name: str) -> None:
    d = setup_dir()
    script = None if d is None else d / spec[0]
    label = f"selftest: {spec[0]} {' '.join(spec[1:])}"
    if script is None or not script.is_file():
        results.append(("skip", guard_name, label, "selftest not locatable (set AIU_GUARD_SETUP_DIR)"))
        return
    try:
        p = subprocess.run([sys.executable, str(script), *spec[1:]],
                           capture_output=True, timeout=120)
    except Exception as exc:                                        # noqa: BLE001
        results.append(("fail", guard_name, label, f"harness error: {exc}"))
        return
    out = (p.stdout + p.stderr).decode("utf-8", "replace").strip()
    tail = out.splitlines()[-1] if out else ""
    results.append(("pass" if p.returncode == 0 else "fail", guard_name, label,
                    f"rc={p.returncode} {tail}"[:160]))


def main() -> int:
    raw = load_user_file()
    suites = dict(SUITES)
    for name, spec in load_user_suites(raw).items():
        suites[name] = spec                      # user cases override built-ins
    excluded = load_exclusions(raw)
    installed = registered_guards()

    results: list[tuple[str, str, str, str]] = []
    for guard_name, spec in sorted(suites.items()):
        path = hooks_dir() / guard_name
        if not path.is_file():
            # SKIP, never pass. A guard you have not installed is a guard whose
            # behaviour you have not checked, and the verdict must say that.
            for case in spec.get("cases", []):
                results.append(("skip", guard_name, case["label"], "guard not installed"))
            if spec.get("selftest"):
                results.append(("skip", guard_name, f"selftest: {spec['selftest'][0]}",
                                "guard not installed"))
            continue
        for case in spec.get("cases", []):
            try:
                rc, out = run_hook(path, build_payload(case), cwd=case.get("cwd"))
            except Exception as exc:                                # noqa: BLE001
                results.append(("fail", guard_name, case["label"], f"harness error: {exc}"))
                continue
            ok, detail = judge(case, rc, out)
            results.append(("pass" if ok else "fail", guard_name, case["label"], detail))
        if spec.get("selftest"):
            run_selftest(spec["selftest"], results, guard_name)

    uncovered = sorted(n for n in installed if n not in suites and n not in excluded)
    excluded_here = sorted(n for n in installed if n in excluded)

    n_fail = sum(1 for s, *_ in results if s == "fail")
    n_skip = sum(1 for s, *_ in results if s == "skip")
    n_pass = sum(1 for s, *_ in results if s == "pass")

    if AS_JSON:
        print(json.dumps({
            "results": [{"status": s, "guard": g, "label": l, "detail": d}
                        for s, g, l, d in results],
            "uncovered": uncovered,
            "excluded": {n: excluded[n] for n in excluded_here},
            "passed": n_pass, "failed": n_fail, "skipped": n_skip,
            "verdict": "HEALTHY" if not n_fail else "REGRESSED",
        }, indent=2))
        return 1 if n_fail else 0

    print("=" * 78)
    print("GUARD REGRESSION -- does each guard still catch what it was built for?")
    print("=" * 78)
    cur = None
    marks = {"pass": "  ok  ", "fail": " FAIL ", "skip": " skip "}
    for status, guard, label, detail in results:
        if guard != cur:
            cur = guard
            print(f"\n{guard}")
        print(f"  {marks[status]}  {label}")
        if status != "pass" or VERBOSE:
            print(f"            {detail}")

    print()
    print("-" * 78)
    print(f"{len(results)} cases: {n_pass} pass, {n_fail} FAIL, {n_skip} skipped "
          f"(guard not installed -- NOT a pass)")
    if excluded_here:
        print(f"OUT OF SCOPE: {len(excluded_here)} registered hook(s), by declaration in "
              f"guard_cases.json")
        if VERBOSE:
            for n in excluded_here:
                print(f"             {n:32} {excluded[n]}")
        else:
            print("             (run --verbose to see the reason given for each)")
    if uncovered:
        print(f"UNCOVERED: {len(uncovered)} registered hook(s) have no cases and no stated "
              f"reason -- {', '.join(uncovered)}")
        print("           Either add cases in $CLAUDE_HOME/guard_cases.json, or say why not")
        print("           in its \"_EXCLUDE\" map. Undecided is the one state worth fixing.")
    if n_fail:
        print("\nA FAIL means a footgun you have ALREADY hit is no longer caught.")
        print("Run hook_doctor.py first -- a DEAD hook fails every one of its cases,")
        print("and that is a different repair from a matcher that stopped matching.")
    print("VERDICT:", "HEALTHY" if not n_fail else "REGRESSED")
    return 1 if n_fail else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")            # type: ignore[attr-defined]
    raise SystemExit(main())
