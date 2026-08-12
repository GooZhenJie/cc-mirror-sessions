# cc-mirror-sessions

Make every Claude account on your Mac share one combined Claude Code sidebar — sessions, names, and archive status included.

## The problem

The Claude desktop app scopes its Code-tab sidebar to the currently logged-in account. Each session gets a small index file at:

```
~/Library/Application Support/Claude/claude-code-sessions/<accountUuid>/<orgUuid>/local_<id>.json
```

while the actual conversation transcript lives in the account-agnostic store at `~/.claude/projects/<cwd>/<cliSessionId>.jsonl`. Switch logins and your history "disappears" — the transcripts are all still on disk, but the sidebar only reads the new account's index folder. Renames and archive flags live inside each per-account index file too, so they also fail to follow you across accounts.

This is a long-standing, unresolved gap — see [anthropics/claude-code#48511](https://github.com/anthropics/claude-code/issues/48511) (closed "not planned"), [#85794](https://github.com/anthropics/claude-code/issues/85794), [#85209](https://github.com/anthropics/claude-code/issues/85209), [#72438](https://github.com/anthropics/claude-code/issues/72438), [#85083](https://github.com/anthropics/claude-code/issues/85083), and [#43786](https://github.com/anthropics/claude-code/issues/43786).

## What it does

One stdlib-only Python script, safe to run every minute from launchd:

1. **Mirrors** every openable session (one whose transcript exists on disk) into every account's index folder, so each login shows the full combined sidebar.
2. **Repairs** stale copies frozen with an empty `cliSessionId` (they render as "no messages").
3. **Revives** dead sessions — if you keep a raw-transcript backup, a session whose transcript Claude Code pruned is restored from the archive before mirroring (creation-only, idempotent).
4. **Syncs archive status and titles** across all copies of a session. A sidecar (`~/.claude/cc-mirror-state.json`) remembers each session's last-synced values; a copy that differs from that base is a user action, and the *change* wins — archive and un-archive both propagate. No mtime guessing (the app rewrites index files on mere focus).
5. **Anchors titles to the transcript.** The app appends a `{"type": "custom-title"}` record to the transcript on every (re)title, so the transcript's last record is the newest intended name — account-agnostic, append-only, and written even when the index write is lost or skipped (the [#85794](https://github.com/anthropics/claude-code/issues/85794) regression class stopped index writes entirely for a stretch of builds). A change in that record since the last sync is stamped across every index copy, so **session names persist across accounts even if no index file ever caught the rename**.

It never deletes anything by default. The only deleting mode, `--prune`, is opt-in and only removes spread copies of dead (transcript-less) sessions, keeping one in your designated home account.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/MaxGhenis/cc-mirror-sessions/main/cc-mirror-sessions -o ~/bin/cc-mirror-sessions
chmod +x ~/bin/cc-mirror-sessions
```

Optional per-user settings in `~/.claude/cc-mirror.json` (so the launchd job needs no CLI arguments):

```json
{
  "dead_home": "<orgUuid to park dead sessions in>",
  "archive": "~/my-transcript-backups/**/*.jsonl",
  "exclude": ["<accountUuid-or-orgUuid to skip>"]
}
```

Both keys are optional: with no `archive` the revive step is skipped; with no `dead_home`, `--prune` keeps the first copy it finds.

To run it every 60 seconds, copy [`com.example.cc-mirror-sessions.plist`](com.example.cc-mirror-sessions.plist) to `~/Library/LaunchAgents/`, replace `YOUR_USERNAME`, and:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.cc-mirror-sessions.plist
```

## Usage

```
cc-mirror-sessions            # sync now: add missing + repair stale copies
cc-mirror-sessions --list     # per-account openable/dead counts, change nothing
cc-mirror-sessions --dry-run  # show what would change
cc-mirror-sessions --quiet    # one-line summary (for launchd)
cc-mirror-sessions --prune    # also remove spread copies of dead sessions
cc-mirror-sessions --no-flag-sync   # skip archive/title propagation
cc-mirror-sessions --no-restore     # skip reviving from the archive
```

## Caveats

- **The running app won't show changes until it reloads.** The desktop app reads the index folder only at launch or account switch; there is no way to make a running app re-scan (verified: external writes to index files trigger nothing, and the app's own session-management MCP can't see unloaded entries). Sessions and renames synced from another account appear at the next app restart.
- Avoid the app's "Clear Cache & Restart" repair — users report it makes session-list problems worse ([#85794](https://github.com/anthropics/claude-code/issues/85794) triage notes).
- A session's stable identity is its index **filename**, not its `cliSessionId` — filenames are *not* unique across accounts, so on collision the tool writes a `cli`-derived filename instead of clobbering.
- Back up `~/Library/Application Support/Claude/claude-code-sessions/` before first run if you're nervous. The tool itself never deletes outside `--prune`.
- Unofficial tool, tested on macOS. It only touches Claude's local session-index JSON files and (for revive) `~/.claude/projects/`.

Tip: raise `"cleanupPeriodDays"` in `~/.claude/settings.json` so Claude Code stops pruning transcripts after 30 days — pruned transcripts are why sessions go "dead" in the first place.

## Tests

```bash
uvx pytest
```

Covers the transcript-title parser, config loading, and end-to-end integration: mirroring across accounts, rename propagation, the transcript-anchored repair of a rename every index copy missed, and archive-flag round-trips.

## License

MIT
