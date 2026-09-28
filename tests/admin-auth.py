#!/usr/bin/env python3
"""Run: python3 tests/admin-auth.py --image IMAGE [--source-overlay]

Creates/removes a disposable container, without ports, host mounts, DB, entrypoint
initialization or mail services. Default tests the shipped image without network.
For a legacy image, --source-overlay copies current auth sources and permits apt
to install missing mod_magnet. Sources are never mounted writable.
Secure cookies are deliberately sent manually
over container-loopback HTTP: this models the trusted HTTPS reverse-proxy hop,
not browser cookie enforcement or TLS. No production credentials are read.
"""
import argparse
import hashlib
import http.client
from http.cookies import SimpleCookie
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import time
import urllib.parse
import uuid


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def inside(source_overlay):
    assert os.environ.get('SQMAIL_DISPOSABLE_TEST') == '1'
    if not Path('/usr/lib/lighttpd/mod_magnet.so').exists():
        assert source_overlay, 'image is missing required mod_magnet (use --source-overlay only for legacy-image testing)'
        run('apt-get', 'update', '-qq')
        run('apt-get', 'install', '-y', '--no-install-recommends', 'lighttpd-mod-magnet')
    run('php8.5', '-v')
    run('lighttpd', '-v')
    uid = pwd.getpwnam('www-data').pw_uid
    auth = Path('/run/sqmail-admin')
    auth.mkdir(mode=0o700, exist_ok=True)
    auth.chmod(0o700)
    os.chown(auth, uid, pwd.getpwnam('www-data').pw_gid)
    credentials = Path('/var/qmail/control/lighttpd-admins.htdigest')
    password = 'Synthetic-test-password!'

    def record(user):
        digest = hashlib.sha256(f'{user}:SQMail AIO Admin:{password}'.encode()).hexdigest()
        return f'{user}:SQMail AIO Admin:{digest}\n'

    records = record('admin') + record('operator')
    credentials.write_text(records)
    credentials.chmod(0o644)
    cgi = Path('/var/www/admin/cgi/auth-identity.cgi')
    cgi.write_text('#!/bin/sh\nprintf "Content-Type: text/plain\\r\\n\\r\\n%s|%s" "$REMOTE_USER" "$AUTH_TYPE"\n')
    cgi.chmod(0o755)
    php = Path('/var/www/admin/html/auth-identity.php')
    php.write_text("<?php header('Content-Type: text/plain'); "
                   "echo ($_SERVER['REMOTE_USER'] ?? ''), '|', ($_SERVER['AUTH_TYPE'] ?? '');")
    config = Path('/etc/lighttpd/lighttpd.conf').read_text()
    # TLS terminates at the proxy; omit only the unrelated public TLS listener.
    config = re.sub(r'\$SERVER\["socket"\] == ":443" \{.*?\}', '', config, flags=re.S)
    config = config.replace('/var/run/lighttpd-log.pipe', '/tmp/admin-auth-lighttpd.log')
    Path('/tmp/admin-auth-lighttpd.conf').write_text(config)
    Path('/run/php').mkdir(exist_ok=True)
    run('php-fpm8.5', '-t')
    run('lighttpd', '-tt', '-f', '/tmp/admin-auth-lighttpd.conf')
    processes = [subprocess.Popen(['php-fpm8.5', '-F']),
                 subprocess.Popen(['lighttpd', '-D', '-f', '/tmp/admin-auth-lighttpd.conf'])]

    def request(path, cookies=None, fields=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', 88, timeout=15)
        h = dict(headers or {})
        if cookies:
            h['Cookie'] = '; '.join(f'{k}={v}' for k, v in cookies.items())
        body = None
        if fields is not None:
            body = urllib.parse.urlencode(fields)
            h['Content-Type'] = 'application/x-www-form-urlencoded'
        conn.request('POST' if fields is not None else 'GET', path, body, h)
        response = conn.getresponse()
        result = (response.status, dict(response.getheaders()), response.read().decode(errors='replace'))
        for key, value in response.getheaders():
            if key.lower() == 'set-cookie':
                parsed = SimpleCookie(value)
                for name, morsel in parsed.items():
                    assert morsel['secure'] and morsel['httponly'], value
                    assert morsel['path'] == '/' and morsel['samesite'] == 'Strict', value
                    assert not morsel['domain'], value
                    if cookies is not None:
                        cookies[name] = morsel.value
        conn.close()
        return result

    def csrf(body):
        match = re.search(r'name="csrf" value="([a-f0-9]{64})"', body)
        assert match, body[:300]
        return match[1]

    def denied(path, cookies=None, **kwargs):
        status, headers, body = request(path, cookies, **kwargs)
        assert status == 303 and headers.get('Location') == '/login.php', (path, status, body[:200])
        assert headers.get('Cache-Control') == 'no-store'
        assert 'WWW-Authenticate' not in headers

    def login(user='admin', cookies=None):
        cookies = {} if cookies is None else cookies
        status, _, body = request('/login.php', cookies)
        assert status == 200
        old = cookies['__Host-sqmail-login']
        status, headers, body = request('/login.php', cookies, {
            'csrf': csrf(body), 'username': user, 'password': password})
        assert status == 303 and headers.get('Location') == '/', (status, body[:300])
        assert cookies['__Host-sqmail-login'] != old, 'PHP session was not rotated'
        assert re.fullmatch('[a-f0-9]{64}', cookies['__Host-sqmail-admin'])
        assert request('/cgi/auth-identity.cgi', cookies)[2] == f'{user}|Session'
        assert request('/auth-identity.php', cookies)[2] == f'{user}|Session'
        return cookies

    def passed(label):
        print('PASS:', label, flush=True)

    try:
        for attempt in range(100):
            try:
                if request('/login.php')[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(.1)
        else:
            raise AssertionError('lighttpd/PHP did not become ready')
        routes = ['/', '/index.php', '/logout.php', '/info.php', '/auth-identity.php', '/cgi/qmail-queue.php',
                  '/cgi/vqadmin/vqadmin.cgi', '/cgi/qmailadmin', '/cgi/auth-identity.cgi',
                  '/assets/', '/assets/absent.css', '/dmarc/', '/dmarc/index.php',
                  '/js/bootstrap.bundle.min.js', '/css/line-awesome.min.css', '/missing',
                  '/delivery/', '/delivery/index.php', '/delivery/style.css',
                  '/login.php/extra', '/cgi%2fvqadmin/vqadmin.cgi']
        for path in routes:
            denied(path)
            denied(path, headers={'Remote-User': 'admin', 'REMOTE_USER': 'admin',
                                 'X-Remote-User': 'admin', 'X-Forwarded-User': 'admin',
                                 'Authorization': 'Basic YWRtaW46YWRtaW4='})
            denied(path, fields={'action': 'delete'})
        for path in ['/login.php', '/css/style.css', '/css/bootstrap.min.css']:
            assert request(path)[0] == 200, path
        passed('anonymous GET/POST and forged identity headers across every route family; public allowlist')
        jar = {'__Host-sqmail-login': 'attacker-chosen-session', '__Host-sqmail-admin': 'a' * 64}
        denied('/', jar)
        status, _, body = request('/login.php', jar)
        assert status == 200 and jar['__Host-sqmail-login'] != 'attacker-chosen-session'
        token = csrf(body)
        assert request('/login.php', jar, {'username': 'admin', 'password': password})[0] == 403
        assert request('/login.php', jar, {'csrf': '0' * 64, 'username': 'admin', 'password': password})[0] == 403
        assert request('/login.php', jar, {'csrf': token, 'username': 'admin', 'password': 'wrong'})[0] == 401
        denied('/', jar)
        passed('incorrect credentials, missing/invalid CSRF and strict PHP session fixation protection')
        jar = login(cookies=jar)
        assert jar['__Host-sqmail-admin'] != 'a' * 64
        prior = dict(jar)
        jar = login(cookies=jar)
        assert prior['__Host-sqmail-admin'] != jar['__Host-sqmail-admin']
        denied('/', prior)
        passed('relogin rotates bearer token and invalidates previous copied token')
        assert request('/')[0] == 303
        status, _, body = request('/', jar)
        assert status == 200 and 'Sign out' in body
        assert request('/info.php', jar)[0] == 200
        assert request('/cgi/auth-identity.cgi', jar, headers={'REMOTE_USER': 'forged', 'Remote-User': 'forged'})[2] == 'admin|Session'
        assert request('/auth-identity.php', jar, headers={
            'REMOTE_USER': 'forged', 'Remote-User': 'forged',
            'AUTH_TYPE': 'Basic', 'Auth-Type': 'Basic',
            'X-Remote-User': 'forged', 'X-Forwarded-User': 'forged'})[2] == 'admin|Session'
        assert (auth / ('token-' + jar['__Host-sqmail-admin'])).stat().st_mode & 0o777 == 0o600
        passed('existing SHA256 htdigest login; admin PHP and native CGI identity; private token mode')
        copied = dict(jar)
        assert request('/logout.php', jar)[0] == 303
        assert request('/cgi/auth-identity.cgi', copied)[0] == 200
        assert request('/logout.php', jar, {'csrf': 'bad'})[0] == 403
        assert request('/cgi/auth-identity.cgi', copied)[0] == 200
        assert request('/logout.php', jar, {'csrf': csrf(body)})[0] == 303
        denied('/', copied)
        passed('logout requires POST and valid CSRF; copied bearer token revoked server-side')
        jar = login()
        tokenfile = auth / ('token-' + jar['__Host-sqmail-admin'])
        lines = tokenfile.read_text().splitlines()
        lines[1] = str(int(time.time()) - 1)
        tokenfile.write_text('\n'.join(lines) + '\n')
        denied('/', jar)
        passed('expired token rejected (expiry fixture changed, no one-hour wait)')
        jar = login()
        credentials.write_text(record('operator'))
        denied('/', jar)
        credentials.write_text(record('admin').replace(record('admin').split(':')[-1].strip(), '0' * 64) + record('operator'))
        denied('/', jar)
        credentials.write_text(records)
        passed('credential removal and password digest changes immediately revoke sessions')
        operator = login('operator')
        assert request('/cgi/auth-identity.cgi', operator, headers={'REMOTE_USER': 'admin'})[2] == 'operator|Session'
        assert request('/auth-identity.php', operator, headers={'REMOTE_USER': 'admin'})[2] == 'operator|Session'
        native = '/var/www/admin/cgi/vqadmin/vqadmin.cgi'
        env = dict(os.environ, REQUEST_METHOD='GET', QUERY_STRING='', SERVER_PROTOCOL='HTTP/1.1',
                   GATEWAY_INTERFACE='CGI/1.1', SCRIPT_NAME='/cgi/vqadmin/vqadmin.cgi')
        env.pop('REMOTE_USER', None)
        baseline = subprocess.run([native], cwd=str(Path(native).parent), env=env,
                                  capture_output=True, timeout=15).stdout.decode(errors='replace')
        admin_body = request('/cgi/vqadmin/vqadmin.cgi', jar)[2]
        operator_body = request('/cgi/vqadmin/vqadmin.cgi', operator)[2]
        assert 'Authentication Failed' in baseline and 'Username unknown' in baseline, baseline
        for user, permission, response in [('admin', 'senior', admin_body), ('operator', 'default', operator_body)]:
            text = ' '.join(re.sub('<[^>]+>', ' ', response).split())
            assert 'Authentication Failed' not in text, text
            assert f'User: {user} ~ Permission: {permission}' in text, text
            print(f'VQADMIN: User: {user}, Permission: {permission}', flush=True)
        passed('real vqadmin CGI receives authenticated identity, including non-admin ACL behavior (no DB)')
        jar = {}
        token = csrf(request('/login.php', jar)[2])
        for index in range(10):
            assert request('/login.php', jar, {'csrf': token, 'username': 'admin', 'password': 'wrong'})[0] == 401, index
        status, headers, _ = request('/login.php', jar, {'csrf': token, 'username': 'admin', 'password': password},
                                     {'X-Forwarded-For': '198.51.100.42'})
        assert status == 429 and 0 < int(headers.get('Retry-After', '0')) <= 300
        login()
        login('operator')
        passed('ten failed attempts block session even with valid password; forwarded IP cannot bypass; fresh session works')
        unknown = {}
        unknown_csrf = csrf(request('/login.php', unknown)[2])
        for index in range(10):
            assert request('/login.php', unknown, {'csrf': unknown_csrf, 'username': f'unknown{index}', 'password': 'wrong'})[0] == 401
        assert request('/login.php', unknown, {'csrf': unknown_csrf, 'username': 'another-unknown', 'password': 'wrong'})[0] == 429
        session_file = auth / ('sess_' + jar['__Host-sqmail-login'])
        session, count = re.subn(r'"until";i:\d+;', '"until";i:1;', session_file.read_text())
        assert count == 1
        session_file.write_text(session)
        login(cookies=jar)
        passed('changing username cannot bypass session limiter; expired rate window resets')
        print('ALL ADMIN AUTH INTEGRATION TESTS PASSED', flush=True)
    finally:
        for process in reversed(processes):
            process.terminate()
            process.wait(timeout=10)
        log = Path('/tmp/admin-auth-lighttpd.log')
        if sys.exc_info()[0] and log.exists():
            print(log.read_text()[-6000:], file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='sqmail-aio:dev')
    parser.add_argument('--source-overlay', action='store_true',
                        help='test current source on legacy image; allow installing missing mod_magnet')
    parser.add_argument('--inside', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.inside:
        inside(args.source_overlay)
        return
    root = Path(__file__).resolve().parents[1]
    name = 'sqmail-admin-auth-' + uuid.uuid4().hex[:12]
    run('docker', 'create', '--name', name, '--network', 'bridge' if args.source_overlay else 'none',
        '--entrypoint', '/usr/bin/python3', '-e', 'SQMAIL_DISPOSABLE_TEST=1',
        args.image, '/tmp/admin-auth.py', '--inside', *(['--source-overlay'] if args.source_overlay else []))
    try:
        files = [('tests/admin-auth.py', '/tmp/admin-auth.py')]
        if args.source_overlay:
            files += [
                ('rootfs/etc/lighttpd/admin-auth.lua', '/etc/lighttpd/admin-auth.lua'),
                ('rootfs/etc/lighttpd/lighttpd.conf', '/etc/lighttpd/lighttpd.conf'),
                *[(f'rootfs/var/www/admin/html/{page}.php', f'/var/www/admin/html/{page}.php')
                  for page in ('login', 'index', 'logout')],
            ]
        for source, destination in files:
            run('docker', 'cp', str(root / source), f'{name}:{destination}')
        run('docker', 'start', '-a', name)
        result = subprocess.check_output(['docker', 'inspect', '--format', '{{.State.ExitCode}}', name], text=True)
        assert result.strip() == '0', f'test container exit code {result.strip()}'
    finally:
        run('docker', 'rm', '-f', '-v', name)


if __name__ == '__main__':
    main()
