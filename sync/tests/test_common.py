"""Tests for sync/gdrive_common.py (config, legacy migration, requirement checks)."""
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import gdrive_common as gc  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.t = pathlib.Path(self.tmp.name)
        self.home = self.t / "home"
        self.home.mkdir()
        self.bin = self.t / "bin"
        self.bin.mkdir()
        self.env = {"HOME": str(self.home), "PATH": str(self.bin)}
        self.p = gc.paths(self.env)

    def fake(self, name, body):
        f = self.bin / name
        f.write_text("#!/bin/sh\n" + body + "\n")
        f.chmod(0o755)

    def legacy_install(self):
        unit = pathlib.Path(self.p["unit"])
        unit.parent.mkdir(parents=True)
        unit.write_text("[Service]\nExecStart=/x/gdrive-syncd\n")
        state = pathlib.Path(self.p["state"])
        state.mkdir(parents=True)
        (state / "initialized").touch()


class ConfigTest(Base):
    def test_paths(self):
        self.assertEqual(self.p["config"], f"{self.home}/.config/gdrive-sync/config")
        self.assertEqual(self.p["state"], f"{self.home}/.local/state/gdrive-sync")
        self.assertEqual(self.p["conflicts"], f"{self.home}/.local/share/gdrive-sync/backup")
        self.assertEqual(self.p["unit"], f"{self.home}/.config/systemd/user/gdrive-sync.service")
        env = dict(self.env, XDG_CONFIG_HOME=str(self.t / "cfg"))
        self.assertEqual(gc.paths(env)["config"], f"{self.t}/cfg/gdrive-sync/config")

    def test_round_trip_with_spaces_and_turkish(self):
        values = {"REMOTE": "gdrive:", "REMOTE_PATH": "Şirket/Belgeler 2026",
                  "LOCAL": "/home/u/Google Sürücü", "MODE": "download"}
        gc.write_config(self.p["config"], values)
        got = gc.read_config(self.p["config"])
        self.assertEqual(got, dict(values, VERSION="1"))
        text = pathlib.Path(self.p["config"]).read_text()
        self.assertTrue(text.startswith("REMOTE=gdrive:\n"))

    def test_garbled_or_missing_config_is_empty(self):
        self.assertEqual(gc.read_config(self.p["config"]), {})
        pathlib.Path(self.p["config"]).parent.mkdir(parents=True)
        pathlib.Path(self.p["config"]).write_bytes(b"\xff\xfe garbage\nnot a line\nEVIL=$(rm -rf /)\n")
        self.assertEqual(gc.read_config(self.p["config"]), {})

    def test_newline_in_value_is_refused(self):
        with self.assertRaises(ValueError):
            gc.write_config(self.p["config"], {"REMOTE": "gdrive:", "LOCAL": "/a\nMODE=upload"})

    def test_effective_target_and_env_override(self):
        self.assertIsNone(gc.effective(self.env))
        gc.write_config(self.p["config"], {"REMOTE": "gdrive:", "REMOTE_PATH": "A/B",
                                           "LOCAL": "/l", "MODE": "twoway"})
        e = gc.effective(self.env)
        self.assertEqual(e["target"], "gdrive:A/B")
        self.assertEqual(e["mode"], "twoway")
        self.assertFalse(e["createdRemote"])
        e = gc.effective(dict(self.env, GDRIVE_LOCAL="/other", GDRIVE_MODE="upload"))
        self.assertEqual((e["local"], e["mode"]), ("/other", "upload"))
        gc.write_config(self.p["config"], {"REMOTE": "gdrive:", "LOCAL": "/l", "MODE": "bogus"})
        self.assertEqual(gc.effective(self.env)["target"], "gdrive:")
        self.assertEqual(gc.effective(self.env)["mode"], "twoway")


class LegacyTest(Base):
    def test_not_legacy_without_unit_or_initialized(self):
        self.assertIsNone(gc.detect_legacy(self.env))
        unit = pathlib.Path(self.p["unit"])
        unit.parent.mkdir(parents=True)
        unit.write_text("x")
        self.assertIsNone(gc.detect_legacy(self.env))

    def test_legacy_detected_and_migrated_once(self):
        self.legacy_install()
        d = gc.detect_legacy(self.env)
        self.assertEqual(d["REMOTE"], "gdrive:")
        self.assertEqual(d["LOCAL"], f"{self.home}/GoogleDrive")
        self.assertEqual(d["MODE"], "twoway")
        self.assertTrue(gc.migrate_if_legacy(self.env))
        self.assertFalse(gc.migrate_if_legacy(self.env))
        cfg = gc.read_config(self.p["config"])
        self.assertEqual(cfg["LEGACY"], "1")
        self.assertEqual(gc.effective(self.env)["target"], "gdrive:")

    def test_legacy_honours_env_remote_with_path(self):
        self.legacy_install()
        gc.migrate_if_legacy(dict(self.env, GDRIVE_REMOTE="work:Backup", GDRIVE_LOCAL="/d"))
        cfg = gc.read_config(self.p["config"])
        self.assertEqual((cfg["REMOTE"], cfg["REMOTE_PATH"], cfg["LOCAL"]), ("work:", "Backup", "/d"))


class ChecksTest(Base):
    def test_old_rclone_is_not_ok(self):
        self.fake("rclone", 'echo "rclone v1.65.0"; echo "- os/version: x"')
        c = gc.checks(self.env)
        self.assertTrue(c["rclone"])
        self.assertEqual(c["rcloneVersion"], "1.65.0")
        self.assertFalse(c["rcloneOk"])

    def test_current_rclone_is_ok(self):
        self.fake("rclone", 'echo "rclone v1.75.2"')
        self.fake("systemctl", "exit 0")
        self.fake("systemd-run", "exit 0")
        self.fake("inotifywait", "exit 0")
        c = gc.checks(self.env)
        self.assertTrue(c["rcloneOk"] and c["systemd"] and c["inotify"] and c["python"])
        self.assertIsNone(c["installCommand"])

    def test_install_command_lists_only_missing_packages(self):
        self.fake("pacman", "exit 0")
        c = gc.checks(self.env)
        self.assertFalse(c["rclone"])
        self.assertEqual(c["pkgManager"], "pacman")
        self.assertEqual(c["installCommand"], "sudo pacman -S --needed rclone inotify-tools")
        self.fake("inotifywait", "exit 0")
        self.assertEqual(gc.checks(self.env)["installCommand"], "sudo pacman -S --needed rclone")

    def test_apt_gets_official_rclone_installer(self):
        self.fake("apt-get", "exit 0")
        self.fake("inotifywait", "exit 0")
        cmd = gc.checks(self.env)["installCommand"]
        self.assertIn("rclone.org/install.sh", cmd)


if __name__ == "__main__":
    unittest.main()
