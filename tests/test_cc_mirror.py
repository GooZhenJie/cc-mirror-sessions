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
    monkeypatch.setattr(m, "CLAUDE_DIR", str(tmp_path / "no-claude"))
    monkeypatch.setattr(m, "LS_DIR", str(tmp_path / "no-claude" / "ls"))
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


def set_flag(fp, key, value):
    d = json.loads(fp.read_text())
    d[key] = value
    fp.write_text(json.dumps(d))


def test_pin_and_unpin_propagate(m, tmp_path, monkeypatch):
    base, proj = make_store(m, tmp_path, monkeypatch)
    (proj / "cli-1.jsonl").write_text('{"type":"custom-title","customTitle":"T"}\n')
    a = write_entry(base, "acctA", "orgA", "s1", "cli-1", "T")
    b = write_entry(base, "acctB", "orgB", "s1", "cli-1", "T")
    run_main(m, monkeypatch)

    set_flag(b, "isStarred", True)
    run_main(m, monkeypatch)
    assert json.loads(a.read_text())["isStarred"] is True

    set_flag(a, "isStarred", False)
    run_main(m, monkeypatch)
    assert json.loads(b.read_text())["isStarred"] is False


def test_pin_bootstrap_starred_anywhere_wins(m, tmp_path, monkeypatch):
    base, proj = make_store(m, tmp_path, monkeypatch)
    (proj / "cli-1.jsonl").write_text('{"type":"custom-title","customTitle":"T"}\n')
    a = write_entry(base, "acctA", "orgA", "s1", "cli-1", "T")
    b = write_entry(base, "acctB", "orgB", "s1", "cli-1", "T")
    set_flag(a, "isStarred", True)
    (tmp_path / "state.json").write_text(json.dumps({"cli-1": {"isArchived": False, "title": "T"}}))

    run_main(m, monkeypatch)
    assert json.loads(b.read_text())["isStarred"] is True
    assert json.loads(a.read_text())["isArchived"] is False


def test_progress_follows_most_recent_copy_and_account_fields_stay(m, tmp_path, monkeypatch):
    base, proj = make_store(m, tmp_path, monkeypatch)
    (proj / "cli-1.jsonl").write_text('{"type":"custom-title","customTitle":"T"}\n')
    a = write_entry(base, "acctA", "orgA", "s1", "cli-1", "T", activity=100)
    b = write_entry(base, "acctB", "orgB", "s1", "cli-1", "T", activity=200)
    set_flag(a, "remoteMcpServersConfig", ["A"])
    set_flag(a, "chromeTabGroupId", 1)
    set_flag(a, "lastFocusedAt", 5)
    set_flag(b, "completedTurns", 9)
    set_flag(b, "postTurnSummary", {"status": "done"})
    set_flag(b, "remoteMcpServersConfig", ["B"])

    run_main(m, monkeypatch)
    da = json.loads(a.read_text())
    assert da["lastActivityAt"] == 200
    assert da["completedTurns"] == 9
    assert da["postTurnSummary"] == {"status": "done"}
    assert da["remoteMcpServersConfig"] == ["A"]
    assert da["chromeTabGroupId"] == 1
    assert da["lastFocusedAt"] == 5


def test_setting_change_propagates_against_base(m, tmp_path, monkeypatch):
    base, proj = make_store(m, tmp_path, monkeypatch)
    (proj / "cli-1.jsonl").write_text('{"type":"custom-title","customTitle":"T"}\n')
    a = write_entry(base, "acctA", "orgA", "s1", "cli-1", "T", activity=100)
    b = write_entry(base, "acctB", "orgB", "s1", "cli-1", "T", activity=200)
    set_flag(a, "model", "opus")
    set_flag(b, "model", "opus")
    run_main(m, monkeypatch)

    set_flag(a, "model", "sonnet")
    run_main(m, monkeypatch)
    assert json.loads(b.read_text())["model"] == "sonnet"


