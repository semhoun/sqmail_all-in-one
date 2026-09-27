#!/usr/bin/env python3
"""Real mail-flow checks, run as root inside the disposable mail fixture only."""

import email.policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import formatdate
import imaplib
import os
from pathlib import Path
import queue
import smtplib
import socket
import socketserver
import ssl
import struct
import subprocess
import sys
import threading
import time
import traceback
import uuid


PASSWORD = 'SyntheticMailOnly927'
ALICE = 'alice@examples.invalid'
BOB = 'bob@examples.invalid'
GTUBE = 'XJS*C4JDBQADN1.NSBN3*2IDNEN*GTUBE-STANDARD-ANTI-UBE-TEST-EMAIL*C.34X'
EICAR = rb'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'
TIMEOUT = 90
# The fixture uses a synthetic, self-signed certificate, never a public endpoint.
TLS = ssl._create_unverified_context()


def require(condition, detail):
    if not condition:
        raise AssertionError(detail)


def guard():
    marker = os.environ.get('SQMAIL_MAIL_TEST_RUN', '')
    require(os.environ.get('SQMAIL_DISPOSABLE_TEST') == '1' and marker
            and os.geteuid() == 0, 'refusing execution outside disposable root fixture')
    require(Path('/tmp/sqmail-mail-test-run').read_text().strip() == marker,
            'disposable fixture marker mismatch')


def message(label, recipient=BOB, body=None, sender='sender@outside.invalid'):
    msg = EmailMessage()
    token = f'mail-probe-{label}-{uuid.uuid4().hex}'
    msg['From'] = sender
    msg['To'] = recipient
    msg['Subject'] = token
    msg['Message-ID'] = f'<{token}@examples.invalid>'
    msg['Date'] = formatdate(usegmt=True)
    msg.set_content(body or f'Synthetic mail payload {token}. No external delivery.')
    return msg


def smtp(port=25):
    client = smtplib.SMTP('127.0.0.1', port, timeout=TIMEOUT,
                          source_address=('127.0.0.2', 0))
    try:
        require(client.ehlo('client.examples.invalid')[0] == 250, 'EHLO failed')
        require(client.starttls(context=TLS)[0] == 220, 'STARTTLS failed')
        require(client.ehlo('client.examples.invalid')[0] == 250, 'TLS EHLO failed')
        return client
    except BaseException:
        client.close()
        raise


def send(msg, expected=250, port=25, authenticate=False):
    with smtp(port) as client:
        if authenticate:
            require(client.login(ALICE, PASSWORD)[0] == 235, 'SMTP authentication failed')
        require(client.mail(str(msg['From']))[0] == 250, 'MAIL FROM rejected before DATA')
        require(client.rcpt(str(msg['To']))[0] == 250, 'RCPT TO rejected before DATA')
        # Distinguish a pre-body rejection from the final scanner verdict.
        client.putcmd('DATA')
        code, reply = client.getreply()
        require(code == 354, ('DATA initiation failed', code, reply))
        wire = msg.as_bytes(policy=email.policy.SMTP)
        wire = b'\r\n'.join(b'.' + line if line.startswith(b'.') else line
                            for line in wire.split(b'\r\n'))
        client.send(wire + (b'' if wire.endswith(b'\r\n') else b'\r\n') + b'.\r\n')
        code, reply = client.getreply()
        require(code == expected, ('final DATA response', expected, code, reply))
        return reply


def mailbox_snapshot(msg):
    found = []
    with imaplib.IMAP4_SSL('127.0.0.1', 993, ssl_context=TLS, timeout=15) as client:
        require(client.login(BOB, PASSWORD)[0] == 'OK', 'IMAP login failed')
        # The fresh fixture delivers only to these folders; examine both to catch
        # duplicates and incorrect spam routing, without changing Seen flags.
        for folder in ('INBOX', 'Junk'):
            status, rows = client.select(folder, readonly=True)
            require(status == 'OK', ('cannot examine mailbox', folder, rows))
            status, rows = client.uid('SEARCH', None, 'HEADER', 'Message-ID',
                                      f'"{msg["Message-ID"]}"')
            require(status == 'OK', ('IMAP search failed', rows))
            for uid in rows[0].split():
                status, data = client.uid('FETCH', uid, '(BODY.PEEK[])')
                require(status == 'OK', ('IMAP fetch failed', uid))
                literals = [row[1] for row in data if isinstance(row, tuple)]
                require(len(literals) == 1, 'expected one full message literal')
                parsed = BytesParser(policy=email.policy.default).parsebytes(literals[0])
                require(parsed.get_all('Message-ID') == [str(msg['Message-ID'])],
                        'Message-ID not preserved exactly once')
                found.append((folder, parsed))
    return found


