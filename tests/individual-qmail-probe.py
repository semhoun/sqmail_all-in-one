#!/usr/bin/env python3
"""Container-only individual delivery proof; launched by individual-qmail.py.

The injector trace shim only records arguments/environment before execing the
unchanged installed wrapper. All mutations are confined to disposable state.
"""

import email.policy
from email.parser import BytesParser
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback


SPEC = importlib.util.spec_from_file_location('mail_probe', Path(__file__).with_name('mail-probe.py'))
mail = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mail)
CONTROL = Path('/var/qmail/control')
TRACE = Path('/tmp/individual-qmail-trace')
ACCOUNT = 'individual@examples.invalid'
LOCAL = 'localtarget@examples.invalid'
LDA = '|/var/qmail/bin/preline -f /usr/libexec/dovecot/deliver -d $EXT@$USER\n'
HOMES = {}


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=30).stdout.strip()


def trace(mode):
    # Subprocess modes run as vpopmail, not root.
    # qmail-send deliberately clears its environment, so use the container marker
    # and the root-created trace directory rather than inherited test variables.
    assert Path('/.dockerenv').exists() and TRACE.is_dir()
    context = {key: os.environ.get(key) for key in
               ('EXT', 'USER', 'HOST', 'SENDER', 'NEWSENDER', 'DTLINE', 'RPLINE')}
    context.update(argv=sys.argv[2:], cwd=os.getcwd(), uid=os.getuid())
    if mode == '--context':
        context['input_headers'] = sys.stdin.buffer.read().split(b'\n\n', 1)[0].decode()
    with (TRACE / ('inject.jsonl' if mode == '--inject' else 'context.jsonl')).open('a') as stream:
        stream.write(json.dumps(context) + '\n')
    if mode == '--inject':
        os.execv('/opt/bin/vpopmail-inject.proof-original',
                 ['/opt/bin/vpopmail-inject.proof-original', *sys.argv[2:]])


def qmail(contents):
    path = HOMES[ACCOUNT] / '.qmail'
    if contents is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(contents)
        os.chown(path, 89, 89)
        path.chmod(0o600)


def settled():
    deadline = time.monotonic() + 60
    stable = None
    while time.monotonic() < deadline:
        # Check both normal and not-yet-preprocessed messages, not just delivery logs.
        output = run('/var/qmail/bin/qmail-qstat')
        if all(line.rsplit(':', 1)[-1].strip() == '0' for line in output.splitlines()):
            stable = stable or time.monotonic()
            if time.monotonic() - stable >= 2:
                return
        else:
            stable = None
        time.sleep(0.2)
    raise AssertionError('queue did not drain: ' + output)


def copies(account, msg):
    found = []
    for directory in (HOMES[account] / 'Maildir').rglob('*'):
        if directory.is_file() and directory.parent.name in ('new', 'cur'):
            parsed = BytesParser(policy=email.policy.default).parsebytes(directory.read_bytes())
            if parsed.get('Message-ID') == msg['Message-ID']:
                found.append(parsed)
    return found


def content(parsed, msg):
    mail.verify_content(parsed, msg)
    for header in ('From', 'To', 'Subject', 'Date', 'Message-ID'):
        assert parsed.get_all(header) == msg.get_all(header), (header, parsed.get_all(header), msg.get_all(header))
    signatures = parsed.get_all('DKIM-Signature', [])
    assert signatures.count(msg['DKIM-Signature']) == 1, signatures
    # The normal qmail-remote path adds our domain's signature, without replacing
    # the original author's signature. The synthetic original is not crypto-valid.
    extra = [value for value in signatures if value != msg['DKIM-Signature']]
    assert len(extra) <= 1 and all('d=examples.invalid;' in value for value in extra), extra


def local_count(account, msg, count):
    found = copies(account, msg)
    assert len(found) == count, (account, msg['Subject'], len(found), count)
    for parsed in found:
        content(parsed, msg)
    if count:
        assert any(f'lda({account})' in line and str(msg['Message-ID']) in line
                   and 'sieve:' in line and 'stored_mail_into_mailbox' in line
                   for line in Path('/log/qmail-send/current').read_text().splitlines()), account
    return found


def payload(label):
    msg = mail.message(label, ACCOUNT, sender='origin@outside.invalid',
                       body='Synthetic unchanged body.\n.leading dot\n')
    msg['DKIM-Signature'] = ('v=1; a=rsa-sha256; d=outside.invalid; s=synthetic; '
                             'h=from:to:subject; bh=synthetic; b=synthetic')
    return msg


def send(msg, recipient=None, sender='origin@outside.invalid'):
    with mail.smtp() as client:
        assert not client.sendmail(sender, [recipient or ACCOUNT], msg.as_bytes(policy=email.policy.SMTP))


