# First-run Setup and Sync Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new user goes from nothing to a running Google Drive sync from the widget (clicks only) or the terminal (`gdrive-setup`), choosing account, Drive folder, local folder and mode (two-way / upload only / download only); existing 0.1.0 installs are migrated silently.

**Architecture:** One stdlib Python module `sync/gdrive_common.py` holds config, migration and requirement checks; `gdrive-status`, the new `gdrive-setup` and (via a tiny `KEY=value` reader) the bash scripts all use the same `~/.config/gdrive-sync/config`. Long steps (Google login, first sync) run detached under `systemd-run --user` and report into `~/.local/state/gdrive-sync/setup.json`, which `gdrive-status show` includes; the widget keeps polling `show` and only fires short `gdrive-setup <step> --json` commands.

**Tech Stack:** bash, Python 3 stdlib, rclone ≥ 1.66 (bisync, copy, check), systemd user units + `systemd-run`, QML (Plasma 6, Kirigami, Plasma5Support), Node ≥ 20 `node --test`, gettext.

**Spec:** `docs/superpowers/specs/2026-11-06-first-run-setup-design.md`

**Execution:** native, in a git worktree (see Task 0). The live service and `~/.local/bin/gdrive-status` run from this checkout, and `gdrive-syncd` re-reads `gdrive-sync` from disk every loop: a half-edited script would run live.

## Global Constraints

- Config file `~/.config/gdrive-sync/config`, lines `KEY=value`, keys `REMOTE` (with colon, e.g. `gdrive:`), `REMOTE_PATH` (empty = My Drive root), `LOCAL`, `MODE` (`twoway|upload|download`), `VERSION=1`, optional `CREATED_REMOTE=1`, `LEGACY=1`. Never `source`d/`eval`ed; unknown keys ignored. Env `GDRIVE_REMOTE`, `GDRIVE_LOCAL`, `GDRIVE_MODE` override.
- Sync target = `REMOTE + REMOTE_PATH` (`gdrive:` + `Belgeler` → `gdrive:Belgeler`).
- Dirs: state `~/.local/state/gdrive-sync/` (status.json, setup.json, sync.log), installed scripts `~/.local/share/gdrive-sync/bin/`, backup `~/.local/share/gdrive-sync/backup/<YYYY-MM-DD>/` (pruned after 30 days), set-aside `~/.local/share/gdrive-sync/set-aside-<YYYY-MM-DD>/`.
- States: existing six plus `unconfigured`. New error code `not_initialized`.
- **Nothing ever runs `bisync --resync` except** `gdrive-setup apply` (after the first-sync rules) and a human typing `gdrive-sync --resync`.
- One-way modes never delete on the target side; files they overwrite go to a backup (download → `--backup-dir` dated backup dir; upload → Drive version history).
- rclone minimum 1.66; inotify-tools optional; the widget never runs `sudo`.
- Commands the widget runs are built with `Status.shellQuote`; no user text is ever concatenated unquoted.
- All writes of status.json / setup.json / config are atomic (tmp + rename).
- Bisync runs that are not the live pair (tests, scratch) pass their own `--workdir`.
- Commit footer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- Service starts before `apply` finished, or `initialized` vanished → `gdrive-sync` must fail with `not_initialized`, never resync (Task 1 test).
- `show` is polled every 2–10 s → migration check is one `stat` of the config path when it exists; migration writes once and is idempotent (Task 1 test).
- Scratch/test bisync writing `.lst` files into `~/.cache/rclone/bisync` → live `fileCount` wrong (Task 2 uses `--workdir`; Task 3 test asserts `file_count` ignores other workdirs).
- Conflict tie (equal modtimes, no winner): verified in Task 2 — rclone renames both to `.conflict1`/`.conflict2` despite `delete`; must be surfaced as a `conflict` change, not silently left (Task 3 test).
- `setup.json` half-written or stale (`running` but unit gone after reboot) while the widget polls → `show` reports `setup.state = "failed"` with code `interrupted`, never an eternal spinner (Task 6 test).

---

### Task 0: Worktree

- [x] `git worktree add ../gdrive_widget-setup -b first-run-setup` (superpowers:using-git-worktrees); all work below happens there. Baseline: `python3 -m unittest discover -s sync/tests` (27 pass) and `npm test` (14 pass).

### Task 1: Config, migration, no automatic resync

**Files:** Create `sync/gdrive_common.py`, `sync/tests/test_common.py`. Modify `sync/gdrive-status`, `sync/gdrive-sync`, `sync/tests/test_status.py`, `sync/tests/test_sync.py`.

