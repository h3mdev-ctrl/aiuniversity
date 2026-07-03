"""Tests for the obsidian-wiki pack -- vault setup + memory linkage.

Run against a throwaway CLAUDE_HOME. The environmental steps (node-present,
published-free, gbrain-queryable) aren't exercised here -- they need Node, a free
host, and gbrain respectively. What we prove: the vault is created, it links into
memory, and the memory doctor stays HEALTHY after linking (the wiki reference must
be reachable, not dark).

    python -m pytest tests/test_obsidian_pack.py -q
"""

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WIKI = REPO / "packs" / "obsidian-wiki" / "files"
MEM = REPO / "packs" / "memory" / "files"
sys.path.insert(0, str(REPO))

from runner.verify import load_pack  # noqa: E402


def run(files: Path, script: str, *args: str, home: Path):
    env = dict(os.environ, CLAUDE_HOME=str(home))
    return subprocess.run(
        [sys.executable, str(files / script), *args],
        capture_output=True, text=True, env=env, encoding="utf-8",
    )


def test_vault_install_creates_files(tmp_path):
    assert run(WIKI, "setup_wiki.py", home=tmp_path).returncode == 0
    w = tmp_path / "wiki"
    for f in ("index.md", "getting-started.md", "_template.md", "PUBLISHING.md"):
        assert (w / f).exists(), f"missing {f}"
    assert (w / ".obsidian" / "app.json").exists()


def test_check_red_then_green(tmp_path):
    assert run(WIKI, "setup_wiki.py", "--check", home=tmp_path).returncode == 1
    run(WIKI, "setup_wiki.py", home=tmp_path)
    assert run(WIKI, "setup_wiki.py", "--check", home=tmp_path).returncode == 0


def test_link_memory_requires_memory_first(tmp_path):
    run(WIKI, "setup_wiki.py", home=tmp_path)  # vault, but no memory yet
    r = run(WIKI, "setup_wiki.py", "--link-memory", home=tmp_path)
    assert r.returncode == 1
    assert "memory" in r.stdout


def test_link_memory_after_memory_is_set_up(tmp_path):
    run(MEM, "setup_memory.py", home=tmp_path)     # memory first
    run(WIKI, "setup_wiki.py", home=tmp_path)       # vault
    assert run(WIKI, "setup_wiki.py", "--check-memory-link", home=tmp_path).returncode == 1
    assert run(WIKI, "setup_wiki.py", "--link-memory", home=tmp_path).returncode == 0
    assert run(WIKI, "setup_wiki.py", "--check-memory-link", home=tmp_path).returncode == 0
    assert (tmp_path / "memory" / "reference_wiki.md").exists()
    assert "reference_wiki" in (tmp_path / "memory" / "MEMORY.md").read_text(encoding="utf-8")


def test_doctor_stays_healthy_after_link(tmp_path):
    run(MEM, "setup_memory.py", home=tmp_path)
    run(WIKI, "setup_wiki.py", home=tmp_path)
    run(WIKI, "setup_wiki.py", "--link-memory", home=tmp_path)
    r = run(MEM, "memory_doctor.py", home=tmp_path)   # the linked wiki must be reachable
    assert r.returncode == 0
    assert "HEALTHY" in r.stdout


def test_set_url_records_it(tmp_path):
    run(WIKI, "setup_wiki.py", home=tmp_path)
    assert run(WIKI, "setup_wiki.py", "--set-url", "https://example.test", home=tmp_path).returncode == 0
    assert "example.test" in (tmp_path / "wiki" / ".publish_url").read_text(encoding="utf-8")


def test_pack_loads_with_variants():
    pack = load_pack(REPO / "packs" / "obsidian-wiki" / "pack.yaml")
    assert pack.name == "obsidian-wiki"
    assert pack.variants == ["local", "hosted"]
    assert pack.default_variant == "local"
    assert [s.id for s in pack.steps] == [
        "vault", "memory-linked", "node-present", "published-free", "gbrain-queryable",
    ]


def test_local_variant_skips_publishing_steps():
    from runner.verify import expand_steps  # noqa: PLC0415
    pack = load_pack(REPO / "packs" / "obsidian-wiki" / "pack.yaml")
    local_ids = [s["id"] for s in expand_steps(pack, variant="local")]
    hosted_ids = [s["id"] for s in expand_steps(pack, variant="hosted")]
    # local: no node/publish; hosted: includes them
    assert "node-present" not in local_ids and "published-free" not in local_ids
    assert "node-present" in hosted_ids and "published-free" in hosted_ids
    assert "vault" in local_ids and "memory-linked" in local_ids  # shared
