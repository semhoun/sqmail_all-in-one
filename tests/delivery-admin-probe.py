#!/usr/bin/env python3
"""Container-only tests of real delivery-admin, sudo, PHP and native Sieve.

Never import or replace helper internals. Fixture writes and fault injection are
allowed only after the disposable-container/run-marker guard. Secure cookies are
sent explicitly over loopback HTTP to model the trusted TLS proxy hop.
"""

import hashlib
import html
import email.policy
from email.parser import BytesParser
from html.parser import HTMLParser
import http.client
from http.cookies import SimpleCookie
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import stat
import sys
import threading
import time
import urllib.parse


HELPER = '/opt/libexec/delivery-admin'
MAILBOX = 'alice@examples.invalid'
BACKUPS = Path('/var/qmail/control/delivery-admin-backups')
AUTH = Path('/run/sqmail-admin')
PASSWORD = 'SyntheticDeliveryOnly927!'


def check(condition, label):
    if not condition:
        raise AssertionError(label)


def run(*args, data=None, success=True):
    result = subprocess.run(args, input=data, text=True, capture_output=True, timeout=65)
    if success:
        check(result.returncode == 0, 'native command failed: ' + Path(args[0]).name)
    return result


def passed(label):
    print('PASS: ' + label, flush=True)


def backup_digest():
    check(Path('/.dockerenv').exists() and os.geteuid() == 0, 'container root guard')
    check(os.environ.get('SQMAIL_DISPOSABLE_TEST') == '1'
          and bool(os.environ.get('SQMAIL_MAIL_TEST_RUN')), 'disposable backup readback guard')
    marker = Path('/tmp/sqmail-mail-test-run')
    if marker.exists():
        check(marker.read_text().strip() == os.environ['SQMAIL_MAIL_TEST_RUN'], 'backup run marker')
    else:
        check(os.statvfs(BACKUPS).f_flag & os.ST_RDONLY, 'fresh reader requires read-only volume')
    records = []
    for path in [BACKUPS, *sorted(BACKUPS.rglob('*'))]:
        info = path.lstat()
        check(info.st_uid == 0 and not info.st_mode & 0o077, 'backup record root/private')
        check(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode), 'backup record regular/directory')
        records.append((str(path.relative_to(BACKUPS)), info.st_mode, info.st_uid, info.st_gid,
                        hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None))
    check(len(records) > 1, 'persistent backup records exist')
    print(hashlib.sha256(json.dumps(records).encode()).hexdigest())


