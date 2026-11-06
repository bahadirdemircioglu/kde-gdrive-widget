# Google Drive Sync Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A KDE Plasma 6 widget that shows the state of the rclone-bisync Google Drive service (`gdrive-sync`) and offers sync-now / pause / open actions.

**Architecture:** The sync scripts write a small `status.json`; a stdlib-only Python helper `gdrive-status` writes it (begin/end of each run), parses the run's slice of `sync.log` into recent changes and an error code, and on `show` overlays live phase/progress and service state. The QML widget polls `gdrive-status show` through the Plasma5Support executable engine and never touches rclone. Pure view logic lives in `logic/Status.js` (tested under Node).

**Tech Stack:** bash, Python 3 stdlib, rclone bisync, systemd user service, QML (Plasma 6, Kirigami, Plasma5Support), Node ≥20 `node --test`, gettext.

**Status:** executed 2026-11-06 (order 1 → 3 → 4 → 2 → 5).

**Spec:** visual plan https://claude.ai/artifact/Q5xkTkSX4pvhG7tVEy37jB (6 boards: panel states, architecture, popup synced/syncing/error, desktop view), approved 2026-11-06.

## Global Constraints

- Plugin id `io.github.bahadirdemircioglu.gdrivesync`, name "Google Drive Sync", license GPL-3.0-or-later, `X-Plasma-API-Minimum-Version` 6.0.
- States (exact strings): `synced`, `syncing`, `error`, `paused`, `offline`, `missing` (helper not installed / no status yet).
- Phases: `listing`, `comparing`, `transferring`, `saving`.
- Change kinds: `up` (local→Drive), `down` (Drive→local), `deleted_remote` (deleted on Drive because deleted locally), `deleted_local`.
- Error codes: `lock`, `out_of_sync`, `too_many_deletes`, `permission`, `auth`, `unknown`.
- No resync button anywhere in the widget.
- Files: `~/.local/state/gdrive-sync/status.json`, log `~/.local/state/gdrive-sync/sync.log`, trigger `$XDG_RUNTIME_DIR/gdrive-sync/now`.
- Widget calls only `"$HOME/.local/bin/gdrive-status" <show|now|pause|resume>` (plasmashell PATH lacks ~/.local/bin); command configurable.
- The helper must never make a sync fail: every call from the scripts is `|| true`.
- UI languages: English source strings, Turkish catalog (same Lang/I18n system as ~/Dev/kde_widget).
- Recent list keeps the last 50 changes; widget shows `recentCount` (default 7).

## Review Focus

- status.json missing, empty or half-written (crash mid-write) → widget shows `missing`, never a QML error; writes are atomic (tmp + rename).
- Service stopped while status says `syncing` (pause mid-run, kill) → `show` reports `paused`, not an eternal spinner.
- Log rotated (`sync.log` → `sync.log.1`) between begin and end → offset larger than file: parse from 0, no crash.
- Paths with spaces, Turkish characters, `[Conflict]` brackets in queue lines → parsed exactly, relative to the sync root.
- Clock/locale: relative times for "now", minutes, hours, yesterday, days; counts "today" by local date.

---

### Task 1: `gdrive-status` helper (Python)

**Files:** Create `sync/gdrive-status`, `sync/tests/test_status.py`, `sync/tests/fixtures/run_changes.log`, `sync/tests/fixtures/run_out_of_sync.log`.

**Interfaces — Produces:**
- `parse_run(text: str, local_root: str) -> dict` → `{"changes":[{"kind","path"}], "phase": str|None, "progress": {"done":int,"total":int}|None, "error": {"code":str,"lines":[str]}|None, "ok": bool}`
- CLI: `gdrive-status begin` · `end ok|fail|offline` · `show` (JSON to stdout) · `now` · `pause` · `resume`.
- status.json keys: `version:1, state, runStartedAt, logOffset, lastRunAt, lastSuccessAt, failCount, fileCount, lastError{code,lines,at}, recent[{kind,path,at}]`; `show` adds `serviceActive, phase, progress, current[{kind,path,done}]`.

