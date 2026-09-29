<?php
declare(strict_types=1);
if (!is_file('/.dockerenv') || getenv('MAIL_STATS_BROWSER_FIXTURE') !== '1') throw new RuntimeException('Disposable browser fixture required.');
require '/var/www/admin/lib/mail-stats.php';
@mkdir('/var/qmail/control/aio-conf', 0750, true);
@mkdir('/run/mail-stats', 0750, true);
$credentials = ['MYSQL_HOST' => 'db', 'MYSQL_USER' => 'stats', 'MYSQL_PASS' => 'SyntheticBrowser927', 'MYSQL_DB' => 'stats'];
file_put_contents('/var/qmail/control/aio-conf/mysql.php', '<?php $MYSQL_CONF=' . var_export($credentials, true) . ';');
file_put_contents('/run/mail-stats/web.json', json_encode(['enabled' => true, 'history_months' => 6, 'instance_id' => str_repeat('a', 32), 'reason' => '']));
foreach (['/var/qmail/control/aio-conf', '/run/mail-stats'] as $directory) { chgrp($directory, 'www-data'); chmod($directory, 0750); }
foreach (['/var/qmail/control/aio-conf/mysql.php', '/run/mail-stats/web.json'] as $file) { chgrp($file, 'www-data'); chmod($file, 0640); }
$deadline = microtime(true) + 100;
do {
    try { $db = mail_stats_connect(); break; } catch (Throwable $error) { if (microtime(true) > $deadline) throw $error; sleep(1); }
} while (true);
$instance = str_repeat('a', 32);
if (($argv[1] ?? '') === 'address-lists') {
    $db->begin_transaction();
    for ($n = 1; $n <= 115; $n++) {
        $suffix = sprintf('%03d', $n);
        $sender = 'bulk' . $suffix . '@listing.invalid';
        $recipient = 'dest' . $suffix . '@listing.invalid';
        $generation = 'address-list-' . $suffix;
        $db->execute_query('INSERT INTO mail_stats_messages (instance_id,source_id,generation,queue_id,started_at,last_event_at,sender,bytes) VALUES (?,1,?,?,UTC_TIMESTAMP(6)-INTERVAL 1 DAY,UTC_TIMESTAMP(6),?,?)', [$instance,$generation,(string) (10000+$n),$sender,$n*1024]);
        $message = $db->insert_id;
        $db->execute_query('INSERT INTO mail_stats_attempts (instance_id,source_id,message_id,generation,attempt_key,recipient,started_at,finished_at,outcome) VALUES (?,1,?,?,?,?,UTC_TIMESTAMP(6)-INTERVAL 2 HOUR,UTC_TIMESTAMP(6),?)', [$instance,$message,$generation,$generation,$recipient,'success']);
        $attempt = $db->insert_id;
        $db->execute_query('INSERT INTO mail_stats_events (instance_id,source_id,source_position,message_id,attempt_id,generation,event_at,observed_at,component,event_type,severity,parser,parser_version,queue_id,sender,recipient,metadata) VALUES (?,1,?,?,?,?,UTC_TIMESTAMP(6)-INTERVAL 2 HOUR,UTC_TIMESTAMP(6),?,?,?, ?,1,?,?,?,?)', [$instance,$generation,$message,$attempt,$generation,'qmail-send','delivery_local_success','info','fixture',(string) (10000+$n),$sender,$recipient,'{}']);
    }
    $db->commit();
    $db->close();
    echo "Synthetic address-list rows ready.\n";
    exit;
}
$db->multi_query(file_get_contents('/opt/sql/mail-stats.sql'));
do { if ($result = $db->store_result()) $result->free(); } while ($db->more_results() && $db->next_result());
$db->query('INSERT INTO mail_stats_schema VALUES (1,1,UTC_TIMESTAMP(6))');
$sources = [
    ['qmail-send', 'transport', 'active', 'partial'],
    ['dovecot', 'dovecot', 'active', 'partial'],
    ['spamd', 'filtering', 'active', 'partial'],
    ['roundcube', 'web', 'conditional', 'routed'],
    ['local-syslog', 'maintenance', 'active', 'partial'],
    ['retention', 'maintenance', 'active', 'partial'],
    ['roundcube-debug', 'web', 'disabled', 'none'],
    ['lastauth', 'dovecot', 'observed_only', 'state_observed'],
];
foreach ($sources as [$key, $family, $status, $coverage]) {
    $db->execute_query('INSERT INTO mail_stats_sources (instance_id,source_key,family,status,coverage,reason_code,first_seen_at,last_success_at,lines_unknown,lines_seen) VALUES (?,?,?,?,?,?,UTC_TIMESTAMP(6)-INTERVAL 7 DAY,UTC_TIMESTAMP(6),2,120)', [$instance, $key, $family, $status, $coverage, 'synthetic_coverage']);
}
for ($n = 1; $n <= 2; $n++) {
    $db->execute_query('INSERT INTO mail_stats_messages (instance_id,source_id,generation,queue_id,started_at,last_event_at,sender,bytes) VALUES (?,1,?,?,UTC_TIMESTAMP(6)-INTERVAL 1 DAY,UTC_TIMESTAMP(6),?,1024)', [$instance, 'synthetic-generation-' . $n, '123', 'sender@example.invalid']);
    $db->execute_query('INSERT INTO mail_stats_attempts (instance_id,source_id,message_id,generation,attempt_key,recipient,started_at,finished_at,outcome) VALUES (?,1,?,?,?,?,UTC_TIMESTAMP(6)-INTERVAL 1 HOUR,UTC_TIMESTAMP(6),?)', [$instance, $n, 'synthetic-generation-' . $n, 'attempt-' . $n, 'example.invalid-recipient@example.invalid', 'success']);
}
for ($n = 1; $n <= 110; $n++) {
    $source = $n > 105 ? $n - 104 : 1;
    $component = $source === 5 ? 'freshclam' : $sources[$source - 1][0];
    $type = $source === 1 ? 'delivery_local_success' : 'service_notice';
    $metadata = ['reason_code'=>'synthetic_<script>alert(1)</script>', 'outcome'=>'success',
                 'recognized'=>true, 'time_format'=>'s6-utc', 'time_uncertain'=>false, 'subsource'=>$component];
    if ($source === 1) $metadata['delivery_kind'] = 'local';
    if ($n === 109) $metadata = array_replace($metadata, ['incomplete'=>true, 'time_uncertain'=>true, 'reason_code'=>'late_archive_append']);
    if ($n === 108) { $type = 'http_access'; $metadata = ['http_status'=>503, 'method'=>'GET']; }
    if ($n === 107) { $type = 'spam_verdict'; $metadata = ['verdict'=>'ham', 'score'=>0, 'threshold'=>5, 'duration_ms'=>0, 'bytes'=>null]; }
    if ($n === 106) $metadata = [];
    $db->execute_query('INSERT INTO mail_stats_events (instance_id,source_id,source_position,message_id,attempt_id,generation,event_at,observed_at,component,event_type,severity,parser,parser_version,queue_id,sender,recipient,ip,account,metadata) VALUES (?,?,?,?,?,?,UTC_TIMESTAMP(6)-INTERVAL 1 HOUR,UTC_TIMESTAMP(6),?,?,?, ?,1,?,?,?,?,?,?)', [$instance, $source, 'synthetic-' . $n, $source === 1 ? ($n % 2 + 1) : null, $source === 1 ? ($n % 2 + 1) : null, $source === 1 ? 'synthetic-generation-' . ($n % 2 + 1) : null, $component, $type, 'info', 'fixture', '123', 'sender@example.invalid', $source === 1 ? 'example.invalid-recipient@example.invalid' : 'recipient@example.invalid', '192.0.2.1', 'synthetic-account', json_encode($metadata)]);
}
// Older than the first event page: rankings must use the entire selected period.
foreach ([['delivery_failure','failure',1,'trouble@failed.invalid'], ['delivery_deferral','deferral',1,'trouble@failed.invalid'], ['delivery_remote_success','success',2,'peer@remote.invalid']] as [$type,$outcome,$message,$recipient]) {
    $db->execute_query('INSERT INTO mail_stats_attempts (instance_id,source_id,message_id,generation,attempt_key,recipient,started_at,finished_at,outcome) VALUES (?,1,?,?,?,?,UTC_TIMESTAMP(6)-INTERVAL 2 HOUR,UTC_TIMESTAMP(6),?)', [$instance,$message,'synthetic-generation-'.$message,$type,$recipient,$outcome]);
    $attempt = $db->insert_id;
    $db->execute_query('INSERT INTO mail_stats_events (instance_id,source_id,source_position,message_id,attempt_id,generation,event_at,observed_at,component,event_type,severity,parser,parser_version,queue_id,sender,recipient,metadata) VALUES (?,1,?,?,?,?,UTC_TIMESTAMP(6)-INTERVAL 2 HOUR,UTC_TIMESTAMP(6),?,?,?, ?,1,?,?,?,?)', [$instance,'rank-'.$type,$message,$attempt,'synthetic-generation-'.$message,'qmail-send',$type,$outcome === 'success' ? 'info' : 'warning','fixture','123','sender@example.invalid',$recipient,json_encode(['outcome'=>$outcome])]);
}
$db->close();
echo "Synthetic browser database ready.\n";