class Inputs(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.values = {}
        self.feed(body)

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == 'input' and 'name' in attributes:
            self.values[attributes['name']] = attributes.get('value', '')


def request(path, jar=None, fields=None, headers=None):
    connection = http.client.HTTPConnection('127.0.0.1', 88, timeout=65)
    headers = dict(headers or {})
    if jar:
        headers['Cookie'] = '; '.join(f'{key}={value}' for key, value in jar.items())
    body = None
    if fields is not None:
        body = urllib.parse.urlencode(fields)
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    try:
        connection.request('POST' if fields is not None else 'GET', path, body, headers)
        response = connection.getresponse()
        status, response_headers = response.status, response.getheaders()
        body = response.read().decode('utf-8', errors='replace')
        for name, value in response_headers:
            if name.lower() == 'set-cookie' and jar is not None:
                for key, morsel in SimpleCookie(value).items():
                    check(bool(morsel['secure'] and morsel['httponly']), 'secure HTTP cookie attributes')
                    jar[key] = morsel.value
        return status, {key.lower(): value for key, value in response_headers}, body
    finally:
        connection.close()


def login(user):
    jar = {}
    status, _, body = request('/login.php', jar)
    check(status == 200, 'login form available')
    csrf = Inputs(body).values.get('csrf')
    check(bool(csrf), 'login CSRF present')
    status, _, _ = request('/login.php', jar, {'csrf': csrf, 'username': user, 'password': PASSWORD})
    check(status == 303 and bool(jar.get('__Host-sqmail-admin')), 'real login succeeds')
    return jar


class API:
    def __init__(self, token):
        self.token = token

    def raw(self, payload, arguments=()):
        result = run('runuser', '-u', 'www-data', '--', 'sudo', '-n', HELPER,
                     *arguments, data=payload, success=False)
        check(self.token not in result.stdout + result.stderr, 'helper does not disclose bearer token')
        return result

    def call(self, operation, expected=True, **fields):
        payload = {'operation': operation, 'token': self.token, **fields}
        result = self.raw(json.dumps(payload))
        audits = []
        for line in result.stderr.splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict) and 'actor' in entry:
                audits.append(entry)
        self.audit = audits[-1] if audits else None
        try:
            response = json.loads(result.stdout)
        except (ValueError, TypeError):
            raise AssertionError('helper returned invalid JSON for ' + operation) from None
        if response.get('ok') is not expected:
            code = response.get('error', {}).get('code', 'unexpected_success')
            safe_code = code if isinstance(code, str) and code.replace('_', '').isalnum() else 'invalid_error'
            if expected and operation == 'inspect' and safe_code == 'native_failed':
                message = str(response['error'].get('message', ''))[:1024]
                for secret in (self.token, PASSWORD, 'SyntheticDbOnly927', 'SyntheticMailOnly927'):
                    message = message.replace(secret, '[redacted]')
                print('INSPECT DIAGNOSTIC: ' + json.dumps(message), flush=True)
            raise AssertionError(operation + ' unexpected result: ' + safe_code)
        if expected:
            check(result.returncode == 0 and 'data' in response, operation + ' success envelope')
            return response['data']
        error = response.get('error', {})
        check(isinstance(error.get('code'), str) and isinstance(error.get('message'), str),
              operation + ' bounded error envelope')
        return error

    def inspect(self, script='', **fields):
        return self.call('inspect', mailbox=MAILBOX, script=script, **fields)

    def mutate(self, operation, script='', expected=True, state=None, **fields):
        if operation in ('qmail_restore', 'sieve_restore') and 'backup_version' not in fields:
            preview = self.call(operation + '_preview', mailbox=MAILBOX, script=script)
            fields['backup_version'] = preview['backup_version']
            state = preview['state'] if state is None else state
        state = self.inspect(script) if state is None else state
        return self.call(operation, expected=expected, mailbox=MAILBOX, script=script,
                         version=state['version'], **fields)


def native_sieve(action, script=None, content=None):
    args = ['setpriv', '--reuid=89', '--regid=89', '--clear-groups', '--',
            'doveadm', '-f', 'json', 'sieve', action, '-u', MAILBOX]
    if script is not None:
        args += ['--', script]
    return run(*args, data=content).stdout


