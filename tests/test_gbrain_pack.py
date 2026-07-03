"""Tests for the gbrain-windows pack -- the usage-discipline wiring.

The environmental steps (install / brain-reachable / mcp-registered / activation-exam)
need a real gbrain + claude and aren't exercised here. What we prove: the pack teaches
Claude to USE gbrain habitually by writing a usage-discipline block into CLAUDE.md,
idempotently, coexisting with a gstack search-guidance block.

    python -m pytest tests/test_gbrain_pack.py -q
"""

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FILES = REPO / "packs" / "gbrain-windows" / "files"
sys.path.insert(0, str(REPO))

from runner.verify import load_pack  # noqa: E402


def run(script: str, *args: str, home: Path):
    env = dict(os.environ, CLAUDE_HOME=str(home))
    return subprocess.run(
        [sys.executable, str(FILES / script), *args],
        capture_output=True, text=True, env=env, encoding="utf-8",
    )


def test_check_red_before_install(tmp_path):
    assert run("setup_gbrain_usage.py", "--check", home=tmp_path).returncode == 1


def test_install_then_check_green(tmp_path):
    assert run("setup_gbrain_usage.py", "--install", home=tmp_path).returncode == 0
    assert run("setup_gbrain_usage.py", "--check", home=tmp_path).returncode == 0
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    # the load-bearing behaviours must be present
    assert "put_page" in text                       # capture
    assert "before researching" in text.lower()     # research-first
    assert "query" in text and "search" in text     # query > search
    assert "back-link" in text.lower() or "backlink" in text.lower()
    assert "ideas/" in text and "people/" in text   # slug conventions


def test_install_is_idempotent(tmp_path):
    run("setup_gbrain_usage.py", "--install", home=tmp_path)
    run("setup_gbrain_usage.py", "--install", home=tmp_path)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    # the block markers appear exactly once (no duplication on re-run)
    assert text.count("<!-- gbrain-usage-discipline:start -->") == 1
    assert text.count("<!-- gbrain-usage-discipline:end -->") == 1


def test_coexists_with_existing_claude_md_and_gstack_block(tmp_path):
    # a recipient who already ran /setup-gbrain has a search-guidance block + other rules
    (tmp_path / "CLAUDE.md").write_text(
        "# My constitution\n\nsome rules\n\n"
        "## GBrain Search Guidance (configured by /setup-gbrain)\n"
        "<!-- gstack-gbrain-search-guidance:start -->\nprefer gbrain over grep\n"
        "<!-- gstack-gbrain-search-guidance:end -->\n",
        encoding="utf-8",
    )
    assert run("setup_gbrain_usage.py", "--install", home=tmp_path).returncode == 0
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    # both blocks + the pre-existing content survive
    assert "some rules" in text
    assert "gstack-gbrain-search-guidance:start" in text   # gstack block untouched
    assert "gbrain-usage-discipline:start" in text          # ours added


def test_pack_loads_with_usage_discipline_step():
    pack = load_pack(REPO / "packs" / "gbrain-windows" / "pack.yaml")
    assert pack.name == "gbrain-windows"
    ids = [s.id for s in pack.steps]
    assert ids[-1] == "usage-discipline"   # habit wiring comes after the tool is live
    assert "activation-exam" in ids and ids.index("activation-exam") < ids.index("usage-discipline")
