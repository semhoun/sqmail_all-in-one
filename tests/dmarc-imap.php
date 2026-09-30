<?php

// Run with PHP 8.5: php tests/dmarc-imap.php /path/to/dmarc-srg
namespace DirectoryTree\ImapEngine {
    // Capture the adapter's options without opening a socket or authenticating.
    class Mailbox
    {
        public static array $params;

        public function __construct(array $params)
        {
            self::$params = array_merge(['port' => 993], $params);
        }

        public function connect(): never
        {
            throw new \ConnectionCaptured();
        }

        public function connected(): bool
        {
            return false;
        }
    }
}

namespace {
    class ConnectionCaptured extends RuntimeException {}

    $root = $argv[1] ?? '/var/www/admin/dmarc';
    require $root . '/classes/Mail/MailBox.php';
    require $root . '/classes/Mail/ImapEngine/MailBox.php';
    error_reporting(E_ALL);
    set_error_handler(function (int $severity, string $message, string $file, int $line): never {
        throw new ErrorException($message, -1, $severity, $file, $line);
    });

    foreach ([
        ['localhost', 'none', 143, null],
        ['localhost', 'starttls', 143, 'starttls'],
        ['localhost', 'ssl', 993, 'ssl'],
        ['localhost:1143', 'none', 1143, null],
        ['localhost:1993', 'ssl', 1993, 'ssl'],
    ] as [$host, $encryption, $port, $transport]) {
        $mailbox = new Liuch\DmarcSrg\Mail\ImapEngine\MailBox([
            'host' => $host,
            'username' => 'dmarc@example.test',
            'password' => 'synthetic-test-password',
            'mailbox' => 'INBOX',
            'encryption' => $encryption,
        ]);
        try {
            $mailbox->check();
            throw new RuntimeException('Connection options were not captured');
        } catch (ConnectionCaptured) {
            $params = DirectoryTree\ImapEngine\Mailbox::$params;
            if ($params['host'] !== 'localhost' || $params['port'] !== $port
                || $params['encryption'] !== $transport || $params['validate_cert'] !== true) {
                throw new RuntimeException("Incorrect IMAP options for $host ($encryption): expected port $port, got {$params['port']}");
            }
        }
        unset($mailbox);
    }

    echo "DMARC IMAP connection options passed (5 cases, no network)\n";
}
