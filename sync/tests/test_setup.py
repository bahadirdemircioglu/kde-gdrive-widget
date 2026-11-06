"""Tests for sync/gdrive-setup with fake rclone / systemctl / systemd-run in a temp HOME."""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ["gdrive-setup", "gdrive-sync", "gdrive-syncd", "gdrive-status", "gdrive-nfc",
           "gdrive_common.py", "gdrive-lib.sh"]

FAKE_RCLONE = r'''#!/bin/bash
printf '%s|' "$@" >> "$CALLS/rclone"; echo >> "$CALLS/rclone"
case "$1" in
  version) echo "rclone v1.75.2" ;;
  listremotes) printf '%s\n' "${FAKE_REMOTES-gdrive:      drive}" ;;
  lsf) printf 'Belgeler/\nFotoğraflar ve Videolar/\n' ;;
  lsd) exit "${LSD_EXIT:-0}" ;;
  check) [ -n "${FAKE_CHECK:-}" ] && cat "$FAKE_CHECK"; exit 1 ;;
esac
exit 0
'''


class SetupBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = self.t = pathlib.Path(self.tmp.name)
        self.src = t / "src"
        self.src.mkdir()
        for name in SCRIPTS:
            shutil.copy(ROOT / name, self.src / name)
            (self.src / name).chmod(0o644)  # a .plasmoid may lose exec bits
        self.home = t / "home"
        self.home.mkdir()
        self.calls = t / "calls"
        self.calls.mkdir()
        self.bin = t / "bin"
        self.bin.mkdir()
        self.fake("rclone", FAKE_RCLONE)
        self.fake("systemctl", '#!/bin/bash\necho "$*" >> "$CALLS/systemctl"\n'
                               'case "$*" in *is-active*) exit 3;; esac\nexit 0\n')
        self.fake("systemd-run", '#!/bin/bash\necho "$*" >> "$CALLS/systemd-run"\nexit 0\n')
        self.fake("loginctl", "#!/bin/bash\nexit 0\n")
        self.env = dict(os.environ, HOME=str(self.home), PATH=f"{self.bin}:/usr/bin:/bin",
                        CALLS=str(self.calls), XDG_RUNTIME_DIR=str(t / "run"))
        self.env.pop("XDG_CONFIG_HOME", None)
        self.env.pop("GDRIVE_LOCAL", None)
        self.env.pop("GDRIVE_REMOTE", None)
        self.env.pop("GDRIVE_MODE", None)
        self.state = self.home / ".local/state/gdrive-sync"

    def fake(self, name, body):
        p = self.bin / name
        p.write_text(body)
        p.chmod(0o755)

    def setup(self, *args, code=0, **env):
        p = subprocess.run([sys.executable, str(self.src / "gdrive-setup"), *args, "--json"],
                           env=dict(self.env, **env), capture_output=True, text=True)
        self.assertEqual(p.returncode, code, p.stderr)
        return json.loads(p.stdout)

    def rclone_calls(self):
        f = self.calls / "rclone"
        return [c.split("|")[:-1] for c in f.read_text().splitlines()] if f.exists() else []

    def systemctl_calls(self):
        f = self.calls / "systemctl"
        return f.read_text() if f.exists() else ""

    def write_config(self, local, mode="twoway", extra=""):
        cfg = self.home / ".config/gdrive-sync/config"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(f"REMOTE=gdrive:\nLOCAL={local}\nMODE={mode}\nVERSION=1\n{extra}")


