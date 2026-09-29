#!/usr/bin/env python3
"""Installer orchestration tests in a disposable image; DB calls are explicit stubs."""

import argparse
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import types
import unittest
from contextlib import nullcontext
from unittest.mock import patch


def inside():
    if os.geteuid() != 0 or os.environ.get('SQMAIL_STATS_INSTALL_TEST') != '1':
        raise RuntimeError('Disposable root test container required')
    loader = importlib.machinery.SourceFileLoader('stats_install', '/opt/libexec/mail-stats-init')
    spec = importlib.util.spec_from_loader(loader.name, loader)
    installer = importlib.util.module_from_spec(spec)
    loader.exec_module(installer)
    from mail_stats import config
    Path('/etc/fcrontab').mkdir(exist_ok=True)
    Path('/var/qmail/control/aio-conf').mkdir(parents=True, exist_ok=True)
    original = '!stdout(yes),mail(no)\n# Keep custom task\n0 3 * * * /bin/true\n'
    cron = Path('/etc/fcrontab/root')
    cron.write_text(original)
    password = 'SyntheticOnly \\ \' " $() ;\n\t&%'
    values = {'MYSQL_HOST': 'synthetic.invalid', 'MYSQL_USER': 'synthetic',
              'MYSQL_PASS': password, 'MYSQL_DB': 'synthetic'}
    generated = subprocess.run(['/usr/bin/php', '-r',
        '$c=json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR); '
        'echo "<?php\\n\\$MYSQL_CONF = ",var_export($c,true),";\\n";'],
        input=json.dumps(values), capture_output=True, text=True, check=True).stdout
    mysql = Path('/var/qmail/control/aio-conf/mysql.php')
    mysql.write_text(generated)
    mysql.chmod(0o640)
    connection = types.SimpleNamespace(close=lambda: None)
    database = types.ModuleType('mail_stats.db')
    database.connect = lambda conf: connection
    database.instance_lock = lambda conn, identity: nullcontext()
    database.install_schema = lambda conn: None

    class InstallTests(unittest.TestCase):
        def test_workflow(self):
            self.assertEqual(installer.credentials()['password'], password)
            with patch.dict(os.environ, {'MAIL_STATS_ENABLED': '1', 'MAIL_STATS_HISTORY_MONTHS': '6'}), \
                    patch.dict(sys.modules, {'mail_stats.db': database}):
                self.assertEqual(installer.main(), 0)
                public = json.loads((config.RUNTIME / 'web.json').read_text())
                self.assertTrue(public['enabled'])
                identity = public['instance_id']
                self.assertEqual(config.load_private()['database']['password'], password)
                self.assertEqual(cron.read_text().count(config.CRON_JOB), 1)
                self.assertEqual(installer.main(), 0)
                self.assertEqual(json.loads((config.RUNTIME / 'web.json').read_text())['instance_id'], identity)
                self.assertEqual(cron.read_text().count(config.CRON_JOB), 1)
                # Even unchanged text must retry installation into fcron's spool.
                with patch.object(installer.subprocess, 'run', side_effect=OSError('synthetic failure')):
                    with self.assertRaises(OSError):
                        installer.reconcile_cron(True)
                self.assertEqual(installer.main(), 0)
                with patch.object(database, 'install_schema', side_effect=RuntimeError('SyntheticPrivateFailure')):
                    self.assertEqual(installer.main(), 1)
                self.assertFalse(json.loads((config.RUNTIME / 'web.json').read_text())['enabled'])
                self.assertEqual(cron.read_text(), original)
                self.assertEqual(installer.main(), 0)
            with patch.dict(os.environ, {'MAIL_STATS_ENABLED': '1', 'MAIL_STATS_HISTORY_MONTHS': '0'}):
                self.assertEqual(installer.main(), 1)
                public = json.loads((config.RUNTIME / 'web.json').read_text())
                self.assertFalse(public['enabled'])
                self.assertIn('MAIL_STATS_HISTORY_MONTHS', public['reason'])
                self.assertEqual(cron.read_text(), original)
            with patch.dict(os.environ, {'MAIL_STATS_ENABLED': '0', 'MAIL_STATS_HISTORY_MONTHS': '6'}):
                self.assertEqual(installer.main(), 0)
                self.assertFalse(json.loads((config.RUNTIME / 'web.json').read_text())['enabled'])
                self.assertEqual(cron.read_text(), original)

        def test_symlink_credentials_refused(self):
            moved = mysql.with_suffix('.saved')
            mysql.rename(moved)
            try:
                mysql.symlink_to(moved)
                with self.assertRaises(ValueError):
                    installer.credentials()
            finally:
                mysql.unlink()
                moved.rename(mysql)

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(InstallTests))
    return 0 if result.wasSuccessful() else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='sqmail_aio-sqmail_aio:latest')
    parser.add_argument('--inside', action='store_true')
    args = parser.parse_args()
    if args.inside:
        return inside()
    root = Path(__file__).resolve().parents[1]
    command = ['docker', 'run', '--rm', '--network', 'none', '-e', 'SQMAIL_STATS_INSTALL_TEST=1']
    for source, destination in [('tests', '/tests'), ('rootfs/opt/lib', '/opt/lib'),
                                 ('rootfs/opt/libexec/mail-stats-init', '/opt/libexec/mail-stats-init')]:
        command += ['--mount', f'type=bind,src={root / source},dst={destination},readonly']
    command += ['--entrypoint', 'python3', args.image, '-B', '/tests/mail-stats-install.py', '--inside']
    return subprocess.run(command, timeout=120).returncode


if __name__ == '__main__':
    sys.exit(main())
