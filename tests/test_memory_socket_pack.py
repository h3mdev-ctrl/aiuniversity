"""Tests for the memory-socket pack: the recall hook's branches and trace, the
doctor's LIVE / DEGRADED / DARK verdicts, identity staleness, and the learning
loop probe -- all against a throwaway CLAUDE_HOME and memory store.

No ollama needed: the semantic branch is exercised against a stub embed server
on 127.0.0.1 that speaks the /api/embed shape.

    python -m pytest tests/test_memory_socket_pack.py -q
"""

import http.server
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
import zlib
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
PACK = REPO / "packs" / "memory-socket"
FILES = PACK / "files"
EX = FILES / "examples"
RECALL = EX / "recall_on_prompt.py"
IDENTITY = EX / "identity_on_start.py"
LEARN = EX / "learn_on_compact.py"
BUILD = EX / "build_recall_index.py"
DOCTOR = FILES / "socket_doctor.py"

GOOD_PROMPT = "how do I set up the memory index"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def world(tmp_path):
    """A project with a memory store, and an empty CLAUDE_HOME."""
    home = tmp_path / "home"
    home.mkdir()
    proj = tmp_path / "proj"
    mem = proj / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text(
        "# index\n\n| When you're about to... | Consult |\n| --- | --- |\n"
        "| set up the memory index or resolver | [idx](reference_memory_index.md) |\n"
        "| deploy a release to production | [gate](feedback_deploy_gate.md) |\n",
        encoding="utf-8")
    (mem / "reference_memory_index.md").write_text(
        "---\nname: memory-index\ndescription: how the memory index and resolver "
        "are laid out, see index_v2\ntype: reference\n---\nbody\n", encoding="utf-8")
    (mem / "feedback_deploy_gate.md").write_text(
        "---\nname: deploy-gate\ndescription: before you deploy a release run the "
        "smoke gate first\ntype: feedback\n---\nbody\n", encoding="utf-8")
    return {"home": home, "proj": proj, "mem": mem, "tmp": tmp_path}


def run(script: Path, payload, world, *args, **env_extra):
    env = dict(os.environ, CLAUDE_HOME=str(world["home"]))
    env.pop("CLAUDE_MEMORY_HOME", None)
    env.pop("RECALL_TRACE", None)
    env.update({k: str(v) for k, v in env_extra.items()})
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, str(script), *args], input=stdin,
                          capture_output=True, text=True, encoding="utf-8",
                          env=env, cwd=str(world["proj"]), timeout=60)


def recall_payload(world, prompt=GOOD_PROMPT):
    return {"prompt": prompt, "cwd": str(world["proj"]), "session_id": "t"}


def register(world, event: str, script: Path):
    p = world["home"] / "settings.json"
    s = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"hooks": {}}
    s["hooks"].setdefault(event, []).append(
        {"hooks": [{"type": "command", "command": f'"{sys.executable}" "{script}"'}]})
    p.write_text(json.dumps(s), encoding="utf-8")


def doctor(world, *args, **env_extra):
    return run(DOCTOR, "", world, *args, **env_extra)


class _Embed(http.server.BaseHTTPRequestHandler):
    """Deterministic bag-of-words vectors in the ollama /api/embed shape."""

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        texts = body["input"] if isinstance(body["input"], list) else [body["input"]]
        vecs = []
        for t in texts:
            v = [0.0] * 32
            for w in t.lower().split():
                v[zlib.crc32(w.strip(".,?").encode()) % 32] += 1.0
            vecs.append(v)
        out = json.dumps({"embeddings": vecs}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


@pytest.fixture
def embed_url():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Embed)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/api/embed"
    srv.shutdown()


# --- recall hook ------------------------------------------------------------


@pytest.mark.parametrize("garbage", ["", "not json", "null", "42", "[]", '{"prompt": 7}'])
def test_recall_exits_0_and_silent_on_garbage(world, garbage):
    r = run(RECALL, garbage, world)
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_recall_injects_and_traces_lexical(world):
    r = run(RECALL, recall_payload(world), world, RECALL_TRACE=1)
    assert r.returncode == 0
    assert "reference_memory_index.md" in r.stdout
    assert "trace: branches=lexical" in r.stderr
    assert "trace: lexical ran, 1 hit" in r.stderr
    # every injection is logged for the learning loop
    fires = (world["mem"] / ".recall" / "fires.jsonl").read_text(encoding="utf-8")
    assert "reference_memory_index.md" in fires


