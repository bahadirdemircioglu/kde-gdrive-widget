# First-run setup and sync modes — design

Status: approved and implemented in 0.2.0 · 2026-11-06 · builds on 0.1.0 (widget + gdrive-status + bisync service)

## Intent

Today everything assumes a machine that is already set up: rclone installed, a remote called
`gdrive`, the folder `~/GoogleDrive`, two-way sync. On any other machine the widget only says
"helper not found". The project is going to be shared, so a new user must be able to go from
nothing to a running sync **either from the widget (clicks only) or from a terminal**, with
the same result.

The user's one-line requirement: **everything visible in Google Drive appears the same way in
a folder I choose, and no extra files get created.** They delegated all other decisions.

## Goals

1. Guided setup in the widget (wizard) and in the terminal (`gdrive-setup`), one shared
   backend, identical outcome.
2. Steps: check requirements → connect Google account → choose Drive folder → choose local
   folder → choose sync mode → first sync (with a preview when both sides have files) →
   install and start the service.
3. Three sync modes:
   - **Two-way** (default): rclone bisync, as today.
   - **Upload only**: local → Drive, `rclone copy` — never deletes on Drive (backup).
   - **Download only**: Drive → local, `rclone copy` — never deletes locally (backup).
4. Faithful mirror: Google Docs/Sheets/Slides/Forms appear as `.desktop` shortcuts that open
   in the browser (download direction).
5. "No extra files": the sync itself never adds files to the user's folder that are not on
   Drive (see the rules below).
6. Change later from the widget settings ("Change setup…") and disconnect cleanly.

## Non-goals (v1)

- Several folder pairs, Shared drives ("Ortak Drive'lar"), "Shared with me" items.
- Installing system packages from the widget (needs root): we show the exact command.
- Per-file sync status in Dolphin.

## Anti-goals (would make it a failure even if it "works")

- A first sync that silently merges two non-empty sides (union → duplicates). This is what
  broke the author's Drive on 2026-11-05.
- Conflict copies (`file.conflict1`) appearing next to the user's files.
- Any operation that deletes data without a backup.
- A wizard that leaves a half-configured service running.

## Decisions

### No-extra-files rules
- **Conflicts** (same file changed on both sides): newer wins (`--conflict-resolve newer`);
  the older version is not renamed into the folder (`--conflict-loser delete`) but kept:
  local losers go to `--backup-dir1 ~/.local/share/gdrive-sync/backup/<YYYY-MM-DD>/` (outside
  the synced folder); Drive losers go to Drive's trash. The widget lists conflicts as a
  change kind `conflict` ("older copy kept aside") with an "Open" button for the backup.
  - *Verified 2026-11-06 (rclone 1.75.2, scratch folder):* `--backup-dir1` receives **every**
    local file that a sync replaces or deletes, not only conflict losers. That is a useful
    safety net, so it stays, in dated folders, and folders older than 30 days are pruned after
    a successful run.
  - *Tie* (both sides changed, identical modification time, so no winner): rclone ignores
    `delete` and renames both copies (`name.conflict1` local, `name.conflict2` Drive) on both
    sides. Needs identical times to the millisecond, so practically only by hand; accepted as
    the one exception to "no extra files": nothing is lost, and the widget reports it as a
    conflict ("two copies kept, keep one").
- **Download only** passes `--backup-dir` (same dated folder) so a local edit overwritten by
  Drive's version is kept. **Upload only** relies on Drive's version history.
- **First sync never unions blindly.** Local folder empty → plain download. Both sides have
  files → the wizard runs a dry run and shows counts (only on Drive / only here / different),
  then offers: *Use another (empty) folder* (recommended) · *Make this folder match Drive*
  (local-only files are **moved** to `~/.local/share/gdrive-sync/set-aside-<date>/`, not
  deleted) · *Merge both* (explicit, with the duplicate warning). One-way modes: upload-only
  just copies up, download-only just copies down; no question needed.
