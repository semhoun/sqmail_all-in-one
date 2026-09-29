<?php
// Use Roundcube's updater and packaged SQL. Only its non-atomic final DDL/DML
// step needs special handling so a retry never adds ten minutes twice.
define('INSTALL_PATH', '/var/www/html/');
require INSTALL_PATH . 'program/include/clisetup.php';

function checkedQuery(string $sql, ...$params)
{
    $db = rcmail_utils::db();
    $result = $db->query($sql, ...$params);
    if ($result === false || $db->is_error()) {
        throw new RuntimeException('Roundcube schema query failed: ' . ($db->is_error() ?: 'unknown database error'));
    }
    return $result;
}

$temporary = null;
try {
    $db = rcmail_utils::db();
    $db->set_option('ignore_errors', true);
    if ($db->db_provider !== 'mysql' || $rcmail->config->get('db_prefix') !== 'rcb_') {
        throw new RuntimeException('Expected the AIO MySQL schema with rcb_ prefix');
    }
    $versions = checkedQuery("SELECT value FROM rcb_system WHERE name = 'roundcube-version'")->fetchAll(PDO::FETCH_COLUMN);
    $supported = ['2020122900', '2021081000', '2021100300', '2022081200', '2022100100', '2025092300'];
    if (count($versions) !== 1 || !in_array($versions[0], $supported, true)) {
        throw new RuntimeException('Unsupported Roundcube schema version');
    }
    $version = $versions[0];
    $temporary = sys_get_temp_dir() . '/aio-roundcube-' . bin2hex(random_bytes(12));
    if (!mkdir($temporary . '/mysql', 0700, true)) {
        throw new RuntimeException('Cannot prepare Roundcube updater');
    }
    $tables = checkedQuery('SHOW TABLES')->fetchAll(PDO::FETCH_COLUMN);
    foreach (['2021081000' => 'responses', '2022100100' => 'uploads'] as $step => $table) {
        $sql = file_get_contents(INSTALL_PATH . "SQL/mysql/$step.sql");
        if ($sql === false || !str_starts_with($sql, "CREATE TABLE `$table`")) {
            throw new RuntimeException('Unexpected Roundcube migration SQL');
        }
        if (in_array('rcb_' . $table, $tables, true)) {
            // Compare existing/partially-created tables to the packaged upstream definition.
            $expected = preg_replace('/CONSTRAINT.*?ON DELETE CASCADE ON UPDATE CASCADE,\s*/s', '', $sql);
            $expected = str_replace("CREATE TABLE `$table`", "CREATE TEMPORARY TABLE `aio_expected_$table`", $expected);
            checkedQuery(rtrim(trim($expected), ';'));
            $actualColumns = checkedQuery("SHOW FULL COLUMNS FROM `rcb_$table`")->fetchAll(PDO::FETCH_ASSOC);
            $expectedColumns = checkedQuery("SHOW FULL COLUMNS FROM `aio_expected_$table`")->fetchAll(PDO::FETCH_ASSOC);
            if ($actualColumns !== $expectedColumns) {
                throw new RuntimeException("Incompatible Roundcube $table columns");
            }
            $actualKeys = checkedQuery("SHOW INDEX FROM `rcb_$table`")->fetchAll(PDO::FETCH_ASSOC);
            $expectedKeys = checkedQuery("SHOW INDEX FROM `aio_expected_$table`")->fetchAll(PDO::FETCH_ASSOC);
            $normalize = static function ($rows) {
                return array_map(static fn($r) => [$r['Non_unique'], $r['Seq_in_index'], $r['Column_name'], $r['Sub_part'], $r['Index_type']], $rows);
            };
            if ($normalize($actualKeys) !== $normalize($expectedKeys)) {
                throw new RuntimeException("Incompatible Roundcube $table indexes");
            }
            if ($table === 'responses') {
                $foreignKeys = checkedQuery("SELECT k.COLUMN_NAME, k.REFERENCED_TABLE_NAME, k.REFERENCED_COLUMN_NAME,
                    r.UPDATE_RULE, r.DELETE_RULE FROM information_schema.KEY_COLUMN_USAGE k
                    JOIN information_schema.REFERENTIAL_CONSTRAINTS r ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA
                    AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME AND r.TABLE_NAME=k.TABLE_NAME
                    WHERE k.TABLE_SCHEMA=DATABASE() AND k.TABLE_NAME='rcb_responses'")->fetchAll(PDO::FETCH_NUM);
                if ($foreignKeys !== [['user_id', 'rcb_users', 'user_id', 'CASCADE', 'CASCADE']]) {
                    throw new RuntimeException('Incompatible Roundcube responses foreign key');
                }
            }
            $sql = "-- Already created and verified after an interrupted upstream step.\n";
        } elseif ($version >= $step) {
            throw new RuntimeException("Roundcube marker precedes missing $table table");
        }
        if (file_put_contents($temporary . "/mysql/$step.sql", $sql) !== strlen($sql)) {
            throw new RuntimeException('Cannot prepare Roundcube SQL');
        }
    }
    foreach (['2021100300', '2022081200'] as $step) {
        if (!copy(INSTALL_PATH . "SQL/mysql/$step.sql", $temporary . "/mysql/$step.sql")) {
            throw new RuntimeException('Cannot copy Roundcube SQL');
        }
    }
    if (!rcmail_utils::db_update($temporary, 'roundcube')) {
        throw new RuntimeException('Upstream Roundcube update failed: ' . ($db->is_error() ?: 'unknown database error'));
    }
    // MariaDB DDL commits implicitly. Repeat only missing structural operations;
    // commit the data conversion together with its application version afterwards.
    $columns = checkedQuery('SHOW COLUMNS FROM rcb_session')->fetchAll(PDO::FETCH_UNIQUE | PDO::FETCH_ASSOC);
    if (isset($columns['changed']) === isset($columns['expires_at'])) {
        throw new RuntimeException('Ambiguous Roundcube session columns');
    }
    $dateColumn = $columns['changed'] ?? $columns['expires_at'];
    if ($dateColumn['Type'] !== 'datetime' || $dateColumn['Null'] !== 'NO'
        || ($dateColumn['Default'] !== "'1000-01-01 00:00:00'" && $dateColumn['Default'] !== '1000-01-01 00:00:00')) {
        throw new RuntimeException('Incompatible Roundcube session date column');
    }
    if (isset($columns['changed'])) {
        if ($version === '2025092300') {
            throw new RuntimeException('Roundcube session schema contradicts its marker');
        }
        checkedQuery("ALTER TABLE rcb_session CHANGE COLUMN changed expires_at datetime NOT NULL DEFAULT '1000-01-01 00:00:00'");
    }
    $indexes = checkedQuery('SHOW INDEX FROM rcb_session')->fetchAll(PDO::FETCH_ASSOC);
    $names = array_column($indexes, 'Key_name');
    foreach (['PRIMARY' => 'sess_id', 'rcb_changed_index' => 'expires_at', 'rcb_expires_at_index' => 'expires_at'] as $name => $column) {
        $parts = array_values(array_filter($indexes, static fn($r) => $r['Key_name'] === $name));
        if (($name === 'PRIMARY' || $parts) && (count($parts) !== 1 || $parts[0]['Column_name'] !== $column || $parts[0]['Sub_part'] !== null)) {
            throw new RuntimeException('Incompatible Roundcube session index');
        }
    }
    if (in_array('rcb_changed_index', $names, true)) {
        checkedQuery('ALTER TABLE rcb_session DROP INDEX rcb_changed_index');
    }
    if (!in_array('rcb_expires_at_index', $names, true)) {
        checkedQuery('ALTER TABLE rcb_session ADD INDEX rcb_expires_at_index (expires_at)');
    }
    checkedQuery('SELECT sess_id, expires_at, ip, vars FROM rcb_session LIMIT 0');
    if ($version !== '2025092300') {
        $engines = checkedQuery("SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()
            AND TABLE_NAME IN ('rcb_session', 'rcb_system')")->fetchAll(PDO::FETCH_COLUMN);
        if ($engines !== ['InnoDB', 'InnoDB']) {
            throw new RuntimeException('Roundcube session conversion requires transactional tables');
        }
        checkedQuery('START TRANSACTION');
        $current = checkedQuery("SELECT value FROM rcb_system WHERE name='roundcube-version' FOR UPDATE")->fetchColumn();
        if ($current !== '2022100100') {
            throw new RuntimeException('Roundcube schema changed concurrently');
        }
        checkedQuery("UPDATE rcb_session SET expires_at = ADDTIME(expires_at, '00:10:00')");
        checkedQuery("UPDATE rcb_system SET value='2025092300' WHERE name='roundcube-version'");
        checkedQuery('COMMIT');
    }
    if (rcmail_utils::db_version('roundcube') !== '2025092300') {
        throw new RuntimeException('Roundcube schema postcondition failed');
    }
} catch (Throwable $e) {
    $reason = get_class($e) === RuntimeException::class ? $e->getMessage() : get_class($e);
    fwrite(STDERR, 'Roundcube schema migration failed: ' . $reason . '; no AIO checkpoint was advanced.' . PHP_EOL);
    exit(1);
} finally {
    if ($temporary !== null && is_dir($temporary . '/mysql')) {
        foreach (glob($temporary . '/mysql/*.sql') as $file) {
            unlink($file);
        }
        rmdir($temporary . '/mysql');
        rmdir($temporary);
    }
}