**Interfaces — Produces** (`gdrive_common`, imported by scripts via `sys.path.insert(0, dirname(realpath(__file__)))`):
- `paths(env: dict) -> dict` keys `home, config, filters, state, setupJson, share, bin, conflicts, unitDir, unit, localBin` (honours `HOME`, `XDG_CONFIG_HOME`, `GDRIVE_STATE`).
- `read_config(path) -> dict` (missing/garbled file → `{}`), `write_config(path, values: dict) -> None` (atomic, fixed key order).
- `effective(env) -> dict | None` → `{remote, remotePath, target, local, mode, createdRemote, legacy}` or `None` when unconfigured; env overrides applied.
- `detect_legacy(env) -> dict | None` — no config, unit file exists, `state/initialized` exists → values `REMOTE=GDRIVE_REMOTE or "gdrive:"`, `LOCAL=GDRIVE_LOCAL or ~/GoogleDrive`, `MODE=twoway`, `LEGACY=1`.
- `migrate_if_legacy(env) -> bool` — writes the config from `detect_legacy`; never runs rclone.
- `checks(env) -> dict` → `{rclone: bool, rcloneVersion: str|None, rcloneOk: bool, python: True, systemd: bool, inotify: bool, pkgManager: str|None, installCommand: str|None}`; version from first line of `rclone version`; `installCommand` e.g. `sudo pacman -S --needed rclone inotify-tools` listing only missing packages (pacman/apt/dnf/zypper).

- [x] Tests `test_common.py`: config round trip incl. spaces/Turkish chars in `LOCAL` and `REMOTE_PATH`; garbled file → `{}`; env override wins; `effective` builds `target` (`gdrive:` + `A/B` → `gdrive:A/B`, empty path → `gdrive:`); legacy detected only with unit **and** `initialized`; `migrate_if_legacy` twice → one write, second returns False; `checks` with fake `rclone version` printing `rclone v1.65.0` → `rcloneOk False`, `v1.75.2` → True; missing rclone + pacman present → `installCommand` contains `rclone`.
- [x] Run → fail. Implement `gdrive_common.py`. Run → pass.
- [x] `gdrive-status`: read `LOCAL` (and later `MODE`) from `effective()`; `cmd_show`: if config missing → `migrate_if_legacy`; still unconfigured → print `{"state":"unconfigured","checks":checks(),"setup":<setup.json or null>, "serviceActive":…}`. Tests in `test_status.py`: temp HOME with unit + initialized → `show` writes config with `MODE=twoway` and state is not `unconfigured`; no unit → `unconfigured` with `checks`.
- [x] `gdrive-sync`: read config with a `while IFS='=' read -r k v` loop accepting only `REMOTE REMOTE_PATH LOCAL MODE`; env still wins. Remove automatic first resync: if `initialized` missing and no `--resync` arg → `fail "not initialized: run gdrive-setup"`. `gdrive-status classify`: add `("not initialized", "not_initialized")`. Tests in `test_sync.py`: no `initialized` → exit 1, fake rclone log shows **no** `bisync` call, status error code `not_initialized`; `--resync` still runs `bisync --resync`; config `LOCAL=/x y` honoured.
- [x] All Python tests pass. Commit "Config file, legacy migration, no automatic resync".

### Task 2: Verify Google docs, conflicts and copy logs on a scratch Drive folder (real account)

**Files:** Create `sync/tests/fixtures/run_copy_down.log`, `run_copy_up.log` (anonymized). Modify spec section "Google-native documents" with findings.

Scratch: remote folder `gdrive:_gdrive-sync-test-2026-11-06`, local + `--workdir` under the session scratchpad. Never the live pair, never the default workdir.

- [x] Create a Google Doc there: `rclone copy t.docx gdrive:_gdrive-sync-test-…/ --drive-import-formats docx`; add two plain files.
- [x] Bisync `--resync` into an empty scratch local with `--drive-export-formats desktop --workdir <scratch>`; then two normal runs. Pass = `.desktop` exists and runs 2–3 log `No changes found`.
- [x] Conflict: edit the same plain file on both sides (Drive side newer) → run with `--conflict-resolve newer --conflict-loser delete --backup-dir1 <scratch>/conflicts`; expect local loser in backup dir, no `.conflict` file in folder. Tie: same modtime both sides (`touch -d` + `rclone touch -t`) → record exactly where both copies end up.
- [x] Capture `rclone copy` (both directions, `--log-level INFO`, `--backup-dir`) logs as the two fixtures.
- [x] Purge the scratch Drive folder (goes to Drive trash). Write findings (pass/fallback, tie behaviour) into the spec. Commit "Verify docs export and conflict handling".
- [x] ~~If `.desktop` is unstable~~ (stable — not needed):: keep `--drive-skip-gdocs` everywhere and Task 3 adds a `gdocsSkipped` count from `rclone lsf -R --files-only --drive-only-gdocs TARGET` (fallback per spec).

