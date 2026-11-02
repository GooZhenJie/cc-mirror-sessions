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

## Local changes to the script (2026-09-24)

The fork carries its own edits to step 1.6 of `cc-mirror-sessions`, because upstream only synced
`isArchived` and `title`. The symptom was: pin a session in one account, switch accounts, and the
session followed but the pin did not. Upstream only copies an index file the **first** time a
session reaches an account, so any later change to a field that step 1.6 did not handle stayed
stuck in that one account.

What step 1.6 now syncs, and how:

| Group | Fields | Rule |
|---|---|---|
| Flags | `isArchived`, `isStarred` (= **pin**) | Change-vs-base via the state file; with no base, true-anywhere wins |
| Title | `title`, `titleSource` + transcript `custom-title` | Upstream logic, unchanged |
| Progress (`PROGRESS_KEYS`) | `lastActivityAt`, `completedTurns`, `latestUserFrameAt`, `lastAssistantUuid`, `postTurnSummary`, `postTurnSummaryFor`, `titleTurn`, `previousTitles`, `writtenBranches`, `publishedArtifacts` | Copied as a bundle from the copy with the newest `lastActivityAt`; no base needed |
| Settings (`SETTING_KEYS`) | `model`, `effort`, `permissionMode`, `chromePermissionMode`, `sessionSettings`, `classifierSummaryEnabled`, `alwaysAllowedReasons`, `sessionPermissionUpdates`, `resolvedBackgroundTaskSuggestions` | Change-vs-base by value hash (state file `settings` map); with no base, most recently active copy wins |

Deliberately **not** synced — they are per account or per app run, and copying them would be wrong:
`remoteMcpServersConfig`, `toolSurfaceSnapshot`, `promptAppendSnapshot` (differ by account's
connectors), `chromeTabGroupId`, `lastFocusedAt`, `steeredByRemoteClient`, `spawnSeed`, `envScopeId`.

When a new field shows up in index files, decide which group it belongs to before adding it. To see
which fields actually differ between copies of the same session, group every
`local_*.json` by `cliSessionId` and compare values per key (read-only). Syncing everything by
copying the whole newest file is wrong — it would overwrite the account-specific fields above.

The `--quiet` summary gained trailing `state-synced N`, `pin-list N` and `pin-seeded N` items. Swivel splits the line on commas and
shows every `name N` part with N > 0, so appending items is safe; renaming or reordering existing
ones is not.

### Sidebar pins: where they really live (re-established 2026-10-07)

The sidebar pin state has **three copies plus one ignored flag**. Only the first is read at launch:

| # | Store | Location (per account, inside the Claude folder Swivel swaps) | Role |
|---|---|---|---|
| 1 | IndexedDB | `IndexedDB/https_claude.ai_0.indexeddb.leveldb`, object store `pin-state`, key `dframe-starred-code`, value `{"state":{"starredIds":[...]},"version":0,"updatedAt":ms}` | **Source of truth.** The renderer hydrates from it at launch |
| 2 | localStorage | `Local Storage/leveldb`, keys `LSS-persisted.starred-local-code-sessions` (`{"value":[...],"tabId":"","timestamp":ms}`), `LSS-persisted.dframe-local-slice` (`value.pinnedOrder`), `dframe-store` (`state.pinnedOrder`) | Cache, rewritten from #1 about 1.5–6 s after launch. Order lives only here and in #3 |
| 3 | config | `claude_desktop_config.json` → `preferences.epitaxyPrefs["starred-local-code-sessions"]` and `["dframe-local-slice"].pinnedOrder` | Mirror of #2, rewritten right after it |
| – | index | `isStarred` in each `local_*.json` | Written on pin, often **not** cleared on unpin; never read for the sidebar |

Swivel snapshots and restores the whole Claude folder per profile except `claude-code-sessions`
and caches, so #1–#3 are **per account** while the index folders are shared on disk.

Membership is #1; `pinnedOrder` only orders it and may hold stale or non-code entries (normal).
The sidebar also applies its own "last activity" filter (`code-sessions-state-activity-days.<acct>`)
to the Pinned section, so a correct pin can be hidden. Compare data, not the screenshot alone.

#### How the script keeps pins in step (two parts)

