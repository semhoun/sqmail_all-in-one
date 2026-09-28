#!/usr/bin/env python3
"""Private directory tests; run only in a disposable, uninitialized image."""

import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest


class StorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if (not Path('/.dockerenv').exists()
                or os.environ.get('SQMAIL_DISPOSABLE_TEST') != '1'
                or os.geteuid() != 0
                or Path('/var/qmail/control/aio-conf/mysql.conf').exists()):
            raise RuntimeError('Use a fresh disposable container without mail volumes')
        cls.prepare = staticmethod(runpy.run_path('/opt/libexec/delivery-admin-init')['prepare'])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='delivery-storage-', dir='/root')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_private_and_idempotent(self):
        target = self.root / 'backups'
        self.prepare(str(target))
        info = target.stat()
        self.assertEqual((info.st_uid, info.st_gid, info.st_mode & 0o777), (0, 0, 0o700))
        backup = target / 'existing'
        backup.write_bytes(b'previous backup')
        self.prepare(str(target))
        self.assertEqual(backup.read_bytes(), b'previous backup')

    def test_symlinks_rejected(self):
        real = self.root / 'real'
        real.mkdir(mode=0o755)
        link = self.root / 'link'
        link.symlink_to(real, target_is_directory=True)
        for path in (link, link / 'backups'):
            with self.subTest(path=path), self.assertRaises(OSError):
                self.prepare(str(path))
        self.assertEqual(real.stat().st_mode & 0o777, 0o755)
        self.assertFalse((real / 'backups').exists())

    def test_untrusted_owner_rejected(self):
        target = self.root / 'backups'
        target.mkdir(mode=0o700)
        os.chown(target, 89, 89)
        with self.assertRaises(PermissionError):
            self.prepare(str(target))
        self.assertEqual(target.stat().st_uid, 89)

    def test_writable_parent_rejected(self):
        parent = self.root / 'writable'
        parent.mkdir()
        parent.chmod(0o777)
        with self.assertRaises(PermissionError):
            self.prepare(str(parent / 'backups'))
        self.assertFalse((parent / 'backups').exists())

    def test_file_rejected(self):
        target = self.root / 'backups'
        target.write_bytes(b'not a directory')
        with self.assertRaises(OSError):
            self.prepare(str(target))
        self.assertEqual(target.read_bytes(), b'not a directory')

    def test_entrypoint(self):
        command = ['/usr/bin/python3', '-I', '/opt/libexec/delivery-admin-init']
        subprocess.run(command, check=True, timeout=10)
        subprocess.run(command, check=True, timeout=10)
        for path in ('/run/sqmail-delivery-admin', '/var/qmail/control/delivery-admin-backups'):
            info = Path(path).stat()
            self.assertEqual((info.st_uid, info.st_gid, info.st_mode & 0o777), (0, 0, 0o700))
        result = subprocess.run([*command, 'unexpected'], capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
