#!/usr/bin/env php
<?php
define('VPOPMAIL_DOMAIN_DIR', '/var/vpopmail/domains');
define('PRELINE', '| /var/qmail/bin/preline -f /usr/libexec/dovecot/deliver -d $EXT@$USER');
include '/var/qmail/control/aio-conf/mysql.php';

echo "Migrating Sieves forward to valias\n";

function doUser($domain, $user) {
    global $mysqlDb;

    echo '   # Checking user ' . $user . '@' . $domain . "\n";
    $filename = VPOPMAIL_DOMAIN_DIR . DIRECTORY_SEPARATOR . $domain . DIRECTORY_SEPARATOR . $user . '/.sieve/Base.sieve';
    $sieve = file_get_contents($filename);

    // Looking for a transfert
    $forwardStart = strpos($sieve, '# rule:[Transfert]');
    if ($forwardStart === false) return;

    // Retreiving the forward
    $forward = substr($sieve, $forwardStart + 2); // +2 to remove '# '
    $pos = strpos($forward, '# rule:');
    if ($pos !== false) {
        $forward = substr($forward, 0 ,$pos);
    }

    // We recreate sieve file
    $nsieve = substr($sieve, 0, $forwardStart);
    $pos = strpos($sieve, '# rule:', $forwardStart + 3);  // +3 to skip '# '
    if ($pos !== false) {
        $nsieve .= substr($sieve, $pos);
    }

    // Now we migrate the forward
    $isCopy = preg_match('/:copy/', $forward) !== 0;
    $pattern = '/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/';
    if (!(preg_match($pattern, $forward, $emails))) {
        echo "    > Error can't found email\n";
    }

    foreach ($emails as $email) {
        if (empty($email)) continue;
        $mysqlDb->query('INSERT INTO valias(valias_type, alias, domain, valias_line, copy)'
            . ' VALUES('
                . '1'
                . ", '" . $user . "'"
                . ", '" . $domain . "'"
                . ", '" . $email . "'"
                . ', ' . ($isCopy ? '1' : '0')
            . ');'
        );
        if ($isCopy) {
            $mysqlDb->query('INSERT INTO valias(valias_type, alias, domain, valias_line, copy)'
                . ' VALUES('
                    . '0    '
                    . ", '" . $user . "'"
                    . ", '" . $domain . "'"
                    . ", '" . PRELINE . "'"
                    . ', 0'
                . ');'
            );
        }
        echo '    > Adding forward ' . ($isCopy ? 'and copy ' : '') . 'to ' . $email . "\n";
    }

    file_put_contents($filename, $nsieve);
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

$mysqlDb = new mysqli($MYSQL_CONF['MYSQL_HOST'], $MYSQL_CONF['MYSQL_USER'], $MYSQL_CONF['MYSQL_PASS'], $MYSQL_CONF['MYSQL_DB']);
if ($mysqlDb->connect_errno) {
    die("Can't connec to mysql : " . $mysqlDb->connect_error);
}

$ddir = scandir(VPOPMAIL_DOMAIN_DIR);
foreach ($ddir as $key => $value) {
    if (!in_array($value,array(".","..")) && (is_dir(VPOPMAIL_DOMAIN_DIR . DIRECTORY_SEPARATOR . $value))) {
        doDomain($value);
    }
}
