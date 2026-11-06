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
for a; do case "${prev:-}" in --log-file) log="$a";; esac; prev="$a"; done
case "$1" in
  config)
    [ "$2" = create ] || exit 0
    echo "NOTICE: If your browser doesn't open automatically go to the following link: http://127.0.0.1:53682/auth?state=abc" >&2
    echo "NOTICE: Log in and authorize rclone for access" >&2
    exit "${CONNECT_EXIT:-0}" ;;
  bisync|copy|sync)
    [ -n "${log:-}" ] && echo "x INFO  : Bisync successful" >> "$log"
    if [ "$1" = sync ]; then  # imitate --backup-dir: local-only files move aside
      for a; do case "${p2:-}" in --backup-dir) bk="$a";; esac; p2="$a"; done
      mkdir -p "$bk"; [ -f "$3/only-here.txt" ] && mv "$3/only-here.txt" "$bk/"
    fi
    exit "${SYNC_EXIT:-0}" ;;
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
                               'case "$*" in *is-active*gdrive-sync.service*) [ -n "${FAKE_ACTIVE:-}" ] && exit 0; exit 3;;'
                               ' *is-active*) exit 3;; esac\nexit 0\n')
        # runs the detached command inline, with its --setenv values
        self.fake("systemd-run", '#!/bin/bash\necho "$*" >> "$CALLS/systemd-run"\n'
                                 'while [[ "$1" == --* ]]; do case "$1" in --setenv=*) export "${1#--setenv=}";; esac; shift; done\n'
                                 '"$@" > "$CALLS/detached.out" 2>&1\nexit 0\n')
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
                 str(self.home / ".local/state"): "state", str(self.home / ".local/share/gdrive-sync/x"): "state",
                 "/home/kullanici-yok/GoogleDrive": "not_writable"}
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


