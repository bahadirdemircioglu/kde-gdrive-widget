# Google Drive Sync for Plasma

Google has no Drive client for Linux. This project keeps a local folder in sync with Google
Drive using [rclone](https://rclone.org/) as a systemd user service, and adds a KDE Plasma 6
widget that sets it up and shows what the sync is doing.

- **Setup from the widget or a terminal:** Google sign-in in the browser, which part of Drive,
  which local folder, which mode. Nothing to configure by hand.
- **Three modes:** two-way (rclone bisync), upload only, download only. The one-way modes
  never delete anything on the receiving side, so they work as a backup.
- **What you see on Drive is what you get, and nothing more:** Google Docs/Sheets/Slides
  appear as `.desktop` shortcuts that open in the browser; conflicting edits keep the newer
  version in place and move the older one to a backup folder instead of leaving
  `file.conflict1` copies next to your files.

- **Panel icon:** a cloud with a state badge: up to date, syncing, error, paused, offline.
- **Popup:** last sync time, file count, today's uploads/downloads, recent changes (click to
  open), the phase of a running sync (listing → comparing → transfer → saving) with file
  progress, and errors in plain words with what to do.
- **Actions:** sync now, pause / resume, open folder, open Drive in the browser, open the log.
- **No resync button, deliberately.** `--resync` merges both sides; run it only from a terminal,
  and only after you checked that both sides are identical.
- English and Turkish.

Unofficial; not affiliated with Google.

## How it works

```
gdrive-syncd (systemd user service)
  └─ gdrive-sync ── rclone bisync ──> sync.log
        └─ gdrive-status begin/end ──> status.json
Plasma widget ── "$HOME/.local/bin/gdrive-status" show ──> JSON (+ live phase from the log)
```

The widget never runs rclone. It calls `gdrive-status show|now|pause|resume`.

| Path | What |
|---|---|
| `sync/gdrive-syncd` | daemon: syncs on local changes (inotify), every 5 min, or when asked |
| `sync/gdrive-sync` | one bisync run, failure counter, desktop notification after 3 failures |
| `sync/gdrive-status` | status file and log parsing (Python 3, standard library only) |
| `sync/gdrive-nfc` | renames NFD file names (e.g. from macOS) to NFC on both sides |
| `sync/gdrive-setup` | first-run setup: terminal wizard and the widget's backend |
| `sync/gdrive_common.py`, `sync/gdrive-lib.sh` | settings file shared by the scripts |
| `sync/install.sh` | developer mode: runs the service from this checkout |
| `package/` | the Plasma widget (QML) |

## Install

Requirements: rclone ≥ 1.66, Python 3, systemd, Plasma 6; inotify-tools is optional (without
it local changes are picked up every 5 minutes). The setup shows the exact install command
for your distribution if something is missing.

**From the widget:** `scripts/install.sh` (or install the `.plasmoid` from
`scripts/package.sh`), add "Google Drive Sync" from *Add Widgets*, click it and follow the
steps. The sync scripts come with the widget and are installed to
`~/.local/share/gdrive-sync/bin/`.

**From a terminal:** `python3 sync/gdrive-setup` asks the same questions (English or
Turkish, following `LANG`).

What the setup does, in order: checks the folder (never your home folder, never inside the
folder already in sync); if the folder already has files it compares it with Drive and asks:
use another, empty folder (recommended) · make this folder match Drive (files only here are
moved to `~/.local/share/gdrive-sync/set-aside-<date>/`, not deleted) · merge both. Then the
first sync, and only after it succeeded: scripts, settings
(`~/.config/gdrive-sync/config`) and the service. Long steps run as their own systemd unit,
so closing the popup or restarting Plasma does not stop them; "Cancel" keeps what was
already copied.

Change it later from the widget's menu ("Change setup…"); "Disconnect…" stops the service
and keeps your files (and removes the Google sign-in only if the setup created it).

Excluded from sync (`~/.config/gdrive-sync/filters.txt`): `.venv`, `__pycache__`,
`node_modules`, `*.pyc`, LibreOffice lock files. After changing the filters of a two-way
setup, run one `gdrive-sync --resync`.

