#!/usr/bin/env python3
"""Pure tests: no runtime scripts, live configuration, or database access."""

from pathlib import Path
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'rootfs/opt/lib'))
from mail_stats.config import (CRON_BEGIN, CRON_END, CRON_JOB, atomic_json, cron_text,
                               instance_identity, load_private, settings)


class ConfigurationTests(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(settings({}), (True, 6))

    def test_limits(self):
        for value in ('1', '6', '120', '006'):
            self.assertEqual(settings({'MAIL_STATS_HISTORY_MONTHS': value}), (True, int(value)))
        self.assertEqual(settings({'MAIL_STATS_ENABLED': '0'}), (False, 6))

    def test_invalid_never_falls_back(self):
        for value in ('', '0', '121', '-1', '+6', '6.0', ' 6', '6 ', 'unlimited', '1\n', '\u0666'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                settings({'MAIL_STATS_HISTORY_MONTHS': value})
        for value in ('', 'true', 'false', '2', '01'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                settings({'MAIL_STATS_ENABLED': value})
        with self.assertRaises(ValueError):
            settings({'MAIL_STATS_ENABLED': '0', 'MAIL_STATS_HISTORY_MONTHS': 'wrong'})

    def test_crontab_preservation_and_idempotence(self):
        original = '!stdout(yes),mail(no)\n# Custom task\n0 1 * * * /custom\n'
        enabled = cron_text(original, True)
        self.assertTrue(enabled.startswith(original))
        self.assertEqual(enabled.count(CRON_JOB), 1)
        self.assertEqual(cron_text(enabled, True), enabled)
        self.assertEqual(cron_text(enabled, False), original)
        self.assertEqual(cron_text(original, False), original)

    def test_broken_block_preserves_safety(self):
        for text in (CRON_BEGIN + '\ncustom\n', CRON_END + '\n', CRON_BEGIN + '\n' + CRON_BEGIN):
            with self.assertRaises(ValueError):
                cron_text(text, False)

    @unittest.skipUnless(os.geteuid() == 0, 'Root ownership checks run in disposable container')
    def test_private_roundtrip_and_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            identity = instance_identity(path / 'instance')
            self.assertEqual(identity, instance_identity(path / 'instance'))
            password = 'SyntheticOnly \\ \' " $() ;\n\t&%'
            config = {'enabled': True, 'history_months': 6, 'instance_id': identity,
                      'database': {'password': password}}
            atomic_json(path / 'config', config)
            self.assertEqual(load_private(path / 'config'), config)
            self.assertEqual((path / 'config').stat().st_mode & 0o777, 0o600)
            (path / 'config').chmod(0o640)
            with self.assertRaises(ValueError):
                load_private(path / 'config')

    @unittest.skipUnless(os.geteuid() == 0, 'Root ownership checks run in disposable container')
    def test_symlinks_and_disabled_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            atomic_json(path / 'config', {'enabled': False})
            with self.assertRaises(ValueError):
                load_private(path / 'config')
            (path / 'link').symlink_to(path / 'config')
            with self.assertRaises(ValueError):
                atomic_json(path / 'link', {'enabled': True})
            self.assertEqual(json.loads((path / 'config').read_text()), {'enabled': False})
            with self.assertRaises(ValueError):
                instance_identity(path / 'link')


if __name__ == '__main__':
    unittest.main()