class DetachedTest(SetupBase):
    def setup_json(self):
        return json.loads((self.state / "setup.json").read_text())

    def config(self):
        f = self.home / ".config/gdrive-sync/config"
        return f.read_text() if f.exists() else None

    def detached_out(self):
        f = self.calls / "detached.out"
        return f.read_text() if f.exists() else ""

    def test_connect_runs_detached_with_display_env_and_records_url(self):
        r = self.setup("connect", "gdrive:", DISPLAY=":0", WAYLAND_DISPLAY="wayland-0", FAKE_REMOTES="")
        self.assertTrue(r["started"])
        run = (self.calls / "systemd-run").read_text()
        self.assertIn("--unit=gdrive-setup-connect", run)
        self.assertIn("--setenv=WAYLAND_DISPLAY=wayland-0", run)
        sj = self.setup_json()
        self.assertEqual((sj["step"], sj["state"]), ("connect", "done"), self.detached_out())
        self.assertEqual(sj["authUrl"], "http://127.0.0.1:53682/auth?state=abc")
        self.assertTrue(sj["createdRemote"])
        create = [c for c in self.rclone_calls() if c[:2] == ["config", "create"]][0]
        self.assertEqual(create[2:5], ["gdrive", "drive", "scope=drive"])

    def test_connect_failure_removes_half_created_remote(self):
        self.setup("connect", "gdrive:", CONNECT_EXIT="1", FAKE_REMOTES="")
        self.assertEqual(self.setup_json()["state"], "failed")
        self.assertTrue([c for c in self.rclone_calls() if c[:3] == ["config", "delete", "gdrive"]])

    def test_connect_refuses_a_name_that_is_taken(self):
        r = self.setup("connect", "work:", FAKE_REMOTES="work:   s3")
        self.assertEqual(r["error"], "name_taken")

    def test_apply_twoway_into_empty_folder(self):
        local = self.home / "Google Drive"
        r = self.setup("apply", "gdrive:", "", str(local), "twoway", "empty")
        self.assertTrue(r["started"])
        sj = self.setup_json()
        self.assertEqual(sj["state"], "done", self.detached_out())
        calls = self.rclone_calls()
        bisync = [c for c in calls if c[0] == "bisync"]
        self.assertEqual(len(bisync), 1)
        self.assertIn("--resync", bisync[0])
        self.assertEqual(bisync[0][1:3], [str(local), "gdrive:"])
        self.assertFalse([c for c in calls if c[0] == "sync"])
        self.assertIn(f"LOCAL={local}\n", self.config())
        self.assertIn("MODE=twoway\n", self.config())
        self.assertTrue((self.state / "initialized").exists())
        self.assertIn("--user enable --now gdrive-sync.service", self.systemctl_calls())

    def test_apply_match_moves_local_only_files_aside_first(self):
        local = self.home / "GD"
        local.mkdir()
        (local / "only-here.txt").write_text("x")
        self.setup("apply", "gdrive:", "Belgeler", str(local), "twoway", "match")
        self.assertEqual(self.setup_json()["state"], "done", self.detached_out())
        verbs = [c[0] for c in self.rclone_calls() if c[0] in ("sync", "bisync")]
        self.assertEqual(verbs, ["sync", "bisync"])
        sync = [c for c in self.rclone_calls() if c[0] == "sync"][0]
        self.assertEqual(sync[1:3], ["gdrive:Belgeler", str(local)])
        aside = list((self.home / ".local/share/gdrive-sync").glob("set-aside-*/only-here.txt"))
        self.assertEqual(len(aside), 1)
        self.assertIn("REMOTE_PATH=Belgeler\n", self.config())

    def test_apply_refuses_empty_choice_for_a_full_folder(self):
        local = self.home / "GD"
        local.mkdir()
        (local / "a.txt").write_text("x")
        r = self.setup("apply", "gdrive:", "", str(local), "twoway", "empty")
        self.assertEqual(r["error"], "needs_choice")
        self.assertFalse((self.calls / "systemd-run").exists())

    def test_apply_one_way_modes(self):
        for mode, verb_order in (("download", ["gdrive:", None]), ("upload", [None, "gdrive:"])):
            with self.subTest(mode=mode):
                (self.calls / "rclone").unlink(missing_ok=True)
                local = self.home / f"GD-{mode}"
                self.setup("apply", "gdrive:", "", str(local), mode, "none")
                self.assertEqual(self.setup_json()["state"], "done", self.detached_out())
                copy = [c for c in self.rclone_calls() if c[0] == "copy"][0]
                self.assertEqual(copy[1:3], ["gdrive:", str(local)] if mode == "download" else [str(local), "gdrive:"])
                self.assertFalse([c for c in self.rclone_calls() if c[0] == "bisync"])
                self.assertIn(f"MODE={mode}\n", self.config())

    def test_failed_first_sync_writes_no_config_and_enables_nothing(self):
        self.setup("apply", "gdrive:", "", str(self.home / "GD"), "twoway", "empty", SYNC_EXIT="2")
        sj = self.setup_json()
        self.assertEqual(sj["state"], "failed")
        self.assertIsNone(self.config())
        self.assertNotIn("enable", self.systemctl_calls())
        self.assertTrue(self.setup("check-local", str(self.home / "GD"))["ours"])

    def test_folder_that_cannot_be_created_is_refused_before_anything_runs(self):
        ro = self.t / "ro"
        ro.mkdir()
        ro.chmod(0o500)
        self.addCleanup(ro.chmod, 0o700)
        r = self.setup("apply", "gdrive:", "", str(ro / "GD"), "twoway", "empty", FAKE_ACTIVE="1")
        self.assertEqual(r["error"], "local_not_writable")
        self.assertFalse((self.calls / "systemd-run").exists())
        self.assertNotIn("stop gdrive-sync.service", self.systemctl_calls())

    def test_failed_first_sync_restarts_the_previous_service(self):
        self.setup("apply", "gdrive:", "", str(self.home / "GD"), "twoway", "empty", FAKE_ACTIVE="1", SYNC_EXIT="2")
        self.assertEqual(self.setup_json()["state"], "failed")
        calls = self.systemctl_calls()
        self.assertLess(calls.index("--user stop gdrive-sync.service"), calls.index("--user start gdrive-sync.service"))
        self.assertNotIn("enable", calls)

    def test_nothing_is_installed_before_the_first_sync_succeeded(self):
        self.setup("apply", "gdrive:", "", str(self.home / "GD"), "twoway", "empty", SYNC_EXIT="2")
        self.assertEqual(self.setup_json()["state"], "failed")
        self.assertFalse((self.home / ".config/systemd/user/gdrive-sync.service").exists())
        self.assertFalse((self.home / ".local/bin/gdrive-status").exists())
        self.assertFalse((self.home / ".local/share/gdrive-sync/bin").exists())

    def test_offline_apply_fails(self):
        self.setup("apply", "gdrive:", "", str(self.home / "GD"), "download", "none", LSD_EXIT="1")
        self.assertEqual(self.setup_json()["error"]["code"], "offline")
        self.assertIsNone(self.config())

    def test_created_remote_is_recorded_from_connect(self):
        self.setup("connect", "gdrive:", FAKE_REMOTES="")
        self.setup("apply", "gdrive:", "", str(self.home / "GD"), "download", "none")
        self.assertIn("CREATED_REMOTE=1\n", self.config())

    def test_cancel_marks_cancelled_and_keeps_target(self):
        self.state.mkdir(parents=True)
        (self.state / "setup.json").write_text(json.dumps(
            {"step": "apply", "state": "running", "unit": "gdrive-setup-apply.service",
             "target": {"local": str(self.home / "GD")}}))
        r = self.setup("cancel")
        self.assertTrue(r["ok"])
        self.assertIn("--user stop gdrive-setup-apply.service", self.systemctl_calls())
        self.assertEqual(self.setup_json()["state"], "cancelled")
        self.assertTrue(self.setup("check-local", str(self.home / "GD"))["ours"])

    def test_cancelled_login_removes_the_half_made_connection(self):
        self.state.mkdir(parents=True)
        (self.state / "setup.json").write_text(json.dumps(
            {"step": "connect", "state": "running", "unit": "gdrive-setup-connect.service", "remote": "gdrive:"}))
        self.setup("cancel")
        self.assertIn("--user stop gdrive-setup-connect.service", self.systemctl_calls())
        self.assertTrue([c for c in self.rclone_calls() if c[:3] == ["config", "delete", "gdrive"]])

    def test_disconnect_keeps_files_and_foreign_remote(self):
        local = self.home / "GD"
        local.mkdir()
        (local / "a.txt").write_text("x")
        self.write_config(local)
        self.state.mkdir(parents=True)
        (self.state / "initialized").touch()
        unit = self.home / ".config/systemd/user/gdrive-sync.service"
        unit.parent.mkdir(parents=True)
        unit.write_text("[Service]\n")
        r = self.setup("disconnect", "--delete-remote")
        self.assertTrue(r["ok"])
        self.assertFalse(r["remoteDeleted"])
        self.assertTrue((local / "a.txt").exists())
        self.assertIsNone(self.config())
        self.assertTrue(list((self.home / ".config/gdrive-sync").glob("config.bak-*")))
        self.assertFalse((self.state / "initialized").exists())
        self.assertFalse(unit.exists())
        self.assertIn("--user disable --now gdrive-sync.service", self.systemctl_calls())
        self.assertFalse([c for c in self.rclone_calls() if c[:2] == ["config", "delete"]])
        # no silent re-migration afterwards
        self.assertFalse(self.setup("migrate")["migrated"])

    def test_disconnect_deletes_remote_created_by_setup_only_when_asked(self):
        self.write_config(self.home / "GD", extra="CREATED_REMOTE=1\n")
        r = self.setup("disconnect", "--delete-remote")
        self.assertTrue(r["remoteDeleted"])
        self.assertTrue([c for c in self.rclone_calls() if c[:3] == ["config", "delete", "gdrive"]])


