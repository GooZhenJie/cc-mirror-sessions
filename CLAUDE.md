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
  permission mode), `starred-session-groups`, `dframe-group-scopes` (local-only part of custom groups),
  `dframe-store.state.customGroupsByScope` (custom groups and their session assignments; the group list is
  carried on a switch, see "Sidebar carry on a switch" below). The built-in sections' view settings are not carried (see "Sidebar view" below). Other `pin-state` IndexedDB keys (`dframe-session-groups`,
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
  (`/Volumes/T9/Documents/www/confstack-data/shared/common/skills/claude-desktop-scheduled-tasks-sync/`);
  `~/bin/claude-scheduled-tasks-sync` is a copy of its `sync_scheduled_tasks.py`.
- Missing script: the step is skipped. Any error: caught, counted as `tasks-sync-failed 1`, and the
  rest of the run goes on. Summary items: `tasks-synced N`, `tasks-sync-failed N`.
- Log: `~/Library/Logs/claude-scheduled-tasks-sync.log`. Opt out: `--no-task-sync`.
- Cloud routines (Scheduled cards without "Only on this computer") are per account on Anthropic's
  side and are not touched.
- Verified with a real round-trip switch on 2026-11-02: each direction carried its new tasks and the
  Scheduled list matched in both accounts.

### Sidebar view: server-side, cannot be synced from here (established 2026-11-15)

The sidebar's view settings (Sessions grouped by folder / date / state, sort order, shown and
collapsed state of each section) are per account, keyed by scope `<account>/<org>`. Three local
copies exist inside the Claude folder Swivel swaps:

| # | Store | Location |
|---|---|---|
| 1 | localStorage | `dframe-store` → `state.codeSidebarByScope[scope]` |
| 2 | localStorage | `LSS-persisted.dframe-code-sections` → `value[scope]` |
| 3 | config | `claude_desktop_config.json` → `preferences.epitaxyPrefs["dframe-code-sections"][scope]` |

Value shape: `{"sections": [...], "migratedFrom": 1, "prefsSeeded": true}`; built-in sections
`pinned`, `routines`, `sessions`, a missing `groupBy` means none, custom groups add `kind: "manual"`
sections. `dframe-store.state.groupByByMode` is a pre-migration leftover and is not used.

**None of the three is the source.** About 3 s after launch the app replaces all three with the
account's own value, which it does not read from any local file. Evidence (pin-watch log,
2026-11-15 19:25): the RAS snapshot was staged with config = none, store 2 = date, store 1 = state;
after the switch the app showed folder and rewrote config at +2.7 s and both localStorage keys at
+5.3 s to folder, a value no local copy held. Searched and ruled out: every LevelDB under the Claude
folder (incl. IndexedDB and the decompressed react-query-cache blob), `Partitions`, `WebStorage`,
the preferences plist, other JSON files in the Claude folder, and shared locations outside it
(`~/.claude`, `~/.claude.json`, `~/Library/Preferences`). It differs per account and is not in the
swapped folder, so it is held by Anthropic per account.

What this covers: only the built-in sections' view fields (`groupBy`, `sortBy`, `ascending`, `show`,
`collapsed`, `shown`). e2b7484 deliberately left custom (`kind: "manual"`) sections alone, so this test
says nothing about them; they were tested separately on 2026-11-20 and are server-side too, see "Sidebar carry on a switch" below.
The app's code confirms the view part: `groupByByMode`, `sortByByMode` and `sidebarSections` are wire keys of the
server-synced sidebar store (same evidence as below).

Consequences:

- Each account keeps its own view by itself, independent of Swivel; set it once in each account.
- Copying it on a switch cannot work; a write to all three stores was tried (e2b7484, reverted) and
  the app put the account's value back on launch. Do not retry it.
- `tools/pin-watch` logs the three copies (`cfg.view`, `ls.sections.view`, `ls.store.view`) if this
  needs re-checking after an app update.
- The pending-upload marker described in "Sidebar carry on a switch" makes the local copy win at launch, so
  the view could now be carried the same way. It is not: it was not part of the owner's 2026-11-20
  decisions (on that day all three accounts grouped Sessions by folder). Section order and each section's
  `collapsed` are carried since the afternoon of 2026-11-20; `groupBy`, `sortBy`, `ascending`, `show` and
  `shown` are still not.
- Correction (code read 2026-11-20): `collapsed` is not held by the server. Before upload `iAt` passes the
  sections through `xp` (export `aS`), which resets `collapsed` to the default (routines collapsed, the rest
  open); when a server row is applied, `Sp` (export `oS`) takes `collapsed` from the local sections by id.
  The 2026-11-15 evidence above only exercised `groupBy`.

### Sidebar carry on a switch: groups, nav entries, section order, display settings (2026-11-20)

