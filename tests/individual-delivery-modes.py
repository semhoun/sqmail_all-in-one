#!/usr/bin/env python3
"""Native individual delivery modes in an isolated MailEnvironment.

python3 -B tests/individual-delivery-modes.py --image sqmail-aio:user-delivery-20260928
Only disposable synthetic accounts are changed. No helper or runtime overlays.
"""

import argparse
from email.parser import BytesParser
import email.policy
import importlib.util
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time


LDA_NO_SIEVE = ('|/var/qmail/bin/preline -f /usr/libexec/dovecot/deliver '
                '-o mail_plugins/sieve=no -d $EXT@$USER\n')
DISCARD = '# SQMail AIO: discard messages for this mailbox\n'
DESTINATION = 'sink@destination.invalid'


def probe():
    spec = importlib.util.spec_from_file_location(
        'individual_proof', Path(__file__).with_name('individual-qmail-probe.py'))
    proof = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(proof)
    proof.mail.guard()
    run = proof.run
    account = proof.ACCOUNT
    run('/var/vpopmail/bin/vadduser', account, proof.mail.PASSWORD)
    home = Path(run('/var/vpopmail/bin/vuserinfo', '-d', account))
    proof.HOMES[account] = home
    domain = home.parent
    default = (domain / '.qmail-default').read_text()
    assert default == "| /var/vpopmail/bin/vdelivermail '' delete\n", default
    print('DOMAIN ' + repr(default), flush=True)
    run('/opt/bin/mksrs.sh', '-i', '192.0.2.10', 'examples.invalid')
    (proof.CONTROL / 'smtproutes').write_text(':127.0.0.1;2526\n')
    script = 'require ["fileinto", "mailbox"];\nfileinto :create "Junk";\n'
    argv = ['setpriv', '--reuid=89', '--regid=89', '--clear-groups',
            'doveadm', 'sieve']
    subprocess.run([*argv, 'put', '-u', account, 'individual-modes'], input=script,
                   text=True, check=True, capture_output=True, timeout=30)
    run(*argv, 'activate', '-u', account, 'individual-modes')
    assert (home / '.sieve/dovecot.sieve').readlink() == Path('individual-modes.sieve')
    normal_plugins = run('doveconf', '-n', 'mail_plugins')
    no_sieve_plugins = run('doveconf', '-o', 'mail_plugins/sieve=no', '-n', 'mail_plugins')
    assert 'quota = yes' in normal_plugins and 'quota = yes' in no_sieve_plugins
    print('PLUGIN CONFIG baseline=' + repr(normal_plugins) + ' no-Sieve=' + repr(no_sieve_plugins), flush=True)
    proof.mail.ready()
    observations = []

    def locations(msg):
        found = []
        # Scan every synthetic mailbox, including all folders, for unexpected
        # local recipients as well as duplicates in the intended mailbox.
        for path in domain.rglob('*'):
            if path.is_file() and path.parent.name in ('new', 'cur'):
                parsed = BytesParser(policy=email.policy.default).parsebytes(path.read_bytes())
                if parsed.get('Message-ID') == msg['Message-ID']:
                    proof.content(parsed, msg)
                    found.append(str(path.parent.parent.relative_to(domain)))
        return sorted(found)

    def expect(msg, folders):
        expected = sorted('individual/Maildir' + ('/.Junk' if f == 'Junk' else '')
                          for f in folders)
        actual = locations(msg)
        assert actual == expected, (str(msg['Subject']), actual, expected)

    def quiet(collector):
        proof.settled()
        # Queue drained includes both preprocessed and not-yet-preprocessed mail.
        # Keep checking outcomes during an additional quiet window, not a single
        # absence snapshot immediately after SMTP acceptance.
        until = time.monotonic() + 3
        while time.monotonic() < until:
            proof.no_remote(collector)
            for msg, folders in observations:
                expect(msg, folders)
            time.sleep(0.2)

    with proof.mail.Collector() as collector:
        worker = threading.Thread(target=collector.serve_forever, daemon=True)
        worker.start()
        try:
            for label, form, folders in (
                    ('LDA-personal-Sieve', proof.LDA, ['Junk']),
                    ('LDA-without-Sieve', LDA_NO_SIEVE, ['INBOX'])):
                proof.qmail(form)
                msg = proof.payload(label)
                proof.send(msg)
                proof.settled()
                expect(msg, folders)
                observations.append((msg, folders))
                quiet(collector)
                print('PASS ' + label + ': exactly one ' + folders[0]
                      + '; form=' + repr(form), flush=True)

            # Exercise both action orders. This proves successful delivery counts,
            # not transactional exactly-once semantics after a later action fails.
            for label, form in (
                    ('LDA-no-Sieve-first', LDA_NO_SIEVE + '&' + DESTINATION + '\n'),
                    ('forward-LDA-no-Sieve', '&' + DESTINATION + '\n' + LDA_NO_SIEVE)):
                proof.qmail(form)
                msg = proof.payload(label)
                proof.send(msg)
                token = proof.remote(collector, msg, DESTINATION)
                bounce = proof.payload(label + '-bounce')
                proof.send(bounce, token, sender='')
                proof.remote(collector, bounce, 'origin@outside.invalid', srs=False, sender='')
                proof.settled()
                observations.extend(((msg, ['INBOX']), (bounce, [])))
                quiet(collector)
                print('PASS ' + label + ': one INBOX copy, SRS outbound, null-sender '
                      'SMTP bounce returns origin; form=' + repr(form), flush=True)

            proof.qmail(DISCARD)
            assert (home / '.qmail').read_bytes() == DISCARD.encode('ascii')
            discarded = proof.payload('explicit-discard-marker')
            proof.send(discarded)
            observations.append((discarded, []))
            quiet(collector)
            print('PASS discard: SMTP accepted, no local/forward/bounce, quiet empty queue; '
                  'form=' + repr(DISCARD), flush=True)

            # Reenable both delivery and forwarding, force queued-message retry,
            # and send a positive control. Previously discarded mail must not
            # reappear locally, remotely, or as a DSN after this transition.
            proof.qmail(LDA_NO_SIEVE + '&' + DESTINATION + '\n')
            run('/bin/s6-svc', '-a', '/service/qmail-send')
            control = proof.payload('reenabled-positive-control')
            proof.send(control)
            proof.remote(collector, control, DESTINATION)
            observations.append((control, ['INBOX']))
            quiet(collector)
            proof.qmail(proof.LDA)
            run('/bin/s6-svc', '-a', '/service/qmail-send')
            quiet(collector)
            print('PASS reenable + ALRM + positive control + LDA restoration: '
                  'all earlier per-message counts unchanged; discard never replayed', flush=True)

            # Prove unchanged production quota behavior before enabling it only
            # inside this disposable fixture for a positive enforcement test.
            run('/var/vpopmail/bin/vsetuserquota', account, '65536S')
            assert run('/var/vpopmail/bin/vuserinfo', '-q', account) == '65536S'

            # Shipped Dovecot explicitly disables quota enforcement. Both LDA
            # variants must preserve that baseline, not invent enforcement.
            quota_config = Path('/etc/dovecot/conf.d/90-quota.conf')
            original_quota_config = quota_config.read_text()
            assert '  enforce = no\n' in original_quota_config
            run('doveadm', 'auth', 'cache', 'flush', account)
            run('doveadm', 'quota', 'recalc', '-u', account)
            for label, form, folder in (('LDA', proof.LDA, 'Junk'),
                                        ('LDA-no-Sieve', LDA_NO_SIEVE, 'INBOX')):
                proof.qmail(form)
                large = proof.payload(label + '-quota-not-enforced')
                large.set_content('Synthetic quota payload.\n' * 10000)
                proof.send(large)
                observations.append((large, [folder]))
                quiet(collector)
                print('PASS ' + label + ': shipped enforce=no preserves delivery to ' + folder, flush=True)

            try:
                quota_config.write_text(original_quota_config.replace('  enforce = no\n', '  enforce = yes\n'))
                run('doveadm', 'reload')
                deadline = time.monotonic() + 20
                while True:
                    refreshed = subprocess.run(['doveadm', 'auth', 'cache', 'flush', account],
                                               capture_output=True, timeout=5)
                    if refreshed.returncode == 0:
                        break
                    assert time.monotonic() < deadline, 'Dovecot auth did not return after reload'
                    time.sleep(0.2)
                run('doveadm', 'quota', 'recalc', '-u', account)
                print('FIXTURE quota state: ' + run('doveadm', 'quota', 'get', '-u', account), flush=True)
                for label, form in (('LDA', proof.LDA), ('LDA-no-Sieve', LDA_NO_SIEVE)):
                    proof.qmail(form)
                    rejected = proof.payload(label + '-quota-enforced')
                    rejected.set_content('Synthetic quota payload.\n' * 10000)
                    proof.send(rejected)
                    sender, recipients, raw = collector.messages.get(timeout=60)
                    assert recipients == ['<origin@outside.invalid>'], (sender, recipients)
                    assert str(rejected['Message-ID']).encode() in raw
                    assert b'quota' in raw.lower(), 'expected Dovecot quota DSN'
                    observations.append((rejected, []))
                    quiet(collector)
                    print('PASS ' + label + ': fixture enforce=yes gives one quota DSN, '
                          'zero copies', flush=True)
            finally:
                quota_config.write_text(original_quota_config)
                run('doveadm', 'reload')
            run('/var/vpopmail/bin/vsetuserquota', account, 'NOQUOTA')
            proof.qmail(LDA_NO_SIEVE)
            run('/bin/s6-svc', '-a', '/service/qmail-send')
            recovered = proof.payload('LDA-no-Sieve-quota-restored')
            proof.send(recovered)
            observations.append((recovered, ['INBOX']))
            quiet(collector)
            assert quota_config.read_text() == original_quota_config
            assert (home / '.sieve/dovecot.sieve').readlink() == Path('individual-modes.sieve')
            assert (home / '.sieve/individual-modes.sieve').read_text() == script
            print('PASS NOQUOTA control delivers once, earlier outcomes unchanged', flush=True)
        finally:
            collector.shutdown()
            worker.join(timeout=5)
    print('PASS native individual delivery modes', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='sqmail-aio:user-delivery-20260928')
    parser.add_argument('--database-image', default='mariadb:11.4')
    parser.add_argument('--probe', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.probe:
        probe()
        return 0
    from mail import MailEnvironment

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    environment = MailEnvironment(args.image, args.database_image)
    try:
        print(environment.docker('image', 'inspect', '--format', '{{.Id}}', args.image).stdout,
              end='', flush=True)
        print('Resources: ' + environment.prefix, flush=True)
        environment.prepare()
        result = subprocess.run(['docker', 'exec', environment.mail, 'python3', '-B',
                                 '/tests/individual-delivery-modes.py', '--probe'], timeout=600)
        if result.returncode:
            raise RuntimeError('Individual delivery modes proof failed')
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        environment.logs()
        return 1
    except KeyboardInterrupt:
        return 130
    finally:
        environment.cleanup()
        print('CLEANUP complete: ' + environment.prefix, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
