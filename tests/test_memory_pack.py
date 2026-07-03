"""Tests for the memory pack -- setup + audit, run against a throwaway home.

Everything runs with CLAUDE_HOME pointed at a tmp dir, so the real ~/.claude is
never touched. No `claude -p` here -- the live recall probe (step 4) is the
recipient's one behavioural check; its handling is covered by the pack-loads test.

    python -m pytest tests/test_memory_pack.py -q
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FILES = REPO / "packs" / "memory" / "files"
sys.path.insert(0, str(REPO))

from runner.verify import expand_steps, load_pack, make_disk_resolver  # noqa: E402


def run(script: str, *args: str, home: Path):
    env = dict(os.environ, CLAUDE_HOME=str(home))
    return subprocess.run(
        [sys.executable, str(FILES / script), *args],
        capture_output=True, text=True, env=env, encoding="utf-8",
    )


# --- setup_memory.py --------------------------------------------------------


def test_install_creates_the_structure(tmp_path):
    r = run("setup_memory.py", home=tmp_path)
    assert r.returncode == 0
    mem = tmp_path / "memory"
    for f in ("MEMORY.md", "reference_canary.md", "_template_memory.md", "memory_doctor.py"):
        assert (mem / f).exists(), f"missing {f}"


def test_install_ships_worked_examples(tmp_path):
    run("setup_memory.py", home=tmp_path)
    mem = tmp_path / "memory"
    for f in ("_example_index.md", "_example_feedback.md", "_example_reference.md"):
        assert (mem / f).exists(), f"missing {f}"
    # examples are underscore-prefixed -> the doctor ignores them; still HEALTHY
    r = run("memory_doctor.py", home=tmp_path)
    assert r.returncode == 0 and "HEALTHY" in r.stdout


def test_check_is_red_before_and_green_after_install(tmp_path):
    assert run("setup_memory.py", "--check", home=tmp_path).returncode == 1
    run("setup_memory.py", home=tmp_path)
    assert run("setup_memory.py", "--check", home=tmp_path).returncode == 0


def test_install_is_idempotent(tmp_path):
    run("setup_memory.py", home=tmp_path)
    second = run("setup_memory.py", home=tmp_path)
    assert second.returncode == 0
    # discovery short-circuits: it finds the one it just made, doesn't duplicate
    assert "found existing" in second.stdout


# --- discovery: audit + find where it is (don't build a duplicate) ----------


def _project_scoped_memory(tmp_path):
    """Simulate Claude Code's project-scoped memory location."""
    d = tmp_path / "projects" / "C--Users-jason-ClaudeCode" / "memory"
    d.mkdir(parents=True)
    (d / "MEMORY.md").write_text("# Memory\n\nindex only\n", encoding="utf-8")
    return d


def test_check_finds_project_scoped_memory(tmp_path):
    _project_scoped_memory(tmp_path)  # no global memory, only project-scoped
    assert run("setup_memory.py", "--check", home=tmp_path).returncode == 0


def test_find_reports_the_project_scoped_location(tmp_path):
    _project_scoped_memory(tmp_path)
    r = run("setup_memory.py", "--find", home=tmp_path)
    assert r.returncode == 0
    assert "projects" in r.stdout and "memory" in r.stdout


def test_install_does_not_duplicate_when_project_scoped_exists(tmp_path):
    _project_scoped_memory(tmp_path)
    r = run("setup_memory.py", home=tmp_path)
    assert r.returncode == 0
    assert "found existing" in r.stdout
    assert not (tmp_path / "memory" / "MEMORY.md").exists()  # no global duplicate


def test_doctor_audits_the_discovered_project_scoped_memory(tmp_path):
    _project_scoped_memory(tmp_path)
    r = run("memory_doctor.py", home=tmp_path)
    assert r.returncode == 0
    assert "auditing memory at" in r.stdout
    assert "HEALTHY" in r.stdout