`sync_sidebar()` runs on a Swivel switch (same `swivel_switch()` checks as pin seeding) and gives the
incoming account the outgoing account's:

| Item | Where | On Anthropic's server too? |
|---|---|---|
| Custom groups (P0–P3) and their `code:local_*` assignments | `dframe-store` → `state.customGroupsByScope[<account>/<org>]`; local slice `dframe-group-scopes` (localStorage and config) | yes, wire keys `customGroups*` |
| Nav entries at the top left | `dframe-store` → `state.navPinnedIds`, `navPinV` | yes, in `eAt` |
| Order of the sidebar sections (Pinned, custom groups, Routines, Sessions) | `dframe-store` → `state.codeSidebarByScope[<account>/<org>].sections` (array order and each `order`) | yes, wire key `sidebarSections` |
| Where routines sit (`inline` or `section`) | `dframe-store` → `state.routinesSidebarPlacement` | yes, in `eAt` |
| Each section open or collapsed | same `sections`, each `collapsed` | no, see the correction under "Sidebar view" |
| Sidebar width, collapsed folder groups | `dframe-store` → `state.sidebarWidth`, `state.collapsedGroups` | no |
| Editor for "open in editor" | pref `claude-code-preferred-editor` | no |
| Session activity filter | pref `code-sessions-state-activity-days.<account>` | no |
| New-session permission mode | pref `cc-landing-draft-permission-mode.<account>` | no |

Prefs live in config `epitaxyPrefs[<name>]` and localStorage `LSS-persisted.<name>` (`{value, tabId, timestamp}`).
The app reads the config first and falls back to localStorage (`W_` and `tv` in `shared-1-BtdOJW1_.js`), so
both are written and a missing value is removed from both. Account-keyed names map from the outgoing
account's key to the incoming account's key.

**Server-synced items need the app's pending-upload marker.** Writing them alone does not stick: 8070a55
wrote P0–P3 into all local copies on 2026-11-20 and the app put the server's empty list back within 7 s
(reverted in e39f784). Code (Claude 6.28899.2, `ion-dist.asar`, sync module `shared-5-bRuN4H_n.js`,
sidebar store `index-DxfrQydf.js`, groups `shared-107-DTjE99PW.js`): the sidebar store `ob` (`dframe-store`)
is registered with `KM(ob, eAt, {extraWireKeys, serverPartialize: iAt, serverMerge: uX, mergePendingSeed: oAt, …})`,
and launch reconcile (`CC`) applies the account's server row over local state, unless
`ccd-sync-pending:ccd/dframe-store` matches the vouched identity `<account>/<org>` (`Dx`). With that marker and
no `|migrate` suffix it keeps local state, takes the server row as the base and uploads the full local row (`Hx`).
It is the marker `jx(…, "edit")` writes after a local edit. So when groups, nav, section order or the routines
placement change, `sync_sidebar()`:

1. writes the marker `<account>/<ccd-sync-org>`, only when `ccd-sync-org` is known, `ccd-sync-owner` is missing
   or the incoming account, and `ccd-sync-quarantine` is not `1` (otherwise only the local-only items are carried);
2. deletes `ccd-sync-pending-base:ccd/dframe-store` if present (with a stored base reconcile folds the server row in);
3. sets `pendingLegacyGroupMigration` to null: `onIdentityResolve` would otherwise call `EQe`, turn the marker
   into `|migrate`, and the server row would win for everything except groups. 5f3cf26 carried groups only
   through that legacy migration; this replaced it.

Sections (added the afternoon of 2026-11-20, after the owner agreed to carry where Routines sits and whether it
is open): the incoming account's own scope gets the outgoing account's section order. On load the store's
persist `merge` runs `Tg` → `yp` for every scope: it keeps the given order, drops `kind: "manual"` sections whose
group is gone, inserts a section for each group without one before `sessions` (default settings) and renumbers
`order` (`hp`); `pp` on load sorts by `order`. So the script writes the whole order itself: a manual section for
a carried group the incoming account lacks is created the way `yp` does (`SECTION_DEFAULTS` is `Yf`), sections only
the incoming account has stay after their previous neighbour (as `gp` does), sections of groups it does not have
are dropped, `sessions` stays last and `order` is renumbered as `hp` does. Only the order and `collapsed` are
taken from the outgoing account; every other field of an existing section stays. Order needs the marker;
`collapsed` alone is written without it, like the width.

Neither is written unless the incoming entry has `prefsSeeded: true` (all three accounts did on 2026-11-20):
without it hydration (`Ufn` via `Hfn`) and `eX` rebuild the entry from the `LSS-persisted.dframe-code-sections`
copy and the legacy per-account prefs. That localStorage copy and the config copy
(`epitaxyPrefs["dframe-code-sections"]`) are not written: `QY()` reads them only in those two places, both skip
seeded entries, and the app rewrites both from the store (`tf("dframe-code-sections", Nfn(...))`).

