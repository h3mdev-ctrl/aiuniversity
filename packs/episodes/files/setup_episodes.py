#!/usr/bin/env python
"""setup_episodes.py -- install, check and PROVE the episodes recall hook.

    python setup_episodes.py                # install (idempotent)
    python setup_episodes.py --init-store   # create <CLAUDE_HOME>/state/episodes.jsonl
    python setup_episodes.py --check-store  # store exists and every line parses
    python setup_episodes.py --check        # scripts installed + hook registered
    python setup_episodes.py --probe        # behavioural: the recall BRANCH actually runs

Install copies episodes.py to <CLAUDE_HOME>/episodes.py and recall_episodes_hook.py
to <CLAUDE_HOME>/hooks/, then merges ONE UserPromptSubmit entry into
<CLAUDE_HOME>/settings.json. It never removes or rewrites anyone else's hooks, and a
second run changes nothing.

--probe is the check that matters. It logs a canary episode carrying a unique
identifier into a TEMPORARY store (EPISODES_STORE override -- your real store is not
touched), pipes a prompt naming that identifier through the INSTALLED hook with
EPISODES_TRACE=1, and requires BOTH the canary in stdout AND the branch trace on
stderr. Then a negative control: a prompt that shares plenty of ordinary words with
the canary but not its identifier must inject nothing. A check that only asks "did
the hook exit 0 / print something" passes over a hook whose search branch is dead.

CLAUDE_HOME defaults to ~/.claude. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import uuid

HERE = pathlib.Path(__file__).resolve().parent
HOOK_NAME = "recall_episodes_hook.py"
LIB_NAME = "episodes.py"


def home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))


def hook_dst() -> pathlib.Path:
    return home() / "hooks" / HOOK_NAME


def lib_dst() -> pathlib.Path:
    return home() / LIB_NAME


def store() -> pathlib.Path:
    override = os.environ.get("EPISODES_STORE")
    return pathlib.Path(override) if override else home() / "state" / "episodes.jsonl"


def settings_path() -> pathlib.Path:
    return home() / "settings.json"


def hook_command() -> str:
    return f'"{sys.executable}" "{hook_dst().as_posix()}"'


# --- settings ---------------------------------------------------------------


def read_settings() -> dict:
    p = settings_path()
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    data = json.loads(text)  # invalid JSON -> raise: never overwrite a file we can't parse
    if not isinstance(data, dict):
        raise ValueError(f"{p} is not a JSON object")
    return data


def registered_commands(data: dict) -> list[str]:
    out = []
    for entry in ((data.get("hooks") or {}).get("UserPromptSubmit") or []):
        for h in (entry.get("hooks") or []) if isinstance(entry, dict) else []:
            if isinstance(h, dict) and HOOK_NAME in str(h.get("command", "")):
                out.append(str(h.get("command")))
    return out


def register() -> bool:
    """Returns True if settings.json was changed."""
    data = read_settings()
    if registered_commands(data):
        return False
    hooks = data.setdefault("hooks", {})
    ups = hooks.setdefault("UserPromptSubmit", [])
    ups.append({"hooks": [{"type": "command", "command": hook_command(), "timeout": 10}]})
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return True


# --- modes ------------------------------------------------------------------


def init_store() -> int:
    s = store()
    s.parent.mkdir(parents=True, exist_ok=True)
    if not s.exists():
        s.write_text("", encoding="utf-8")
    print(f"store ready: {s}")
    return 0


def check_store() -> int:
    s = store()
    if not s.exists():
        print(f"FAIL: no episode store at {s} -- run: python setup_episodes.py --init-store")
        return 1
    lines = [ln for ln in s.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    bad = 0
    for ln in lines:
        try:
            if not isinstance(json.loads(ln), dict):
                bad += 1
        except Exception:
            bad += 1
    if bad:
        print(f"FAIL: {bad} of {len(lines)} line(s) in {s} are not JSON objects")
        return 1
    print(f"store OK: {s} ({len(lines)} of {len(lines)} lines parse as episodes)")
    return 0


def install() -> int:
    (home() / "hooks").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE / HOOK_NAME, hook_dst())
    shutil.copyfile(HERE / LIB_NAME, lib_dst())
    init_store()
    try:
        changed = register()
    except Exception as exc:
        print(f"FAIL: could not read {settings_path()} ({type(exc).__name__}: {exc}) -- "
              "fix the JSON by hand; refusing to overwrite it")
        return 1
    print(f"installed {hook_dst()} + {lib_dst()}; settings.json "
          + ("updated (1 UserPromptSubmit entry added)" if changed else "already registered, unchanged"))
    return 0


def check() -> int:
    problems = []
    for p in (hook_dst(), lib_dst()):
        if not p.is_file():
            problems.append(f"missing {p}")
    try:
        cmds = registered_commands(read_settings())
    except Exception as exc:
        cmds = []
        problems.append(f"settings.json unreadable ({type(exc).__name__})")
    if not cmds:
        problems.append("no UserPromptSubmit entry runs " + HOOK_NAME)
    elif len(cmds) > 1:
        problems.append(f"{len(cmds)} duplicate UserPromptSubmit entries for {HOOK_NAME}")
    if problems:
        print("FAIL: " + "; ".join(problems) + " -- run: python setup_episodes.py")
        return 1
    print(f"OK: {HOOK_NAME} + {LIB_NAME} installed, 1 UserPromptSubmit entry registered")
    return 0


def _run_hook(prompt: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(hook_dst())],
        input=json.dumps({"prompt": prompt, "cwd": str(pathlib.Path.cwd())}),
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=30,
    )


def probe() -> int:
    if not hook_dst().is_file() or not lib_dst().is_file():
        print(f"PROBE FAIL: hook not installed at {hook_dst()} -- run: python setup_episodes.py")
        return 1
    ident = f"probe_canary_{uuid.uuid4().hex[:8]}.py"
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ, EPISODES_STORE=str(pathlib.Path(td) / "episodes.jsonl"),
                   EPISODES_TRACE="1", PYTHONIOENCODING="utf-8")
        logged = subprocess.run(
            [sys.executable, str(lib_dst()), "--log",
             "--task", f"{ident} nightly build keeps failing overnight",
             "--tried", "reran the nightly build twice",
             "--why", "canary episode written by setup_episodes.py --probe",
             "--fix", "none -- this is a probe", "--tags", "probe"],
            capture_output=True, text=True, encoding="utf-8", env=env, timeout=30)
        if logged.returncode != 0:
            print(f"PROBE FAIL: could not log the canary episode: {logged.stdout.strip()}")
            return 1

        pos = _run_hook(f"why does {ident} break the nightly build?", env)
        neg = _run_hook("the nightly build keeps failing overnight again", env)

    failures = []
    if pos.returncode != 0 or neg.returncode != 0:
        failures.append(f"hook exited non-zero ({pos.returncode}/{neg.returncode})")
    if ident not in pos.stdout:
        failures.append("canary NOT recalled on its identifier")
    if "trace: episodes.search ran, 1 hits" not in pos.stderr:
        failures.append("no branch trace 'episodes.search ran, 1 hits' on the positive prompt "
                        "(the search branch did not run)")
    if "trace: episodes.search ran, 0 hits" not in neg.stderr:
        failures.append("no branch trace on the control prompt")
    if neg.stdout.strip():
        failures.append("control prompt (word overlap, no identifier) injected context")
    if "EXCEPTION" in pos.stderr or "EXCEPTION" in neg.stderr:
        failures.append("hook swallowed an exception: "
                        + (pos.stderr + neg.stderr).split("EXCEPTION", 1)[1].splitlines()[0])
    if failures:
        print("PROBE FAIL: " + "; ".join(failures))
        if pos.stderr.strip():
            print("--- hook trace (positive) ---\n" + pos.stderr.strip())
        return 1
    print("PROBE PASS: canary ep recalled on identifier, silent on control, branch trace present")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true")
    g.add_argument("--check-store", action="store_true")
    g.add_argument("--init-store", action="store_true")
    g.add_argument("--probe", action="store_true")
    a = ap.parse_args(argv)
    if a.check:
        return check()
    if a.check_store:
        return check_store()
    if a.init_store:
        return init_store()
    if a.probe:
        return probe()
    return install()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main(sys.argv[1:]))
