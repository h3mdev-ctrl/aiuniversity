#!/usr/bin/env python3
"""
setup_wrap_up.py -- install the /wrap-up skill into ~/.claude/skills/wrap-up/SKILL.md.

The wrap-up skill orchestrates the end-of-session close-out: the ship gate (via
gstack's /ship + /land-and-deploy if available, or a documented hand-rolled
fallback), the deploy gate for publishable artefacts, and the 6-stage autolearn
pipeline (which reads the autolearn pack's phantom_workflow.md for its principles).

Gstack-optional: the skill detects whether /ship exists and falls back to a
documented manual ship pattern if not. So this pack works standalone; gstack
just makes Part 1 richer.

Modes:
    (no arg) / --install       install SKILL.md into ~/.claude/skills/wrap-up/
    --check                    exit 0 if skill file is installed
    --check-autolearn          exit 0 if autolearn pack is also installed (recommended companion)
    --uninstall                remove the skill (leaves the aiuniversity source alone)
"""
import os
import pathlib
import shutil
import sys


SKILL_TEMPLATE_NAME = "wrap_up_skill_template.md"


def base_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))


def skill_dir() -> pathlib.Path:
    return base_dir() / "skills" / "wrap-up"


def skill_path() -> pathlib.Path:
    return skill_dir() / "SKILL.md"


def _src() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent / SKILL_TEMPLATE_NAME


def install(force: bool = False) -> int:
    skill_dir().mkdir(parents=True, exist_ok=True)
    src = _src()
    if not src.exists():
        print(f"ERROR: source template not found at {src}")
        return 1
    dst = skill_path()
    if dst.exists():
        existing = dst.read_text(encoding="utf-8")
        new = src.read_text(encoding="utf-8")
        if existing == new:
            print("already installed and up-to-date")
            return 0
        if not force:
            print(f"REFUSING to overwrite existing SKILL.md at {dst}")
            print("The installed file differs from the pack template — likely a personal")
            print("customisation. Use --force to overwrite, or diff the two files first:")
            print(f"  diff \"{src}\" \"{dst}\"")
            print("If you want to keep your customisation but pull in updates, edit by hand.")
            return 1
        print(f"FORCE-updating existing skill at {dst}")
    else:
        print(f"installing new skill at {dst}")
    shutil.copyfile(src, dst)
    return 0


def check() -> int:
    if not skill_path().exists():
        print(f"missing: {skill_path()}")
        return 1
    return 0


def check_autolearn() -> int:
    """The wrap-up skill references autolearn's phantom_workflow.md for its principles.
    Recommend but do not require the autolearn pack be installed."""
    home = base_dir()
    # phantom_workflow.md gets installed by the autolearn pack next to memory
    candidates = [
        home / "projects",  # will search recursively
    ]
    for c in candidates:
        if not c.exists():
            continue
        for path in c.rglob("phantom_workflow.md"):
            print(f"autolearn workflow found: {path}")
            return 0
    print("autolearn pack workflow guide not found. Recommended companion:")
    print("  packs/autolearn — installs the git-commit capture + drain pipeline")
    print("The wrap-up skill still works without it, but the Part 2 autolearn scan")
    print("will be less structured. Consider installing autolearn alongside.")
    return 1


def uninstall() -> int:
    if not skill_path().exists():
        print("nothing to uninstall")
        return 0
    skill_path().unlink()
    try:
        skill_dir().rmdir()  # only removes if empty
    except OSError:
        pass
    print(f"removed {skill_path()}")
    return 0


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--install"
    force = "--force" in argv
    if mode == "--install":
        return install(force=force)
    if mode == "--check":
        return check()
    if mode == "--check-autolearn":
        return check_autolearn()
    if mode == "--uninstall":
        return uninstall()
    if mode == "--force":
        # allow `--force` as first arg meaning `--install --force`
        return install(force=True)
    print(f"unknown mode {mode!r}")
    return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main(sys.argv))