def verify_content(actual, expected):
    require(str(actual['From']) == str(expected['From']), 'From header changed')
    require(actual.get_all('Message-ID') == [str(expected['Message-ID'])],
            'Message-ID changed or duplicated')
    require(actual.get_body(preferencelist=('plain',)).get_content().replace('\r\n', '\n')
            == expected.get_body(preferencelist=('plain',)).get_content().replace('\r\n', '\n'),
            'plain message body changed')
    require([(p.get_filename(), p.get_payload(decode=True)) for p in actual.iter_attachments()]
            == [(p.get_filename(), p.get_payload(decode=True)) for p in expected.iter_attachments()],
            'attachment payload changed')


def delivered(msg, folder='INBOX'):
    deadline = time.monotonic() + TIMEOUT
    stable_until = None
    while time.monotonic() < deadline:
        found = mailbox_snapshot(msg)
        require(len(found) <= 1, 'duplicate delivery')
        if found:
            require(found[0][0] == folder, ('wrong destination folder', found[0][0], folder))
            actual = found[0][1]
            if folder == 'Junk':
                require(str(actual.get('X-Spam-Flag', '')).upper() == 'YES', 'spam flag missing')
                # report_safe=1 preserves the original as a message/rfc822 attachment.
                originals = [part for part in actual.walk() if part.get_content_type() == 'message/rfc822']
                if originals:
                    require(len(originals) == 1 and len(originals[0].get_payload()) == 1,
                            'ambiguous original message in spam report')
                    actual = originals[0].get_payload()[0]
            verify_content(actual, msg)
            if stable_until is None:
                stable_until = time.monotonic() + 3
            if time.monotonic() >= stable_until:
                return
        else:
            require(stable_until is None, 'delivered message disappeared')
        time.sleep(0.5)
    raise AssertionError(f'delivery timed out: {msg["Subject"]}')


def absent(msg):
    deadline = time.monotonic() + 8
    while True:
        require(not mailbox_snapshot(msg), 'rejected message was delivered')
        if time.monotonic() >= deadline:
            return
        time.sleep(0.5)