- [x] Tests (unittest): queue lines → kinds/paths (incl. space + `[Conflict]`); phases from marker lines; file-count progress `Transferred: 12 / 40, 30%` (ignore byte lines); `out of sync` → `out_of_sync`, `prior lock file` → `lock`, `too many deletes` → `too_many_deletes`, `insufficientFilePermissions` → `permission`, `invalid_grant` → `auth`; begin/end round-trip with temp HOME + fake `systemctl`; `show` with inactive service and state syncing → `paused`; offset beyond EOF → parse from 0; corrupt status.json → treated as empty.
- [x] Implement; atomic write; fileCount = non-dir entries in bisync `path1.lst`.
- [x] Commit.

### Task 2: Sync scripts emit status, daemon honours "sync now"

**Files:** Move `~/Files/bin/gdrive/*` into `sync/`; modify `sync/gdrive-sync`, `sync/gdrive-syncd`, `sync/install.sh` (also links `gdrive-status` into `~/.local/bin`).

- [x] gdrive-sync: `begin` before rclone, `end ok|fail` after, `end offline` when Drive unreachable.
- [x] gdrive-syncd: watch `$XDG_RUNTIME_DIR/gdrive-sync/` too; a `now` event skips the debounce.
- [x] Extend existing stub test (fake rclone) to assert status.json transitions; existing install tests still pass.
- [x] Replace `~/Files/bin/gdrive` with a symlink to `sync/` (keep a backup), restart service, verify one real run writes status.json.
- [x] Commit.

### Task 3: Widget logic `Status.js` + i18n infrastructure

**Files:** `package/contents/ui/logic/Status.js`, `I18n.js`, `Catalogs.js`; `scripts/i18n-*.{sh,mjs}`; `tests/status.test.mjs`, `tests/i18n.test.mjs`, `tests/helpers/load-qml-js.mjs`; `package.json`.

**Produces:** `parseShow(stdout) -> model` (`state` per constraints, `missing` on bad input); `relTime(isoString, nowMs) -> {unit:"now"|"min"|"hour"|"yesterday"|"day", n}`; `todayCounts(recent, nowDate) -> {up, down, deleted}`; `badgeIcon(state) -> "state-ok"|"state-sync"|"state-error"|"state-pause"|"state-offline"|"state-warning"`; `splitPath(path) -> {name, dir}`; `nextPollMs(state, expanded) -> 2000|5000|30000`.

- [x] Tests first for each, then implement; `npm test` green. Commit.

### Task 4: Plasmoid UI

**Files:** `package/metadata.json`, `contents/config/{main.xml,config.qml}`, `contents/icons/cloud.svg`, `contents/ui/{main.qml,CompactRepresentation.qml,FullRepresentation.qml,PhaseStrip.qml,ErrorCard.qml,ChangeRow.qml,ConfigGeneral.qml,Lang.qml,qmldir}`, `translations/tr.po`, `scripts/{install.sh,package.sh}`.

- [x] Compact: masked cloud icon + Breeze state badge; tooltip per board 1.
- [x] Full: header, 3 stat tiles, phase strip (syncing), error card with localized explanation per code (board 5), change list (click opens file/folder via `xdg-open`), buttons Sync now / Pause|Resume / Open folder / Open in Drive / Open log.
- [x] Desktop form factor: compact list (board 6), background option.
- [x] `qmllint` clean; install with `scripts/install.sh`; run in `plasmawindowed`, screenshot each state (fake status files). Commit.

### Task 5: Docs and packaging

- [x] README (EN, short TR section): what it is, install sync + widget, safety notes (resync rule, NFC, drkonqi cycle). `scripts/package.sh` builds `.plasmoid`. Commit.
