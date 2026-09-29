#!/usr/bin/env python3
"""Full image integration: synthetic mail, isolated DB, existing HTTP portal and PDF.

Secure cookies are sent manually over container-loopback HTTP, modelling the
trusted reverse-proxy hop. This does not test browser HTTPS cookie enforcement.
"""

import argparse
import base64
from http.cookies import SimpleCookie
import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.parse

from mail import MailEnvironment


def probe():
    if os.environ.get('SQMAIL_DISPOSABLE_TEST') != '1':
        raise RuntimeError('Disposable test environment required')
    if Path('/tmp/sqmail-mail-test-run').read_text().strip() != os.environ['SQMAIL_MAIL_TEST_RUN']:
        raise RuntimeError('Disposable ownership marker mismatch')
    sys.path.insert(0, '/opt/lib')
    from mail_stats.config import load_private
    from mail_stats import db
    config = load_private()
    assert config['database']['host'] == 'db' and config['database']['database'] == 'sqmail_test'
    subprocess.run(['openssl', 'rehash', '/ssl'], check=True, capture_output=True, timeout=10)
    connection = db.connect(config['database'])
    try:
        with connection.cursor() as cursor:
            cursor.execute('''INSERT INTO fetchmail
                (mailbox,domain,src_server,src_port,src_user,src_password,src_folder,
                 fetchall,keep,protocol,usessl,sslcertck,sslcertpath,mda,date)
                VALUES (%s,%s,%s,995,%s,%s,'',1,1,'POP3',1,1,'/ssl','dovecot',UTC_TIMESTAMP()-INTERVAL 1 DAY)''',
                ('bob@examples.invalid', 'examples.invalid', 'localhost',
                 'alice@examples.invalid', base64.b64encode(b'SyntheticMailOnly927').decode()))
        fetched = subprocess.run(['s6-setuidgid', 'vpopmail', 'env', 'HOME=/var/vpopmail',
                                  '/opt/bin/fetchmail.pl'],
                                 capture_output=True, timeout=60)
        assert fetched.returncode == 0, 'Synthetic Fetchmail execution failed'
    finally:
        connection.close()
    subprocess.run(['/usr/bin/python3', '-I', '/opt/libexec/mail-stats-collect'], check=True, timeout=60)
    connection = db.connect(config['database'])
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) AS n FROM mail_stats_events WHERE instance_id=%s',
                           (config['instance_id'].encode(),))
            count = cursor.fetchone()['n']
            assert count > 0, 'Synthetic service events were not ingested'
            cursor.execute('SELECT COUNT(*) AS n FROM mail_stats_messages WHERE instance_id=%s',
                           (config['instance_id'].encode(),))
            assert cursor.fetchone()['n'] > 0, 'No synthetic queue messages correlated'
            cursor.execute('SELECT source_key FROM mail_stats_sources WHERE instance_id=%s',
                           (config['instance_id'].encode(),))
            registry = {row['source_key'].decode() for row in cursor.fetchall()}
            assert {'qmail-send', 'dovecot', 'spamd', 'clamd', 'lighttpd', 'php-fpm',
                    'fcron', 'qmailadmin', 'local-syslog', 'lifecycle', 'retention'} <= registry
            cursor.execute('''SELECT metadata FROM mail_stats_events
                WHERE instance_id=%s AND event_type=%s AND component=%s''',
                (config['instance_id'].encode(), b'fetchmail_result', b'fetchmail'))
            outcomes = cursor.fetchall()
            assert outcomes and any(json.loads(row['metadata']).get('outcome') in ('success', 'skipped')
                                    for row in outcomes), \
                ('Actual Fetchmail outcome was not recorded', outcomes,
                 fetched.stderr.decode(errors='replace').replace('SyntheticMailOnly927', '[synthetic password]')[:1500])
    finally:
        connection.close()

    cookies = {}

    def request(path, fields=None, authenticated=True):
        headers = {}
        if authenticated and cookies:
            headers['Cookie'] = '; '.join(f'{key}={value}' for key, value in cookies.items())
        body = None
        if fields is not None:
            body = urllib.parse.urlencode(fields)
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        connection = http.client.HTTPConnection('127.0.0.1', 88, timeout=40)
        try:
            connection.request('POST' if fields is not None else 'GET', path, body, headers)
            response = connection.getresponse()
            result = response.status, dict(response.getheaders()), response.read()
            for key, value in response.getheaders():
                if key.lower() == 'set-cookie' and authenticated:
                    for name, morsel in SimpleCookie(value).items():
                        assert morsel['secure'] and morsel['httponly']
                        cookies[name] = morsel.value
            return result
        finally:
            connection.close()

    def csrf(body):
        match = re.search(rb'name="csrf" value="([a-f0-9]{64})"', body)
        assert match, 'Missing CSRF token'
        return match[1].decode()

    for path in ('/stats/', '/stats/index.php', '/stats/export.php'):
        status, headers, _ = request(path, authenticated=False)
        assert status == 303 and headers.get('Location') == '/login.php'
    status, _, body = request('/login.php')
    assert status == 200
    status, _, _ = request('/login.php', {'csrf': csrf(body), 'username': 'admin',
                                        'password': 'SyntheticAdminOnly927'})
    assert status == 303 and '__Host-sqmail-admin' in cookies
    status, headers, body = request('/stats/')
    assert status == 200, body[:200]
    assert 'no-store' in headers.get('Cache-Control', ''), headers.get('Cache-Control')
    assert 'Content-Security-Policy' in headers
    token = csrf(body)
    assert request('/stats/', {'csrf': 'invalid'})[0] == 403
    assert request('/stats/export.php', {'csrf': 'invalid'})[0] == 403
    status, _, _ = request('/stats/?address=alice%40examples.invalid')
    assert status == 400
    fields = {'csrf': token, 'view': 'overview', 'report': 'summary'}
    status, headers, pdf = request('/stats/export.php', fields)
    assert status == 200, pdf[:200]
    assert headers.get('Content-Type', '').startswith('application/pdf')
    assert headers.get('Content-Disposition', '').startswith('attachment;')
    assert 'no-store' in headers.get('Cache-Control', ''), headers.get('Cache-Control')
    assert pdf.startswith(b'%PDF-') and b'%%EOF' in pdf[-1024:]
    assert not list(Path('/run/mail-stats-pdf/work').iterdir()), 'PDF temporaries leaked'
    # A path-info bypass must never execute the export in the unbounded default pool.
    assert request('/stats/export.php/extra', fields)[0] != 200
    # Only in this owned disposable fixture: prove the real pool's wall timeout,
    # including a blocked native sleep which PHP's CPU timer cannot interrupt.
    def restart_php():
        old_pid = subprocess.run(['s6-svstat', '-o', 'pid', '/service/php-fpm'],
                                 check=True, capture_output=True, text=True).stdout
        subprocess.run(['s6-svc', '-t', '/service/php-fpm'], check=True)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            new_pid = subprocess.run(['s6-svstat', '-o', 'pid', '/service/php-fpm'],
                                     check=True, capture_output=True, text=True).stdout
            if new_pid != old_pid and new_pid.strip() != '-1':
                try:
                    if request('/stats/')[0] == 200:
                        return
                except (OSError, http.client.HTTPException):
                    pass
            time.sleep(0.2)
        raise AssertionError('Disposable PHP service did not restart')

    endpoint = Path('/var/www/admin/html/stats/export.php')
    original_endpoint = endpoint.read_bytes()
    try:
        endpoint.write_text("<?php if (getenv('MAIL_STATS_PDF_POOL',true)!=='1') { http_response_code(418); exit; } "
                            "mkdir('/run/mail-stats-pdf/work/render-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',0700); "
                            "file_put_contents('/run/mail-stats-pdf/work/render-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/orphan','synthetic'); "
                            "while (true) { usleep(500000); }")
        restart_php()  # Discard shared opcodes before the intentional native stall.
        started = time.monotonic()
        status, _, _ = request('/stats/export.php', fields)
        elapsed = time.monotonic() - started
        assert status >= 500 and 18 <= elapsed <= 30, (status, elapsed)
    finally:
        endpoint.write_bytes(original_endpoint)
        restart_php()
    status, _, recovered_pdf = request('/stats/export.php', fields)
    assert status == 200 and recovered_pdf.startswith(b'%PDF-'), (status, recovered_pdf[:200])
    assert not list(Path('/run/mail-stats-pdf/work').iterdir()), 'Interrupted render temporaries were not removed'
    for service in ('qmail-send', 'qmail-smtpd', 'dovecot', 'spamd', 'clamd'):
        result = subprocess.run(['s6-svstat', '-o', 'up', '/service/' + service],
                                check=True, capture_output=True, text=True)
        assert result.stdout.strip() == 'true', service
    # The production jobs stay disabled. Install only the collector into this
    # disposable scheduler, proving credentials/settings do not depend on fcron's
    # inherited environment without running ACME, feed updates or mailbox jobs.
    for user in ('vpopmail', 'www-data'):
        subprocess.run(['fcrontab', '-r', user], capture_output=True, check=False)
    cron = Path('/etc/fcrontab/root')
    cron.write_text('!stdout(yes),mail(no)\n* * * * * /usr/bin/python3 -I /opt/libexec/mail-stats-collect\n')
    subprocess.run(['fcrontab', '-n', str(cron), 'root'], check=True, capture_output=True)
    connection = db.connect(config['database'])
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT UTC_TIMESTAMP(6) AS now')
            started_at = cursor.fetchone()['now']
        subprocess.run(['s6-svc', '-u', '/service/fcron'], check=True)
        deadline = time.monotonic() + 80
        while time.monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute('''SELECT last_success_at FROM mail_stats_sources
                    WHERE instance_id=%s AND source_key=%s''',
                    (config['instance_id'].encode(), b'retention'))
                state = cursor.fetchone()
            if state and state['last_success_at'] and state['last_success_at'] > started_at:
                break
            time.sleep(1)
        else:
            raise AssertionError('Real fcron did not execute the isolated collector schedule')
    finally:
        subprocess.run(['s6-svc', '-d', '/service/fcron'], check=False)
        connection.close()
    print('PASS: real image collection, fcron, registry, portal auth/CSRF, PDF, hard wall timeout, interruption cleanup and mail supervision')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='sqmail-aio:mail-stats-dev')
    parser.add_argument('--database-image', default='mariadb:11.4')
    parser.add_argument('--smoke', action='store_true', help='Use only the real reception case while debugging integration')
    parser.add_argument('--inside', action='store_true')
    args = parser.parse_args()
    if args.inside:
        probe()
        return 0
    environment = MailEnvironment(args.image, args.database_image)
    try:
        environment.prepare()
        if args.smoke:
            environment.docker('exec', environment.mail, 'python3', '-B', '-c',
                "import runpy; p=runpy.run_path('/tests/mail-probe.py'); "
                "p['guard'](); p['ready'](); p['reception'](); print('PASS smoke reception')", timeout=240)
        else:
            environment.test()
        print(environment.docker('exec', environment.mail, 'python3', '-B',
                                 '/tests/mail-stats-e2e.py', '--inside', timeout=180), end='')
    except Exception:
        environment.logs()
        raise
    finally:
        environment.cleanup()
    print('PASS: isolated statistics integration; disposable resources removed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
