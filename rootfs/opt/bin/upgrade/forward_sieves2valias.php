#!/usr/bin/env php
<?php
define('VPOPMAIL_DOMAIN_DIR', '/var/vpopmail/domains');
define('PRELINE', '| /var/qmail/bin/preline -f /usr/libexec/dovecot/deliver -d $EXT@$USER');
require '/var/qmail/control/aio-conf/mysql.php';
mysqli_report(MYSQLI_REPORT_ERROR | MYSQLI_REPORT_STRICT);
set_error_handler(static function ($severity, $message, $file, $line) {
    throw new ErrorException($message, 0, $severity, $file, $line);
});

echo "Migrating Sieves forward to valias\n";

function doUser($domain, $user) {
    global $mysqlDb;

    echo '   # Checking user ' . $user . '@' . $domain . "\n";
    $filename = VPOPMAIL_DOMAIN_DIR . DIRECTORY_SEPARATOR . $domain . DIRECTORY_SEPARATOR . $user . '/.sieve/Base.sieve';
    if (is_link($filename) || !is_file($filename)) {
        throw new RuntimeException('Expected a regular Sieve file');
    }
    $stat = stat($filename);
    $sieve = file_get_contents($filename);

    // Looking for a transfert
    $forwardStart = strpos($sieve, '# rule:[Transfert]');
    if ($forwardStart === false) return;

    $pos = strpos($sieve, '# rule:', $forwardStart + 3);  // +3 to skip '# '
    $length = ($pos === false ? strlen($sieve) : $pos) - $forwardStart;
    $forward = substr($sieve, $forwardStart, $length);
    // Only the historical unconditional, single-destination rule is equivalent to valias.
    if (!preg_match('/\A# rule:\[Transfert\]\s*if\s+true\s*\{\s*redirect\s+(:copy\s+)?"([^"\\\\]+)"\s*;\s*\}\s*\z/', $forward, $match)
        || !filter_var($match[2], FILTER_VALIDATE_EMAIL)
        || substr_count($sieve, '# rule:[Transfert]') !== 1) {
        throw new RuntimeException('Unsupported forwarding rule; Sieve file retained');
    }
    $isCopy = $match[1] !== '';
    $rows = [[1, $user, $domain, $match[2], $isCopy ? 1 : 0]];
    if ($isCopy) {
        $rows[] = [0, $user, $domain, PRELINE, 0];
    }
    $mysqlDb->begin_transaction();
    foreach ($rows as $row) {
        // Reconcile exact rows before rewriting the file, including after a failed rename.
        $statement = $mysqlDb->prepare('INSERT INTO valias(valias_type, alias, domain, valias_line, copy)
            SELECT ?, ?, ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM valias
            WHERE valias_type = ? AND alias = ? AND domain = ? AND BINARY valias_line = BINARY ? AND copy = ?)');
        $statement->execute(array_merge($row, $row));
    }
    $mysqlDb->commit();
    $nsieve = substr_replace($sieve, '', $forwardStart, $length);
    $temporary = tempnam(dirname($filename), '.aio-sieve-');
    try {
        if (file_put_contents($temporary, $nsieve) !== strlen($nsieve)) {
            throw new RuntimeException('Incomplete Sieve write');
        }
        chown($temporary, $stat['uid']);
        chgrp($temporary, $stat['gid']);
        chmod($temporary, $stat['mode'] & 0777);
        if (file_get_contents($filename) !== $sieve) {
            throw new RuntimeException('Sieve changed concurrently; original retained');
        }
        rename($temporary, $filename);
    } finally {
        if (is_file($temporary)) {
            unlink($temporary);
        }
    }
}

function doDomain($domain) {
    echo '  -> Doing domain ' . $domain . "\n";
    $udir = scandir(VPOPMAIL_DOMAIN_DIR . DIRECTORY_SEPARATOR . $domain);
    foreach ($udir as $key => $value) {
        if (!in_array($value,array(".","..")) && (is_dir(VPOPMAIL_DOMAIN_DIR . DIRECTORY_SEPARATOR . $domain . DIRECTORY_SEPARATOR . $value))) {
            if (file_exists(VPOPMAIL_DOMAIN_DIR . DIRECTORY_SEPARATOR . $domain . DIRECTORY_SEPARATOR . $value . '/.sieve/Base.sieve')) {
                doUser($domain, $value);
            }
        }
    }
}

try {
    $mysqlDb = new mysqli($MYSQL_CONF['MYSQL_HOST'], $MYSQL_CONF['MYSQL_USER'], $MYSQL_CONF['MYSQL_PASS'], $MYSQL_CONF['MYSQL_DB']);
    $mysqlDb->set_charset('utf8mb4');
    $ddir = scandir(VPOPMAIL_DOMAIN_DIR);
    foreach ($ddir as $key => $value) {
        if (!in_array($value,array(".","..")) && (is_dir(VPOPMAIL_DOMAIN_DIR . DIRECTORY_SEPARATOR . $value))) {
            doDomain($value);
        }
    }
} catch (Throwable $e) {
    fwrite(STDERR, 'Forwarding migration failed (' . get_class($e) . '); original Sieve rules are retained for retry.' . PHP_EOL);
    exit(1);
}
