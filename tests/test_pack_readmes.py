"""Structural conformance: every pack ships a README with the four convention sections.

This is the deterministic slice of the gbrain-skillpack doctor idea, applied to
aiuniversity as a pytest (no LLM judge, no local model needed): each packs/<name>/
must have a README.md carrying Contract / Iron Laws / Anti-Patterns / Related.
See docs/pack-structure.md.

    python -m pytest tests/test_pack_readmes.py -q
"""

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PACKS = sorted(p.name for p in (REPO / "packs").iterdir() if (p / "pack.yaml").exists())

REQUIRED_SECTIONS = ("## Contract", "## Iron Laws", "## Anti-Patterns", "## Related")


def test_there_are_packs():
    assert PACKS, "no packs discovered"


@pytest.mark.parametrize("pack", PACKS)
def test_pack_has_readme_with_sections(pack):
    readme = REPO / "packs" / pack / "README.md"
    assert readme.exists(), f"packs/{pack}/README.md missing"
    text = readme.read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS:
        assert section in text, f"packs/{pack}/README.md missing a '{section}' section"


@pytest.mark.parametrize("pack", PACKS)
def test_anti_patterns_use_the_marker(pack):
    # the convention: each anti-pattern leads with ❌ so it reads as a don't-list
    text = (REPO / "packs" / pack / "README.md").read_text(encoding="utf-8")
    anti = text.split("## Anti-Patterns", 1)[1].split("## ", 1)[0]
    assert "❌" in anti, f"packs/{pack}/README.md Anti-Patterns section has no ❌ items"
