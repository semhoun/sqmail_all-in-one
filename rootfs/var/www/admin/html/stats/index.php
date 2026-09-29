<?php
declare(strict_types=1);
require dirname(__DIR__, 2) . '/lib/mail-stats.php';
mail_stats_boot();
$csrf = (string) $_SESSION['csrf'];
session_write_close();
$snapshot = null;
$error = '';
$filters = mail_stats_filters([]);
try {
    $filters = mail_stats_filters($_SERVER['REQUEST_METHOD'] === 'POST' ? $_POST : $_GET);
    $snapshot = mail_stats_snapshot($filters);
} catch (InvalidArgumentException | LengthException $exception) {
    http_response_code(400);
    $error = $exception->getMessage();
} catch (Throwable $exception) {
    http_response_code(503);
    $error = $exception instanceof RuntimeException && !($exception instanceof mysqli_sql_exception) ? $exception->getMessage() : 'Statistics unavailable. Mail transport is unaffected.';
}
$formFields = $filters;
if ($snapshot) {
    $formFields['start'] = $snapshot['start'];
    $formFields['end'] = $snapshot['end'];
}
unset($formFields['cursor_at'], $formFields['cursor_id'], $formFields['cursor_metric'], $formFields['cursor_identity'], $formFields['cursor_rank_by']);
$overview = $filters['view'] === 'overview';
$addressView = isset(MAIL_STATS_ADDRESS_VIEWS[$filters['view']]);
$advancedActive = array_filter(array_intersect_key($filters, array_flip(['component', 'type', 'severity', 'address', 'queue', 'ip', 'account', 'message'])), static fn ($value) => $value !== '');

function stats_number(mixed $value, string $unknown = 'Unknown'): string
{
    if ($value === null || $value === '') return mail_stats_escape($unknown);
    // Group decimal strings directly so large database counters retain every digit.
    return mail_stats_escape(preg_replace('/\B(?=(\d{3})+(?!\d))/', ',', (string) $value));
}

function stats_time(mixed $value, string $unknown = 'Unknown'): string
{
    if ($value === null || $value === '') return '<span class="stats-muted">' . mail_stats_escape($unknown) . '</span>';
    $raw = (string) $value;
    return '<time datetime="' . mail_stats_escape(str_replace(' ', 'T', $raw) . 'Z') . '" title="' . mail_stats_escape($raw . ' UTC') . '">' . mail_stats_escape(substr($raw, 0, 19)) . '</time>';
}

function stats_bytes(mixed $value): string
{
    if ($value === null || $value === '') return 'Unknown';
    $bytes = (float) $value;
    $units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB'];
    $unit = 0;
    while ($bytes >= 1024 && $unit < count($units) - 1) {
        $bytes /= 1024;
        $unit++;
    }
    return '<span title="' . mail_stats_escape((string) $value . ' bytes') . '">' . number_format($bytes, $unit === 0 ? 0 : 1) . ' ' . $units[$unit] . '</span>';
}

function stats_rate(mixed $value, mixed $count): string
{
    if ($value === null || !(int) $count) return '<span class="stats-muted">Not observed</span>';
    $rate = (float) $value;
    return $rate > 0 && $rate < 0.001 ? '&lt;0.001' : rtrim(rtrim(number_format($rate, 3), '0'), '.');
}

function stats_badge(mixed $value): string
{
    $text = (string) ($value ?? 'Unknown');
    $tone = match ($text) {
        'error', 'critical', 'failed', 'unavailable' => 'danger',
        'warning', 'partial', 'conditional', 'stale' => 'warning',
        'active', 'complete' => 'success',
        default => 'neutral',
    };
    return '<span class="stats-badge stats-badge-' . $tone . '" title="' . mail_stats_escape($text) . '">' . mail_stats_escape(ucfirst(str_replace('_', ' ', $text))) . '</span>';
}

