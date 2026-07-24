#!/usr/bin/env python3
"""
setup_agent_honesty.py -- install the four agent-honesty guardrails as an
always-loaded rules doc, wire a pointer into the constitution, and prove the
deterministic phantom-claim linter fires.

Modes:
    (no arg) / --install   copy agent_honesty.md into <home> + wire CLAUDE.md pointer
    --check-doc            exit 0 if the rules doc is present with all three guardrails
    --check-wired          exit 0 if the CLAUDE.md pointer block is present
    --test-linter          run phantom_claim_lint over known cases, prove verdicts

Home: $CLAUDE_HOME or ~/.claude
"""
import os
import pathlib
import sys

DOC_NAME = "agent_honesty.md"

# The four guardrail headers that MUST be present for the doc to count as installed.
GUARDRAIL_MARKERS = (
    "## 1. no-phantom-done",
    "## 2. research-before-asserting",
    "## 3. judge-to-spec",
    "## 4. no-vague-time-claims",
)

POINTER_START = "<!-- agent-honesty-pointer:start -->"
POINTER_END = "<!-- agent-honesty-pointer:end -->"
POINTER_BLOCK = f"""{POINTER_START}
## Agent honesty (always applies)

Four honesty guardrails live in `~/.claude/{DOC_NAME}` and apply every turn:
**no-phantom-done** (never claim done without a receipt -- the tool call ran this
turn and you show it), **research-before-asserting** (check the source before
stating a load-bearing fact/constraint, don't complete a pattern from memory),
**judge-to-spec** (grade an output against the real spec, not a remembered copy),
and **no-vague-time-claims** (check the clock before naming a time of day or date --
don't infer it from message order or conversation feel). Read that file; when a
completion claim, a load-bearing assertion, a pass/fail judgment, or a date/time
claim is in play, follow it.
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


def main(argv: "list[str]") -> int:
    mode = argv[1] if len(argv) > 1 else "--install"
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