def remote(collector, msg, recipient, srs=True, sender=None):
    actual, recipients, raw = collector.messages.get(timeout=60)
    assert recipients == [f'<{recipient}>'], recipients
    if srs:
        assert actual.startswith('<SRS0') and actual.endswith('@srs.examples.invalid>'), actual
    else:
        assert actual == f'<{sender}>', actual
    parsed = BytesParser(policy=email.policy.default).parsebytes(raw)
    content(parsed, msg)
    if srs:
        assert parsed.get_all('Delivered-To') == [ACCOUNT], parsed.get_all('Delivered-To')
    return actual[1:-1]


def no_remote(collector):
    assert collector.messages.empty(), 'unexpected or duplicate external delivery'


def main():
    mail.guard()
    print('AIO=' + os.environ['SQMAIL_AIO_VERSION'], flush=True)
    for line in Path('/usr/local/share/sqmail-aio/source-versions.txt').read_text().splitlines():
        if line.startswith(('SQMail=', 'vpopmail/', 'Dovecot/')):
            print(line, flush=True)
    print('dovecot --version: ' + run('/usr/sbin/dovecot', '--version'), flush=True)
    assert (CONTROL / 'defaultdelivery').read_text() == LDA
    for account in (ACCOUNT, LOCAL):
        run('/var/vpopmail/bin/vadduser', account, mail.PASSWORD)
        HOMES[account] = Path(run('/var/vpopmail/bin/vuserinfo', '-d', account))
    run('/opt/bin/mksrs.sh', '-i', '192.0.2.10', 'examples.invalid')
    # All external domains including synthetic original senders end at our sink.
    (CONTROL / 'smtproutes').write_text(':127.0.0.1;2526\n')
    mail.ready()
    with mail.Collector() as collector:
        worker = threading.Thread(target=collector.serve_forever, daemon=True)
        worker.start()
        try:
            for name, form, count in [('absent', None, 1), ('empty', '', 1),
                                      ('comments', '# comment only\n', 0), ('explicit-LDA', LDA, 1)]:
                qmail(form)
                msg = payload(name)
                send(msg)
                settled()
                local_count(ACCOUNT, msg, count)
                no_remote(collector)
                print(f'PASS {name}: local copies={count}; queue drained', flush=True)

            # First prove forwarding on the entirely unmodified installed injector.
            qmail('&sink@destination.invalid\n')
            msg = payload('pristine-external-forward')
            send(msg)
            token = remote(collector, msg, 'sink@destination.invalid')
            settled()
            local_count(ACCOUNT, msg, 0)
            no_remote(collector)
            print('PASS pristine individual &address external forward: SRS and preserved headers/body', flush=True)

            TRACE.mkdir(mode=0o700)
            os.chown(TRACE, 89, 89)
            injector = Path('/opt/bin/vpopmail-inject.sh')
            injector.rename('/opt/bin/vpopmail-inject.proof-original')
            injector.write_text('#!/bin/sh\nexec /usr/bin/python3 /tests/individual-qmail-probe.py --inject "$@"\n')
            injector.chmod(0o755)

            for destination in (LOCAL, 'sink@destination.invalid'):
                for copy in (False, True):
                    qmail('&' + destination + '\n' + (LDA if copy else ''))
                    msg = payload(f'forward-{destination}-copy-{copy}')
                    send(msg)
                    if destination == LOCAL:
                        settled()
                        actual = local_count(LOCAL, msg, 1)[0]
                        assert actual['Return-Path'] == '<origin@outside.invalid>', actual['Return-Path']
                    else:
                        token = remote(collector, msg, destination)
                        bounce = payload('bounce-copy-' + str(copy))
                        send(bounce, token, sender='')
                        remote(collector, bounce, 'origin@outside.invalid', srs=False, sender='')
                        settled()
                    local_count(ACCOUNT, msg, int(copy))
                    no_remote(collector)
                    print(f'PASS &{destination} copy={copy}: exact counts, headers/body, '
                          + ('unchanged local envelope' if destination == LOCAL else 'SRS + SMTP bounce return'), flush=True)

            for name, form in [('bare-address', 'sink@destination.invalid\n'),
                               ('LDA-first-multiple', LDA + '# comment\n&' + LOCAL + '\n&sink@destination.invalid\n')]:
                qmail(form)
                msg = payload(name)
                send(msg)
                remote(collector, msg, 'sink@destination.invalid')
                settled()
                count = int(name == 'LDA-first-multiple')
                local_count(ACCOUNT, msg, count)
                local_count(LOCAL, msg, count)
                no_remote(collector)
                print('PASS ' + name, flush=True)

            for name, form in [('absent', None), ('empty', ''), ('comments', '# ignored\n'),
                               ('LDA', LDA), ('forward', '&sink@destination.invalid\n')]:
                qmail(form)
                run('/var/vpopmail/bin/valias', '-i', LOCAL, ACCOUNT)
                try:
                    msg = payload('valias-over-' + name)
                    send(msg)
                    settled()
                    local_count(LOCAL, msg, 1)
                    local_count(ACCOUNT, msg, 0)
                    no_remote(collector)
                    print('PASS valias supersedes individual ' + name, flush=True)
                finally:
                    run('/var/vpopmail/bin/valias', '-d', ACCOUNT)

            qmail('|/usr/bin/python3 /tests/individual-qmail-probe.py --context\n' + LDA)
            msg = payload('context-preline')
            send(msg)
            settled()
            actual = local_count(ACCOUNT, msg, 1)[0]
            context = json.loads((TRACE / 'context.jsonl').read_text().splitlines()[-1])
            assert (context['EXT'], context['USER'], context['HOST'], context['uid'], context['cwd']) == (
                'individual', 'examples.invalid', 'examples.invalid', 89, str(HOMES[ACCOUNT])), context
            assert not context['input_headers'].startswith('Return-Path:'), context
            assert actual['Return-Path'] == '<origin@outside.invalid>'
            assert actual.get_all('Delivered-To') == ['examples.invalid-individual@examples.invalid']
            print('PASS EXT=individual USER=HOST=examples.invalid uid=89 cwd=resolved home; '
                  'preline adds Return-Path/Delivered-To', flush=True)
            traces = [json.loads(line) for line in (TRACE / 'inject.jsonl').read_text().splitlines()]
            for entry in traces:
                assert len(entry['argv']) == 2 and entry['argv'][0] == '--', entry
                assert entry['HOST'] == 'examples.invalid' and entry['EXT'] == 'individual', entry
                assert entry['SENDER'] == entry['NEWSENDER'] == 'origin@outside.invalid', entry
                assert entry['RPLINE'] == 'Return-Path: <origin@outside.invalid>\n', entry
            assert any(entry['argv'] == ['--', 'sink@destination.invalid'] for entry in traces)
            print(f'PASS {len(traces)} injector calls: -- destination and required SRS environment', flush=True)

            # A failed local forwarding destination must bounce to the unchanged
            # original envelope sender, not to the forwarding mailbox.
            target_qmail = HOMES[LOCAL] / '.qmail'
            target_qmail.write_text('|exit 100\n')
            os.chown(target_qmail, 89, 89)
            for copy in (False, True):
                qmail('&' + LOCAL + '\n' + (LDA if copy else ''))
                msg = payload('local-target-bounce-' + str(copy))
                send(msg)
                sender, recipients, raw = collector.messages.get(timeout=60)
                assert sender == '<>' and recipients == ['<origin@outside.invalid>'], (sender, recipients)
                assert str(msg['Message-ID']).encode() in raw
                settled()
                local_count(LOCAL, msg, 0)
                local_count(ACCOUNT, msg, int(copy))
                no_remote(collector)
                print(f'PASS local target failure copy={copy}: DSN to original sender', flush=True)
            target_qmail.unlink()

            # Contrast the global fallback against an explicit individual command.
            (CONTROL / 'defaultdelivery').write_text('|exit 100\n')
            try:
                for name, form in [('absent', None), ('empty', ''), ('LDA', LDA)]:
                    qmail(form)
                    msg = payload('defaultdelivery-contrast-' + name)
                    send(msg)
                    if name != 'LDA':
                        sender, recipients, raw = collector.messages.get(timeout=60)
                        assert sender == '<>' and recipients == ['<origin@outside.invalid>']
                        assert str(msg['Message-ID']).encode() in raw
                    settled()
                    local_count(ACCOUNT, msg, int(name == 'LDA'))
                    no_remote(collector)
                    print('PASS defaultdelivery exit100 contrast: ' + name, flush=True)
            finally:
                (CONTROL / 'defaultdelivery').write_text(LDA)

            # Permanent command failure stops later actions and creates a real DSN.
            qmail('|exit 100\n&sink@destination.invalid\n')
            msg = payload('permanent-failure')
            send(msg)
            sender, recipients, raw = collector.messages.get(timeout=60)
            assert sender == '<>' and recipients == ['<origin@outside.invalid>'], (sender, recipients)
            assert str(msg['Message-ID']).encode() in raw
            settled()
            local_count(ACCOUNT, msg, 0)
            no_remote(collector)
            print('PASS command exit 100: DSN to original sender, later action skipped', flush=True)

            # Temporary command failure stays queued; recover only this synthetic message.
            qmail('|exit 111\n&sink@destination.invalid\n')
            msg = payload('temporary-failure')
            log = Path('/log/qmail-send/current')
            offset = log.stat().st_size
            send(msg)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if 'deferral:' in log.read_text()[offset:]:
                    break
                time.sleep(0.2)
            else:
                raise AssertionError('no temporary deferral logged')
            assert 'messages in queue: 1' in run('/var/qmail/bin/qmail-qstat')
            local_count(ACCOUNT, msg, 0)
            no_remote(collector)
            qmail(LDA)
            run('/bin/s6-svc', '-a', '/service/qmail-send')
            settled()
            local_count(ACCOUNT, msg, 1)
            no_remote(collector)
            print('PASS command exit 111: deferred without forwarding, recovered once after ALRM', flush=True)
        finally:
            collector.shutdown()
            worker.join(timeout=5)
    print('PASS individual .qmail delivery and SRS blocking proof', flush=True)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] in ('--inject', '--context'):
        trace(sys.argv[1])
    else:
        try:
            main()
        except Exception:
            traceback.print_exc()
            sys.exit(1)
