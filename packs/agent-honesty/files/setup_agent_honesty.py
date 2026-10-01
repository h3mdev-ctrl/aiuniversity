#!/usr/bin/env python3
"""
setup_agent_honesty.py -- install the six agent-honesty guardrails as an
always-loaded rules doc, wire a pointer into the constitution, and prove the
deterministic phantom-claim linter fires.

Modes:
    (no arg) / --install   copy agent_honesty.md into <home> + wire CLAUDE.md pointer
    --check-doc            exit 0 if the rules doc is present with all three guardrails
    --check-wired          exit 0 if the CLAUDE.md pointer block is present
    --test-linter          run phantom_claim_lint over known cases, prove verdicts
    --install-stop-hook    OPT-IN: copy the linter + Stop adapter into <home>/hooks/
                           agent_honesty/ and register it on Stop (warn mode)
    --check-stop-hook      exit 0 iff registered once AND it behaves (5 checks)

Home: $CLAUDE_HOME or ~/.claude
"""
import os
import pathlib
import sys

DOC_NAME = "agent_honesty.md"

# The six guardrail headers that MUST be present for the doc to count as installed.
GUARDRAIL_MARKERS = (
    "## 1. no-phantom-done",
    "## 2. research-before-asserting",
    "## 3. judge-to-spec",
    "## 4. no-vague-time-claims",
    "## 5. verify-mechanism-before-acting",
    "## 6. verify-effect-not-acknowledgment",
)

POINTER_START = "<!-- agent-honesty-pointer:start -->"
POINTER_END = "<!-- agent-honesty-pointer:end -->"
POINTER_BLOCK = f"""{POINTER_START}
## Agent honesty (always applies)

Six honesty guardrails live in `~/.claude/{DOC_NAME}` and apply every turn:
**no-phantom-done** (never claim done without a receipt -- the tool call ran this
turn and you show it), **research-before-asserting** (check the source before
stating a load-bearing fact/constraint, don't complete a pattern from memory),
**judge-to-spec** (grade an output against the real spec, not a remembered copy),
**no-vague-time-claims** (check the clock before naming a time of day or date --
don't infer it from message order or conversation feel), **verify-mechanism-before-acting**
(before a live system takes a new/bigger real-world action, check that exact path
has actually run successfully before, don't trust a plausible sourced mechanism
alone), and **verify-effect-not-acknowledgment** (a write returning success is not
proof the effect happened -- confirm with an independent read, and diff the full
payload shape when it doesn't match). Read that file; when a completion claim, a
load-bearing assertion, a pass/fail judgment, a date/time claim, or an automated
real-world action is in play, follow it.
{POINTER_END}
"""


def base_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))


def doc_path() -> pathlib.Path:
    return base_dir() / DOC_NAME


def claude_md() -> pathlib.Path:
    return base_dir() / "CLAUDE.md"


def _src_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent


def _source_doc() -> str:
    return (_src_dir() / DOC_NAME).read_text(encoding="utf-8")


# --- install ---------------------------------------------------------------


def _install_doc() -> bool:
    """Write/refresh the rules doc. Returns True if it changed."""
    dst = doc_path()
    dst.parent.mkdir(parents=True, exist_ok=True)
    new = _source_doc()
    if dst.exists() and dst.read_text(encoding="utf-8") == new:
        return False
    dst.write_text(new, encoding="utf-8")
    return True


def _wire_pointer() -> bool:
    """Insert/refresh the pointer block in CLAUDE.md (idempotent). Returns True if changed."""
    p = claude_md()
    p.parent.mkdir(parents=True, exist_ok=True)
    text = p.read_text(encoding="utf-8") if p.exists() else "# Claude -- your constitution\n"
    if POINTER_START in text and POINTER_END in text:
        pre = text[: text.index(POINTER_START)]
        post = text[text.index(POINTER_END) + len(POINTER_END):]
        updated = pre.rstrip() + "\n\n" + POINTER_BLOCK.rstrip() + "\n" + post
        if updated == text:
            return False
        p.write_text(updated, encoding="utf-8")
        return True
    p.write_text(text.rstrip() + "\n\n" + POINTER_BLOCK, encoding="utf-8")
    return True


def install() -> int:
    doc_changed = _install_doc()
    ptr_changed = _wire_pointer()
    if doc_changed:
        print(f"installed {DOC_NAME} into {doc_path()}")
    if ptr_changed:
        print(f"wired agent-honesty pointer into {claude_md()}")
    if not doc_changed and not ptr_changed:
        print("already set up")
    return 0


# --- checks ----------------------------------------------------------------


def check_doc() -> int:
    p = doc_path()
    if not p.exists():
        print(f"missing: {p}")
        return 1
    text = p.read_text(encoding="utf-8")
    missing = [m for m in GUARDRAIL_MARKERS if m not in text]
    if missing:
        print(f"doc present but missing guardrails: {', '.join(missing)}")
        return 1
    return 0


def check_wired() -> int:
    p = claude_md()
    if not p.exists() or POINTER_START not in p.read_text(encoding="utf-8"):
        print(f"agent-honesty pointer not found in {p}")
        return 1
    return 0


# --- behavioural: the linter fires -----------------------------------------


