#!/usr/bin/env python3
"""capabilities_check.py -- the foundation's layer-4 (gbrain) check, made honest.

gbrain is OPTIONAL for the foundation, so "not installed" passes. But the
previous check was `exit(0 if which('gbrain') else 0)` -- it exited 0 on BOTH
branches, so it could never fail and proved nothing. A check that cannot fail
is decoration: it reads as verified while testing nothing.

Now:
  gbrain not on PATH      -> PASS, and says so ("not installed -- optional")
  gbrain on PATH, runs    -> PASS ("installed and runs")
  gbrain on PATH, broken  -> FAIL (exit 1) -- a half-installed brain is the
                             case worth catching, because every pack that
                             leans on it will fail later and further away.

Usage:  python packs/foundation/files/capabilities_check.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys


def main() -> int:
    exe = shutil.which("gbrain")
    if not exe:
        print("gbrain: not installed -- optional, layer 4 skipped")
        return 0
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"gbrain: on PATH but did not run ({type(e).__name__}) -- "
              f"run packs/gbrain-windows to repair")
        return 1
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or [""]
        print(f"gbrain: on PATH but `gbrain --version` exited {r.returncode}: {tail[0][:160]}")
        return 1
    ver = (r.stdout or "").strip().splitlines()[:1] or ["?"]
    print(f"gbrain: installed and runs ({ver[0][:60]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