def test_find_reports_none_when_absent(tmp_path):
    r = run("setup_memory.py", "--find", home=tmp_path)
    assert r.returncode == 1
    assert "no memory system found" in r.stdout


# --- ambiguity: >1 memory found -> fail loud, never silently pick ------------
# (Jason's real case: "brain" sorts before "Documents-ClaudeCode" case-folded.)


def _two_project_memories(tmp_path):
    for name in ("C--Users-jason-brain", "C--Users-jason-Documents-ClaudeCode"):
        d = tmp_path / "projects" / name / "memory"
        d.mkdir(parents=True)
        (d / "MEMORY.md").write_text("# Memory\n\nindex only\n", encoding="utf-8")


def test_check_fails_when_ambiguous(tmp_path):
    _two_project_memories(tmp_path)
    # must NOT silently pass by guessing one
    assert run("setup_memory.py", "--check", home=tmp_path).returncode != 0


def test_find_reports_ambiguity_and_lists_all(tmp_path):
    _two_project_memories(tmp_path)
    r = run("setup_memory.py", "--find", home=tmp_path)
    assert r.returncode != 0
    assert "AMBIGUOUS" in r.stdout
    assert "brain" in r.stdout and "ClaudeCode" in r.stdout  # both listed


def test_install_refuses_and_does_not_duplicate_when_ambiguous(tmp_path):
    _two_project_memories(tmp_path)
    r = run("setup_memory.py", home=tmp_path)
    assert r.returncode != 0
    assert "AMBIGUOUS" in r.stdout
    assert not (tmp_path / "memory" / "MEMORY.md").exists()  # no global duplicate


def test_doctor_fails_loudly_when_ambiguous(tmp_path):
    _two_project_memories(tmp_path)
    r = run("memory_doctor.py", home=tmp_path)
    assert r.returncode == 1
    assert "ambiguous" in r.stdout.lower()
    assert "VERDICT: ISSUES" in r.stdout


def test_pinning_CLAUDE_MEMORY_HOME_resolves_ambiguity(tmp_path):
    _two_project_memories(tmp_path)
    target = tmp_path / "projects" / "C--Users-jason-Documents-ClaudeCode" / "memory"
    env = dict(os.environ, CLAUDE_HOME=str(tmp_path), CLAUDE_MEMORY_HOME=str(target))
    r = subprocess.run(
        [sys.executable, str(FILES / "memory_doctor.py")],
        capture_output=True, text=True, env=env, encoding="utf-8",
    )
    assert r.returncode == 0
    assert "HEALTHY" in r.stdout
    assert str(target) in r.stdout  # audited the pinned one, not the other


def test_wire_and_check_wire(tmp_path):
    run("setup_memory.py", home=tmp_path)
    assert run("setup_memory.py", "--check-wire", home=tmp_path).returncode == 1
    assert run("setup_memory.py", "--wire", home=tmp_path).returncode == 0
    assert run("setup_memory.py", "--check-wire", home=tmp_path).returncode == 0
    assert "memory/MEMORY.md" in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")


# --- memory_doctor.py -------------------------------------------------------


def test_doctor_healthy_on_fresh_install(tmp_path):
    run("setup_memory.py", home=tmp_path)
    r = run("memory_doctor.py", home=tmp_path)
    assert r.returncode == 0
    assert "HEALTHY" in r.stdout


def test_doctor_counts_index_and_catalog_reachability(tmp_path):
    # a memory linked only from a Tier-2 INDEX_*.md (not MEMORY.md) is NOT dark
    run("setup_memory.py", home=tmp_path)
    mem = tmp_path / "memory"
    (mem / "feedback_windows_quirk.md").write_text(
        "---\nname: windows-quirk\ndescription: x\ntype: feedback\n---\nbody\n", encoding="utf-8"
    )
    # route it from a sub-index, the way the tiered structure prescribes
    (mem / "INDEX_windows.md").write_text(
        "# Windows quirks\n\n| ... | [feedback_windows_quirk](feedback_windows_quirk.md) |\n",
        encoding="utf-8",
    )
    r = run("memory_doctor.py", home=tmp_path)
    assert r.returncode == 0 and "HEALTHY" in r.stdout   # reachable via INDEX_, not dark