def threshold(value):
    subprocess.run(['bash', '/tests/fixtures/mail-server.sh', 'threshold', str(value)],
                   check=True, timeout=30, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def ready():
    deadline = time.monotonic() + TIMEOUT
    last = None
    while time.monotonic() < deadline:
        try:
            with imaplib.IMAP4_SSL('127.0.0.1', 993, ssl_context=TLS, timeout=15) as client:
                require(client.login(BOB, PASSWORD)[0] == 'OK', 'IMAP login failed')
                if client.select('Junk', readonly=True)[0] != 'OK':
                    require(client.create('Junk')[0] == 'OK', 'cannot create fixture Junk mailbox')
            mailbox_snapshot(message('readiness'))
            with smtp() as client:
                require(client.noop()[0] == 250, 'SMTP not ready')
            with smtp(587) as client:
                require(client.noop()[0] == 250, 'submission not ready')
            with socket.create_connection(('127.0.0.1', 3310), timeout=10) as connection:
                connection.sendall(b'zINSTREAM\0' + struct.pack('!I', len(EICAR))
                                   + EICAR + b'\0\0\0\0')
                result = connection.recv(4096)
                require(b'FOUND' in result, ('real clamd does not detect fixture EICAR', result))
            result = subprocess.run(['/usr/local/bin/spamc', '-x', '-u', BOB],
                                    input=message('ready-gtube', body=GTUBE).as_bytes(),
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
            require(result.returncode == 0, ('spamc failed', result.stderr[-1000:]))
            parsed = BytesParser(policy=email.policy.default).parsebytes(result.stdout)
            require(str(parsed.get('X-Spam-Flag', '')).upper() == 'YES'
                    and 'GTUBE' in str(parsed.get('X-Spam-Status', '')),
                    'actual SpamAssassin did not classify GTUBE')
            print('READY real ClamAV synthetic signature and SpamAssassin GTUBE rule', flush=True)
            return
        except (OSError, AssertionError, smtplib.SMTPException, imaplib.IMAP4.error,
                subprocess.TimeoutExpired) as error:
            last = error
            time.sleep(1)
    raise AssertionError(f'scanner/service readiness timeout: {last}')


class Collector(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        self.messages = queue.Queue()
        super().__init__(('127.0.0.1', 2526), CollectorHandler)


class CollectorHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(20)
        sender, recipients = None, []
        self.wfile.write(b'220 collector.destination.invalid ESMTP\r\n')
        while True:
            line = self.rfile.readline(65537)
            if not line:
                return
            command = line.decode('ascii', errors='replace').strip()
            verb = command.split(' ', 1)[0].upper()
            if verb in ('EHLO', 'HELO', 'NOOP'):
                reply = b'250 collector.destination.invalid\r\n'
            elif verb == 'MAIL' and command.upper().startswith('MAIL FROM:'):
                sender, recipients = command[10:].strip(), []
                reply = b'250 sender accepted\r\n'
            elif verb == 'RCPT' and command.upper().startswith('RCPT TO:'):
                recipients.append(command[8:].strip())
                reply = b'250 recipient accepted\r\n'
            elif verb == 'DATA' and sender is not None and recipients:
                self.wfile.write(b'354 send message\r\n')
                lines, size = [], 0
                while True:
                    line = self.rfile.readline(65537)
                    if not line:
                        return
                    if line == b'.\r\n':
                        break
                    size += len(line)
                    if size > 1024 * 1024:
                        return
                    lines.append(line[1:] if line.startswith(b'..') else line)
                self.server.messages.put((sender, recipients, b''.join(lines)))
                reply = b'250 collected\r\n'
                sender, recipients = None, []
            elif verb == 'RSET':
                sender, recipients = None, []
                reply = b'250 reset\r\n'
            elif verb == 'QUIT':
                self.wfile.write(b'221 bye\r\n')
                return
            else:
                reply = b'502 unsupported command\r\n'
            self.wfile.write(reply)


def reception():
    msg = message('reception')
    send(msg)
    delivered(msg)


def alias():
    msg = message('alias', 'team@examples.invalid')
    send(msg)
    delivered(msg)


def relay_rejected():
    with smtp() as client:
        require(client.mail(ALICE)[0] == 250, 'relay check failed at MAIL FROM')
        code, reply = client.rcpt('recipient@destination.invalid')
        require(500 <= code < 600 and (b'relay' in reply.lower() or b'rcpthosts' in reply.lower()),
                ('unauthenticated relay not explicitly denied at RCPT', code, reply))


def submission_rejected():
    with smtp(587) as client:
        code, reply = client.mail(ALICE)
        if code == 250:
            code, reply = client.rcpt('recipient@destination.invalid')
        require(code in (530, 535, 553, 554) and b'auth' in reply.lower(),
                ('anonymous submission not explicitly denied', code, reply))
    with smtp(587) as client:
        try:
            client.login(ALICE, 'DeliberatelyWrongPassword')
        except smtplib.SMTPAuthenticationError as error:
            require(error.smtp_code == 535, ('unexpected AUTH failure', error.smtp_code))
        else:
            raise AssertionError('wrong password accepted')


def outbound(collector):
    msg = message('outbound', 'recipient@destination.invalid', sender=ALICE)
    send(msg, port=587, authenticate=True)
    sender, recipients, data = collector.messages.get(timeout=TIMEOUT)
    require(sender == f'<{ALICE}>', ('outbound envelope sender', sender))
    require(recipients == ['<recipient@destination.invalid>'], ('outbound envelope recipients', recipients))
    verify_content(BytesParser(policy=email.policy.default).parsebytes(data), msg)
    try:
        collector.messages.get(timeout=3)
    except queue.Empty:
        return
    raise AssertionError('duplicate outbound delivery')


def spam_delivered():
    threshold(0)
    msg = message('gtube-junk', body=GTUBE)
    send(msg)
    delivered(msg, 'Junk')


def spam_rejected():
    threshold(10)
    try:
        msg = message('gtube-rejected', body=GTUBE)
        send(msg, expected=554)
        absent(msg)
    finally:
        threshold(0)


def attachments():
    clean = message('clean-attachment')
    clean.add_attachment(b'Harmless synthetic attachment.\n', maintype='application',
                         subtype='octet-stream', filename='attachment.bin')
    send(clean)
    delivered(clean)
    infected = message('eicar-attachment')
    infected.add_attachment(EICAR, maintype='application', subtype='octet-stream', filename='attachment.bin')
    send(infected, expected=554)
    absent(infected)


def diagnostics():
    for name in ('qmail-smtpd', 'qmail-smtpsub', 'qmail-send', 'spamd', 'clamd', 'dovecot'):
        path = Path('/log') / name / 'current'
        try:
            with path.open('rb') as stream:
                stream.seek(max(0, path.stat().st_size - 2500))
                print(f'--- {name} (synthetic fixture only) ---', file=sys.stderr)
                print(stream.read().decode(errors='replace'), file=sys.stderr)
        except OSError:
            pass


def main():
    # Do not even read logs until the explicit disposable-fixture guard passes.
    try:
        guard()
    except (OSError, AssertionError) as error:
        print(f'REFUSED: {error}', file=sys.stderr)
        return 2
    try:
        ready()
        threshold(0)
        with Collector() as collector:
            worker = threading.Thread(target=collector.serve_forever, daemon=True)
            worker.start()
            try:
                cases = (reception, alias, relay_rejected, submission_rejected,
                         lambda: outbound(collector), spam_delivered, spam_rejected, attachments)
                for index, case in enumerate(cases, 1):
                    case()
                    print(f'PASS {index}/8 {"authenticated_outbound" if index == 5 else case.__name__}', flush=True)
            finally:
                collector.shutdown()
                worker.join(timeout=5)
                require(not worker.is_alive(), 'collector thread failed to stop')
        print('PASS all 8 real mail-flow cases; no external delivery', flush=True)
        return 0
    except Exception:
        traceback.print_exc()
        diagnostics()
        return 1


if __name__ == '__main__':
    sys.exit(main())