def test_linter() -> int:
    sys.path.insert(0, str(_src_dir()))
    import phantom_claim_lint as lint  # noqa: E402

    # (label, text, should_flag)
    cases = [
        ("phantom push",        "Done -- pushed the fix to main.",                       True),
        ("phantom log",         "Logged the run into memory.",                           True),
        ("phantom tests",       "All tests pass.",                                       True),
        ("phantom saved",       "Saved your profile to the memory folder.",              True),
        ("evidenced push",      "Pushed the fix (commit a1b2c3d, CI green).",            False),
        ("evidenced tests",     "All tests pass -- ran pytest: 219 passed, 0 failed.",   False),
        ("future tense",        "I'll push once you confirm.",                           False),
        ("neutral prose",       "Here's the plan for the refactor and the tradeoffs.",   False),
    ]

    failed = []
    for label, text, should_flag in cases:
        flagged = bool(lint.lint(text))
        ok = flagged == should_flag
        print(f"  {'OK ' if ok else 'FAIL'} {label}: flagged={flagged} (want {should_flag})")
        if not ok:
            failed.append(label)

    if failed:
        print(f"linter misjudged: {', '.join(failed)}")
        return 1
    print("phantom-claim linter flags unevidenced claims and clears evidenced/neutral ones")
    return 0


# --- opt-in: the Stop-hook adapter -------------------------------------------
# Not part of the default install and not a pack step: enforcement is opt-in
# (README "Enforcement"). These modes exist so opting in is one safe command.

STOP_FILES = ("phantom_claim_lint.py", "phantom_claim_stop.py")
STOP_TAG = "phantom_claim_stop.py"


def _stop_dir() -> pathlib.Path:
    return base_dir() / "hooks" / "agent_honesty"


def _settings_path() -> pathlib.Path:
    return base_dir() / "settings.json"


def _read_settings() -> dict:
    import json
    p = _settings_path()
    if not p.exists() or not p.read_text(encoding="utf-8").strip():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))  # unparseable -> raise, never clobber
    if not isinstance(data, dict):
        raise ValueError(f"{p} is not a JSON object")
    return data


def _stop_registered(data: dict) -> int:
    n = 0
    for entry in ((data.get("hooks") or {}).get("Stop") or []):
        for h in (entry.get("hooks") or []) if isinstance(entry, dict) else []:
            if isinstance(h, dict) and STOP_TAG in str(h.get("command", "")):
                n += 1
    return n


def install_stop_hook() -> int:
    import json
    import shutil
    try:
        data = _read_settings()
    except (ValueError, json.JSONDecodeError) as e:
        print(f"refusing: cannot parse {_settings_path()} ({e}); fix it first")
        return 1
    d = _stop_dir()
    d.mkdir(parents=True, exist_ok=True)
    for name in STOP_FILES:
        shutil.copyfile(_src_dir() / name, d / name)
    if _stop_registered(data):
        print(f"stop hook already registered; files refreshed in {d}")
        return 0
    cmd = f'"{sys.executable}" "{(d / "phantom_claim_stop.py").as_posix()}"'
    data.setdefault("hooks", {}).setdefault("Stop", []).append(
        {"hooks": [{"type": "command", "command": cmd, "timeout": 10}]})
    p = _settings_path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    print(f"registered phantom-claim Stop hook (warn mode) -> {d}")
    print("  block mode: set PHANTOM_STOP_MODE=block   off: PHANTOM_STOP_DISABLE=1")
    return 0


def check_stop_hook() -> int:
    """Registered exactly once, files present, AND it behaves: flags a planted
    phantom claim (warn -> systemMessage, block -> exit 2), stays silent on an
    evidenced one, and never re-fires when stop_hook_active is set."""
    import json
    import subprocess
    import tempfile
    try:
        n = _stop_registered(_read_settings())
    except Exception as e:
        print(f"cannot read settings: {e}")
        return 1
    adapter = _stop_dir() / "phantom_claim_stop.py"
    if n != 1 or not adapter.exists() or not (_stop_dir() / "phantom_claim_lint.py").exists():
        print(f"stop hook not installed (registered {n}x, adapter present={adapter.exists()})")
        return 1

    def run(reply: str, mode: str, active: bool = False):
        with tempfile.TemporaryDirectory() as td:
            t = pathlib.Path(td) / "t.jsonl"
            t.write_text("\n".join(json.dumps(o) for o in (
                {"type": "user", "message": {"role": "user", "content": "do it"}},
                {"type": "assistant", "message": {"content": [{"type": "text", "text": reply}]}},
            )) + "\n", encoding="utf-8")
            env = dict(os.environ, PHANTOM_STOP_MODE=mode, CLAUDE_HOME=td)
            env.pop("PHANTOM_STOP_DISABLE", None)
            return subprocess.run([sys.executable, str(adapter)], input=json.dumps(
                {"transcript_path": str(t), "stop_hook_active": active}),
                capture_output=True, text=True, encoding="utf-8", env=env, timeout=30)

    phantom, evidenced = "Done -- pushed the fix to main.", "Pushed the fix (commit a1b2c3d, CI green)."
    checks = [
        ("block flags a phantom claim",    run(phantom, "block").returncode == 2),
        ("warn never blocks",              run(phantom, "warn").returncode == 0),
        ("warn tells the user",            "phantom-claim (warn)" in run(phantom, "warn").stdout),
        ("evidenced claim is silent",      run(evidenced, "block").returncode == 0),
        ("no loop when stop_hook_active",  run(phantom, "block", active=True).returncode == 0),
    ]
    bad = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'OK ' if ok else 'FAIL'} {name}")
    if bad:
        return 1
    print("phantom-claim Stop hook installed once and behaves (5/5 checks)")
    return 0


def main(argv: "list[str]") -> int:
    mode = argv[1] if len(argv) > 1 else "--install"
    if mode == "--install-stop-hook":
        return install_stop_hook()
    if mode == "--check-stop-hook":
        return check_stop_hook()
    if mode == "--install":
        return install()
    if mode == "--check-doc":
        return check_doc()
    if mode == "--check-wired":
        return check_wired()
    if mode == "--test-linter":
        return test_linter()
    print(f"unknown mode {mode!r}")
    return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main(sys.argv))
