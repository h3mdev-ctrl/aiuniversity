#!/usr/bin/env python
"""setup_session_guard.py -- install the session-end Stop hook + prove it bounces.

Companion guard to the credential guard: it stops Claude signing off with "go rest /
call it a day / you've done enough" phrases, which a builder mid-flow reads as
friction. The behavioural check proves it (a) bounces a real sign-off, (b) does NOT
bounce the same phrase when it's merely QUOTED (in code / a blockquote), and (c)
lets a clean response through.

Modes:
    (no arg) / --install     install the hook + register it as a Stop hook
    --check-hook-file        exit 0 if the hook script is installed
    --check-registered       exit 0 if settings.json registers it (Stop)
    --test-blocking          behavioural: prose sign-off blocks; quoted passes; clean passes

Home: $CLAUDE_HOME or ~/.claude ; hook at <home>/hooks/session_end_guard.py ;
settings merged into <home>/settings.json.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys

HOOK_NAME = "session_end_guard.py"
GUARD_MARKER = "session_end_guard.py"


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
    if dst.exists():
        return False
    shutil.copyfile(src, dst)
    try:
        os.chmod(dst, 0o755)
    except Exception:
        pass
    return True


def _registered(stop_entries: list) -> bool:
    for entry in stop_entries or []:
        for h in (entry.get("hooks") or []):
            if GUARD_MARKER in (h.get("command", "") or ""):
                return True
    return False


def _merge_into_settings() -> bool:
    p = settings_path()
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    stop = data.setdefault("hooks", {}).setdefault("Stop", [])
    if _registered(stop):
        return False
    stop.append({"hooks": [{"type": "command", "command": f'python "{hook_path()}"'}]})
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return True


def install() -> int:
    parts = []
    if _install_hook_file():
        parts.append(f"installed hook at {hook_path()}")
    if _merge_into_settings():
        parts.append(f"registered (Stop) in {settings_path()}")
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
    return 0 if _registered((data.get("hooks") or {}).get("Stop") or []) else 1


def _pipe(response_text: str) -> int:
    return subprocess.run(
        [sys.executable, str(hook_path())],
        input=json.dumps({"response": response_text}),
        capture_output=True, text=True, encoding="utf-8",
    ).returncode


def test_blocking() -> int:
    if not hook_path().exists():
        print("hook not installed -- run --install first")
        return 1
    cases = [
        ("prose sign-off",  "Great work. Good night, get some rest!", True),
        ("quoted phrase",   "The guard bans `good night` and blockquoted rules.", False),
        ("blockquoted",     "> call it a day\n\nHere's the summary. Ready for the next one.", False),
        ("clean",           "Shipped X; Y is now unblocked. Ready for the next one.", False),
    ]
    failed = []
    for label, text, should_block in cases:
        rc = _pipe(text)
        blocked = rc != 0
        ok = blocked if should_block else not blocked
        print(f"  {'OK ' if ok else 'FAIL '}{label}: rc={rc}")
        if not ok:
            failed.append(label)
    if failed:
        print(f"guard misbehaved on: {', '.join(failed)}")
        return 1
    print("bounces a real sign-off, ignores quoted phrases, allows a clean close")
    return 0


def main(argv: list[str]) -> int:
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
