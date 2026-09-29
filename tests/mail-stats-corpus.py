#!/usr/bin/env python3
"""Capture a small synthetic log contract; never run against existing containers.

python3 tests/mail-stats-corpus.py --image sqmail_aio-sqmail_aio:latest --database-image mariadb:latest
Fixtures are generated output, not invented parser examples. --output must be a
new tests/fixtures/mail-stats*.json path. No message bodies or subjects are saved.
"""

import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import re
import signal
import socketserver
import subprocess
import sys
import threading
import time

from mail import MailEnvironment


SOURCES = ('qmail-send', 'qmail-smtpd', 'qmail-smtpsd', 'qmail-smtpsub',
           'dovecot', 'spamd', 'clamd', 'vusaged', 'lighttpd', 'php-fpm', 'fcron')
# Selection is deliberately narrower than collection: unknown lines stay out.
SELECT = {
    'qmail-send': r'(starting delivery|delivery \d+:|new msg |info msg |end msg |status:|bounce msg |running|exiting)',
    'qmail-smtpd': r'(tcpserver:|qmail-smtpd:)',
    'qmail-smtpsd': r'(tcpserver:|qmail-smtpd:)',
    'qmail-smtpsub': r'(tcpserver:|qmail-smtpd:)',
    'dovecot': r'(Login:|Disconnected:|auth failed|Dovecot v)',
    'spamd': r'(spamd: (clean message|identified spam|result:|server started|processing message))',
    'clamd': r'(FOUND|SelfCheck:|Loaded \d+ signatures)',
    'vusaged': r'(error|warning|started|listening)',
    'lighttpd': r'(server started|server stopped|error|HTTP/1\.[01])',
    'php-fpm': r'(NOTICE:|WARNING:|ERROR:)',
    'fcron': r'(started|error|warning)',
}


