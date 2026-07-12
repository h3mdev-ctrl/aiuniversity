#!/usr/bin/env python3
"""
auto_format.py -- PostToolUse hook that runs the project formatter after every
Write or Edit call.

Detects which formatter to use from file extension + project config:
  .py        -> ruff format (preferred), then black, then autopep8
  .ts/.tsx   -> prettier (npx/bunx)
  .js/.jsx   -> prettier
  .json      -> prettier
  .yaml/.yml -> prettier
  .md        -> prettier (--prose-wrap preserve so markdown isn't reflowed)
  .go        -> gofmt
  .rs        -> rustfmt

Silently skips if no formatter is found for the extension. Never fails loudly --
a formatter error should not block the write workflow.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys


def _run(cmd: list[str], cwd: str | None = None) -> bool:
    try:
        r = subprocess.run(cmd, capture_output=True, cwd=cwd, timeout=30)
        return r.returncode == 0
    except Exception:
        return False


def _npx_or_bunx() -> str | None:
    if shutil.which("bunx"):
        return "bunx"
    if shutil.which("npx"):
        return "npx"
    return None


def _format(file_path: str) -> None:
    p = pathlib.Path(file_path)
    if not p.exists():
        return
    ext = p.suffix.lower()
    cwd = str(p.parent)

    if ext == ".py":
        if shutil.which("ruff"):
            _run(["ruff", "format", str(p)])
        elif shutil.which("black"):
            _run(["black", "--quiet", str(p)])
        elif shutil.which("autopep8"):
            _run(["autopep8", "--in-place", str(p)])

    elif ext == ".go":
        if shutil.which("gofmt"):
            _run(["gofmt", "-w", str(p)])

    elif ext == ".rs":
        if shutil.which("rustfmt"):
            _run(["rustfmt", str(p)])

    elif ext in (".ts", ".tsx", ".js", ".jsx", ".json", ".yaml", ".yml"):
        runner = _npx_or_bunx()
        if runner:
            _run([runner, "prettier", "--write", "--ignore-unknown", str(p)], cwd=cwd)

    elif ext == ".md":
        runner = _npx_or_bunx()
        if runner:
            _run([runner, "prettier", "--write", "--prose-wrap", "preserve", str(p)], cwd=cwd)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    tool = data.get("tool_name", "")
    if tool not in ("Write", "Edit"):
        return 0

    inp = data.get("tool_input") or {}
    file_path = inp.get("file_path", "")
    if not file_path:
        return 0

    try:
        _format(file_path)
    except Exception:
        pass  # never fail loudly

    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
