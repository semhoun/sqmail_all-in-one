<?php
// Narrow repairs for the two historical AIO schema steps, not an application updater.
mysqli_report(MYSQLI_REPORT_ERROR | MYSQLI_REPORT_STRICT);

function columns(mysqli $db, string $table): array
{
    return array_column($db->query("SHOW COLUMNS FROM `$table`")->fetch_all(MYSQLI_ASSOC), null, 'Field');
}

function indexes(mysqli $db, string $table): array
{
    $result = [];
    foreach ($db->query("SHOW INDEX FROM `$table`")->fetch_all(MYSQLI_ASSOC) as $row) {
        $result[$row['Key_name']][(int) $row['Seq_in_index']] = [
            $row['Column_name'], (int) $row['Non_unique'], $row['Sub_part'], $row['Index_type'],
        ];
    }
    foreach ($result as &$parts) {
        ksort($parts);
    }
    return $result;
}

try {
    $db = new mysqli(getenv('MYSQL_HOST'), getenv('MYSQL_USER'), getenv('MYSQL_PASS'), getenv('MYSQL_DB'));
    $db->set_charset('utf8mb4');
    $tables = array_column($db->query('SHOW TABLES')->fetch_all(), 0);
    if (($argv[1] ?? '') === 'valias') {
        $definitions = [
            'valias_type' => "TINYINT NULL DEFAULT '1' COMMENT '1=forwarder 0=lda'",
            'id' => 'INT NOT NULL AUTO_INCREMENT PRIMARY KEY',
            'copy' => "TINYINT NULL DEFAULT '0' COMMENT '0=redirect 1=copy&redirect'",
        ];
        foreach ($definitions as $name => $definition) {
            $actual = columns($db, 'valias');
            if (!isset($actual[$name])) {
                $db->query("ALTER TABLE valias ADD `$name` $definition");
                $actual = columns($db, 'valias');
            }
            $column = $actual[$name];
            $type = preg_replace('/\(\d+\)/', '', $column['Type']);
            if ($type !== ($name === 'id' ? 'int' : 'tinyint')
                || ($name === 'id' && ($column['Extra'] !== 'auto_increment' || $column['Key'] !== 'PRI'))
                || ($name !== 'id' && ($column['Null'] !== 'YES' || (string) $column['Default'] !== ($name === 'copy' ? '0' : '1')))) {
                throw new RuntimeException("Incompatible valias.$name; no existing column was replaced");
            }
        }
        $keys = indexes($db, 'valias');
        if (($keys['PRIMARY'] ?? null) !== [1 => ['id', 0, null, 'BTREE']]) {
            throw new RuntimeException('Incompatible valias primary key');
        }
        $expected = [1 => ['alias', 1, null, 'BTREE'], 2 => ['domain', 1, null, 'BTREE'], 3 => ['valias_type', 1, null, 'BTREE']];
        if (!in_array($expected, $keys, true)) {
            $db->query('ALTER TABLE valias ADD INDEX aio_alias_domain_type (alias, domain, valias_type)');
        }
    } elseif (($argv[1] ?? '') === 'dmarc') {
        // The old dump stamps 4.0 before adding keys. Validate structure, not just its version.
        if (in_array('dmarc_system', $tables, true)) {
            $versions = $db->query("SELECT value FROM dmarc_system WHERE `key` = 'version' AND user_id = 0")->fetch_all();
            if (count($versions) > 1 || ($versions && $versions[0][0] !== '4.0')) {
                throw new RuntimeException('Unsupported or ambiguous DMARC schema version');
            }
        }
        $sql = file_get_contents('/opt/sql/dmarc.sql');
        if ($sql === false) {
            throw new RuntimeException('Cannot read DMARC schema');
        }
        // Build session-local expected tables from the shipped dump, including its later ALTERs.
        preg_match_all('/(?:CREATE TABLE|ALTER TABLE) `dmarc_[a-z]+`[^;]+;/s', $sql, $statements);
        $expectedTables = [];
        foreach ($statements[0] as $statement) {
            preg_match('/`(dmarc_[a-z]+)`/', $statement, $match);
            $table = $match[1];
            $expectedTables[$table] = 'aio_expected_' . $table;
            $statement = str_replace("`$table`", "`aio_expected_$table`", $statement);
            $db->query(str_replace('CREATE TABLE', 'CREATE TEMPORARY TABLE', $statement));
        }
        if (count($expectedTables) !== 7) {
            throw new RuntimeException('Unexpected shipped DMARC schema');
        }
        foreach ($expectedTables as $table => $temporary) {
            if (!in_array($table, $tables, true)) {
                $create = $db->query("SHOW CREATE TABLE `$temporary`")->fetch_row()[1];
                $db->query(str_replace(['CREATE TEMPORARY TABLE', "`$temporary`"], ['CREATE TABLE', "`$table`"], $create));
                continue;
            }
            $actual = columns($db, $table);
            $expected = columns($db, $temporary);
            if (array_keys($actual) !== array_keys($expected)) {
                throw new RuntimeException("Incompatible columns in $table; manual reconciliation required");
            }
            foreach ($expected as $name => $column) {
                $found = $actual[$name];
                // Missing keys and auto_increment are the known interrupted dump states.
                unset($column['Key'], $found['Key']);
                if ($name === 'id' && $found['Extra'] === '') {
                    $found['Extra'] = $column['Extra'];
                }
                if ($column !== $found) {
                    throw new RuntimeException("Incompatible $table.$name; no data was overwritten");
                }
            }
            $keys = indexes($db, $table);
            foreach (indexes($db, $temporary) as $name => $parts) {
                if (isset($keys[$name])) {
                    if ($keys[$name] !== $parts) {
                        throw new RuntimeException("Incompatible $table index $name");
                    }
                    continue;
                }
                $fields = implode(',', array_map(fn($part) => '`' . $part[0] . '`', $parts));
                $key = $name === 'PRIMARY' ? 'PRIMARY KEY' : ($parts[1][1] ? 'INDEX' : 'UNIQUE INDEX') . " `$name`";
                $db->query("ALTER TABLE `$table` ADD $key ($fields)");
            }
            if (isset($expected['id']) && $actual['id']['Extra'] === '') {
                $db->query("ALTER TABLE `$table` MODIFY id INT UNSIGNED NOT NULL AUTO_INCREMENT");
            }
        }
        $db->query("INSERT INTO dmarc_system (`key`, user_id, value) SELECT 'version', 0, '4.0'
            WHERE NOT EXISTS (SELECT 1 FROM dmarc_system WHERE `key` = 'version' AND user_id = 0)");
    } else {
        throw new RuntimeException('Expected valias or dmarc');
    }
} catch (Throwable $e) {
    // Do not print SQL/connection exception messages, which can contain credentials or data.
    $reason = get_class($e) === RuntimeException::class ? $e->getMessage() : get_class($e);
    fwrite(STDERR, 'Historical schema check failed: ' . $reason . '. Preserve the database and reconcile its schema before retrying.' . PHP_EOL);
    exit(1);
}
