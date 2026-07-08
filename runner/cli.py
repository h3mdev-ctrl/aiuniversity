"""
cli.py -- the command SKILL.md calls. Emits JSON so the agent reads a clean,
machine-readable result instead of parsing prose.

    python -m runner.cli steps      <pack_dir>   # teach: the ordered steps
    python -m runner.cli verify     <pack_dir>   # read-only: check, report gap
    python -m runner.cli remediate  <pack_dir>   # apply fixes, then re-check

A pack_dir is a folder containing pack.yaml. Its PARENT is the registry root, so
module refs resolve as sibling folders (packs/foundation -> packs/gbrain-windows).

Exit code: 0 = PASS, 1 = stopped (human needed), 2 = bad recipe / usage error.
The JSON on stdout is the source of truth; the exit code is a convenience.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from runner.verify import (
    PackCompositionError,
    PackValidationError,
    expand_steps,
    load_pack,
    make_disk_resolver,
    run_pack,
)

EXIT_PASS = 0
EXIT_STOPPED = 1
EXIT_BAD = 2


def _pack_and_resolver(pack_dir: str):
    d = Path(pack_dir)
    pack = load_pack(d / "pack.yaml")
    resolver = make_disk_resolver(d.parent)  # siblings are modules
    return pack, resolver


def _cmd_steps(pack_dir: str, variant: "str | None") -> int:
    pack, resolver = _pack_and_resolver(pack_dir)
    print(
        json.dumps(
            {"pack": pack.name, "version": pack.version,
             "variant": variant or pack.default_variant,
             "variants": pack.variants,
             "steps": expand_steps(pack, resolver, variant=variant)},
            indent=2,
        )
    )
    return EXIT_PASS


def _run(pack_dir: str, apply_fixes: bool, variant: "str | None") -> int:
    pack, resolver = _pack_and_resolver(pack_dir)
    result = run_pack(pack, resolver=resolver, apply_fixes=apply_fixes, variant=variant)

    payload = {
        "pack": pack.name,
        "mode": "remediate" if apply_fixes else "verify",
        "variant": variant or pack.default_variant,
        "passed": result.passed,
        "stopped_at": result.stopped_at,
        "outcomes": [asdict(o) for o in result.outcomes],
    }
    # On failure, attach the stopped step's instruction + exact fix so the skill
    # can build the four-part failure message (interaction-design Rule 2).
    if not result.passed and result.stopped_at is not None:
        for s in expand_steps(pack, resolver, variant=variant):
            if s["id"] == result.stopped_at:
                payload["stopped_step"] = {
                    "id": s["id"],
                    "instruction": s.get("instruction"),
                    "fix": s.get("fix"),
                    "on_fail": s.get("on_fail"),
                }
                break

    print(json.dumps(payload, indent=2))
    return EXIT_PASS if result.passed else EXIT_STOPPED


def main(argv: "list[str] | None" = None) -> int:
    # Windows: make stdout UTF-8 so pack text with non-ASCII never crashes.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    parser = argparse.ArgumentParser(prog="runner.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("steps", "verify", "remediate"):
        p = sub.add_parser(name)
        p.add_argument("pack_dir", help="folder containing pack.yaml")
        p.add_argument(
            "--variant",
            default=None,
            help="which variant to run (e.g. local / hosted); default = pack's default_variant",
        )

    args = parser.parse_args(argv)

    try:
        if args.command == "steps":
            return _cmd_steps(args.pack_dir, args.variant)
        if args.command == "verify":
            return _run(args.pack_dir, apply_fixes=False, variant=args.variant)
        if args.command == "remediate":
            return _run(args.pack_dir, apply_fixes=True, variant=args.variant)
    except (PackValidationError, PackCompositionError, FileNotFoundError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, indent=2))
        return EXIT_BAD

    return EXIT_BAD  # pragma: no cover -- argparse requires a known command


if __name__ == "__main__":
    raise SystemExit(main())
