#!/usr/bin/qmailq-php
<?php

echo 'Content-type: text/html; charset=utf-8' . "\n\n";

define('QUEUE_DIR', '/var/qmail/queue/');

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
                'direction' => NULL
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
            $fContents = fread($fh,1024);
            fclose($fh);
            $messages[$msgId]['size'] = filesize(QUEUE_DIR . 'mess' . '/' . $split . '/' .$msgId);
            if (preg_match_all('/Subject: (.*)/i', $fContents, $subject)) {
                $messages[$msgId]['subject'] = $subject[1][0];
            }
            else {
                $messages[$msgId]['subject'] = "";
            }
            if (preg_match_all('/Date: (.*)/i', $fContents, $date)) {
                $messages[$msgId]['date'] = new DateTime($date[1][0]);
            }
            else {
                $messages[$msgId]['date'] = "";
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

    echo
      '<figure class="text-center">'
      . '<blockquote class="blockquote">'
      . '<figcaption class="blockquote-footer">Message ' . $split . '/' .$msgId . '</figcaption>'
      . '<pre>' . $msg . '</pre>'
      . '</blockquote>'
      . '</figure>';
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
<html lang="en" >

<head><meta http-equiv="Content-Type" content="text/html; charset=windows-1252">
    
    <title>QMail AIO - Admin</title>

    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="/css/bootstrap.min.css">
    <link rel="stylesheet" href="/css/line-awesome.min.css">
</head>

<body>
    <div class="container">
    <div class="col-xs-12">
      <div class="text-center" style="padding-top: 30px; padding-bottom: 30px;">
          <h2>QMail Queue</h2>
      </div>
    </div>
    </div>
 
    <h3 class="text-center"><a href="/cgi/qmail-queue.php?action=doqueue">Force queue process <i class="las la-redo-alt"></i></a></h3>
<?php
    if (!empty($GET['action']) && $GET['action'] == 'view' && !empty($GET['id'])) viewMessage($GET['id']);
?>
    <table class="table table-striped">
    <thead>
        <tr>
            <th scope="col">id</th>
            <th scope="col">Direction</th>
            <th scope="col">From</th>
            <th scope="col">To</th>
            <th scope="col">Date</th>
            <th scope="col">Subject</th>
            <th scope="col">Size</th>
            <th scope="col">Action</th>
        </tr>
    </thead>
    <tbody>
<?php
    foreach ($messages as $msg) {
        echo '
        <tr>
            <td>'. $msg['id'] . '</td>
            <td>'. $msg['direction'] . '</td>
            <td>'. $msg['from'] . '</td>
            <td>'. $msg['to'] . '</td>
            <td>'. $msg['date']->format('Y/m/d H:i:s') . '</td>
            <td>'. $msg['subject'] . '</td>
            <td>'. $msg['size'] . ' bytes</td>
            <td><a href="/cgi/qmail-queue.php?action=remove&id=' . $msg['ext_id'] . '" data-toggle="tooltip" title="Remove this mail"><i class="las la-trash"></i></a> <a href="/cgi/qmail-queue.php?action=view&id=' . $msg['ext_id'] . '" data-toggle="tooltip" title="View this mail"><i class="las la-eye"></i></a></td>
        </tr>
';
    }
?>
    </tbody>
    </table>

    <script src="/js/jquery-3.6.0.slim.min.js"></script>
    <script src="/js/bootstrap.bundle.min.js"></script>
    <script>
    $(function () {
      $('[data-toggle="tooltip"]').tooltip()
    })
    </script>
</body>

</html>
