#!/usr/bin/env python3
"""
phantom_claim_lint.py -- a deterministic, model-free linter for the no-phantom-done
guardrail. It scans a block of text (a proposed final message) for COMPLETION
CLAIMS that carry no evidence, and flags them so the model self-checks before
emitting them.

It lints two high-risk claim categories -- the ones that are dangerous when
phantom (they assert something happened OUTSIDE the message):

  A. external side-effects  -- committed / pushed / deployed / merged / published /
     sent / posted / logged / saved / filed. Claiming one that didn't run is the
     classic "phantom done" failure.
  B. verification results    -- "all tests pass", "it works", "build succeeds".
     A weak model asserting its own success without running the check.

It deliberately does NOT flag plain descriptions of edits made this turn ("I added
a helper") -- those are low-risk and flagging them would make the linter a wall.

A finding is CLEARED when the text also carries an EVIDENCE token anywhere -- a
commit SHA, an exit/return code, "ran:", "verified", "0 failed", a test tally, a
PR/issue link. The rule this enforces: *if you claim it, show the receipt.*

This is a lint, not a proof. It cannot know whether a tool truly ran; it forces
the model to pair every completion claim with the evidence that it did. That is
exactly the deterministic-verification-beats-self-judgment principle applied to
the model's OWN report of its work.

CLI:
    echo "Done -- pushed the fix." | python phantom_claim_lint.py
    python phantom_claim_lint.py --text "All tests pass."
Exit 0 = clean (or evidenced); exit 1 = unevidenced completion claim(s) found.
Add --quiet to suppress the report (exit code only).
"""
import re
import sys

# --- Category A: external side-effect claims (past / present-perfect / state) ---
# Past-tense or "have <verb>" forms only, so future tense ("I'll push") never trips.
_SIDE_EFFECT = re.compile(
    r"""\b(
        committed | pushed | deployed | merged | published | released |
        sent | posted | emailed | messaged |
        logged | saved | filed | persisted | uploaded |
        installed | provisioned
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)
# "Done" as a standalone completion claim: line-leading, or "Done -- ...", "Done:".
_DONE = re.compile(r"(^|[\n])\s*done\b|\bdone\s*[\-–—:]", re.IGNORECASE)
# "fixed / resolved the bug", "fixed it"
_FIXED = re.compile(r"\b(fixed|resolved)\s+(the|this|that|it|the\s+\w+)\b", re.IGNORECASE)

# --- Category B: verification-result claims ---
_VERIFY_CLAIM = re.compile(
    r"""(
        \ball\s+(the\s+)?(tests|checks|builds)\s+(pass(ed)?|are\s+green|green)\b |
        \btests?\s+(are\s+)?green\b |
        \bbuild\s+(succeeds|succeeded|passes|passed|is\s+green)\b |
        \bit\s+works\b | \bworks\s+now\b | \bverified\s+working\b
    )""",
    re.IGNORECASE | re.VERBOSE,
)

# --- Evidence tokens: any one of these ANYWHERE clears the whole message ---
_EVIDENCE = [
    re.compile(r"\bexit\s+code\b", re.IGNORECASE),
    re.compile(r"\breturn\s+code\b", re.IGNORECASE),
    re.compile(r"\brc\s*=\s*\d", re.IGNORECASE),
    re.compile(r"\bran\b\s*[:`]", re.IGNORECASE),
    re.compile(r"\bran\s+`", re.IGNORECASE),
    re.compile(r"\bverified\b", re.IGNORECASE),
    re.compile(r"\bconfirmed\b", re.IGNORECASE),
    re.compile(r"\boutput\s*[:\-]", re.IGNORECASE),
    re.compile(r"\b\d+\s+passed\b", re.IGNORECASE),
    re.compile(r"\b0\s+failed\b", re.IGNORECASE),
    re.compile(r"\b[0-9a-f]{7,40}\b"),          # commit SHA
    re.compile(r"#\d+\b"),                        # PR / issue reference
    re.compile(r"https?://\S+"),                 # a link to the receipt
]

_CATEGORIES = [
    ("side-effect", _SIDE_EFFECT),
    ("done", _DONE),
    ("fixed", _FIXED),
    ("verification", _VERIFY_CLAIM),
]


def has_evidence(text: str) -> bool:
    return any(rx.search(text) for rx in _EVIDENCE)


def find_claims(text: str) -> "list[tuple[str, str]]":
    """Return [(category, matched_phrase), ...] for every completion claim found."""
    found = []
    for label, rx in _CATEGORIES:
        for m in rx.finditer(text):
            phrase = (m.group(0) or "").strip()
            if phrase:
                found.append((label, phrase))
    return found


def lint(text: str) -> "list[tuple[str, str]]":
    """Findings that survive the evidence check. Empty list == clean."""
    if has_evidence(text):
        return []
    return find_claims(text)


def main(argv: "list[str]") -> int:
    quiet = "--quiet" in argv
    argv = [a for a in argv if a != "--quiet"]
    if "--text" in argv:
        i = argv.index("--text")
        text = argv[i + 1] if i + 1 < len(argv) else ""
    else:
        text = sys.stdin.read()

    findings = lint(text)
    if not findings:
        if not quiet:
            print("clean -- no unevidenced completion claims")
        return 0
    if not quiet:
        print("PHANTOM-CLAIM WARNING -- completion claim(s) with no evidence in the message:")
        for label, phrase in findings:
            print(f"  [{label}] {phrase!r}")
        print("Pair each claim with a receipt (exit code, test tally, commit SHA, "
              "a ran command) -- or soften it to what you actually did.")
    return 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main(sys.argv[1:]))
