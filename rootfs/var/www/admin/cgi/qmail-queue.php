#!/usr/bin/qmailq-php
<?php

echo 'Content-type: text/html; charset=utf-8' . "\n\n";

define('QUEUE_DIR', '/var/qmail/queue/');

function escapeHtml($value) {
    return htmlspecialchars((string) $value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function fatalError($msg) {
    echo $msg;
    die();
}

function getAddressFromFile($file) {
    $addr = file_get_contents($file);
    $addr = substr($addr, 1); // Remove the first char
    $addr = trim($addr);
    return $addr;
}

function getMessages() {
    $messages = [];

    /* First we get all message info with info directory */
    $handle = opendir(QUEUE_DIR . 'info');
    if ($handle === false) fatalError("Can't open: " . QUEUE_DIR . 'info');
    while (false !== ($split = readdir($handle))) {
        if (!is_dir(QUEUE_DIR . 'info' . '/' . $split) || $split == "." || $split == "..") continue;
        $shandle = opendir(QUEUE_DIR . 'info'. '/' . $split);
        if ($shandle === false) fatalError("Can't open: " . QUEUE_DIR . 'info' . '/' . $split);
        while (false !== ($msgId = readdir($shandle))) {
            if ($msgId == "." || $msgId == "..") continue;
            $messages[$msgId] = [
                'ext_id' => $split . '@' . $msgId,
                'id' => $msgId,
                'split' => $split,
                'from' => getAddressFromFile(QUEUE_DIR . 'info' . '/' . $split . '/' .$msgId),
                'direction' => NULL,
				'date' => NULL,
                'subject' => NULL,
                'size' => NULL
            ];
        }
    }

    /* Second we look for local info */
    $handle = opendir(QUEUE_DIR . 'local');
    if ($handle === false) fatalError("Can't open: " . QUEUE_DIR . 'local');
    while (false !== ($split = readdir($handle))) {
        if (!is_dir(QUEUE_DIR . 'local' . '/' . $split) || $split == "." || $split == "..") continue;
        $shandle = opendir(QUEUE_DIR . 'local'. '/' . $split);
        if ($shandle === false) fatalError("Can't open: " . QUEUE_DIR . 'local' . '/' . $split);
        while (false !== ($msgId = readdir($shandle))) {
            if ($msgId == "." || $msgId == "..") continue;
            $messages[$msgId]['to'] = getAddressFromFile(QUEUE_DIR . 'local' . '/' . $split . '/' .$msgId);
            $messages[$msgId]['direction'] = 'local';
        }
    }

    /* third we look for remote info */
    $handle = opendir(QUEUE_DIR . 'remote');
    if ($handle === false) fatalError("Can't open: " . QUEUE_DIR . 'remote');
    while (false !== ($split = readdir($handle))) {
        if (!is_dir(QUEUE_DIR . 'remote' . '/' . $split) || $split == "." || $split == "..") continue;
        $shandle = opendir(QUEUE_DIR . 'remote'. '/' . $split);
        if ($shandle === false) fatalError("Can't open: " . QUEUE_DIR . 'remote' . '/' . $split);
        while (false !== ($msgId = readdir($shandle))) {
            if ($msgId == "." || $msgId == "..") continue;
            $messages[$msgId]['to'] = getAddressFromFile(QUEUE_DIR . 'remote' . '/' . $split . '/' .$msgId);
            $messages[$msgId]['direction'] = 'remote';
        }
    }

    /* Get mail content */
    $handle = opendir(QUEUE_DIR . 'mess');
    if ($handle === false) fatalError("Can't open: " . QUEUE_DIR . 'mess');
    while (false !== ($split = readdir($handle))) {
        if (!is_dir(QUEUE_DIR . 'mess' . '/' . $split) || $split == "." || $split == "..") continue;
        $shandle = opendir(QUEUE_DIR . 'mess'. '/' . $split);
        if ($shandle === false) fatalError("Can't open: " . QUEUE_DIR . 'mess' . '/' . $split);
        while (false !== ($msgId = readdir($shandle))) {
            if ($msgId == "." || $msgId == "..") continue;
            $fh = fopen(QUEUE_DIR . 'mess' . '/' . $split . '/' .$msgId, 'rb');
            $fContents = fread($fh, 2048);
            fclose($fh);
            $messages[$msgId]['size'] = filesize(QUEUE_DIR . 'mess' . '/' . $split . '/' .$msgId);
            if (preg_match('/^Subject: (.*)/im', $fContents, $subject)) {
                $messages[$msgId]['subject'] = $subject[1];
            }
            if (preg_match('/^Date: (.*)/im', $fContents, $date)) {
				try {
					$messages[$msgId]['date'] = new DateTime($date[1]);
				}
				catch (Exception $e) {
				}
            }
        }
    }

    return $messages;
}

function getQuery() {
    $query = parse_url($_SERVER["REQUEST_URI"], PHP_URL_QUERY);
    if (empty($query)) return [];
    $parts = explode("&", $query);
    $datas = [];
    foreach($parts as $p){
        $arg = explode("=",$p);
        $datas[$arg[0]] = $arg[1];
    }
    return $datas;
}

function removeMessage($msgId) {
    // First stop qmail-send
    exec('/bin/s6-svc -d /service/qmail-send');

    $msgInfo = explode("@", $msgId);
    if (count($msgInfo) == 2) {
        $split = $msgInfo[0];
        $msgId = $msgInfo[1];

        @unlink(QUEUE_DIR . 'mess' . '/' . $split . '/' .$msgId);
        @unlink(QUEUE_DIR . 'info' . '/' . $split . '/' .$msgId);
        @unlink(QUEUE_DIR . 'local' . '/' . $split . '/' .$msgId);
        @unlink(QUEUE_DIR . 'remote' . '/' . $split . '/' .$msgId);
    }

    // Finally relaunch qmail-send
    exec('/bin/s6-svc -u /service/qmail-send');
}

function viewMessage($msgId) {
    $msgInfo = explode("@", $msgId);
    if (count($msgInfo) != 2) return;

    $split = $msgInfo[0];
    $msgId = $msgInfo[1];

    $msg = file_get_contents(QUEUE_DIR . 'mess' . '/' . $split . '/' .$msgId);
    $msg = trim($msg);

    echo '<section class="queue-preview" aria-labelledby="message-title">'
      . '<header><div><p class="queue-caption">Message source</p>'
      . '<h2 id="message-title">Message ' . escapeHtml($split . '/' . $msgId) . '</h2></div>'
      . '<a class="queue-button" href="/cgi/qmail-queue.php">Close preview</a></header>'
      . '<pre tabindex="0" aria-label="Message source">' . escapeHtml($msg) . '</pre>'
      . '</section>';
}

function doQueue() {
    exec('/bin/s6-svc -a /service/qmail-send');
}

$GET = getQuery();
if (!empty($GET['action']) && $GET['action'] == 'remove' && !empty($GET['id'])) removeMessage($GET['id']);
if (!empty($GET['action']) && $GET['action'] == 'doqueue') doQueue();

$messages = getMessages();
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>SQMail AIO - Mail queue</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="/css/bootstrap.min.css">
    <link rel="stylesheet" href="/css/style.css">
</head>
<body class="admin-page queue-page">
<div class="admin-shell queue-shell">
    <header class="admin-header">
        <div class="login-brand" aria-label="SQMail All-in-One">
            <span class="login-mark" aria-hidden="true">
                <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.6">
                    <rect x="4" y="7" width="24" height="18" rx="4" /><path d="m5 9 11 9L27 9" />
                </svg>
            </span>
            <span>SQMail <span class="login-brand-edition">All-in-One</span></span>
        </div>
        <a class="queue-button" href="/">Administration</a>
    </header>
    <main>
        <div class="queue-heading">
            <header class="login-heading admin-heading">
                <p class="login-eyebrow">Message delivery</p>
                <h1>Mail queue.</h1>
                <p>Inspect pending messages and manage their delivery.</p>
            </header>
            <a class="queue-button queue-button-primary" href="/cgi/qmail-queue.php?action=doqueue">
                <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                    <path d="M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 14 6M4 12a8 8 0 0 0 14 6" />
                </svg>
                Process queue now
            </a>
        </div>
<?php
    if (!empty($GET['action']) && $GET['action'] == 'view' && !empty($GET['id'])) viewMessage($GET['id']);
?>
    <section class="queue-panel" aria-labelledby="queue-title">
        <header class="queue-panel-header">
            <h2 id="queue-title">Pending messages <span class="queue-count"><?= count($messages) ?></span></h2>
            <a class="queue-refresh" href="/cgi/qmail-queue.php">Refresh list <span aria-hidden="true">&orarr;</span></a>
        </header>
        <?php if (empty($messages)) { ?>
        <div class="queue-empty">
            <span class="admin-tool-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <rect x="3" y="3" width="18" height="18" rx="4" /><path d="m7 12 3 3 7-7" />
                </svg>
            </span>
            <h3>The queue is empty.</h3>
            <p>There are no queued messages to display.</p>
        </div>
        <?php } else { ?>
    <p class="queue-scroll-hint" id="queue-scroll-hint">Scroll horizontally to see all message details and actions.</p>
    <div class="queue-table-scroll" role="region" aria-label="Pending messages" aria-describedby="queue-scroll-hint" tabindex="0">
    <table class="queue-table">
    <thead>
        <tr>
            <th scope="col">ID</th>
            <th scope="col">Direction</th>
            <th scope="col">From</th>
            <th scope="col">To</th>
            <th scope="col">Date</th>
            <th scope="col">Subject</th>
            <th scope="col">Size</th>
            <th scope="col">Actions</th>
        </tr>
    </thead>
    <tbody>
        <?php
        foreach ($messages as $msg) {
            $bytes = $msg['size'] ?? 0;
            $size = $bytes >= 1048576 ? round($bytes / 1048576, 2) . ' MiB'
                : ($bytes >= 1024 ? round($bytes / 1024, 2) . ' KiB' : $bytes . ' B');
            $direction = $msg['direction'] ?? '';
        ?>
        <tr>
            <th scope="row" class="queue-id"><?= escapeHtml($msg['id'] ?? '') ?></th>
            <td><span class="queue-badge <?= $direction === 'local' ? 'queue-badge-local' : '' ?>"><?= escapeHtml($direction ?: 'Pending') ?></span></td>
            <td class="queue-address"><?= escapeHtml($msg['from'] ?? '') ?></td>
            <td class="queue-address"><?= escapeHtml($msg['to'] ?? '') ?></td>
            <td class="queue-date"><?= !empty($msg['date']) ? escapeHtml($msg['date']->format('Y/m/d H:i:s')) : '&mdash;' ?></td>
            <td class="queue-subject"><?= escapeHtml(($msg['subject'] ?? '') ?: '(No subject)') ?></td>
            <td class="queue-size"><?= escapeHtml($size) ?></td>
            <td><div class="queue-actions">
                <a class="queue-button" href="/cgi/qmail-queue.php?action=view&amp;id=<?= escapeHtml($msg['ext_id'] ?? '') ?>" aria-label="View message <?= escapeHtml($msg['id'] ?? '') ?>">View</a>
                <a class="queue-button queue-remove" href="/cgi/qmail-queue.php?action=remove&amp;id=<?= escapeHtml($msg['ext_id'] ?? '') ?>" aria-label="Remove message <?= escapeHtml($msg['id'] ?? '') ?>">Remove</a>
            </div></td>
        </tr>
        <?php } ?>
    </tbody>
    </table>
    </div>
        <p class="queue-footnote">Removing a message permanently deletes it from the queue.</p>
        <?php } ?>
    </section>
    </main>
    <footer class="admin-footer">
        <span>QMail Queue</span>
        <a href="/">Back to administration <span aria-hidden="true">&rarr;</span></a>
    </footer>
</div>
</body>

</html>
