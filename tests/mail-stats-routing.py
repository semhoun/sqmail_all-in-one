#!/usr/bin/env python3
"""Synthetic routing tests; privileged integration requires an isolated container."""

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.dont_write_bytecode = True
INSIDE = '--inside-container' in sys.argv
if INSIDE:
    sys.argv.remove('--inside-container')
    if not Path('/.dockerenv').exists() or os.geteuid() != 0:
        raise SystemExit('isolated root container required')
    ROUTER = Path('/opt/libexec/mail-stats-routing')
else:
    ROUTER = Path(__file__).resolve().parents[1] / 'rootfs/opt/libexec/mail-stats-routing'
loader = importlib.machinery.SourceFileLoader('routing', str(ROUTER))
spec = importlib.util.spec_from_loader(loader.name, loader)
routing = importlib.util.module_from_spec(spec)
loader.exec_module(routing)


class RoutingTests(unittest.TestCase):
    def test_fixed_schema(self):
        record = routing.event_record('fetchmail_result', 'fetchmail', 'skipped', 1)
        self.assertEqual(set(record), {'v', 'event', 'component', 'at', 'status', 'exit_code'})
        self.assertTrue(record['at'].endswith('+00:00'))
        for args in [('unknown', 'fetchmail', 'success'), ('lifecycle', 'fetchmail', 'success'),
                     ('fetchmail_result', 'dcc', 'failure'), ('maintenance_run', 'dcc', 'secret'),
                     ('maintenance_run', 'dcc', 'success', 256),
                     ('maintenance_run', 'dcc', 'success', True)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                routing.event_record(*args)

    def test_datagram_allowlist(self):
        samples = [b'<21>Sep 28 22:00:00 vpopmail[12]: vchkpw-smtp: null password given test@example.invalid:192.0.2.1',
                   b'<19>Sep 28 22:00:00 cron-dccd: synthetic failure',
                   b'<19>DCC: synthetic failure']
        for sample in samples:
            self.assertEqual(routing.accepted_datagram(sample), sample)
        for sample in [b'<21>sshd: secret', b'<21>vpopmail: password=secret',
                       b'<21>DCC: forged\nnew line', b'<21>DCC: ' + b'x' * 8192,
                       b'<999>DCC: synthetic', b'<21>DCC: bad\x00data']:
            self.assertIsNone(routing.accepted_datagram(sample))

    def test_structured_datagrams_reject_extra_fields(self):
        record = routing.event_record('maintenance_run', 'dcc', 'failure', 1)
        def data():
            return ('<14>mail-stats: ' + json.dumps(record)).encode()
        self.assertEqual(routing.accepted_datagram(data()), data())
        record['password'] = 'must-not-persist'
        self.assertIsNone(routing.accepted_datagram(data()))
        del record['password']
        record['at'] = '2026-09-28T00:00:00'
        self.assertIsNone(routing.accepted_datagram(data()))

    def test_rotation_preserves_open_writer_and_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'current'
            path.write_bytes(b'before\n')
            path.chmod(0o600)
            with path.open('ab') as writer:
                inode = path.stat().st_ino
                routing.rotate_file(path, 1)
                writer.write(b'in-flight\n')
            self.assertEqual(Path(str(path) + '.1').stat().st_ino, inode)
            self.assertEqual(Path(str(path) + '.1').read_bytes(), b'before\nin-flight\n')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            for _ in range(12):
                path.write_bytes(b'new\n')
                routing.rotate_file(path, 1)
            self.assertEqual(len(list(Path(directory).glob('current.*'))), routing.ARCHIVES)

    def test_nofollow(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'target'
            target.write_text('unchanged')
            link = Path(directory) / 'current'
            link.symlink_to(target)
            with self.assertRaises(OSError):
                routing.regular_fd(link, os.O_WRONLY | os.O_APPEND)
            with self.assertRaises(ValueError):
                routing.rotate_file(link, 1)
            self.assertEqual(target.read_text(), 'unchanged')
            fifo = Path(directory) / 'fifo'
            os.mkfifo(fifo)
            with self.assertRaises(ValueError):
                routing.regular_fd(fifo, os.O_RDONLY)

    def test_cron_preserves_custom_tasks_and_schedule(self):
        original = ('!stdout(yes),mail(no)\n# custom\n2 3 * * 4 /custom/job\n'
                    '7 8 * * 2 /usr/bin/freshclam\n'
                    '1 2 * * * /usr/bin/freshclam --custom\n'
                    '%hourly,random(yes) * /usr/lib/php/sessionclean\n')
        updated = routing.cron_text(original, 'root')
        self.assertIn('2 3 * * 4 /custom/job\n', updated)
        self.assertIn('7 8 * * 2 /opt/bin/mail-stats-event run freshclam -- /usr/bin/freshclam\n', updated)
        self.assertIn('1 2 * * * /usr/bin/freshclam --custom\n', updated)
        self.assertEqual(updated.count(routing.CRON_JOB), 1)
        self.assertEqual(routing.cron_text(updated, 'root'), updated)
        for text in (routing.CRON_BEGIN + '\n', routing.CRON_END + '\n',
                     routing.CRON_BEGIN + '\n/custom\n' + routing.CRON_END):
            with self.assertRaises(ValueError):
                routing.cron_text(text, 'root')
        old = '45 4 * * * /usr/bin/php -q /var/www/admin/dmarc/utils/reportlog_cleaner.ph\n'
        new = routing.cron_text(old, 'www-data')
        self.assertIn('run dmarc -- ', new)
        self.assertTrue(new.endswith('reportlog_cleaner.php\n'))

    def test_run_does_not_log_arguments_or_capture_streams(self):
        with mock.patch.object(routing, 'emit') as emit, mock.patch.object(routing.subprocess, 'Popen') as popen:
            popen.return_value.wait.return_value = 23
            command = ['/synthetic', 'secret-not-logged']
            self.assertEqual(routing.run_command('dcc', command), 23)
            popen.assert_called_once_with(command)
            self.assertEqual(emit.call_args_list, [mock.call('maintenance_run', 'dcc', 'started'),
                mock.call('maintenance_run', 'dcc', 'failure', 23)])

    def test_cron_retries_after_failed_install(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'root'
            path.write_text('1 2 * * * /custom/unchanged\n')
            with mock.patch.object(routing.subprocess, 'run') as run:
                run.return_value.returncode = 1
                with self.assertRaises(ValueError):
                    routing.reconcile_cron(directory)
                installed_text = path.read_text()
                run.return_value.returncode = 0
                routing.reconcile_cron(directory)
                self.assertEqual(path.read_text(), installed_text)
                self.assertEqual(run.call_count, 2)


@unittest.skipUnless(INSIDE, 'requires disposable image; no host runtime paths')
class ImageRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Path('/var/vpopmail/log').mkdir(parents=True, exist_ok=True)
        Path('/var/vpopmail/log/qmailadmin-auth.log').write_text(
            '2026/09/28 22:00:00 user:synthetic@example.invalid ip:192.0.2.1 auth:failed\n')
        routing.prepare()

    def test_actual_fcrontab_reconciliation(self):
        directory = Path('/etc/fcrontab')
        directory.mkdir(exist_ok=True)
        root = directory / 'root'
        root.write_text('!stdout(yes),mail(no)\n1 2 * * * /custom/preserved\n'
                        '%nightly,random(yes) * 1-4 /usr/bin/freshclam\n')
        (directory / 'vpopmail').write_text('*/5 * * * * /opt/bin/fetchmail.pl\n')
        (directory / 'www-data').write_text('45 4 * * * /usr/bin/php -q /var/www/admin/dmarc/utils/reportlog_cleaner.ph\n')
        sentinel = Path('/var/spool/fcron/routing-test-sentinel')
        sentinel.write_text('unrelated-spool-file')
        routing.reconcile_cron()
        installed = root.read_text()
        routing.reconcile_cron()
        self.assertEqual(root.read_text(), installed)
        self.assertIn('1 2 * * * /custom/preserved\n', installed)
        self.assertEqual(installed.count(routing.CRON_JOB), 1)
        self.assertEqual(sentinel.read_text(), 'unrelated-spool-file')

    def test_qmailadmin_migration_restart_rotation(self):
        source = Path('/var/vpopmail/log/qmailadmin-auth.log')
        target = Path('/log/qmailadmin/current')
        self.assertTrue(source.is_symlink())
        self.assertIn('synthetic@example.invalid', Path(str(target) + '.0').read_text())
        with source.open('a') as out:
            out.write('first synthetic future record\n')
        routing.prepare()
        self.assertIn('first synthetic future record', target.read_text())
        routing.rotate_file(target, 1)
        subprocess.run(['s6-setuidgid', 'vpopmail', 'sh', '-c',
                        'printf "second synthetic future record\\n" >> /var/vpopmail/log/qmailadmin-auth.log'], check=True)
        self.assertIn('first synthetic future record', Path(str(target) + '.1').read_text())
        self.assertEqual(target.read_text(), 'second synthetic future record\n')
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        denied = subprocess.run(['s6-setuidgid', 'www-data', 'test', '-r', str(target)])
        self.assertNotEqual(denied.returncode, 0)

    def test_local_receiver_and_stream_status_preservation(self):
        logger = subprocess.Popen(['s6-setuidgid', 'qmaill', 's6-log', 't', 'T', 's2000000',
                                   '/log/local-syslog'], stdin=subprocess.PIPE,
                                  env={**os.environ, 'TZ': 'UTC0'})
        receiver = subprocess.Popen([sys.executable, '-I', str(ROUTER), 'receive'], stdout=logger.stdin)
        try:
            for _ in range(100):
                if Path('/dev/log').exists():
                    break
                time.sleep(0.02)
            self.assertTrue(Path('/dev/log').is_socket())
            result = subprocess.run([sys.executable, '-I', str(ROUTER), 'run', 'dcc', '--',
                '/bin/sh', '-c', 'printf stdout-preserved; printf stderr-preserved >&2; exit 23'], capture_output=True)
            self.assertEqual((result.returncode, result.stdout, result.stderr),
                             (23, b'stdout-preserved', b'stderr-preserved'))
            for sig in (signal.SIGTERM, signal.SIGKILL):
                result = subprocess.run([sys.executable, '-I', str(ROUTER), 'run', 'dcc', '--',
                    '/bin/sh', '-c', 'kill -' + str(int(sig)) + ' $$'], capture_output=True)
                self.assertEqual(result.returncode, -sig)
            subprocess.run(['logger', '-s', '-p', 'mail.err', '-t', 'cron-dccd', 'synthetic-dcc'],
                           check=True, capture_output=True)
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
                client.sendto(b'<21>vpopmail[12]: vchkpw-smtp: null password given synthetic@example.invalid:192.0.2.1', '/dev/log')
                client.sendto(b'<14>external: must-not-be-collected', '/dev/log')
            time.sleep(0.05)
        finally:
            receiver.terminate()
            receiver.wait(timeout=5)
            logger.stdin.close()
            logger.wait(timeout=5)
            output = Path('/log/local-syslog/current').read_bytes()
        self.assertRegex(output, rb'^@[0-9a-f]{24} \d{4}-\d\d-\d\d ')
        self.assertIn(b'"status":"started"', output)
        self.assertIn(b'"exit_code":23', output)
        self.assertIn(b'cron-dccd: synthetic-dcc', output)
        self.assertIn(b'vchkpw-smtp:', output)
        self.assertNotIn(b'must-not-be-collected', output)
        self.assertNotIn(b'stdout-preserved', output)
        self.assertNotIn(b'stderr-preserved', output)
        self.assertFalse(Path('/dev/log').exists())

    def test_lifecycle_before_services(self):
        self.assertTrue(routing.emit('lifecycle', 'entrypoint', 'started'))
        line = Path('/log/lifecycle/current').read_text().splitlines()[-1]
        record = json.loads(line.removeprefix('mail-stats: '))
        self.assertEqual(record['component'], 'entrypoint')
        self.assertTrue(record['at'].endswith('+00:00'))

    def test_fpm_worker_stdout_reaches_master(self):
        Path('/run/php').mkdir(exist_ok=True)
        script = Path('/tmp/routing-probe.php')
        script.write_text('<?php file_put_contents("php://stdout", "errors: synthetic-roundcube\\n"); echo "response-preserved";')
        script.chmod(0o644)
        fpm = subprocess.Popen(['/usr/sbin/php-fpm8.5', '-O', '-F'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            sockpath = '/run/php/php8.5-fpm.sock'
            for _ in range(100):
                if Path(sockpath).exists():
                    break
                time.sleep(0.02)
            def record(kind, body):
                return struct.pack('!BBHHBB', 1, kind, 1, len(body), 0, 0) + body
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(5)
                client.connect(sockpath)
                params = {b'SCRIPT_FILENAME': str(script).encode(), b'REQUEST_METHOD': b'GET',
                          b'SERVER_PROTOCOL': b'HTTP/1.1', b'REMOTE_ADDR': b'192.0.2.1'}
                body = b''.join(bytes([len(k), len(v)]) + k + v for k, v in params.items())
                client.sendall(record(1, struct.pack('!HB5x', 1, 0)) + record(4, body) + record(4, b'') + record(5, b''))
                response = b''
                while True:
                    chunk = client.recv(65536)
                    if not chunk:
                        break
                    response += chunk
            self.assertIn(b'response-preserved', response)
            self.assertNotIn(b'synthetic-roundcube', response)
        finally:
            fpm.terminate()
            output = fpm.communicate(timeout=5)[0]
        self.assertIn(b'said into stdout: "errors: synthetic-roundcube"', output)
        for line in output.splitlines():
            if b'synthetic-roundcube' in line:
                print('Verified FPM fixture: ' + line.decode('ascii'))


if __name__ == '__main__':
    unittest.main()
