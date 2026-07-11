#!/usr/bin/env python3
"""
stop_verify.py -- Stop hook that runs the project test suite + type checker
before Claude is allowed to declare it's done.

Exits 2 (blocking) if tests or type checks fail; exits 0 to allow the Stop.
Detect project type from the CWD (or STOP_VERIFY_DIR env var to override):

  package.json with "typecheck" script -> npm run typecheck
  package.json with "test" script      -> npm test (or vitest/jest)
  pytest.ini / pyproject.toml [pytest] -> python -m pytest -q
  go.mod                               -> go test ./...
  Cargo.toml                           -> cargo test --quiet

Skips silently if no project type is detected. Runs at most once per directory
per session (sentinel at /tmp/stop_verify_<hash>.done so repeated Stop calls
in the same session are fast).

Set STOP_VERIFY_SKIP=1 to bypass for a single turn (e.g. if you're mid-refactor
and know tests are intentionally broken).
"""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile


def _run(cmd: list[str], cwd: str) -> tuple[int, str]:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            cwd=cwd, timeout=120
        )
        return r.returncode, (r.stdout + r.stderr)[-3000:]
    except subprocess.TimeoutExpired:
        return 1, "timeout after 120s"
    except Exception as e:
        return 1, str(e)


def _sentinel(cwd: str) -> pathlib.Path:
    key = hashlib.md5(cwd.encode()).hexdigest()[:8]
    return pathlib.Path(tempfile.gettempdir()) / f"stop_verify_{key}.done"


def _pkg_has_script(pkg: dict, name: str) -> bool:
    return name in (pkg.get("scripts") or {})


def main() -> int:
    if os.environ.get("STOP_VERIFY_SKIP") == "1":
        return 0

    cwd = os.environ.get("STOP_VERIFY_DIR") or os.getcwd()
    sentinel = _sentinel(cwd)
    if sentinel.exists():
        return 0  # already verified this session

    failures: list[str] = []

    # Python
    py_markers = ["pytest.ini", "pyproject.toml", "setup.cfg"]
    if any((pathlib.Path(cwd) / m).exists() for m in py_markers):
        if shutil.which("pytest") or shutil.which("python"):
            rc, out = _run([sys.executable, "-m", "pytest", "-q", "--tb=short",
                            "--no-header", "-x"], cwd)
            if rc != 0:
                failures.append(f"pytest failed:\n{out}")

    # Node / TypeScript
    pkg_path = pathlib.Path(cwd) / "package.json"
    if pkg_path.exists():
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
        except Exception:
            pkg = {}
        runner = "npm"
        if (pathlib.Path(cwd) / "bun.lockb").exists() and shutil.which("bun"):
            runner = "bun"

        if _pkg_has_script(pkg, "typecheck"):
            rc, out = _run([runner, "run", "typecheck"], cwd)
            if rc != 0:
                failures.append(f"typecheck failed:\n{out}")

        if _pkg_has_script(pkg, "test") and not failures:
            rc, out = _run([runner, "test", "--", "--passWithNoTests", "--silent"],
                           cwd)
            if rc != 0:
                # Retry without --silent in case the runner doesn't support it
                rc, out = _run([runner, "test"], cwd)
                if rc != 0:
                    failures.append(f"tests failed:\n{out}")

    # Go
    if (pathlib.Path(cwd) / "go.mod").exists() and shutil.which("go"):
        rc, out = _run(["go", "test", "./..."], cwd)
        if rc != 0:
            failures.append(f"go test failed:\n{out}")

    # Rust
    if (pathlib.Path(cwd) / "Cargo.toml").exists() and shutil.which("cargo"):
        rc, out = _run(["cargo", "test", "--quiet"], cwd)
        if rc != 0:
            failures.append(f"cargo test failed:\n{out}")

    if failures:
        print("STOP BLOCKED — tests/type checks are failing. Fix before declaring done:",
              file=sys.stderr)
        for f in failures:
            print(f, file=sys.stderr)
        return 2

    sentinel.touch()
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
