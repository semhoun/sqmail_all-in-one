#!/usr/bin/env python3
"""Destructive synthetic fixture: run ONLY in a fresh disposable mail container.

Requires a separate synthetic MariaDB at db, the installed wrapper/mksrs, and
vdelivermail compiled with QMAILINJECT=/opt/bin/vpopmail-inject.sh. No host ports
or production volumes may be attached. SQMAIL_DISPOSABLE_TEST=1 is mandatory.
"""
import email.parser
import email.policy
import os
from pathlib import Path
import queue
import smtplib
import socketserver
import subprocess
import threading
import time


CONTROL = Path('/var/qmail/control')
RESULTS = queue.Queue()
PROCESSES = []


def run(*args, **kwargs):
    result = subprocess.run(args, capture_output=True, **kwargs)
    assert result.returncode == 0, (args, result.returncode, result.stdout, result.stderr)
    return result


def put(name, value):
    (CONTROL / name).write_text(value)


class Collector(socketserver.StreamRequestHandler):
    def handle(self):
        sender, recipients = '', []
        self.wfile.write(b'220 collector.invalid ESMTP\r\n')
        while line := self.rfile.readline():
            command = line.decode().strip()
            verb = command.split(' ', 1)[0].upper()
            if verb in ('EHLO', 'HELO'):
                reply = b'250 collector.invalid\r\n'
            elif verb == 'MAIL':
                sender = command.split('<', 1)[1].split('>', 1)[0]
                recipients = []
                reply = b'250 sender\r\n'
            elif verb == 'RCPT':
                recipients.append(command.split('<', 1)[1].split('>', 1)[0])
                reply = b'250 recipient\r\n'
            elif verb == 'DATA':
                self.wfile.write(b'354 data\r\n')
                lines = []
                while (line := self.rfile.readline()) != b'.\r\n':
                    if not line:
                        raise AssertionError('truncated SMTP DATA')
                    lines.append(line[1:] if line.startswith(b'..') else line)
                RESULTS.put((sender, recipients, b''.join(lines)))
                reply = b'250 accepted\r\n'
            elif verb == 'QUIT':
                self.wfile.write(b'221 bye\r\n')
                return
            else:
                reply = b'250 ok\r\n'
            self.wfile.write(reply)


class Incoming(socketserver.BaseRequestHandler):
    def handle(self):
        env = os.environ.copy()
        env.update(TCPREMOTEIP='127.0.0.1', TCPREMOTEHOST='collector.invalid',
                   TCPLOCALIP='127.0.0.1', TCPLOCALHOST='mail.examples.invalid')
        for key in ('QMAILQUEUE', 'RELAYCLIENT', 'SMTPAUTH', 'UCSPITLS'):
            env.pop(key, None)
        subprocess.run(['/bin/s6-setuidgid', 'vpopmail', '/var/qmail/bin/qmail-smtpd'],
                       stdin=self.request, stdout=self.request, stderr=subprocess.PIPE,
                       env=env, timeout=30, check=True)


def message(label):
    return (f'From: Original Author <origin@outside.invalid>\r\n'
            f'To: forward@examples.invalid\r\nSubject: {label}\r\n'
            f'Date: Sun, 27 Sep 2026 12:00:00 +0000\r\n'
            f'Message-ID: <{label}@outside.invalid>\r\n'
            'DKIM-Signature: v=1; a=rsa-sha256; d=outside.invalid; s=synthetic;\r\n'
            ' h=from:to:subject; bh=synthetic; b=synthetic\r\n'
            '\r\nSynthetic body, unchanged.\r\n.leading dot\r\n').encode()


def smtp(sender, recipient, payload):
    with smtplib.SMTP('127.0.0.1', 2525, timeout=20) as client:
        assert not client.sendmail(sender, [recipient], payload)