- **Drive duplicates** (same name twice in one Drive folder, impossible on disk): never
  invent `name (1)` locally. `gdrive-status` counts them from rclone's
  "Duplicate object/directory found" notices; the widget shows "N items have duplicate names
  on Drive — only one is synced" with an "Open in Drive" action.
- Exclusions stay (`.venv`, `__pycache__`, `node_modules`, `*.pyc`, lock files) — they keep
  local junk off Drive, they do not add files.

### Google-native documents
- Exported with `--drive-export-formats desktop` → `Name.desktop` shortcut (verified with
  rclone 1.75 against the real account). Import formats stay empty: a local `.desktop` is
  never converted into a Google Doc.
- Two-way: deleting the shortcut locally trashes the document on Drive (faithful two-way).
  Upload-only: Google docs are not touched (`--drive-skip-gdocs`).
- *Verified 2026-11-06 on a scratch Drive folder:* after the first run, two more bisync runs
  report "No changes found"; a document changed on Drive replaces the local shortcut once and
  is stable again; deleting the shortcut locally moves the document to Drive's trash; a plain
  local `.desktop` file uploads as a normal file and stays stable. So no fallback is needed.

### Account connection
- `rclone config create <name> drive scope=drive` (full access, needed for two-way) with
  rclone's built-in OAuth: rclone opens the browser, the user signs in, rclone stores the
  token. Remote name `gdrive`; if taken by a non-drive remote, `gdrive-sync-1`, …
- Existing Drive remotes are offered first (`rclone listremotes --long`, type `drive`).
- rclone's shared client id is the default; an "own client id" field is in an "Advanced"
  expander only.

### Drive folder
- Default: the whole "My Drive". Option: pick a folder (one level at a time, `rclone lsf
  --dirs-only`). Stored as `REMOTE_PATH` (empty = root).

### Local folder
- Default `~/GoogleDrive`; folder picker. Refused: `$HOME` itself, `/`, a folder inside
  another configured sync root, a folder containing the state dir. Created if missing.

### Requirements
- rclone ≥ 1.66 (bisync with `--recover`/`--max-lock`), Python 3, systemd user session:
  required. inotify-tools: optional (without it changes are picked up every 5 min).
- Missing → the wizard shows the command for the detected package manager (pacman, apt,
  dnf, zypper) with a copy button and a "Check again" button.

### Configuration
- `~/.config/gdrive-sync/config`, `KEY=value` lines (shell-sourceable, Python-parsable):
  `REMOTE`, `REMOTE_PATH`, `LOCAL`, `MODE` (`twoway|upload|download`), `VERSION=1`.
- All scripts read it; `GDRIVE_*` environment variables still override (tests, power users).
- No config → `gdrive-status show` reports state `unconfigured` with `checks`
  (`rclone`, `rcloneVersion`, `python`, `inotify`, `systemd`, `remotes[]`).

### Where the code lives when installed from the widget
- The `.plasmoid` bundles `sync/` under `contents/code/sync/` (copied by `scripts/package.sh`
  and `scripts/install.sh`; `sync/` stays the single source).
- Setup copies the scripts to `~/.local/share/gdrive-sync/bin/` (stable across widget
  updates), links the commands into `~/.local/bin`, writes the unit, starts the service.
  Scripts are run as `python3 <file>` / `bash <file>` so lost exec bits do not matter.
- The widget finds the helper at `~/.local/bin/gdrive-status`; if absent it uses the bundled
  copy for the setup steps.

### Backend: `gdrive-setup` (Python, stdlib)
One program, two front ends:
- `gdrive-setup` (no args, TTY): interactive terminal wizard.
- `gdrive-setup <step> --json`: one step per call for the widget, JSON out:
  `check`, `remotes`, `connect <name>` (blocks until the browser login finishes; prints the
  auth URL first for fallback), `drive-folders <remote> [path]`, `preview <remote> <path>
  <local> <mode>` (dry-run counts), `apply <remote> <path> <local> <mode> <first-sync>`
  (writes config, first sync, installs + starts service), `disconnect` (stop + disable
  service, keep files and config backup).