def vacation_delivery(api, home):
    spec = importlib.util.spec_from_file_location('mail_probe', Path(__file__).with_name('mail-probe.py'))
    mail = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mail)
    script = 'delivery-vacation'
    content = ('require ["vacation"];\n'
               'vacation :days 1 :addresses ["alice@examples.invalid"] '
               ':subject "Synthetic vacation response" "Synthetic absence notice.";\nkeep;\n')
    api.mutate('qmail_save', mode='local', destinations=[])
    api.mutate('sieve_save', script, content=content, confirm_active=False)
    api.mutate('sieve_activate', script)

    def settled(stage):
        deadline, stable = time.monotonic() + 60, None
        while time.monotonic() < deadline:
            output = run('/var/qmail/bin/qmail-qstat').stdout.splitlines()
            if output and all(line.rsplit(':', 1)[-1].strip() == '0' for line in output):
                stable = stable or time.monotonic()
                if time.monotonic() - stable >= 3:
                    return
            else:
                stable = None
            time.sleep(.2)
        raise AssertionError('vacation mail queue did not drain: ' + stage)

    def original_retained(message):
        found = []
        for path in (home / 'Maildir').rglob('*'):
            if path.is_file() and path.parent.name in ('new', 'cur'):
                parsed = BytesParser(policy=email.policy.default).parsebytes(path.read_bytes())
                if parsed.get('Message-ID') == message['Message-ID']:
                    found.append(parsed)
        check(len(found) == 1, 'vacation keeps original exactly once')
        mail.verify_content(found[0], message)

    collector = mail.Collector()
    thread = threading.Thread(target=collector.serve_forever, daemon=True)
    thread.start()
    try:
        sender = 'vacation-sender@destination.invalid'
        first = mail.message('vacation-first', recipient=MAILBOX, sender=sender)
        mail.send(first)
        settled('first message')
        original_retained(first)
        check(collector.messages.qsize() == 1, 'first eligible mail produces one vacation response')
        envelope, recipients, wire = collector.messages.get_nowait()
        reply = BytesParser(policy=email.policy.default).parsebytes(wire)
        # The production sendmail integration currently emits the mailbox sender,
        # not <>. Loop prevention is checked through the actual Auto-Submitted
        # marker and suppressed automatic/null-sender inputs, not assumed here.
        check(envelope in ('<>', '<' + MAILBOX + '>') and recipients == ['<' + sender + '>'],
              'vacation return envelope addresses')
        auto_submitted = str(reply.get('Auto-Submitted', '')).lower()
        check(auto_submitted in ('auto-replied', 'auto-replied (vacation)'), 'vacation response loop marker')
        check('Synthetic absence notice.' in reply.get_body(preferencelist=('plain',)).get_content(),
              'helper-installed vacation content executed')
        second = mail.message('vacation-repeat', recipient=MAILBOX, sender=sender)
        automatic = mail.message('vacation-auto-generated', recipient=MAILBOX,
                                 sender='automation@destination.invalid')
        automatic['Auto-Submitted'] = 'auto-generated'
        auto_reply = mail.message('vacation-auto-replied', recipient=MAILBOX,
                                  sender='other-vacation@destination.invalid')
        auto_reply['Auto-Submitted'] = 'auto-replied'
        bounce = mail.message('vacation-null-sender', recipient=MAILBOX,
                              sender='mailer-daemon@destination.invalid')
        for message in (second, automatic, auto_reply):
            mail.send(message)
        with mail.smtp() as client:
            check(not client.sendmail('', [MAILBOX], bounce.as_bytes(policy=email.policy.SMTP)),
                  'null-sender original accepted')
        settled('suppression messages')
        for message in (second, automatic, auto_reply, bounce):
            original_retained(message)
        check(collector.messages.empty(), 'no repeated, automatic, autoreply-loop or bounce vacation response')
        passed('real SMTP vacation reply, repeat/Auto-Submitted/null-sender suppression and original retention')
    finally:
        collector.shutdown()
        collector.server_close()
        thread.join(timeout=5)
        api.mutate('sieve_deactivate', script)


