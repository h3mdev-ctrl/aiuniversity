#!/usr/bin/env python
"""setup_windows_quirk_guard.py -- install the Windows shell-composition guard + prove it.

The windows-shell pack DOCUMENTS these traps; this installs the half that fires at
the moment you make one. The behavioural check proves both directions: it bounces
a PowerShell here-string in bash, a broken python heredoc and a `$_` pipeline sent
through bash, and it stays SILENT on the near-misses those rules could easily eat
(a valid heredoc, an ordinary command, a prose file that merely describes the
traps).

Modes:
    (no arg) / --install     install the hook + register it (PreToolUse)
    --check-hook-file        exit 0 if the hook script is installed
    --check-registered       exit 0 if settings.json registers it
    --test-blocking          behavioural: blocks the three traps, allows the near-misses

Home: $CLAUDE_HOME or ~/.claude ; hook at <home>/hooks/windows_quirk_guard.py ;
settings merged into <home>/settings.json.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys

HOOK_NAME = "windows_quirk_guard.py"
GUARD_MARKER = "windows_quirk_guard.py"
MATCHER = "Bash|PowerShell|Write|Edit"


def base_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))


def hook_path() -> pathlib.Path:
    return base_dir() / "hooks" / HOOK_NAME


def settings_path() -> pathlib.Path:
    return base_dir() / "settings.json"


def _install_hook_file() -> bool:
    (base_dir() / "hooks").mkdir(parents=True, exist_ok=True)
    src = pathlib.Path(__file__).resolve().parent / HOOK_NAME
    dst = hook_path()
    # Always refresh, and report only a genuinely NEW install. A framework guard
    # gets revised, and an installer that skips an existing file leaves the user
    # pinned to whatever they first installed with no upgrade path -- exactly the
    # drift that made a shipped selftest disagree with a live hook.
    existed = dst.exists()
    shutil.copyfile(src, dst)
    try:
        os.chmod(dst, 0o755)
    except Exception:
        pass
    return not existed


def _registered(entries: list) -> bool:
    for entry in entries or []:
        for h in (entry.get("hooks") or []):
            if GUARD_MARKER in (h.get("command", "") or ""):
                return True
    return False


def _merge_into_settings() -> bool:
    p = settings_path()
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
    if _registered(pre):
        return False
    pre.append({"matcher": MATCHER,
                "hooks": [{"type": "command", "command": f'python "{hook_path()}"'}]})
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return True


def install() -> int:
    parts = []
    if _install_hook_file():
        parts.append(f"installed hook at {hook_path()}")
    if _merge_into_settings():
        parts.append(f"registered (PreToolUse) in {settings_path()}")
    print("; ".join(parts) or "already set up")
    return 0


def check_hook_file() -> int:
    return 0 if hook_path().exists() else 1


def check_registered() -> int:
    p = settings_path()
    if not p.exists():
        return 1
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 1
    return 0 if _registered((data.get("hooks") or {}).get("PreToolUse") or []) else 1


def _pipe(payload: dict) -> tuple[int, str]:
    p = subprocess.run(
        [sys.executable, str(hook_path())],
        input=json.dumps(payload).encode("utf-8"), capture_output=True,
    )
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")


# (label, payload, expect) where expect is block | allow | advise.
# Every BLOCK case is paired with the near-miss it must not eat: an unguarded
# guard that blocks everything would otherwise score full marks here.
def _cases():
    bash = lambda c: {"tool_name": "Bash", "tool_input": {"command": c}}   # noqa: E731
    return [
        ("PS here-string in bash",
         bash("git commit -m @'\nSubject\n\nBody\n'@"), "block"),
        ("broken python heredoc",
         bash("python - <<'PY'\nprint('a\nb'\nPY"), "block"),
        ("$_ sent to powershell through bash",
         bash("powershell -c \"Get-Process | ? { $_.Name -like 'x*' }\""), "block"),

        # The narrowing in _strip_quoted_heredoc_bodies, pinned in BOTH directions:
        # a quoted delimiter suppresses expansion, so prose ABOUT the trap is fine;
        # the same text where bash WOULD expand it must still block.
        ("prose naming $_ and powershell, in a quoted heredoc",
         bash("git commit -F - <<'MSG'\nfix: $_ pre-expanded by bash before powershell "
              "sees it\nMSG"), "allow"),
        ("the same text where bash WOULD expand it",
         bash("powershell -c \"gps | ? { $_.Name }\""), "block"),

        ("valid python heredoc", bash("python - <<'PY'\nprint('hello')\nPY"), "allow"),
        ("prose heredoc to git commit -F -",
         bash("git commit -q -F - <<'MSG'\nfix(x): a message\n\nBody line.\nMSG"), "allow"),
        ("ordinary command", bash("git status --short"), "allow"),

        ("text=True with no encoding (Write)",
         {"tool_name": "Write",
          "tool_input": {"file_path": "x.py",
                         "content": "import subprocess\nsubprocess.run(c, text=True)\n"}},
         "advise"),
        ("the same text in a PROSE file",
         {"tool_name": "Write",
          "tool_input": {"file_path": "notes.md",
                         "content": "Avoid subprocess.run(c, text=True) with no encoding.\n"}},
         "allow"),
    ]


def test_blocking() -> int:
    if not hook_path().exists():
        print("hook not installed -- run --install first")
        return 1
    failed = []
    for label, payload, expect in _cases():
        rc, out = _pipe(payload)
        said = bool(out.strip())
        if expect == "block":
            ok = rc == 2
        elif expect == "advise":
            ok = rc == 0 and said
        else:
            ok = rc == 0 and not said
        print(f"  {'OK ' if ok else 'FAIL '}{label}: rc={rc}{'' if ok else ' -- ' + out.strip()[:120]}")
        if not ok:
            failed.append(label)
    if failed:
        print(f"guard misbehaved on: {', '.join(failed)}")
        return 1
    print("blocks the three composition traps, advises on the code patterns, "
          "and stays silent on the near-misses")
    return 0


def main(argv) -> int:
    mode = argv[1] if len(argv) > 1 else "--install"
    dispatch = {
        "--install": install, "--check-hook-file": check_hook_file,
        "--check-registered": check_registered, "--test-blocking": test_blocking,
    }
    fn = dispatch.get(mode)
    if fn is None:
        print(f"unknown mode {mode!r}")
        return 2
    return fn()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main(sys.argv))
