#!/usr/bin/env python3
"""Real HTTPS/Lua/FPM browser checks with source overlays and a disposable DB.

uv run --with playwright python tests/mail-stats-browser.py
Uses installed Chromium, no published ports, no mail services or existing data.
Screenshots and the bounded test result are written only below /tmp/kilo.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import signal
import ssl
import subprocess
import sys
import time
import urllib.request
import uuid


def serve():
    if not Path('/.dockerenv').is_file() or os.environ.get('MAIL_STATS_BROWSER_FIXTURE') != '1':
        raise RuntimeError('Disposable fixture required')
    subprocess.run(['php8.5', '/tests/mail-stats-browser-fixture.php'], check=True)
    token = os.environ['MAIL_STATS_BROWSER_TOKEN']
    digest = hashlib.sha256(b'synthetic-admin:SQMail AIO Admin:synthetic').hexdigest()
    for path in ['/run/php', '/run/sqmail-admin', '/tmp/browser']:
        Path(path).mkdir(parents=True, exist_ok=True)
    os.chown('/run/sqmail-admin', 33, 33)
    os.chmod('/run/sqmail-admin', 0o700)
    Path('/tmp/browser/lighttpd.log').touch()
    os.chown('/tmp/browser/lighttpd.log', 33, 33)
    for path, content in [
        ('/var/qmail/control/lighttpd-admins.htdigest', 'synthetic-admin:SQMail AIO Admin:' + digest + '\n'),
        ('/run/sqmail-admin/token-' + token, 'synthetic-admin\n' + str(int(time.time()) + 1800) + '\n' + digest + '\n'),
    ]:
        Path(path).write_text(content)
        os.chown(path, 0, 33)
        os.chmod(path, 0o640)
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-subj', '/CN=stats-browser.invalid', '-keyout', '/tmp/browser/key.pem',
                    '-out', '/tmp/browser/cert.pem'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    Path('/tmp/browser/fpm.conf').write_text('''[global]
error_log = /tmp/browser/fpm.log
daemonize = no
[www]
user = www-data
group = www-data
listen = /run/php/stats-browser.sock
listen.owner = www-data
listen.group = www-data
listen.mode = 0660
pm = static
pm.max_children = 2
php_admin_flag[display_errors] = off
php_admin_value[memory_limit] = 128M
''')
    Path('/tmp/browser/lighttpd.conf').write_text('''server.modules = ("mod_magnet", "mod_indexfile", "mod_access", "mod_fastcgi", "mod_staticfile", "mod_openssl")
server.document-root = "/var/www/admin/html"
server.port = 8443
server.bind = "0.0.0.0"
server.username = "www-data"
server.groupname = "www-data"
server.errorlog = "/tmp/browser/lighttpd.log"
server.pid-file = "/tmp/browser/lighttpd.pid"
index-file.names = ("index.php")
static-file.exclude-extensions = (".php")
mimetype.assign = (".css" => "text/css", ".svg" => "image/svg+xml")
ssl.engine = "enable"
ssl.pemfile = "/tmp/browser/cert.pem"
ssl.privkey = "/tmp/browser/key.pem"
magnet.attract-raw-url-to = ("/etc/lighttpd/admin-auth.lua")
fastcgi.server = (".php" => (("socket" => "/run/php/stats-browser.sock", "broken-scriptfilename" => "enable")))
''')
    subprocess.run(['php-fpm8.5', '-t', '-y', '/tmp/browser/fpm.conf'], check=True)
    subprocess.run(['lighttpd', '-tt', '-f', '/tmp/browser/lighttpd.conf'], check=True)
    children = []
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        children.append(subprocess.Popen(['php-fpm8.5', '-F', '-y', '/tmp/browser/fpm.conf']))
        children.append(subprocess.Popen(['lighttpd', '-D', '-f', '/tmp/browser/lighttpd.conf']))
        while all(child.poll() is None for child in children):
            time.sleep(0.25)
        raise RuntimeError('Fixture HTTP process exited unexpectedly')
    finally:
        for child in children:
            child.terminate()
        for child in children:
            child.wait(timeout=10)


def browser_checks(origin, token, screenshot_dir, docker, web):
    from playwright.sync_api import sync_playwright
    checks = []

    def check(value, name):
        if not value:
            page.screenshot(path=str(screenshot_dir / 'failure.png'), full_page=True)
            print('Fixture failure page:', page.url, page.title(), page.inner_text('body')[:300])
            print('Overflow elements:', page.evaluate("[...document.querySelectorAll('body *')].filter(e => !e.closest('.table-responsive') && e.getBoundingClientRect().right > innerWidth).slice(0,10).map(e => [e.tagName,e.className,e.getBoundingClientRect().width])"))
            print('Layout:', page.evaluate("({viewport:innerWidth,body:[getComputedStyle(document.body).display,getComputedStyle(document.body).width],shell:[getComputedStyle(document.querySelector('.stats-shell')).width,getComputedStyle(document.querySelector('.stats-shell')).minWidth],sheets:[...document.styleSheets].map(s=>s.href)})"))
            raise AssertionError(name)
        checks.append(name)
        print('PASS', name)

    with sync_playwright() as playwright:
        candidates = sorted(Path.home().glob('.cache/ms-playwright/chromium-*/chrome-linux64/chrome'))
        browser = playwright.chromium.launch(headless=True, executable_path=str(candidates[-1]) if candidates else None,
                                             args=['--disable-background-networking'])
        context = browser.new_context(ignore_https_errors=True, viewport={'width': 1440, 'height': 1000})
        context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(origin + '/') else route.abort())
        page = context.new_page()
        anonymous = context.request.get(origin + '/stats/', max_redirects=0)
        check(anonymous.status == 303 and anonymous.headers.get('location') == '/login.php', 'real Lua denies anonymous stats')
        await_cookie = {'name': '__Host-sqmail-admin', 'value': token, 'url': origin + '/', 'secure': True, 'httpOnly': True, 'sameSite': 'Strict'}
        context.add_cookies([await_cookie])
        check(any(cookie['name'] == '__Host-sqmail-admin' for cookie in context.cookies()), 'browser accepts secure host-only admin cookie')
        probe = docker('exec', web, 'runuser', '-u', 'www-data', '--', 'test', '-r', '/var/qmail/control/lighttpd-admins.htdigest', check=False)
        check(probe.returncode == 0, 'synthetic Lua credentials readable by web user')
        response = page.goto(origin + '/')
        page.wait_for_load_state('networkidle')
        check(response.status == 200, 'authenticated portal served by Lighttpd and FPM')
        menu = page.get_by_role('link', name='Statistics & logs', exact=False)
        check(menu.count() == 1, 'Reports menu exposes statistics link')
        menu.click()
        page.wait_for_load_state('networkidle')
        check(page.locator('h1').inner_text() == 'Statistics & logs', 'query-backed stats page loads')
        check(page.locator('.stats-events').count() == 0 and page.locator('#coverage-title').count() == 0, 'overview presents summaries rather than detailed logs')
        check(page.locator('[data-ranking]').count() == 4, 'overview has four compact ranking panels')
        check(all(panel.locator('tbody tr').count() <= 10 for panel in page.locator('[data-ranking]').all()), 'every ranking is limited to ten rows')
        check('sender@example.invalid' in page.locator('[data-ranking=senders]').inner_text() and 'recipient@example.invalid' in page.locator('[data-ranking=recipients]').inner_text(), 'sender and recipient rankings contain proven linked identities')
        check('example.invalid-recipient@example.invalid' not in page.locator('[data-ranking=recipients]').inner_text(), 'local qmail routing prefix is absent from recipient ranking')
        check('example.invalid' in page.locator('[data-ranking=traffic_domains]').inner_text() and 'Received / min' in page.locator('[data-ranking=traffic_domains]').inner_text(), 'domain overview includes received and sent mean rates')
        traffic = page.locator('[data-ranking=traffic_domains] tbody tr')
        incoming = traffic.filter(has=page.locator('td', has_text=re.compile(r'^example\.invalid$')))
        outgoing = traffic.filter(has=page.locator('td', has_text=re.compile(r'^remote\.invalid$')))
        check(incoming.locator('td').nth(1).inner_text() == '2' and incoming.locator('td').nth(2).inner_text() == '<0.001', 'local receipts are deduplicated and tiny positive means remain nonzero')
        check(outgoing.locator('td').nth(3).inner_text() == '1' and outgoing.locator('td').nth(4).inner_text() == '<0.001', 'remote domain traffic includes records outside the log page')
        failures = page.locator('[data-ranking=error_domains] tbody tr').first.locator('td').all_inner_texts()
        check(failures == ['failed.invalid', '1', '1', '1'], 'domain problems distinguish overlapping failures and deferrals without retry inflation')
        advanced = page.locator('#stats-advanced-filters')
        check(advanced.count() == 1 and advanced.get_attribute('open') is None, 'overview keeps advanced filters collapsed')
        check(page.locator('.stats-metrics').bounding_box()['y'] < 900, 'desktop shows metrics without a full-screen filter form')
        check(page.locator('.stats-metrics').get_by_title('2048 bytes', exact=True).inner_text() == '2.0 KiB', 'byte totals have readable units and precise original value')
        exact = page.locator('.stats-exact')
        exact.locator('summary').click()
        check('2,048 bytes' in exact.inner_text(), 'exact byte totals remain available with digit grouping')
        exact.locator('summary').click()
        page.get_by_label('Rank by', exact=True).select_option('bytes')
        with page.expect_response(lambda response: response.request.method == 'POST' and response.url == origin + '/stats/') as ranked:
            page.get_by_role('button', name='Update ranking', exact=True).click()
        check(ranked.value.status == 200 and page.get_by_label('Rank by', exact=True).input_value() == 'bytes' and page.url == origin + '/stats/', 'ranking order is selected through protected POST')
        page.evaluate('window.scrollTo(0, 0)')
        page.screenshot(path=str(screenshot_dir / 'desktop.png'), full_page=True)
        page.screenshot(path=str(screenshot_dir / 'desktop-overview.png'))
        page.locator('section:has(#rankings-title)').screenshot(path=str(screenshot_dir / 'desktop-rankings.png'))
        check(page.get_by_role('button', name='Inspect matching events', exact=True).count() == 0, 'overview has no Inspect matching events action')
        page.get_by_role('navigation', name='Statistics views').get_by_role('link', name='Transport / SMTP', exact=True).click()
        check(page.locator('.stats-events tbody tr').count() == 100, 'details view renders bounded first page on demand')
        local_identity = page.locator('.stats-events tbody tr').filter(has=page.locator('.stats-event-type', has_text='delivery_local_success')).first.locator('.stats-identities').inner_text()
        check('recipient@example.invalid' in local_identity and 'example.invalid-recipient@example.invalid' not in local_identity, 'local delivery details show the real recipient')
        check(page.locator('script').count() == 0 and '<script>alert(1)</script>' in page.locator('body').text_content(), 'stored diagnostic remains escaped text')
        check(page.locator('.stats-events').evaluate('table => parseFloat(getComputedStyle(table).fontSize) >= 14'), 'event table uses readable text size')
        timestamp = page.locator('.stats-events time').first
        check(len(timestamp.inner_text()) == 19 and '.' in timestamp.get_attribute('title'), 'timestamps stay compact without losing exact precision')
        diagnostic = page.locator('.stats-events tbody tr').first.locator('td').last
        check('recognized' not in diagnostic.inner_text().lower() and 's6-utc' not in diagnostic.inner_text(), 'legacy parser bookkeeping is absent from the diagnostic summary')
        check(page.locator('.stats-diagnostic-context').evaluate_all('lists => lists.every(list => list.children.length <= 3)'), 'diagnostic summaries contain at most three useful details')
        technical = diagnostic.locator('.stats-diagnostic-details')
        raw = technical.locator('.stats-raw-diagnostic')
        check(technical.get_attribute('open') is None and raw.get_attribute('open') is None and not raw.is_visible(), 'technical details and raw JSON stay out of the default summary')
        technical.locator(':scope > summary').focus()
        page.keyboard.press('Enter')
        check('Recognized by parser' in technical.inner_text(), 'historical technical fields remain available on demand')
        raw.locator('summary').focus()
        page.keyboard.press('Enter')
        check(raw.get_attribute('open') is not None and '<script>alert(1)</script>' in json.loads(raw.locator('pre').inner_text())['reason_code'], 'keyboard reveals complete escaped diagnostic')
        raw.locator('summary').click()
        technical.locator(':scope > summary').click()
        page.locator('.stats-events tbody tr').first.screenshot(path=str(screenshot_dir / 'desktop-event-row.png'))
        page.goto(origin + '/stats/?view=maintenance')
        warning = page.locator('.stats-diagnostic-warning').first
        check(warning.is_visible() and 'correlation unavailable' in warning.inner_text() and 'Event time uncertain' in warning.inner_text(), 'incomplete correlation and uncertain timestamps remain prominent')
        page.goto(origin + '/stats/?view=web')
        http_row = page.locator('.stats-events tbody tr').filter(has=page.locator('.stats-event-type', has_text='http_access'))
        check('HTTP status: 503' in http_row.inner_text() and 'HTTP method: GET' in http_row.inner_text(), 'HTTP diagnostic shows response status and method')
        page.goto(origin + '/stats/?view=filtering')
        spam_row = page.locator('.stats-events tbody tr').filter(has=page.locator('.stats-event-type', has_text='spam_verdict'))
        check('Not flagged as spam' in spam_row.inner_text() and 'Spam score: 0' in spam_row.inner_text() and 'Spam threshold: 5' in spam_row.inner_text(), 'spam diagnostic retains verdict threshold and zero measurements')
        spam_row.locator('.stats-diagnostic-details > summary').click()
        check('Not recorded (null)' in spam_row.inner_text(), 'unknown values are not presented as measured zero')
        spam_row.locator('.stats-diagnostic-details > summary').click()
        page.goto(origin + '/stats/?view=dovecot')
        empty_row = page.locator('.stats-events tbody tr').filter(has=page.locator('.stats-source', has_text='dovecot'))
        check(empty_row.locator('.stats-diagnostic-details').count() == 0, 'empty diagnostics have no useless JSON control')
        check(page.locator('svg[role=img] > title').count() == 1 and page.locator('svg[role=img] > desc').count() == 1, 'SVG chart has accessible title and description')
        check(all(item.evaluate('(e) => e.labels && e.labels.length > 0') for item in page.locator('.stats-filter input:not([type=hidden]), .stats-filter select').all()), 'every visible filter has a programmatic label')
        check(page.get_by_label('Include addresses, IPs and account details in diagnostic only').is_checked() is False, 'nominal export is explicit and unchecked by default')
        check('masked' in page.get_by_label('Report', exact=True).input_value() or page.get_by_label('Report', exact=True).input_value() == 'summary', 'shareable summary is default')
        page.goto(origin + '/stats/?view=sources')
        coverage_text = page.locator('section:has(#coverage-title)').inner_text().lower().replace('_', ' ')
        check('roundcube-debug' in coverage_text and 'observed only' in coverage_text, 'disabled and observed-only source coverage remains visible')
        check(page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'desktop has no document horizontal overflow')
        page.evaluate('window.scrollTo(0, 0)')
        page.goto(origin + '/stats/?view=transport')
        page.screenshot(path=str(screenshot_dir / 'desktop-transport.png'))
        check(page.get_by_role('navigation', name='Statistics views').get_by_role('link', name='Search', exact=True).count() == 0, 'Search tab is absent while inline search remains available')
        for label, family in [('Overview', None), ('Transport / SMTP', 'transport'), ('Dovecot', 'dovecot'), ('Antispam / antivirus', 'filtering'), ('Web / admin', 'web'), ('Maintenance', 'maintenance'), ('Source status', None)]:
            page.get_by_role('navigation', name='Statistics views').get_by_role('link', name=label, exact=True).click()
            page.wait_for_load_state('networkidle')
            check(page.locator('.stats-tabs [aria-current=page]').inner_text() == label, 'tab navigation: ' + label)
            check(page.get_by_role('button', name='Inspect matching events', exact=True).count() == 0 and page.locator('a[href*="view=search"], input[name=view][value=search]').count() == 0, 'no obsolete Search entrypoints: ' + label)
            if family:
                rows = page.locator('section:has(#coverage-title) tbody tr').all()
                check(all(family in row.locator('td').first.inner_text().lower() for row in rows), 'source family isolation: ' + family)
            if label == 'Source status':
                check(page.locator('.stats-events').count() == 0 and page.locator('#coverage-title').is_visible(), 'source view focuses on coverage without unrelated log rows')
        response = page.goto(origin + '/stats/?view=search')
        check(response.status == 400 and 'Invalid view or report.' in page.get_by_role('alert').inner_text() and page.locator('.stats-events').count() == 0, 'obsolete Search URL is rejected without a hidden compatibility view')
        csrf = page.locator('form.stats-filter input[name=csrf]').input_value()
        denied = context.request.post(origin + '/stats/', form={'csrf': csrf, 'view': 'search'})
        check(denied.status == 400 and 'Invalid view or report.' in denied.text(), 'obsolete Search POST is rejected')
        page.goto(origin + '/stats/?view=transport')
        check(page.locator('#stats-advanced-filters').get_attribute('open') is None, 'unfiltered transport keeps advanced controls collapsed')
        page.locator('#stats-advanced-filters > summary').click()
        page.get_by_label('Exact sender or recipient').fill('recipient@example.invalid')
        page.get_by_label('Historical queue ID').fill('123')
        page.get_by_label('Exact IP', exact=True).fill('192.0.2.1')
        page.get_by_label('Exact account').fill('synthetic-account')
        page.get_by_label('Exact source', exact=True).fill('qmail-send')
        page.get_by_label('Exact component / sub-source').fill('qmail-send')
        page.get_by_label('Exact event type').fill('delivery_local_success')
        page.get_by_label('Severity', exact=True).select_option('info')
        with page.expect_response(lambda response: response.request.method == 'POST' and response.url == origin + '/stats/') as submitted:
            page.get_by_role('button', name='Apply filters').click()
        check(submitted.value.status == 200 and page.url == origin + '/stats/', 'canonical recipient and exact filters submit by POST without nominal URL')
        check(page.locator('#stats-advanced-filters').get_attribute('open') is not None, 'active advanced filters stay visible after submission')
        check(page.get_by_role('button', name='Open occurrence').count() == 2, 'HTTP queue reuse shows two occurrence choices')
        page.get_by_role('button', name='Older events').click()
        check(page.locator('.stats-events tbody tr').count() == 5, 'HTTP cursor pagination preserves filters')
        page.get_by_role('button', name='Open occurrence').first.click()
        check(page.get_by_role('heading', name='Message timeline').count() == 1, 'HTTP occurrence opens message timeline')
        check(page.locator('.stats-tabs [aria-current=page]').inner_text() == 'Transport / SMTP' and page.locator('#stats-advanced-filters').get_attribute('open') is not None, 'occurrence timeline uses transport and opens its active message filter')
        check(page.get_by_label('Exact sender or recipient').input_value() == '' and page.get_by_label('Exact event type').input_value() == '', 'occurrence timeline clears narrowing event filters')
        page.goto(origin + '/stats/')
        page.locator('#stats-advanced-filters > summary').click()
        page.get_by_label('Exact IP', exact=True).fill('bad-ip')
        page.get_by_role('button', name='Apply filters').click()
        check('exact IPv4 or IPv6' in page.get_by_role('alert').inner_text(), 'invalid filter error is visible and specific')
        csrf = page.locator('form.stats-filter input[name=csrf]').input_value()
        denied = context.request.post(origin + '/stats/', form={'csrf': 'wrong', 'address': 'private@example.invalid'})
        check(denied.status == 403, 'real HTTP invalid CSRF rejected')
        denied = context.request.get(origin + '/stats/?address=private@example.invalid')
        check(denied.status == 400, 'real HTTP nominal GET rejected')
        fresh = context.request.post(origin + '/stats/', form={'csrf': csrf, 'source': 'does-not-exist'})
        check(fresh.status == 200 and 'Metrics are unavailable, not proven zero' in fresh.text(), 'unknown source does not claim measured zero')
        check('no-store' in fresh.headers.get('cache-control', '') and "default-src 'none'" in fresh.headers.get('content-security-policy', '') and fresh.headers.get('referrer-policy') == 'no-referrer', 'real HTTP privacy and CSP headers')
        docker('exec', web, 'php8.5', '/tests/mail-stats-browser-fixture.php', 'address-lists')
        for kind, total in [('senders', 116), ('recipients', 118)]:
            page.goto(origin + '/stats/')
            with page.expect_response(lambda response: response.request.method == 'POST' and response.url == origin + '/stats/') as opened:
                page.get_by_role('button', name='View all ' + kind, exact=True).click()
            check(opened.value.status == 200 and page.locator('.stats-address-list tbody tr').count() == 50, 'complete ' + kind + ' list opens through protected POST')
            check(page.locator('.stats-events').count() == 0 and page.get_by_role('button', name='Export PDF', exact=True).count() == 0, 'address list avoids raw logs and misleading full-list PDF export: ' + kind)
            seen = []
            for _ in range(4):
                seen += page.locator('.stats-address-list tbody tr td:first-child').all_inner_texts()
                next_page = page.get_by_role('button', name='Next page', exact=True)
                if not next_page.count():
                    break
                with page.expect_response(lambda response: response.request.method == 'POST' and response.url == origin + '/stats/') as advanced:
                    next_page.click()
                check(advanced.value.status == 200 and 'cursor_identity=' in advanced.value.request.post_data and '@' not in page.url and '%40' not in page.url.lower(), 'address cursor is POST-only: ' + kind)
            check(len(seen) == total and len(set(seen)) == total, 'complete ' + kind + ' traversal has no missing or repeated identities')
            if kind == 'recipients':
                check('recipient@example.invalid' in seen and 'example.invalid-recipient@example.invalid' not in seen, 'complete recipient list uses normalized local addresses')
            page.get_by_role('button', name='First page', exact=True).click()
            check(page.locator('.stats-address-list tbody tr').count() == 50 and page.locator('.stats-address-list tbody tr td').first.inner_text() == seen[0], 'first page resets ' + kind + ' cursor')
            page.get_by_role('button', name='Next page', exact=True).click()
            page.get_by_label('Rank by', exact=True).select_option('bytes')
            page.get_by_role('button', name='Update ranking', exact=True).click()
            expected = ('bulk' if kind == 'senders' else 'dest') + '115@listing.invalid'
            check(page.locator('.stats-address-list tbody tr td').first.inner_text() == expected, 'changing volume order resets ' + kind + ' cursor')
            page.get_by_role('button', name='Back to Overview', exact=True).click()
            check(page.get_by_label('Rank by', exact=True).input_value() == 'bytes' and page.locator('[data-ranking]').count() == 4, 'return preserves ranking order: ' + kind)
        denied = context.request.get(origin + '/stats/?cursor_identity=private%40example.invalid')
        check(denied.status == 400, 'nominal address cursor is rejected in URLs')
        page.goto(origin + '/stats/')
        for width in [390, 320]:
            page.set_viewport_size({'width': width, 'height': 844})
            page.wait_for_load_state('networkidle')
            check(page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'mobile {width}px no document horizontal overflow')
            check(page.get_by_role('button', name='Apply filters').is_visible() and page.get_by_label('Report', exact=True).is_visible(), f'mobile {width}px filter and export controls visible')
            check(page.locator('.table-responsive').count() >= 2, f'mobile {width}px wide tables have local scroll containers')
            page.screenshot(path=str(screenshot_dir / f'mobile-{width}.png'), full_page=True)
            page.screenshot(path=str(screenshot_dir / f'mobile-{width}-overview.png'))
            page.locator('#stats-advanced-filters > summary').click()
            check(page.get_by_label('Exact IP', exact=True).is_visible() and page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'mobile {width}px expanded advanced controls stay readable')
            page.screenshot(path=str(screenshot_dir / f'mobile-{width}-filters.png'))
            page.locator('#stats-advanced-filters > summary').click()
            page.evaluate('window.scrollTo(0, 0)')
            page.get_by_role('button', name='View all recipients', exact=True).click()
            check(page.locator('.stats-address-list tbody tr').count() == 50 and page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'mobile {width}px complete address list remains bounded and readable')
            page.screenshot(path=str(screenshot_dir / f'mobile-{width}-addresses.png'))
            page.get_by_role('button', name='Back to Overview', exact=True).click()
            page.evaluate('window.scrollTo(0, 0)')
        page.get_by_label('Report', exact=True).select_option('diagnostic')
        page.get_by_label('Include addresses, IPs and account details in diagnostic only').check()
        captured = []
        page.route(origin + '/stats/export.php', lambda route: (captured.append(route.request.post_data), route.fulfill(status=200, content_type='text/plain', body='Synthetic export request inspected; PDF rendering is a separate test.')))
        page.get_by_role('button', name='Export PDF', exact=True).click()
        check(len(captured) == 1 and 'include_nominal=1' in captured[0] and 'report=diagnostic' in captured[0] and 'csrf=' in captured[0], 'explicit nominal diagnostic export POST fields')
        # A real table/metadata lock must not monopolize the PHP worker or leak SQL.
        blocker = subprocess.Popen(['docker', 'exec', web, 'php8.5', '-r', 'require "/var/www/admin/lib/mail-stats.php";$db=mail_stats_connect();$db->query("LOCK TABLES mail_stats_events WRITE");echo "locked\\n";flush();sleep(7);$db->query("UNLOCK TABLES");'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            check(blocker.stdout.readline().strip() == 'locked', 'isolated DB lock fixture acquired')
            started = time.monotonic()
            blocked = context.request.get(origin + '/stats/', timeout=12000)
            check(blocked.status == 503 and time.monotonic() - started < 6, 'real HTTP metadata lock fails within bounded wait')
            body = blocked.text()
            check('Statistics database unavailable' in body and all(value not in body for value in ['SyntheticBrowser927', 'mysqli_sql_exception', 'SELECT COUNT', '/var/qmail/control/aio-conf/mysql.php']), 'database error response contains no credentials SQL or stack trace')
        finally:
            blocker.communicate(timeout=10)
        docker('exec', web, 'php8.5', '-r', '$p="/run/mail-stats/web.json";$c=json_decode(file_get_contents($p),true);$c["enabled"]=false;$c["reason"]="Synthetic disabled test";file_put_contents($p,json_encode($c));')
        response = page.goto(origin + '/stats/')
        check(response.status == 503 and 'Synthetic disabled test' in page.get_by_role('alert').inner_text(), 'disabled component shows safe diagnostic without breaking portal')
        page.screenshot(path=str(screenshot_dir / 'mobile-disabled.png'), full_page=True)
        check(context.request.get(origin + '/').status == 200, 'portal remains available while statistics disabled')
        browser.close()
    (screenshot_dir / 'results.txt').write_text('\n'.join('PASS ' + item for item in checks) + '\n')
    print(f'{len(checks)} browser/HTTP assertions passed; screenshots: {screenshot_dir}')


def isolated():
    root = Path(__file__).resolve().parents[1]
    run_id = uuid.uuid4().hex
    prefix = 'sqmail-stats-browser-' + run_id[:12]
    network, database, web = prefix + '-net', prefix + '-db', prefix + '-web'
    label_key = 'sqmail.stats-browser-test'
    label = label_key + '=' + run_id
    token = uuid.uuid4().hex + uuid.uuid4().hex
    screenshot_dir = Path('/tmp/kilo') / prefix
    screenshot_dir.mkdir(mode=0o700)

    def docker(*command, check=True, timeout=120):
        result = subprocess.run(['docker', *command], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        if check and result.returncode:
            raise RuntimeError(result.stdout)
        return result

    def owned(kind, name):
        field = '.Labels' if kind == 'network' else '.Config.Labels'
        result = docker(kind, 'inspect', '--format', '{{index ' + field + ' "' + label_key + '"}}', name, check=False)
        return result.returncode == 0 and result.stdout.strip() == run_id

    try:
        docker('network', 'create', '--internal', '--label', label, network)
        docker('run', '-d', '--name', database, '--label', label, '--network', network, '--network-alias', 'db',
               '--tmpfs', '/var/lib/mysql:rw,nosuid,size=1g', '-e', 'MYSQL_ROOT_PASSWORD=SyntheticRoot927',
               '-e', 'MYSQL_DATABASE=stats', '-e', 'MYSQL_USER=stats', '-e', 'MYSQL_PASSWORD=SyntheticBrowser927', 'mariadb:latest')
        mounts = []
        paths = ['rootfs/var/www/admin/lib/mail-stats.php', 'rootfs/var/www/admin/html/index.php',
                 'rootfs/var/www/admin/html/stats/index.php', 'rootfs/var/www/admin/html/stats/stats.css',
                 'rootfs/var/www/admin/html/css/style.css', 'rootfs/var/www/admin/html/css/bootstrap.min.css',
                 'rootfs/etc/lighttpd/admin-auth.lua', 'rootfs/opt/sql/mail-stats.sql',
                 'tests/mail-stats-browser.py', 'tests/mail-stats-browser-fixture.php']
        for source in paths:
            target = '/' + source.removeprefix('rootfs/')
            mounts += ['--mount', f'type=bind,src={root / source},dst={target},readonly']
        docker('run', '-d', '--name', web, '--label', label, '--network', network, '-e', 'MAIL_STATS_BROWSER_FIXTURE=1',
               '-e', 'MAIL_STATS_BROWSER_TOKEN=' + token, *mounts, '--entrypoint', 'python3', 'sqmail_aio-sqmail_aio:latest',
               '-B', '/tests/mail-stats-browser.py', '--serve')
        ip = docker('inspect', '--format', '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}', web).stdout.strip()
        origin = 'https://' + ip + ':8443'
        deadline = time.monotonic() + 120
        while True:
            try:
                with urllib.request.urlopen(origin + '/css/style.css', context=ssl._create_unverified_context(), timeout=2) as response:
                    if response.status == 200:
                        break
            except Exception:
                running = docker('inspect', '--format', '{{.State.Running}}', web).stdout.strip() == 'true'
                if not running or time.monotonic() > deadline:
                    raise RuntimeError('HTTP fixture did not become ready: ' + docker('logs', web, check=False).stdout)
                time.sleep(0.5)
        browser_checks(origin, token, screenshot_dir, docker, web)
    finally:
        for name in (web, database):
            if owned('container', name):
                docker('rm', '-f', '-v', name)
        if owned('network', network):
            docker('network', 'rm', network)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    serve() if args.serve else isolated()