def main():
    check(Path('/.dockerenv').exists() and os.geteuid() == 0, 'container root guard')
    check(os.environ.get('SQMAIL_DISPOSABLE_TEST') == '1', 'disposable environment guard')
    marker = Path('/tmp/sqmail-mail-test-run')
    check(not marker.is_symlink() and marker.read_text().strip() == os.environ['SQMAIL_MAIL_TEST_RUN'],
          'disposable run marker')
    check(Path(HELPER).is_file(), 'image contains delivery helper; build current source first')
    run('/opt/libexec/delivery-admin-init')
    credentials = Path('/var/qmail/control/lighttpd-admins.htdigest')

    def record(user):
        digest = hashlib.sha256(f'{user}:SQMail AIO Admin:{PASSWORD}'.encode()).hexdigest()
        return f'{user}:SQMail AIO Admin:{digest}\n'

    records = record('admin') + record('operator')
    credentials.write_text(records)
    credentials.chmod(0o644)
    # Start supervised production services if the fixture did not start them.
    for service in ('php-fpm', 'lighttpd'):
        directory = Path('/service') / service
        if directory.exists():
            run('s6-svc', '-u', str(directory))
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            if request('/login.php')[0] == 200:
                break
        except OSError:
            pass
        time.sleep(.2)
    else:
        raise AssertionError('production PHP/lighttpd did not become ready')

    jar = login('admin')
    api = API(jar['__Host-sqmail-admin'])
    operator = API(login('operator')['__Host-sqmail-admin'])
    check(operator.inspect(actor='admin')['mailbox'] == MAILBOX, 'operator can inspect all mailboxes')
    check(operator.audit and operator.audit['actor'] == 'operator', 'actor derived from operator token')
    state = api.inspect(actor='operator')
    check(api.audit and api.audit['actor'] == 'admin', 'actor derived from admin token')
    home = Path(run('/var/vpopmail/bin/vuserinfo', '-d', MAILBOX).stdout.strip())
    check(state['home'] == str(home), 'native home resolution')
    qmail = home / '.qmail'
    check(not qmail.exists(), 'fresh mailbox inherits delivery')
    check(state['qmail']['content'] is None and state['qmail']['editable'], 'absent qmail editable')
    if sys.argv[1:] == ['--vacation-only']:
        vacation_delivery(api, home)
        return
    run('/var/vpopmail/bin/vaddaliasdomain', 'examples.invalid', 'alias.examples.invalid')
    alias = api.call('inspect', mailbox='alice@alias.examples.invalid', script='')
    check(alias['mailbox'] == MAILBOX and alias['home'] == str(home), 'alias canonicalization')
    run('/var/vpopmail/bin/vmoduser', '-p', '-s', '-w', '-i', MAILBOX)
    check(api.inspect()['mailbox'] == MAILBOX, 'disabled account remains administrable')
    for operation, fields, item in [('domains', {}, 'examples.invalid'),
                                    ('mailboxes', {'domain': 'examples.invalid'}, MAILBOX)]:
        result = api.call(operation, query='', page=0, **fields)
        check(item in result['items'] and 'next_page' in result, 'bounded native enumeration')
    passed('admin/operator sessions, canonical alias, disabled mailbox and enumeration')

    for token in ('', '../lighttpd-admins.htdigest', '/etc/passwd', 'not-a-token'):
        api.call('inspect', expected=False, token=token, mailbox=MAILBOX, script='')
    forged = api.token[:-1] + ('0' if api.token[-1] != '0' else '1')
    api.call('inspect', expected=False, token=forged, mailbox=MAILBOX, script='')
    expired = login('operator')['__Host-sqmail-admin']
    tokenfile = AUTH / ('token-' + expired)
    lines = tokenfile.read_text().splitlines()
    lines[1] = str(int(time.time()) - 1)
    tokenfile.write_text('\n'.join(lines) + '\n')
    API(expired).call('domains', expected=False, query='', page=0)
    revoked = login('operator')['__Host-sqmail-admin']
    credentials.write_text(record('admin'))
    API(revoked).call('domains', expected=False, query='', page=0)
    credentials.write_text(record('admin') + record('operator').replace(
        record('operator').split(':')[-1].strip(), '0' * 64))
    API(revoked).call('domains', expected=False, query='', page=0)
    credentials.write_text(records)
    (AUTH / ('token-' + revoked)).unlink()
    API(revoked).call('domains', expected=False, query='', page=0)
    for payload in ('{', '[]', json.dumps({'operation': 'domains', 'token': api.token,
                                         'padding': 'x' * 1048576})):
        result = api.raw(payload)
        check(len(result.stdout) < 65536, 'bounded malformed-request response')
        check(json.loads(result.stdout).get('ok') is False, 'malformed/oversized request refused')
    api.call('not_an_operation', expected=False)
    for operation in ('domain_inspect', 'domain_preview', 'domain_save',
                      'domain_restore_preview', 'domain_restore'):
        rejected = api.call(operation, expected=False, domain='examples.invalid', mode='delete')
        check(rejected['code'] == 'invalid_request', 'domain capability removed, not merely disabled')
    for mailbox in ('../alice', '-A', '*', '?@examples.invalid', 'alice@examples.invalid\n-A'):
        api.call('inspect', expected=False, mailbox=mailbox, script='')
    for script in ('../outside', '/tmp/outside', '-A', '*', 'bad\nname'):
        api.mutate('sieve_save', script=script, state=state, content='keep;\n', expected=False)
    for destinations in (['*'], ['-A'], ['a@b.invalid\n|id'], [MAILBOX],
                         ['bob@examples.invalid'] * 2, ['x@destination.invalid'] * 101):
        api.call('qmail_preview', expected=False, mailbox=MAILBOX, script='',
                 mode='forward', destinations=destinations)
    check(not qmail.exists(), 'hostile requests preserve qmail')
    passed('expired/revoked/path tokens, request bounds and unsafe inputs')

    def save(mode, destinations=(), **fields):
        return api.mutate('qmail_save', mode=mode, destinations=list(destinations), **fields)

    stale = api.inspect()
    preview = api.call('qmail_preview', mailbox=MAILBOX, script='', mode='local', destinations=[])
    check(bool(preview['diff']) and not qmail.exists(), 'preview diff without mutation')
    local = save('local')
    local_content = qmail.read_text()
    check(local['qmail']['mode'] == 'local' and 'preline' in local_content, 'local save')
    check(qmail.stat().st_uid == 89 and qmail.stat().st_gid == 89, 'qmail uid/gid preserved')
    check(save('inherit', state=stale, expected=False)['code'] == 'conflict', 'stale qmail conflict code')
    check(qmail.read_text() == local_content, 'stale version preserves qmail')
    restored = api.mutate('qmail_restore')
    check(restored['qmail']['content'] is None and not qmail.exists(), 'restore prior absence')
    no_sieve = '|/var/qmail/bin/preline -f /usr/libexec/dovecot/deliver -o mail_plugins/sieve=no -d $EXT@$USER\n'
    save('local_no_sieve')
    check(qmail.read_text() == no_sieve, 'fixed no-Sieve LDA keeps absolute paths and other Dovecot checks')
    save('copy_no_sieve', ['bob@examples.invalid'])
    check(api.inspect()['qmail']['mode'] == 'copy_no_sieve', 'no-Sieve local copy recognized')
    before_discard = qmail.read_bytes()
    before_backups = {p.name: p.read_bytes() for p in BACKUPS.iterdir() if p.is_file()}
    check(save('discard', expected=False)['code'] == 'confirmation', 'discard needs explicit acknowledgment')
    check(qmail.read_bytes() == before_discard, 'unconfirmed discard preserves delivery')
    check(before_backups == {p.name: p.read_bytes() for p in BACKUPS.iterdir() if p.is_file()},
          'unconfirmed discard preserves backups')
    save('discard', confirm_discard=True)
    check(qmail.read_text() == '# SQMail AIO: discard messages for this mailbox\n', 'explicit discard marker')
    save('local_no_sieve')
    check(api.mutate('qmail_restore', expected=False)['code'] == 'confirmation', 'discard restore needs acknowledgment')
    check(qmail.read_text() == no_sieve, 'unconfirmed discard restore preserves delivery')
    api.mutate('qmail_restore', confirm_discard=True)
    check(api.inspect()['qmail']['mode'] == 'discard', 'acknowledged discard restored')
    api.mutate('qmail_restore')
    check(qmail.read_text() == no_sieve, 'leaving discard removes its marker')
    passed('user-only no-Sieve/copy/discard modes with separate save/restore acknowledgment')
    save('local')
    save('copy', ['bob@examples.invalid'])
    check(api.inspect()['qmail']['mode'] == 'copy', 'copy mode recognized')
    copy_content = qmail.read_text()
    save('forward', ['bob@examples.invalid'])
    restore_preview = api.call('qmail_restore_preview', mailbox=MAILBOX, script='')
    check(bool(restore_preview['diff']), 'last snapshot restore diff')
    # Reinitialization must preserve persistent last-snapshot files, not reset them.
    snapshots = {str(p.relative_to(BACKUPS)): p.read_bytes() for p in BACKUPS.rglob('*') if p.is_file()}
    check(bool(snapshots), 'persistent snapshot created')
    check(BACKUPS.stat().st_uid == 0 and BACKUPS.stat().st_mode & 0o777 == 0o700,
          'persistent backups root-owned and private')
    check(run('runuser', '-u', 'www-data', '--', 'test', '-r', str(BACKUPS),
              success=False).returncode != 0, 'web identity cannot read backup directory')
    run('/opt/libexec/delivery-admin-init')
    check(snapshots == {str(p.relative_to(BACKUPS)): p.read_bytes()
                        for p in BACKUPS.rglob('*') if p.is_file()}, 'init preserves snapshots')
    api.mutate('qmail_restore')
    check(qmail.read_text() == copy_content, 'restore last snapshot, not original snapshot')
    run('/var/vpopmail/bin/valias', '-i', 'bob@examples.invalid', MAILBOX)
    state = api.inspect()
    check(bool(state['valias']['lines']), 'native valias warning present')
    save('local', state=state, expected=False)
    save('local', state=state, confirm_valias=True, valias_fingerprint='stale', expected=False)
    run('/var/vpopmail/bin/valias', '-i', 'postmaster@examples.invalid', MAILBOX)
    current = api.inspect()
    save('local', state=current, confirm_valias=True,
         valias_fingerprint=state['valias']['fingerprint'], expected=False)
    state = current
    save('local', state=state, confirm_valias=True, valias_fingerprint=state['valias']['fingerprint'])
    check(api.inspect()['valias'] == state['valias'], 'helper never changes valias')
    run('/var/vpopmail/bin/valias', '-d', MAILBOX)
    passed('qmail preview/local/copy/forward, stale revision, valias confirmation and persistent restoration')

    for content in ('', '# comment only\n', '|/bin/echo preline\n', '|/bin/false\n'):
        qmail.write_text(content)
        state = api.inspect()
        check(not state['qmail']['editable'], 'unknown/empty/comment-only qmail read-only')
        save('inherit', state=state, expected=False)
        check(qmail.read_text() == content, 'refused qmail preserved')
    qmail.write_text('# preserved comment\n' + local_content)
    state = api.inspect()
    check(state['qmail']['editable'], 'known delivery with comments editable')
    save('local', state=state)
    check('# preserved comment' in qmail.read_text(), 'unchanged delivery preserves comment')
    qmail.unlink()
    target = home / 'delivery-link-target'
    target.write_text(local_content)
    os.chown(target, 89, 89)
    for kind in ('symlink', 'hardlink'):
        if kind == 'symlink':
            qmail.symlink_to(target)
        else:
            os.link(target, qmail)
        state = api.inspect()
        check(not state['qmail']['editable'], kind + ' qmail read-only')
        save('inherit', state=state, expected=False)
        check(target.read_text() == local_content, kind + ' target preserved')
        qmail.unlink()
    target.unlink()
    save('local')
    state = api.inspect()
    holding = BACKUPS.with_name(BACKUPS.name + '-test-hold')
    BACKUPS.rename(holding)
    BACKUPS.write_text('synthetic backup failure\n')
    try:
        save('inherit', state=state, expected=False)
        check(qmail.read_text() == local_content, 'backup failure preserves qmail')
    finally:
        BACKUPS.unlink()
        holding.rename(BACKUPS)
    passed('unknown content, empty/comments, symlink/hardlink refusal and backup failure preservation')

    script = 'delivery-integration'
    first = '# <script>delivery-test</script>\nkeep;\n'
    second = '# second version\nkeep;\n'
    state = api.inspect(script)
    if not state['sieve']['available']:
        reason = str(state['sieve'].get('reason', ''))[:1024].replace(api.token, '[redacted]')
        print('SIEVE DIAGNOSTIC: ' + json.dumps(reason), flush=True)
        native_user = run('setpriv', '--reuid=89', '--regid=89', '--clear-groups', '--',
                          'doveadm', '-f', 'json', 'user', MAILBOX)
        document = json.loads(native_user.stdout)
        shape = [sorted(row) for row in document] if isinstance(document, list) else type(document).__name__
        print('USERDB JSON KEY SHAPE: ' + json.dumps(shape), flush=True)
        for option in ('-n', '-h'):
            scoped = run('setpriv', '--reuid=89', '--regid=89', '--clear-groups', '--',
                         'doveconf', option, 'sieve_script', success=False)
            print('SCOPED SIEVE CONFIG ' + option + ': ' + json.dumps({
                'exit': scoped.returncode, 'stdout': scoped.stdout[:4096], 'stderr': scoped.stderr[:1024]}),
                  flush=True)
    check(state['sieve']['available'], 'native Sieve available')
    api.mutate('sieve_save', script, content=first, confirm_active=False)
    check(api.inspect(script)['sieve']['selected']['content'] == first, 'Sieve save/read')
    api.mutate('sieve_save', script, content='not valid sieve;\n', confirm_active=False, expected=False)
    check(api.inspect(script)['sieve']['selected']['content'] == first, 'invalid Sieve preserves content')
    api.mutate('sieve_activate', script)
    check(api.inspect(script)['sieve']['selected']['active'], 'Sieve activated')
    api.mutate('sieve_save', script, content=second, confirm_active=False, expected=False)
    api.mutate('sieve_delete', script, expected=False)
    check(api.inspect(script)['sieve']['selected']['content'] == first, 'active edit/delete protection')
    api.mutate('sieve_save', script, content=second, confirm_active=True)
    restore = api.call('sieve_restore_preview', mailbox=MAILBOX, script=script)
    check(restore['content'] == first and restore['previous_active'], 'Sieve snapshot content and active state')
    api.mutate('sieve_restore', script, confirm_active=False, expected=False)
    api.mutate('sieve_restore', script, confirm_active=True)
    check(api.inspect(script)['sieve']['selected']['content'] == first, 'Sieve restore content')
    stale = api.inspect(script)
    # An independent native writer simulates a ManageSieve client between inspect
    # and POST. This proves observable stale detection, not cross-process CAS.
    native_sieve('put', script, second)
    conflict = api.mutate('sieve_save', script, state=stale, content=first,
                          confirm_active=True, expected=False)
    check(conflict['code'] == 'conflict', 'native external edit returns conflict')
    check(api.inspect(script)['sieve']['selected']['content'] == second, 'native external edit preserved')
    api.mutate('sieve_deactivate', script)
    check(not api.inspect(script)['sieve']['selected']['active'], 'Sieve deactivated')
    check(any(row['script'] == 'default' and row['active'] == 'ACTIVE'
              for row in json.loads(native_sieve('list'))), 'native global fallback active')
    api.mutate('sieve_delete', script)
    check(not api.inspect(script)['sieve']['selected']['exists'], 'inactive script deleted')
    api.mutate('sieve_restore', script, confirm_active=False)
    restored = api.inspect(script)['sieve']['selected']
    check(restored['content'] == second and not restored['active'], 'restoration does not silently activate')
    api.mutate('sieve_save', script, content=first, confirm_active=False)
    preview = api.call('sieve_restore_preview', mailbox=MAILBOX, script=script)
    check(preview['content'] == second, 'restore race preview contains preceding content')
    api.mutate('sieve_save', script, content='not valid sieve;\n', confirm_active=False, expected=False)
    check(api.inspect(script)['version'] == preview['state']['version'],
          'failed compile does not change live revision')
    error = api.mutate('sieve_restore', script, state=preview['state'],
                       backup_version=preview['backup_version'], confirm_active=False, expected=False)
    check(error['code'] == 'conflict', 'changed backup rejects old restore preview')
    check(api.inspect(script)['sieve']['selected']['content'] == first,
          'stale backup preview does not overwrite live script')
    passed('native Sieve compile/lifecycle, active confirmation, fallback, restore and external-edit conflict')

    path = '/delivery/?' + urllib.parse.urlencode({'mailbox': MAILBOX, 'script': script})
    status, headers, body = request(path, jar)
    check(status == 200, 'ordinary PHP delivery page')
    check('no-store' in headers.get('cache-control', '') and 'content-security-policy' in headers,
          'delivery security response headers')
    before = api.inspect(script)['version']
    fields = {'operation': 'qmail_save', 'action': 'qmail_save', 'mailbox': MAILBOX,
              'script': script, 'mode': 'inherit', 'version': before}
    request('/delivery/?' + urllib.parse.urlencode(fields), jar)
    check(api.inspect(script)['version'] == before, 'GET cannot mutate')
    status, _, _ = request('/delivery/', jar, fields)
    check(status == 403, 'missing CSRF rejected')
    status, _, _ = request('/delivery/', jar, {**fields, 'csrf': 'invalid'})
    check(status == 403 and api.inspect(script)['version'] == before, 'invalid CSRF preserves state')
    api.mutate('sieve_save', script, content=first, confirm_active=False)
    status, _, body = request(path, jar)
    check(status == 200 and '<script>delivery-test</script>' not in body
          and html.escape('<script>delivery-test</script>') in body, 'script markup escaped')
    csrf = Inputs(body).values.get('csrf')
    check(bool(csrf), 'ordinary PHP CSRF form token')
    invalid = '# <script>delivery-error</script>\nnot valid sieve;\n'
    state = api.inspect(script)
    status, _, body = request('/delivery/', jar, {
        'operation': 'sieve_save', 'mailbox': MAILBOX, 'script': script,
        'version': state['version'], 'content': invalid, 'csrf': csrf})
    check(status in (200, 400, 422), 'compiler failure rendered by ordinary PHP')
    check('<script>delivery-error</script>' not in body
          and html.escape('<script>delivery-error</script>') in body,
          'invalid source retained and escaped in error page')
    check(api.inspect(script)['sieve']['selected']['content'] == first, 'HTTP compiler failure preserves script')
    for spoof in ({}, {'Remote-User': 'admin', 'X-Remote-User': 'admin', 'Auth-Type': 'Session'}):
        check(request(path, headers=spoof)[0] == 303, 'anonymous/spoofed HTTP identity denied')
    passed('ordinary PHP GET/CSRF protection, escaped script source, headers and anonymous denial')
    qmail.chmod(0o644)
    save('inherit')
    check(not qmail.exists(), 'explicit inheritance removes known qmail')
    api.mutate('qmail_restore')
    check(qmail.stat().st_mode & 0o777 == 0o644, 'qmail restore preserves archived mode')
    global_before = Path('/etc/dovecot/sieve/default.sieve').read_bytes()
    api.mutate('sieve_save', 'default', content='keep;\n', confirm_active=False, expected=False)
    check(Path('/etc/dovecot/sieve/default.sieve').read_bytes() == global_before,
          'reserved default save leaves global script untouched')
    check(not api.inspect('default')['sieve']['selected']['exists'], 'reserved default not created')
    vacation_delivery(api, home)
    # A denied sudo command sends an administrator notification with the shipped
    # sudo policy. Run it after SMTP assertions so fixture root-address routing
    # cannot contaminate the vacation queue-drain check; do not change that policy.
    check(api.raw('{}', ('--help',)).returncode != 0, 'sudo restricts helper to no arguments')
    passed('sudo restricts helper to no arguments')


if __name__ == '__main__':
    try:
        if sys.argv[1:] == ['--backup-digest']:
            backup_digest()
        else:
            check(sys.argv[1:] in ([], ['--vacation-only']), 'unsupported probe arguments')
            main()
    except Exception as error:
        # No traceback locals, bearer tokens, subprocess stdout, or response bodies.
        print('FAIL: ' + (str(error) if isinstance(error, AssertionError) else type(error).__name__),
              file=sys.stderr, flush=True)
        sys.exit(1)
