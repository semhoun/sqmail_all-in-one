<?php
declare(strict_types=1);
require '/var/www/admin/lib/mail-stats.php';
if (!is_file('/.dockerenv') || getenv('MAIL_STATS_RANKINGS_FIXTURE') !== '1') throw new RuntimeException('Disposable test container required.');
function check(bool $condition, string $message): void {
    if (!$condition) throw new RuntimeException($message);
    echo "PASS $message\n";
}
@mkdir('/run/mail-stats', 0755, true);
@mkdir('/var/qmail/control/aio-conf', 0755, true);
$instance = str_repeat('a', 32);
file_put_contents('/run/mail-stats/web.json', json_encode(['enabled' => true, 'history_months' => 6, 'instance_id' => $instance]));
file_put_contents('/var/qmail/control/aio-conf/mysql.php', '<?php $MYSQL_CONF=' . var_export(['MYSQL_HOST' => 'db', 'MYSQL_USER' => 'stats', 'MYSQL_PASS' => 'SyntheticRankings927', 'MYSQL_DB' => 'stats'], true) . ';');
$deadline = microtime(true) + 120;
do {
    try { $db = mail_stats_connect(); break; } catch (Throwable $error) { if (microtime(true) > $deadline) throw $error; sleep(1); }
} while (true);
$db->multi_query(file_get_contents('/opt/sql/mail-stats.sql'));
do { if ($result = $db->store_result()) $result->free(); } while ($db->more_results() && $db->next_result());
$db->query('INSERT INTO mail_stats_schema VALUES (1,1,UTC_TIMESTAMP(6))');
foreach ([[$instance, 'qmail-send', 'transport'], [$instance, 'dovecot', 'dovecot'], [str_repeat('b', 32), 'qmail-send', 'transport']] as [$tenant, $source, $family]) {
    $db->execute_query("INSERT INTO mail_stats_sources (instance_id,source_key,family,status,coverage,first_seen_at) VALUES (?,?,?,'active','partial',UTC_TIMESTAMP(6))", [$tenant, $source, $family]);
}
function message(string $sender, ?int $bytes, bool $old = false, string $tenant = ''): int {
    global $db, $instance;
    $tenant = $tenant ?: $instance;
    $db->execute_query("INSERT INTO mail_stats_messages (instance_id,source_id,generation,queue_id,started_at,last_event_at,sender,bytes) VALUES (?,1,?,'123',UTC_TIMESTAMP(6)-INTERVAL " . ($old ? '7 MONTH' : '1 DAY') . ',UTC_TIMESTAMP(6),?,?)', [$tenant, bin2hex(random_bytes(8)), $sender, $bytes]);
    return $db->insert_id;
}
function event(?int $message, string $recipient, string $type = 'delivery_failure', bool $linked = true, int $source = 1, string $tenant = ''): void {
    global $db, $instance;
    $tenant = $tenant ?: $instance;
    $attempt = null;
    if ($linked) {
        $db->execute_query("INSERT INTO mail_stats_attempts (instance_id,source_id,message_id,generation,attempt_key,recipient,started_at) VALUES (?,?,?,'g',?,?,UTC_TIMESTAMP(6)-INTERVAL 1 HOUR)", [$tenant, $source, $message, bin2hex(random_bytes(8)), $recipient]);
        $attempt = $db->insert_id;
    }
    $db->execute_query("INSERT INTO mail_stats_events (instance_id,source_id,source_position,message_id,attempt_id,event_at,observed_at,component,event_type,severity,parser,parser_version,queue_id,sender,recipient,ip,account,metadata) VALUES (?,?,?,?,?,UTC_TIMESTAMP(6)-INTERVAL 30 MINUTE,UTC_TIMESTAMP(6),'qmail-send',?,'warning','fixture',1,'123','observed@example.invalid',?,'192.0.2.1','fixture','{}')", [$tenant, $source, bin2hex(random_bytes(8)), $message, $attempt, $type, $recipient]);
}
$one = message('sender@example.invalid', 100);
$two = message('sender@example.invalid', null);
$zero = message('zero@example.invalid', 0);
for ($i = 0; $i < 105; $i++) event($one, 'a@MiXeD.invalid', $i % 2 ? 'delivery_failure' : 'delivery_deferral');
event($one, 'b@mixed.invalid');
event($two, 'a@MiXeD.invalid', 'delivery_remote_success');
event($zero, 'z@zero.invalid');
event(message('old@example.invalid', 99999, true), 'old@old.invalid');
event(null, 'orphan@orphan.invalid');
event($one, 'unlinked@unlinked.invalid', 'delivery_failure', false);
event(message('foreign@example.invalid', 99999, false, str_repeat('b', 32)), 'foreign@foreign.invalid', 'delivery_failure', true, 3, str_repeat('b', 32));
foreach (['SRS0+SENSITIVE+user@example.invalid', 'token=PRIVATE@example.invalid', '[SRS redacted]', '<script>@evil.invalid', 'no-at', 'user@[127.0.0.1]', 'a..b@bad.invalid', 'a@-bad.invalid', 'a@' . str_repeat('x', 64) . '.invalid', str_repeat('x', 65) . '@example.invalid'] as $unsafe) event(message($unsafe, 1), $unsafe);
$snapshot = mail_stats_snapshot(['view' => 'transport']);
$r = $snapshot['rankings'];
$overview = mail_stats_snapshot([]);
check(!$overview['events'] && $overview['next_cursor'] === null && $overview['rankings'] === $r, 'overview omits detailed event page without changing rankings');
$sources = mail_stats_snapshot(['view' => 'sources']);
check(!$sources['events'] && $sources['next_cursor'] === null && $sources['rankings'] === $r, 'source status omits event page without changing rankings');
check(!mail_stats_snapshot(['queue' => '123'])['occurrences'] && mail_stats_snapshot(['view' => 'transport', 'queue' => '123'])['occurrences'], 'overview skips unused occurrences while Transport retains them');
check($r['senders'][0]['identity'] === 'sender@example.invalid' && (int) $r['senders'][0]['messages'] === 2 && (int) $r['senders'][0]['bytes'] === 100 && (int) $r['senders'][0]['known_size_messages'] === 1, 'sender envelope occurrences once, NULL size distinct from known size');
check(count($r['senders']) === 2 && (int) $r['senders'][1]['known_size_messages'] === 1 && (int) $r['senders'][1]['bytes'] === 0, 'known zero bytes retained, unsafe/expired/foreign identities excluded');
foreach (['senders', 'recipients'] as $view) check(mail_stats_snapshot(['view' => $view])['address_list']['rows'] === $r[$view], 'list retains exactly ranking identity/link/retention rules: ' . $view);
check($r['recipients'][0]['identity'] === 'a@MiXeD.invalid' && (int) $r['recipients'][0]['messages'] === 2 && count($r['recipients']) === 3, 'recipient retries deduplicated and unlinked/orphans excluded');
check($r['traffic_domains'][0]['identity'] === 'mixed.invalid' && (int) $r['traffic_domains'][0]['sent_messages'] === 1 && (int) $r['traffic_domains'][0]['known_size_messages'] === 0, 'remote domain casefold and unknown bytes preserved');
check((int) $r['traffic_domains'][0]['received_messages'] === 0 && $r['traffic_domains'][0]['sent_per_minute'] > 0 && $r['traffic_domains'][0]['sent_per_minute'] < 0.001, 'empty direction and tiny positive average rate preserved');
$errors = $r['error_domains'][0];
check($errors['identity'] === 'mixed.invalid' && (int) $errors['affected_messages'] === 1 && (int) $errors['failed_messages'] === 1 && (int) $errors['deferred_messages'] === 1, 'historical failure/deferral overlap without retry inflation');
check(mail_stats_snapshot($snapshot['next_cursor'] + ['view' => 'transport', 'start' => $snapshot['start'], 'end' => $snapshot['end']])['rankings'] === $r, 'all rankings invariant under event pagination');
foreach (['view' => 'dovecot', 'source' => 'dovecot', 'component' => 'other', 'type' => 'other', 'severity' => 'info', 'address' => "' OR 1=1 --", 'queue' => '999', 'ip' => '192.0.2.2', 'account' => 'other', 'message' => '999999'] as $key => $value) {
    check(!array_filter(mail_stats_snapshot([$key => $value])['rankings']), 'filter honored: ' . $key);
}
check(!array_filter(mail_stats_snapshot(['end' => (new DateTimeImmutable('-2 days', new DateTimeZone('UTC')))->format('Y-m-d H:i:s')])['rankings']), 'time window honored');
check((int) mail_stats_snapshot(['type' => 'delivery_remote_success'])['rankings']['senders'][0]['messages'] === 1, 'matching subset not all message events');
foreach ([[true, 'summary', true], [true, 'diagnostic', false]] as [$export, $report, $nominal]) {
    foreach (mail_stats_snapshot(['report' => $report], $export, $nominal)['rankings'] as $rows) foreach ($rows as $row) check($row['identity'] === '[masked]', 'export ranking identity masked');
}
check(mail_stats_snapshot(['report' => 'diagnostic'], true, true)['rankings'] === $r, 'explicit nominal diagnostic keeps safe rankings');
check(!str_contains(json_encode($r), 'SENSITIVE') && !str_contains(json_encode($r), 'PRIVATE') && !str_contains(json_encode($r), '<script>'), 'ranking SRS, credential and stored XSS secrecy');
check(mail_stats_filters([])['rank_by'] === 'messages', 'default ranking order');
try { mail_stats_filters(['rank_by' => 'bytes DESC;DROP TABLE x']); throw new LogicException('accepted invalid rank'); } catch (InvalidArgumentException) { check(true, 'ranking order injection refused'); }
for ($i = 0; $i < 12; $i++) {
    $name = sprintf('rank%02d', $i);
    $id = message($name . '@example.invalid', 1000 + $i);
    event($id, $name . '@' . $name . '.invalid');
    event($id, $name . '@' . $name . '.invalid', 'delivery_remote_success');
}
$ranked = mail_stats_snapshot([])['rankings'];
foreach ($ranked as $kind => $rows) check(count($rows) === 10, 'SQL top ten: ' . $kind);
check($ranked['senders'][1]['identity'] === 'rank00@example.invalid' && $ranked['senders'][9]['identity'] === 'rank08@example.invalid', 'message order has deterministic binary identity ties');
$bytes = mail_stats_snapshot(['rank_by' => 'bytes'])['rankings'];
foreach (['senders', 'recipients', 'traffic_domains'] as $kind) check(str_starts_with($bytes[$kind][0]['identity'], 'rank11') && (int) $bytes[$kind][0]['bytes'] === 1011, 'byte order: ' . $kind);
check($bytes['error_domains'] === $ranked['error_domains'], 'error domains ignore byte order');
check($ranked['traffic_domains'][0]['identity'] === 'mixed.invalid' && $ranked['traffic_domains'][9]['identity'] === 'rank08.invalid', 'traffic ties use deterministic domain identity');
foreach (['secretary', 'token', 'password', 'cookie', 'authorization'] as $word) {
    $id = message($word . '@ordinary.invalid', 0);
    event($id, $word . '@ordinary.invalid', 'delivery_local_success');
    $safe = mail_stats_snapshot(['message' => (string) $id])['rankings'];
    check($safe['senders'][0]['identity'] === $word . '@ordinary.invalid' && $safe['recipients'][0]['identity'] === $word . '@ordinary.invalid', 'ordinary sensitive word is not a secret: ' . $word);
}
$identities = ["o'connor", 'bill!tag', 'user=tag', "!#$%&'*+/=?^_`{|}~-", 'first.last',
    'secret=PRIVATE', 'token=PRIVATE', 'x+password=PRIVATE', 'authorization=PRIVATE', 'cookie=PRIVATE',
    'SECRET=PRIVATE', 'mysecret=normal', 'x_token=normal', 'token=}normal',
    'SRS0=PRIVATE', 'SRS1+PRIVATE', 'srs0-PRIVATE', "SRS0+'", "SRS0+'normal"];
