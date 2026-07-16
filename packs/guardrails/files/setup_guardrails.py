#!/usr/bin/env python
"""
setup_guardrails.py -- install PreToolUse guardrail hooks + prove they block.

Guardrails are the layer that catches mistakes by CODE, not by hoping the agent
remembered. v1 ships one core guard (credential_guard) that blocks reads of .env,
private keys, and other credential files. The behavioural check pipes a forbidden
action through the INSTALLED hook and confirms it exits non-zero -- so this pack
proves the guard actually fires end to end, not just that a file is present.

Modes:
    (no arg) / --install       install the hook script + merge into settings.json
    --check-hook-file          exit 0 if the hook script is installed
    --check-registered         exit 0 if settings.json points at it (PreToolUse)
    --test-blocking            behavioural: pipe forbidden + allowed inputs, prove
                               the guard blocks the first and allows the second

Home: $CLAUDE_HOME or ~/.claude ; hook at <home>/hooks/credential_guard.py ;
settings merged into <home>/settings.json.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys

HOOK_NAME = "credential_guard.py"
GUARD_MARKER = "credential_guard.py"   # unique in settings.json entries


def base_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))


def hooks_dir() -> pathlib.Path:
    return base_dir() / "hooks"


def hook_path() -> pathlib.Path:
    return hooks_dir() / HOOK_NAME


def settings_path() -> pathlib.Path:
    return base_dir() / "settings.json"


def _install_hook_file() -> bool:
    hooks_dir().mkdir(parents=True, exist_ok=True)
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


def _already_registered(pretool: list, marker: str) -> bool:
    for entry in pretool or []:
        for h in (entry.get("hooks") or []):
            if marker in (h.get("command", "") or ""):
                return True
    return False


def _merge_into_settings() -> bool:
    p = settings_path()
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    hooks = data.setdefault("hooks", {})
    pretool = hooks.setdefault("PreToolUse", [])
    if _already_registered(pretool, GUARD_MARKER):
        return False
    pretool.append(
        {
            "matcher": "Bash|Read",
            "hooks": [{"type": "command", "command": f'python "{hook_path()}"'}],
        }
    )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return True


def install() -> int:
    wrote_hook = _install_hook_file()
    wrote_reg = _merge_into_settings()
    parts = []
    if wrote_hook:
        parts.append(f"installed hook at {hook_path()}")
    if wrote_reg:
        parts.append(f"registered in {settings_path()}")
    if not parts:
        parts.append("already set up")
    for p in parts:
        print(p)
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
    return 0 if _already_registered((data.get("hooks") or {}).get("PreToolUse") or [], GUARD_MARKER) else 1


def _pipe(payload: dict) -> "tuple[int, str]":
    proc = subprocess.run(
        [sys.executable, str(hook_path())],
        input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8",
    )
    return proc.returncode, (proc.stdout + proc.stderr)


def test_blocking() -> int:
    """Behavioural: forbidden probes must be blocked; a harmless one must pass."""
    if not hook_path().exists():
        print("hook not installed -- run --install first")
        return 1

    cases: list[tuple[str, dict, bool]] = [
        ("Read .env",   {"tool_name": "Read", "tool_input": {"file_path": "/some/path/.env"}}, True),
        ("cat .env",    {"tool_name": "Bash", "tool_input": {"command": "cat .env && echo hi"}}, True),
        ("SSH key read",{"tool_name": "Read", "tool_input": {"file_path": "~/.ssh/id_rsa"}}, True),
        ("harmless ls", {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}, False),
        # regression: whole-word matching must not false-positive on a bare
        # identifier that merely contains ".env" as a substring
        ("grep process.env", {"tool_name": "Bash", "tool_input": {"command": 'grep "process.env" file.ts'}}, False),
        # explicit bypass prefix must still let a real credential read through
        ("explicit bypass",  {"tool_name": "Bash", "tool_input": {"command": "CLAUDE_CRED_GUARD=off cat .env"}}, False),
    ]
    failed: list[str] = []
    for label, payload, should_block in cases:
        rc, out = _pipe(payload)
        blocked = rc != 0 and "BLOCKED" in out
        ok = blocked if should_block else not blocked
        print(f"  {'OK ' if ok else 'FAIL '}{label}: rc={rc}"
              f"{' (' + out.strip().splitlines()[0] + ')' if out.strip() else ''}")
        if not ok:
            failed.append(label)
    if failed:
        print(f"guard misbehaved on: {', '.join(failed)}")
        return 1
    print("guard actually blocks forbidden actions and allows harmless ones")
    return 0


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--install"
    if mode == "--install":
        return install()
    if mode == "--check-hook-file":
        return check_hook_file()
    if mode == "--check-registered":
        return check_registered()
    if mode == "--test-blocking":
        return test_blocking()
    print(f"unknown mode {mode!r}")
    return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main(sys.argv))