def test_trace_is_off_by_default(world):
    r = run(RECALL, recall_payload(world), world)
    assert "trace:" not in r.stderr


def test_trivial_prompt_runs_no_branch(world):
    r = run(RECALL, recall_payload(world, "ok"), world, RECALL_TRACE=1)
    assert r.stdout.strip() == ""
    assert "no branch ran" in r.stderr


def test_absolute_floor_suppresses_weak_lexical_match(world):
    # shares only "index" with the store: 1/8 of the query terms < MIN_OVERLAP
    r = run(RECALL, recall_payload(world, "the index finger hurts after typing all day"),
            world, RECALL_TRACE=1)
    assert r.stdout.strip() == ""
    assert "lexical ran, 0 hits" in r.stderr


def test_confidence_floor_suppresses_a_demoted_memory(world):
    # same strong prompt; trust voted down to 0.31 (still >= MIN_TRUST) pushes
    # relevance*trust under MIN_INJECT -- the trust loop prunes through the floor
    (world["mem"] / ".recall").mkdir()
    (world["mem"] / ".recall" / "trust.json").write_text(
        json.dumps({"reference_memory_index.md": 0.31}), encoding="utf-8")
    r = run(RECALL, recall_payload(world), world, RECALL_TRACE=1)
    assert "reference_memory_index.md" not in r.stdout
    assert "lexical ran, 0 hits" in r.stderr


def test_corrupt_trust_store_fails_open(world):
    (world["mem"] / ".recall").mkdir()
    (world["mem"] / ".recall" / "trust.json").write_text("{not json", encoding="utf-8")
    r = run(RECALL, recall_payload(world), world, RECALL_TRACE=1)
    assert r.returncode == 0 and "reference_memory_index.md" in r.stdout
    assert "trust store unreadable" in r.stderr


# --- semantic slot ----------------------------------------------------------


def test_merge_is_one_slot_each_and_solo_is_gated(world):
    m = _load(RECALL)
    mem = world["mem"]
    lex = [{"target": "reference_memory_index.md", "content": "x", "score": 0.4,
            "trust": 0.5, "via": "lexical"},
           {"target": "other.md", "content": "y", "score": 0.35, "trust": 0.5,
            "via": "lexical"}]
    sem = [(0.70, "feedback_deploy_gate.md")] + [(0.58, f"f{i}.md") for i in range(7)]
    # lexical fired: lexical #1 + semantic #1 -- semantic can REPLACE lexical #2
    assert [h["target"] for h in m.merge(mem, lex, sem, {})] == \
        ["reference_memory_index.md", "feedback_deploy_gate.md"]
    # they agree: fall back to lexical #2
    same = [(0.70, "reference_memory_index.md")] + sem[1:]
    assert [h["target"] for h in m.merge(mem, lex, same, {})] == \
        ["reference_memory_index.md", "other.md"]
    # lexical silent: solo only past BOTH bars
    assert [h["target"] for h in m.merge(mem, [], sem, {})] == ["feedback_deploy_gate.md"]
    plateau = [(0.70, "feedback_deploy_gate.md")] + [(0.65, f"f{i}.md") for i in range(7)]
    assert m.merge(mem, [], plateau, {}) == []            # gap 0.05 < 0.10
    chatter = [(0.607, "feedback_deploy_gate.md")] + [(0.40, f"f{i}.md") for i in range(7)]
    assert m.merge(mem, [], chatter, {}) == []            # "ok lets do 1-4" territory
    # a voted-out memory cannot ride in on the semantic slot
    assert m.merge(mem, [], sem, {"feedback_deploy_gate.md": 0.1}) == []


