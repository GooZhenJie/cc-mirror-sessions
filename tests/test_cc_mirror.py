"""Tests for cc-mirror-sessions.

Run from the repo root:  uvx pytest  (or: python3 -m pytest tests/)
"""
import importlib.machinery
import importlib.util
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "cc-mirror-sessions")


def load_module():
    loader = importlib.machinery.SourceFileLoader("ccm", SCRIPT)
    spec = importlib.util.spec_from_loader("ccm", loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


@pytest.fixture()
def m():
    return load_module()


# ---------------------------------------------------------------- unit tests

def test_slug(m):
    assert m.slug("/Users/alice/dev/my repo") == "-Users-alice-dev-my-repo"
    assert m.slug("/a/b.c_d") == "-a-b-c-d"


def test_transcript_title_last_record_wins(m, tmp_path):
    t = tmp_path / "abc.jsonl"
    t.write_text(
        '{"type":"custom-title","customTitle":"First name"}\n'
        '{"type":"user","text":"hello"}\n'
        '{"type":"custom-title","customTitle":"Second name"}\n'
        '{"type":"assistant","text":"world"}\n'
    )
    assert m.transcript_title(str(t)) == "Second name"


def test_transcript_title_ignores_lookalikes_and_corruption(m, tmp_path):
    t = tmp_path / "abc.jsonl"
    t.write_text(
        '{"type":"custom-title","customTitle":"Real"}\n'
        '{"type":"user","text":"mentions \\"custom-title\\" in prose"}\n'
        'not json at all "custom-title"\n'
        '{"type":"other","customTitle":"wrong type","note":"custom-title"}\n'
    )
    assert m.transcript_title(str(t)) == "Real"


def test_transcript_title_none_when_absent(m, tmp_path):
    t = tmp_path / "abc.jsonl"
    t.write_text('{"type":"user","text":"hi"}\n')
    assert m.transcript_title(str(t)) is None
    assert m.transcript_title(str(tmp_path / "missing.jsonl")) is None


def test_transcript_title_window_no_signal(m, tmp_path):
    # A record pushed beyond the tail window is a no-signal (None), not a change.
    t = tmp_path / "abc.jsonl"
    filler = json.dumps({"type": "user", "text": "x" * 1000}) + "\n"
    t.write_text('{"type":"custom-title","customTitle":"Old"}\n' + filler * 300)
    assert m.transcript_title(str(t), window=4096) is None


def test_archive_index_largest_snapshot_wins(m, tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    small = tmp_path / "a" / "s1.jsonl"
    big = tmp_path / "b" / "s1.jsonl"
    small.write_text("x")
    big.write_text("x" * 100)
    idx = m.archive_index(str(tmp_path / "**" / "*.jsonl"))
    assert idx["s1"] == str(big)


def test_load_config(m, tmp_path):
    cfg = tmp_path / "cc-mirror.json"
    cfg.write_text('{"dead_home": "org-1", "archive": "~/arch/**/*.jsonl"}')
    assert m.load_config(str(cfg))["dead_home"] == "org-1"
    assert m.load_config(str(tmp_path / "missing.json")) == {}
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2]")
    assert m.load_config(str(bad)) == {}


# -------------------------------------------------------- integration tests

def make_store(m, tmp_path, monkeypatch):
    """Point the module at a synthetic HOME-ish layout."""
    base = tmp_path / "store"
    proj = tmp_path / "projects" / "-work-repo"
    proj.mkdir(parents=True)
    monkeypatch.setattr(m, "BASE", str(base))
    monkeypatch.setattr(m, "PROJ", str(tmp_path / "projects"))
    monkeypatch.setattr(m, "STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(m, "LOCKFILE", str(tmp_path / "lock"))
    monkeypatch.setattr(m, "CONFIG", str(tmp_path / "no-config.json"))
    return base, proj


def write_entry(base, acct, org, sid, cli, title, archived=False, activity=100):
    d = base / acct / org
    d.mkdir(parents=True, exist_ok=True)
    fp = d / f"local_{sid}.json"
    fp.write_text(json.dumps({
        "sessionId": f"local_{sid}",
        "cliSessionId": cli,
        "cwd": "/work/repo",
        "createdAt": 1,
        "lastActivityAt": activity,
        "isArchived": archived,
        "title": title,
        "titleSource": "auto",
    }))
    return fp


def run_main(m, monkeypatch, argv=("--quiet",)):
    monkeypatch.setattr(sys, "argv", ["cc-mirror-sessions", *argv])
    assert m.main() == 0


def test_mirror_spreads_sessions_and_syncs_rename(m, tmp_path, monkeypatch, capsys):
    base, proj = make_store(m, tmp_path, monkeypatch)
    (proj / "cli-1.jsonl").write_text('{"type":"custom-title","customTitle":"Fix login bug"}\n')
    write_entry(base, "acctA", "orgA", "s1", "cli-1", "Fix login bug")
    (base / "acctB" / "orgB").mkdir(parents=True)

    run_main(m, monkeypatch)
    copy = json.loads((base / "acctB" / "orgB" / "local_s1.json").read_text())
    assert copy["title"] == "Fix login bug"

    # Rename lands in ONE account's index (as the app does), then propagates.
    write_entry(base, "acctA", "orgA", "s1", "cli-1", "Login bug RCA", activity=200)
    run_main(m, monkeypatch)
    copy = json.loads((base / "acctB" / "orgB" / "local_s1.json").read_text())
    assert copy["title"] == "Login bug RCA"


def test_transcript_anchor_repairs_lost_rename(m, tmp_path, monkeypatch):
    base, proj = make_store(m, tmp_path, monkeypatch)
    t = proj / "cli-1.jsonl"
    t.write_text('{"type":"custom-title","customTitle":"Old name"}\n')
    write_entry(base, "acctA", "orgA", "s1", "cli-1", "Old name")
    write_entry(base, "acctB", "orgB", "s1", "cli-1", "Old name")
    run_main(m, monkeypatch)  # bootstrap records base ttitle/tmt

    # The app records a rename ONLY in the transcript — every index copy misses it
    # (the anthropics/claude-code#85794 failure class).
    with open(t, "a") as f:
        f.write('{"type":"custom-title","customTitle":"New name"}\n')
    os.utime(t, (os.path.getmtime(t) + 5,) * 2)

    run_main(m, monkeypatch)
    for acct, org in (("acctA", "orgA"), ("acctB", "orgB")):
        copy = json.loads((base / acct / org / "local_s1.json").read_text())
        assert copy["title"] == "New name", f"{acct}/{org} kept the lost title"

    state = json.loads((tmp_path / "state.json").read_text())
    assert state["cli-1"]["ttitle"] == "New name"


def test_archive_flip_propagates(m, tmp_path, monkeypatch):
    base, proj = make_store(m, tmp_path, monkeypatch)
    (proj / "cli-1.jsonl").write_text('{"type":"custom-title","customTitle":"T"}\n')
    write_entry(base, "acctA", "orgA", "s1", "cli-1", "T")
    write_entry(base, "acctB", "orgB", "s1", "cli-1", "T")
    run_main(m, monkeypatch)  # record base (unarchived)

    write_entry(base, "acctA", "orgA", "s1", "cli-1", "T", archived=True)
    run_main(m, monkeypatch)
    copy = json.loads((base / "acctB" / "orgB" / "local_s1.json").read_text())
    assert copy["isArchived"] is True
