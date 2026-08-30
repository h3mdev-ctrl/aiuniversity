#!/usr/bin/env python
"""setup_recon_build_guard.py -- install the recon-before-build PreToolUse hook + prove it.

Companion (opt-in) guard: bounces the FIRST Write of a new source file into an
already-populated repo, once per (session, repo), so Claude reads the existing code
before building a parallel version of it. Behavioural check proves it (a) bounces a
new .py landing in a dir that already has .py files, (b) does NOT bounce the second
such Write in the same session (nudge-once), (c) lets an EXISTING file, a doc file,
a sparse/fresh dir, a scratch/throwaway dir, and a session that has ALREADY read
something in the target directory through.

`--install` always refreshes the hook file, so it is also the upgrade path; the
behavioural check refuses to run (and says so) against an installed copy older
than this pack, rather than reporting a misleading misbehaviour.

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


def _pipe(payload: dict, selftest: bool = True) -> int:
    """Run the installed hook on one payload.

    `selftest` sets CLAUDE_RECON_SELFTEST, which disables ONLY the OS-temp-tree
    exclusion. The fixture below has to build a fake populated repo somewhere, and
    `tempfile` puts it inside the very tree the guard learned to ignore -- so
    without the flag every case here asserts silence and passes against a guard
    that does nothing at all. The flag can only make the guard fire MORE, never
    less, which is why it is safe to ship. The `temp tree is excluded` case below
    runs with it OFF, so the exclusion it disables is itself proven.
    """
    env = dict(os.environ)
    if selftest:
        env["CLAUDE_RECON_SELFTEST"] = "1"
    else:
        env.pop("CLAUDE_RECON_SELFTEST", None)
    return subprocess.run(
        [sys.executable, str(hook_path())],
        input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8",
        env=env,
    ).returncode


def _transcript(path: pathlib.Path, tool: str, tool_input: dict) -> str:
    """A one-line JSONL transcript in the shape the guard reads, so the
    recon-evidence path is exercised on real input rather than mocked away."""
    path.write_text(json.dumps({
        "message": {"content": [{"type": "tool_use", "name": tool, "input": tool_input}]}
    }) + "\n", encoding="utf-8")
    return str(path)


def test_blocking() -> int:
    if not hook_path().exists():
        print("hook not installed -- run --install first")
        return 1
    # Version drift is its own diagnosis. An installed copy older than this pack
    # cannot honour CLAUDE_RECON_SELFTEST, so every case below would land in the
    # excluded temp tree and the run would report "guard misbehaved on: new .py in
    # populated repo" -- true, and completely misleading about the cause. Say what
    # is actually wrong instead. (_install_hook_file always refreshes, so plain
    # --install is the upgrade.)
    try:
        installed = hook_path().read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"cannot read the installed hook: {exc}")
        return 1
    if "CLAUDE_RECON_SELFTEST" not in installed:
        print(f"  the installed hook at {hook_path()}")
        print(f"  predates the selftest flag, so this check cannot exercise it.")
        # LAST line, deliberately: a caller that folds this in (guard_regression's
        # selftest delegation) surfaces only the tail, so the tail has to carry both
        # the diagnosis and the fix or the failure reads as "the guard is broken".
        print(f"NOT CHECKED: installed hook is an OLDER revision than this pack ships "
              f"-- upgrade with: python {pathlib.Path(__file__).name} --install")
        return 1
    failed = []
    with tempfile.TemporaryDirectory() as td:
        repo = pathlib.Path(td)
        (repo / ".git").mkdir()                          # make it a repo root
        (repo / "extract.py").write_text("# a\n")        # already-populated with .py
        (repo / "reconcile.py").write_text("# b\n")
        sparse = repo / "fresh"
        sparse.mkdir()
        scratch = repo / "scratchpad"
        scratch.mkdir()
        (scratch / "one.py").write_text("# a\n")
        (scratch / "two.py").write_text("# b\n")

        def payload(fp, sess="test-session-1", transcript=""):
            return {"session_id": sess, "tool_name": "Write",
                    "transcript_path": transcript,
                    "tool_input": {"file_path": str(fp), "content": "x"}}

        # A session that already READ a file in the target directory has done the
        # recon; nudging it would be noise. Fresh session id so nudge-once cannot
        # be what makes this pass.
        read_dir = _transcript(repo / "t_dir.jsonl", "Read", {"file_path": str(repo)})
        read_sib = _transcript(repo / "t_sib.jsonl", "Grep",
                               {"pattern": "x", "path": str(repo / "extract.py")})

        cases = [
            ("new .py in populated repo (1st)", payload(repo / "crosscheck3.py"), True, True),
            ("same repo, 2nd Write (nudge-once)", payload(repo / "another.py"), False, True),
            ("existing file overwrite",           payload(repo / "extract.py"), False, True),
            ("doc file (.md)",                    payload(repo / "NOTES.md"), False, True),
            ("new .py in a fresh/sparse dir",     payload(sparse / "brand_new.py"), False, True),

            # scratch/throwaway areas: "read the neighbours first" is meaningless
            # advice about a throwaway script, and 38% of measured fires were here.
            ("new .py in a scratchpad/ dir",
             payload(scratch / "probe.py", sess="s-scratch"), False, True),

            # recon already happened -> the guard has nothing to add.
            ("session already READ the target dir",
             payload(repo / "after_dir_read.py", sess="s-dir", transcript=read_dir),
             False, True),
            ("session already GREPped a sibling",
             payload(repo / "after_sib_read.py", sess="s-sib", transcript=read_sib),
             False, True),

            # The exclusion this selftest's own flag disables, proven WITH THE FLAG
            # OFF. Without this case the flag could quietly become a bypass.
            ("OS temp tree is excluded (flag off)",
             payload(repo / "in_temp.py", sess="s-temp"), False, False),
        ]
        for label, pl, should_block, selftest in cases:
            rc = _pipe(pl, selftest=selftest)
            # PreToolUse defines 0=allow and 2=block; anything else is a
            # non-blocking ERROR. Testing `rc != 0` would score a CRASHED guard as
            # a successful block, which is the one outcome this must never call a
            # pass -- a guard that dies permits, silently.
            ok = (rc == 2) if should_block else (rc == 0)
            print(f"  {'OK ' if ok else 'FAIL '}{label}: rc={rc}")
            if not ok:
                failed.append(label)
    if failed:
        print(f"guard misbehaved on: {', '.join(failed)}")
        return 1
    print("bounces the first un-reconnoitred new-module Write in a populated repo, "
          "and stays out of the way everywhere else")
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