### Task 3: `gdrive-sync` modes, conflicts, counts

**Files:** Modify `sync/gdrive-sync`, `sync/gdrive-status`, tests.

**Interfaces — Produces:**
- `parse_run(text, local_root, mode="twoway")`: in `upload`/`download`, every `INFO  : <rel>: Copied (…)` is a change of kind `up`/`down`; `phase` `"transferring"` once any copy line or progress appears, else `"listing"`; `Duplicate object found`/`Duplicate directory found` lines → `run["duplicates"]` (unique names).
- `file_count(mode)`: twoway → newest `*.path1.lst` **in `BISYNC_DIR` whose name contains the local root's bisync slug** (not just newest); one-way → `os.walk(LOCAL)` file count skipping `.venv`, `__pycache__`, `node_modules`.
- New change kind `conflict` from `New or changed in both paths` NOTICE lines (path relative). status.json adds `mode`, `duplicates: [str]` (last run), `backupDir` (`paths()["conflicts"]`, now `~/.local/share/gdrive-sync/backup`); `show` passes them through.
- After a successful run `gdrive-sync` deletes dated backup folders older than 30 days (`find "$BACKUP" -mindepth 1 -maxdepth 1 -type d -mtime +30`).

- [x] Tests first: copy fixtures → kinds/paths; duplicates parsed; `file_count` ignores a scratch `.lst` with another slug; fake rclone receives, per mode:
  - twoway: `bisync LOCAL TARGET … --conflict-loser delete --backup-dir1 <backup>/<YYYY-MM-DD> --drive-export-formats desktop`, no `pathname`, no `--drive-skip-gdocs`;
  - upload: `copy LOCAL TARGET --drive-skip-gdocs --filters-file …`, no `bisync`, no `--delete*`;
  - download: `copy TARGET LOCAL --drive-export-formats desktop --backup-dir <backup>/<YYYY-MM-DD>`;
  - one-way modes do not require `initialized`.
- [x] Implement; tie `Renaming Path1 copy` lines also produce a `conflict` change. All tests pass. Commit "Sync modes and conflict backups".

### Task 4: Daemon by mode

**Files:** Modify `sync/gdrive-syncd`, `sync/tests/test_sync.py`.

- [x] `MODE` from config/env: twoway unchanged; upload → inotify + `POLL` default 1800; download → no inotify, `POLL` 300, trigger polled every 5 s. Test: download mode with inotifywait on PATH still never invokes it (fake inotifywait logs calls); "now" trigger wakes it < 7 s. Commit.

### Task 5: `gdrive-setup` backend — short steps and service install

**Files:** Create `sync/gdrive-setup`, `sync/tests/test_setup.py`. Modify `sync/install.sh`, `sync/tests/test_install.py`, `.gitignore`, `scripts/package.sh`, `scripts/install.sh`.