1. **Seed from the outgoing account** (`outgoing_pin_list` + `seed_starred_from_list`, before
   step 1). Only when this run is the switch Swivel just made: `Swivel/state.json` was written
   within `SWIVEL_RUN_WINDOW` (30 s = Swivel's own timeout for this script, `SessionMirror.swift`
   `defaultTimeout`), Claude is quit, and the saved profile's account differs from the live one.
   It reads the outgoing account's real list (IndexedDB, else localStorage, else config) from
   `Swivel/profiles/<previousProfile>/Claude/`, and sets that account's `isStarred` to match.
   Step 1.6 then propagates the change by change-vs-base. A stale snapshot is never used, because
   it would undo pins made since. Summary item: `pin-seeded N`.
2. **Write the target account** (`sync_starred_list`, after step 1.6): computes the list from
   `isStarred`, then writes it to all three stores — config (JSON rewrite as before),
   localStorage (`sync_local_storage_pins`) and IndexedDB (`sync_idb_pins`). `pinnedOrder` is
   append-only. Summary item: `pin-list N`.

LevelDB writes (`ls_append_batch`): one WriteBatch appended to the newest `*.log`, sequence =
max(every record seq, MANIFEST last sequence) + 1, 32 KiB block framing, masked CRC32C, under an
exclusive `lockf` on that DB's `LOCK` (Claude holds it while running, so a running app means no
write). The IndexedDB value keeps the record's own version varint and Blink/V8 envelope bytes and
replaces only the JSON string; re-encoding the two real records reproduced them byte for byte.
IndexedDB uses Chromium's `idb_cmp1` comparator, so stock LevelDB libraries cannot open it; the
localStorage path was checked with `classic-level` instead (keys unchanged, values read back,
46 block-boundary crossings).

#### Dead ends, in order — do not repeat them

| Date | Assumption | What actually happened |
|---|---|---|
| 09-24 | Sync `isStarred` | App ignores it; the other account launched with its old pins |
| 09-24 | Write localStorage | Overwritten 1.2 s after launch; wrongly concluded config was the source and removed the writer |
| 09-24 → 10-07 | Config is the source | Script wrote config, app overwrote it from localStorage ~2 s after launch |
| 10-07 | localStorage + config | Both written and confirmed, app restored the old list ~6 s after launch from **IndexedDB** |
| 10-07 | All three stores | Works: after launch the app re-saved the synced list itself |

The common mistake: verifying that the **write** landed instead of what the app holds **after it
launches**. "Written" proves nothing here; every wrong turn above had a successful write.

#### How to debug a pin that does not follow

1. `tools/pin-watch --detach` (log: `~/Library/Logs/cc-mirror-pin-watch.log`) samples every
   0.2 s and logs any change in: Claude running, account, Swivel state, mirror summary, config
   lists, localStorage lists, IndexedDB list. Start it, let the owner do a round-trip switch
   without touching pins, then read the timeline: who wrote which value, and when after launch.
   `tools/pin-watch --once` prints the current state.
2. If the app restores a value that none of the watched stores held, search every store in the
   profile snapshot for a distinctive run of ids (all LevelDB dirs under the Claude folder, parse
   `.log` and `.ldb`; values may be UTF-16 or snappy-compressed). That is how #1 was found.
3. `tools/simulate-switch --round-trip [--script PATH]` replays Swivel's restore + this script in
   a sandbox (`HOME` pointed at a temp copy, including both profiles' localStorage and
   IndexedDB) and checks config, localStorage and IndexedDB. It must fail on the old version for
   the reason seen in reality before a fix is trusted. It cannot simulate what the app does after
   launch; only a real switch with `pin-watch` running proves that.

### Other Claude Desktop state

- Other localStorage keys: `epitaxy-folder-permission-mode.<accountUuid>` (per-account folder
  permission mode), `starred-session-groups`, `dframe-group-scopes` (sidebar groups; empty today).
  Not synced. Other `pin-state` IndexedDB keys (`dframe-session-groups`,
  `dframe-pinned-project-outputs`, `dframe-starred-cowork-remote`, …) are not synced either.
- `local-agent-mode-sessions/<account>/<org>/` is Cowork, not Claude Code; out of scope.

### Scheduled tasks (added 2026-11-02)

Local scheduled tasks are split like sessions: the prompt lives once in
`~/.claude/scheduled-tasks/<id>/SKILL.md` (shared), while the schedule, on/off switch and last-run
record live per account in `claude-code-sessions/<account>/<org>/scheduled-tasks.json`. The app
reads that file only at launch and rewrites it from memory, so only a quit app can be written.