class ShortStepsTest(SetupBase):
    def test_check(self):
        c = self.setup("check")
        self.assertTrue(c["rcloneOk"])
        self.assertEqual(c["rcloneVersion"], "1.75.2")

    def test_remotes_lists_drive_only_and_suggests_a_free_name(self):
        r = self.setup("remotes", FAKE_REMOTES="gdrive:      drive\nwork:        s3\nyedek:       drive")
        self.assertEqual([x["name"] for x in r["remotes"]], ["gdrive:", "yedek:"])
        self.assertEqual(r["suggestName"], "gdrive-sync-1:")
        r = self.setup("remotes", FAKE_REMOTES="")
        self.assertEqual((r["remotes"], r["suggestName"]), ([], "gdrive:"))

    def test_drive_folders(self):
        r = self.setup("drive-folders", "gdrive:", "Şirket/Belgeler")
        self.assertEqual(r["folders"], ["Belgeler", "Fotoğraflar ve Videolar"])
        lsf = [c for c in self.rclone_calls() if c[0] == "lsf"][0]
        self.assertEqual(lsf[1], "gdrive:Şirket/Belgeler")
        self.assertIn("--dirs-only", lsf)

    def test_check_local_refusals(self):
        self.write_config(self.home / "GoogleDrive")
        f = self.home / "file.txt"
        f.write_text("x")
        cases = {"/": "root", str(self.home): "home", str(self.home.parent): "home",
                 str(f): "file", str(self.home / "GoogleDrive/Sub"): "nested",
                 str(self.home / ".local/state"): "state", str(self.home / ".local/share/gdrive-sync/x"): "state"}
        for path, reason in cases.items():
            with self.subTest(path=path):
                r = self.setup("check-local", path)
                self.assertFalse(r["ok"])
                self.assertEqual(r["reason"], reason)

    def test_check_local_new_existing_and_ours(self):
        r = self.setup("check-local", str(self.home / "Yeni Klasör"))
        self.assertEqual((r["ok"], r["exists"], r["empty"], r["ours"]), (True, False, True, False))
        d = self.home / "Dolu"
        d.mkdir()
        (d / "a.txt").write_text("a")
        r = self.setup("check-local", str(d))
        self.assertEqual((r["ok"], r["exists"], r["empty"], r["ours"]), (True, True, False, False))
        self.state.mkdir(parents=True)
        (self.state / "setup.json").write_text(json.dumps(
            {"step": "apply", "state": "cancelled", "target": {"local": str(d)}}))
        self.assertTrue(self.setup("check-local", str(d))["ours"])
        self.assertTrue(self.setup("check-local", "~/Dolu")["ours"])

    def test_preview_counts_and_choice(self):
        d = self.home / "Dolu"
        d.mkdir()
        (d / "x").write_text("x")
        check = self.t / "check.txt"
        check.write_text("= same.txt\n- only drive.pdf\n- Klasör/iki.pdf\n+ only here.txt\n* changed.xlsx\n")
        r = self.setup("preview", "gdrive:", "", str(d), FAKE_CHECK=str(check))
        self.assertEqual((r["same"], r["onlyDrive"], r["onlyLocal"], r["different"]), (1, 2, 1, 1))
        self.assertTrue(r["needsChoice"])
        c = [c for c in self.rclone_calls() if c[0] == "check"][0]
        self.assertEqual(c[1:3], ["gdrive:", str(d)])
        check.write_text("= same.txt\n- only drive.pdf\n")
        self.assertFalse(self.setup("preview", "gdrive:", "", str(d), FAKE_CHECK=str(check))["needsChoice"])

    def test_preview_of_empty_folder_needs_no_check(self):
        r = self.setup("preview", "gdrive:", "Belgeler", str(self.home / "yok"))
        self.assertFalse(r["needsChoice"])
        self.assertTrue(r["empty"])
        self.assertFalse([c for c in self.rclone_calls() if c[0] == "check"])

    def test_migrate(self):
        self.assertFalse(self.setup("migrate")["migrated"])
        unit = self.home / ".config/systemd/user/gdrive-sync.service"
        unit.parent.mkdir(parents=True)
        unit.write_text("[Service]\n")
        self.state.mkdir(parents=True)
        (self.state / "initialized").touch()
        self.assertTrue(self.setup("migrate")["migrated"])


class InstallServiceTest(SetupBase):
    def test_install_copies_scripts_links_and_writes_unit_without_starting(self):
        r = self.setup("install-service")
        dest = self.home / ".local/share/gdrive-sync/bin"
        self.assertEqual(r["binDir"], str(dest))
        for name in SCRIPTS:
            self.assertTrue((dest / name).exists(), name)
        self.assertTrue(os.access(dest / "gdrive-syncd", os.X_OK))
        self.assertTrue(os.access(dest / "gdrive-status", os.X_OK))
        link = self.home / ".local/bin/gdrive-status"
        self.assertEqual(link.resolve(), (dest / "gdrive-status").resolve())
        unit = (self.home / ".config/systemd/user/gdrive-sync.service").read_text()
        self.assertIn(f'ExecStart="{dest}/gdrive-syncd"', unit)
        self.assertIn("daemon-reload", self.systemctl_calls())
        self.assertNotIn("enable", self.systemctl_calls())

    def test_start_enables_and_dev_links_the_checkout(self):
        self.setup("install-service", "--dev", "--start")
        link = self.home / ".local/bin/gdrive-setup"
        self.assertEqual(link.resolve(), (self.src / "gdrive-setup").resolve())
        self.assertFalse((self.home / ".local/share/gdrive-sync/bin").exists())
        self.assertIn("--user enable --now gdrive-sync.service", self.systemctl_calls())

    def test_user_file_in_local_bin_is_kept(self):
        b = self.home / ".local/bin"
        b.mkdir(parents=True)
        (b / "gdrive-sync").write_text("mine")
        r = self.setup("install-service")
        self.assertEqual((b / "gdrive-sync").read_text(), "mine")
        self.assertIn(str(b / "gdrive-sync"), r["skippedLinks"])


if __name__ == "__main__":
    unittest.main()