foreach ($identities as $local) {
    $address = $local . '@punctuation.invalid';
    $id = message($address, 0);
    event($id, $address, 'delivery_remote_success');
    $rows = mail_stats_snapshot(['message' => (string) $id])['rankings'];
    $unchanged = mail_stats_redact($address) === $address;
    check($unchanged ? ($rows['senders'][0]['identity'] ?? null) === $address && ($rows['recipients'][0]['identity'] ?? null) === $address : !$rows['senders'] && !$rows['recipients'], 'ASCII punctuation and redactor equivalence: ' . $local);
    check($unchanged ? count($rows['traffic_domains']) === 1 : !$rows['traffic_domains'], 'traffic identity eligibility matches redactor: ' . $local);
}
$both = message('source@BiDi.invalid', 123);
$unknown = message('source@bidi.invalid', null);
$knownZero = message('source@bidi.invalid', 0);
foreach ([$both, $unknown, $knownZero] as $id) {
    foreach (['first@BiDi.invalid', 'second@bidi.invalid'] as $recipient) {
        for ($retry = 0; $retry < 3; $retry++) {
            event($id, $recipient, 'delivery_local_success');
            event($id, $recipient, 'delivery_remote_success');
        }
    }
}
$db->query("UPDATE mail_stats_events SET account='bidirectional' WHERE message_id IN ($both,$unknown,$knownZero)");
$fixedEnd = new DateTimeImmutable('-1 minute', new DateTimeZone('UTC'));
$fixedStart = $fixedEnd->modify('-1 hour');
$window = ['account' => 'bidirectional', 'start' => $fixedStart->format('Y-m-d H:i:s.u'), 'end' => $fixedEnd->format('Y-m-d H:i:s.u')];
$traffic = mail_stats_snapshot($window);
$row = $traffic['rankings']['traffic_domains'][0];
check(count($traffic['rankings']['traffic_domains']) === 1 && $row['identity'] === 'bidi.invalid', 'both directions fold sender and destination domain');
check((int) $row['received_messages'] === 3 && (int) $row['sent_messages'] === 3, 'each message once per direction despite recipients and retries');
check((int) $row['bytes'] === 246 && (int) $row['known_size_messages'] === 4, 'known bytes count once per message per direction, including zero excluding NULL');
check($traffic['period_minutes'] == 60 && abs($row['received_per_minute'] - 0.05) < 1e-12 && abs($row['sent_per_minute'] - 0.05) < 1e-12, 'fixed-period rate denominator is entire selected hour');
check(!isset($traffic['rankings']['domains']), 'unused destination-only query removed');
$receivedOnly = mail_stats_snapshot($window + ['type' => 'delivery_local_success'])['rankings']['traffic_domains'][0];
check((int) $receivedOnly['received_messages'] === 3 && (int) $receivedOnly['sent_messages'] === 0, 'direction respects event-type filter');
$db->query("UPDATE mail_stats_events SET event_at=UTC_TIMESTAMP(6)-INTERVAL 7 MONTH WHERE message_id=$unknown");
check((int) mail_stats_snapshot($window)['rankings']['traffic_domains'][0]['sent_messages'] === 2, 'expired directional events excluded');
$db->query("UPDATE mail_stats_messages SET started_at=UTC_TIMESTAMP(6)-INTERVAL 7 MONTH WHERE id=$knownZero");
check((int) mail_stats_snapshot($window)['rankings']['traffic_domains'][0]['received_messages'] === 1, 'expired directional message parent excluded');
$microBase = $fixedEnd->modify('-1 second')->format('Y-m-d H:i:s');
$db->execute_query('UPDATE mail_stats_events SET event_at=? WHERE message_id=?', [$microBase . '.123457', $both]);
$micro = mail_stats_snapshot(['account' => 'bidirectional', 'start' => $microBase . '.123456', 'end' => $microBase . '.123458']);
check(abs($micro['period_minutes'] - 2 / 60000000) < 1e-20 && abs($micro['rankings']['traffic_domains'][0]['received_per_minute'] - 30000000) < 1e-6, 'microsecond interval avoids epoch float cancellation');
foreach ([['summary', true], ['diagnostic', false]] as [$report, $nominal]) check(mail_stats_snapshot(['report' => $report, 'account' => 'bidirectional'], true, $nominal)['rankings']['traffic_domains'][0]['identity'] === '[masked]', 'bidirectional domain masked in export');
// Inspect the same indexed event/attempt/message link path used by traffic.
$plan = mail_stats_select($db, "EXPLAIN SELECT e.message_id FROM mail_stats_events e JOIN mail_stats_sources s ON s.id=e.source_id AND s.instance_id=e.instance_id WHERE s.instance_id=? AND e.instance_id=? AND e.event_at>=? AND e.event_at<? AND e.account=? AND e.event_type IN ('delivery_local_success','delivery_remote_success') AND EXISTS (SELECT 1 FROM mail_stats_attempts a WHERE a.id=e.attempt_id AND a.instance_id=e.instance_id AND a.message_id=e.message_id AND a.recipient=e.recipient AND a.started_at>=?)", [$instance, $instance, $window['start'], $window['end'], 'bidirectional', $snapshot['retention_cutoff']]);
foreach (['e', 'a'] as $table) {
    $part = array_values(array_filter($plan, static fn(array $row): bool => $row['table'] === $table));
    check(count($part) === 1 && $part[0]['key'] !== null && $part[0]['type'] !== 'ALL', 'indexed directional link plan: ' . $table);
    echo 'EXPLAIN ' . $table . ': ' . $part[0]['key'] . ' / ' . $part[0]['type'] . "\n";
}
// More than two pages, including binary case ties, unknown/zero bytes and large sums.
$expected = [];
for ($i = 0; $i < 113; $i++) {
    $address = sprintf('%s%03d@pages.invalid', $i % 2 ? 'Page' : 'page', $i);
    $expected[] = $address;
    foreach ($i < 80 ? [PHP_INT_MAX, PHP_INT_MAX - $i % 2] : [$i % 3 === 0 ? null : 0] as $size) {
        $id = message($address, $size);
        event($id, $address);
        event($id, $address, 'delivery_remote_success');
        $db->execute_query("UPDATE mail_stats_events SET account='pages' WHERE message_id=?", [$id]);
    }
}
$pageWindow = ['account' => 'pages', 'start' => $window['start'], 'end' => $window['end']];
sort($expected, SORT_STRING);
foreach (['senders', 'recipients'] as $view) {
    foreach (['messages', 'bytes'] as $order) {
        $selection = $pageWindow + ['view' => $view, 'rank_by' => $order];
        $cursor = [];
        $seen = [];
        $sizes = [];
        do {
            $page = mail_stats_snapshot($selection + $cursor);
            check(!$page['events'] && !$page['occurrences'] && !$page['series'], 'address page skips unrelated work: ' . $view);
            $sizes[] = count($page['address_list']['rows']);
            $seen = [...$seen, ...array_column($page['address_list']['rows'], 'identity')];
            $cursor = $page['address_list']['next_cursor'];
        } while ($cursor !== null);
        check($sizes === [50, 50, 13], '50 + 50 + tail: ' . $view . '/' . $order);
        $sorted = $seen;
        sort($sorted, SORT_STRING);
        check($sorted === $expected, 'no duplicate or omitted identity: ' . $view . '/' . $order);
        $expectedOrder = $expected;
        usort($expectedOrder, static function (string $a, string $b) use ($order): int {
            $group = static function (string $s) use ($order): int {
                $n = (int) substr($s, 4, 3);
                return $n < 80 ? ($order === 'bytes' ? 2 - $n % 2 : 1) : 0;
            };
            return ($group($b) <=> $group($a)) ?: strcmp($a, $b);
        });
        check($seen === $expectedOrder, 'exact aggregates and binary ties: ' . $view . '/' . $order);
        $first = mail_stats_snapshot($selection);
        check($first['address_list'] === mail_stats_snapshot($selection)['address_list'], 'first-page reset stable: ' . $view . '/' . $order);
        $cursor = $first['address_list']['next_cursor'];
        if ($order === 'bytes') check($cursor['cursor_metric'] === '18446744073709551613', 'above-uint64 byte cursor preserves adjacent integers');
        foreach ([['summary', false], ['diagnostic', false], ['diagnostic', true]] as [$report, $nominal]) {
            $pdf = mail_stats_snapshot($selection + $cursor + ['report' => $report], true, $nominal);
            check(!$pdf['address_list']['rows'] && $pdf['address_list']['next_cursor'] === null && $pdf['filters']['cursor_identity'] === '' && $pdf['filters']['cursor_metric'] === '' && count($pdf['rankings'][$view]) === 10, 'PDF never includes pagination or full list: ' . $view . '/' . $report);
        }
        foreach (['source' => 'dovecot', 'end' => $fixedStart->modify('-1 day')->format('Y-m-d H:i:s.u')] as $field => $value) {
            $empty = array_replace($selection, [$field => $value]);
            if ($field === 'end') $empty['start'] = $fixedStart->modify('-2 days')->format('Y-m-d H:i:s.u');
            check(!mail_stats_snapshot($empty)['address_list']['rows'], 'address list filter: ' . $field);
        }
    }
}
$validCursor = ['view' => 'senders', 'cursor_metric' => '1', 'cursor_identity' => 'page@example.invalid', 'cursor_rank_by' => 'messages'];
foreach ([['cursor_metric' => ''], ['cursor_identity' => ''], ['cursor_rank_by' => ''], ['rank_by' => 'bytes'], ['cursor_metric' => '-1'], ['cursor_metric' => '1e2'], ['cursor_metric' => str_repeat('9', 66)], ['cursor_identity' => ['bad']], ['cursor_identity' => null], ['cursor_identity' => "bad\naddress"], ['cursor_identity' => str_repeat('x', 321)], ['view' => 'overview']] as $bad) {
    try { mail_stats_filters(array_replace($validCursor, $bad)); throw new LogicException('accepted invalid cursor'); }
    catch (InvalidArgumentException) { check(true, 'malformed or stale sort cursor refused'); }
}
check(mail_stats_filters(array_replace($validCursor, ['cursor_metric' => str_repeat('9', 65)]))['cursor_metric'] === str_repeat('9', 65), 'DECIMAL65 cursor remains exact');
$hostile = mail_stats_snapshot($pageWindow + ['view' => 'senders', 'cursor_metric' => '2', 'cursor_identity' => "' OR 1=1 --", 'cursor_rank_by' => 'messages']);
check(count($hostile['address_list']['rows']) === 50, 'cursor identity bound as data, not SQL');
// Retained raw identities are normalized only at read time with local evidence.
$localCases = [
    ['dune.tf-nathanael@dune.tf', 'nathanael@dune.tf', 'attempt_started', '{"delivery_kind":"local"}'],
    ['dune.tf-nathanael@dune.tf', 'nathanael@dune.tf', 'delivery_failure', '{"delivery_kind":"local"}'],
    ['dune.tf-nathanael@dune.tf', 'nathanael@dune.tf', 'delivery_deferral', '{"delivery_kind":"local"}'],
    ['dune.tf-nathanael@dune.tf', 'nathanael@dune.tf', 'delivery_local_success', '{}'],
    ['dune.tf-nathanael@dune.tf', 'nathanael@dune.tf', 'delivery_local_success', '{broken'],
    ['dune.tf-nathanael@dune.tf', 'dune.tf-nathanael@dune.tf', 'delivery_remote_success', '{"delivery_kind":"remote"}'],
    ['dune.tf-nathanael@dune.tf', 'dune.tf-nathanael@dune.tf', 'delivery_failure', '{broken'],
    ['dune.tf-nathanael@dune.tf', 'dune.tf-nathanael@dune.tf', 'delivery_failure', '{"delivery_kind":null}'],
    ['dune.tf-nathanael@dune.tf', 'dune.tf-nathanael@dune.tf', 'delivery_failure', '{"delivery_kind":"unknown"}'],
    ['wrong-nathanael@dune.tf', 'wrong-nathanael@dune.tf', 'delivery_local_success', '{}'],
    ['dune.tf-nathanael', 'dune.tf-nathanael', 'delivery_local_success', '{}'],
    ['dune.tf-@dune.tf', 'dune.tf-@dune.tf', 'delivery_local_success', '{}'],
    ['dune.tf-a@b@dune.tf', 'dune.tf-a@b@dune.tf', 'delivery_local_success', '{}'],
    ['dune.tf-dune.tf-name@dune.tf', 'dune.tf-name@dune.tf', 'delivery_local_success', '{}'],
    ['dune.tf-Nathanael@dune.tf', 'Nathanael@dune.tf', 'delivery_local_success', '{}'],
    ['DUNE.TF-name@dune.tf', 'DUNE.TF-name@dune.tf', 'delivery_local_success', '{}'],
    ['DUNE.TF-name@DUNE.TF', 'name@DUNE.TF', 'delivery_local_success', '{}'],
    ['dune.tf-nathanael@dune.tf', 'dune.tf-nathanael@dune.tf', 'auth_success', '{}'],
    ['dune.tf-nathanael@dune.tf', 'dune.tf-nathanael@dune.tf', 'auth_success', '{"delivery_kind":"local"}'],
    ['dune.tf-nathanael@dune.tf', 'dune.tf-nathanael@dune.tf', 'delivery_remote_success', '{"delivery_kind":"local"}'],
];
foreach ($localCases as [$raw, $canonical, $type, $metadata]) {
    $id = message('dune.tf-sender@dune.tf', 17);
    event($id, $raw, $type);
    $eventId = $db->insert_id;
    $db->execute_query('UPDATE mail_stats_events SET metadata=? WHERE id=?', [$metadata, $eventId]);
    $selection = ['view' => 'transport', 'message' => (string) $id];
    $result = mail_stats_snapshot($selection);
    check($result['events'][0]['recipient'] === $canonical, 'local recipient normalization: ' . $raw . '/' . $type . '/' . $metadata);
    check(count(mail_stats_snapshot($selection + ['address' => $canonical])['events']) === 1 && count(mail_stats_snapshot($selection + ['address' => $raw])['events']) === 1, 'canonical and raw exact searches retained');
    check($result['rankings']['senders'][0]['identity'] === 'dune.tf-sender@dune.tf', 'envelope sender never normalized');
    $stored = $db->execute_query('SELECT e.recipient,a.recipient AS attempt_recipient FROM mail_stats_events e JOIN mail_stats_attempts a ON a.id=e.attempt_id WHERE e.id=?', [$eventId])->fetch_assoc();
    check($stored['recipient'] === $raw && $stored['attempt_recipient'] === $raw, 'read-time transformation leaves raw provenance unchanged');
}
foreach ([[2, 'qmail-send'], [1, 'smtp-auth'], [1, 'roundcube']] as [$sourceId, $component]) {
    $id = message('unchanged@example.invalid', 1);
    event($id, 'dune.tf-name@dune.tf', 'delivery_local_success', true, $sourceId);
    $db->execute_query('UPDATE mail_stats_events SET component=? WHERE id=?', [$component, $db->insert_id]);
    check(mail_stats_snapshot(['view' => $sourceId === 2 ? 'dovecot' : 'transport', 'message' => (string) $id])['events'][0]['recipient'] === 'dune.tf-name@dune.tf', 'both source and component proof required');
}
$id = message('unchanged@example.invalid', 1);
event($id, 'dune.tf-orphan@dune.tf', 'delivery_failure', false);
check(mail_stats_snapshot(['view' => 'transport', 'message' => (string) $id])['events'][0]['recipient'] === 'dune.tf-orphan@dune.tf', 'unproven orphan remains unchanged');
$db->execute_query('UPDATE mail_stats_events SET recipient=NULL WHERE id=?', [$db->insert_id]);
check(mail_stats_snapshot(['view' => 'transport', 'message' => (string) $id])['events'][0]['recipient'] === null, 'NULL recipient remains NULL');
$normalExpected = [];
for ($i = 0; $i < 103; $i++) {
    $local = sprintf('user%03d', $i);
    if ($i === 50) $local = str_repeat('x', 64);
    $canonical = $local . '@dune.tf';
    $normalExpected[] = $canonical;
    $id = message('unchanged@example.invalid', 7);
    foreach ([['dune.tf-' . $canonical, 'delivery_local_success'], [$canonical, 'delivery_local_success'], [$canonical, 'delivery_remote_success']] as [$raw, $type]) event($id, $raw, $type);
    if ($i === 50) {
        event($id, 'dune.tf-' . $canonical, 'delivery_failure');
        $db->execute_query('UPDATE mail_stats_events SET metadata=? WHERE id=?', ['{"delivery_kind":"local"}', $db->insert_id]);
        $long = mail_stats_snapshot(['message' => (string) $id]);
        check($long['rankings']['error_domains'][0]['identity'] === 'dune.tf', 'error domain eligibility uses normalized long local part');
        $directions = array_column($long['rankings']['traffic_domains'], null, 'identity');
        check((int) $directions['dune.tf']['sent_messages'] === 1 && (int) $directions['example.invalid']['received_messages'] === 1, 'directional domain suffix and message dedup unchanged');
    }
    $db->execute_query("UPDATE mail_stats_events SET account='normalized-pages' WHERE message_id=?", [$id]);
}
sort($normalExpected, SORT_STRING);
foreach (['messages', 'bytes'] as $order) {
    $selection = ['view' => 'recipients', 'account' => 'normalized-pages', 'rank_by' => $order];
    $cursor = [];
    $seen = [];
    $sizes = [];
    do {
        $page = mail_stats_snapshot($selection + $cursor);
        $sizes[] = count($page['address_list']['rows']);
        foreach ($page['address_list']['rows'] as $row) {
            check((int) $row['messages'] === 1 && (int) $row['bytes'] === 7, 'normalized raw/canonical local and remote dedup per message');
            $seen[] = $row['identity'];
        }
        $cursor = $page['address_list']['next_cursor'];
    } while ($cursor !== null);
    check($sizes === [50, 50, 3] && $seen === $normalExpected, 'normalized identities grouped before safety and keyset pagination: ' . $order);
}
$normalizedPdf = mail_stats_snapshot(['view' => 'transport', 'address' => 'nathanael@dune.tf', 'report' => 'diagnostic'], true, true);
check($normalizedPdf['events'] && !array_filter($normalizedPdf['events'], static fn(array $row): bool => $row['recipient'] !== 'nathanael@dune.tf'), 'nominal diagnostic displays canonical recipient');
$maskedPdf = mail_stats_snapshot(['view' => 'transport', 'address' => 'nathanael@dune.tf', 'report' => 'diagnostic'], true);
check(!str_contains(json_encode($maskedPdf), 'nathanael@dune.tf'), 'normalized recipients remain masked in exports');
$db->query("UPDATE mail_stats_attempts SET instance_id=REPEAT('b',32)");
check(!mail_stats_snapshot(['view' => 'recipients'])['address_list']['rows'], 'list rejects cross-instance attempt links');
check(!mail_stats_snapshot([])['rankings']['recipients'], 'cross-instance attempt links rejected');
check(!mail_stats_snapshot([])['rankings']['traffic_domains'], 'cross-instance directional attempt links rejected');
$db->execute_query('UPDATE mail_stats_attempts SET instance_id=?,message_id=?', [$instance, $zero]);
check(count(mail_stats_snapshot([])['rankings']['recipients']) === 1, 'attempt-to-message mismatch rejected');
$db->query("UPDATE mail_stats_attempts SET recipient='mismatch@example.invalid'");
check(!mail_stats_snapshot([])['rankings']['recipients'], 'attempt-to-recipient mismatch rejected');
$db->query('UPDATE mail_stats_attempts a JOIN mail_stats_events e ON e.attempt_id=a.id SET a.message_id=e.message_id,a.recipient=e.recipient,a.instance_id=e.instance_id');
$db->query('UPDATE mail_stats_attempts SET started_at=UTC_TIMESTAMP(6)-INTERVAL 7 MONTH');
check(!mail_stats_snapshot([])['rankings']['recipients'], 'expired attempt parents excluded before physical purge');
check(!mail_stats_snapshot(['view' => 'recipients'])['address_list']['rows'], 'list excludes expired attempt parents before purge');
check(!mail_stats_snapshot([])['rankings']['traffic_domains'], 'expired directional attempt parents excluded');
$started = hrtime(true);
try { mail_stats_select($db, 'SELECT SLEEP(2)', [], $started - 1); throw new LogicException('accepted expired deadline'); } catch (RuntimeException $error) { check(!$error instanceof LogicException, 'expired shared SQL deadline refuses execution'); }
check(hrtime(true) - $started < 500000000, 'expired deadline returns immediately');
$deadline = hrtime(true) + 250000000;
mail_stats_select($db, 'SELECT SLEEP(0.12)', [], $deadline);
try {
    $interrupted = mail_stats_select($db, 'SELECT SLEEP(2) AS interrupted', [], $deadline);
    // MySQL may report an interrupted lone SLEEP as 1 instead of an SQL error.
    check((int) $interrupted[0]['interrupted'] === 1, 'remaining cumulative SQL budget interrupts next query');
} catch (mysqli_sql_exception | RuntimeException $error) {
    check($error instanceof mysqli_sql_exception || str_contains($error->getMessage(), 'budget exceeded'), 'remaining cumulative SQL budget interrupts next query');
}
check(hrtime(true) < $deadline + 1000000000, 'cumulative budget not reset per query');
$db->close();
echo "All isolated ranking checks passed.\n";