**Interfaces — Produces** (all `gdrive-setup <step> … --json` print one JSON object, exit 0 on handled errors with `{"ok":false,"error":code}`):
- `check` → `checks()`.
- `remotes` → `{"remotes":[{"name":"gdrive:"}]}` (type `drive` only, from `rclone listremotes --long`); `suggestName` = `gdrive:` or first free `gdrive-sync-N:`.
- `drive-folders <remote> [path]` → `{"folders":[…]}` via `rclone lsf --dirs-only --max-depth 1`.
- `check-local <path>` → `{"ok", "reason": null|"home"|"root"|"nested"|"state"|"file", "exists", "empty", "ours"}`; `ours` = path equals `setup.json` target local.
- `preview <remote> <remotePath> <local>` → `{"onlyDrive","onlyLocal","different","same","needsChoice"}` from `rclone check TARGET LOCAL --combined - --one-way=false` (`-`, `+`, `*`, `=` prefixes); `needsChoice` = local not empty and not `ours` and (`onlyLocal`+`different`) > 0.
- `install-service [--dev]`: non-dev copies `sync/` scripts into `share/bin` (realpath of own dir is the source); dev leaves them; links `gdrive-status gdrive-sync gdrive-setup gdrive-nfc` into `~/.local/bin` (never over a non-symlink); writes the unit (escaping as today's `install.sh`), `daemon-reload`, best-effort `loginctl enable-linger`; does **not** enable/start.
- `GDRIVE_SYSTEMCTL`, `GDRIVE_SYSTEMD_RUN`, `GDRIVE_RCLONE` override the binaries (tests).

- [x] Tests with fake rclone/systemctl in temp HOME: each step's JSON; `check-local` refuses `$HOME`, `/`, a path inside current `LOCAL`, a file; `preview` counts from a canned `--combined` output (incl. names with spaces); `install-service` unit escaping for a path with `%` and `$`; link not overwritten when a regular file exists.
- [x] Implement. `sync/install.sh` → dev mode: checks systemd/flock, `gdrive-setup install-service --dev`, then if `effective()` is None runs `gdrive-setup` (interactive, Task 7) else `enable --now`/restart as today; no sudo, no `rclone config`. Update `test_install.py`.
- [x] `scripts/package.sh` and `scripts/install.sh` copy `sync/{gdrive-*,gdrive_common.py}` into `package/contents/code/sync/`; `.gitignore` it. Tests pass. Commit "gdrive-setup: checks, folders, preview, service install".

### Task 6: Detached connect / apply, cancel, disconnect

**Files:** Modify `sync/gdrive-setup`, `sync/gdrive-status`, `sync/tests/test_setup.py`.

**Interfaces — Produces:**
- setup.json: `{"step":"connect"|"apply", "state":"running"|"done"|"failed"|"cancelled", "unit", "startedAt", "authUrl", "remote", "createdRemote", "target":{"remote","remotePath","local","mode","firstSync"}, "progress":{"done","total"}|null, "error":{"code","message"}|null}`.
- `connect <name>` → starts `systemd-run --user --unit=gdrive-setup-connect --collect --setenv=DISPLAY=… --setenv=WAYLAND_DISPLAY=… --setenv=DBUS_SESSION_BUS_ADDRESS=… --setenv=XDG_RUNTIME_DIR=… python3 <bin>/gdrive-setup connect-run <name>`; returns `{"started":true}`. `connect-run`: `rclone config create <name-no-colon> drive scope=drive`, scans its output for `http://127.0.0.1:53682/auth?…` → `authUrl` written before blocking; success → `done`, `createdRemote:true`.
- `apply <remote> <remotePath> <local> <mode> <firstSync>`; `firstSync ∈ empty|match|merge|resume|none`. `apply-run`: `install-service` → first sync → `write_config` (+`CREATED_REMOTE=1` if the remote came from `connect`) → `initialized` (twoway) → `enable --now` → `done`. First sync runs the installed `gdrive-sync` with `GDRIVE_REMOTE/LOCAL/MODE` set (one code path for all modes): twoway = `gdrive-sync --resync` (now `--resync-mode newer`), preceded for `match` by `rclone sync TARGET LOCAL --backup-dir <set-aside>`; one-way = one normal run. Success = status.json `synced` from a new run. *(Changed while building: a separate `rclone copy` before the resync added nothing — resync of an empty or ours-only folder is the same download and is resumable.)* Download: `copy` down. Upload: `copy` up. Progress from rclone `--stats-one-line` lines into `progress`. Any failure → `failed`, no config, no enable, files kept.
- `cancel` → `systemctl --user stop gdrive-setup-<step>`; setup.json `cancelled`, target kept (so next `apply` with same local gets `ours`); a cancelled login also deletes the half-made remote (verified: rclone writes the section before the OAuth finishes).
- `disconnect [--delete-remote]` → stop+disable service, config → `config.bak-<date>`, remote deleted only if `--delete-remote` and `CREATED_REMOTE=1`.
- `gdrive-status show` includes `setup`; `running` but `systemctl is-active <unit>` false → reported as `failed` with `error.code = "interrupted"`.

- [x] Tests (fake `systemd-run` that runs the command inline, fake rclone): connect writes `authUrl` then `done`; apply twoway/`empty` call order (copy, then `bisync --resync`, then config, then `enable --now`); `merge` → only `bisync --resync`; failure of copy → no config file, no `enable` call, state `failed`; `match` moves a local-only file into set-aside (fake rclone sync implements `--backup-dir` with `mv`); cancel → `cancelled` and `check-local` then says `ours`; disconnect keeps a pre-existing remote, deletes one with `CREATED_REMOTE=1`; stale running unit → `interrupted`; truncated setup.json → `setup: null`.
- [x] Implement. Tests pass. Commit "gdrive-setup: detached login and first sync".

### Task 7: Terminal wizard

**Files:** Modify `sync/gdrive-setup` (no-arg TTY path), `sync/tests/test_setup.py`.

- [ ] Interactive flow uses the same step functions in-process (not detached): check (print `installCommand`, stop if required missing) → account (existing drive remotes numbered, or "new": runs `rclone config create` in the foreground so the browser opens) → Drive folder (root default; browse one level at a time) → local folder (default `~/GoogleDrive`, `check-local`) → mode (1 two-way default, 2 upload only, 3 download only) → preview + choice when `needsChoice` (1 another empty folder [default], 2 make this folder match Drive, 3 merge, with the duplicate warning) → summary, confirm → apply in-process with a one-line progress → service enabled. Turkish when `LANG` starts with `tr`, English otherwise.
- [ ] Test: drive stdin through the happy path with fakes (`printf '\n\n\n1\ny\n'`) → config written, `enable --now` called. Non-TTY without args → prints usage, exit 2. Commit.

### Task 8: Widget logic

**Files:** Modify `package/contents/ui/logic/Status.js`, `tests/status.test.mjs`. Create `package/contents/ui/logic/Setup.js`, `tests/setup.test.mjs`.

**Interfaces — Produces:**
- `parseShow`: allow `unconfigured`; keep `checks`, `setup`, `mode` (`twoway` default), `duplicates`, `conflictsKept`; `errorCode` allows `not_initialized`; `badgeIcon("unconfigured") = "state-warning"`; `nextPollMs`: setup running → 1000.
- `helperCommand(installedCmd, bundledDir, action) -> string` — `test -x <installed> && <installed> <action> || python3 <quoted bundled>/gdrive-status <action>`; `setupCommand(bundledDir, args[]) -> string` (prefers `$HOME/.local/bin/gdrive-setup`, all args quoted, ends with `--json`).
- `Setup.js`: `pages(checks, needsChoice, mode) -> [ "requirements"?, "account", "driveFolder", "localFolder", "mode", "preview"?, "progress", "done" ]` (requirements only when a required check fails; preview only when twoway and `needsChoice`); `canNext(page, draft) -> bool`; `applyArgs(draft) -> [remote, remotePath, local, mode, firstSync]` (one-way → `none`; `ours` → `resume`; empty local → `empty`).

- [ ] Tests first (incl. `setupCommand` with `'`, `$()`, spaces through a real `sh`), implement, `npm test` green. Commit.

### Task 9: Widget UI

**Files:** Create `package/contents/ui/SetupWizard.qml`. Modify `StatusSource.qml` (`setup(args, tag)`, results by tag), `FullRepresentation.qml` (`unconfigured` → wizard; mode label under title; notices "N conflicts kept aside" → open conflicts dir, "N items have duplicate names on Drive" → open in Drive), `ConfigGeneral.qml` ("Change setup…" opens the wizard prefilled, "Disconnect…" with "Also remove the Google login" checkbox only when `createdRemote`), `Texts.qml`, `ErrorCard` (`not_initialized` text + "Set up again"), `translations/tr.po`.

- [ ] Pages: Requirements (missing items, copyable `installCommand`, "Check again"), Account (existing remotes + "Connect a new Google account"; while running shows "Waiting for the browser…" and the `authUrl` as a link, "Cancel"), Drive folder (breadcrumb + list, "Use My Drive"), Local folder (path field + `FolderDialog`, inline reason when refused), Mode (three radio cards, two-way default, one sentence each), Preview (three counts, three choices, recommended first), Progress (progress bar from `setup.progress`, "Cancel"), Done.
- [ ] `qmllint -I /usr/lib/qt6/qml` clean; i18n extract/build; fake `show` outputs for every page in `tests/fixtures/show-setup-*.json`; `plasmawindowed` screenshot per page (spectacle `-b -n -a`, no key input). Commit.

### Task 10: End to end, release, live migration

- [ ] E2E with real rclone and the existing `gdrive:` remote, temp `HOME` (copy of `rclone.conf` only), `REMOTE_PATH=_gdrive-sync-e2e-…` (created with two files), fake systemctl: `apply … twoway empty` → local equals Drive byte-level (`rclone lsf -R` both sides + `comm`, no `.conflict`, no extra files); then purge the scratch folder.
- [ ] Version 0.2.0 (`metadata.json`), README (setup from widget/terminal, modes, safety), package `.plasmoid`, all tests green. Commit.
- [ ] Merge `first-run-setup` into `main` in this checkout. Live: `gdrive-status show` → config written with `MODE=twoway`, `LEGACY=1`, state still `synced`, sync.log shows no extra run.
- [ ] Live flag change: with the service paused, `rclone bisync ~/GoogleDrive gdrive: --dry-run <new ARGS>` → only new `.desktop` shortcuts on Path1, zero deletes. Then resume; next real run "Bisync successful". `scripts/install.sh` to upgrade the widget; screenshot popup.
- [ ] Advisor check, push to GitHub, update memory note (config file, `gdrive-setup`).
