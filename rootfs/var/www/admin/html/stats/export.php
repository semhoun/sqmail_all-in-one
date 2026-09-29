<?php
declare(strict_types=1);

require_once __DIR__ . '/../../lib/mail-stats.php';
require_once __DIR__ . '/../../lib/mail-stats-pdf.php';

ini_set('display_errors', '0');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
header("Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'");

try {
    mail_stats_boot();
    if (session_status() === PHP_SESSION_ACTIVE) session_write_close();
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
        header('Allow: POST');
        http_response_code(405);
        exit('PDF export requires POST.');
    }
    foreach ($_POST as $value) {
        if (!is_string($value)) throw new InvalidArgumentException('Invalid report field.');
    }
    $report = $_POST['report'] ?? 'summary';
    $nominal = $_POST['include_nominal'] ?? '0';
    if (!in_array($report, ['summary', 'diagnostic'], true) || !in_array($nominal, ['0', '1'], true)
        || ($nominal === '1' && $report !== 'diagnostic')) {
        throw new InvalidArgumentException('Invalid report mode or personal-details selection.');
    }
    // Only the dedicated pool has a hard wall-clock deadline. Do not trust FastCGI request variables.
    if (getenv('MAIL_STATS_PDF_POOL', true) !== '1') throw new RuntimeException('Bounded PDF pool unavailable.');
    $filters = mail_stats_filters($_POST);
    $filters['report'] = $report;
    $snapshot = mail_stats_snapshot($filters, true, $nominal === '1');
    // The read-only transaction is closed by snapshot(); never hold it during rendering.
    $bytes = mail_stats_pdf_render($snapshot, $report, $nominal === '1');
    header('Content-Type: application/pdf');
    header('Content-Disposition: attachment; filename="sqmail-statistics.pdf"');
    header('Content-Length: ' . strlen($bytes));
    echo $bytes;
} catch (LengthException $error) {
    http_response_code(422);
    header('Content-Type: text/plain; charset=UTF-8');
    echo 'Report exceeds its export limits. Reduce the period or filters and try again.';
} catch (InvalidArgumentException $error) {
    http_response_code(400);
    header('Content-Type: text/plain; charset=UTF-8');
    echo 'Invalid PDF export request.';
} catch (Throwable $error) {
    http_response_code(503);
    header('Content-Type: text/plain; charset=UTF-8');
    echo 'PDF export is unavailable or another report is running. Try again later.';
}
