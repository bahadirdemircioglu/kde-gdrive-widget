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
        for name in ("gdrive-sync", "gdrive-status"):
            shutil.copy(ROOT / name, self.src / name)
        self.bin = t / "bin"
        self.bin.mkdir()
        self.fake("rclone", """
[ "$1" = lsd ] && exit "${LSD_EXIT:-0}"
for a; do case "$prev" in --log-file) log="$a";; esac; prev="$a"; done
[ -n "${BISYNC_LINE:-}" ] && echo "$BISYNC_LINE" >> "$log"
[ "${RC_EXIT:-0}" = 0 ] && echo "x INFO  : Bisync successful" >> "$log" || echo "x ERROR : Bisync critical error: path1 and path2 are out of sync" >> "$log"
exit "${RC_EXIT:-0}"
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
