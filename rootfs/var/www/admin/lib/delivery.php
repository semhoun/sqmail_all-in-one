<?php
declare(strict_types=1);

const DELIVERY_REQUEST_MAX = 262144;
const DELIVERY_SCRIPT_MAX = 131072;
const DELIVERY_OUTPUT_MAX = 1048576;

function delivery_escape(mixed $value): string
{
    return htmlspecialchars((string) $value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function delivery_string(array $input, string $key, string $default = ''): string
{
    if (!isset($input[$key])) return $default;
    if (!is_string($input[$key])) throw new RuntimeException('Invalid request field: ' . $key);
    return $input[$key];
}

function delivery_boot(): void
{
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
    if ((int) ($_SERVER['CONTENT_LENGTH'] ?? 0) > DELIVERY_REQUEST_MAX) {
        http_response_code(413);
        exit('Request exceeds the 256 KiB limit.');
    }
    $body = fopen('php://input', 'rb');
    if ($body === false || strlen((string) stream_get_contents($body, DELIVERY_REQUEST_MAX + 1)) > DELIVERY_REQUEST_MAX) {
        http_response_code(413);
        exit('Request exceeds the 256 KiB limit.');
    }
    fclose($body);
    session_name('__Host-sqmail-login');
    session_save_path('/run/sqmail-admin/');
    ini_set('session.use_strict_mode', '1');
    ini_set('session.gc_maxlifetime', '3600');
    session_set_cookie_params(['path' => '/', 'secure' => true, 'httponly' => true, 'samesite' => 'Strict']);
    if (!session_start()) throw new RuntimeException('Session unavailable.');
    $_SESSION['csrf'] ??= bin2hex(random_bytes(32));
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && (!is_string($_POST['csrf'] ?? null) || !hash_equals($_SESSION['csrf'], $_POST['csrf']))) {
        http_response_code(403);
        exit('Session expired or invalid CSRF token. Reload the page before trying again.');
    }
}

function delivery_call(string $operation, array $fields = []): array
{
    $token = $_COOKIE['__Host-sqmail-admin'] ?? '';
    if (!is_string($token) || !preg_match('/\A[a-f0-9]{64}\z/', $token)) throw new RuntimeException('Portal session expired. Sign in again.');
    $request = json_encode(['operation' => $operation, 'token' => $token] + $fields, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    if (strlen($request) > DELIVERY_REQUEST_MAX) throw new RuntimeException('Request exceeds the 256 KiB limit.');
    $process = proc_open(['/usr/bin/sudo', '-n', '/opt/libexec/delivery-admin'], [0 => ['pipe', 'r'], 1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes, '/', ['PATH' => '/usr/bin:/bin', 'LANG' => 'C.UTF-8']);
    if (!is_resource($process)) throw new RuntimeException('Delivery service unavailable.');
    $stdout = $stderr = '';
    $offset = 0;
    // Leave time for the helper's 110-second operation deadline and audit response.
    $deadline = hrtime(true) + 60_000_000_000;
    $exit = -1;
    try {
        foreach ($pipes as $pipe) stream_set_blocking($pipe, false);
        while (true) {
            if (hrtime(true) > $deadline) throw new RuntimeException('Delivery service timed out. Reload to inspect the current state before retrying.');
            if (isset($pipes[0]) && $offset === strlen($request)) { fclose($pipes[0]); unset($pipes[0]); }
            $read = array_values(array_filter([$pipes[1], $pipes[2]], static fn($pipe) => !feof($pipe)));
            $write = isset($pipes[0]) ? [$pipes[0]] : [];
            $except = [];
            if ($read || $write) {
                if (stream_select($read, $write, $except, 0, 100000) === false) throw new RuntimeException('Delivery service communication failed.');
                foreach ($write as $pipe) {
                    $count = fwrite($pipe, substr($request, $offset, 8192));
                    if ($count === false || ($count === 0 && feof($pipe))) throw new RuntimeException('Delivery service rejected the request.');
                    $offset += $count;
                }
                foreach ($read as $pipe) {
                    $chunk = fread($pipe, 8192);
                    if ($chunk === false) throw new RuntimeException('Delivery service communication failed.');
                    if ($pipe === $pipes[1]) $stdout .= $chunk; else $stderr .= $chunk;
                    if (strlen($stdout) + strlen($stderr) > DELIVERY_OUTPUT_MAX) throw new RuntimeException('Delivery service output exceeded its limit.');
                }
            } else {
                usleep(10000);
            }
            $status = proc_get_status($process);
            if (!$status['running'] && feof($pipes[1]) && feof($pipes[2])) { $exit = $status['exitcode']; break; }
        }
    } finally {
        foreach ($pipes as $pipe) fclose($pipe);
        if (proc_get_status($process)['running']) proc_terminate($process, 9);
        proc_close($process);
        // Only structured, helper-sanitized audit records enter the web error log.
        foreach (explode("\n", $stderr) as $line) {
            $record = json_decode($line, true);
            if (is_array($record) && !array_is_list($record)) error_log('delivery-admin: ' . json_encode($record, JSON_INVALID_UTF8_SUBSTITUTE));
        }
    }
    $response = json_decode($stdout, true);
    if (!is_array($response) || !is_bool($response['ok'] ?? null)) throw new RuntimeException('Invalid delivery service response. Reload to inspect the current state.');
    if (!$response['ok']) throw new RuntimeException(is_string($response['error']['message'] ?? null) ? $response['error']['message'] : 'Delivery operation failed.');
    if ($exit !== 0 || !is_array($response['data'] ?? null)) throw new RuntimeException('Delivery service failed. Reload to inspect the current state.');
    return $response['data'];
}

function delivery_hidden(string $name, string $value): void
{
    echo '<input type="hidden" name="' . delivery_escape($name) . '" value="' . delivery_escape($value) . '">';
}

function delivery_form(array $state, string $operation): void
{
    echo '<form method="post" action="/delivery/" class="delivery-form">';
    foreach (['csrf' => $_SESSION['csrf'], 'operation' => $operation, 'mailbox' => $state['mailbox'], 'script' => $state['sieve']['selected']['name'] ?? '', 'version' => $state['version']] as $key => $value) delivery_hidden($key, $value);
}

function delivery_url(array $fields): string
{
    return '/delivery/?' . http_build_query($fields, '', '&', PHP_QUERY_RFC3986);
}

function delivery_sieve_string(string $value): string
{
    if (str_contains($value, "\0")) throw new RuntimeException('Vacation text must not contain NUL characters.');
    return '"' . str_replace(['\\', '"', "\r\n", "\r"], ['\\\\', '\\"', "\n", "\n"], $value) . '"';
}