Cost, accepted by the owner on 2026-11-20 (decision page 1-B): the incoming account's whole sidebar row on the
server (pins order, view settings, filters, groups, nav) is replaced by this Mac's copy, so changes made to
that account on another device since it was last open here are lost.

Rules:

- Groups: shared ids take the outgoing version (renames follow), outgoing groups are appended, incoming-only
  groups stay; `code:local_*` assignments follow the outgoing account, including moves and removals.
  `~/.claude/cc-mirror-groups.json` records the ids seen per account; an id that disappears from an account
  (with no unconsumed legacy migration) goes into `dropped` and is removed from every account it is carried into.
- Nav: copied only when the outgoing `navPinnedIds` is a list. `null` means the account never customised its
  nav (no UI path sets it back to null; only `stripAccountSlice` does, on an account change), so it never
  overwrites a customised list. `navSeedHere` is set to null, as `uX` does when it takes a server list.
- Display settings and prefs: the outgoing value wins, including "not set" (coming from an account without an
  activity filter removes the incoming account's filter). Owner's choice, 2026-11-20 (decision page 2-A).
- Routines placement: copied only when the outgoing value is `inline` or `section` (`Zh`).
- Nothing is written when the incoming account already matches. Summary item `sidebar-synced N`; opt out with
  `--no-sidebar-sync`.

Tested: unit tests (Python 3.9); copies of all three profiles, Personal → RAS → RASA → Personal → RAS (P0–P3
with 5 assignments, 16 nav entries, width 363, 8 collapsed groups and editor vscode carried; RAS's permission
mode and RASA's 3-day filter removed; the last two switches wrote nothing); `tools/simulate-switch --to RAS
--round-trip` (pins PASS, `sidebar-synced 1` into RAS, 0 back).

Section order, tested 2026-11-20 15:40 on the final script: 8 new test cases (6 fail on the previous version;
the 2 that pass expect nothing to be written: an unknown placement, an entry the app has not seeded); `tools/simulate-switch
--round-trip` from Personal to RAS and back, and to RASA. RAS (Routines collapsed above P0–P3) and RASA (Routines
open above P0–P3) both became Pinned, P0–P3, Routines collapsed, Sessions, with the marker; only `order` and
Routines' `collapsed` changed in RASA; the way back wrote nothing.

Real switch 2026-11-20 16:29, Personal → RASA, `sidebar-synced 1`: RASA went from Routines open above P0–P3 to
Pinned, P0–P3, Routines collapsed, Sessions. Read with `read_sidebar_store` at 16:30 and 16:31 (pin-watch was not
running): the marker was deleted and the order had not reverted. Whether the server row holds the new order is
checked on the next switch into RASA that writes nothing (`sidebar-synced 0`), see confstack-data `docs/Todoist.md` T-011.

Real switches on 2026-11-20, from `~/Library/Logs/cc-mirror-pin-watch.log` (times are when pin-watch saw it):

- Personal → RAS at 12:55:52, `sidebar-synced 1`: RAS went from no groups, nav `null`, 22 collapsed, editor
  cursor and permission mode auto to P0–P3 with 5 assignments, 16 nav entries, 8 collapsed, vscode and no
  permission mode. `ls.pending` held `<account>/<org>` at 12:55:56 and was gone at 12:56:02; nothing reverted.
- RAS → RASA at 12:56:10, `sidebar-synced 1`: RASA ended with the same values; its width 420 became 363 and
  its 3-day activity filter was removed. Marker gone at 12:56:19.
- RASA → RAS at 12:56:26: nothing to write, so no marker. RAS still had P0–P3, 5 assignments, 16 nav entries
  and width 363 at 12:56:35 and 12:57:30, so the server row holds them (before the marker existed, the server
  copy replaced local groups 2.7 s and 6.5 s after launch).

A deleted marker alone does not prove the upload, since `Ox` also clears it on 403/404; RASA has not been
reopened without the marker yet. To check again, run `tools/pin-watch --detach` before the switch: after
launch the incoming account keeps `ls.store.groups`, `ls.store.display` and `cfg.prefs`, `ls.pending` shows
`<account>/<org>` and is then deleted, and the values survive the next launch without a marker. Rollback:
`~/.claude/backups/sidebar-sync-20261120-122649/` (all three profiles' localStorage and config, the groups
state, and the previous `~/bin/cc-mirror-sessions`).

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
  agent-configs, managed by agents from now on"). Rules: confstack-data
  `/Volumes/T9/Documents/www/confstack-data/shared/common/rules/confstack-data-auto-commit.md`. Write every git call as
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