def test_quiet_summary_keeps_swivel_format(m, tmp_path, monkeypatch, capsys):
    base, proj = make_store(m, tmp_path, monkeypatch)
    (proj / "cli-1.jsonl").write_text('{"type":"custom-title","customTitle":"T"}\n')
    write_entry(base, "acctA", "orgA", "s1", "cli-1", "T", activity=100)
    b = write_entry(base, "acctB", "orgB", "s1", "cli-1", "T", activity=200)
    set_flag(b, "completedTurns", 3)
    run_main(m, monkeypatch)
    line = capsys.readouterr().out.strip()
    assert line.startswith("cc-mirror-sessions: added 0,")
    assert line.endswith("state-synced 1, pin-list 0")


def make_claude_dir(tmp_path, acct, starred, order=None, running=False):
    cdir = tmp_path / "claude"
    ldir = cdir / "Local Storage" / "leveldb"
    ldir.mkdir(parents=True)
    (ldir / "LOCK").write_text("")
    (cdir / "config.json").write_text(json.dumps({"lastKnownAccountUuid": acct}))
    prefs = {"other": {"keep": "me"}, "starred-local-code-sessions": starred}
    if order is not None:
        prefs["dframe-local-slice"] = {"pinnedOrder": order, "x": 1}
    cfg = {"deploymentMode": "1p", "preferences": {"menuBarEnabled": False, "epitaxyPrefs": prefs}}
    (cdir / "claude_desktop_config.json").write_text(json.dumps(cfg, indent=2))
    return cdir


def prefs_of(cdir):
    return json.loads((cdir / "claude_desktop_config.json").read_text())["preferences"]


def test_pin_list_follows_index(m, tmp_path, monkeypatch):
    base, _ = make_store(m, tmp_path, monkeypatch)
    a = write_entry(base, "acctA", "orgA", "s1", "cli-1", "T")
    write_entry(base, "acctA", "orgA", "s2", "cli-2", "T")
    set_flag(a, "isStarred", True)
    cdir = make_claude_dir(tmp_path, "acctA", ["local_s2", "local_gone"],
                           order=["code:local_s2", "cowork:x"])
    folders = m.discover_folders([])

    assert m.sync_starred_list(folders, True, claude_dir=str(cdir)) == 1
    assert prefs_of(cdir)["epitaxyPrefs"]["starred-local-code-sessions"] == ["local_s2", "local_gone"]

    assert m.sync_starred_list(folders, False, claude_dir=str(cdir)) == 1
    p = prefs_of(cdir)
    assert p["epitaxyPrefs"]["starred-local-code-sessions"] == ["local_gone", "local_s1"]
    assert p["epitaxyPrefs"]["dframe-local-slice"] == {
        "pinnedOrder": ["code:local_s2", "cowork:x", "code:local_gone", "code:local_s1"], "x": 1}
    assert p["epitaxyPrefs"]["other"] == {"keep": "me"}
    assert p["menuBarEnabled"] is False
    assert m.sync_starred_list(folders, False, claude_dir=str(cdir)) == 0


def test_pin_list_skips_when_claude_running(m, tmp_path, monkeypatch):
    import subprocess
    base, _ = make_store(m, tmp_path, monkeypatch)
    a = write_entry(base, "acctA", "orgA", "s1", "cli-1", "T")
    set_flag(a, "isStarred", True)
    cdir = make_claude_dir(tmp_path, "acctA", [])
    lock = cdir / "Local Storage" / "leveldb" / "LOCK"
    holder = subprocess.Popen([sys.executable, "-c",
                               "import fcntl,os,sys,time;fd=os.open(sys.argv[1],os.O_RDWR);"
                               "fcntl.lockf(fd,fcntl.LOCK_EX);print('x',flush=True);time.sleep(30)",
                               str(lock)], stdout=subprocess.PIPE)
    try:
        holder.stdout.readline()
        assert m.sync_starred_list(m.discover_folders([]), False, claude_dir=str(cdir)) == 0
        assert prefs_of(cdir)["epitaxyPrefs"]["starred-local-code-sessions"] == []
    finally:
        holder.kill()


def test_pin_list_leaves_other_account_alone(m, tmp_path, monkeypatch):
    base, _ = make_store(m, tmp_path, monkeypatch)
    a = write_entry(base, "acctA", "orgA", "s1", "cli-1", "T")
    set_flag(a, "isStarred", True)
    cdir = make_claude_dir(tmp_path, "acctB", [])
    assert m.sync_starred_list(m.discover_folders([]), False, claude_dir=str(cdir)) == 0
