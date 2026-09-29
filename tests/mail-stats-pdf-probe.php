<?php
declare(strict_types=1);

require '/var/www/admin/lib/mail-stats-pdf.php';

function check(bool $condition, string $message): void
{
    if (!$condition) throw new RuntimeException($message);
}

function rejected(callable $call, string $class = LengthException::class): void
{
    try { $call(); } catch (Throwable $error) {
        check($error instanceof $class, 'Wrong rejection: ' . get_class($error) . ': ' . $error->getMessage());
        return;
    }
    throw new RuntimeException('Expected rejection did not occur.');
}

function inspect_pdf(string $bytes, string $directory, string $name): string
{
    check(str_starts_with($bytes, '%PDF-'), 'Missing PDF signature');
    file_put_contents($directory . '/' . $name . '.pdf', $bytes);
    $process = proc_open(['/usr/bin/pdftotext', '-layout', $directory . '/' . $name . '.pdf', '-'], [1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes);
    $text = stream_get_contents($pipes[1]);
    $error = stream_get_contents($pipes[2]);
    fclose($pipes[1]); fclose($pipes[2]);
    check(proc_close($process) === 0 && $error === '', 'Invalid PDF: ' . $error);
    check(!preg_match('~/JavaScript|/JS\b|/Launch\b|/EmbeddedFile\b|/URI\b~', $bytes), 'Active PDF content or clickable link');
    $process = proc_open(['/usr/bin/pdfinfo', $directory . '/' . $name . '.pdf'], [1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes);
    $info = stream_get_contents($pipes[1]); $error = stream_get_contents($pipes[2]);
    fclose($pipes[1]); fclose($pipes[2]);
    check(proc_close($process) === 0 && $error === '' && str_contains($info, '(A4)'), 'PDF metadata or A4 size invalid');
    check(preg_match('/Pages:\s+([0-9]+)/', $info, $pages) === 1 && (int) $pages[1] <= 60, 'Page cap violated');
    return $text . "\n" . $info;
}

if (($argv[1] ?? '') === 'endpoint') {
    // Test the real shared bootstrap with synthetic session state; no DB is opened.
    $mode = $argv[2];
    $_SERVER['REQUEST_METHOD'] = $mode === 'get' ? 'GET' : 'POST';
    if ($mode !== 'anonymous') { $_SERVER['AUTH_TYPE'] = 'Session'; $_SERVER['REMOTE_USER'] = 'test-admin'; }
    if (!in_array($mode, ['anonymous', 'csrf', 'get'], true)) {
        $id = 'pdf' . bin2hex(random_bytes(16));
        file_put_contents('/run/sqmail-admin/sess_' . $id, 'csrf|s:10:"test-token";');
        $_COOKIE['__Host-sqmail-login'] = $id;
        $_POST['csrf'] = 'test-token';
    }
    if ($mode === 'array') $_POST['report'] = ['summary'];
    if ($mode === 'nominal-summary') $_POST += ['report' => 'summary', 'include_nominal' => '1'];
    if ($mode === 'database-down') $_POST += ['report' => 'diagnostic', 'include_nominal' => '0'];
    if ($mode === 'database-down') putenv('MAIL_STATS_PDF_POOL=1');
    if ($mode === 'spoof-pool') $_SERVER['MAIL_STATS_PDF_POOL'] = '1';
    register_shutdown_function(static function (): void { fwrite(STDERR, 'STATUS=' . http_response_code()); });
    require '/var/www/admin/html/stats/export.php';
    exit;
}

set_error_handler(static function (int $level, string $message, string $file, int $line): bool {
    if (!(error_reporting() & $level)) return false;
    throw new ErrorException($message, 0, $level, $file, $line);
});
$directory = '/tmp/mail-stats-pdf-test-' . bin2hex(random_bytes(8));
mkdir($directory, 0700);
try {
    $event = ['id' => '1', 'event_at' => '2026-09-28 22:00:00.000000', 'observed_at' => '2026-09-28 22:01:00.000000',
        'source_key' => 'qmail-send', 'component' => 'sqmail', 'event_type' => 'delivery_local_success', 'severity' => 'info',
        'message_id' => '1', 'queue_id' => '987654321', 'sender' => 'sender-private@example.test', 'recipient' => 'recipient-private@example.test',
        'ip' => '192.0.2.44', 'account' => 'private-account',
        'metadata' => 'Diagnostic ' . "\u{00e9}t\u{00e9}" . ' <img src="file:///etc/passwd"><script type="text/php">file_put_contents("/tmp/pdf-pwned","yes");</script> password=NEVER_PASSWORD token=NEVER_TOKEN SRS0=NEVER_SRS@private.example'];
    $snapshot = ['generated_at' => '2026-09-28 23:00:00.000000', 'instance_id' => str_repeat('a', 32),
        'start' => '2026-09-27 00:00:00.000000', 'end' => '2026-09-29 00:00:00.000000',
        'retention_cutoff' => '2026-03-28 23:00:00.000000', 'history_months' => 6,
        'filters' => ['view' => 'overview', 'component' => 'sqmail', 'address' => $event['sender'], 'ip' => $event['ip'], 'account' => $event['account']],
        'sources' => [], 'counts' => [['event_type' => 'delivery_local_success', 'count' => '7']],
        'series' => [['bucket' => '2026-09-27', 'count' => '2'], ['bucket' => '2026-09-28', 'count' => '7']], 'granularity' => 'day',
        'messages_count' => '7', 'messages_bytes' => '12345', 'events' => [$event],
        'warnings' => ['Coverage is partial. Unknown lines are not zero events.'], 'masked' => false,
        'rankings' => [
            'senders' => [['identity' => $event['sender'], 'messages' => '17', 'bytes' => '12345', 'known_size_messages' => '12']],
            'recipients' => [
                ['identity' => $event['recipient'], 'messages' => '13', 'bytes' => '0', 'known_size_messages' => '0'],
                ['identity' => 'known-zero@example.test', 'messages' => '1', 'bytes' => '0', 'known_size_messages' => '1'],
            ],
            'traffic_domains' => [
                ['identity' => 'sender-domain.private.test', 'received_messages' => '19', 'sent_messages' => '0', 'received_per_minute' => 19 / 2880, 'sent_per_minute' => 0, 'bytes' => '24680', 'known_size_messages' => '18'],
                ['identity' => 'recipient-domain.private.test', 'received_messages' => '0', 'sent_messages' => '23', 'received_per_minute' => 0, 'sent_per_minute' => 23 / 2880, 'bytes' => null, 'known_size_messages' => '0'],
                ['identity' => 'tiny-domain.private.test', 'received_messages' => '1', 'sent_messages' => '1', 'received_per_minute' => 1 / 2880, 'sent_per_minute' => 1 / 2880, 'bytes' => null, 'known_size_messages' => null],
            ],
            'error_domains' => [['identity' => 'error-domain.private.test', 'failed_messages' => '11', 'deferred_messages' => '7', 'affected_messages' => '14']],
        ]];
    foreach (['transport', 'dovecot', 'filtering', 'web', 'maintenance'] as $i => $family) {
        $snapshot['sources'][] = ['source_key' => 'test-' . $family, 'family' => $family, 'status' => $i ? 'unavailable' : 'active',
            'coverage' => 'partial', 'reason_code' => 'synthetic_fixture', 'last_success_at' => $i ? null : '2026-09-28 22:01:00.000000',
            'last_event_at' => $i ? null : $event['event_at'], 'lines_unknown' => '3', 'discontinuities' => '1'];
    }
    if (($argv[1] ?? '') === 'page-limit') {
        $event['metadata'] = str_repeat('bounded synthetic report detail ', 30);
        $snapshot['events'] = array_fill(0, 500, $event);
        try {
            mail_stats_pdf_render($snapshot, 'diagnostic', true);
            throw new RuntimeException('Oversized document was accepted.');
        } catch (LengthException $error) {
            check(str_contains($error->getMessage(), '60 pages') || str_contains($error->getMessage(), 'memory budget'), 'Wrong load-test limit: ' . $error->getMessage());
            print "PAGE_LIMIT_REJECTED\n";
        }
        exit;
    }
    if (($argv[1] ?? '') === 'shutdown') {
        // Exercise cleanup after an uncatchable memory fatal in a separate process.
        $event['metadata'] = str_repeat('bounded synthetic report detail ', 30);
        $snapshot['events'] = array_fill(0, 1000, $event);
        ini_set('memory_limit', '32M');
        mail_stats_pdf_render($snapshot, 'diagnostic', true);
        throw new RuntimeException('Memory pressure did not exercise fatal cleanup.');
    }
    $summary = mail_stats_pdf_render($snapshot, 'summary');
    $text = inspect_pdf($summary, $directory, 'summary');
    foreach ([$event['sender'], $event['recipient'], $event['ip'], $event['account'], 'private.test', 'NEVER_PASSWORD', 'NEVER_TOKEN', 'NEVER_SRS'] as $secret) {
        check(!str_contains($text, $secret) && !str_contains($summary, $secret), 'Summary leaked ' . $secret);
    }
    foreach (['PERSONAL DETAILS MASKED', 'component: sqmail', '12345', 'Peak: 7', '22:01:00', 'Page 1', 'outside server retention'] as $expected) check(str_contains($text, $expected), 'Missing ' . $expected);
    foreach (['Top 10 rankings', 'Senders (top 10)', 'Recipients (top 10)', 'Traffic domains (top 10)', 'Domains with errors (top 10)', '0.007', '0.008', '<0.001', 'Unknown', 'full selected exact period', 'not instantaneous'] as $expected) {
        check(str_contains($text, $expected), 'Missing ranking content: ' . $expected);
    }
    check(preg_match('/\[masked\]\s+17\s+12345\s+12/', $text) === 1, 'Sender counts or known-size coverage missing');
    check(preg_match('/\[masked\]\s+13\s+Unknown\s+0/', $text) === 1, 'Unknown recipient size shown as zero');
    check(preg_match('/\[masked\]\s+1\s+0\s+1/', $text) === 1, 'Known zero size mistaken for unknown');
    check(preg_match('/\[masked\]\s+19\s+0\s+0\.007\s+0\.000\s+24680\s+18/', $text) === 1, 'Received sender-domain flow missing');
    check(preg_match('/\[masked\]\s+0\s+23\s+0\.000\s+0\.008\s+Unknown\s+0/', $text) === 1, 'Sent recipient-domain flow missing');
    check(preg_match('/\[masked\]\s+11\s+7\s+14/', $text) === 1, 'Overlapping error union missing');
    foreach ($snapshot['sources'] as $source) check(str_contains($text, $source['source_key']), 'Source omitted');
    check(str_contains($summary, '/Subtype /Image') || str_contains($text, 'Event counts by UTC day'), 'Chart missing');
    $nominal = mail_stats_pdf_render($snapshot, 'diagnostic', true);
    $nominalText = inspect_pdf($nominal, $directory, 'nominal');
    foreach ([$event['sender'], $event['recipient'], $event['ip'], 'Diagnostic ' . "\u{00e9}t\u{00e9}", 'PERSONAL DETAILS INCLUDED'] as $expected) check(str_contains($nominalText, $expected), 'Nominal field or accents missing: ' . $expected);
    foreach (['traffic_domains', 'error_domains'] as $key) foreach ($snapshot['rankings'][$key] as $row) {
        check(str_contains($nominalText, $row['identity']), 'Explicit nominal ranking identity missing');
    }
    foreach (['NEVER_PASSWORD', 'NEVER_TOKEN', 'NEVER_SRS'] as $secret) check(!str_contains($nominalText, $secret) && !str_contains($nominal, $secret), 'Nominal secret leaked');
    check(!file_exists('/tmp/pdf-pwned') && !str_contains($nominalText, 'root:x:'), 'Markup executed or file included');
    $masked = inspect_pdf(mail_stats_pdf_render($snapshot, 'diagnostic'), $directory, 'masked');
    check(!str_contains($masked, $event['sender']) && !str_contains($masked, $event['account']) && !str_contains($masked, 'private.test'), 'Default diagnostic leaks PII');
    $forcedMask = $snapshot;
    $forcedMask['masked'] = true;
    $forcedText = inspect_pdf(mail_stats_pdf_render($forcedMask, 'diagnostic', true), $directory, 'forced-mask');
    check(!str_contains($forcedText, 'private.test') && !str_contains($forcedText, $event['sender']), 'Snapshot masking policy ignored');
    $malicious = $snapshot;
    $malicious['rankings']['traffic_domains'][0]['identity'] = '<img src="file:///etc/passwd"><script type="text/php">file_put_contents("/tmp/pdf-pwned","yes");</script>';
    [$maliciousHtml] = mail_stats_pdf_document($malicious, 'diagnostic', true);
    check(str_contains($maliciousHtml, '&lt;img src=&quot;file:///etc/passwd&quot;&gt;') && !str_contains($maliciousHtml, '<script'), 'Ranking markup not escaped');
    $maliciousText = inspect_pdf(mail_stats_pdf_render($malicious, 'diagnostic', true), $directory, 'malicious-ranking');
    check(!file_exists('/tmp/pdf-pwned') && !str_contains($maliciousText, 'root:x:'), 'Ranking markup executed or file fetched');
    $empty = $snapshot;
    foreach ($empty['rankings'] as &$rows) $rows = [];
    unset($rows);
    $emptyText = inspect_pdf(mail_stats_pdf_render($empty, 'summary'), $directory, 'empty-rankings');
    check(substr_count($emptyText, 'No matching linked data.') === 4, 'Empty ranking silently omitted');
    $byBytes = $snapshot;
    $byBytes['filters']['rank_by'] = 'bytes';
    $bytesText = inspect_pdf(mail_stats_pdf_render($byBytes, 'summary'), $directory, 'by-bytes');
    check(str_contains($bytesText, 'Traffic ranked by bytes'), 'Ranking order missing');
    foreach ($snapshot['rankings'] as $key => $rows) {
        $largeRanking = $snapshot;
        $largeRanking['rankings'][$key] = array_fill(0, 10, $rows[0]);
        mail_stats_pdf_document($largeRanking, 'summary', false);
        $largeRanking['rankings'][$key][] = $rows[0];
        rejected(static fn() => mail_stats_pdf_render($largeRanking, 'summary'));
    }
    $fullRankings = $snapshot;
    foreach ($fullRankings['rankings'] as &$rows) $rows = array_fill(0, 10, $rows[0]);
    unset($rows);
    $fullText = inspect_pdf(mail_stats_pdf_render($fullRankings, 'summary'), $directory, 'full-rankings');
    check(substr_count($fullText, '[masked]') >= 40, 'Top-10 rows omitted');
    check(preg_match('/Pages:\s+([0-9]+)/', $fullText, $rankingPages) === 1 && (int) $rankingPages[1] <= 4, 'Compact rankings expanded into excessive pages');
    foreach ([-1, INF, NAN, 'not-a-rate', []] as $invalidRate) rejected(static fn() => mail_stats_pdf_rate($invalidRate), UnexpectedValueException::class);
    [$html, $uris] = mail_stats_pdf_document($snapshot, 'diagnostic', true);
    check(str_contains($html, '&lt;img') && !str_contains($html, '<script'), 'Untrusted markup not escaped');
    check(mail_stats_pdf_text('2026-09-28 22:01:00') === '2026-09-28 22:01:00', 'Time mistaken for IPv6');
    check(!str_contains(mail_stats_pdf_text('2001:db8::1234'), 'db8'), 'IPv6 not masked');
    check(!str_contains(mail_stats_pdf_text('{"token":"NEVER_JSON"}', true), 'NEVER_JSON'), 'JSON token leaked');
    check(!str_contains(mail_stats_pdf_text('Authorization: Bearer NEVER_BEARER', true), 'NEVER_BEARER'), 'Authorization token leaked');
    check(!str_contains(mail_stats_pdf_text('{"password":"NEVER WITH SPACES"}', true), 'WITH SPACES'), 'Spaced secret leaked');
    $options = mail_stats_pdf_options($directory, $uris);
    check(!$options->getIsPhpEnabled() && !$options->getIsJavascriptEnabled() && !$options->getIsRemoteEnabled(), 'Unsafe option');
    $protocols = $options->getAllowedProtocols();
    check(array_keys($protocols) === ['file://', 'data://'], 'Unexpected protocol');
    symlink('/etc/passwd', $directory . '/font.ttf');
    foreach (['/etc/passwd', '/opt/mail-stats-pdf/vendor/dompdf/dompdf/src/Options.php', $directory . '/font.ttf'] as $path) {
        $allowed = true;
        foreach ($protocols['file://']['rules'] as $rule) $allowed = $allowed && $rule('file://' . $path)[0];
        check(!$allowed, 'Forbidden local resource allowed: ' . $path);
    }
    foreach ($protocols['file://']['rules'] as $rule) check($rule('file:///opt/mail-stats-pdf/vendor/dompdf/dompdf/lib/fonts/DejaVuSans.ttf')[0], 'Built-in font blocked');
    foreach ($protocols['data://']['rules'] as $rule) {
        check($rule($uris[0])[0], 'Internal chart blocked');
        check(!$rule('data:image/svg+xml;base64,PHN2Zy8+')[0], 'Arbitrary SVG allowed');
    }
    check(!$options->validateRemoteUri('https://example.invalid/resource')[0], 'Remote resource allowed');
    $tooManyPages = new \Dompdf\Dompdf($options);
    $tooManyPages->setCallbacks(mail_stats_pdf_callbacks(memory_get_usage(true), hrtime(true) + 30_000_000_000));
    $tooManyPages->loadHtml(str_repeat('<div style="page-break-after:always">Synthetic page</div>', 61));
    try {
        $tooManyPages->render();
        throw new RuntimeException('61 pages accepted');
    } catch (LengthException $error) {
        check(str_contains($error->getMessage(), '60 pages'), 'Real page guard failed');
    }
    unset($tooManyPages);
    gc_collect_cycles();
    foreach (['events' => 1001, 'counts' => 51, 'series' => 367] as $field => $count) {
        $large = $snapshot;
        $large[$field] = array_fill(0, $count, $snapshot[$field][0]);
        rejected(static fn() => mail_stats_pdf_render($large, 'diagnostic', true));
    }
    $monthly = $snapshot;
    $monthly['granularity'] = 'month';
    $monthly['series'] = array_fill(0, 121, ['bucket' => '2026-01', 'count' => '1']);
    mail_stats_pdf_document($monthly, 'summary', false);
    $monthly['series'][] = ['bucket' => '2026-01', 'count' => '1'];
    rejected(static fn() => mail_stats_pdf_document($monthly, 'summary', false));
    $hourly = $snapshot;
    $hourly['granularity'] = 'hour';
    $hourly['series'] = array_fill(0, 25, ['bucket' => '2026-01-01 00', 'count' => '1']);
    rejected(static fn() => mail_stats_pdf_document($hourly, 'summary', false));
    rejected(static fn() => mail_stats_pdf_document($snapshot, 'summary', true), InvalidArgumentException::class);
    rejected(static fn() => mail_stats_pdf_budget(memory_get_usage(true), hrtime(true) - 1));
    rejected(static fn() => mail_stats_pdf_budget(memory_get_usage(true), hrtime(true) + 1_000_000_000, 61));
    rejected(static fn() => mail_stats_pdf_budget(memory_get_usage(true) - MAIL_STATS_PDF_MEMORY, hrtime(true) + 1_000_000_000));
    $lock = fopen(MAIL_STATS_PDF_BASE . '/render.lock', 'r+');
    flock($lock, LOCK_EX);
    rejected(static fn() => mail_stats_pdf_render($snapshot, 'summary'), RuntimeException::class);
    flock($lock, LOCK_UN); fclose($lock);
    $paginated = $snapshot;
    $paginated['events'] = array_fill(0, 70, $event);
    $pages = inspect_pdf(mail_stats_pdf_render($paginated, 'diagnostic', true), $directory, 'pages');
    check(str_contains($pages, 'Page 2'), 'Pagination not exercised');
    check(glob(MAIL_STATS_PDF_BASE . '/work/*') === [], 'Temporary artifacts remained');
    $orphan = MAIL_STATS_PDF_BASE . '/work/render-' . str_repeat('a', 32);
    mkdir($orphan, 0700);
    file_put_contents($orphan . '/orphan.tmp', 'synthetic stale temporary');
    symlink('/etc', $orphan . '/outside');
    mail_stats_pdf_render($snapshot, 'summary');
    check(!is_dir($orphan) && is_file('/etc/passwd'), 'Orphan cleanup follows links or leaves files');
    foreach (['page-limit', 'shutdown'] as $mode) {
        $process = proc_open(['/usr/bin/php8.5', '-d', 'memory_limit=256M', __FILE__, $mode], [1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes);
        $output = stream_get_contents($pipes[1]); $errors = stream_get_contents($pipes[2]);
        fclose($pipes[1]); fclose($pipes[2]);
        $status = proc_close($process);
        if ($mode === 'page-limit') check($status === 0 && str_contains($output, 'PAGE_LIMIT_REJECTED'), 'Real page limit failed: ' . $errors);
        else check($status !== 0 && str_contains($errors, 'Allowed memory size'), 'Memory pressure not exercised: ' . $errors);
        check(glob(MAIL_STATS_PDF_BASE . '/work/*') === [], 'Fatal/limit cleanup left artifacts');
        $lock = fopen(MAIL_STATS_PDF_BASE . '/render.lock', 'r+');
        check(flock($lock, LOCK_EX | LOCK_NB), 'Fatal/limit cleanup left lock held');
        flock($lock, LOCK_UN); fclose($lock);
    }
    foreach (['anonymous' => 403, 'csrf' => 403, 'get' => 405, 'array' => 400, 'nominal-summary' => 400, 'wrong-pool' => 503, 'spoof-pool' => 503, 'database-down' => 503] as $mode => $expected) {
        $process = proc_open(['/usr/bin/php8.5', __FILE__, 'endpoint', $mode], [1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes);
        $output = stream_get_contents($pipes[1]); $status = stream_get_contents($pipes[2]);
        fclose($pipes[1]); fclose($pipes[2]);
        check(proc_close($process) === 0 && $status === 'STATUS=' . $expected, 'Endpoint ' . $mode . ' failed: ' . $status);
        check(!str_contains($output, 'Stack trace') && !str_contains($output, '/var/qmail'), 'Endpoint leaks internals');
    }
    print "PASS: real PDF, top-10 rankings, domain flows, exact-period rates, unknown sizes, empty rankings, accents, charts, source coverage, masking, secret exclusion, injection, resource denial, bounds, pagination, concurrency, cleanup, auth/CSRF/method/error checks\n";
} finally {
    mail_stats_pdf_remove($directory);
}