class WizardTest(SetupBase):
    def wizard(self, answers, **env):
        return subprocess.run([sys.executable, str(self.src / "gdrive-setup"), "wizard"], input=answers,
                              env=dict(self.env, LANG="en_US.UTF-8", **env), capture_output=True, text=True)

    def test_happy_path_with_defaults(self):
        local = self.home / "Google Drive"
        # account 1 (gdrive:), whole Drive, folder, two-way, confirm
        p = self.wizard(f"\n\n{local}\n\n\n")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        cfg = (self.home / ".config/gdrive-sync/config").read_text()
        self.assertIn(f"LOCAL={local}\n", cfg)
        self.assertIn("MODE=twoway\n", cfg)
        self.assertIn("--user enable --now gdrive-sync.service", self.systemctl_calls())
        self.assertIn("Done.", p.stdout)

    def test_browse_drive_folder_and_download_only(self):
        # account 1, choose a folder -> pick "Belgeler" (3rd option: use this / Belgeler / Foto...)
        # -> inside Belgeler: use this (1); local; mode 3; confirm
        p = self.wizard(f"1\n2\n2\n1\n{self.home / 'B'}\n3\ny\n")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        cfg = (self.home / ".config/gdrive-sync/config").read_text()
        self.assertIn("REMOTE_PATH=Belgeler\n", cfg)
        self.assertIn("MODE=download\n", cfg)

    def test_refused_folder_is_asked_again_and_full_folder_offers_choices(self):
        full = self.home / "Dolu"
        full.mkdir()
        (full / "only-here.txt").write_text("x")
        check = self.t / "check.txt"
        check.write_text("+ only-here.txt\n- a.pdf\n")
        # home refused -> full folder -> two-way -> choice 2 (match) -> confirm
        p = self.wizard(f"\n\n{self.home}\n{full}\n1\n2\n\n", FAKE_CHECK=str(check))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("Not your home folder", p.stdout)
        self.assertIn("only here: 1", p.stdout)
        self.assertTrue(list((self.home / ".local/share/gdrive-sync").glob("set-aside-*/only-here.txt")))

    def test_missing_rclone_shows_install_command(self):
        self.fake("pacman", "#!/bin/sh\nexit 0\n")
        p = self.wizard("", GDRIVE_RCLONE="no-such-rclone")
        self.assertEqual(p.returncode, 1)
        self.assertIn("sudo pacman -S --needed rclone", p.stdout)

    def test_no_args_without_terminal_prints_usage(self):
        p = subprocess.run([sys.executable, str(self.src / "gdrive-setup")], input="", env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("gdrive-setup <step>", p.stderr)


class ShowSetupTest(SetupBase):
    def show(self):
        p = subprocess.run([sys.executable, str(self.src / "gdrive-status"), "show"],
                           env=dict(self.env, GDRIVE_SYSTEMCTL=str(self.bin / "systemctl")),
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_running_setup_whose_unit_is_gone_is_interrupted(self):
        self.state.mkdir(parents=True)
        (self.state / "setup.json").write_text(json.dumps(
            {"step": "apply", "state": "running", "unit": "gdrive-setup-apply.service"}))
        s = self.show()
        self.assertEqual(s["state"], "unconfigured")
        self.assertEqual(s["setup"]["state"], "failed")
        self.assertEqual(s["setup"]["error"]["code"], "interrupted")

    def test_setup_is_reported_when_configured_too(self):
        self.write_config(self.home / "GD")
        self.state.mkdir(parents=True)
        (self.state / "setup.json").write_text(json.dumps({"step": "apply", "state": "done"}))
        self.assertEqual(self.show()["setup"]["state"], "done")


if __name__ == "__main__":
    unittest.main()