On a Swivel switch, `swivel_switch()` (the same freshness, quit-app and outgoing-account checks the
pin seeding uses) hands the outgoing and incoming account to `sync_scheduled_tasks()`, which loads
`~/bin/claude-scheduled-tasks-sync` and calls its `switch_sync()`. That copies the outgoing
account's tasks and last-run records into the incoming account, so whichever account is open runs a
task and the other one does not run the same slot again. A task is removed from the incoming
account only if the outgoing one deleted it since the last sync.

- The sync script is not part of this repo. Its source and rules are the agent-configs skill
  `claude-desktop-scheduled-tasks-sync`
  (`/Volumes/T9/Documents/www/agent-configs/shared/common/skills/claude-desktop-scheduled-tasks-sync/`);
  `~/bin/claude-scheduled-tasks-sync` is a copy of its `sync_scheduled_tasks.py`.
- Missing script: the step is skipped. Any error: caught, counted as `tasks-sync-failed 1`, and the
  rest of the run goes on. Summary items: `tasks-synced N`, `tasks-sync-failed N`.
- Log: `~/Library/Logs/claude-scheduled-tasks-sync.log`. Opt out: `--no-task-sync`.
- Cloud routines (Scheduled cards without "Only on this computer") are per account on Anthropic's
  side and are not touched.
- Verified with a real round-trip switch on 2026-11-02: each direction carried its new tasks and the
  Scheduled list matched in both accounts.

### After editing the script

1. Tests on the Python that actually runs it:
   `~/.local/bin/uvx --python /usr/bin/python3 pytest -q tests` and
   `/usr/bin/python3 -m py_compile cc-mirror-sessions`
2. `/usr/bin/python3 cc-mirror-sessions --dry-run` against the real store — read-only, safe while
   Claude Desktop is open. Check the counts are plausible and the run takes well under 30s.
3. For anything touching pins: `tools/simulate-switch --round-trip --script ./cc-mirror-sessions`.
4. Back up first: both profiles' `IndexedDB/https_claude.ai_0.indexeddb.leveldb`,
   `Local Storage/leveldb` and `claude_desktop_config.json` into `~/.claude/backups/`.
5. `cp cc-mirror-sessions ~/bin/cc-mirror-sessions` — **Swivel never reads this clone**; without the
   copy nothing changes. There is exactly one installed copy and no launchd job.
6. Do **not** run the real sync while Claude Desktop is open (it rewrites these files on focus), and
   never quit Claude Desktop yourself. The real run happens on the owner's next Swivel switch.
7. Verification is a real round-trip switch with `pin-watch` running: the values must still be the
   synced ones after each app launch, not just after the script.

Backups: `~/claude-code-sessions.bak-20260924` (index folder plus `cc-mirror-state.json`);
`~/.claude/backups/pin-stores-20261007-105628/` (both profiles' IndexedDB, localStorage, config
before the IndexedDB writer was installed); `~/.claude/backups/cc-mirror-sessions.before-pin-seed-20261007`
(script before the 2026-10-07 changes).

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
local edits to it make every future rebase harder. The step 1.6 edits above are the exception and
are the conflict-prone spot: if upstream touches the `isArchived` block, the `rec = {...}` line or
the summary line, stop and report both sides.

## House rules that apply here

- Agents commit and push their own changes here without asking (owner, 2026-11-02: "same as
  agent-configs, managed by agents from now on"). Rules: agent-configs
  `shared/common/rules/agent-configs-auto-commit.mdc`. Write every git call as
  `git -C /Volumes/T9/Documents/www/cc-mirror-sessions <subcommand>`, one per Bash call; push to
  `origin main` only; never force-push. Merging upstream and running `--prune` still need the
  owner's approval (see above). A pushed script is not live until it is copied to `~/bin`.
- No AI attribution in commit messages, no `Co-Authored-By: Claude`.
- Commit messages follow Conventional Commits per
  `/Volumes/T9/Documents/www/rasa-projects/.cursorrules`; read that file before writing one.
- No code comments unless the owner explicitly asks.
- On a rebase conflict: stop, report both sides, let the owner decide.

## Related

`/Volumes/T9/Documents/www/Swivel/CLAUDE.md` — the fork that invokes this script, and where the
switch-time integration is documented.
