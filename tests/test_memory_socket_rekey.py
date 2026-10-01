"""Tests for the salvage -> compaction -> restore chain across the session re-key.

Claude Code assigns a NEW session_id at compaction. A carry keyed only on
session_id is written under one id and looked up under another, so restore
misses every time -- and the old `--probe restore` still said LIVE, because the
example restore hook always prints boilerplate. These tests pin both halves:
the example hooks survive the re-key without leaking across directories, and
the doctor can tell LIVE from DEAD from LEAK.

    python -m pytest tests/test_memory_socket_rekey.py -q
"""

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
PACK = REPO / "packs" / "memory-socket"
EX = PACK / "files" / "examples"
SALVAGE = EX / "salvage_pre_compact.py"
RESTORE = EX / "restore_post_compact.py"
DOCTOR = PACK / "files" / "socket_doctor.py"
MARK = "rekeycanary_0042"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem + "_t", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def w(tmp_path):
    home, real = tmp_path / "home", tmp_path / "realhome"
    a, b = tmp_path / "projA", tmp_path / "projB"
    for d in (home, real, a, b):
        d.mkdir()
    tr = tmp_path / "t.jsonl"
    tr.write_text("\n".join(json.dumps(o) for o in (
        {"type": "user", "message": {"role": "user", "content": f"measure {MARK} please"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": f"Measured {MARK} at 412 ms, verified on 3 runs."}]}},
    )) + "\n", encoding="utf-8")
    return {"home": home, "real": real, "a": a, "b": b, "tr": tr, "tmp": tmp_path}


def run(script, payload, w, cwd, *args):
    env = dict(os.environ, CLAUDE_HOME=str(w["home"]),
               HOME=str(w["real"]), USERPROFILE=str(w["real"]))
    return subprocess.run([sys.executable, str(script), *args],
                          input=payload if isinstance(payload, str) else json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8",
                          env=env, cwd=str(cwd), timeout=60)


def salvage(w, session="A", cwd=None):
    cwd = cwd or w["a"]
    return run(SALVAGE, {"session_id": session, "transcript_path": str(w["tr"]),
                         "cwd": str(cwd), "trigger": "manual"}, w, cwd)


def restore(w, session, cwd):
    return run(RESTORE, {"session_id": session, "cwd": str(cwd)}, w, cwd)


def carry_dir(w):
    return w["home"] / "state" / "compact_carry"


# --- the example hooks -------------------------------------------------------


def test_cwd_key_is_identical_in_both_hooks(w):
    s, r = _load(SALVAGE), _load(RESTORE)
    for p in (w["a"], str(w["a"]).upper(), str(w["a"]) + os.sep):
        assert s.cwd_key(str(p)) == r.cwd_key(str(p))
    assert s.cwd_key(str(w["a"])) != s.cwd_key(str(w["b"]))


def test_salvage_writes_both_keys_with_origin_header(w):
    assert salvage(w).returncode == 0
    files = sorted(p.name for p in carry_dir(w).glob("*.md"))
    assert "A.md" in files and any(f.startswith("cwd-") for f in files), files
    for f in carry_dir(w).glob("*.md"):
        text = f.read_text(encoding="utf-8")
        assert text.startswith("<!-- origin-session: A ") and MARK in text


def test_restore_survives_the_rekey_in_the_same_directory(w):
    salvage(w, "A")
    r = restore(w, "B", w["a"])          # compaction re-keyed A -> B
    assert r.returncode == 0
    assert MARK in r.stdout
    assert "Matched by working directory" in r.stdout and "session A" in r.stdout
    assert "origin-session" not in r.stdout          # header stripped
    assert "no carry-forward digest found" not in r.stdout


def test_restore_prefers_the_exact_session_key(w):
    salvage(w, "A")
    r = restore(w, "A", w["a"])
    assert MARK in r.stdout and "Matched by working directory" not in r.stdout


def test_restore_never_leaks_into_another_directory(w):
    salvage(w, "A", w["a"])
    r = restore(w, "C", w["b"])
    assert r.returncode == 0
    assert MARK not in r.stdout
    assert "no carry-forward digest found" in r.stdout


def test_cwd_key_has_a_tighter_window_than_the_session_key(w):
    salvage(w, "A")
    old = time.time() - 20 * 60                       # 20 min: past 15, inside 60
    for f in carry_dir(w).glob("*.md"):
        os.utime(f, (old, old))
    assert MARK not in restore(w, "B", w["a"]).stdout   # re-keyed: cwd key only -> stale
    assert MARK in restore(w, "A", w["a"]).stdout       # exact session key still valid


def test_restore_exits_0_on_garbage(w):
    for g in ("", "nope", "null", "42", "[]"):
        assert run(RESTORE, g, w, w["a"]).returncode == 0


# --- the doctor's re-key probe -----------------------------------------------


def register(w, event, script):
    p = w["home"] / "settings.json"
    s = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"hooks": {}}
    s["hooks"].setdefault(event, []).append(
        {"hooks": [{"type": "command", "command": f'"{sys.executable}" "{script}"'}]})
    p.write_text(json.dumps(s), encoding="utf-8")


def probe(w):
    return run(DOCTOR, "", w, w["tmp"], "--probe", "restore")


def _write(w, name, body):
    p = w["tmp"] / name
    p.write_text(body, encoding="utf-8")
    return p


def test_probe_live_with_the_example_hooks(w):
    register(w, "PreCompact", SALVAGE)
    register(w, "PostCompact", RESTORE)
    d = probe(w)
    assert d.returncode == 0, d.stdout
    assert d.stdout.startswith("LIVE")


def test_probe_dead_with_a_session_only_restore(w):
    # The v0.1 restore: keyed on session_id alone. Prints boilerplate every time,
    # which the old probe counted as LIVE.
    old = _write(w, "restore_session_only.py", (
        "import json,os,pathlib,re,sys\n"
        "d=json.loads(sys.stdin.read() or '{}')\n"
        "cd=pathlib.Path(os.environ['CLAUDE_HOME'])/'state'/'compact_carry'\n"
        "sid=re.sub(r'[^A-Za-z0-9_-]','_',str(d.get('session_id') or ''))\n"
        "p=cd/f'{sid}.md'\n"
        "print('CONTEXT COMPACTED - your rules and constraints are unchanged.')\n"
        "print(p.read_text(encoding='utf-8') if p.is_file() else 'NOTE: no carry')\n"))
    register(w, "PreCompact", SALVAGE)
    register(w, "PostCompact", old)
    d = probe(w)
    assert d.returncode == 1
    assert d.stdout.startswith("DEAD"), d.stdout


def test_probe_leak_with_a_newest_file_restore(w):
    leaky = _write(w, "restore_newest.py", (
        "import os,pathlib,sys\n"
        "sys.stdin.read()\n"
        "cd=pathlib.Path(os.environ['CLAUDE_HOME'])/'state'/'compact_carry'\n"
        "fs=sorted(cd.glob('*.md'),key=lambda f:f.stat().st_mtime) if cd.is_dir() else []\n"
        "print(fs[-1].read_text(encoding='utf-8') if fs else 'nothing')\n"))
    register(w, "PreCompact", SALVAGE)
    register(w, "PostCompact", leaky)
    d = probe(w)
    assert d.returncode == 1
    assert d.stdout.startswith("LEAK"), d.stdout


def test_probe_dark_when_one_half_is_missing(w):
    register(w, "PostCompact", RESTORE)
    d = probe(w)
    assert d.returncode == 1 and d.stdout.startswith("DARK")
    assert "PreCompact" in d.stdout


def test_probe_never_writes_into_the_real_home(w):
    # A hook that ignores CLAUDE_HOME and writes under Path.home() -- like many
    # real ones. The probe must redirect HOME/USERPROFILE so it lands in temp.
    rude = _write(w, "rude_salvage.py", (
        "import pathlib,sys\n"
        "sys.stdin.read()\n"
        "p=pathlib.Path.home()/'.claude'/'state'/'compact_carry'\n"
        "p.mkdir(parents=True,exist_ok=True)\n"
        "(p/'rude.md').write_text('x',encoding='utf-8')\n"))
    register(w, "PreCompact", rude)
    register(w, "PostCompact", RESTORE)
    probe(w)
    assert not any(w["real"].rglob("*")), list(w["real"].rglob("*"))


def test_pack_step_uses_the_rekey_probe_and_can_fail():
    y = yaml.safe_load((PACK / "pack.yaml").read_text(encoding="utf-8"))
    step = next(s for s in y["steps"] if s["id"] == "salvage-survives-rekey")
    assert "--probe restore" in step["check"]["cmd"]
    # `contains LIVE` would also be satisfied by any detail text mentioning it;
    # anchor it to the verdict at the start of a line.
    assert step["check"]["type"] == "regex" and step["check"]["expect"].startswith("(?m)^LIVE")