- `apply` is all-or-nothing: on failure the service is not enabled and the config is not
  written.

### Widget
- State `unconfigured` → `SetupWizard.qml` instead of the placeholder: pages Requirements →
  Account → Drive folder → Local folder → Mode → Preview (only when needed) → Done. Long
  steps (login, first sync) show progress and can be cancelled.
- Settings get "Change setup…" (reopens the wizard, prefilled) and "Disconnect…".
- Popup shows the mode ("Two-way" / "Upload only" / "Download only") under the title; in
  one-way modes "Pause" and "Sync now" stay; conflicts and duplicates notices as above.
- `missing` (helper not runnable at all) keeps a short message pointing to the wizard.

### Daemon by mode
- Two-way: unchanged (inotify + 5 min poll + "now").
- Upload only: inotify + "now"; poll every 30 min as a safety net.
- Download only: 5 min poll + "now"; no inotify.

### Existing 0.1.0 installs (migration) — must come first
- An install without `~/.config/gdrive-sync/config` but with `gdrive-sync.service`
  and `~/.local/state/gdrive-sync/initialized` is **already in sync**. `gdrive-setup`
  detects this (unit present, `initialized` present, remote from the unit/env, default
  `gdrive:`/`~/GoogleDrive`, any `GDRIVE_*` overrides) and writes the config from those
  values with `MODE=twoway` — **no first sync, no resync, the bisync baseline is kept.**
- `gdrive-status show` runs this detection itself before reporting `unconfigured`, so an
  upgraded widget never opens the wizard over a working pair.
- A legacy install keeps its script location (the author's dev checkout); migration does not
  move scripts.

### Long steps run detached
- Plasma's executable engine returns output only when the process exits and cannot stop
  it, and a child of plasmashell dies when Plasma restarts. So `connect` and `apply` are
  started detached with `systemd-run --user --unit=gdrive-setup-<step> …` and report
  progress into `~/.local/state/gdrive-sync/setup.json`; `gdrive-status show` includes it,
  the widget polls as usual. `gdrive-setup cancel` stops the unit.
- "All-or-nothing" means: config and service are written only after the first sync
  succeeded. A cancelled or failed first sync leaves the downloaded files in place and
  records the target in `setup.json`; running `apply` again for the same folder resumes
  (the folder is recognised as ours, not treated as "both sides have files").

### Terminal install and development
- `sync/install.sh` becomes the **developer mode**: links the commands to the checkout
  (as today) and, if there is no config, runs `gdrive-setup` interactively. End users use
  `gdrive-setup` (installs into `~/.local/share/gdrive-sync/bin/`) or the widget.
- `sync/tests/test_install.py` is adjusted accordingly.

### Disconnect
- Stops and disables the service, keeps the files and moves the config to
  `config.bak-<date>`.
- The rclone remote is deleted **only if setup created it** (`CREATED_REMOTE=1` in the
  config), offered as a checked option. A remote that existed before setup is never
  deleted.

## Left to the builder
- Exact wizard layout and copy (follow the existing Breeze style and the Lang/Texts pattern).
- Package-manager detection details, rclone version parsing.
- How `connect` streams progress (line-based JSON events on stdout is fine).

## Calls I made on the user's behalf (for review)
1. One folder pair, whole My Drive by default.
2. Two-way is the default mode; one-way modes never delete.
3. Conflict losers (and every local file a sync replaces or deletes) go to a hidden dated
   backup folder kept 30 days; exact-time ties are the one case where rclone keeps two
   `.conflict` copies.
4. First sync with two non-empty sides asks, and recommends an empty folder.
5. Google docs appear as `.desktop` shortcuts (with a verified fallback).
6. Drive duplicate names are reported, not renamed.
7. The widget never installs system packages; it shows the command.
8. Existing installs are migrated silently, without any sync (this machine included).
9. Login and first sync run detached and survive a Plasma restart; cancel keeps files.
10. `install.sh` becomes developer mode; end users use `gdrive-setup` or the widget.
11. Disconnect deletes the Google login only if setup created it.