function stats_diagnostic(array $event): void
{
    $raw = (string) ($event['metadata'] ?? '');
    $decoded = json_decode($raw, true);
    $fields = is_array($decoded) ? $decoded : [];
    $text = static fn (mixed $value): string => is_string($value) ? $value : ($value === null ? 'Not recorded (null)' : (string) json_encode($value, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE));
    $type = (string) ($event['event_type'] ?? '');
    $reason = is_string($fields['reason_code'] ?? null) ? $fields['reason_code'] : '';
    $reasons = [
        'webmail_error' => 'Webmail reported an error', 'clamav_database_unavailable' => 'ClamAV database unavailable',
        'mangled_delivery_report' => 'Malformed delivery report; delivery deferred', 'queue_diagnostic' => 'Queue service reported an error',
        'fpm_diagnostic' => 'PHP-FPM reported an error', 'native_syslog' => 'Native syslog report',
        'new_message' => 'New queue message', 'stopping' => 'Shutdown in progress',
        'Grey_Listed' => 'Greylisted', 'Virus_Infected' => 'Virus detected', 'Spam_Message' => 'Message flagged as spam',
        'Invalid_Size' => 'Invalid message size', 'Toomany_Rcptto' => 'Too many recipients',
        'Bad_Helo' => 'HELO rejected', 'Invalid_Relay' => 'Relay rejected',
    ];
    $heading = match ($type) {
        'delivery_local_success' => 'Delivered locally', 'delivery_remote_success' => 'Accepted by remote server',
        'delivery_success' => 'Delivery succeeded', 'delivery_deferral' => 'Delivery temporarily deferred',
        'delivery_failure' => 'Delivery permanently failed', 'attempt_started' => 'Delivery attempt started',
        'message_observed' => 'Message recorded in queue', 'message_finished' => 'Queue processing finished',
        'bounce_created' => 'Bounce generated', 'queue_status' => 'Queue activity recorded',
        'auth_success' => 'Signed in', 'auth_failure', 'smtp_auth_failure' => 'Authentication failed',
        'smtp_accepted' => 'SMTP request accepted',
        'smtp_rejected' => ($fields['outcome'] ?? null) === 'deferred' ? 'SMTP request deferred' : 'SMTP request rejected',
        'spam_verdict' => match ($fields['verdict'] ?? null) { 'spam' => 'Flagged as spam', 'ham' => 'Not flagged as spam', default => 'Spam scan recorded' },
        'virus_detected' => 'Virus detected', 'http_access' => 'HTTP response recorded',
        'service_started' => 'Service started', 'service_stopped' => 'Service stopped', 'session_closed' => 'Session closed',
        'service_error' => 'Service reported an error', 'service_notice' => 'Service notice recorded',
        default => 'Observation recorded',
    };
    if (in_array($type, ['lifecycle', 'maintenance_run', 'fetchmail_result', 'admin_action', 'dmarc_observed'], true)) {
        $operation = match ($type) { 'maintenance_run' => 'Maintenance', 'fetchmail_result' => 'Mail retrieval', 'admin_action' => 'Admin operation', 'dmarc_observed' => 'DMARC processing', default => 'Lifecycle operation' };
        $heading = $operation . match ($fields['outcome'] ?? null) {
            'started' => ' started', 'success' => ' succeeded', 'failure' => ' failed', 'skipped' => ' skipped',
            default => isset($fields['outcome']) ? ': ' . $text($fields['outcome']) : ' recorded',
        };
    }
    if (in_array($type, ['service_error', 'service_notice', 'queue_status'], true) && isset($reasons[$reason])) $heading = $reasons[$reason];
    echo '<div class="stats-diagnostic-heading">' . mail_stats_escape($heading) . '</div>';
    $warnings = [];
    if ($reason === 'late_archive_append') $warnings[] = 'Late archive append; correlation unavailable';
    elseif (($fields['incomplete'] ?? false) === true) $warnings[] = 'Incomplete correlation';
    if (($fields['time_uncertain'] ?? false) === true) $warnings[] = 'Event time uncertain';
    if ($warnings) echo '<div class="stats-diagnostic-warning">' . mail_stats_escape(implode('. ', $warnings)) . '</div>';
    $labels = ['reason_code' => 'Technical reason', 'smtp_code' => 'SMTP status', 'enhanced_status' => 'Enhanced SMTP status', 'http_status' => 'HTTP status',
        'exit_code' => 'Exit code', 'score' => 'Spam score', 'threshold' => 'Spam threshold', 'protocol' => 'Protocol',
        'duration_ms' => 'Duration (ms)', 'bytes' => 'Size (bytes)', 'method' => 'HTTP method',
        'delivery_kind' => 'Delivery route', 'action' => 'Operation / stage', 'direction' => 'Report source',
        'incomplete' => 'Incomplete correlation', 'time_uncertain' => 'Uncertain event time',
        'recognized' => 'Recognized by parser', 'time_format' => 'Timestamp format', 'subsource' => 'Sub-source'];
    $keys = ['reason_code'];
    if (str_starts_with($type, 'smtp_')) $keys = [...$keys, 'smtp_code', 'enhanced_status', 'protocol', 'action'];
    elseif ($type === 'http_access') $keys = [...$keys, 'http_status', 'method'];
    elseif ($type === 'spam_verdict') $keys = [...$keys, 'score', 'threshold', 'duration_ms', 'bytes'];
    elseif (str_starts_with($type, 'auth_') || $type === 'session_closed') $keys[] = 'protocol';
    elseif ($type === 'message_observed' || str_starts_with($type, 'delivery_') || $type === 'attempt_started') $keys = [...$keys, 'smtp_code', 'enhanced_status', 'delivery_kind', 'bytes'];
    elseif ($type === 'admin_action') $keys[] = 'action';
    elseif ($type === 'dmarc_observed') $keys[] = 'direction';
    if (($fields['outcome'] ?? null) === 'failure' || in_array($event['severity'] ?? '', ['error', 'critical'], true)) $keys = ['exit_code', ...$keys];
    $details = [];
    foreach ($keys as $key) {
        if (!isset($fields[$key]) || $fields[$key] === '') continue;
        $value = $key === 'reason_code' ? ($reasons[$reason] ?? $text($fields[$key])) : $text($fields[$key]);
        if ($key === 'reason_code' && ($reason === 'late_archive_append' || $value === $heading)) continue;
        if ($key === 'delivery_kind' && in_array($type, ['delivery_local_success', 'delivery_remote_success'], true)) continue;
        $details[] = $labels[$key] . ': ' . $value;
        if (count($details) === 3) break;
    }
    if ($details) echo '<ul class="stats-diagnostic-context"><li>' . implode('</li><li>', array_map('mail_stats_escape', $details)) . '</li></ul>';
    if (!$fields && (is_array($decoded) || trim($raw) === '' || trim($raw) === 'null')) return;
    echo '<details class="stats-diagnostic-details"><summary>Technical details</summary>';
    if ($fields) {
        echo '<dl class="stats-key-values">';
        foreach ($fields as $key => $value) {
            $label = $labels[$key] ?? ucfirst(str_replace('_', ' ', (string) $key));
            echo '<div><dt>' . mail_stats_escape($label) . '</dt><dd>' . mail_stats_escape($text($value)) . '</dd></div>';
        }
        echo '</dl>';
    }
    echo '<details class="stats-raw stats-raw-diagnostic"><summary>Raw JSON</summary><pre tabindex="0">' . mail_stats_escape($raw) . '</pre></details></details>';
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Statistics &amp; logs - SQMail AIO</title>
    <link rel="stylesheet" href="/css/bootstrap.min.css">
    <link rel="stylesheet" href="/css/style.css">
    <link rel="stylesheet" href="/stats/stats.css">
</head>
<body class="admin-page">
<div class="admin-shell stats-shell">
    <header class="admin-header">
        <a class="login-brand" href="/">SQMail <span class="login-brand-edition">Administration</span></a>
        <form method="post" action="/logout.php"><?php mail_stats_hidden(['csrf' => $csrf]); ?><button class="admin-signout" type="submit">Sign out</button></form>
    </header>
    <main>
        <header class="login-heading admin-heading">
            <p class="login-eyebrow">Reports &amp; diagnostics</p>
            <h1>Statistics &amp; logs</h1>
            <p>Mail activity, busiest addresses and delivery problems. All times are UTC.</p>
        </header>
        <nav class="stats-tabs" aria-label="Statistics views">
            <?php foreach (MAIL_STATS_VIEWS as $key => $label): ?>
                <a class="btn <?= $filters['view'] === $key ? 'btn-primary' : 'btn-default' ?>" href="/stats/?view=<?= mail_stats_escape($key) ?>" <?= $filters['view'] === $key ? 'aria-current="page"' : '' ?>><?= mail_stats_escape($label) ?></a>
            <?php endforeach; ?>
        </nav>
        <?php if ($error !== ''): ?><div class="alert alert-warning" role="alert"><?= mail_stats_escape($error) ?></div><?php endif; ?>
        <section class="stats-panel" aria-labelledby="filters-title">
            <h2 id="filters-title"><?= mail_stats_escape((MAIL_STATS_VIEWS + MAIL_STATS_ADDRESS_VIEWS)[$filters['view']]) ?></h2>
            <form method="post" action="/stats/" class="stats-filter">
                <?php mail_stats_hidden(['csrf' => $csrf, 'view' => $filters['view'], 'rank_by' => $filters['rank_by']]); ?>
                <label>Start UTC (inclusive)<input class="form-control" type="datetime-local" step="1" name="start" value="<?= mail_stats_escape(str_replace(' ', 'T', substr($formFields['start'], 0, 19))) ?>"></label>
                <label>End UTC (exclusive)<input class="form-control" type="datetime-local" step="1" name="end" value="<?= mail_stats_escape(str_replace(' ', 'T', substr($formFields['end'], 0, 19))) ?>"></label>
                <label>Exact source<input class="form-control" name="source" maxlength="96" value="<?= mail_stats_escape($filters['source']) ?>" placeholder="All registered sources"></label>
                <div class="stats-actions"><button class="btn btn-primary" type="submit">Apply filters</button><a class="btn btn-default" href="/stats/?view=<?= mail_stats_escape($filters['view']) ?>">Reset</a></div>
                <details id="stats-advanced-filters" class="stats-advanced" <?= $advancedActive ? 'open' : '' ?>>
                <summary>Advanced search<?= $advancedActive ? ' (' . count($advancedActive) . ' active)' : '' ?></summary>
                <div class="stats-advanced-fields">
                <label>Exact component / sub-source<input class="form-control" name="component" maxlength="64" value="<?= mail_stats_escape($filters['component']) ?>" placeholder="For example freshclam or fetchmail"></label>
                <label>Exact event type<input class="form-control" name="type" maxlength="64" value="<?= mail_stats_escape($filters['type']) ?>"></label>
                <label>Severity<select class="form-control" name="severity" aria-label="Severity"><?php foreach (['' => 'All', 'debug' => 'Debug', 'info' => 'Info', 'notice' => 'Notice', 'warning' => 'Warning', 'error' => 'Error', 'critical' => 'Critical'] as $value => $label): ?><option value="<?= mail_stats_escape($value) ?>" <?= $filters['severity'] === $value ? 'selected' : '' ?>><?= mail_stats_escape($label) ?></option><?php endforeach; ?></select></label>
                <label>Exact sender or recipient<input class="form-control" name="address" maxlength="320" value="<?= mail_stats_escape($filters['address']) ?>" autocomplete="off" spellcheck="false"></label>
                <label>Historical queue ID<input class="form-control" name="queue" inputmode="numeric" maxlength="20" value="<?= mail_stats_escape($filters['queue']) ?>"></label>
                <label>Exact IP<input class="form-control" name="ip" maxlength="45" value="<?= mail_stats_escape($filters['ip']) ?>" autocomplete="off"></label>
                <label>Exact account<input class="form-control" name="account" maxlength="320" value="<?= mail_stats_escape($filters['account']) ?>" autocomplete="off" spellcheck="false"></label>
                <?php if ($filters['message'] !== ''): ?>
                    <label>Internal message occurrence<input class="form-control" name="message" value="<?= mail_stats_escape($filters['message']) ?>" inputmode="numeric"></label>
                <?php endif; ?>
                </div>
                </details>
            </form>
            <p class="help-block">Exact, case-sensitive values only, no regex. Searches and pagination use protected POST requests, not URL parameters. Default period: seven days, clipped to retained history.</p>
        </section>
        <?php if ($snapshot): ?>
        <?php if (!$addressView): ?>
        <section class="stats-panel" aria-labelledby="period-title">
            <h2 id="period-title">Observed period</h2>
            <p class="stats-period"><?= stats_time($snapshot['start']) ?> <span>to</span> <?= stats_time($snapshot['end']) ?> <span>UTC</span></p>
            <div class="stats-metrics">
                <div><strong><?= stats_number($snapshot['messages_count']) ?></strong><span>Proven message occurrences</span></div>
                <div><strong><?= stats_bytes($snapshot['messages_bytes']) ?></strong><span>Known message bytes</span><details class="stats-exact"><summary>Exact bytes</summary><?= stats_number($snapshot['messages_bytes']) ?> bytes</details></div>
                <?php $byType = array_column($snapshot['counts'], 'count', 'event_type'); foreach (['delivery_local_success' => 'Local delivery successes', 'delivery_remote_success' => 'Remote acceptances', 'delivery_deferral' => 'Temporary deferrals', 'delivery_failure' => 'Permanent failures'] as $type => $label): ?>
                <div><strong<?= isset($byType[$type]) ? '' : ' class="stats-unavailable"' ?>><?= stats_number($byType[$type] ?? null, 'Not observed') ?></strong><span><?= mail_stats_escape($label) ?></span></div>
                <?php endforeach; ?>
            </div>
            <p class="help-block">Message occurrences are distinct retained messages with a proven link to matching events, not “incoming mail”. Bytes count each occurrence once, exclude unknown sizes and are not delivery bytes. Delivery outcomes count attempts, so retries may contribute multiple outcomes. Absent categories are not measured zero.</p>
            <details class="stats-retention"><summary>Snapshot &amp; retention</summary><p>Frozen at <?= stats_time($snapshot['generated_at']) ?> UTC. Retention: <?= stats_number($snapshot['history_months']) ?> calendar months; oldest permitted time <?= stats_time($snapshot['retention_cutoff']) ?> UTC. Last completed purge: <?= stats_time($snapshot['purge_last_success_at'] ?? null) ?>.</p></details>
            <?php if ($overview): ?><details class="stats-activity"><summary>Activity over time</summary><?php endif; ?>
            <?php if ($snapshot['series']): $maximum = max(array_column($snapshot['series'], 'count')); $width = 720 / count($snapshot['series']); ?>
            <figure>
                <svg class="stats-chart" viewBox="0 0 720 180" role="img" aria-labelledby="chart-title chart-desc">
                    <title id="chart-title">Recorded events by <?= mail_stats_escape($snapshot['granularity']) ?></title>
                    <desc id="chart-desc">Counts of matching recorded events, not unique messages. The table below provides all values. Gaps are not evidence of zero activity.</desc>
                    <?php foreach ($snapshot['series'] as $i => $point): $height = 160 * ((float) $point['count'] / max(1, (float) $maximum)); $barWidth = min(36, max(0.5, $width - 1)); ?>
                    <rect x="<?= $i * $width + ($width - $barWidth) / 2 ?>" y="<?= 170 - $height ?>" width="<?= $barWidth ?>" height="<?= $height ?>"><title><?= mail_stats_escape($point['bucket']) ?>: <?= stats_number($point['count']) ?></title></rect>
                    <?php endforeach; ?>
                </svg>
                <div class="stats-chart-range"><span>First bucket: <?= mail_stats_escape($snapshot['series'][0]['bucket']) ?></span><span>Last bucket: <?= mail_stats_escape($snapshot['series'][count($snapshot['series']) - 1]['bucket']) ?></span></div>
                <figcaption>Recorded events by <?= mail_stats_escape($snapshot['granularity']) ?> UTC, maximum <?= stats_number($maximum) ?>. Only observed buckets are drawn.</figcaption>
            </figure>
            <details><summary>Accessible chart data</summary><div class="table-responsive" tabindex="0" role="region" aria-label="Chart data"><table class="table table-striped"><thead><tr><th>UTC bucket</th><th>Recorded events</th></tr></thead><tbody><?php foreach ($snapshot['series'] as $point): ?><tr><td><?= mail_stats_escape($point['bucket']) ?></td><td><?= stats_number($point['count']) ?></td></tr><?php endforeach; ?></tbody></table></div></details>
            <?php else: ?><p>No matching recorded events. Check source coverage before interpreting this result.</p><?php endif; ?>
            <details><summary>Event categories and counts</summary><div class="table-responsive" tabindex="0" role="region" aria-label="Event categories"><table class="table table-striped"><thead><tr><th>Category</th><th>Recorded events</th></tr></thead><tbody><?php foreach ($snapshot['counts'] as $count): ?><tr><td><?= mail_stats_escape($count['event_type']) ?></td><td><?= stats_number($count['count']) ?></td></tr><?php endforeach; ?></tbody></table></div></details>
            <?php if ($overview): ?></details><?php endif; ?>
        </section>
        <?php endif; ?>
        <?php if ($addressView): ?>
        <section class="stats-panel stats-address-list" aria-labelledby="address-list-title" data-address-list="<?= mail_stats_escape($filters['view']) ?>">
            <div class="stats-ranking-header">
                <h2 id="address-list-title"><?= mail_stats_escape(MAIL_STATS_ADDRESS_VIEWS[$filters['view']]) ?></h2>
                <form method="post" action="/stats/" class="stats-ranking-order">
                    <?php $rankingFields = $formFields; unset($rankingFields['rank_by']); mail_stats_hidden($rankingFields + ['csrf' => $csrf]); ?>
                    <label>Rank by<select class="form-control" name="rank_by" aria-label="Rank by"><option value="messages" <?= $filters['rank_by'] === 'messages' ? 'selected' : '' ?>>Message count</option><option value="bytes" <?= $filters['rank_by'] === 'bytes' ? 'selected' : '' ?>>Known volume</option></select></label>
                    <button type="submit" class="btn btn-default">Update ranking</button>
                </form>
            </div>
            <p class="stats-period"><?= stats_time($snapshot['start']) ?> to <?= stats_time($snapshot['end']) ?> UTC</p>
            <p class="help-block">Up to 50 addresses per page across the whole selected period, ordered by <?= $filters['rank_by'] === 'bytes' ? 'known volume' : 'message count' ?>, then case-sensitive address. Only safe, attributable identities are included, with each message counted once per address. Unknown sizes are excluded from volume.</p>
            <div class="table-responsive" tabindex="0" role="region" aria-label="Address list"><table class="table table-striped"><thead><tr><th>Address</th><th>Messages</th><th>Known volume</th></tr></thead><tbody>
            <?php foreach ($snapshot['address_list']['rows'] as $row): ?><tr><td class="stats-ranking-identity"><?= mail_stats_escape($row['identity']) ?></td><td class="stats-numeric"><?= stats_number($row['messages']) ?></td><td class="stats-numeric"><?= (int) $row['known_size_messages'] > 0 ? stats_bytes($row['bytes']) : 'Unknown' ?></td></tr><?php endforeach; ?>
            <?php if (!$snapshot['address_list']['rows']): ?><tr><td colspan="3">No attributable addresses on this page. Return to the first page or check filters and source coverage.</td></tr><?php endif; ?>
            </tbody></table></div>
            <nav class="stats-overview-links stats-address-pagination" aria-label="Address list pages">
                <form method="post" action="/stats/"><?php mail_stats_hidden(array_replace($formFields, ['csrf' => $csrf, 'view' => 'overview'])); ?><button class="btn btn-default" type="submit">Back to Overview</button></form>
                <form method="post" action="/stats/" class="stats-address-first"><?php mail_stats_hidden($formFields + ['csrf' => $csrf]); ?><button class="btn btn-default" type="submit">First page</button></form>
                <?php if ($snapshot['address_list']['next_cursor']): ?><form method="post" action="/stats/" class="stats-address-next"><?php mail_stats_hidden(array_replace($formFields, $snapshot['address_list']['next_cursor'], ['csrf' => $csrf])); ?><button class="btn btn-primary" type="submit">Next page</button></form><?php endif; ?>
            </nav>
            <p class="help-block">The period stays fixed while paging, but collection, backfill or retention purge can change these lists between requests. No snapshot is cached across pages. PDFs contain bounded Top 10 summaries, not the full address list.</p>
        </section>
        <?php endif; ?>
        <?php if ($overview): ?>
        <section class="stats-panel" aria-labelledby="rankings-title">
            <div class="stats-ranking-header">
                <h2 id="rankings-title">Mail overview · Top 10</h2>
                <form method="post" action="/stats/" class="stats-ranking-order">
                    <?php $rankingFields = $formFields; unset($rankingFields['rank_by']); mail_stats_hidden($rankingFields + ['csrf' => $csrf]); ?>
                    <label>Rank by<select class="form-control" name="rank_by" aria-label="Rank by"><option value="messages" <?= $filters['rank_by'] === 'messages' ? 'selected' : '' ?>>Message count</option><option value="bytes" <?= $filters['rank_by'] === 'bytes' ? 'selected' : '' ?>>Known volume</option></select></label>
                    <button type="submit" class="btn btn-default">Update ranking</button>
                </form>
            </div>
            <p class="help-block">Whole selected period. Retries do not add messages; only proven links are included. Missing data is not proof of zero activity.</p>
            <div class="stats-ranking-grid">
            <?php foreach (['senders' => 'Top envelope senders', 'recipients' => 'Top recorded recipients'] as $key => $label): ?>
                <div class="stats-ranking" data-ranking="<?= $key ?>">
                    <h3><?= $label ?></h3>
                    <div class="table-responsive" tabindex="0" role="region" aria-label="<?= $label ?>"><table class="table table-striped"><thead><tr><th>Address</th><th>Messages</th><th>Known volume</th></tr></thead><tbody>
                    <?php foreach ($snapshot['rankings'][$key] as $row): ?><tr><td class="stats-ranking-identity"><?= mail_stats_escape($row['identity']) ?></td><td class="stats-numeric"><?= stats_number($row['messages']) ?></td><td class="stats-numeric"><?= (int) $row['known_size_messages'] > 0 ? stats_bytes($row['bytes']) : 'Unknown' ?></td></tr><?php endforeach; ?>
                    <?php if (!$snapshot['rankings'][$key]): ?><tr><td colspan="3">No attributable messages in this selection.</td></tr><?php endif; ?>
                    </tbody></table></div>
                    <form method="post" action="/stats/" class="stats-view-all"><?php mail_stats_hidden(array_replace($formFields, ['csrf' => $csrf, 'view' => $key])); ?><button class="btn btn-default" type="submit">View all <?= $key ?></button></form>
                </div>
            <?php endforeach; ?>
            </div>
            <div class="stats-ranking" data-ranking="traffic_domains">
                <h3>Traffic by domain</h3>
                <p class="help-block">Received: locally delivered messages, grouped by sender domain. Sent: remote acceptances, grouped by destination domain. Rates are averages over the selected period, not live readings.</p>
                <div class="table-responsive" tabindex="0" role="region" aria-label="Traffic by domain"><table class="table table-striped stats-traffic"><thead><tr><th>Domain</th><th>Received</th><th>Received / min</th><th>Sent</th><th>Sent / min</th><th>Known volume</th></tr></thead><tbody>
                <?php foreach ($snapshot['rankings']['traffic_domains'] as $row): ?><tr><td class="stats-ranking-identity"><?= mail_stats_escape($row['identity']) ?></td><td class="stats-numeric"><?= (int) $row['received_messages'] > 0 ? stats_number($row['received_messages']) : '<span class="stats-muted">Not observed</span>' ?></td><td class="stats-numeric"><?= stats_rate($row['received_per_minute'], $row['received_messages']) ?></td><td class="stats-numeric"><?= (int) $row['sent_messages'] > 0 ? stats_number($row['sent_messages']) : '<span class="stats-muted">Not observed</span>' ?></td><td class="stats-numeric"><?= stats_rate($row['sent_per_minute'], $row['sent_messages']) ?></td><td class="stats-numeric"><?= (int) $row['known_size_messages'] > 0 ? stats_bytes($row['bytes']) : 'Unknown' ?></td></tr><?php endforeach; ?>
                <?php if (!$snapshot['rankings']['traffic_domains']): ?><tr><td colspan="6">No attributable local deliveries or remote acceptances.</td></tr><?php endif; ?>
                </tbody></table></div>
            </div>
            <div class="stats-ranking" data-ranking="error_domains">
                <h3>Domains with delivery problems</h3>
                <div class="table-responsive" tabindex="0" role="region" aria-label="Domains with delivery problems"><table class="table table-striped"><thead><tr><th>Destination domain</th><th>Affected messages</th><th>Permanent failures</th><th>Temporary deferrals</th></tr></thead><tbody>
                <?php foreach ($snapshot['rankings']['error_domains'] as $row): ?><tr><td class="stats-ranking-identity"><?= mail_stats_escape($row['identity']) ?></td><td class="stats-numeric"><?= stats_number($row['affected_messages']) ?></td><td class="stats-numeric"><?= stats_number($row['failed_messages']) ?></td><td class="stats-numeric"><?= stats_number($row['deferred_messages']) ?></td></tr><?php endforeach; ?>
                <?php if (!$snapshot['rankings']['error_domains']): ?><tr><td colspan="4">No attributable delivery problems observed.</td></tr><?php endif; ?>
                </tbody></table></div>
                <p class="help-block">Historical observations, not the current queue or proof of a remote-domain fault. A message may have been deferred, then failed or delivered; error columns can overlap.</p>
            </div>
            <p class="help-block"><?= count($snapshot['sources']) ?> registered sources in this selection. Coverage can be partial, unavailable or unknown; consult source coverage before comparing totals.</p>
            <?php if ($snapshot['purge_delayed']): ?><p class="alert alert-warning">Retention purge is delayed or its last completion is unknown.</p><?php endif; ?>
        </section>
        <?php endif; ?>
        <?php if (!$overview && $snapshot['occurrences']): ?>
        <section class="stats-panel" aria-labelledby="occurrences-title">
            <h2 id="occurrences-title">Historical message occurrences</h2>
            <p>A queue ID can be reused. Each row is a distinct internal occurrence; no nearest-time or address-based correlation is inferred.</p>
            <div class="table-responsive" tabindex="0" role="region" aria-label="Historical message occurrences"><table class="table table-striped stats-occurrences"><thead><tr><th>Occurrence / queue</th><th>Generation</th><th>Started UTC</th><th>Sender</th><th>Finished UTC</th><th>Timeline</th></tr></thead><tbody>
            <?php foreach ($snapshot['occurrences'] as $message): ?><tr><td><?= mail_stats_escape($message['id'] . ' / ' . $message['queue_id']) ?></td><td><?= mail_stats_escape($message['generation']) ?></td><td><?= stats_time($message['started_at']) ?></td><td><?= mail_stats_escape($message['sender']) ?></td><td><?= stats_time($message['finished_at'], 'Not observed') ?></td><td><form method="post" action="/stats/"><?php mail_stats_hidden(array_replace($formFields, ['csrf' => $csrf, 'view' => 'transport', 'source' => '', 'component' => '', 'type' => '', 'severity' => '', 'address' => '', 'queue' => '', 'ip' => '', 'account' => '', 'message' => (string) $message['id']])); ?><button class="btn btn-default btn-sm" type="submit">Open occurrence</button></form></td></tr><?php endforeach; ?>
            </tbody></table></div>
        </section>
        <?php endif; ?>
        <?php if (!$overview && !$addressView && $filters['view'] !== 'sources'): ?>
        <section class="stats-panel" aria-labelledby="events-title">
            <h2 id="events-title"><?= $filters['message'] !== '' ? 'Message timeline' : 'Matching events' ?></h2>
            <p>Newest first, at most 100 events per page. A missing message link means correlation is unavailable or its retained metadata expired.</p>
            <p class="stats-scroll-hint">Scroll horizontally for all columns on smaller screens.</p>
            <div class="table-responsive" tabindex="0" role="region" aria-label="Matching events"><table class="table table-striped stats-events"><thead><tr><th>UTC time / source</th><th>Type / severity</th><th>Identity and correlation</th><th>Diagnostic</th></tr></thead><tbody>
            <?php foreach ($snapshot['events'] as $event): ?>
                <tr>
                    <td><?= stats_time($event['event_at']) ?><div class="stats-source"><?= mail_stats_escape($event['source_key']) ?></div><div class="stats-muted"><?= mail_stats_escape($event['component']) ?></div><small class="stats-observed">Observed <?= stats_time($event['observed_at']) ?></small></td>
                    <td><div class="stats-event-type"><?= mail_stats_escape($event['event_type']) ?></div><?= stats_badge($event['severity']) ?></td>
                    <td><dl class="stats-key-values stats-identities"><?php foreach (['message_id' => 'Occurrence', 'queue_id' => 'Queue', 'sender' => 'Sender', 'recipient' => 'Recipient', 'ip' => 'IP', 'account' => 'Account'] as $field => $label): ?><?php if ($event[$field] !== null): ?><div><dt><?= mail_stats_escape($label) ?></dt><dd><?= mail_stats_escape($event[$field]) ?></dd></div><?php endif; ?><?php endforeach; ?></dl><?php if ($event['message_id'] === null): ?><span class="stats-muted">Unlinked event</span><?php endif; ?></td>
                    <td><?php stats_diagnostic($event); ?></td>
                </tr>
            <?php endforeach; ?>
            <?php if (!$snapshot['events']): ?><tr><td colspan="4">No matching recorded events on this page.</td></tr><?php endif; ?>
            </tbody></table></div>
            <?php if ($snapshot['next_cursor']): ?><form method="post" action="/stats/"><?php mail_stats_hidden(array_replace($formFields, $snapshot['next_cursor'], ['csrf' => $csrf])); ?><button class="btn btn-default" type="submit">Older events</button></form><?php endif; ?>
        </section>
        <?php endif; ?>
        <?php if (!$overview && !$addressView): ?>
        <section class="stats-panel" aria-labelledby="coverage-title">
            <h2 id="coverage-title">Source registry &amp; coverage</h2>
            <p>All registered sources selected by the family/source filter, including disabled, conditional and non-historical sources. Other filters do not hide unavailable sources.</p>
            <p class="stats-scroll-hint">Scroll horizontally for all columns on smaller screens.</p>
            <div class="table-responsive" tabindex="0" role="region" aria-label="Source registry and coverage"><table class="table table-striped stats-coverage"><thead><tr><th>Source / family</th><th>Status / coverage / reason</th><th>First observed UTC</th><th>Last successful collection UTC</th><th>Latest event UTC / lag</th><th>Unknown / seen lines</th><th>Discontinuities</th></tr></thead><tbody>
            <?php foreach ($snapshot['sources'] as $source): ?><tr><td><div class="stats-source"><?= mail_stats_escape($source['source_key']) ?></div><span class="stats-muted"><?= mail_stats_escape($source['family']) ?></span></td><td><div class="stats-status-line"><span>Status</span> <?= stats_badge($source['status']) ?></div><div class="stats-status-line"><span>Coverage</span> <?= stats_badge($source['coverage']) ?></div><div class="stats-reason"><?= mail_stats_escape($source['reason_code'] ?? '') ?></div></td><td><?= stats_time($source['first_seen_at']) ?></td><td><?= stats_time($source['last_success_at']) ?></td><td><?= stats_time($source['last_event_at']) ?><div class="stats-muted">Lag: <?= $source['lag_seconds'] === null ? 'Unknown' : stats_number($source['lag_seconds']) . ' s' ?></div></td><td class="stats-numeric"><?= stats_number($source['lines_unknown']) ?> / <?= stats_number($source['lines_seen']) ?></td><td class="stats-numeric"><?= stats_number($source['discontinuities']) ?></td></tr><?php endforeach; ?>
            </tbody></table></div>
        </section>
        <?php endif; ?>
        <section class="stats-panel" aria-labelledby="warnings-title"><details><summary id="warnings-title">Interpretation &amp; limitations</summary><ul><?php foreach ($snapshot['warnings'] as $warning): ?><li><?= mail_stats_escape($warning) ?></li><?php endforeach; ?></ul></details></section>
        <?php if (!$addressView): ?>
        <section class="stats-panel" aria-labelledby="export-title">
            <h2 id="export-title">Export PDF</h2>
            <form method="post" action="/stats/export.php" class="stats-export">
                <?php $exportFields = $formFields; unset($exportFields['report']); mail_stats_hidden($exportFields + ['csrf' => $csrf]); ?>
                <label>Report<select class="form-control" name="report" aria-label="Report"><option value="summary">Shareable summary (identities masked)</option><option value="diagnostic">Detailed diagnostic (maximum 1,000 events)</option></select></label>
                <label class="stats-check"><input type="checkbox" name="include_nominal" value="1"> Include addresses, IPs and account details in diagnostic only</label>
                <button class="btn btn-default" type="submit">Export PDF</button>
            </form>
            <p class="help-block">The full selected period is exported, not just this page. Oversized reports are refused, not silently truncated. Downloaded PDFs are not removed by server retention. Secrets remain excluded.</p>
        </section>
        <?php endif; ?>
        <?php endif; ?>
    </main>
    <footer class="admin-footer"><a href="/">Back to administration</a><span>No live queue operations. No message contents.</span></footer>
</div>
</body>
</html>
