#!/usr/bin/env python3
"""
setup_empirical_rigor.py -- install the three empirical-rigor guardrails as an
always-loaded rules doc and wire a pointer into the constitution.

Modes:
    (no arg) / --install   copy empirical_rigor.md into <home> + wire CLAUDE.md pointer
    --check-doc            exit 0 if the rules doc is present with all three guardrails
    --check-wired          exit 0 if the CLAUDE.md pointer block is present

Home: $CLAUDE_HOME or ~/.claude
"""
import os
import pathlib
import sys

DOC_NAME = "empirical_rigor.md"

# The three guardrail headers that MUST be present for the doc to count as installed.
GUARDRAIL_MARKERS = (
    "## 1. distribution-before-statistic",
    "## 2. environment-parity-for-adhoc-runs",
    "## 3. continuity-is-not-uptime",
)

POINTER_START = "<!-- empirical-rigor-pointer:start -->"
POINTER_END = "<!-- empirical-rigor-pointer:end -->"
POINTER_BLOCK = f"""{POINTER_START}
## Empirical rigor (always applies)

Three guardrails live in `~/.claude/{DOC_NAME}` and apply every turn:
**distribution-before-statistic** (look at the real shape of historical data
before picking a mean/average -- a spiky or bimodal distribution needs a max or
percentile instead), **environment-parity-for-adhoc-runs** (a diagnostic
invocation of production code must mirror its real mounts/env/config exactly, not
a trimmed copy -- a shortened environment can silently produce false inputs),
and **continuity-is-not-uptime** (a gap-free dataset is not proof a job has been
running correctly -- check deploy history before citing "N days, zero gaps" as
reliability). Read that file; when sizing a threshold from history, running
anything ad-hoc against production code, or citing data continuity as evidence of
uptime, follow it.
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
        print(f"wired empirical-rigor pointer into {claude_md()}")
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
        print(f"empirical-rigor pointer not found in {p}")
        return 1
    return 0


def main(argv: "list[str]") -> int:
    mode = argv[1] if len(argv) > 1 else "--install"
    if mode == "--install":
        return install()
    if mode == "--check-doc":
        return check_doc()
    if mode == "--check-wired":
        return check_wired()
    print(f"unknown mode {mode!r}")
    return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main(sys.argv))
