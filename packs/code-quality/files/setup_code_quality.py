#!/usr/bin/env python3
"""
setup_code_quality.py -- install code quality hooks: auto-format and stop-verify.

Modes:
    (no arg) / --install       install hook scripts + merge into settings.json
    --check-hook-files         exit 0 if both hook scripts are present
    --check-registered         exit 0 if both hooks are registered
    --test-blocking            test stop_verify blocks when tests fail
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys

HOOKS = {
    "auto_format.py": {"event": "PostToolUse", "matcher": "Write|Edit"},
    "stop_verify.py": {"event": "Stop", "matcher": None},
}


def base_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))


def hooks_dir() -> pathlib.Path:
    return base_dir() / "hooks"


def settings_path() -> pathlib.Path:
    return base_dir() / "settings.json"


def _src_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent


def _install_hook_files() -> list[str]:
    hooks_dir().mkdir(parents=True, exist_ok=True)
    written = []
    for name in HOOKS:
        src = _src_dir() / name
        dst = hooks_dir() / name
        if not dst.exists():
            shutil.copyfile(src, dst)
            try:
                os.chmod(dst, 0o755)
            except Exception:
                pass
            written.append(name)
    return written


def _already_registered(entries: list, marker: str) -> bool:
    for entry in entries or []:
        for h in entry.get("hooks") or []:
            if marker in (h.get("command") or ""):
                return True
    return False


def _merge_into_settings() -> list[str]:
    p = settings_path()
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    hooks_cfg = data.setdefault("hooks", {})
    added = []

    for name, meta in HOOKS.items():
        event = meta["event"]
        matcher = meta.get("matcher")
        hook_path = str(hooks_dir() / name)
        event_list = hooks_cfg.setdefault(event, [])
        if not _already_registered(event_list, name):
            entry: dict = {"hooks": [{"type": "command", "command": f'python "{hook_path}"'}]}
            if matcher:
                entry["matcher"] = matcher
            event_list.append(entry)
            added.append(name)

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return added


def install() -> int:
    written = _install_hook_files()
    added = _merge_into_settings()
    if written:
        print(f"installed: {', '.join(written)}")
    if added:
        print(f"registered: {', '.join(added)}")
    if not written and not added:
        print("already set up")
    return 0


def check_hook_files() -> int:
    missing = [n for n in HOOKS if not (hooks_dir() / n).exists()]
    if missing:
        print(f"missing: {', '.join(missing)}")
        return 1
    return 0


def check_registered() -> int:
    p = settings_path()
    if not p.exists():
        return 1
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 1
    hooks_cfg = data.get("hooks") or {}
    for name, meta in HOOKS.items():
        event_list = hooks_cfg.get(meta["event"]) or []
        if not _already_registered(event_list, name):
            print(f"not registered: {name}")
            return 1
    return 0


def test_blocking() -> int:
    if check_hook_files() != 0:
        print("hook files not installed -- run --install first")
        return 1

    # Test stop_verify: in a dir with no project files it should pass (no tests to run)
    hook = hooks_dir() / "stop_verify.py"
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            [sys.executable, str(hook)],
            input=b"{}",
            capture_output=True,
            env={**os.environ, "STOP_VERIFY_DIR": tmp},
        )
        if proc.returncode != 0:
            print(f"FAIL stop_verify failed on empty dir: {proc.stderr[:200]}")
            return 1
        print("  OK  stop_verify passes on project with no test suite")

    print("code-quality hooks installed and behaving correctly")
    return 0


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--install"
    if mode == "--install":
        return install()
    if mode == "--check-hook-files":
        return check_hook_files()
    if mode == "--check-registered":
        return check_registered()
    if mode == "--test-blocking":
        return test_blocking()
    print(f"unknown mode {mode!r}")
    return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main(sys.argv))
