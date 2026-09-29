<?php
declare(strict_types=1);
require '/var/www/admin/lib/mail-stats.php';
if (!is_file('/.dockerenv') || getenv('MAIL_STATS_WEB_FIXTURE') !== '1') throw new RuntimeException('Disposable test container required.');

if (str_starts_with($argv[1] ?? '', 'boot-')) {
    $case = $argv[1];
    $_SERVER['REQUEST_METHOD'] = 'GET';
    if ($case !== 'boot-anonymous') {
        $_SERVER['AUTH_TYPE'] = 'Session';
        $_SERVER['REMOTE_USER'] = 'synthetic-admin';
    }
    if ($case === 'boot-get-nominal') $_GET['address'] = 'private@example.invalid';
    if ($case === 'boot-method') $_SERVER['REQUEST_METHOD'] = 'PUT';
    if ($case === 'boot-size') $_SERVER['CONTENT_LENGTH'] = '20000';
    if (in_array($case, ['boot-csrf', 'boot-valid-post'], true)) {
        @mkdir('/run/sqmail-admin', 0700, true);
        session_name('__Host-sqmail-login');
        session_save_path('/run/sqmail-admin');
        session_start();
        $_SESSION['csrf'] = str_repeat('a', 64);
        $sessionId = session_id();
        session_write_close();
        session_id($sessionId);
        $_SERVER['REQUEST_METHOD'] = 'POST';
        $_POST['csrf'] = $case === 'boot-valid-post' ? str_repeat('a', 64) : 'wrong';
    }
    mail_stats_boot();
    echo 'BOOT-ACCEPTED';
    exit;
}

function check(bool $condition, string $message): void
{
    if (!$condition) throw new RuntimeException($message);
    echo 'PASS ' . $message . "\n";
}

function rejects(callable $operation, string $class, string $message): void
{
    try { $operation(); } catch (Throwable $error) { check($error instanceof $class, $message); return; }
    throw new RuntimeException('Expected rejection: ' . $message);
}

