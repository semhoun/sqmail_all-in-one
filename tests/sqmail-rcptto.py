#!/usr/bin/python3
"""Container-only SMTP/queue contract test; never invokes the real queue.

docker run --rm --network none --entrypoint python3 \
  -e SQMAIL_DISPOSABLE_TEST=1 -v "$PWD/tests:/tests:ro" IMAGE \
  /tests/sqmail-rcptto.py

For a disposable pre-fix image, additionally mount Dockerfile read-only and pass
--patch /Dockerfile to run its exact guarded compatibility RUN before testing.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


assert Path('/.dockerenv').exists() and os.environ.get('SQMAIL_DISPOSABLE_TEST') == '1', \
    'Use only a disposable Docker container, without existing mail volumes.'

if sys.argv[1:] == ['--queue']:
    message = sys.stdin.buffer.read()
    with os.fdopen(1, 'rb') as envelope:
        records = envelope.read().split(b'\0')
    Path(os.environ['CAPTURE_DIR'], str(os.getpid()) + '.json').write_text(json.dumps({
        'rcptto': os.environ.get('RCPTTO'),
        'recipients': [item[1:].decode() for item in records if item.startswith(b'T')],
        'message': message.decode(),
    }))
    sys.exit(0)

if len(sys.argv) == 3 and sys.argv[1] == '--patch':
    section = Path(sys.argv[2]).read_text().split('# SQMail RCPTTO compatibility\n', 1)[1]
    command = section[section.index('RUN ') + 4:].split('\n\n', 1)[0]
    subprocess.run(['/bin/sh', '-ec', command], check=True,
                   env={**os.environ, 'SQMAIL_TAG': '4.4.14'})
elif len(sys.argv) != 1:
    raise SystemExit('Usage: sqmail-rcptto.py [--patch /Dockerfile]')

# These are new anonymous image volumes, not an initialized mail installation.
control = Path('/var/qmail/control')
control.mkdir(parents=True, exist_ok=True)
(control / 'me').write_text('smtp.examples.invalid\n')
(control / 'rcpthosts').write_text('examples.invalid\n')

with tempfile.TemporaryDirectory(prefix='sqmail-rcptto-') as directory:
    work = Path(directory)
    work.chmod(0o777)  # The actual smtpd and queue capture run as vpopmail.
    wrapper = work / 'queue'
    wrapper.write_text('#!/bin/sh\nexec /usr/bin/python3 "' + str(Path(__file__).resolve()) + '" --queue\n')
    wrapper.chmod(0o755)
    cases = [None, '', 'seed@examples.invalid', 'seed1@examples.invalid seed2@examples.invalid']
    for index, seed in enumerate(cases):
        captures = work / str(index)
        captures.mkdir(mode=0o777)
        captures.chmod(0o777)
        env = {
            'PATH': '/usr/bin:/bin', 'SQMAIL_DISPOSABLE_TEST': '1',
            'QMAILQUEUE': str(wrapper), 'CAPTURE_DIR': str(captures),
            'TCPREMOTEIP': '127.0.0.1', 'TCPREMOTEHOST': 'client.examples.invalid',
            'TCPLOCALIP': '127.0.0.1', 'TCPLOCALHOST': 'smtp.examples.invalid',
            'TCPLOCALPORT': '25', 'RELAYCLIENT': '',
        }
        if seed is not None:
            env['DELIVERTO'] = seed
        transcript = ['EHLO client.examples.invalid']
        expected = {}

        def start(*recipients):
            transcript.append('MAIL FROM:<sender@examples.invalid>')
            transcript.extend('RCPT TO:<' + recipient + '>' for recipient in recipients)

        def data(label, *recipients):
            expected[label] = list(recipients)
            transcript.extend(['DATA', 'Subject: ' + label, '', label, '.'])

        start('one@examples.invalid', 'two@examples.invalid')
        data('multi', 'one@examples.invalid', 'two@examples.invalid')
        start('scan@examples.invalid')
        data('second', 'scan@examples.invalid')
        start('abandoned@examples.invalid')
        transcript.extend(['RSET', 'RCPT TO:<invalid-after-rset@examples.invalid>', 'DATA'])
        start('after-reset@examples.invalid')
        data('reset', 'after-reset@examples.invalid')
        start('superseded@examples.invalid')
        start('replacement@examples.invalid')
        data('replacement', 'replacement@examples.invalid')
        transcript.append('EHLO client.examples.invalid')
        start('last@examples.invalid')
        data('ehlo', 'last@examples.invalid')
        transcript.append('QUIT')

        result = subprocess.run(
            ['/bin/s6-setuidgid', 'vpopmail', '/var/qmail/bin/qmail-smtpd'],
            input=('\r\n'.join(transcript) + '\r\n').encode(), env=env,
            capture_output=True, timeout=30,
        )
        assert result.returncode == 0, (result.returncode, result.stderr.decode())
        replies = result.stdout.decode().splitlines()
        assert sum(line.startswith('354 ') for line in replies) == 5, replies
        assert sum(line.startswith('503 ') for line in replies) == 2, replies
        assert replies[-1].startswith('221 '), replies
        rows = [json.loads(path.read_text()) for path in captures.glob('*.json')]
        assert len(rows) == len(expected), (len(rows), replies, result.stderr.decode())
        seen = set()
        for row in rows:
            label = row['message'].split('Subject: ', 1)[1].splitlines()[0]
            assert label not in seen, label
            seen.add(label)
            recipients = expected[label]
            assert row['recipients'] == recipients, row
            prefix = '' if seed is None else seed + ' '
            value = prefix + ''.join(recipient + ' ' for recipient in recipients)
            assert row['rcptto'] == value, (label, repr(row['rcptto']), repr(value))
        assert seen == set(expected), seen
        print('PASS 5 SMTP transactions, exact RCPTTO/envelopes; DELIVERTO=' + repr(seed))

print('PASS 20 queue captures: no Z/over-read bytes, all recipients/trailing space preserved,')
print('MAIL/RSET/EHLO isolation and DELIVERTO prefix preserved; no real queue or external mail.')
