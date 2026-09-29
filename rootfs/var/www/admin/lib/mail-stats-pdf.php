<?php
declare(strict_types=1);

const MAIL_STATS_PDF_BASE = '/run/mail-stats-pdf';
const MAIL_STATS_PDF_AUTOLOAD = '/opt/mail-stats-pdf/vendor/autoload.php';
const MAIL_STATS_PDF_MEMORY = 134217728;
const MAIL_STATS_PDF_BYTES = 8388608;

function mail_stats_pdf_text(mixed $value, bool $nominal = false): string
{
    if ($value === null) return 'Unavailable';
    if (!is_scalar($value) || strlen((string) $value) > 4096) {
        throw new LengthException('Report text exceeds its limit. Reduce the period or filters.');
    }
    $value = (string) $value;
    $value = preg_replace('/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/', '', $value);
    $value = preg_replace('/\bSRS[01][=+\-][^\s<>"\x27]+/i', '[redacted SRS]', $value);
    $value = preg_replace('/\b(password|passwd|secret|token|authorization|cookie)["\x27]?\s*[:=][^\r\n]*/i', '$1=[sensitive remainder redacted]', $value);
    $value = preg_replace('/\b(Bearer|Basic)\s+[a-zA-Z0-9._~+\/-]+=*/i', '$1 [redacted]', $value);
    $value = preg_replace('~https?://[^\s<>"\x27]+~i', '[URL omitted]', $value);
    if (!$nominal) {
        $value = preg_replace('/[^\s<>"\x27=@]+@[^\s<>"\x27]+/', '[address masked]', $value);
        $value = preg_replace('/\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b/', '[IP masked]', $value);
        $value = preg_replace_callback('/(?<![a-zA-Z0-9])(?:[a-fA-F0-9]{0,4}:){2,}[a-fA-F0-9:.%]*(?![a-zA-Z0-9])/',
            static fn(array $match): string => filter_var($match[0], FILTER_VALIDATE_IP, FILTER_FLAG_IPV6) !== false ? '[IP masked]' : $match[0], $value);
    }
    return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function mail_stats_pdf_number(mixed $value): string
{
    if ($value === null) return 'Unavailable';
    if ((!is_int($value) && !is_string($value)) || !preg_match('/\A[0-9]{1,20}\z/', (string) $value)) {
        throw new UnexpectedValueException('Invalid report counter.');
    }
    return (string) $value;
}

function mail_stats_pdf_rate(mixed $value): string
{
    if ($value === null) return 'Unknown';
    if ((!is_int($value) && !is_float($value) && !is_string($value)) || !is_numeric($value)
        || !is_finite((float) $value) || (float) $value < 0) {
        throw new UnexpectedValueException('Invalid report rate.');
    }
    if ((float) $value > 0 && (float) $value < 0.001) return '&lt;0.001';
    return number_format((float) $value, 3, '.', '');
}

function mail_stats_pdf_budget(int $baseline, int $deadline, int $pages = 0): void
{
    if ($pages > 60) throw new LengthException('Report exceeds 60 pages. Reduce the period or filters.');
    if (hrtime(true) >= $deadline) throw new LengthException('Report exceeded 30 seconds. Reduce the period or filters.');
    if (memory_get_usage(true) - $baseline > MAIL_STATS_PDF_MEMORY - 4194304) {
        throw new LengthException('Report exceeded its memory budget. Reduce the period or filters.');
    }
}

function mail_stats_pdf_callbacks(int $baseline, int $deadline): array
{
    $guard = static function (...$arguments) use ($baseline, $deadline): void {
        $pages = isset($arguments[1]) && $arguments[1] instanceof \Dompdf\Canvas ? $arguments[1]->get_page_count() : 0;
        mail_stats_pdf_budget($baseline, $deadline, $pages);
    };
    return [
        ['event' => 'begin_page_reflow', 'f' => $guard], ['event' => 'begin_frame', 'f' => $guard],
        ['event' => 'end_page_render', 'f' => $guard],
    ];
}

/** Build only internal markup; every data value is text, never HTML, CSS or a URL. */
function mail_stats_pdf_document(array $snapshot, string $report, bool $nominal): array
{
    if (!in_array($report, ['summary', 'diagnostic'], true) || ($nominal && $report !== 'diagnostic')) {
        throw new InvalidArgumentException('Personal details are available only in an explicit diagnostic export.');
    }
    $nominal = $nominal && !($snapshot['masked'] ?? false);
    foreach (['sources' => 256, 'counts' => 50, 'events' => 1000, 'warnings' => 288] as $key => $limit) {
        if (!is_array($snapshot[$key] ?? null) || !array_is_list($snapshot[$key]) || count($snapshot[$key]) > $limit) {
            throw new LengthException('Report exceeds the ' . $key . ' limit. Reduce the period or filters.');
        }
    }
    $granularity = $snapshot['granularity'] ?? '';
    $pointLimit = ['hour' => 24, 'day' => 366, 'month' => 121][$granularity] ?? 0;
    if (!$pointLimit || !is_array($snapshot['series'] ?? null) || !array_is_list($snapshot['series']) || count($snapshot['series']) > $pointLimit) {
        throw new LengthException('Report series exceeds its limit. Use daily or monthly aggregation.');
    }
    if (!is_array($snapshot['filters'] ?? null)) throw new UnexpectedValueException('Invalid report filters.');
    $rankBy = $snapshot['filters']['rank_by'] ?? 'messages';
    if (!in_array($rankBy, ['messages', 'bytes'], true)) throw new UnexpectedValueException('Invalid ranking order.');
    foreach (['senders', 'recipients', 'traffic_domains', 'error_domains'] as $key) {
        $rows = $snapshot['rankings'][$key] ?? null;
        if (!is_array($rows) || !array_is_list($rows) || count($rows) > 10) {
            throw new LengthException('Report exceeds the top 10 ' . $key . ' limit or ranking data is unavailable.');
        }
    }
    $h = static fn($value): string => mail_stats_pdf_text($value, $nominal);
    $html = '<!doctype html><html><head><meta charset="UTF-8"><style>'
        . '@page{size:A4 portrait;margin:35px 30px 45px}body{font-family:"DejaVu Sans",sans-serif;font-size:9px;color:#182c3b}'
        . 'h1{font-size:21px;color:#193c54}h2{font-size:13px;margin-top:18px;border-bottom:1px solid #aebbc4;padding-bottom:5px}'
        . 'p{line-height:1.4}table{width:100%;border-collapse:collapse;table-layout:fixed}thead{display:table-header-group}'
        . 'td,th{border-bottom:1px solid #dce2e6;padding:5px;text-align:left;vertical-align:top;overflow-wrap:break-word;word-wrap:break-word}'
        . 'th{background:#e8eef2}.notice{padding:8px;background:#edf2f5;color:#263b4b}.small{font-size:7px}.chart{width:520px;height:130px}'
        . '</style></head><body><h1>S/QMail ' . ($report === 'summary' ? 'multiservice summary' : 'delivery and service diagnostic') . '</h1>';
    $html .= '<p>Instance: ' . $h($snapshot['instance_id'] ?? null)
        . '<br>Period (UTC): ' . $h($snapshot['start'] ?? null) . ' to ' . $h($snapshot['end'] ?? null)
        . '<br>Generated (UTC): ' . $h($snapshot['generated_at'] ?? null)
        . '<br>Retention boundary (UTC): ' . $h($snapshot['retention_cutoff'] ?? null)
        . '<br>Last completed purge (UTC): ' . $h($snapshot['purge_last_success_at'] ?? null) . '</p>';
    $html .= '<p class="notice">' . ($nominal ? 'PERSONAL DETAILS INCLUDED: administrator diagnostic. Handle as confidential.' : 'PERSONAL DETAILS MASKED: shareable report; coverage may be partial.')
        . '<br>Downloaded PDFs are outside server retention and will not be deleted by its purge. No message bodies are included.'
        . '<br>Observed logs are not the current queue. Remote acceptance does not prove inbox delivery or reading.</p>';
    $html .= '<h2>Filters</h2><p>';
    foreach (['view', 'source', 'component', 'type', 'severity', 'address', 'queue', 'ip', 'account', 'message', 'rank_by'] as $key) {
        $value = $snapshot['filters'][$key] ?? '';
        if ($value === '' || $value === null) continue;
        if (!$nominal && in_array($key, ['address', 'queue', 'ip', 'account', 'message'], true)) $value = '[masked]';
        $html .= $key . ': ' . $h($value) . '<br>';
    }
    $html .= '</p>';
    foreach ($snapshot['warnings'] as $warning) $html .= '<p class="notice">' . $h($warning) . '</p>';
    $html .= '<h2>Observed activity</h2><p>Observed messages: ' . mail_stats_pdf_number($snapshot['messages_count'] ?? null)
        . ' | Observed message bytes: ' . mail_stats_pdf_number($snapshot['messages_bytes'] ?? null) . '</p>';

    $html .= '<h2>Top 10 rankings</h2><p>Traffic ranked by ' . $rankBy . '; errors by affected messages. Linked data only; missing identities are excluded.'
        . ' Known bytes exclude unknown sizes; size-known counts show coverage.</p>';
    foreach (['senders' => 'Senders', 'recipients' => 'Recipients', 'traffic_domains' => 'Traffic domains', 'error_domains' => 'Domains with errors'] as $key => $title) {
        $html .= '<p><b>' . $title . ' (top 10)</b></p>';
        if (!$snapshot['rankings'][$key]) {
            $html .= '<p>No matching linked data.</p>';
            continue;
        }
        $columns = match ($key) {
            'traffic_domains' => ['received_messages' => 'Received', 'sent_messages' => 'Sent', 'received_per_minute' => 'Received/min', 'sent_per_minute' => 'Sent/min', 'bytes' => 'Known bytes', 'known_size_messages' => 'Size-known'],
            'error_domains' => ['failed_messages' => 'Failed', 'deferred_messages' => 'Deferred', 'affected_messages' => 'Affected'],
            default => ['messages' => 'Messages', 'bytes' => 'Known bytes', 'known_size_messages' => 'Size-known'],
        };
        $html .= '<table class="small"><thead><tr><th style="width:28%">Identity</th>';
        foreach ($columns as $label) $html .= '<th>' . $label . '</th>';
        $html .= '</tr></thead><tbody>';
        foreach ($snapshot['rankings'][$key] as $row) {
            $html .= '<tr><td>' . ($nominal ? $h($row['identity'] ?? null) : '[masked]') . '</td>';
            foreach ($columns as $field => $label) {
                $value = $row[$field] ?? null;
                if ($field === 'bytes' && (($row['known_size_messages'] ?? null) === null || (string) $row['known_size_messages'] === '0')) $value = null;
                $html .= '<td>' . (str_ends_with($field, '_per_minute') ? mail_stats_pdf_rate($value)
                    : ($value === null ? 'Unknown' : mail_stats_pdf_number($value))) . '</td>';
            }
            $html .= '</tr>';
        }
        $html .= '</tbody></table>';
    }
    $html .= '<p class="small">Received: local delivery grouped by sender domain. Sent: remote acceptance grouped by recipient domain, not inbox delivery.'
        . ' Messages are deduplicated per domain and direction. Rates are means over the full selected exact period, not instantaneous.'
        . ' Error domains identify recipient domains, not fault: failed and deferred messages can overlap; affected counts their union.</p>';

    $uris = [];
    if ($snapshot['series']) {
        $maximum = 1.0;
        $peak = '0';
        foreach ($snapshot['series'] as $point) {
            if (!isset($point['count'])) throw new UnexpectedValueException('Unavailable chart counter.');
            $count = mail_stats_pdf_number($point['count']);
            if ((float) $count > (float) $peak) $peak = $count;
            $maximum = max($maximum, (float) $count);
        }
        $width = 500 / count($snapshot['series']);
        $svg = '<svg xmlns="http://www.w3.org/2000/svg" width="520" height="130" viewBox="0 0 520 130"><rect width="520" height="130" fill="#f2f6f8"/>';
        foreach ($snapshot['series'] as $i => $point) {
            $height = 110 * (float) mail_stats_pdf_number($point['count']) / $maximum;
            $svg .= '<rect x="' . (10 + $i * $width) . '" y="' . (120 - $height) . '" width="' . max(0.2, $width * 0.85) . '" height="' . $height . '" fill="#235d7c"/>';
        }
        $svg .= '</svg>';
        $uris[] = 'data:image/svg+xml;base64,' . base64_encode($svg);
        $html .= '<img class="chart" alt="Event counts by UTC bucket" src="' . $uris[0] . '"><p>Event counts by UTC ' . $granularity . ', oldest first. Peak: '
            . $peak . '. Range: ' . $h($snapshot['series'][0]['bucket']) . ' to '
            . $h($snapshot['series'][count($snapshot['series']) - 1]['bucket']) . '.</p>';
    } else {
        $html .= '<p>No observed series is available for this selection; this is not proof of no activity.</p>';
    }
    $html .= '<table><thead><tr><th>Event category (observations, not unique deliveries)</th><th>Count</th></tr></thead><tbody>';
    foreach ($snapshot['counts'] as $row) $html .= '<tr><td>' . $h($row['event_type'] ?? null) . '</td><td>' . mail_stats_pdf_number($row['count'] ?? null) . '</td></tr>';
    $html .= '</tbody></table><h2>Selected sources and coverage</h2><p>Each source has its own collection watermark. Missing or unavailable logs must not be interpreted as zero events.</p>'
        . '<table><thead><tr><th>Source / family</th><th>Status / coverage</th><th>Collection watermark (UTC)</th></tr></thead><tbody>';
    foreach ($snapshot['sources'] as $source) {
        $html .= '<tr><td>' . $h($source['source_key'] ?? null) . '<br>' . $h($source['family'] ?? null) . '</td><td>'
            . $h($source['status'] ?? null) . ' / ' . $h($source['coverage'] ?? null) . '<br>' . $h($source['reason_code'] ?? '')
            . '<br>Unknown lines: ' . mail_stats_pdf_number($source['lines_unknown'] ?? null)
            . '; discontinuities: ' . mail_stats_pdf_number($source['discontinuities'] ?? null) . '</td><td>'
            . $h($source['last_success_at'] ?? null) . '<br>Latest event: ' . $h($source['last_event_at'] ?? null) . '</td></tr>';
    }
    $html .= '</tbody></table>';
    if ($report === 'diagnostic') {
        $html .= '<h2>Frozen diagnostic events (' . count($snapshot['events']) . ')</h2><p>Correlation identifiers are observations, not proof of a relationship. Orphan or incomplete correlations remain explicit.</p>'
            . '<table class="small"><thead><tr><th style="width:21%">Time (UTC) / source</th><th style="width:24%">Type / correlation</th><th>Details</th></tr></thead><tbody>';
        foreach ($snapshot['events'] as $event) {
            $html .= '<tr><td>' . $h($event['event_at'] ?? null) . '<br>' . $h($event['source_key'] ?? null) . '<br>' . $h($event['component'] ?? '')
                . '</td><td>' . $h($event['event_type'] ?? null) . ' / ' . $h($event['severity'] ?? null)
                . '<br>Message: ' . $h($event['message_id'] ?? 'uncorrelated') . '</td><td>';
            foreach (['queue_id', 'sender', 'recipient', 'ip', 'account', 'metadata'] as $key) {
                $value = $event[$key] ?? '';
                if ($value === '' || $value === null) continue;
                $html .= $key . ': ' . ($nominal ? $h($value) : '[masked]') . '<br>';
            }
            $html .= '</td></tr>';
        }
        $html .= '</tbody></table>';
    }
    $html .= '</body></html>';
    if (strlen($html) > 2097152) throw new LengthException('Report exceeds its document limit. Reduce the period or filters.');
    return [$html, $uris];
}

function mail_stats_pdf_options(string $temporary, array $chartUris): \Dompdf\Options
{
    $fonts = '/opt/mail-stats-pdf/vendor/dompdf/dompdf/lib/fonts';
    $options = new \Dompdf\Options([
        'isPhpEnabled' => false, 'isJavascriptEnabled' => false, 'isRemoteEnabled' => false,
        'defaultFont' => 'DejaVu Sans', 'defaultPaperSize' => 'a4', 'pdfBackend' => 'CPDF',
        'tempDir' => $temporary, 'fontDir' => $temporary, 'fontCache' => $temporary,
        'logOutputFile' => '', 'debugKeepTemp' => false, 'imageByteSizeLimit' => 8388608,
    ]);
    $options->setChroot([$fonts]);
    // Dompdf also permits rootDir implicitly. A second rule closes that wider read scope.
    $options->setAllowedProtocols([
        'file://' => ['rules' => [[$options, 'validateLocalUri'], static function (string $uri) use ($fonts): array {
            $path = realpath(str_replace('file://', '', $uri));
            $valid = $path !== false && str_starts_with($path, $fonts . '/')
                && in_array(strtolower(pathinfo($path, PATHINFO_EXTENSION)), ['ttf', 'afm', 'ufm'], true);
            return [$valid, $valid ? null : 'Report resource denied.'];
        }]],
        'data://' => ['rules' => [static fn(string $uri): array => [in_array($uri, $chartUris, true), 'Only internal report charts are permitted.']]],
    ]);
    return $options;
}

/** Private render directories only; never follow symlinks. */
function mail_stats_pdf_remove(string $directory): void
{
    if (is_link($directory) || !is_dir($directory)) return;
    foreach (new DirectoryIterator($directory) as $entry) {
        if ($entry->isDot()) continue;
        $path = $entry->getPathname();
        if ($entry->isDir() && !$entry->isLink()) mail_stats_pdf_remove($path);
        else @unlink($path);
    }
    @rmdir($directory);
}

function mail_stats_pdf_render(array $snapshot, string $report, bool $includeNominal = false): string
{
    $baseline = memory_get_usage(true);
    $deadline = hrtime(true) + 30_000_000_000;
    if (!is_file(MAIL_STATS_PDF_AUTOLOAD)) throw new RuntimeException('PDF renderer is unavailable.');
    foreach ([MAIL_STATS_PDF_BASE => [0, 0755], MAIL_STATS_PDF_BASE . '/work' => [posix_geteuid(), 0700]] as $path => [$owner, $mode]) {
        $stat = @lstat($path);
        if (!$stat || ($stat['mode'] & 0170000) !== 0040000 || $stat['uid'] !== $owner || ($stat['mode'] & 0777) !== $mode) {
            throw new RuntimeException('PDF temporary storage is unavailable.');
        }
    }
    $lockPath = MAIL_STATS_PDF_BASE . '/render.lock';
    $stat = @lstat($lockPath);
    if (!$stat || ($stat['mode'] & 0170000) !== 0100000 || $stat['uid'] !== 0 || ($stat['mode'] & 0777) !== 0660) {
        throw new RuntimeException('PDF concurrency control is unavailable.');
    }
    $lock = @fopen($lockPath, 'r+');
    if ($lock === false) throw new RuntimeException('PDF concurrency control is unavailable.');
    $opened = fstat($lock);
    if ($opened['ino'] !== $stat['ino'] || $opened['dev'] !== $stat['dev'] || !flock($lock, LOCK_EX | LOCK_NB)) {
        fclose($lock);
        throw new RuntimeException('Another PDF report is running. Try again later.');
    }
    $temporary = MAIL_STATS_PDF_BASE . '/work/render-' . bin2hex(random_bytes(16));
    $reserve = str_repeat('x', 65536);
    $cleanup = static function () use (&$lock, &$temporary, &$reserve): void {
        $reserve = '';
        if ($temporary !== '') { mail_stats_pdf_remove($temporary); $temporary = ''; }
        if (is_resource($lock)) { flock($lock, LOCK_UN); fclose($lock); }
        $lock = null;
    };
    register_shutdown_function($cleanup);
    $oldMemory = ini_get('memory_limit');
    $oldTime = (int) ini_get('max_execution_time');
    try {
        // Recover a prior hard-terminated FPM request; the exclusive lock proves it is no longer rendering.
        foreach (new DirectoryIterator(MAIL_STATS_PDF_BASE . '/work') as $entry) {
            if (preg_match('/\Arender-[a-f0-9]{32}\z/', $entry->getFilename()) && $entry->isDir() && !$entry->isLink()) {
                mail_stats_pdf_remove($entry->getPathname());
            }
        }
        if (!mkdir($temporary, 0700)) throw new RuntimeException('PDF temporary storage is unavailable.');
        $target = $baseline + MAIL_STATS_PDF_MEMORY;
        $oldBytes = ini_parse_quantity($oldMemory);
        if ($oldBytes > 0) $target = min($target, $oldBytes);
        if (ini_set('memory_limit', (string) $target) === false || !set_time_limit(30)) {
            throw new RuntimeException('PDF resource limits are unavailable.');
        }
        require_once MAIL_STATS_PDF_AUTOLOAD;
        [$html, $uris] = mail_stats_pdf_document($snapshot, $report, $includeNominal);
        mail_stats_pdf_budget($baseline, $deadline);
        $pdf = new \Dompdf\Dompdf(mail_stats_pdf_options($temporary, $uris));
        $pdf->setCallbacks(mail_stats_pdf_callbacks($baseline, $deadline));
        $pdf->loadHtml($html, 'UTF-8');
        $pdf->render();
        $canvas = $pdf->getCanvas();
        mail_stats_pdf_budget($baseline, $deadline, $canvas->get_page_count());
        $font = $pdf->getFontMetrics()->getFont('DejaVu Sans');
        $canvas->page_text(30, 814, 'S/QMail | UTC | Page {PAGE_NUM} / {PAGE_COUNT}', $font, 8, [0.2, 0.25, 0.3]);
        $pdf->addInfo('Title', 'S/QMail statistics report');
        $pdf->addInfo('Author', 'S/QMail');
        $pdf->addInfo('Subject', 'Bounded administrator report');
        $bytes = $pdf->output();
        mail_stats_pdf_budget($baseline, $deadline);
        if (strlen($bytes) > MAIL_STATS_PDF_BYTES) throw new LengthException('PDF exceeds 8 MiB. Reduce the period or filters.');
        return $bytes;
    } finally {
        unset($pdf, $html, $uris, $canvas);
        gc_collect_cycles();
        $cleanup();
        ini_set('memory_limit', $oldMemory);
        set_time_limit($oldTime);
    }
}
