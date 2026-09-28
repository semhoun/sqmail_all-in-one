#!/usr/bin/env python3
"""Host-safe tests: pure parsing and temporary files, never native mail tools."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'rootfs/opt/libexec/delivery-admin'
loader = importlib.machinery.SourceFileLoader('delivery_helper', str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
helper = importlib.util.module_from_spec(spec)
loader.exec_module(helper)


class ParserTests(unittest.TestCase):
    def test_removed_domain_operations_are_unavailable(self):
        for operation in ('domain_inspect', 'domain_preview', 'domain_save',
                          'domain_restore_preview', 'domain_restore'):
            with self.subTest(operation=operation):
                self.assertNotIn(operation, helper.OPERATIONS)
        for action in ('domain_resolve', 'domain_inspect', 'domain_propose', 'domain_commit'):
            with self.subTest(action=action), self.assertRaises(helper.Error) as raised:
                helper.worker_action(action, {'domain': 'examples.invalid'})
            self.assertEqual(raised.exception.code, 'invalid_request')
        self.assertTrue({'domains', 'mailboxes'} <= helper.OPERATIONS)

    def test_mailbox_vdelivermail_recursion_refusal(self):
        for action in helper.RECURSIVE_VDELIVERMAIL_LINES:
            content = '# before\n' + action + '\n# after\n'
            self.assertFalse(helper.parse_qmail(content)['editable'])
            self.assertIn('recurse', helper.parse_qmail(content)['reason'])
            with self.assertRaises(helper.Error):
                helper.render_qmail(content, 'local', [])

    def test_absence_and_known_modes(self):
        for content, mode in ((None, 'inherit'), (helper.LDA + '\n', 'local'),
                              ('&a@external.invalid\n', 'forward'),
                              ('a@external.invalid\n' + helper.LDA + '\n', 'copy')):
            with self.subTest(content=content):
                parsed = helper.parse_qmail(content)
                self.assertTrue(parsed['editable'])
                self.assertEqual(parsed['mode'], mode)

    def test_unproven_or_unknown_instructions_readonly(self):
        for content in ('', '# comment\n', '\n', helper.LDA, helper.LDA + '\r\n',
                        helper.LDA + ' ; id\n', '|echo preline\n', './Other/\n',
                        helper.LDA + '\n\n', '&a@external.invalid\0\n',
                        '&a@external.invalid\n&a@external.invalid\n',
                        helper.LDA + '\n' + helper.LDA + '\n',
                        ' &a@external.invalid\n', '&-x@external.invalid\n'):
            with self.subTest(content=content):
                self.assertFalse(helper.parse_qmail(content)['editable'])
                with self.assertRaises(helper.Error):
                    helper.render_qmail(content, 'local', [])

    def test_preserve_comments_bare_spelling_and_action_order(self):
        current = '# top\na@external.invalid\n# between\n' + helper.LDA + '\n&b@external.invalid\n'
        self.assertEqual(helper.render_qmail(current, 'copy', ['b@external.invalid', 'a@external.invalid'])[0], current)
        result = helper.render_qmail(current, 'copy', ['a@external.invalid', 'c@external.invalid'])[0]
        self.assertEqual(result, '# top\na@external.invalid\n# between\n' + helper.LDA + '\n&c@external.invalid\n')

    def test_no_sieve_and_discard_exact_parser(self):
        for content, mode in ((helper.LDA_NO_SIEVE + '\n', 'local_no_sieve'),
                              (helper.LDA_NO_SIEVE + '\na@external.invalid\n', 'copy_no_sieve'),
                              ('&a@external.invalid\n# comment\n' + helper.LDA_NO_SIEVE + '\n', 'copy_no_sieve'),
                              (helper.DISCARD + '\n', 'discard'),
                              ('# before\n' + helper.DISCARD + '\n# after\n', 'discard')):
            with self.subTest(content=content):
                parsed = helper.parse_qmail(content)
                self.assertTrue(parsed['editable'])
                self.assertEqual(parsed['mode'], mode)
                self.assertEqual(helper.render_qmail(content, mode, parsed['destinations'])[0], content)
        for content in (helper.LDA_NO_SIEVE + '\n' + helper.LDA + '\n',
                        helper.LDA + '\n' + helper.LDA_NO_SIEVE + '\n', helper.LDA_NO_SIEVE + '\n' + helper.LDA_NO_SIEVE + '\n',
                        helper.DISCARD + '\n' + helper.DISCARD + '\n',
                        helper.DISCARD + '\n' + helper.LDA_NO_SIEVE + '\n',
                        helper.LDA + '\n' + helper.DISCARD + '\n',
                        helper.DISCARD + '\n&a@external.invalid\n',
                        './Maildir/\n', './Maildir\n', 'Maildir/\n', './Maildir/.Junk/\n', './Maildir/ \n',
                        '~/Maildir/\n', '/var/vpopmail/Maildir/\n',
                        helper.DISCARD + ' \n', helper.DISCARD, helper.DISCARD + '\r\n',
                        helper.DISCARD + '\n\n', helper.LDA_NO_SIEVE + '\u2028# comment\n',
                        helper.LDA_NO_SIEVE.replace('sieve=no', 'sieve=yes') + '\n',
                        helper.LDA_NO_SIEVE.replace('mail_plugins/sieve=no', 'mail_plugins=') + '\n',
                        helper.LDA_NO_SIEVE.replace('mail_plugins/sieve=no', 'mail_plugins/quota=no') + '\n',
                        helper.LDA_NO_SIEVE.replace(' -d ', ' -o quota/enforce=no -d ') + '\n',
                        helper.LDA_NO_SIEVE.replace('/usr/libexec/dovecot/deliver', 'deliver') + '\n',
                        helper.LDA_NO_SIEVE.replace('/var/qmail/bin/preline', '~/bin/preline') + '\n'):
            with self.subTest(content=content):
                self.assertFalse(helper.parse_qmail(content)['editable'])
                with self.assertRaises(helper.Error):
                    helper.render_qmail(content, 'discard', [])

    def test_new_modes_preserve_comments_and_remove_control_marker(self):
        current = '# top\na@external.invalid\n# between\n' + helper.LDA_NO_SIEVE + '\n# end\n'
        self.assertEqual(helper.render_qmail(current, 'copy_no_sieve', ['a@external.invalid'])[0], current)
        discarded = helper.render_qmail(current, 'discard', [])[0]
        self.assertEqual(discarded, '# top\n# between\n# end\n' + helper.DISCARD + '\n')
        for mode, action in (('local', helper.LDA), ('local_no_sieve', helper.LDA_NO_SIEVE),
                             ('forward', '&a@external.invalid')):
            destinations = ['a@external.invalid'] if mode == 'forward' else []
            self.assertEqual(helper.render_qmail(discarded, mode, destinations)[0],
                             '# top\n# between\n# end\n' + action + '\n')
        self.assertIsNone(helper.render_qmail(discarded, 'inherit', [])[0])
        modes = ('inherit', 'local', 'forward', 'copy', 'local_no_sieve', 'copy_no_sieve', 'discard')
        content = None
        for mode in modes + modes[::-1]:
            destinations = ['a@external.invalid'] if mode in ('forward', 'copy', 'copy_no_sieve') else []
            content = helper.render_qmail(content, mode, destinations)[0]
            parsed = helper.parse_qmail(content)
            self.assertTrue(parsed['editable'])
            self.assertEqual(parsed['mode'], mode)
            self.assertEqual(parsed['destinations'], destinations)
            self.assertNotIn('vdelivermail', content or '')
            self.assertNotIn('~', content or '')

    def test_no_sieve_generation_uses_only_exact_absolute_binaries(self):
        command = '|/var/qmail/bin/preline -f /usr/libexec/dovecot/deliver -o mail_plugins/sieve=no -d $EXT@$USER'
        self.assertEqual(helper.LDA_NO_SIEVE, command)
        self.assertEqual(helper.render_qmail(None, 'local_no_sieve', [])[0], command + '\n')
        self.assertEqual(helper.render_qmail(None, 'copy_no_sieve', ['a@external.invalid'])[0],
                         command + '\n&a@external.invalid\n')
        state = {'mailbox': 'alice@examples.invalid', 'qmail': helper.parse_qmail(None)}
        restore = {'qmail': {'content': './Maildir/\n',
                            'metadata': [0, 1, helper.UID, helper.GID, 0o644, 1, 0, 0, 0]}}
        with self.assertRaises(helper.Error) as raised:
            helper.proposed_qmail({'operation': 'qmail_restore'}, state, restore)
        self.assertEqual(raised.exception.code, 'readonly')

    def test_new_mode_destinations_and_alias_safety(self):
        for mode, destinations in (('local_no_sieve', ['a@external.invalid']), ('discard', ['a@external.invalid']),
                                   ('copy_no_sieve', []), ('copy_no_sieve', ['a@external.invalid'] * 2),
                                   ('maildir', []), ('copy_maildir', ['a@external.invalid'])):
            with self.subTest(mode=mode), self.assertRaises(helper.Error):
                helper.render_qmail(None, mode, destinations)
        state = {'mailbox': 'alice@examples.invalid', 'qmail': helper.parse_qmail(None)}
        with patch.object(helper, 'domain_map', return_value={'examples.invalid': 'examples.invalid',
                                                             'alias.invalid': 'examples.invalid'}):
            for destinations in (['alice@examples.invalid'], ['alice@alias.invalid'],
                                 ['bob@examples.invalid', 'bob@alias.invalid']):
                with self.subTest(destinations=destinations), self.assertRaises(helper.Error):
                    helper.proposed_qmail({'mode': 'copy_no_sieve', 'destinations': destinations}, state)

    def test_discard_requires_boolean_confirmation_for_save_and_restore(self):
        state = {'mailbox': 'alice@examples.invalid', 'qmail': helper.parse_qmail(None)}
        restore = {'qmail': {'content': helper.DISCARD + '\n',
                            'metadata': [0, 1, helper.UID, helper.GID, 0o644, 1, 0, 0, 0]}}
        for operation in ('qmail_save', 'qmail_restore'):
            archived = restore if operation == 'qmail_restore' else None
            for confirmation in (None, False, 'true', 'yes', 1, [], {}):
                with self.subTest(operation=operation, confirmation=confirmation), self.assertRaises(helper.Error) as raised:
                    helper.proposed_qmail({'operation': operation, 'mode': 'discard',
                                           'confirm_discard': confirmation}, state, archived)
                self.assertEqual(raised.exception.code, 'confirmation')
            self.assertEqual(helper.proposed_qmail({'operation': operation, 'mode': 'discard',
                                                    'confirm_discard': True}, state, archived), helper.DISCARD + '\n')
        for operation in ('qmail_preview', 'qmail_restore_preview'):
            self.assertEqual(helper.proposed_qmail({'operation': operation, 'mode': 'discard'}, state,
                                                  restore if 'restore' in operation else None), helper.DISCARD + '\n')

    def test_only_lf_separates_qmail_actions(self):
        for separator in ('\v', '\f', '\x85', '\u2028', '\u2029', '\x1c', '\x1d', '\x1e'):
            for content in (helper.LDA + separator + '&a@external.invalid\n',
                            '# comment' + separator + helper.LDA + '\n'):
                with self.subTest(content=repr(content)):
                    self.assertFalse(helper.parse_qmail(content)['editable'])
            content = '# comment' + separator + 'not an action\n' + helper.LDA + '\n'
            self.assertEqual(helper.render_qmail(content, 'local', [])[0], content)

    def test_destination_limits_and_mode_consistency(self):
        for mode, destinations in (('unknown', []), ('local', ['a@b.invalid']),
                                   ('forward', []), ('copy', ['a@b.invalid'] * 2),
                                   ('forward', [f'a{i}@b.invalid' for i in range(21)]),
                                   ('forward', ['a@b.invalid\n|id']), ('forward', 'a@b.invalid')):
            with self.subTest(mode=mode, destinations=destinations):
                with self.assertRaises(helper.Error):
                    helper.render_qmail(None, mode, destinations)

    def test_exact_mailbox_and_script_validation(self):
        for value in ('*', '*@x.invalid', '-A', 'a@x.invalid\n', '../a@x.invalid',
                      'a@x..invalid', 'a@-x.invalid', 'a@x.invalid/../../etc/passwd',
                      'CaseSensitive@external.invalid'):
            with self.subTest(value=value), self.assertRaises(helper.Error):
                helper.address(value)
        for value in ('../secret', 'dir/script', '\\secret', 'a\nflag', '.', '..'):
            with self.subTest(value=value), self.assertRaises(helper.Error):
                helper.script_name(value)
        for name in ('-leading-option', 'script with spaces'):
            self.assertEqual(helper.script_name(name), name)
            with self.assertRaises(helper.Error):
                helper.script_name(name, writable=True)
        self.assertEqual(helper.address('lower@EXTERNAL.INVALID'), 'lower@external.invalid')

    def test_direct_and_alias_self_forwarding_and_duplicate_aliases(self):
        state = {'mailbox': 'alice@examples.invalid', 'qmail': helper.parse_qmail(None)}
        with patch.object(helper, 'native', return_value=('examples.invalid\nalias.invalid (alias of examples.invalid)\n', 0)):
            for destinations in (['alice@examples.invalid'], ['alice@alias.invalid'],
                                 ['bob@examples.invalid', 'bob@alias.invalid']):
                with self.subTest(destinations=destinations), self.assertRaises(helper.Error):
                    helper.proposed_qmail({'mode': 'forward', 'destinations': destinations}, state)

    def test_confirmation_requires_exact_version_and_valias_fingerprint(self):
        state = {'version': 'v', 'valias': {'lines': ['native alias'], 'fingerprint': 'f'}}
        for request in ({}, {'version': 'v'}, {'version': 'v', 'confirm_valias': True},
                        {'version': 'v', 'confirm_valias': 'true', 'valias_fingerprint': 'f'}):
            with self.subTest(request=request), self.assertRaises(helper.Error):
                helper.check_confirmation(request, state)
        helper.check_confirmation({'version': 'v', 'confirm_valias': True, 'valias_fingerprint': 'f'}, state)

    def test_sieve_active_edit_delete_and_reserved_fallback(self):
        state = {'sieve': {'available': True, 'selected': {'name': 'draft', 'exists': True, 'active': True}}}
        for operation in ('sieve_save', 'sieve_delete'):
            with self.subTest(operation=operation), self.assertRaises(helper.Error):
                helper.check_sieve({'operation': operation, 'script': 'draft', 'content': 'keep;'}, state, None)
        helper.check_sieve({'operation': 'sieve_save', 'script': 'draft', 'content': 'keep;',
                            'confirm_active': True}, state, None)
        state['sieve']['selected'] = {'name': 'default', 'exists': False, 'active': False}
        with self.assertRaises(helper.Error):
            helper.check_sieve({'operation': 'sieve_save', 'script': 'default', 'content': 'keep;'}, state, None)
        state['sieve']['selected']['exists'] = True
        with self.assertRaises(helper.Error):
            helper.check_sieve({'operation': 'sieve_save', 'script': 'default', 'content': 'keep;'}, state, None)

    def test_pagination_is_bounded_and_deterministic(self):
        first = helper.paginate([f'a{i:03}@x.invalid' for i in range(120)], {'page': 0})
        self.assertEqual(len(first['items']), 50)
        self.assertEqual(first['next_page'], 1)
        last = helper.paginate([f'a{i:03}@x.invalid' for i in range(120)], {'page': 2})
        self.assertEqual(len(last['items']), 20)
        self.assertIsNone(last['next_page'])
        with self.assertRaises(helper.Error):
            helper.paginate([], {'page': True})


class FileSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='delivery-helper-')
        self.path = Path(self.temporary.name)
        self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY)

    def tearDown(self):
        os.close(self.fd)
        self.temporary.cleanup()

    def test_nofollow_regular_single_link_and_size_bound(self):
        target = self.path / 'target'
        target.write_text('safe')
        (self.path / 'link').symlink_to(target)
        with self.assertRaises(OSError):
            helper.read_file(self.fd, 'link', 100)
        os.link(target, self.path / 'hardlink')
        with self.assertRaises(helper.Error):
            helper.read_file(self.fd, 'target', 100)
        (self.path / 'hardlink').unlink()
        with self.assertRaises(helper.Error):
            helper.read_file(self.fd, 'target', 3)
        os.mkfifo(self.path / 'fifo')
        with self.assertRaises(helper.Error):
            helper.read_file(self.fd, 'fifo', 100)

    def test_directory_component_symlink_is_rejected(self):
        (self.path / 'actual').mkdir()
        (self.path / 'linked').symlink_to(self.path / 'actual', target_is_directory=True)
        with self.assertRaises(OSError):
            helper.directory(str(self.path / 'linked'))

    def test_qmail_owner_modes_and_absence(self):
        with patch.multiple(helper, UID=os.getuid(), GID=os.getgid()):
            self.assertIsNone(helper.qmail_read(self.fd)['content'])
            path = self.path / '.qmail'
            path.write_text(helper.LDA + '\n')
            path.chmod(0o644)
            self.assertEqual(helper.qmail_read(self.fd)['content'], helper.LDA + '\n')
            for mode in (0o755, 0o666, 0o4600):
                path.chmod(mode)
                with self.subTest(mode=mode), self.assertRaises(helper.Error):
                    helper.qmail_read(self.fd)

    def test_backup_failure_preserves_previous_complete_record(self):
        helper.save_backup(self.fd, 'backup', {'old': True})
        before = (self.path / 'backup').read_bytes()
        with patch.object(helper.os, 'replace', side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(OSError):
                helper.save_backup(self.fd, 'backup', {'new': True})
        self.assertEqual((self.path / 'backup').read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.path.iterdir()), ['backup'])
        helper.save_backup(self.fd, 'backup', {'absent': None})
        self.assertEqual((self.path / 'backup').read_text(), '{"absent":null}')
        self.assertEqual((self.path / 'backup').stat().st_mode & 0o777, 0o600)

    def test_backup_directory_fsync_failure_restores_previous_record(self):
        helper.save_backup(self.fd, 'backup', {'old': True})
        before = (self.path / 'backup').read_bytes()
        original = helper.os.fsync
        count = 0
        def fail_after_replace(fd):
            nonlocal count
            if fd == self.fd:
                count += 1
                if count == 2:
                    raise OSError('synthetic directory fsync failure after replacement')
            return original(fd)
        with patch.object(helper.os, 'fsync', side_effect=fail_after_replace):
            with self.assertRaises(OSError):
                helper.save_backup(self.fd, 'backup', {'new': True})
        self.assertEqual((self.path / 'backup').read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.path.iterdir()), ['backup'])

    def test_qmail_restore_recreates_archived_mode_after_absence(self):
        for action in (helper.LDA, helper.LDA_NO_SIEVE, helper.DISCARD):
            with self.subTest(action=action), patch.multiple(helper, UID=os.getuid(), GID=os.getgid()):
                path = self.path / '.qmail'
                path.write_text(action + '\n')
                path.chmod(0o644)
                archived = helper.qmail_read(self.fd)
                path.unlink()
                state = {'mailbox': 'alice@examples.invalid', 'home': str(self.path),
                         '_home': helper.metadata(os.fstat(self.fd))[:5],
                         '_qmail': helper.qmail_read(self.fd), 'qmail': helper.parse_qmail(None),
                         'version': 'v', 'valias': {'lines': [], 'fingerprint': 'f'}, 'sieve': {}}
                def inspect(request):
                    snapshot = helper.qmail_read(self.fd)
                    return dict(state, _qmail=snapshot, qmail=helper.parse_qmail(snapshot['content']))
                with patch.object(helper, 'inspect_worker', side_effect=inspect):
                    helper.commit_worker({'operation': 'qmail_restore', 'version': 'v', 'confirm_discard': True}, state, {'qmail': archived})
                self.assertEqual(path.read_text(), action + '\n')
                self.assertEqual(path.stat().st_mode & 0o777, 0o644)

    def test_discard_confirmation_precedes_backup_and_child_write(self):
        account = {'mailbox': 'alice@examples.invalid', 'home': str(self.path)}
        state = dict(account, version='v', qmail=helper.parse_qmail(None),
                     valias={'lines': [], 'fingerprint': 'f'})
        restore = {'qmail': {'content': helper.DISCARD + '\n',
                            'metadata': [0, 1, helper.UID, helper.GID, 0o644, 1, 0, 0, 0]}}
        original_fstat = os.fstat
        def root_lock(fd):
            info = original_fstat(fd)
            return SimpleNamespace(st_mode=info.st_mode, st_nlink=info.st_nlink, st_uid=0)
        def worker(action, request, expected=None, archived=None):
            if action == 'resolve':
                return account
            if action == 'inspect':
                return state
            if action == 'propose':
                return helper.proposed_qmail(request, expected, archived)
            self.fail('Commit must not be reached without confirmation')
        for operation in ('qmail_save', 'qmail_restore'):
            for confirmation in (None, 'true', False, 1):
                request = dict(account, operation=operation, version='v', mode='discard',
                               confirm_discard=confirmation, backup_version=helper.fingerprint(restore))
                with self.subTest(operation=operation, confirmation=confirmation), \
                        patch.object(helper, 'private_directory', side_effect=lambda path: os.dup(self.fd)), \
                        patch.object(helper.os, 'fstat', side_effect=root_lock), \
                        patch.object(helper, 'worker', side_effect=worker), \
                        patch.object(helper, 'load_backup', return_value=restore), \
                        patch.object(helper, 'save_backup') as save:
                    with self.assertRaises(helper.Error) as raised:
                        helper.dispatch(request)
                    self.assertEqual(raised.exception.code, 'confirmation')
                    save.assert_not_called()
                with patch.object(helper, 'inspect_worker', return_value=state), \
                        patch.object(helper, 'directory') as directory:
                    with self.assertRaises(helper.Error) as raised:
                        helper.commit_worker(request, state, restore if operation == 'qmail_restore' else None)
                    self.assertEqual(raised.exception.code, 'confirmation')
                    directory.assert_not_called()
        # Discard acknowledgement does not bypass the independent valias gate.
        state['valias']['lines'] = ['&alias@external.invalid']
        request.update(confirm_discard=True)
        with patch.object(helper, 'inspect_worker', return_value=state), \
                patch.object(helper, 'directory') as directory:
            with self.assertRaises(helper.Error) as raised:
                helper.commit_worker(request, state, restore)
            self.assertEqual(raised.exception.code, 'confirmation')
            directory.assert_not_called()

    def test_backup_cleanup_failure_does_not_report_write_failure(self):
        helper.save_backup(self.fd, 'backup', {'old': True})
        original = helper.os.unlink
        def fail_cleanup(name, **kwargs):
            if str(name).startswith('.previous-'):
                raise OSError('synthetic cleanup failure')
            return original(name, **kwargs)
        with patch.object(helper.os, 'unlink', side_effect=fail_cleanup):
            helper.save_backup(self.fd, 'backup', {'new': True})
        self.assertEqual((self.path / 'backup').read_text(), '{"new":true}')

    def test_read_detects_path_replacement(self):
        (self.path / 'target').write_text('old')
        original = helper.os.read
        def replace_after_read(fd, size):
            result = original(fd, size)
            if result:
                (self.path / 'replacement').write_text('new')
                os.replace(self.path / 'replacement', self.path / 'target')
            return result
        with patch.object(helper.os, 'read', side_effect=replace_after_read):
            with self.assertRaises(helper.Error) as raised:
                helper.read_file(self.fd, 'target', 100)
        self.assertEqual(raised.exception.code, 'conflict')

    def test_inspect_exact_no_alias_diagnostic_only(self):
        mailbox = 'alice@examples.invalid'
        with patch.multiple(helper, UID=os.getuid(), GID=os.getgid()), \
                patch.object(helper, 'resolve', return_value={'mailbox': mailbox, 'home': str(self.path)}), \
                patch.object(helper, 'global_file', return_value=helper.LDA), \
                patch.object(helper, 'sieve_state', return_value={'available': False}), \
                patch.object(helper, 'native', side_effect=helper.Error('native_failed', 'No aliases ' + mailbox + ' found\n')):
            state = helper.inspect_worker({'mailbox': mailbox})
            self.assertEqual(state['valias']['lines'], [])
            self.assertTrue(state['qmail']['editable'])
        with patch.multiple(helper, UID=os.getuid(), GID=os.getgid()), \
                patch.object(helper, 'resolve', return_value={'mailbox': mailbox, 'home': str(self.path)}), \
                patch.object(helper, 'global_file', return_value=helper.LDA), \
                patch.object(helper, 'native', side_effect=helper.Error('native_failed', 'database unavailable')):
            with self.assertRaises(helper.Error):
                helper.inspect_worker({'mailbox': mailbox})

    def test_authentication_expiry_revocation_and_actor_derivation(self):
        digest = 'b' * 64
        expiry = str(int(time.time()) + 300)
        for record, credentials, valid in (
                ('operator\n' + expiry + '\n' + digest + '\n', 'operator:SQMail AIO Admin:' + digest, True),
                ('operator\n1\n' + digest + '\n', 'operator:SQMail AIO Admin:' + digest, False),
                ('operator\n' + expiry + '\n' + digest + '\n', 'operator:SQMail AIO Admin:' + 'c' * 64, False),
                ('operator\n' + expiry + '\n' + digest + '\n', '', False),
                ('operator:forged\n' + expiry + '\n' + digest + '\n', '', False)):
            with self.subTest(valid=valid, record=record[:20]), \
                    patch.object(helper, 'directory', side_effect=lambda path: os.dup(self.fd)), \
                    patch.object(helper.os, 'fstat', return_value=SimpleNamespace(st_uid=33, st_mode=0o40700)), \
                    patch.object(helper, 'read_file', side_effect=[(record, []), (credentials, [])]):
                if valid:
                    self.assertEqual(helper.authenticate('a' * 64), 'operator')
                else:
                    with self.assertRaises(helper.Error):
                        helper.authenticate('a' * 64)
        for token in ('', '../token', 'a' * 63, 'A' * 64, 'a' * 65, [], None):
            with self.subTest(token=token), self.assertRaises(helper.Error):
                helper.authenticate(token)

    def test_restore_rejects_changed_backup_even_with_unchanged_live_version(self):
        original_fstat = os.fstat
        def root_lock(fd):
            info = original_fstat(fd)
            return SimpleNamespace(st_mode=info.st_mode, st_nlink=info.st_nlink, st_uid=0)
        for operation in ('qmail_restore', 'sieve_restore'):
            request = {'operation': operation, 'mailbox': 'alice@examples.invalid', 'script': 'draft',
                       'version': 'unchanged-live-version', 'backup_version': helper.fingerprint({'old': 'A'})}
            account = {'mailbox': request['mailbox'], 'home': str(self.path)}
            state = dict(account, version=request['version'])
            with self.subTest(operation=operation), \
                    patch.object(helper, 'private_directory', side_effect=lambda path: os.dup(self.fd)), \
                    patch.object(helper.os, 'fstat', side_effect=root_lock), \
                    patch.object(helper, 'worker', side_effect=[account, state]), \
                    patch.object(helper, 'load_backup', return_value={'new': 'B'}), \
                    patch.object(helper, 'save_backup') as save:
                with self.assertRaises(helper.Error) as raised:
                    helper.dispatch(request)
                self.assertEqual(raised.exception.code, 'conflict')
                save.assert_not_called()

    def test_private_storage_rechecks_every_ancestor(self):
        root = SimpleNamespace(st_uid=0, st_gid=0, st_mode=0o40755)
        leaf = SimpleNamespace(st_uid=0, st_gid=0, st_mode=0o40700)
        for control_mode, allowed in ((0o40750, True), (0o40777, False), (0o40770, False)):
            control = SimpleNamespace(st_uid=91, st_gid=91, st_mode=control_mode)
            with self.subTest(control_mode=control_mode), \
                    patch.object(helper.os, 'open', side_effect=[10, 11, 12, 13, 14]), \
                    patch.object(helper.os, 'close'), \
                    patch.object(helper.os, 'fstat', side_effect=[root, root, control, leaf]), \
                    patch.object(helper.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=91)):
                if allowed:
                    self.assertEqual(helper.private_directory(helper.BACKUPS), 14)
                else:
                    with self.assertRaises(helper.Error) as raised:
                        helper.private_directory(helper.BACKUPS)
                    self.assertEqual(raised.exception.code, 'unsafe_storage')


if __name__ == '__main__':
    unittest.main()