def test_doctor_reachable_via_catalog(tmp_path):
    run("setup_memory.py", home=tmp_path)
    mem = tmp_path / "memory"
    (mem / "reference_thing.md").write_text(
        "---\nname: thing\ndescription: x\ntype: reference\n---\nbody\n", encoding="utf-8"
    )
    (mem / "CATALOG.md").write_text("# Catalog\n\n- reference_thing.md -- the thing\n", encoding="utf-8")
    r = run("memory_doctor.py", home=tmp_path)
    assert r.returncode == 0 and "HEALTHY" in r.stdout


def test_doctor_ignores_index_and_catalog_as_memory_files(tmp_path):
    # INDEX_*.md and CATALOG.md are routing files, not memories -- they must not
    # be flagged for missing frontmatter or as dark.
    run("setup_memory.py", home=tmp_path)
    mem = tmp_path / "memory"
    (mem / "INDEX_shipping.md").write_text("# Shipping routing (no frontmatter)\n", encoding="utf-8")
    (mem / "CATALOG.md").write_text("# Catalog (no frontmatter)\n", encoding="utf-8")
    r = run("memory_doctor.py", home=tmp_path)
    assert r.returncode == 0 and "HEALTHY" in r.stdout


def test_doctor_flags_a_dark_file(tmp_path):
    run("setup_memory.py", home=tmp_path)
    # a memory with valid frontmatter but not linked from MEMORY.md
    (tmp_path / "memory" / "feedback_orphan.md").write_text(
        "---\nname: orphan\ndescription: x\ntype: feedback\n---\nbody\n", encoding="utf-8"
    )
    r = run("memory_doctor.py", home=tmp_path)
    assert r.returncode == 1
    assert "dark" in r.stdout


def test_doctor_frontmatter_is_advisory_not_blocking(tmp_path):
    # a LINKED (reachable) file with no frontmatter is an advisory, not a block --
    # a mature memory accumulates older files and must still audit HEALTHY.
    run("setup_memory.py", home=tmp_path)
    mem = tmp_path / "memory"
    (mem / "feedback_untagged.md").write_text("just a body, no frontmatter\n", encoding="utf-8")
    (mem / "CATALOG.md").write_text("# Catalog\n\n- feedback_untagged.md -- x\n", encoding="utf-8")
    r = run("memory_doctor.py", home=tmp_path)
    assert r.returncode == 0 and "HEALTHY" in r.stdout   # advisory does NOT flip verdict
    assert "frontmatter" in r.stdout                      # but it's still surfaced


def test_doctor_missing_index(tmp_path):
    (tmp_path / "memory").mkdir(parents=True)
    r = run("memory_doctor.py", home=tmp_path)
    assert r.returncode == 1
    assert "missing" in r.stdout


# --- the packs themselves ---------------------------------------------------


def test_memory_pack_loads_with_four_steps():
    pack = load_pack(REPO / "packs" / "memory" / "pack.yaml")
    assert pack.name == "memory"
    assert [s.id for s in pack.steps] == [
        "structure", "index-healthy", "wired-to-constitution", "recall-probe",
    ]


def test_foundation_expands_memory_and_gbrain():
    resolver = make_disk_resolver(REPO / "packs")
    ids = [s["id"] for s in expand_steps(load_pack(REPO / "packs" / "foundation" / "pack.yaml"), resolver)]
    # memory module expands first (layer 1), gbrain in layer 4
    assert "memory/structure" in ids
    assert "memory/recall-probe" in ids
    assert "gbrain-windows/install" in ids
    assert ids.index("memory/structure") < ids.index("gbrain-windows/install")
