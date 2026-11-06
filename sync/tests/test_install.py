"""Kurulumu gerçek systemd ve Drive hesabına dokunmadan sınar."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source = self.base / 'script folder % test'
        self.source.mkdir()
        for name in ('install.sh', 'gdrive-sync', 'gdrive-syncd', 'gdrive-status', 'gdrive-nfc', 'gdrive_common.py', 'gdrive-lib.sh'):
            if (ROOT / name).exists():
                shutil.copy(ROOT / name, self.source / name)
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        self.home = self.base / 'home'
        self.home.mkdir()
        self.env = dict(os.environ, HOME=str(self.home),
                        XDG_CONFIG_HOME=str(self.home / '.config'),
                        PATH=f'{self.bin}:/usr/bin:/bin',
                        CALLS=str(self.base / 'calls'))
        # These commands affect the host or contact Google, so replace only them.
        self.command('rclone', 'echo gdrive:')
        self.command('systemctl', 'printf "%s\\n" "$*" >> "$CALLS"')
        self.command('loginctl', 'echo yes')
        self.command('inotifywait', 'exit 0')

    def command(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/bash\n' + body + '\n')
        path.chmod(0o755)

    def run_install(self):
        return subprocess.run(['bash', str(self.source / 'install.sh')],
                              env=self.env, cwd='/', stdin=subprocess.DEVNULL,
                              capture_output=True, text=True)

    def test_install_and_repeat_preserve_sync_state(self):
        state = self.home / '.local/state/gdrive-sync'
        state.mkdir(parents=True)
        marker = state / 'initialized'
        marker.write_text('keep')
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        unit = self.home / '.config/systemd/user/gdrive-sync.service'
        content = unit.read_text()
        self.assertIn('script folder %% test/gdrive-syncd"', content)
        checked = subprocess.run(['systemd-analyze', '--user', 'verify', str(unit)],
                                 capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn('--user enable --now gdrive-sync.service',
                      (self.base / 'calls').read_text())
        (self.base / 'calls').write_text('')
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(unit.read_text(), content)
        self.assertEqual(marker.read_text(), 'keep')
        self.assertNotIn('restart', (self.base / 'calls').read_text())
        link = self.home / '.local/bin/gdrive-status'
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), (self.source / 'gdrive-status').resolve())

    def test_existing_user_file_in_local_bin_is_not_overwritten(self):
        bin_dir = self.home / '.local/bin'
        bin_dir.mkdir(parents=True)
        (bin_dir / 'gdrive-status').write_text('mine')
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((bin_dir / 'gdrive-status').read_text(), 'mine')
        self.assertIn('dokunulmadi', result.stderr)

    def test_missing_remote_stops_before_service_install(self):
        self.command('rclone', 'echo unrelated:')
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('gdrive', result.stderr)
        self.assertFalse((self.home / '.config/systemd/user/gdrive-sync.service').exists())


if __name__ == '__main__':
    unittest.main()
