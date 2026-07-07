#!/usr/bin/env python
"""setup_recon_build_guard.py -- install the recon-before-build PreToolUse hook + prove it.

Companion (opt-in) guard: bounces the FIRST Write of a new source file into an
already-populated repo, once per (session, repo), so Claude reads the existing code
before building a parallel version of it. Behavioural check proves it (a) bounces a
new .py landing in a dir that already has .py files, (b) does NOT bounce the second
such Write in the same session (nudge-once), (c) lets an EXISTING file, a doc file,
and a sparse/fresh dir through.

Modes:
    (no arg) / --install     install the hook + register it as a PreToolUse(Write) hook
    --check-hook-file        exit 0 if the hook script is installed
    --check-registered       exit 0 if settings.json registers it (PreToolUse/Write)
    --test-blocking          behavioural proof (see above)

Home: $CLAUDE_HOME or ~/.claude ; hook at <home>/hooks/recon_before_build_guard.py.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HOOK_NAME = "recon_before_build_guard.py"
GUARD_MARKER = "recon_before_build_guard.py"


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
    # Always refresh (the guard logic may have improved) but report only real installs.
    existed = dst.exists()
    shutil.copyfile(src, dst)
    try:
        os.chmod(dst, 0o755)
    except Exception:
        pass
    return not existed


def _registered(pre_entries: list) -> bool:
    for entry in pre_entries or []:
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
    pre.append({"matcher": "Write",
                "hooks": [{"type": "command", "command": f'python "{hook_path()}"'}]})
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return True


def install() -> int:
    parts = []
    if _install_hook_file():
        parts.append(f"installed hook at {hook_path()}")
    if _merge_into_settings():
        parts.append(f"registered (PreToolUse/Write) in {settings_path()}")
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


def _pipe(payload: dict) -> int:
    return subprocess.run(
        [sys.executable, str(hook_path())],
        input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8",
    ).returncode


def test_blocking() -> int:
    if not hook_path().exists():
        print("hook not installed -- run --install first")
        return 1
    failed = []
    with tempfile.TemporaryDirectory() as td:
        repo = pathlib.Path(td)
        (repo / ".git").mkdir()                          # make it a repo root
        (repo / "extract.py").write_text("# a\n")        # already-populated with .py
        (repo / "reconcile.py").write_text("# b\n")
        sparse = repo / "fresh"
        sparse.mkdir()
        sess = "test-session-1"

        def payload(fp):
            return {"session_id": sess, "tool_name": "Write",
                    "tool_input": {"file_path": str(fp), "content": "x"}}

        cases = [
            ("new .py in populated repo (1st)", payload(repo / "crosscheck3.py"), True),
            ("same repo, 2nd Write (nudge-once)", payload(repo / "another.py"), False),
            ("existing file overwrite",           payload(repo / "extract.py"), False),
            ("doc file (.md)",                     payload(repo / "NOTES.md"), False),
            ("new .py in a fresh/sparse dir",      payload(sparse / "brand_new.py"), False),
        ]
        for label, pl, should_block in cases:
            rc = _pipe(pl)
            blocked = rc != 0
            ok = blocked if should_block else not blocked
            print(f"  {'OK ' if ok else 'FAIL '}{label}: rc={rc}")
            if not ok:
                failed.append(label)
    if failed:
        print(f"guard misbehaved on: {', '.join(failed)}")
        return 1
    print("bounces the first new-module Write in a populated repo, then gets out of the way")
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
