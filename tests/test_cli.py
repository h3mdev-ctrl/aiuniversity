"""CLI tests -- exercises the command SKILL.md calls, end to end.

These actually shell out (real executor), so they use portable commands
(`python --version`, a bogus command name) to stay deterministic on any OS.

    python -m pytest tests/test_cli.py -q
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runner.cli import EXIT_BAD, EXIT_PASS, EXIT_STOPPED, main  # noqa: E402


def write_pack(tmp_path, body: str) -> str:
    d = tmp_path / "mypack"
    d.mkdir()
    (d / "pack.yaml").write_text(body, encoding="utf-8")
    return str(d)


# A passing pack: `python --version` prints "Python X.Y", which contains "Python".
PASS_PACK = """
name: t
version: "1"
steps:
  - id: step-one
    instruction: confirm python is here
    check:
      type: contains
      cmd: python --version
      expect: Python
  - id: step-two
    instruction: confirm again
    check:
      type: command_succeeds
      cmd: python --version
"""

# A failing pack: a bogus command name exits non-zero everywhere.
FAIL_PACK = """
name: t
version: "1"
steps:
  - id: broken
    instruction: this step cannot pass
    check:
      type: command_succeeds
      cmd: this_command_does_not_exist_xyz_123
    on_fail: "install the missing tool, then re-run"
"""

BAD_PACK = """
name: t
version: "1"
steps:
  - id: x
    instruction: bad check type
    check:
      type: containz
      cmd: python --version
      expect: Python
"""


def test_steps_lists_the_ordered_steps(tmp_path, capsys):
    code = main(["steps", write_pack(tmp_path, PASS_PACK)])
    out = json.loads(capsys.readouterr().out)
    assert code == EXIT_PASS
    assert [s["id"] for s in out["steps"]] == ["step-one", "step-two"]


def test_verify_passes_on_a_good_pack(tmp_path, capsys):
    code = main(["verify", write_pack(tmp_path, PASS_PACK)])
    out = json.loads(capsys.readouterr().out)
    assert code == EXIT_PASS
    assert out["passed"] is True
    assert out["mode"] == "verify"


def test_verify_reports_the_gap_read_only(tmp_path, capsys):
    code = main(["verify", write_pack(tmp_path, FAIL_PACK)])
    out = json.loads(capsys.readouterr().out)
    assert code == EXIT_STOPPED
    assert out["passed"] is False
    assert out["stopped_at"] == "broken"
    # the stopped step carries the exact fix, for the failure message (Rule 2)
    assert out["stopped_step"]["on_fail"] == "install the missing tool, then re-run"


def test_bad_recipe_is_rejected(tmp_path, capsys):
    code = main(["verify", write_pack(tmp_path, BAD_PACK)])
    out = json.loads(capsys.readouterr().out)
    assert code == EXIT_BAD
    assert "message" in out
