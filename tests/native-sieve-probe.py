#!/usr/bin/env python3
"""Container-only native Sieve/canonical-account contract probe."""

import os
from pathlib import Path
import subprocess
import hashlib
import json
import tempfile
import stat


def run(*args, data=None, user=None, expected=0, show=True):
    command = list(args)
    if user == 'vpopmail':
        command = ['setpriv', '--reuid=89', '--regid=89', '--clear-groups', '--', *command]
    elif user:
        command = ['runuser', '-u', user, '--', *command]
    result = subprocess.run(command, input=data, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=20)
    print(f'$ {" ".join(command)} [exit {result.returncode}]', flush=True)
    if show:
        print(result.stdout, flush=True)
    if expected is not None:
        assert result.returncode == expected, f'Unexpected exit for {args[0]}'
    return result


def snapshot(home):
    # Compilation uses tmp/: its directory mtime is not a durable script mutation.
    directory = Path(home) / '.sieve'
    return {str(path.relative_to(directory)): (
        path.lstat().st_mode, path.lstat().st_uid, path.lstat().st_gid,
        None if path.is_dir() else path.lstat().st_mtime_ns,
        os.readlink(path) if path.is_symlink() else
        hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None)
        for path in directory.rglob('*')}


def main():
    assert Path('/.dockerenv').exists() and os.geteuid() == 0
    assert os.environ.get('SQMAIL_DISPOSABLE_TEST') == '1'
    assert Path('/tmp/sqmail-mail-test-run').read_text().strip() == os.environ['SQMAIL_MAIL_TEST_RUN']
    assert run('dovecot', '--version').stdout.startswith('2.4.5 ')
    assert run('id', '-G', user='vpopmail').stdout.strip() == '89'
    vp = '/var/vpopmail/bin/'
    mailbox = 'alice@examples.invalid'
    alias = 'alice@alias.examples.invalid'
    run(vp + 'vaddaliasdomain', 'examples.invalid', 'alias.examples.invalid')
    for address in (mailbox, alias):
        assert run(vp + 'vuserinfo', '-n', address).stdout.strip() == 'alice'
        assert run(vp + 'vdominfo', '-r', address.split('@')[1]).stdout.splitlines()[0] == 'examples.invalid'
    home = run(vp + 'vuserinfo', '-d', mailbox).stdout.strip()
    assert Path(home).is_dir()
    assert run(vp + 'vuserinfo', '-d', alias).stdout.strip() == home
    assert run('doveadm', 'user', '-f', 'home', mailbox).stdout.strip() == home
    run('doveadm', 'user', '-f', 'home', alias, expected=67)
    run(vp + 'vuserinfo', '-d', 'missing@examples.invalid', expected=255)
    run(vp + 'vuserinfo', '-d', 'team@examples.invalid', expected=255)
    # Only selected non-secret fields are requested; never vuserinfo's default.
    domains = run(vp + 'vdominfo', '-n').stdout.splitlines()
    assert 'examples.invalid' in domains and 'alias.examples.invalid (alias of examples.invalid)' in domains
    names = run(vp + 'vuserinfo', '-n', '-D', 'examples.invalid', show=False)
    assert names.returncode == 0
    assert set(names.stdout.splitlines()) == {'-' * 42, 'alice', 'bob', 'postmaster'}
    print('ENUMERATION: ' + names.stdout, flush=True)
    print('PASS: native domain/account enumeration contains synthetic accounts', flush=True)
    for tool in ('vuserinfo', 'vdominfo'):
        usage = run(vp + tool, '-h', expected=255).stdout
        assert 'offset' not in usage and 'limit' not in usage
    print('LIMITATION: native CLIs enumerate full sets; pagination requires a bounded snapshot in caller', flush=True)
    enumeration = run('doveadm', 'user', '*', show=False)
    assert set(enumeration.stdout.splitlines()) == {
        'alice@examples.invalid', 'bob@examples.invalid', 'postmaster@examples.invalid'}
    for command in ((vp + 'vuserinfo', '-d', alias), (vp + 'vdominfo', '-r', 'alias.examples.invalid'),
                    (vp + 'vuserinfo', '-n', '-D', 'examples.invalid'),
                    (vp + 'valias', 'team@examples.invalid')):
        run(*command, user='vpopmail')
    run(vp + 'vmoduser', '-p', '-s', '-w', '-i', mailbox)
    assert run(vp + 'vuserinfo', '-d', alias).stdout.strip() == home
    assert run(vp + 'vuserinfo', '-g', alias).stdout.strip() == '2062'
    assert run('doveadm', 'user', '-f', 'home', mailbox).stdout.strip() == home

    def sieve(action, *args, data=None, user='vpopmail', expected=0, address=mailbox):
        return run('doveadm', 'sieve', action, '-u', address, *args,
                   data=data, user=user, expected=expected)

    for identity in (None, 'vpopmail'):
        assert 'default ACTIVE' in sieve('list', user=identity).stdout
    sieve('list', user='www-data', expected=75)
    # Show only relevant effective settings, never full auth/SQL configuration.
    for setting in ('auth_username_format', 'mail_uid', 'mail_gid', 'sieve_max_script_size'):
        run('doveconf', '-h', setting)
    for filename in ('/var/run/dovecot/auth-userdb', '/etc/dovecot/dovecot.conf'):
        info = Path(filename).stat()
        print(f'PERMISSIONS {filename}: {info.st_uid}:{info.st_gid} {oct(info.st_mode & 0o777)}')
    settings = {
        'sieve_script/personal/driver': 'file',
        'sieve_script/personal/path': '~/.sieve',
        'sieve_script/personal/active_path': '~/.sieve/dovecot.sieve',
        'sieve_script/default/type': 'default',
        'sieve_script/default/driver': 'file',
        'sieve_script/default/path': '/etc/dovecot/sieve/default.sieve',
        'sieve_script/default/name': 'default',
        'sieve_vacation_min_period': '1 days',
        'sieve_vacation_max_period': '60 days',
        'sieve_vacation_default_period': '1 weeks',
    }
    for setting, value in settings.items():
        assert run('doveconf', '-h', setting, user='vpopmail').stdout.strip() == value
    for days in (1, 30):
        sieve('put', 'vacation-boundary', data=f'require ["vacation"];\nvacation :days {days} "Synthetic vacation";\n')
        sieve('delete', 'vacation-boundary')
    # A supported query must observe overrides, not silently report built-in paths.
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf') as custom:
        custom.write('dovecot_config_version = 2.4.1\n!include /etc/dovecot/dovecot.conf\n'
                     'sieve_script personal {\n path = ~/custom-sieve\n'
                     ' active_path = ~/custom-active.sieve\n}\n'
                     'sieve_script default {\n path = /tmp/custom-global.sieve\n name = custom-global\n}\n')
        custom.flush()
        os.chmod(custom.name, 0o644)
        for setting, value in {
            'sieve_script/personal/path': '~/custom-sieve',
            'sieve_script/personal/active_path': '~/custom-active.sieve',
            'sieve_script/default/path': '/tmp/custom-global.sieve',
            'sieve_script/default/name': 'custom-global',
        }.items():
            assert run('doveconf', '-c', custom.name, '-h', setting, user='vpopmail').stdout.strip() == value
    script = 'require ["fileinto", "mailbox"];\nfileinto :create "Junk";\n'
    sieve('put', 'native-contract', data=script)
    def get_script(name):
        result = run('doveadm', '-f', 'json', 'sieve', 'get', '-u', mailbox, '--', name, user='vpopmail')
        document = json.loads(result.stdout)
        assert len(document) == 1
        assert len(document[0]) == 1
        return next(iter(document[0].values()))

    assert get_script('native-contract') == script
    listing = run('doveadm', '-f', 'json', 'sieve', 'list', '-u', mailbox, user='vpopmail')
    assert {'script': 'native-contract', 'active': ''} in json.loads(listing.stdout)
    for name in ('script with spaces', '-leading-option'):
        sieve('put', '--', name, data='keep;\n')
        assert get_script(name) == 'keep;\n'
        sieve('delete', '--', name)
    assert 'native-contract ACTIVE' not in sieve('list').stdout
    sieve('activate', 'native-contract')
    assert 'native-contract ACTIVE' in sieve('list').stdout
    before = snapshot(home)
    sieve('put', 'native-contract', data='this is invalid sieve;\n', expected=65)
    assert snapshot(home) == before, 'Invalid put changed existing script storage'
    assert get_script('native-contract') == script
    sieve('put', 'invalid-new', data='this is invalid sieve;\n', expected=65)
    assert snapshot(home) == before
    sieve('delete', 'native-contract', expected=65)
    assert snapshot(home) == before
    print('PASS: invalid create/update and active-script delete preserve storage', flush=True)

    deliver = Path('/usr/libexec/dovecot/deliver')
    lda = Path('/usr/libexec/dovecot/dovecot-lda')
    assert deliver.resolve() == lda.resolve()
    maildir = Path(home) / 'Maildir'
    for index, executable in enumerate((deliver, lda)):
        marker = f'native-contract-{index}@examples.invalid'
        message = (f'From: sender@examples.invalid\nTo: {mailbox}\n'
                   f'Message-ID: <{marker}>\nSubject: native contract\n\nSynthetic body\n')
        run(str(executable), '-d', mailbox, '-f', 'sender@examples.invalid', data=message, user='vpopmail')
        matches = [path for path in maildir.rglob('*')
                   if path.is_file() and path.parent.name in ('new', 'cur') and marker in path.read_text()]
        print('DELIVERY PATHS: ' + repr([str(path.relative_to(maildir)) for path in matches]), flush=True)
        assert all('Junk' in str(path.relative_to(maildir)) for path in matches)
        assert len(matches) == 1, 'LDA must execute the active script exactly once'
    sieve('deactivate')
    assert 'default ACTIVE' in sieve('list').stdout
    sieve('delete', 'native-contract')
    assert 'native-contract' not in sieve('list').stdout
    sieve('get', 'native-contract', expected=68)
    assert all(path.lstat().st_uid == 89 for path in (Path(home) / '.sieve').rglob('*'))
    print('PASS: uid89 lifecycle works for login-disabled canonical mailbox; aliases require vpopmail canonicalization; deliver equals dovecot-lda', flush=True)

    global_path = Path(settings['sieve_script/default/path'])
    global_before = (global_path.read_bytes(), global_path.stat())
    fallback = get_script('default')
    assert fallback == global_before[0].decode()
    personal_default = '# personal default collision\nkeep;\n'
    metadata_probe = '''import json, os, stat, sys
fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
try:
    for component in (sys.argv[1] + '/.sieve').strip('/').split('/'):
        child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        os.close(fd)
        fd = child
    result = {}
    for name in ('default.sieve', 'dovecot.sieve'):
        try:
            item = os.stat(name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            result[name] = None
            continue
        result[name] = {'mode': item.st_mode, 'uid': item.st_uid, 'nlink': item.st_nlink,
                        'target': os.readlink(name, dir_fd=fd) if stat.S_ISLNK(item.st_mode) else None}
    print(json.dumps(result))
finally:
    os.close(fd)
'''
    for action in ('before', 'put', 'activate', 'deactivate', 'delete'):
        if action == 'put':
            sieve(action, '--', 'default', data=personal_default)
        elif action == 'deactivate':
            sieve(action)
        elif action in ('activate', 'delete'):
            sieve(action, '--', 'default')
        print('DEFAULT COLLISION STATE: ' + action, flush=True)
        listing = run('doveadm', '-f', 'json', 'sieve', 'list', '-u', mailbox, user='vpopmail')
        assert json.loads(listing.stdout) == [{'script': 'default', 'active': '' if action == 'deactivate' else 'ACTIVE'}]
        metadata = json.loads(run('python3', '-c', metadata_probe, home, user='vpopmail').stdout)
        personal = metadata['default.sieve']
        active = metadata['dovecot.sieve']
        if action in ('before', 'delete'):
            assert personal is None
        else:
            assert stat.S_ISREG(personal['mode']) and stat.S_IMODE(personal['mode']) == 0o600
            assert personal['uid'] == 89 and personal['nlink'] == 1
        if action in ('put', 'activate'):
            assert stat.S_ISLNK(active['mode']) and active['uid'] == 89
            assert active['target'] == 'default.sieve'
        else:
            assert active is None
        content = get_script('default')
        assert content == (fallback if action in ('before', 'delete') else personal_default)
        marker = f'default-collision-{action}@examples.invalid'
        message = (f'From: sender@examples.invalid\nTo: {mailbox}\n'
                   f'Message-ID: <{marker}>\nX-Spam-Flag: YES\nSubject: collision\n\nSynthetic body\n')
        run(str(lda), '-d', mailbox, '-f', 'sender@examples.invalid', data=message, user='vpopmail')
        matches = [path for path in maildir.rglob('*')
                   if path.is_file() and path.parent.name in ('new', 'cur') and marker in path.read_text()]
        assert len(matches) == 1
        assert ('.Junk' in matches[0].relative_to(maildir).parts) == (active is None)
        assert (global_path.read_bytes(), global_path.stat()) == global_before
    print('PASS: personal default collision never modifies the global script', flush=True)


if __name__ == '__main__':
    main()
