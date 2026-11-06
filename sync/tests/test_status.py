"""Tests for sync/gdrive-status (stdlib unittest; run: python3 -m unittest discover -s sync/tests)."""
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "gdrive-status"
FIX = HERE / "fixtures"


def load_module():
    loader = importlib.machinery.SourceFileLoader("gdrive_status", str(SCRIPT))
    spec = importlib.util.spec_from_loader("gdrive_status", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


gs = load_module()


class ParseRunTest(unittest.TestCase):
    def test_mixed_run_changes_with_kinds_and_relative_paths(self):
        r = gs.parse_run((FIX / "run_mixed.log").read_text(), "/home/u/GoogleDrive")
        self.assertEqual(r["changes"], [
            {"kind": "up", "path": "Şirket/Teklif 2026 [Conflict].pdf"},
            {"kind": "deleted_remote", "path": "Eski/eski.txt"},
            {"kind": "down", "path": "Proje/Liste.xlsx"},
            {"kind": "deleted_local", "path": "Telefon yedekleri/Rapor.pdf"},
        ])

    def test_mixed_run_in_progress_phase_progress_and_done_flags(self):
        r = gs.parse_run((FIX / "run_mixed.log").read_text(), "/home/u/GoogleDrive/")
        self.assertEqual(r["phase"], "transferring")
        self.assertEqual(r["progress"], {"done": 1, "total": 2})
        self.assertFalse(r["ok"])
        self.assertIsNone(r["error"])
        done = {c["path"]: c["done"] for c in r["current"]}
        self.assertTrue(done["Proje/Liste.xlsx"])
        self.assertTrue(done["Telefon yedekleri/Rapor.pdf"])
        self.assertFalse(done["Şirket/Teklif 2026 [Conflict].pdf"])

    def test_do_queued_copies_is_not_a_change(self):
        r = gs.parse_run((FIX / "run_mixed.log").read_text(), "/home/u/GoogleDrive")
        self.assertNotIn("Path1", [c["path"] for c in r["changes"]])
        self.assertNotIn("Path2", [c["path"] for c in r["changes"]])

    def test_real_upload_run_is_ok_with_one_upload(self):
        r = gs.parse_run((FIX / "run_upload_real.log").read_text(), "/home/user/GoogleDrive")
        self.assertTrue(r["ok"])
        self.assertEqual(r["phase"], "saving")
        self.assertEqual(r["changes"], [{"kind": "up", "path": "Notes/server.txt"}])
        self.assertEqual(r["progress"], {"done": 1, "total": 1})

    def test_real_out_of_sync_run_error_code_and_lines(self):
        r = gs.parse_run((FIX / "run_out_of_sync.log").read_text(), "/home/user/GoogleDrive")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"]["code"], "out_of_sync")
        self.assertLessEqual(len(r["error"]["lines"]), 4)
        self.assertTrue(any("out of sync" in l for l in r["error"]["lines"]))

    def test_phase_markers(self):
        self.assertEqual(gs.parse_run("x INFO  : Building Path1 and Path2 listings\n", "/l")["phase"], "listing")
        self.assertEqual(gs.parse_run("x INFO  : Path1 checking for diffs\n", "/l")["phase"], "comparing")
        self.assertIsNone(gs.parse_run("", "/l")["phase"])

    def test_copy_down_log_all_changes_are_downloads(self):
        r = gs.parse_run((FIX / "run_copy_down.log").read_text(), "/l", mode="download")
        self.assertEqual(r["changes"], [{"kind": "down", "path": p} for p in
                                        ["b.txt.conflict1", "link.desktop", "b.txt.conflict2", "a.txt"]])
        self.assertEqual(r["progress"], {"done": 4, "total": 4})
        self.assertEqual(r["phase"], "transferring")
        self.assertTrue(r["ok"])
        self.assertIsNone(r["error"])
        self.assertTrue(all(c["done"] for c in r["current"]))

    def test_copy_up_log_all_changes_are_uploads(self):
        r = gs.parse_run((FIX / "run_copy_up.log").read_text(), "/l", mode="upload")
        self.assertEqual(r["changes"], [{"kind": "up", "path": "a.txt"},
                                        {"kind": "up", "path": "Alt Klasör/Şirket teklif.pdf"}])
        self.assertEqual(r["progress"], {"done": 2, "total": 2})

    def test_copy_error_is_not_ok(self):
        r = gs.parse_run("x ERROR : a.txt: Failed to copy: googleapi: Error 403: insufficientFilePermissions\n",
                         "/l", mode="upload")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"]["code"], "permission")

    def test_conflicts_from_loser_delete_and_tie_rename(self):
        text = ("x NOTICE: - WARNING  New or changed in both paths       - same.txt\n"
                "x NOTICE: - Path1    Deleting Path1 copy                - /l/Dir/a.txt\n"
                "x NOTICE: - Path1    Renaming Path1 copy                - /l/b.txt.conflict1\n"
                "x NOTICE: - Path2    Renaming Path2 copy                - gdrive{X}:Docs/b.txt.conflict2\n")
        r = gs.parse_run(text, "/l", remote_path="Docs")
        self.assertEqual(r["changes"], [{"kind": "conflict", "path": "Dir/a.txt"},
                                        {"kind": "conflict", "path": "b.txt"}])

    def test_remote_path_is_stripped_from_queue_lines(self):
        text = "x INFO  : - Path1   Queue copy to Path2   - gdrive{AB}:Belgeler/2026/x y.pdf\n"
        r = gs.parse_run(text, "/l", remote_path="Belgeler/2026")
        self.assertEqual(r["changes"], [{"kind": "up", "path": "x y.pdf"}])

    def test_duplicates_on_drive_are_collected(self):
        text = ("x NOTICE: Rapor.pdf: Duplicate object found in source - ignoring\n"
                "x NOTICE: Proje/Eski: Duplicate directory found in source - ignoring\n"
                "x NOTICE: Rapor.pdf: Duplicate object found in source - ignoring\n")
        self.assertEqual(gs.parse_run(text, "/l")["duplicates"], ["Rapor.pdf", "Proje/Eski"])

    def test_byte_transfer_line_is_not_file_progress(self):
        r = gs.parse_run("Transferred:   \t    0 B / 0 B, -, 0 B/s, ETA -\n", "/l")
        self.assertIsNone(r["progress"])


class ClassifyTest(unittest.TestCase):
    def test_codes(self):
        cases = {
            "NOTICE: Failed to bisync: prior lock file found: /x.lck": "lock",
            "ERROR : Bisync critical error: path1 and path2 are out of sync, run --resync": "out_of_sync",
            "ERROR : Safety abort: too many deletes (>25%, 30 of 100) on Path2": "too_many_deletes",
            "Couldn't delete: googleapi: Error 403: x, insufficientFilePermissions": "permission",
            'couldn\'t fetch token: oauth2: "invalid_grant" "Token has been expired or revoked."': "auth",
            "ERROR : something odd": "unknown",
        }
        for text, code in cases.items():
            with self.subTest(code=code):
                self.assertEqual(gs.classify(text), code)


class CliBase(unittest.TestCase):
    """Temp HOME with a config and a fake systemctl."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = pathlib.Path(self.tmp.name)
        self.state = t / "state"
        self.state.mkdir()
        self.log = self.state / "sync.log"
        self.bisync = t / "bisync"
        self.bisync.mkdir()
        self.run = t / "run"
        self.run.mkdir()
        self.bin = t / "bin"
        self.bin.mkdir()
        self.svc = t / "svc_active"
        fake = self.bin / "systemctl"
        fake.write_text("#!/bin/sh\n"
                        f'echo "$@" >> "{t}/systemctl_calls"\n'
                        'case "$*" in *is-active*) '
                        f'[ -f "{self.svc}" ] && {{ echo active; exit 0; }} || {{ echo inactive; exit 3; }};; esac\n'
                        "exit 0\n")
        fake.chmod(0o755)
        self.home = t / "home"
        (self.home / ".config/gdrive-sync").mkdir(parents=True)
        (self.home / ".config/gdrive-sync/config").write_text(
            "REMOTE=gdrive:\nLOCAL=/home/u/GoogleDrive\nMODE=twoway\nVERSION=1\n")
        self.env = dict(os.environ,
                        HOME=str(self.home), PATH=f"{self.bin}:/usr/bin:/bin",
                        GDRIVE_LOCAL="/home/u/GoogleDrive",
                        GDRIVE_STATE=str(self.state),
                        GDRIVE_BISYNC_DIR=str(self.bisync),
                        GDRIVE_SYSTEMCTL=str(fake),
                        XDG_RUNTIME_DIR=str(self.run))
        self.svc.touch()

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        p = subprocess.run([sys.executable, str(SCRIPT), *args], env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def status(self):
        return json.loads((self.state / "status.json").read_text())

    def show(self):
        return json.loads(self.cli("show"))


class CliTest(CliBase):
    """begin/end/show round trips."""

    def test_missing_status_shows_missing(self):
        s = self.show()
        self.assertEqual(s["state"], "missing")
        self.assertTrue(s["serviceActive"])

    def test_corrupt_status_is_treated_as_missing(self):
        (self.state / "status.json").write_text('{"state": "syn')
        self.assertEqual(self.show()["state"], "missing")

    def test_begin_end_ok_round_trip(self):
        self.log.write_text("old line\n")
        self.cli("begin")
        st = self.status()
        self.assertEqual(st["state"], "syncing")
        self.assertEqual(st["logOffset"], len("old line\n"))
        with self.log.open("a") as f:
            f.write((FIX / "run_mixed.log").read_text())
            f.write("2026/11/06 14:01:13 INFO  : Şirket/Teklif 2026 [Conflict].pdf: Copied (new)\n"
                    "2026/11/06 14:01:13 INFO  : Updating listings\n"
                    "2026/11/06 14:01:14 INFO  : Bisync successful\n")
        (self.bisync / "home_u_GoogleDrive..gdrive_.path1.lst").write_text(
            '# bisync listing\n- 1 md5 - 2026 "a.txt"\nd -1 - - 2026 "dir"\n- 2 md5 - 2026 "dir/b.txt"\n')
        self.cli("end", "ok")
        st = self.status()
        self.assertEqual(st["state"], "synced")
        self.assertEqual(st["fileCount"], 2)
        self.assertEqual(st["failCount"], 0)
        self.assertIsNone(st["lastError"])
        self.assertEqual([c["kind"] for c in st["recent"]], ["up", "deleted_remote", "down", "deleted_local"])
        self.assertTrue(all("at" in c for c in st["recent"]))
        self.assertEqual(st["lastSuccessAt"], st["lastRunAt"])

    def test_file_count_uses_the_listing_of_our_pair(self):
        self.log.write_text("")
        ours = self.bisync / "home_u_GoogleDrive..gdrive_.path1.lst"
        ours.write_text('- 1 md5 - 2026 "a.txt"\n')
        other = self.bisync / "tmp_scratch_local..gdrive__test.path1.lst"
        other.write_text('- 1 md5 - 2026 "a"\n- 1 md5 - 2026 "b"\n- 1 md5 - 2026 "c"\n')
        os.utime(ours, (1, 1))
        self.cli("begin")
        self.cli("end", "ok")
        self.assertEqual(self.status()["fileCount"], 1)

    def test_one_way_file_count_walks_the_folder(self):
        local = pathlib.Path(self.tmp.name) / "local"
        (local / "d" / ".venv").mkdir(parents=True)
        (local / "a.txt").write_text("a")
        (local / "d" / "b.txt").write_text("b")
        (local / "d" / ".venv" / "junk.py").write_text("x")
        self.env.update(GDRIVE_LOCAL=str(local), GDRIVE_MODE="download")
        self.log.write_text("")
        self.cli("begin")
        self.cli("end", "ok")
        st = self.status()
        self.assertEqual(st["fileCount"], 2)
        self.assertEqual(st["mode"], "download")
        self.assertEqual(self.show()["mode"], "download")
        self.assertTrue(st["backupDir"].endswith("/.local/share/gdrive-sync/backup"))

    def test_end_fail_reads_fail_counter_and_keeps_last_success(self):
        self.log.write_text("")
        self.cli("begin")
        self.cli("end", "ok")
        ok_at = self.status()["lastSuccessAt"]
        self.cli("begin")
        with self.log.open("a") as f:
            f.write((FIX / "run_out_of_sync.log").read_text())
        (self.state / "ardisik_hata").write_text("3\n")
        self.cli("end", "fail")
        st = self.status()
        self.assertEqual(st["state"], "error")
        self.assertEqual(st["failCount"], 3)
        self.assertEqual(st["lastError"]["code"], "out_of_sync")
        self.assertEqual(st["lastSuccessAt"], ok_at)

    def test_recent_is_capped_at_50_newest_first(self):
        self.log.write_text("")
        for i in range(30):
            self.cli("begin")
            with self.log.open("a") as f:
                f.write(f'x INFO  : - Path1   Queue copy to Path2   - gdrive{{A}}:/f{i}a.txt\n'
                        f'x INFO  : - Path1   Queue copy to Path2   - gdrive{{A}}:/f{i}b.txt\n')
            self.cli("end", "ok")
        rec = self.status()["recent"]
        self.assertEqual(len(rec), 50)
        self.assertEqual(rec[0]["path"], "f29a.txt")

    def test_offset_beyond_rotated_log_parses_from_start(self):
        self.log.write_text("x" * 1000 + "\n")
        self.cli("begin")
        self.log.write_text('x INFO  : - Path2   Queue copy to Path1   - /home/u/GoogleDrive/new.pdf\n')
        self.cli("end", "ok")
        self.assertEqual(self.status()["recent"][0], {**self.status()["recent"][0], "kind": "down", "path": "new.pdf"})

    def test_show_syncing_overlays_live_phase(self):
        self.log.write_text("")
        self.cli("begin")
        with self.log.open("a") as f:
            f.write((FIX / "run_mixed.log").read_text())
        s = self.show()
        self.assertEqual(s["state"], "syncing")
        self.assertEqual(s["phase"], "transferring")
        self.assertEqual(s["progress"], {"done": 1, "total": 2})
        self.assertEqual(len(s["current"]), 4)
        self.assertEqual(s["localRoot"], "/home/u/GoogleDrive")

    def test_show_stale_syncing_with_stopped_service_is_paused(self):
        self.log.write_text("")
        self.cli("begin")
        self.svc.unlink()
        s = self.show()
        self.assertEqual(s["state"], "paused")
        self.assertFalse(s["serviceActive"])

    def test_end_offline(self):
        self.log.write_text("")
        self.cli("begin")
        self.cli("end", "offline")
        self.assertEqual(self.status()["state"], "offline")

    def test_now_touches_trigger(self):
        self.cli("now")
        self.assertTrue((self.run / "gdrive-sync" / "now").exists())

    def test_pause_and_resume_call_systemctl(self):
        self.cli("pause")
        self.cli("resume")
        calls = (pathlib.Path(self.tmp.name) / "systemctl_calls").read_text()
        self.assertIn("--user stop gdrive-sync.service", calls)
        self.assertIn("--user start gdrive-sync.service", calls)


class SetupStateTest(CliBase):
    """No config: legacy installs are migrated silently, new machines report 'unconfigured'."""

    def setUp(self):
        super().setUp()
        (self.home / ".config/gdrive-sync/config").unlink()
        self.env.pop("GDRIVE_LOCAL")
        self.env["GDRIVE_STATE"] = str(self.home / ".local/state/gdrive-sync")
        self.state = pathlib.Path(self.env["GDRIVE_STATE"])
        self.state.mkdir(parents=True)

    def test_new_machine_is_unconfigured_with_checks(self):
        s = self.show()
        self.assertEqual(s["state"], "unconfigured")
        self.assertIn("rcloneOk", s["checks"])
        self.assertIsNone(s["setup"])
        self.assertFalse((self.home / ".config/gdrive-sync/config").exists())

    def test_legacy_install_is_migrated_without_a_sync(self):
        unit = self.home / ".config/systemd/user/gdrive-sync.service"
        unit.parent.mkdir(parents=True)
        unit.write_text("[Service]\n")
        (self.state / "initialized").touch()
        (self.state / "status.json").write_text('{"state": "synced"}')
        s = self.show()
        self.assertEqual(s["state"], "synced")
        cfg = (self.home / ".config/gdrive-sync/config").read_text()
        self.assertIn("MODE=twoway\n", cfg)
        self.assertIn(f"LOCAL={self.home}/GoogleDrive\n", cfg)
        self.assertIn("LEGACY=1\n", cfg)
        calls = pathlib.Path(self.tmp.name) / "systemctl_calls"
        self.assertNotIn("start", calls.read_text() if calls.exists() else "")

    def test_setup_json_is_passed_through_and_garbage_is_null(self):
        (self.state / "setup.json").write_text('{"step": "connect", "state": "running"}')
        self.assertEqual(self.show()["setup"]["step"], "connect")
        (self.state / "setup.json").write_text('{"step": "conn')
        self.assertIsNone(self.show()["setup"])



if __name__ == "__main__":
    unittest.main()