def received(payload, sender=None, recipient='sink@remote.invalid', srs=False):
    actual, recipients, raw = RESULTS.get(timeout=45)
    assert recipients == [recipient], recipients
    if srs:
        assert actual.startswith('SRS0') and actual.endswith('@srs.examples.invalid'), actual
        assert raw.endswith(payload), 'SRS changed original header/body bytes'
    else:
        assert actual == sender, (actual, sender)
    original = email.parser.BytesParser(policy=email.policy.default).parsebytes(payload)
    forwarded = email.parser.BytesParser(policy=email.policy.default).parsebytes(raw)
    for header in ('From', 'To', 'Subject', 'Message-ID', 'DKIM-Signature'):
        assert forwarded.get_all(header) == original.get_all(header), header
    assert raw.split(b'\r\n\r\n', 1)[1] == payload.split(b'\r\n\r\n', 1)[1]
    assert len(forwarded.get_all('Delivered-To', [])) == 1, raw
    return actual


def main():
    assert Path('/.dockerenv').exists() and os.environ.get('SQMAIL_DISPOSABLE_TEST') == '1'
    assert os.getuid() == 0
    assert not (CONTROL / 'aio-conf/mysql.conf').exists(), 'refuse initialized installation'
    CONTROL.mkdir(exist_ok=True)
    for name, value in {
        'me': 'mail.examples.invalid\n', 'locals': 'mail.examples.invalid\n',
        'rcpthosts': 'examples.invalid\n', 'virtualdomains': '',
        'defaultdomain': 'examples.invalid\n', 'plusdomain': 'examples.invalid\n',
        'smtproutes': ':127.0.0.1;2526\n', 'concurrencyremote': '1\n',
        'queuelifetime': '3600\n', 'timeoutremote': '10\n',
    }.items():
        put(name, value)
    Path('/var/qmail/users/assign').write_text('.\n')
    Path('/var/vpopmail/etc/vpopmail.mysql').write_text(
        'db|0|sqmail_test|SyntheticDbOnly927|sqmail_test\n')
    os.chown('/var/vpopmail/etc/vpopmail.mysql', 89, 89)
    run('/var/vpopmail/bin/vadddomain', 'examples.invalid', 'SyntheticMailOnly927')
    run('/var/vpopmail/bin/valias', '-i', 'sink@remote.invalid', 'forward@examples.invalid')
    run('/opt/bin/mksrs.sh', '-i', '192.0.2.10', 'examples.invalid')
    servers = []
    for port, handler in ((2526, Collector), (2525, Incoming)):
        server = socketserver.ThreadingTCPServer(('127.0.0.1', port), handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
    log = open('/tmp/srs-qmail.log', 'wb')
    PROCESSES.append(subprocess.Popen(
        ['/var/qmail/bin/qmail-start', '|/var/vpopmail/bin/vdelivermail "" bounce-no-mailbox'],
        stdout=log, stderr=log, env={'PATH': '/var/qmail/bin:/usr/bin:/bin'}))
    time.sleep(1)
    payload = message('actual-valias-forward')
    smtp('origin@outside.invalid', 'forward@examples.invalid', payload)
    token = received(payload, srs=True)
    print('PASS actual SMTP -> qmail-local -> SQL valias -> SRS -> remote SMTP; headers/body preserved', flush=True)
    bounce = message('actual-srs-bounce')
    smtp('', token, bounce)
    received(bounce, sender='', recipient='origin@outside.invalid')
    print('PASS actual SMTP bounce -> srs virtual route -> alias -> srsreverse -> original sender', flush=True)
    for label, sender in [('local-origin', 'postmaster@examples.invalid'), ('null-origin', '')]:
        payload = message(label)
        smtp(sender, 'forward@examples.invalid', payload)
        received(payload, sender=sender)
        print('PASS plain fallback:', label, flush=True)
    policy = (CONTROL / 'srsdomains').read_text()
    source_policy = next(line.split(':', 1)[1] for line in policy.splitlines()
                         if line.startswith('examples.invalid:'))
    put('srsdomains', '*:' + source_policy + '\n')
    payload = message('wildcard-forward')
    smtp('origin@outside.invalid', 'forward@examples.invalid', payload)
    token = received(payload, srs=True)
    bounce = message('wildcard-bounce')
    smtp('', token, bounce)
    received(bounce, sender='', recipient='origin@outside.invalid')
    print('PASS wildcard policy forward and actual SMTP bounce', flush=True)
    for label, replacement in [('unconfigured', ''), ('source-blacklist', '!examples.invalid:\n' + policy)]:
        put('srsdomains', replacement)
        payload = message(label)
        smtp('origin@outside.invalid', 'forward@examples.invalid', payload)
        received(payload, sender='origin@outside.invalid')
        print('PASS plain fallback:', label, flush=True)
    put('srsdomains', policy)
    routes = (CONTROL / 'virtualdomains').read_text()
    put('virtualdomains', ''.join(line + '\n' for line in routes.splitlines()
                                 if not line.startswith('srs.examples.invalid:')))
    payload = message('unconfigured-return-route')
    smtp('origin@outside.invalid', 'forward@examples.invalid', payload)
    received(payload, sender='origin@outside.invalid')
    put('virtualdomains', routes)
    print('PASS plain fallback: return route not configured', flush=True)
    # Local destinations bypass SRS even for a remote original envelope sender.
    put('defaultdelivery', './Maildir/\n')
    run('/var/vpopmail/bin/vadduser', 'local@examples.invalid', 'SyntheticMailOnly927')
    run('/var/vpopmail/bin/valias', '-i', 'local@examples.invalid', 'localforward@examples.invalid')
    localhome = Path(run('/var/vpopmail/bin/vuserinfo', '-d', 'local@examples.invalid').stdout.decode().strip())
    payload = message('local-destination')
    smtp('origin@outside.invalid', 'localforward@examples.invalid', payload)
    deadline = time.monotonic() + 30
    while not list((localhome / 'Maildir/new').glob('*')):
        assert time.monotonic() < deadline, 'local delivery timeout'
        time.sleep(0.2)
    raw = next((localhome / 'Maildir/new').glob('*')).read_bytes()
    assert b'Return-Path: <origin@outside.invalid>' in raw and b'SRS0' not in raw
    print('PASS plain fallback: local destination', flush=True)

    # Failure injection is confined to this disposable image's helper, not the
    # wrapper under test. A failure must not enqueue a plain-sender replacement.
    env = os.environ.copy()
    env.update(HOST='examples.invalid', NEWSENDER='origin@outside.invalid',
               SENDER='origin@outside.invalid', DTLINE='Delivered-To: forward@examples.invalid\n',
               RPLINE='Return-Path: <origin@outside.invalid>\n')
    for label, broken in [('malformed', 'examples.invalid:invalid\n'),
                          ('duplicate', policy + policy),
                          ('wrong-reverse-secret', 'examples.invalid:first|-|srs.\nsrs.examples.invalid:other|-|srs.\n')]:
        put('srsdomains', broken)
        result = subprocess.run(['/bin/s6-setuidgid', 'vpopmail', '/opt/bin/vpopmail-inject.sh',
                                 '--', 'sink@remote.invalid'], env=env, capture_output=True,
                                input=env['RPLINE'].encode() + payload.replace(b'\r\n', b'\n'))
        assert result.returncode == 111, (label, result.returncode, result.stderr)
        print('PASS policy error defers111:', label, flush=True)
    put('srsdomains', policy)
    helper = Path('/var/qmail/bin/srsforward')
    helper.rename('/var/qmail/bin/srsforward.real')
    helper.write_text('#!/bin/sh\nexit 111\n')
    helper.chmod(0o755)
    result = subprocess.run(['/bin/s6-setuidgid', 'vpopmail', '/opt/bin/vpopmail-inject.sh',
                             '--', 'sink@remote.invalid'], env=env, capture_output=True,
                            input=env['RPLINE'].encode() + payload.replace(b'\r\n', b'\n'))
    assert result.returncode == 111, (result.returncode, result.stderr)
    time.sleep(1)
    assert RESULTS.empty(), 'helper failure enqueued mail'
    helper.unlink()
    Path('/var/qmail/bin/srsforward.real').rename(helper)
    print('PASS SRS helper failure defers111 without plain reinjection', flush=True)
    print('PASS integration fixture complete', flush=True)


if __name__ == '__main__':
    try:
        main()
    finally:
        for process in PROCESSES:
            process.terminate()
            process.wait(timeout=10)