def test_semantic_branch_runs_against_stub_embedder(world, embed_url):
    b = run(BUILD, "", world, str(world["mem"]), RECALL_EMBED_URL=embed_url)
    assert b.returncode == 0, b.stderr
    assert "indexed 2 of 2 memories" in b.stdout
    r = run(RECALL, recall_payload(world), world, RECALL_TRACE=1,
            RECALL_EMBED_URL=embed_url)
    assert r.returncode == 0
    assert "trace: branches=lexical,semantic" in r.stderr
    assert "trace: semantic ran, top=" in r.stderr
    assert "reference_memory_index.md" in r.stdout


def test_embedder_down_is_traced_not_silent(world, embed_url):
    run(BUILD, "", world, str(world["mem"]), RECALL_EMBED_URL=embed_url)
    r = run(RECALL, recall_payload(world), world, RECALL_TRACE=1,
            RECALL_EMBED_URL="http://127.0.0.1:9/api/embed")
    assert r.returncode == 0
    assert "semantic SKIPPED:" in r.stderr
    assert "reference_memory_index.md" in r.stdout        # failed OPEN to lexical


def _break_semantic(world):
    (world["mem"] / ".recall").mkdir(exist_ok=True)
    (world["mem"] / ".recall" / "semantic_index.json").write_text("{truncated",
                                                                  encoding="utf-8")


def test_broken_semantic_branch_is_skipped_and_doctor_says_degraded(world):
    """THE MUTATION-CHECKED TEST. A configured branch that raises must (a) say so
    in the trace and (b) turn the doctor's verdict from LIVE to DEGRADED -- the
    exact failure that hid in production for three weeks behind `except: pass`."""
    _break_semantic(world)
    r = run(RECALL, recall_payload(world), world, RECALL_TRACE=1)
    assert r.returncode == 0
    assert "trace: semantic SKIPPED: JSONDecodeError" in r.stderr
    assert "reference_memory_index.md" in r.stdout        # lexical still served

    register(world, "UserPromptSubmit", RECALL)
    d = doctor(world, "--probe", "recall")
    assert d.returncode == 1, d.stdout
    assert d.stdout.startswith("DEGRADED")
    assert "LIVE" not in d.stdout                         # the pack check greps for it
    assert "semantic SKIPPED" in d.stdout


def test_doctor_live_when_every_configured_branch_ran(world):
    register(world, "UserPromptSubmit", RECALL)
    d = doctor(world, "--probe", "recall")
    assert d.returncode == 0, d.stdout
    assert d.stdout.startswith("LIVE")
    assert "trace: lexical ran" in d.stdout


def test_doctor_negative_control_catches_a_hook_that_always_injects(world):
    noisy = world["tmp"] / "noisy.py"
    noisy.write_text("import json\nprint(json.dumps({'hookSpecificOutput': "
                     "{'additionalContext': 'everything is relevant'}}))\n",
                     encoding="utf-8")
    register(world, "UserPromptSubmit", noisy)
    d = doctor(world, "--probe", "recall")
    assert d.returncode == 1
    assert d.stdout.startswith("DEGRADED") and "negative control" in d.stdout


def test_doctor_dark_when_hook_is_silent(world):
    silent = world["tmp"] / "silent.py"
    silent.write_text("pass\n", encoding="utf-8")
    register(world, "UserPromptSubmit", silent)
    d = doctor(world, "--probe", "recall")
    assert d.returncode == 1 and d.stdout.startswith("DARK")


# --- identity staleness -----------------------------------------------------


def _identity(world, age_days: float):
    p = world["mem"] / "user_representation.md"
    p.write_text("---\nname: user\n---\nCurrent focus: shipping the widget.\n",
                 encoding="utf-8")
    t = time.time() - age_days * 86400
    os.utime(p, (t, t))
    return run(IDENTITY, {"cwd": str(world["proj"]), "session_id": "t"}, world)


def test_identity_injects_a_fresh_model(world):
    r = _identity(world, 0.5)
    assert r.returncode == 0 and "Current focus: shipping the widget." in r.stdout


def test_identity_suppresses_a_stale_model_with_one_line(world):
    r = _identity(world, 30)
    assert r.returncode == 0
    assert "Current focus" not in r.stdout
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1 and "SUPPRESSED" in lines[0] and "30 days old" in lines[0]


