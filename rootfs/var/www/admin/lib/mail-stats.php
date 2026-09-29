<?php
declare(strict_types=1);

const MAIL_STATS_VIEWS = ['overview' => 'Overview', 'transport' => 'Transport / SMTP', 'dovecot' => 'Dovecot', 'filtering' => 'Antispam / antivirus', 'web' => 'Web / admin', 'maintenance' => 'Maintenance', 'sources' => 'Source status'];
const MAIL_STATS_ADDRESS_VIEWS = ['senders' => 'All envelope senders', 'recipients' => 'All recorded recipients'];

function mail_stats_escape(mixed $value): string
{
    return htmlspecialchars((string) $value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function mail_stats_boot(): void
{
    ini_set('display_errors', '0');
    header('Cache-Control: no-store');
    header('Content-Type: text/html; charset=UTF-8');
    header("Content-Security-Policy: default-src 'none'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'");
    header('X-Content-Type-Options: nosniff');
    header('Referrer-Policy: no-referrer');
    if (($_SERVER['AUTH_TYPE'] ?? '') !== 'Session' || !is_string($_SERVER['REMOTE_USER'] ?? null) || $_SERVER['REMOTE_USER'] === '') {
        http_response_code(403);
        exit('Authenticated portal session required.');
    }
    if (!in_array($_SERVER['REQUEST_METHOD'] ?? '', ['GET', 'POST'], true)) {
        header('Allow: GET, POST');
        http_response_code(405);
        exit('Method not allowed.');
    }
    $body = fopen('php://input', 'rb');
    if ((int) ($_SERVER['CONTENT_LENGTH'] ?? 0) > 16384 || $body === false || strlen((string) stream_get_contents($body, 16385)) > 16384) {
        http_response_code(413);
        exit('Request exceeds the 16 KiB limit.');
    }
    fclose($body);
    // Only navigation is accepted in URLs; nominal data must never enter access logs.
    if (array_diff(array_keys($_GET), ['view'])) {
        http_response_code(400);
        exit('Use the protected POST form for filters.');
    }
    session_name('__Host-sqmail-login');
    session_save_path('/run/sqmail-admin/');
    ini_set('session.use_strict_mode', '1');
    ini_set('session.gc_maxlifetime', '3600');
    session_set_cookie_params(['path' => '/', 'secure' => true, 'httponly' => true, 'samesite' => 'Strict']);
    if (!session_start()) throw new RuntimeException('Session unavailable.');
    $_SESSION['csrf'] ??= bin2hex(random_bytes(32));
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && (!is_string($_POST['csrf'] ?? null) || !hash_equals($_SESSION['csrf'], $_POST['csrf']))) {
        http_response_code(403);
        exit('Session expired or invalid CSRF token. Reload the page.');
    }
}

function mail_stats_config(): array
{
    $raw = @file_get_contents('/run/mail-stats/web.json');
    $config = $raw === false ? null : json_decode($raw, true);
    if (!is_array($config) || !is_bool($config['enabled'] ?? null)) throw new RuntimeException('Statistics configuration unavailable.');
    if (!$config['enabled']) {
        $reason = is_string($config['reason'] ?? null) ? mail_stats_redact(substr($config['reason'], 0, 512)) : 'Configuration unavailable';
        throw new RuntimeException('Statistics are disabled or unavailable. Collection and retention purge are stopped. ' . $reason);
    }
    if (!is_int($config['history_months'] ?? null) || $config['history_months'] < 1 || $config['history_months'] > 120 || !is_string($config['instance_id'] ?? null) || !preg_match('/\A[a-f0-9]{32}\z/D', $config['instance_id'])) {
        throw new RuntimeException('Statistics configuration unavailable.');
    }
    return $config;
}

function mail_stats_filters(array $input): array
{
    $fields = ['view', 'start', 'end', 'source', 'component', 'type', 'severity', 'address', 'queue', 'ip', 'account', 'message', 'cursor_at', 'cursor_id', 'report', 'rank_by', 'cursor_metric', 'cursor_identity', 'cursor_rank_by'];
    $result = array_fill_keys($fields, '');
    foreach ($fields as $field) {
        if (!array_key_exists($field, $input)) continue;
        if (!is_string($input[$field]) || strlen($input[$field]) > 320 || preg_match('/[\x00-\x1f\x7f]/', $input[$field])) throw new InvalidArgumentException('Invalid filter.');
        $result[$field] = trim($input[$field]);
    }
    $result['view'] = $result['view'] ?: 'overview';
    $result['report'] = $result['report'] ?: 'summary';
    $result['rank_by'] = $result['rank_by'] ?: 'messages';
    if (!in_array($result['rank_by'], ['messages', 'bytes'], true)) throw new InvalidArgumentException('Invalid ranking order.');
    if (!isset((MAIL_STATS_VIEWS + MAIL_STATS_ADDRESS_VIEWS)[$result['view']]) || !in_array($result['report'], ['summary', 'diagnostic'], true)) throw new InvalidArgumentException('Invalid view or report.');
    $hasCursor = $result['cursor_metric'] !== '' || $result['cursor_identity'] !== '' || $result['cursor_rank_by'] !== '';
    if ($hasCursor && (!isset(MAIL_STATS_ADDRESS_VIEWS[$result['view']]) || !preg_match('/\A(?:0|[1-9][0-9]{0,64})\z/D', $result['cursor_metric']) || $result['cursor_identity'] === '' || $result['cursor_identity'] !== ($input['cursor_identity'] ?? '') || $result['cursor_rank_by'] !== $result['rank_by'])) throw new InvalidArgumentException('Invalid address cursor. Return to the first page.');
    foreach (['source', 'component', 'type', 'severity'] as $field) {
        if ($result[$field] !== '' && !preg_match('/\A[a-zA-Z0-9_.:-]{1,96}\z/D', $result[$field])) throw new InvalidArgumentException('Invalid source, type or severity.');
    }
    foreach (['message', 'cursor_id', 'queue'] as $field) {
        if ($result[$field] !== '' && !preg_match('/\A[0-9]{1,20}\z/D', $result[$field])) throw new InvalidArgumentException('Identifiers must be decimal numbers.');
    }
    if ($result['ip'] !== '' && filter_var($result['ip'], FILTER_VALIDATE_IP) === false) throw new InvalidArgumentException('Enter an exact IPv4 or IPv6 address.');
    foreach (['start', 'end', 'cursor_at'] as $field) {
        if ($result[$field] === '') continue;
        $value = str_replace('T', ' ', $result[$field]);
        if (strlen($value) === 16) $value .= ':00';
        if (strlen($value) === 19) $value .= '.000000';
        $date = DateTimeImmutable::createFromFormat('!Y-m-d H:i:s.u', $value, new DateTimeZone('UTC'));
        if (!$date || $date->format('Y-m-d H:i:s.u') !== $value) throw new InvalidArgumentException('Invalid UTC date.');
        $result[$field] = $value;
    }
    if (($result['cursor_at'] === '') !== ($result['cursor_id'] === '')) throw new InvalidArgumentException('Invalid event cursor.');
    return $result;
}

function mail_stats_connect(): mysqli
{
    $MYSQL_CONF = [];
    if (!is_readable('/var/qmail/control/aio-conf/mysql.php')) throw new RuntimeException('Statistics database configuration unavailable.');
    require '/var/qmail/control/aio-conf/mysql.php';
    mysqli_report(MYSQLI_REPORT_ERROR | MYSQLI_REPORT_STRICT);
    $db = mysqli_init();
    $db->options(MYSQLI_OPT_CONNECT_TIMEOUT, 3);
    $db->options(MYSQLI_OPT_READ_TIMEOUT, 8);
    $db->real_connect($MYSQL_CONF['MYSQL_HOST'], $MYSQL_CONF['MYSQL_USER'], $MYSQL_CONF['MYSQL_PASS'], $MYSQL_CONF['MYSQL_DB']);
    $db->set_charset('utf8mb4');
    $db->query("SET time_zone = '+00:00'");
    $db->query('SET SESSION lock_wait_timeout = 3');
    $db->query(str_contains($db->server_info, 'MariaDB') ? 'SET SESSION max_statement_time = 5' : 'SET SESSION max_execution_time = 5000');
    return $db;
}

function mail_stats_select(mysqli $db, string $sql, array $params = [], ?int $deadline = null): array
{
    if ($deadline !== null) {
        $milliseconds = min(5000, (int) (($deadline - hrtime(true)) / 1000000));
        if ($milliseconds < 1) throw new RuntimeException('Statistics query budget exceeded. Narrow the period or filters.');
        $db->query(str_contains($db->server_info, 'MariaDB')
            ? 'SET SESSION max_statement_time = ' . number_format($milliseconds / 1000, 3, '.', '')
            : 'SET SESSION max_execution_time = ' . $milliseconds);
    }
    $rows = $db->execute_query($sql, $params)->fetch_all(MYSQLI_ASSOC);
    if ($deadline !== null && hrtime(true) >= $deadline) throw new RuntimeException('Statistics query budget exceeded. Narrow the period or filters.');
    return $rows;
}

function mail_stats_redact(string $value): string
{
    $value = preg_replace('/[\x00-\x1f\x7f]/', ' ', $value);
    $value = preg_replace('/SRS[01][=+\-][^\s<>"\x27]+/i', '[SRS redacted]', $value);
    return preg_replace('/\b(password|passwd|token|secret|authorization|cookie)\s*[:=]\s*[^\s,;}]+/i', '$1=[redacted]', $value);
}

/** A frozen, bounded result; no database transaction survives this call. */
function mail_stats_snapshot(array $filters, bool $export = false, bool $includeNominal = false): array
{
    $filters = mail_stats_filters($filters);
    if ($export) foreach (['cursor_metric', 'cursor_identity', 'cursor_rank_by'] as $field) $filters[$field] = '';
    $addressView = !$export && isset(MAIL_STATS_ADDRESS_VIEWS[$filters['view']]);
    $config = mail_stats_config();
    $db = null;
    $transaction = false;
    // Aggregate LIMITs bound returned rows, not scanned work. Share one SQL budget.
    $deadline = hrtime(true) + 10000000000;
    try {
        $db = mail_stats_connect();
        $select = static fn(string $sql, array $params = []): array => mail_stats_select($db, $sql, $params, $deadline);
        $db->query('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ');
        $db->query('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY');
        $transaction = true;
        $version = $select('SELECT version FROM mail_stats_schema WHERE id = ?', [1]);
        if (($version[0]['version'] ?? null) != 1) throw new RuntimeException('Statistics schema unavailable.');
        $clock = $select('SELECT UTC_TIMESTAMP(6) AS now_at, UTC_TIMESTAMP(6) - INTERVAL ? MONTH AS cutoff', [$config['history_months']])[0];
        $end = min($filters['end'] ?: $clock['now_at'], $clock['now_at']);
        $defaultStart = (new DateTimeImmutable($end, new DateTimeZone('UTC')))->modify('-7 days')->format('Y-m-d H:i:s.u');
        $start = max($filters['start'] ?: $defaultStart, $clock['cutoff']);
        if ($end <= $start) throw new InvalidArgumentException('Select a nonempty period inside the retained UTC history.');
        $sourceWhere = ['s.instance_id = ?'];
        $sourceParams = [$config['instance_id']];
        if (in_array($filters['view'], ['transport', 'dovecot', 'filtering', 'web', 'maintenance'], true)) {
            $sourceWhere[] = 's.family = ?';
            $sourceParams[] = $filters['view'];
        }
        if ($filters['source'] !== '') {
            $sourceWhere[] = 's.source_key = ?';
            $sourceParams[] = $filters['source'];
        }
        $sourceSql = implode(' AND ', $sourceWhere);
        $sources = $select('SELECT s.source_key,s.family,s.status,s.coverage,s.reason_code,s.first_seen_at,s.last_observed_at,s.last_success_at,s.last_event_at,s.lag_seconds,s.lines_seen,s.lines_unknown,s.discontinuities FROM mail_stats_sources s WHERE ' . $sourceSql . ' ORDER BY s.family,s.source_key LIMIT 257', $sourceParams);
        if (count($sources) > 256) throw new LengthException('Too many sources. Narrow the source filter.');
        $purge = $select('SELECT last_success_at FROM mail_stats_sources WHERE instance_id=? AND source_key=? LIMIT 1', [$config['instance_id'], 'retention']);
        $purgeAt = $purge[0]['last_success_at'] ?? null;
        $staleAt = (new DateTimeImmutable($clock['now_at'], new DateTimeZone('UTC')))->modify('-5 minutes')->format('Y-m-d H:i:s.u');
        $purgeDelayed = $purgeAt === null || $purgeAt < $staleAt;
        // Keep the raw recipient for attempt provenance and legacy exact searches.
        // Strip one byte-exact domain prefix only for evidenced local qmail delivery;
        // neither domain nor local-part case is folded by this identity transform.
        $rawDomain = "SUBSTRING_INDEX(raw.recipient,'@',-1)";
        $rawLocal = "SUBSTRING_INDEX(raw.recipient,'@',1)";
        $localEvidence = "(raw.event_type='delivery_local_success' OR (raw.event_type IN ('attempt_started','delivery_success','delivery_failure','delivery_deferral') AND CAST(JSON_UNQUOTE(JSON_EXTRACT(CASE WHEN JSON_VALID(raw.metadata) THEN raw.metadata ELSE '{}' END,'$.delivery_kind')) AS BINARY)='local'))";
        $canonical = "CASE WHEN origin.source_key='qmail-send' AND raw.component='qmail-send' AND $localEvidence"
            . " AND OCTET_LENGTH(raw.recipient)-OCTET_LENGTH(REPLACE(raw.recipient,'@',''))=1"
            . " AND OCTET_LENGTH($rawDomain)>0 AND OCTET_LENGTH($rawLocal)>OCTET_LENGTH($rawDomain)+1"
            . " AND LEFT($rawLocal,OCTET_LENGTH($rawDomain)+1)=CAST(CONCAT($rawDomain,'-') AS BINARY)"
            . " THEN SUBSTRING(raw.recipient,OCTET_LENGTH($rawDomain)+2) ELSE raw.recipient END";
        $eventTable = '(SELECT raw.*,' . $canonical . ' AS display_recipient FROM mail_stats_events raw JOIN mail_stats_sources origin ON origin.id=raw.source_id AND origin.instance_id=raw.instance_id)';
        $where = [$sourceSql, 'e.instance_id = ?', 'e.event_at >= ?', 'e.event_at < ?'];
        $params = [...$sourceParams, $config['instance_id'], $start, $end];
        foreach (['component' => 'component', 'type' => 'event_type', 'severity' => 'severity', 'queue' => 'queue_id', 'ip' => 'ip', 'account' => 'account', 'message' => 'message_id'] as $field => $column) {
            if ($filters[$field] !== '') {
                $where[] = 'e.' . $column . ' = ?';
                $params[] = $filters[$field];
            }
        }
        if ($filters['address'] !== '') {
            $where[] = '(e.sender = ? OR e.recipient = ? OR e.display_recipient = ?)';
            array_push($params, $filters['address'], $filters['address'], $filters['address']);
        }
        $from = ' FROM ' . $eventTable . ' e JOIN mail_stats_sources s ON s.id=e.source_id AND s.instance_id=e.instance_id WHERE ' . implode(' AND ', $where);
        $counts = $addressView ? [] : $select('SELECT e.event_type,COUNT(*) AS count' . $from . ' GROUP BY e.event_type ORDER BY count DESC,e.event_type LIMIT 129', $params);
        if (count($counts) > 128) throw new LengthException('Too many event categories. Narrow the filters.');
        if ($export && count($counts) > 50) throw new LengthException('The report exceeds 50 categories. Narrow the filters; no partial PDF was generated.');
        $days = (new DateTimeImmutable(substr($start, 0, 10)))->diff(new DateTimeImmutable(substr($end, 0, 10)))->days + 1;
        $granularity = $days > 366 ? 'month' : 'day';
        $format = $granularity === 'month' ? '%Y-%m' : '%Y-%m-%d';
        $series = $addressView ? [] : $select("SELECT DATE_FORMAT(e.event_at, '$format') AS bucket,COUNT(*) AS count" . $from . ' GROUP BY bucket ORDER BY bucket LIMIT 367', $params);
        if (count($series) > 366) throw new LengthException('Too many chart points. Narrow the period.');
        // Only proven message links count here, never SMTP observations or retries.
        $messageTotals = $addressView ? ['count' => null, 'bytes' => null] : $select('SELECT COUNT(*) AS count,COALESCE(SUM(m.bytes),0) AS bytes FROM mail_stats_messages m WHERE m.instance_id=? AND m.started_at>=? AND m.started_at<? AND EXISTS (SELECT 1' . $from . ' AND e.message_id=m.id) LIMIT 1', [$config['instance_id'], $clock['cutoff'], $end, ...$params])[0];
        // Conservative ASCII dot-atom identities only. Exclude secrets before grouping,
        // rather than collapsing unrelated senders into one redacted identity.
        $atom = '[A-Za-z0-9!#$%&\'*+/=?^_`{|}~-]+';
        $addressPattern = str_replace("'", "''", '^' . $atom . '([.]' . $atom . ')*@[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?([.][A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$');
        $safeIdentity = static function (string $column) use ($addressPattern): string {
            $text = "CAST($column AS CHAR CHARACTER SET utf8mb4)";
            // Equivalent to mail_stats_redact for the admitted ASCII grammar:
            // no whitespace/colon/comma/semicolon, and apostrophe stops SRS tokens.
            $sensitive = str_replace("'", "''", "srs[01][=+-][^']|(^|[^A-Za-z0-9_])(password|passwd|token|secret|authorization|cookie)=[^}]");
            return "$text REGEXP '$addressPattern' AND OCTET_LENGTH(SUBSTRING_INDEX($column,'@',1))<=64 AND OCTET_LENGTH(SUBSTRING_INDEX($column,'@',-1))<=253 AND LOWER($text) NOT REGEXP '$sensitive'";
        };
        $order = $filters['rank_by'] === 'bytes' ? 'bytes' : 'messages';
        $totals = 'COUNT(*) AS messages,COALESCE(SUM(bytes),0) AS bytes,COUNT(bytes) AS known_size_messages';
        $retained = 'm.instance_id=? AND m.started_at>=? AND m.started_at<?';
        $retainedParams = [$config['instance_id'], $clock['cutoff'], $end];
        $rankings = [];
        $addressList = ['rows' => [], 'next_cursor' => null];
        $addressAggregate = static function (string $kind, string $sql, array $bindings) use ($select, $filters, $addressView, $order, &$rankings, &$addressList): void {
            if ($addressView && $filters['view'] !== $kind) return;
            if ($addressView && $filters['cursor_metric'] !== '') {
                // Explicit decimal operands avoid floating-point conversion of SUM(BIGINT).
                $sql = 'SELECT * FROM (' . $sql . ') addresses WHERE (' . $order . ' < CAST(? AS DECIMAL(65,0)) OR (' . $order . ' = CAST(? AS DECIMAL(65,0)) AND identity > CAST(? AS BINARY)))';
                array_push($bindings, $filters['cursor_metric'], $filters['cursor_metric'], $filters['cursor_identity']);
            }
            $rows = $select($sql . ' ORDER BY ' . $order . ' DESC,identity ASC LIMIT ' . ($addressView ? '51' : '10'), $bindings);
            if (!$addressView) { $rankings[$kind] = $rows; return; }
            if (count($rows) > 50) {
                array_pop($rows);
                $last = $rows[array_key_last($rows)];
                $addressList['next_cursor'] = ['cursor_metric' => (string) $last[$order], 'cursor_identity' => $last['identity'], 'cursor_rank_by' => $order];
            }
            $addressList['rows'] = $rows;
        };
        $addressAggregate('senders', 'SELECT m.sender AS identity,COUNT(*) AS messages,COALESCE(SUM(m.bytes),0) AS bytes,COUNT(m.bytes) AS known_size_messages FROM mail_stats_messages m WHERE ' . $retained . ' AND ' . $safeIdentity('m.sender') . ' AND EXISTS (SELECT 1' . $from . ' AND e.message_id=m.id) GROUP BY m.sender', [...$retainedParams, ...$params]);
        // A recipient observation alone is not proof of a delivery attempt. Both
        // parent links and their instance/retention boundaries must still hold.
        $linked = $from . ' AND EXISTS (SELECT 1 FROM mail_stats_attempts a WHERE a.id=e.attempt_id AND a.instance_id=e.instance_id AND a.message_id=e.message_id AND a.recipient=e.recipient AND a.started_at>=? AND a.started_at<?)';
        $linkedParams = [...$params, $clock['cutoff'], $end];
        $domain = 'CAST(LOWER(CAST(SUBSTRING_INDEX(e.recipient,\'@\',-1) AS CHAR CHARACTER SET utf8mb4)) AS BINARY)';
        foreach (['recipients' => 'e.display_recipient', 'error_domains' => $domain] as $kind => $identity) {
            if ($addressView && $kind !== $filters['view']) continue;
            $errors = $kind === 'error_domains';
            $projection = $errors
                ? ",MAX(e.event_type='delivery_failure') AS failed,MAX(e.event_type='delivery_deferral') AS deferred"
                : '';
            $matches = 'SELECT e.message_id,' . $identity . ' AS identity' . $projection . $linked . ' AND ' . $safeIdentity('e.display_recipient')
                . ($errors ? " AND e.event_type IN ('delivery_failure','delivery_deferral')" : '') . ' GROUP BY e.message_id,identity';
            $rows = 'SELECT r.*,m.bytes FROM (' . $matches . ') r JOIN mail_stats_messages m ON m.id=r.message_id WHERE ' . $retained;
            $aggregate = $errors ? 'SUM(failed) AS failed_messages,SUM(deferred) AS deferred_messages,COUNT(*) AS affected_messages' : $totals;
            $aggregateSql = 'SELECT identity,' . $aggregate . ' FROM (' . $rows . ') ranked GROUP BY identity';
            if ($errors) $rankings[$kind] = $select($aggregateSql . ' ORDER BY affected_messages DESC,identity ASC LIMIT 10', [...$linkedParams, ...$retainedParams]);
            else $addressAggregate($kind, $aggregateSql, [...$linkedParams, ...$retainedParams]);
        }
        $received = "r.event_type='delivery_local_success'";
        $trafficMatches = 'SELECT e.message_id,e.display_recipient AS recipient,e.event_type' . $linked . " AND e.event_type IN ('delivery_local_success','delivery_remote_success')";
        $trafficIdentity = "CAST(LOWER(CAST(SUBSTRING_INDEX(CASE WHEN $received THEN m.sender ELSE r.recipient END,'@',-1) AS CHAR CHARACTER SET utf8mb4)) AS BINARY)";
        // Deduplicate each direction independently: one message can legitimately
        // have both local delivery and remote acceptance in the selected history.
        $trafficRows = "SELECT DISTINCT m.id,$trafficIdentity AS identity,m.bytes,($received) AS received FROM ($trafficMatches) r JOIN mail_stats_messages m ON m.id=r.message_id WHERE " . $retained
            . " AND (($received AND " . $safeIdentity('m.sender') . ") OR (r.event_type='delivery_remote_success' AND " . $safeIdentity('r.recipient') . '))';
        $trafficSql = 'SELECT identity,SUM(received) AS received_messages,SUM(1-received) AS sent_messages,COALESCE(SUM(bytes),0) AS bytes,COUNT(bytes) AS known_size_messages FROM (' . $trafficRows . ') traffic GROUP BY identity ORDER BY ' . ($order === 'bytes' ? 'bytes' : 'COUNT(*)') . ' DESC,identity ASC LIMIT 10';
        $rankings['traffic_domains'] = $addressView ? [] : $select($trafficSql, [...$linkedParams, ...$retainedParams]);
        $periodStart = new DateTimeImmutable($start, new DateTimeZone('UTC'));
        $periodEnd = new DateTimeImmutable($end, new DateTimeZone('UTC'));
        $periodMicroseconds = ($periodEnd->getTimestamp() - $periodStart->getTimestamp()) * 1000000
            + (int) $periodEnd->format('u') - (int) $periodStart->format('u');
        $periodMinutes = $periodMicroseconds / 60000000;
        foreach ($rankings['traffic_domains'] as &$row) {
            $row['received_per_minute'] = (int) $row['received_messages'] / $periodMinutes;
            $row['sent_per_minute'] = (int) $row['sent_messages'] / $periodMinutes;
        }
        unset($row);
        $events = [];
        $next = null;
        if ((!$export && !$addressView && !in_array($filters['view'], ['overview', 'sources'], true)) || ($export && $filters['report'] === 'diagnostic')) {
            $eventFrom = $from;
            $eventParams = $params;
            if (!$export && $filters['cursor_at'] !== '') {
                $eventFrom .= ' AND (e.event_at < ? OR (e.event_at = ? AND e.id < ?))';
                array_push($eventParams, $filters['cursor_at'], $filters['cursor_at'], $filters['cursor_id']);
            }
            $limit = $export ? 1001 : 101;
            $events = $select('SELECT e.id,e.event_at,e.observed_at,s.source_key,e.component,e.event_type,e.severity,e.message_id,e.queue_id,e.sender,e.display_recipient AS recipient,e.ip,e.account,LEFT(e.metadata,4097) AS metadata' . $eventFrom . ' ORDER BY e.event_at DESC,e.id DESC LIMIT ' . $limit, $eventParams);
            if ($export && count($events) > 1000) throw new LengthException('The diagnostic exceeds 1,000 events. Reduce the period or add filters; no partial PDF was generated.');
            if (!$export && count($events) > 100) {
                array_pop($events);
                $last = $events[array_key_last($events)];
                $next = ['cursor_at' => $last['event_at'], 'cursor_id' => (string) $last['id']];
            }
        }
        $occurrences = [];
        $occurrencesMore = false;
        if (!$export && !$addressView && $filters['view'] !== 'overview' && ($filters['queue'] !== '' || $filters['address'] !== '' || $filters['message'] !== '')) {
            $occurrences = $select('SELECT m.id,m.queue_id,m.generation,m.started_at,m.last_event_at,m.finished_at,m.sender,m.bytes FROM mail_stats_messages m WHERE m.instance_id=? AND m.started_at>=? AND m.started_at<? AND EXISTS (SELECT 1' . $from . ' AND e.message_id=m.id) ORDER BY m.started_at DESC,m.id DESC LIMIT 101', [$config['instance_id'], $clock['cutoff'], $end, ...$params]);
            if (count($occurrences) > 100) { array_pop($occurrences); $occurrencesMore = true; }
        }
        $db->commit();
        $transaction = false;
        $warnings = [
            'Log observations are not the current queue. Missing logs do not mean zero activity. Correlation is shown only where proven; unlinked events remain independent.',
            'Message totals count distinct retained occurrences with a proven link to matching events. Bytes count known message sizes once, not delivery bytes. Outcome categories count attempts, including retries; series count events, not unique mail.',
            'Rankings show at most 10 known, safe ASCII dot-atom identities with DNS domains, excluding empty, malformed and redacted identities. Quoted local parts, SMTPUTF8 and domain literals are unsupported. Recipients require retained proven attempt links. Each message counts once per sender, recipient or destination domain; bytes are known message sizes, not traffic, and unknown sizes are excluded from byte sums.',
            'Error domains are destination domains with historical matching failures or deferrals, not an inferred cause or current condition. Each affected message counts once per domain; failed and deferred message counts can overlap.',
            'Received domain traffic means local delivery grouped by envelope sender domain; sent means remote acceptance grouped by destination domain, not inferred network ingress or inbox placement. Counts and known bytes count each message once per domain per direction, so a message may count in both directions. Rates are averages over the entire selected UTC period, not live throughput; missing directions are not proven absence of activity.',
            'Remote success means acceptance by a remote server, not inbox placement or reading. Temporary deferrals are not permanent failures.',
            'Retention is clipped in UTC on every query. Physical purge may be delayed while collection or the database is unavailable. Increasing retention cannot restore deleted history.',
            'Coverage and unknown-line counters describe collection health, not only the selected period. Initial history and lost archives cannot be reconstructed.',
            'Legacy records with an unprovable year or timezone are counted as unknown, not imported as fresh events. Mutable SQL snapshots and old quota observations are not complete histories or current measurements.',
        ];
        if (!$sources) $warnings[] = 'No registered source matches this selection. Metrics are unavailable, not proven zero.';
        if ($purgeDelayed) $warnings[] = 'Purge is delayed or its completion is unknown: no successful retention heartbeat within five minutes.';
        if ($filters['start'] !== '' && $filters['start'] < $clock['cutoff']) $warnings[] = 'The requested start was clipped to the retention boundary.';
        if ($occurrencesMore) $warnings[] = 'More than 100 historical message occurrences match. Narrow the period or address/queue filters to inspect the remainder.';
        foreach ($sources as $source) {
            if ($source['status'] !== 'active' || $source['coverage'] !== 'complete' || !$source['last_success_at'] || $source['last_success_at'] < $staleAt || (int) $source['lag_seconds'] > 300 || (int) $source['lines_unknown'] > 0 || (int) $source['discontinuities'] > 0) {
                $warnings[] = $source['source_key'] . ': coverage ' . $source['coverage'] . ', status ' . $source['status'] . '; inspect source health before interpreting counts.';
            }
        }
        $masked = $export && (!$includeNominal || $filters['report'] !== 'diagnostic');
        foreach ($rankings as &$ranking) {
            foreach ($ranking as &$row) $row['identity'] = $masked ? '[masked]' : mail_stats_redact((string) $row['identity']);
            unset($row);
        }
        unset($ranking);
        foreach ($events as &$event) {
            if (strlen($event['metadata']) > 4096) throw new LengthException('A diagnostic exceeds the structured metadata limit; no partial result was returned.');
            foreach (['sender', 'recipient', 'ip', 'account', 'queue_id', 'metadata'] as $field) {
                if ($event[$field] !== null) $event[$field] = $masked ? '[masked]' : mail_stats_redact((string) $event[$field]);
            }
        }
        unset($event);
        foreach ($occurrences as &$occurrence) $occurrence['sender'] = mail_stats_redact((string) $occurrence['sender']);
        unset($occurrence);
        foreach (['address', 'queue', 'ip', 'account'] as $field) $filters[$field] = $masked && $filters[$field] !== '' ? '[masked]' : mail_stats_redact($filters[$field]);
        return [
            'generated_at' => $clock['now_at'], 'instance_id' => $config['instance_id'], 'start' => $start, 'end' => $end,
            'retention_cutoff' => $clock['cutoff'], 'history_months' => $config['history_months'], 'filters' => $filters,
            'purge_last_success_at' => $purgeAt, 'purge_delayed' => $purgeDelayed,
            'sources' => $sources, 'counts' => $counts, 'series' => $series, 'granularity' => $granularity,
            'messages_count' => $messageTotals['count'], 'messages_bytes' => $messageTotals['bytes'],
            'rankings' => $rankings, 'address_list' => $addressList, 'period_minutes' => $periodMinutes,
            'events' => $events, 'occurrences' => $occurrences, 'next_cursor' => $next, 'warnings' => $warnings, 'masked' => $masked,
        ];
    } catch (mysqli_sql_exception $error) {
        throw new RuntimeException('Statistics database unavailable. Mail transport is unaffected.');
    } finally {
        if ($db instanceof mysqli) {
            if ($transaction) {
                try { $db->rollback(); } catch (Throwable) { /* Connection may already be unavailable. */ }
            }
            $db->close();
        }
    }
}

function mail_stats_hidden(array $fields): void
{
    foreach ($fields as $key => $value) echo '<input type="hidden" name="' . mail_stats_escape($key) . '" value="' . mail_stats_escape($value) . '">';
}
