"""gdrive-sync writes status.json; gdrive-syncd wakes up on "gdrive-status now".
Uses a fake rclone; the daemon test uses the real inotifywait."""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
UPLOAD = 'x INFO  : - Path1   Queue copy to Path2   - gdrive{A}:/docs/new file.pdf'


class SyncStatusTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = pathlib.Path(self.tmp.name)
        self.home = t / "home"
        (self.home / ".local/state/gdrive-sync").mkdir(parents=True)
        (self.home / ".local/state/gdrive-sync/initialized").touch()
        self.state = self.home / ".local/state/gdrive-sync"
        self.src = t / "sync"
        self.src.mkdir()
        for name in ("gdrive-sync", "gdrive-status", "gdrive_common.py", "gdrive-lib.sh"):
            shutil.copy(ROOT / name, self.src / name)
        self.bin = t / "bin"
        self.bin.mkdir()
        self.calls = t / "rclone_calls"
        self.fake("rclone", f"""
printf '%s|' "$@" >> "{self.calls}"; echo >> "{self.calls}"
[ "$1" = lsd ] && exit "${{LSD_EXIT:-0}}"
for a; do case "$prev" in --log-file) log="$a";; esac; prev="$a"; done
[ -n "${{BISYNC_LINE:-}}" ] && echo "$BISYNC_LINE" >> "$log"
[ "${{RC_EXIT:-0}}" = 0 ] && echo "x INFO  : Bisync successful" >> "$log" || echo "x ERROR : Bisync critical error: path1 and path2 are out of sync" >> "$log"
exit "${{RC_EXIT:-0}}"
""")
        self.fake("notify-send", "exit 0")
        self.fake("systemctl", "exit 0")
        self.env = dict(os.environ, HOME=str(self.home), PATH=f"{self.bin}:/usr/bin:/bin",
                        XDG_RUNTIME_DIR=str(t / "run"), GDRIVE_BISYNC_DIR=str(t / "bisync"),
                        GDRIVE_SYSTEMCTL=str(self.bin / "systemctl"))

    def fake(self, name, body):
        p = self.bin / name
        p.write_text("#!/bin/bash\n" + body + "\n")
        p.chmod(0o755)

    def sync(self, **extra):
        return subprocess.run([str(self.src / "gdrive-sync")], env=dict(self.env, **extra),
                              capture_output=True, text=True)

    def status(self):
        return json.loads((self.state / "status.json").read_text())

    def test_success_records_changes(self):
        self.assertEqual(self.sync(BISYNC_LINE=UPLOAD).returncode, 0)
        st = self.status()
        self.assertEqual(st["state"], "synced")
        self.assertEqual(st["recent"][0]["path"], "docs/new file.pdf")
        self.assertEqual(st["recent"][0]["kind"], "up")

    def test_failure_records_error_and_counter(self):
        self.sync()
        self.assertEqual(self.sync(RC_EXIT="2").returncode, 1)
        self.assertEqual(self.sync(RC_EXIT="2").returncode, 1)
        st = self.status()
        self.assertEqual(st["state"], "error")
        self.assertEqual(st["failCount"], 2)
        self.assertEqual(st["lastError"]["code"], "out_of_sync")
        self.assertIsNotNone(st["lastSuccessAt"])

    def test_offline_does_not_replay_previous_changes(self):
        self.sync(BISYNC_LINE=UPLOAD)
        self.assertEqual(self.sync(LSD_EXIT="1").returncode, 0)
        st = self.status()
        self.assertEqual(st["state"], "offline")
        self.assertEqual(len(st["recent"]), 1)

    def rclone_calls(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_missing_baseline_never_resyncs_on_its_own(self):
        (self.state / "initialized").unlink()
        self.assertEqual(self.sync().returncode, 1)
        self.assertFalse([c for c in self.rclone_calls() if c.startswith("bisync|")])
        self.assertEqual(self.status()["lastError"]["code"], "not_initialized")

    def test_explicit_resync_still_works(self):
        (self.state / "initialized").unlink()
        p = subprocess.run([str(self.src / "gdrive-sync"), "--resync"], env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(any("|--resync|" in c for c in self.rclone_calls()))
        self.assertTrue((self.state / "initialized").exists())

    def test_config_file_is_honoured_and_never_executed(self):
        cfg = self.home / ".config/gdrive-sync/config"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        local = self.home / "My Drive Ş"
        cfg.write_text(f"REMOTE=work:\nREMOTE_PATH=Belgeler/2026\nLOCAL={local}\n"
                       "MODE=twoway\nVERSION=1\nEVIL=$(touch /tmp/gdrive-pwned)\n")
        self.assertEqual(self.sync().returncode, 0)
        bisync = [c for c in self.rclone_calls() if c.startswith("bisync|")][0].split("|")
        self.assertEqual(bisync[1:3], [str(local), "work:Belgeler/2026"])
        self.assertTrue(local.is_dir())

    def test_env_overrides_config(self):
        cfg = self.home / ".config/gdrive-sync/config"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(f"REMOTE=work:\nLOCAL={self.home}/a\nMODE=twoway\nVERSION=1\n")
        self.sync(GDRIVE_LOCAL=str(self.home / "b"), GDRIVE_REMOTE="other:")
        bisync = [c for c in self.rclone_calls() if c.startswith("bisync|")][0].split("|")
        self.assertEqual(bisync[1:3], [str(self.home / "b"), "other:"])

    def write_config(self, mode, local=None):
        cfg = self.home / ".config/gdrive-sync/config"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        self.local = local or self.home / "Drive"
        cfg.write_text(f"REMOTE=gdrive:\nLOCAL={self.local}\nMODE={mode}\nVERSION=1\n")

    def call(self, verb):
        found = [c.split("|")[:-1] for c in self.rclone_calls() if c.startswith(verb + "|")]
        self.assertEqual(len(found), 1, self.rclone_calls())
        return found[0]

    def backup_today(self):
        return str(self.home / ".local/share/gdrive-sync/backup" / time.strftime("%Y-%m-%d"))

    def test_twoway_args(self):
        self.write_config("twoway")
        self.assertEqual(self.sync().returncode, 0)
        a = self.call("bisync")
        self.assertEqual(a[1:3], [str(self.local), "gdrive:"])
        self.assertEqual(a[a.index("--conflict-loser") + 1], "delete")
        self.assertEqual(a[a.index("--backup-dir1") + 1], self.backup_today())
        self.assertEqual(a[a.index("--drive-export-formats") + 1], "desktop")
        self.assertNotIn("--drive-skip-gdocs", a)

    def test_upload_only_copies_up_and_never_deletes(self):
        self.write_config("upload")
        (self.state / "initialized").unlink()
        self.assertEqual(self.sync(BISYNC_LINE="x INFO  : f.txt: Copied (new)").returncode, 0)
        a = self.call("copy")
        self.assertEqual(a[1:3], [str(self.local), "gdrive:"])
        self.assertIn("--drive-skip-gdocs", a)
        self.assertFalse([x for x in a if x.startswith("--delete") or x.startswith("--backup-dir")])
        self.assertFalse([c for c in self.rclone_calls() if c.startswith("bisync|")])
        st = self.status()
        self.assertEqual(st["state"], "synced")
        self.assertEqual(st["recent"][0], {**st["recent"][0], "kind": "up", "path": "f.txt"})

    def test_download_only_copies_down_with_backup(self):
        self.write_config("download")
        (self.state / "initialized").unlink()
        self.assertEqual(self.sync().returncode, 0)
        a = self.call("copy")
        self.assertEqual(a[1:3], ["gdrive:", str(self.local)])
        self.assertEqual(a[a.index("--drive-export-formats") + 1], "desktop")
        self.assertEqual(a[a.index("--backup-dir") + 1], self.backup_today())
        self.assertFalse([x for x in a if x.startswith("--delete")])

    def test_old_backups_are_pruned_after_success(self):
        backup = self.home / ".local/share/gdrive-sync/backup"
        old, new = backup / "2026-09-01", backup / "2026-11-01"
        old.mkdir(parents=True)
        new.mkdir()
        (old / "x.txt").write_text("x")
        t = time.time() - 40 * 86400
        os.utime(old, (t, t))
        self.assertEqual(self.sync().returncode, 0)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())

    def test_missing_helper_never_breaks_the_sync(self):
        (self.src / "gdrive-status").unlink()
        self.assertEqual(self.sync().returncode, 0)


class DaemonTriggerTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("inotifywait"), "inotify-tools not installed")
    def test_now_trigger_wakes_daemon_without_debounce(self):
        with tempfile.TemporaryDirectory() as d:
            t = pathlib.Path(d)
            src = t / "sync"
            src.mkdir()
            shutil.copy(ROOT / "gdrive-syncd", src / "gdrive-syncd")
            shutil.copy(ROOT / "gdrive-status", src / "gdrive-status")
            shutil.copy(ROOT / "gdrive_common.py", src / "gdrive_common.py")
            shutil.copy(ROOT / "gdrive-lib.sh", src / "gdrive-lib.sh")
            runs = t / "runs"
            (src / "gdrive-sync").write_text(f'#!/bin/bash\necho run >> "{runs}"\n')
            (src / "gdrive-sync").chmod(0o755)
            env = dict(os.environ, HOME=str(t / "home"), XDG_RUNTIME_DIR=str(t / "run"),
                       GDRIVE_LOCAL=str(t / "drive"), GDRIVE_POLL="60", GDRIVE_DEBOUNCE="30")
            daemon = subprocess.Popen([str(src / "gdrive-syncd")], env=env)
            try:
                deadline = time.time() + 5
                while time.time() < deadline and not runs.exists():
                    time.sleep(0.1)
                time.sleep(0.5)  # let inotifywait start watching
                subprocess.run([str(src / "gdrive-status"), "now"], env=env, check=True)
                deadline = time.time() + 5
                while time.time() < deadline and runs.read_text().count("run") < 2:
                    time.sleep(0.1)
                self.assertEqual(runs.read_text().count("run"), 2, "second run within 5 s, debounce skipped")
                self.assertFalse((t / "run/gdrive-sync/now").exists())
            finally:
                daemon.terminate()
                daemon.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