def test_doctor_reports_stale_identity_as_degraded(world):
    _identity(world, 30)
    register(world, "SessionStart", IDENTITY)
    d = doctor(world, "--probe", "identity")
    assert d.returncode == 1 and d.stdout.startswith("DEGRADED")


# --- learning loop ----------------------------------------------------------


def test_learn_probe_fails_when_precompact_hook_is_a_noop(world):
    noop = world["tmp"] / "noop.py"
    noop.write_text("import sys\nsys.stdin.read()\n", encoding="utf-8")
    register(world, "PreCompact", noop)
    d = doctor(world, "--probe", "learn")
    assert d.returncode == 1
    assert d.stdout.startswith("NO VOTE")


def test_learn_probe_fails_with_nothing_registered(world):
    (world["home"] / "settings.json").write_text('{"hooks": {}}', encoding="utf-8")
    d = doctor(world, "--probe", "learn")
    assert d.returncode == 1 and d.stdout.startswith("NO VOTE")


def test_learn_probe_passes_with_the_real_voter(world):
    register(world, "PreCompact", LEARN)
    d = doctor(world, "--probe", "learn")
    assert d.returncode == 0, d.stdout
    assert d.stdout.startswith("VOTED") and "0.50 -> 0.55" in d.stdout


def _transcript(world, turns):
    p = world["tmp"] / "t.jsonl"
    lines = []
    for user, reply in turns:
        lines.append({"type": "user", "message": {"content": user}})
        lines.append({"type": "assistant", "message": {"content": [
            {"type": "text", "text": reply}]}})
    p.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    return p


def _learn(world, transcript):
    return run(LEARN, {"cwd": str(world["proj"]), "transcript_path": str(transcript),
                       "session_id": "after-rekey"}, world, RECALL_TRACE=1)


def _trust(world):
    return json.loads((world["mem"] / ".recall" / "trust.json").read_text(encoding="utf-8"))


def test_learn_end_to_end_votes_once_and_reverts(world):
    # recall fires for real, under the pre-compaction session id
    run(RECALL, recall_payload(world), world)
    t = _transcript(world, [(GOOD_PROMPT, "Following index_v2 from the memory.")])
    r = _learn(world, t)
    assert r.returncode == 0 and "learn ran, 1 votes (1 helpful" in r.stderr
    assert _trust(world)["reference_memory_index.md"] == pytest.approx(0.55)
    # the same transcript again: every firing already scored -> no double vote
    _learn(world, t)
    assert _trust(world)["reference_memory_index.md"] == pytest.approx(0.55)
    rv = run(LEARN, "", world, "--revert", str(world["mem"]))
    assert "reverted 1 of 1" in rv.stdout
    assert _trust(world)["reference_memory_index.md"] == pytest.approx(0.5)


def test_learn_ignores_firings_with_no_real_turn(world):
    # a probe/benchmark firing whose prompt the user never typed is never scored
    run(RECALL, recall_payload(world), world)
    t = _transcript(world, [("something else entirely", "index_v2")])
    _learn(world, t)
    assert "reference_memory_index.md" not in _trust(world)


def test_learn_needs_three_ignored_firings_for_one_negative_vote(world):
    for i in range(3):
        run(RECALL, recall_payload(world, f"{GOOD_PROMPT} {i}"), world)
    turns = [(f"{GOOD_PROMPT} {i}", "unrelated reply about the weather") for i in range(3)]
    _learn(world, _transcript(world, turns))
    assert _trust(world)["reference_memory_index.md"] == pytest.approx(0.4)


# --- pack wiring ------------------------------------------------------------


def test_pack_yaml_learning_step_can_fail_and_version_bumped():
    data = yaml.safe_load((PACK / "pack.yaml").read_text(encoding="utf-8"))
    assert data["version"] == "0.2.0"
    steps = {s["id"]: s for s in data["steps"]}
    assert "--probe learn" in steps["learning-loop-votes"]["check"]["cmd"]
    assert steps["learning-loop-votes"]["check"]["cmd"] != steps["salvage-wired"]["check"]["cmd"]
    for s in data["steps"]:
        assert '"' not in (s.get("check") or {}).get("cmd", ""), "cmd.exe: no quotes"
