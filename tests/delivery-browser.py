#!/usr/bin/env python3
"""Real Chromium workflow in a disposable MailEnvironment, through synthetic HTTPS.

Requires Python Playwright and Chromium. No ports or production volumes are used.
python3 -B tests/delivery-browser.py --image sqmail-aio:dev --chromium /usr/bin/chromium
"""

import argparse
from pathlib import Path
import signal
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

from mail import MailEnvironment
from playwright.sync_api import expect, sync_playwright


def workflow(base, executable, artifacts):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=executable)
        print('Chromium:', browser.version, flush=True)
        try:
            context = browser.new_context(ignore_https_errors=True, viewport={'width': 1365, 'height': 900})
            page = context.new_page()
            page.set_default_timeout(45000)

            def loaded(errors=False):
                page.wait_for_load_state('networkidle')
                page.evaluate('async () => { await document.fonts.ready; await new Promise(requestAnimationFrame); }')
                if not errors:
                    alerts = page.get_by_role('alert').all_text_contents()
                    assert not alerts, 'Application error: ' + '; '.join(alerts)
                assert page.locator('script').count() == 0, 'Unescaped script element'
                if not page.evaluate('document.documentElement.scrollWidth <= innerWidth'):
                    if artifacts:
                        page.screenshot(path=str(artifacts / 'delivery-failure.png'), full_page=True)
                    offenders = page.locator('body *').evaluate_all('''nodes => nodes.filter(node => {
                        const rect = node.getBoundingClientRect();
                        return rect.width && (rect.right > innerWidth || rect.left < 0);
                    }).slice(0, 12).map(node => ({tag: node.tagName, id: node.id,
                        classes: node.className, width: node.getBoundingClientRect().width}))''')
                    raise AssertionError('Horizontal page overflow: ' + repr(offenders))

            def form(operation):
                return page.locator(f'form:has(input[name="operation"][value="{operation}"])')

            def submit(operation, confirm=False):
                target = form(operation)
                if confirm:
                    target.locator('input[name="confirm"]').check()
                target.get_by_role('button').click()
                loaded()

            page.goto(base + '/delivery/')
            expect(page).to_have_url(base + '/login.php')
            page.get_by_label('Username', exact=True).fill('operator')
            page.get_by_label('Password', exact=True).fill('SyntheticAdminOnly927')
            page.get_by_role('button', name='Sign in', exact=True).click()
            page.locator('a[href="/delivery/"]').click()
            loaded()
            page.get_by_label('Search domains', exact=True).fill('examples.invalid')
            page.get_by_role('button', name='Search', exact=True).click()
            loaded()
            page.get_by_role('link', name='examples.invalid', exact=True).click()
            loaded()
            expect(page.get_by_role('link', name='Unknown-recipient policy', exact=True)).to_have_count(0)
            assert context.request.get(base + '/delivery/domain.php?domain=examples.invalid').status == 404
            page.get_by_label('Search mailboxes', exact=True).fill('alice')
            page.get_by_role('button', name='Search', exact=True).click()
            page.get_by_role('link', name='alice@examples.invalid', exact=True).click()
            loaded()
            print('PASS browser HTTPS login, secure cookies, operator domain/mailbox search', flush=True)

            page.get_by_label('Delivery mode', exact=True).select_option('local')
            submit('qmail_preview')
            expect(page.get_by_label('Delivery configuration diff')).to_contain_text('/usr/libexec/dovecot/deliver')
            submit('qmail_save', confirm=True)
            expect(page.get_by_role('status')).to_contain_text('Delivery configuration updated')
            page.get_by_label('Delivery mode', exact=True).select_option('local_no_sieve')
            submit('qmail_preview')
            submit('qmail_save', confirm=True)
            expect(page.get_by_label('Individual qmail source')).to_have_text('|/var/qmail/bin/preline -f /usr/libexec/dovecot/deliver -o mail_plugins/sieve=no -d $EXT@$USER\n')
            page.get_by_label('Delivery mode', exact=True).select_option('copy_no_sieve')
            page.locator('#destinations').fill('bob@examples.invalid')
            submit('qmail_preview')
            submit('qmail_save', confirm=True)
            expect(page.get_by_label('Individual qmail source')).to_contain_text('&bob@examples.invalid')
            page.get_by_label('Delivery mode', exact=True).select_option('discard')
            page.locator('#destinations').fill('')
            submit('qmail_preview')
            fields = form('qmail_save').evaluate('form => Object.fromEntries(new FormData(form))')
            fields['confirm'] = 'yes'
            denied = context.request.post(base + '/delivery/', form=fields)
            assert 'role="alert"' in denied.text(), 'Discard requires its own acknowledgment'
            page.get_by_role('link', name='Reload observed state', exact=True).click()
            loaded()
            expect(page.get_by_label('Delivery mode', exact=True)).to_have_value('copy_no_sieve')
            page.get_by_label('Delivery mode', exact=True).select_option('discard')
            page.locator('#destinations').fill('')
            submit('qmail_preview')
            form('qmail_save').locator('input[name="confirm_discard"]').check()
            submit('qmail_save', confirm=True)
            expect(page.get_by_label('Individual qmail source')).to_have_text('# SQMail AIO: discard messages for this mailbox\n')
            page.get_by_label('Delivery mode', exact=True).select_option('local_no_sieve')
            submit('qmail_preview')
            submit('qmail_save', confirm=True)
            submit('qmail_restore_preview')
            form('qmail_restore').locator('input[name="confirm_discard"]').check()
            submit('qmail_restore', confirm=True)
            expect(page.get_by_label('Delivery mode', exact=True)).to_have_value('discard')
            page.get_by_label('Delivery mode', exact=True).select_option('local')
            submit('qmail_preview')
            submit('qmail_save', confirm=True)
            expect(page.get_by_label('Individual qmail source')).not_to_contain_text('discard messages')
            print('PASS browser individual no-Sieve/copy/discard and explicit save/restore acknowledgment', flush=True)
            if artifacts:
                page.screenshot(path=str(artifacts / 'delivery-desktop.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 844})
            loaded()
            if artifacts:
                page.screenshot(path=str(artifacts / 'delivery-mobile.png'), full_page=True)
            page.get_by_role('link', name='Reload observed state', exact=True).click()
            loaded()
            page.keyboard.press('Tab')
            assert page.evaluate('document.activeElement.textContent').strip() == 'Skip to content'
            print('PASS browser delivery diff/confirmation, desktop/mobile layout and keyboard entry', flush=True)

            page.get_by_label('Open a new draft name', exact=True).fill('browser-proof')
            page.get_by_role('button', name='Open draft', exact=True).click()
            loaded()
            valid = '# <script>window.unescaped=true</script>\nkeep;\n'
            page.locator('#content').fill(valid)
            submit('sieve_save')
            expect(page.locator('#content')).to_have_value(valid)
            submit('sieve_activate', confirm=True)
            invalid = '# <script>window.unescaped=true</script>\nnot-a-sieve-command;\n'
            page.locator('#content').fill(invalid)
            form('sieve_save').locator('input[name="confirm_active"]').check()
            form('sieve_save').get_by_role('button').click()
            loaded(errors=True)
            expect(page.get_by_role('alert')).to_have_count(1)
            expect(page.locator('#content')).to_have_value(invalid)
            page.get_by_role('link', name='Reload observed state', exact=True).click()
            loaded()
            expect(page.locator('#content')).to_have_value(valid)
            submit('sieve_restore_preview')
            page.get_by_text('Archived previously active source: browser-proof', exact=True).click()
            expect(page.get_by_label('Archived previously active script source')).to_have_text(valid)
            page.get_by_role('link', name='Cancel and reload', exact=True).click()
            loaded()
            submit('sieve_deactivate', confirm=True)
            submit('sieve_delete', confirm=True)
            submit('sieve_restore_preview')
            submit('sieve_restore', confirm=True)
            expect(page.locator('#content')).to_have_value(valid)
            expect(form('sieve_activate')).to_have_count(1)
            print('PASS browser script compilation, escaping, invalid-text preservation, activation and restore', flush=True)

            page.get_by_text('Generate a vacation draft', exact=True).click()
            page.get_by_label('Reply subject', exact=True).fill('Away "quoted" \\ subject')
            page.get_by_label('Reply message', exact=True).fill('First line\nSecond "quoted" line \\ end')
            page.locator('#days').fill('7')
            submit('vacation')
            draft = page.locator('#content').input_value()
            assert 'vacation :days 7' in draft and 'alice@examples.invalid' in draft
            assert '\\"quoted\\"' in draft and '\\\\ end' in draft
            submit('sieve_save')
            expect(form('sieve_activate')).to_have_count(1)
            print('PASS browser vacation draft escaping and validated save without activation', flush=True)
            context.close()
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='sqmail-aio:dev')
    parser.add_argument('--database-image', default='mariadb:11.4')
    parser.add_argument('--chromium', help='Optional system Chromium; otherwise use Playwright Chromium')
    parser.add_argument('--artifacts', type=Path, help='Existing directory for synthetic screenshots')
    args = parser.parse_args()
    if args.artifacts and not args.artifacts.is_dir():
        parser.error('--artifacts must be an existing directory')
    environment = MailEnvironment(args.image, args.database_image)
    proxy = None

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        environment.prepare()
        proxy = subprocess.Popen(['docker', 'exec', environment.mail, 'python3',
                                  '/tests/delivery-browser-proxy.py'])
        address = environment.docker('inspect', '--format',
                                    '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}',
                                    environment.mail).stdout.strip()
        base = 'https://' + address + ':9443'
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if proxy.poll() is not None:
                raise RuntimeError('Synthetic HTTPS proxy stopped unexpectedly')
            try:
                with urllib.request.urlopen(base + '/login.php', context=ssl._create_unverified_context(), timeout=2) as response:
                    if response.status == 200:
                        break
            except (OSError, urllib.error.URLError):
                time.sleep(.2)
        else:
            raise RuntimeError('Synthetic HTTPS proxy did not become ready')
        workflow(base, args.chromium, args.artifacts)
        return 0
    except KeyboardInterrupt:
        return 130
    finally:
        environment.cleanup()
        if proxy is not None:
            proxy.wait(timeout=10)
        print('Disposable browser resources removed', flush=True)


if __name__ == '__main__':
    sys.exit(main())