Files that a sync replaces or deletes on this computer are kept for 30 days in
`~/.local/share/gdrive-sync/backup/<date>/` ("Open kept copies" in the widget's menu).

**Upgrading from 0.1.0:** nothing to do. A running 0.1.0 install is recognised and its
settings are written from the current values (two-way, `gdrive:`, `~/GoogleDrive`) without
any sync. From 0.2.0 on Google Docs appear as shortcuts, so the first run after the upgrade
downloads one small `.desktop` file per document.

## Things that bit us (read before you rely on it)

- **Never `--resync` while the two sides differ.** It is a union: files moved on one side end
  up in both places. Check first: `rclone check ~/GoogleDrive gdrive: --drive-skip-gdocs
  --filter-from ~/.config/gdrive-sync/filters.txt` must report 0 differences, and
  `rclone lsf -R` of both sides must match byte for byte (see the next point).
- **Unicode NFC vs NFD.** Files uploaded from a Mac often have decomposed (NFD) names. Normal
  bisync runs tolerate the difference, but recovery after an interrupted run compares names
  byte by byte and stops with "path1 and path2 are out of sync". Run `gdrive-nfc` (shows a
  plan), stop the service, then `gdrive-nfc --uygula`.
- **Interrupted runs.** The service uses `--max-lock 5m` and `--recover`, so a crash or power
  loss heals itself. On KDE, drkonqi's `drkonqi-sentry-postman.path` and
  `drkonqi-coredump-cleanup.timer` (6.x) create a systemd ordering cycle at shutdown that can
  make systemd drop the service's stop job and kill rclone. Check with
  `journalctl --user -b -1 | grep 'ordering cycle'`; the fix is a copy of those units in
  `~/.config/systemd/user/` without their `After=default.target` / `After=timers.target` line.
- **Files owned by someone else** (shared into your folders) cannot be deleted from your
  Drive (403). Don't delete them locally; remove them on drive.google.com.
- **Two-way never starts a first sync on its own.** If its baseline is missing it stops with
  "The setup was not finished" instead of merging both sides; run the setup again.
- **Conflict ties.** When both sides changed a file with exactly the same modification time,
  rclone cannot pick a winner and keeps both as `name.conflict1` / `name.conflict2`. The
  widget reports it; keep one.
- Google Docs deleted locally (the `.desktop` shortcut) go to Drive's trash.

## Development

```
npm test                                   # widget logic + translations (Node ≥ 20)
python3 -m unittest discover -s sync/tests # helper, scripts, installer
scripts/i18n-extract.sh                    # after changing UI strings; then edit translations/*.po
scripts/package.sh                         # dist/kde-gdrive-widget-<version>.plasmoid
sync/install.sh                            # developer mode: service runs from this checkout
plasmawindowed io.github.bahadirdemircioglu.gdrivesync   # run the widget in a window
```

`tests/fixtures/show-*.json` are sample `gdrive-status show` outputs for every state.

## Türkçe özet

Linux için resmi Google Drive istemcisi yok. Bu proje bir klasörü rclone ile Google Drive'la
senkronlayan bir systemd kullanıcı servisi ve onu kuran, durumunu gösteren bir Plasma 6
widget'ı içerir.

- **Kurulum:** widget'ı ekleyip tıklayın ya da terminalde `python3 sync/gdrive-setup`
  çalıştırın. Google girişi tarayıcıda yapılır; Drive'ın hangi kısmı, hangi yerel klasör ve
  hangi mod (iki yönlü / sadece yükleme / sadece indirme) adım adım sorulur.
- **Fazladan dosya yok:** Google Dokümanlar tarayıcıda açılan kısayol olarak görünür; çakışmada
  yeni sürüm yerinde kalır, eskisi `~/.local/share/gdrive-sync/backup/` altına gider.
  Klasörde zaten dosya varsa ilk senkrondan önce farklar gösterilir ve ne yapılacağı sorulur.
- Tek yönlü modlar karşı tarafta hiçbir şey silmez, yedek gibi çalışır.
- İki taraf farklıyken asla `--resync` çalıştırmayın; Mac'ten gelen NFD dosya adları için
  `gdrive-nfc` kullanın.

## License

GPL-3.0-or-later