def load_probe():
    spec = importlib.util.spec_from_file_location('mail_probe', Path(__file__).with_name('mail-probe.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def probe():
    p = load_probe()
    p.guard()
    results = []
    def wait_log(pattern):
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if re.search(pattern, Path('/log/qmail-send/current').read_text()):
                return
            time.sleep(.25)
        raise AssertionError('qmail-send expected event absent: ' + pattern)

    class RejectRecipient(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(15)
            self.wfile.write(b'220 collector.destination.invalid ESMTP\r\n')
            while True:
                command = self.rfile.readline(4096).upper()
                if not command:
                    return
                if command.startswith(b'RCPT'):
                    self.wfile.write(self.server.verdict)
                elif command.startswith(b'QUIT'):
                    self.wfile.write(b'221 bye\r\n')
                    return
                else:
                    self.wfile.write(b'250 collector.destination.invalid\r\n')

    with contextlib.redirect_stdout(io.StringIO()):
        p.ready()
        with p.Collector() as collector:
            worker = threading.Thread(target=collector.serve_forever, daemon=True)
            worker.start()
            try:
                for name, case in (
                    ('local_delivery', p.reception), ('alias_delivery', p.alias),
                    ('relay_rejected', p.relay_rejected),
                    ('submission_rejected', p.submission_rejected),
                    ('authenticated_remote_delivery', lambda: p.outbound(collector)),
                    ('spam_delivered_to_junk', p.spam_delivered),
                    ('spam_rejected', p.spam_rejected), ('attachments_and_virus', p.attachments),
                ):
                    case()
                    results.append(name)
                # Real qmail-remote sees a disposable loopback SMTP peer, never DNS.
                collector.RequestHandlerClass = RejectRecipient
                collector.verdict = b'550 synthetic permanent recipient rejection\r\n'
                p.send(p.message('permanent', 'failed@destination.invalid', sender=p.ALICE),
                       port=587, authenticate=True)
                wait_log(r'delivery \d+: failure:')
                wait_log(r'bounce msg ')
                results.append('remote_permanent_failure_and_bounce')
                collector.verdict = b'451 synthetic temporary recipient rejection\r\n'
                p.send(p.message('temporary', 'retry@destination.invalid', sender=p.ALICE),
                       port=587, authenticate=True)
                wait_log(r'delivery \d+: deferral:')
                collector.RequestHandlerClass = p.CollectorHandler
                subprocess.run(['s6-svc', '-a', '/service/qmail-send'], check=True, timeout=10)
                collector.messages.get(timeout=40)
                results.append('remote_deferral_then_retry')
                with p.smtp(587) as client:
                    client.login(p.ALICE, p.PASSWORD)
                    assert not client.sendmail(p.ALICE, [p.ALICE, p.BOB],
                                               p.message('multi').as_bytes(policy=p.email.policy.SMTP))
                results.append('smtp_multiple_recipients_accepted')
            finally:
                collector.shutdown()
                worker.join(timeout=5)
        with p.smtplib.SMTP_SSL('127.0.0.1', 465, context=p.TLS, timeout=15,
                               source_address=('127.0.0.2', 0)) as client:
            assert client.ehlo('client.examples.invalid')[0] == 250
            assert client.login(p.ALICE, p.PASSWORD)[0] == 235
            assert client.mail(p.ALICE)[0] == 250
            reply = client.rcpt(p.BOB)
            assert reply[0] == 250, reply
        results.append('implicit_tls_smtp_recipient_accepted')
        import poplib
        client = poplib.POP3_SSL('127.0.0.1', 995, context=p.TLS, timeout=15)
        try:
            client.user(p.BOB)
            client.pass_(p.PASSWORD)
            client.stat()
        finally:
            client.quit()
        results.append('pop3_login')
        import http.client
        client = http.client.HTTPSConnection('127.0.0.1', 443, context=p.TLS, timeout=15)
        try:
            client.request('GET', '/mail-stats-corpus-not-found')
            response = client.getresponse()
            assert response.status in (301, 302, 401, 403, 404), response.status
            response.read(4096)
        finally:
            client.close()
        results.append('https_missing_route')
        subprocess.run(['s6-svc', '-r', '/service/qmail-send'], check=True, timeout=10)
        wait_log('exiting')
        results.append('qmail_send_restart')
    time.sleep(2)
    sources = {}
    for source in SOURCES:
        path = Path('/log') / source / 'current'
        if not path.is_file():
            sources[source] = {'state': 'absent', 'lines': []}
            continue
        # Bounded reads only from known log paths in the guarded synthetic fixture.
        with path.open('rb') as stream:
            data = stream.read(256 * 1024 + 1)
        assert len(data) <= 256 * 1024, 'synthetic log budget exceeded'
        lines = data.decode('utf-8', errors='replace').splitlines()
        selected = [line for line in lines if re.search(SELECT[source], line, re.I)]
        timestamp_shapes = set()
        for line in selected:
            prefix = re.match(r'(?:\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(?:\.\d+)?|'
                              r'[A-Z][a-z]{2} \d+ \d\d:\d\d:\d\d(?:\.\d+)?|'
                              r'\[\d\d-[A-Z][a-z]{2}-\d{4} \d\d:\d\d:\d\d\])', line)
            if prefix:
                timestamp_shapes.add(re.sub(r'\d', 'D', prefix[0]))
        state = subprocess.run(['s6-svstat', '-o', 'up', '/service/' + source],
                               capture_output=True, text=True, timeout=5)
        sources[source] = {'state': 'observed' if selected else 'no_selected_events',
                           'service_up': state.stdout.strip() == 'true',
                           'observed_lines': len(lines), 'lines': selected,
                           'timestamp_prefix_shapes': sorted(timestamp_shapes),
                           'archive_names': sorted(f.name for f in path.parent.glob('@*'))}
    print(json.dumps({'assertions_passed': results, 'sources': sources,
                      'runtime_clock': subprocess.check_output(['date', '+%Z %z'], text=True).strip()}))


def anonymize(document):
    for source, record in document['sources'].items():
        selected = []
        shapes = set()
        for line in record['lines']:
            # Do not retain subject/body, passwords, TLS session tokens or Message-ID.
            if re.search(r'(subject:|password|SyntheticMailOnly|SyntheticDbOnly|SyntheticRootOnly|XJS\*|X5O!)', line, re.I):
                continue
            line = re.sub(r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(\.\d+)?',
                          lambda m: '2000-01-01 00:00:00' + ('.' + '0' * (len(m[1]) - 1) if m[1] else ''), line)
            line = re.sub(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)([ _])\d+([ _])\d\d:\d\d:\d\d(\.\d+)?',
                          lambda m: 'Jan' + m[1] + '01' + m[2] + '00:00:00' + ('.000' if m[3] else ''), line)
            line = re.sub(r'\d\d/[A-Z][a-z]{2}/\d{4}:\d\d:\d\d:\d\d', '01/Jan/2000:00:00:00', line)
            line = re.sub(r'\d\d-[A-Z][a-z]{2}-\d{4} \d\d:\d\d:\d\d', '01-Jan-2000 00:00:00', line)
            line = re.sub(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+ \d\d:\d\d:\d\d \d{4}', 'Sat Jan  1 00:00:00 2000', line)
            line = re.sub(r'<mail-probe-[^<>]*>', '<message-id@examples.invalid>', line)
            line = re.sub(r'(session=)<[^>]*>', r'\1<session-redacted>', line)
            line = re.sub(r'<\d+><[^>]*>', '<100><session-redacted>', line)
            line = re.sub(r'\b[0-9a-f]{32,}\b', '00000000000000000000000000000000', line)
            line = re.sub(r'\b(?:10|172|192)\.\d+\.\d+\.\d+\b', '192.0.2.1', line)
            # Preserve numeric grammar while replacing nondeterministic numeric fields.
            line = re.sub(r'(?<=pid=)\d+|(?<=pid )\d+|(?<=\[)\d+(?=\])', '100', line)
            line = re.sub(r'(?<=rport=)\d+|(?<=127.0.0.1@)\d+', '12345', line)
            shape = re.sub(r'\d+', '#', line)
            if shape not in shapes:
                shapes.add(shape)
                selected.append(line)
            if len(selected) == 24:
                break
        record['lines'] = selected
        record['state'] = 'observed' if selected else 'no_selected_events'
        if source == 'fcron' and not record.get('service_up'):
            record['state'] = 'disabled_by_fixture'
    return document


def validate(document):
    if set(document['sources']) != set(SOURCES):
        raise ValueError('Incomplete source inventory')
    for source, record in document['sources'].items():
        if len(record['lines']) > 24:
            raise ValueError('Corpus line budget exceeded')
        if record['service_up'] != (source != 'fcron'):
            raise ValueError('Unexpected supervised service state: ' + source)
    if document['sources']['fcron']['observed_lines'] != 0:
        raise ValueError('Disabled fcron unexpectedly emitted events')
    expected = {
        'qmail-send': [r'delivery \d+: success:', r'delivery \d+: failure:',
                       r'delivery \d+: deferral:', r'bounce msg ', r'exiting'],
        'qmail-smtpd': ['Reject::SNDR::Invalid_Relay', 'Reject::DATA::Spam_Message',
                        'Reject::DATA::Virus_Infected'],
        'qmail-smtpsd': ['Accept::AUTH::'],
        'qmail-smtpsub': ['Reject::AUTH::', 'Accept::AUTH::'],
        'dovecot': ['imap-login:', 'pop3-login:', 'Disconnected:'],
        'spamd': ['identified spam', 'clean message', 'result:'],
        'clamd': ['MailTest.Eicar.Synthetic.UNOFFICIAL FOUND'],
        'lighttpd': ['server started', 'HTTP/1.1" 404'],
        'php-fpm': ['ready to handle connections'],
    }
    for source, patterns in expected.items():
        text = '\n'.join(document['sources'][source]['lines'])
        for pattern in patterns:
            if not re.search(pattern, text):
                raise ValueError(f'Missing observed log assertion: {source}: {pattern}')
    text = json.dumps(document['sources'])
    if re.search(r'Synthetic(?:Mail|Db|Root)Only|mail-probe-|Subject:|XJS\*|X5O!|\?[^ "\\]*=', text, re.I):
        raise ValueError('Forbidden payload/credential/query data in corpus')
    document['log_assertions'] = expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='sqmail_aio-sqmail_aio:latest')
    parser.add_argument('--database-image', default='mariadb:latest')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--check', type=Path, help='Validate a saved corpus without Docker')
    parser.add_argument('--probe', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.check:
        validate(json.loads(args.check.read_text()))
        print('PASS: saved corpus format and privacy assertions')
        return 0
    if args.probe:
        probe()
        return 0
    if args.output:
        target = args.output.resolve()
        expected = Path(__file__).resolve().parent / 'fixtures'
        if target.parent != expected or not re.fullmatch(r'mail-stats[^/]*\.json', target.name) or target.exists():
            parser.error('--output must be a new tests/fixtures/mail-stats*.json file')
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    environment = MailEnvironment(args.image, args.database_image)
    try:
        environment.prepare()
        result = environment.docker('exec', environment.mail, 'python3',
                                    '/tests/mail-stats-corpus.py', '--probe', timeout=420)
        document = anonymize(json.loads(result.stdout))
        validate(document)
        document['provenance'] = {
            'image_id': environment.docker('image', 'inspect', '--format', '{{.Id}}', args.image).stdout.strip(),
            'database_image_id': environment.docker('image', 'inspect', '--format', '{{.Id}}', args.database_image).stdout.strip(),
            'generator': 'tests/mail-stats-corpus.py',
            'isolation': 'MailEnvironment UUID internal network; tmpfs DB; no ports; ownership-checked cleanup',
            'normalization': 'timestamps, Message-ID, session, long hex, private IP, ephemeral port and PID; one example per numeric line shape; at most 24/source; grammar samples NOT a chronological/correlatable stream',
            'clamav': 'synthetic fixture signature, not official feed coverage',
            'gaps': ['fcron deliberately disabled; no scheduled maintenance', 'SQL traces and mutable states not collected',
                     'no rotation or timezone-offset/DST scenarios; multiple recipient acceptance not individual delivery verification',
                     'no web login, admin audit, Roundcube, Fetchmail or ACME scenarios'],
        }
        text = json.dumps(document, indent=2, sort_keys=True) + '\n'
        if args.output:
            with target.open('x') as stream:
                stream.write(text)
        else:
            print(text)
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        # Never call environment.logs(): startup logs may contain credentials.
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    finally:
        environment.cleanup()
    print('PASS: synthetic corpus collected; disposable resources removed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
