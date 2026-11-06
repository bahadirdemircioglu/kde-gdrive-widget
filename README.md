# Google Drive Sync for Plasma

Google has no Drive client for Linux. This project keeps a local folder in two-way sync
with Google Drive using [rclone bisync](https://rclone.org/bisync/) as a systemd user
service, and adds a KDE Plasma 6 widget that shows what the sync is doing.

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
| `sync/install.sh` | installs the service and links the commands into `~/.local/bin` |
| `package/` | the Plasma widget (QML) |

## Install

Requirements: rclone, inotify-tools, Python 3, systemd, Plasma 6.

1. Create an rclone remote named `gdrive` (`rclone config`, type "drive").
2. Sync service: `sync/install.sh` (as your user, not root). The first run is a full
   `--resync` of `~/GoogleDrive` with the remote.
3. Widget: `scripts/install.sh`, then add "Google Drive Sync" from *Add Widgets*.

Other folder or remote: set `GDRIVE_LOCAL` / `GDRIVE_REMOTE` in the service's environment
(`systemctl --user edit gdrive-sync.service`).

Excluded from sync (`~/.config/gdrive-sync/filters.txt`): `.venv`, `__pycache__`,
`node_modules`, `*.pyc`, LibreOffice lock files. After changing the filters, run one
`gdrive-sync --resync`.

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
- Google Docs/Sheets/Forms are skipped (`--drive-skip-gdocs`); they stay on Drive only.

## Development

```
npm test                                   # widget logic + translations (Node ≥ 20)
python3 -m unittest discover -s sync/tests # helper, scripts, installer
scripts/i18n-extract.sh                    # after changing UI strings; then edit translations/*.po
scripts/package.sh                         # dist/gdrive-sync-plasma-<version>.plasmoid
plasmawindowed io.github.bahadirdemircioglu.gdrivesync   # run the widget in a window
```

`tests/fixtures/show-*.json` are sample `gdrive-status show` outputs for every state.

## Türkçe özet

Linux için resmi Google Drive istemcisi yok. Bu proje `~/GoogleDrive` klasörünü rclone
bisync ile Drive'la iki yönlü senkronlayan bir systemd kullanıcı servisi ve durumunu gösteren
bir Plasma 6 widget'ı içerir. Kurulum: önce `rclone config` ile `gdrive` adlı bağlantı, sonra
`sync/install.sh`, sonra `scripts/install.sh` ve *Widget Ekle* → "Google Drive Senkronu".
İki taraf farklıyken asla `--resync` çalıştırmayın; Mac'ten gelen NFD dosya adları için
`gdrive-nfc` kullanın.

## License

GPL-3.0-or-later