check(mail_stats_filters([])['view'] === 'overview', 'default view');
check(!isset(MAIL_STATS_VIEWS['search']), 'Search is not an allowed view');
rejects(fn() => mail_stats_snapshot(['view' => 'search']), InvalidArgumentException::class, 'obsolete Search view rejected before database access');
check(mail_stats_filters(['start' => '2024-02-29T12:34'])['start'] === '2024-02-29 12:34:00.000000', 'UTC leap date');
foreach ([['start' => '2025-02-29T12:34'], ['address' => ['bad']], ['queue' => '1 OR 1=1'], ['source' => "x' OR 1=1"], ['ip' => 'invalid'], ['cursor_id' => '2'], ['account' => "a\nb"], ['view' => '<script>']] as $invalid) {
    rejects(fn() => mail_stats_filters($invalid), InvalidArgumentException::class, 'invalid filter rejected');
}
check(mail_stats_escape('<script>"&') === '&lt;script&gt;&quot;&amp;', 'HTML injection escaped');
check(!str_contains(mail_stats_redact('SRS0=SECRET=user@example.invalid token=secret'), 'SECRET'), 'SRS redacted');
check(!str_contains(mail_stats_redact('password=unsafe'), 'unsafe'), 'secret assignment redacted');
foreach (['boot-anonymous' => 'Authenticated portal session required.', 'boot-get-nominal' => 'Use the protected POST form', 'boot-method' => 'Method not allowed.', 'boot-size' => 'Request exceeds', 'boot-csrf' => 'invalid CSRF token', 'boot-valid-post' => 'BOOT-ACCEPTED'] as $case => $expected) {
    $child = proc_open(['/usr/bin/php8.5', __FILE__, $case], [0 => ['pipe', 'r'], 1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes);
    fclose($pipes[0]);
    $output = stream_get_contents($pipes[1]);
    $stderr = stream_get_contents($pipes[2]);
    fclose($pipes[1]); fclose($pipes[2]);
    check(proc_close($child) === 0 && str_contains($output, $expected) && $stderr === '', $case);
}

if (($argv[1] ?? '') === 'unit') exit(0);
@mkdir('/run/mail-stats', 0755, true);
@mkdir('/var/qmail/control/aio-conf', 0755, true);
$config = ['enabled' => true, 'history_months' => 6, 'instance_id' => str_repeat('a', 32), 'reason' => ''];
file_put_contents('/run/mail-stats/web.json', json_encode($config));
file_put_contents('/var/qmail/control/aio-conf/mysql.php', '<?php $MYSQL_CONF=' . var_export(['MYSQL_HOST' => 'db', 'MYSQL_USER' => 'stats', 'MYSQL_PASS' => 'SyntheticStatsWeb927', 'MYSQL_DB' => 'stats'], true) . ';');
$deadline = microtime(true) + 120;
do {
    try { $db = mail_stats_connect(); break; } catch (Throwable $error) { if (microtime(true) > $deadline) throw $error; sleep(1); }
} while (true);
if (($argv[1] ?? '') === 'budget') {
    $started = hrtime(true);
    rejects(fn() => mail_stats_select($db, 'SELECT SLEEP(2)', [], $started - 1), RuntimeException::class, 'expired deadline refuses SQL before execution');
    check((hrtime(true) - $started) < 500000000, 'expired deadline returns immediately');
    $deadline = hrtime(true) + 250000000;
    mail_stats_select($db, 'SELECT SLEEP(0.12)', [], $deadline);
    try {
        mail_stats_select($db, 'SELECT SLEEP(2)', [], $deadline);
        throw new LogicException('Expected query interruption');
    } catch (mysqli_sql_exception | RuntimeException $error) {
        check(!$error instanceof LogicException, 'remaining cumulative budget interrupts second query');
    }
    check(hrtime(true) < $deadline + 1000000000, 'cumulative deadline does not reset per statement');
    $db->close();
    exit;
}
$db->multi_query(file_get_contents('/opt/sql/mail-stats.sql'));
do { if ($result = $db->store_result()) $result->free(); } while ($db->more_results() && $db->next_result());
$db->query('INSERT INTO mail_stats_schema VALUES (1,1,UTC_TIMESTAMP(6))');
$instance = $config['instance_id'];
foreach ([['qmail-send', 'transport', 'active'], ['dovecot', 'dovecot', 'unavailable'], ['retention', 'maintenance', 'active']] as [$source, $family, $status]) {
    $db->execute_query('INSERT INTO mail_stats_sources (instance_id,source_key,family,status,coverage,first_seen_at,last_success_at) VALUES (?,?,?,?,?,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))', [$instance, $source, $family, $status, 'partial']);
}
$db->execute_query('INSERT INTO mail_stats_sources (instance_id,source_key,family,status,coverage,first_seen_at) VALUES (?,?,?,?,?,UTC_TIMESTAMP(6))', [str_repeat('b', 32), 'qmail-send', 'transport', 'active', 'complete']);
for ($n = 1; $n <= 2; $n++) {
    $db->execute_query('INSERT INTO mail_stats_messages (instance_id,source_id,generation,queue_id,started_at,last_event_at,sender,bytes) VALUES (?,1,?,?,UTC_TIMESTAMP(6)-INTERVAL 1 DAY,UTC_TIMESTAMP(6),?,100)', [$instance, 'generation-' . $n, '123', 'sender@example.invalid']);
}
$eventSql = 'INSERT INTO mail_stats_events (instance_id,source_id,source_position,message_id,event_at,observed_at,component,event_type,severity,parser,parser_version,queue_id,sender,recipient,ip,account,metadata) VALUES (?,?,?,?,UTC_TIMESTAMP(6)-INTERVAL 1 HOUR,UTC_TIMESTAMP(6),?,?,?,?,1,?,?,?,?,?,?)';
for ($n = 1; $n <= 105; $n++) {
    $db->execute_query($eventSql, [$instance, 1, 'event-' . $n, $n % 2 + 1, 'qmail-send', 'delivery_local_success', 'info', 'fixture', '123', 'sender@example.invalid', 'recipient@example.invalid', '192.0.2.1', 'test-account', '{"reason_code":"synthetic"}']);
}
$db->execute_query($eventSql, [str_repeat('b', 32), 4, 'other-instance', null, 'qmail-send', 'private_other_instance', 'info', 'fixture', '999', 'private@example.invalid', null, null, null, '{}']);
$db->execute_query($eventSql, [$instance, 1, 'expired', null, 'qmail-send', 'expired_event', 'info', 'fixture', '999', 'expired@example.invalid', null, null, null, '{}']);
$db->query("UPDATE mail_stats_events SET event_at=UTC_TIMESTAMP(6)-INTERVAL 7 MONTH WHERE source_position='expired'");
$overview = mail_stats_snapshot([]);
check($overview['events'] === [] && $overview['next_cursor'] === null, 'overview avoids retrieving log detail pages');
check(isset($overview['rankings']['senders'], $overview['rankings']['traffic_domains']), 'overview returns bounded aggregate rankings');
$snapshot = mail_stats_snapshot(['view' => 'transport']);
check(count($snapshot['events']) === 100 && $snapshot['next_cursor'] !== null, '100 event page and cursor');
check(count(mail_stats_snapshot(['view' => 'sources'])['sources']) === 3, 'all selected registry sources including unavailable');
check(count(mail_stats_snapshot(['view' => 'transport'])['sources']) === 1, 'family filter selects registered transport sources');
check(!mail_stats_snapshot(['view' => 'dovecot', 'source' => 'dovecot'])['events'], 'unavailable source has no invented events');
check(!mail_stats_snapshot(['view' => 'maintenance', 'component' => 'freshclam'])['events'], 'component filter excludes unrelated maintenance events');
check(count($snapshot['counts']) === 1 && (int) $snapshot['counts'][0]['count'] === 105, 'instance and retention scoped counts');
check((int) $snapshot['messages_count'] === 2 && (int) $snapshot['messages_bytes'] === 200, 'distinct messages not retry counts');
check(!$snapshot['purge_delayed'], 'recent retention heartbeat');
$next = mail_stats_snapshot($snapshot['next_cursor'] + ['view' => 'transport', 'start' => $snapshot['start'], 'end' => $snapshot['end']]);
check(count($next['events']) === 5 && $next['next_cursor'] === null, 'cursor second page');
check(!array_intersect(array_column($snapshot['events'], 'id'), array_column($next['events'], 'id')), 'cursor pages do not overlap');
$queue = mail_stats_snapshot(['view' => 'transport', 'queue' => '123']);
check(count($queue['occurrences']) === 2, 'queue reuse produces separate historical occurrences');
$timeline = mail_stats_snapshot(['view' => 'transport', 'message' => '1']);
check(count(array_unique(array_column($timeline['events'], 'message_id'))) === 1, 'message timeline scoped');
$injection = mail_stats_snapshot(['view' => 'transport', 'address' => "' OR 1=1 --"]);
check(!$injection['events'] && !$injection['counts'], 'prepared exact address prevents SQL injection');
check(count(mail_stats_snapshot(['view' => 'transport', 'account' => 'test-account', 'ip' => '192.0.2.1'])['events']) === 100, 'exact IP and account filters');
check(!mail_stats_snapshot(['view' => 'transport', 'account' => 'TEST-ACCOUNT'])['events'], 'binary exact account comparison');
$summary = mail_stats_snapshot(['address' => 'sender@example.invalid'], true, true);
check($summary['masked'] && $summary['filters']['address'] === '[masked]' && !$summary['events'], 'summary is always masked');
$diagnostic = mail_stats_snapshot(['report' => 'diagnostic'], true);
check(count($diagnostic['events']) === 105 && $diagnostic['events'][0]['sender'] === '[masked]', 'diagnostic default masking and full period');
$nominal = mail_stats_snapshot(['report' => 'diagnostic'], true, true);
check($nominal['events'][0]['sender'] === 'sender@example.invalid', 'explicit diagnostic identity inclusion');
$old = mail_stats_snapshot(['start' => '2000-01-01T00:00']);
check($old['start'] === $old['retention_cutoff'], 'old date clipped to SQL calendar cutoff');
$db->query("UPDATE mail_stats_events SET metadata='{\"reason_code\":\"<script>alert(1)</script>\"}' WHERE source_position='event-105'");
$render = proc_open(['/usr/bin/php8.5', '-r', '$_SERVER["REQUEST_METHOD"]="GET"; $_SERVER["AUTH_TYPE"]="Session"; $_SERVER["REMOTE_USER"]="synthetic-admin"; $_GET["view"]="transport"; require "/var/www/admin/html/stats/index.php";'], [0 => ['pipe', 'r'], 1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes);
fclose($pipes[0]);
$html = stream_get_contents($pipes[1]);
$stderr = stream_get_contents($pipes[2]);
fclose($pipes[1]); fclose($pipes[2]);
check(proc_close($render) === 0 && $stderr === '', 'portal HTML renders without PHP errors');
check(!str_contains($html, '>Search</a>') && !str_contains($html, 'Inspect matching events') && !str_contains($html, 'view=search') && !str_contains($html, 'value="search"'), 'portal has no Search tab or action');
check(str_contains($html, '&lt;script&gt;alert(1)&lt;/script&gt;') && !str_contains($html, '<script>'), 'stored diagnostic XSS escaped in actual portal');
check(str_contains($html, 'action="/stats/export.php"') && str_contains($html, 'name="csrf"') && str_contains($html, 'name="cursor_id"'), 'export and pagination use protected POST forms');
$config['history_months'] = 120;
file_put_contents('/run/mail-stats/web.json', json_encode($config));
check(mail_stats_snapshot(['start' => '2000-01-01T00:00'])['granularity'] === 'month', 'long history aggregates monthly');
for ($n = 106; $n <= 1001; $n++) {
    $db->execute_query($eventSql, [$instance, 1, 'event-' . $n, 1, 'qmail-send', 'delivery_local_success', 'info', 'fixture', '123', 'sender@example.invalid', null, null, null, '{}']);
}
rejects(fn() => mail_stats_snapshot(['report' => 'diagnostic'], true), LengthException::class, '1001-event export refused explicitly');
foreach (['queue' => [' AND e.queue_id=?', ['123']], 'address' => [' AND (e.sender=? OR e.recipient=?)', ['sender@example.invalid', 'sender@example.invalid']], 'series' => ['', []]] as $name => [$predicate, $extra]) {
    $projection = $name === 'series' ? "DATE_FORMAT(e.event_at,'%Y-%m-%d') AS bucket,COUNT(*) AS count" : 'e.id';
    $order = $name === 'series' ? ' GROUP BY bucket ORDER BY bucket LIMIT 367' : ' ORDER BY e.event_at DESC,e.id DESC LIMIT 101';
    $plan = mail_stats_select($db, 'EXPLAIN SELECT ' . $projection . ' FROM mail_stats_events e JOIN mail_stats_sources s ON s.id=e.source_id AND s.instance_id=e.instance_id WHERE s.instance_id=? AND e.instance_id=? AND e.event_at>=UTC_TIMESTAMP(6)-INTERVAL 6 MONTH' . $predicate . $order, [$instance, $instance, ...$extra]);
    $eventPlan = array_values(array_filter($plan, static fn(array $row): bool => $row['table'] === 'e'))[0];
    check($eventPlan['key'] !== null && $eventPlan['type'] !== 'ALL', 'indexed query plan: ' . $name);
    echo 'EXPLAIN ' . $name . ': ' . $eventPlan['key'] . ' / ' . $eventPlan['type'] . "\n";
}
$db->execute_query('UPDATE mail_stats_events SET metadata=? WHERE source_position=?', [str_repeat('x', 5000), 'event-1001']);
rejects(fn() => mail_stats_snapshot(['view' => 'transport']), LengthException::class, 'oversized metadata refused without silent truncation');
$config['enabled'] = false;
$config['reason'] = 'Invalid history setting';
file_put_contents('/run/mail-stats/web.json', json_encode($config));
rejects(fn() => mail_stats_snapshot([]), RuntimeException::class, 'disabled component fails closed before SQL');
$config['enabled'] = true;
file_put_contents('/run/mail-stats/web.json', json_encode($config));
$db->query('DELETE FROM mail_stats_schema');
rejects(fn() => mail_stats_snapshot([]), RuntimeException::class, 'missing schema refused');
$db->close();
echo "All disposable PHP query tests passed.\n";
