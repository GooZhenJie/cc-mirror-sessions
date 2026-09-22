# CLAUDE.md — cc-mirror-sessions (GooZhenJie fork)

Guidance for agents working in this checkout. Read this before touching anything.

## What this checkout is

A fork of [MaxGhenis/cc-mirror-sessions](https://github.com/MaxGhenis/cc-mirror-sessions): one
stdlib-only Python script that copies Claude Desktop's Code-sidebar session index into every
account's folder, so each signed-in account lists the same sessions.

| Remote | URL | Push |
|---|---|---|
| `upstream` | MaxGhenis/cc-mirror-sessions | **disabled** (`set-url --push DISABLED`) |
| `origin` | GooZhenJie/cc-mirror-sessions | allowed |

**This clone is for tracking upstream and reviewing diffs. It is not what runs.** The executed copy
is `~/bin/cc-mirror-sessions` (internal disk, so it survives the T9 drive being unplugged). Editing
the file here changes nothing until it is copied over.

## Who calls it

The owner's Swivel fork (`/Volumes/T9/Documents/www/Swivel`, branch
`feature/auto-mirror-on-switch`) runs `~/bin/cc-mirror-sessions --quiet` on every account switch,
via `/usr/bin/python3`, while Claude Desktop is quit, with a 30s timeout.

Consequences for any change here:

- **Must stay compatible with Python 3.9.** `/usr/bin/python3` is 3.9.6 and a GUI app gets no
  pyenv/homebrew PATH. No `match`, no `X | Y` annotations at runtime.
- **Must stay fast** (well under 30s) and must not prompt or wait on input.
- **Must keep the `--quiet` one-line summary format** (`cc-mirror-sessions: added N, repaired N, …`).
  Swivel parses it for the popover row; it prints nothing when nothing changed.

## How it works, and the local facts

Session data is split in two:

```
transcript       ~/.claude/projects/<slug>/<cliSessionId>.jsonl          account-agnostic, shared
sidebar index    ~/Library/Application Support/Claude/claude-code-sessions/<account>/<org>/local_*.json
```

Only the index is per-account, which is why switching accounts empties the sidebar. This script
copies index entries; transcripts are never written except by the opt-in revive step.

Accounts on this machine:

| Account | Claude Usage / Swivel name | Org | Sessions |
|---|---|---|---|
| `5c426f7a…` | Personal (`goozhenjie5@gmail.com`) | `379bc3cc…` | a handful |
| `79f05c82…` | RAS (`goo.jie@racingandsports.com`) | `55b9ad9e…` | ~350, of which ~279 openable |

The ~70 non-openable ones had their transcripts pruned by Claude Code's 30-day cleanup and cannot be
recovered by any tool. Raising `cleanupPeriodDays` in `~/.claude/settings.json` prevents more of it —
that is the owner's file, so suggest it, do not edit it.

The owner's work history lives on the **RAS** account and is the important data here.

## Safety rules

- **Never pass `--prune`** unless the owner asks for it in that same request. It is the only mode
  that deletes, and the default run deletes nothing.
- A backup of the index directory exists at `~/claude-code-sessions.bak-20260921`. To restore: quit
  Claude Desktop, then copy it back over
  `~/Library/Application Support/Claude/claude-code-sessions`.
- Claude Desktop reads the index **only at launch or on account switch**. Changes are invisible until
  it restarts, and restarting it closes the owner's current Claude Code conversation. Say so before
  asking for a restart.
- Do not run it against a different `HOME` or a staging/remote machine. It is local-only by design.
- Continuing an RAS session while signed into Personal sends company context under the personal
  account. The owner accepted this tradeoff; do not silently widen it (e.g. by adding automation that
  moves sessions around on its own).

## Updating from upstream

Do not blind-pull. This script runs against the owner's real session index, so the diff gets read
first:

```bash
git fetch upstream && git log --oneline HEAD..upstream/main
git diff HEAD upstream/main -- cc-mirror-sessions
```

Review the diff for: new delete paths, new network calls, new subprocess use, 3.10+ syntax, changes
to the `--quiet` output format. Report what changed and wait for approval. Only then:

```bash
git rebase upstream/main
cp cc-mirror-sessions ~/bin/cc-mirror-sessions
```

`main` here carries this doc commit on top of upstream, so update with `rebase`, not
`merge --ff-only`. **The `cp` is required** — skipping it means the update did not take effect.

Prefer configuration (`~/.claude/cc-mirror.json`) or a wrapper over editing the vendored script;
local edits to it make every future rebase harder.

## House rules that apply here

- No AI attribution in commit messages, no `Co-Authored-By: Claude`.
- Commit messages follow Conventional Commits per
  `/Volumes/T9/Documents/www/rasa-projects/.cursorrules`; read that file before writing one.
- No code comments unless the owner explicitly asks.
- On a rebase conflict: stop, report both sides, let the owner decide.

## Related

`/Volumes/T9/Documents/www/Swivel/CLAUDE.md` — the fork that invokes this script, and where the
switch-time integration is documented.
