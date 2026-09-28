<?php
declare(strict_types=1);

const AUTH_DIR = '/run/sqmail-admin/';
const AUTH_COOKIE = '__Host-sqmail-admin';
const AUTH_LIFETIME = 3600;

header('Cache-Control: no-store');
header('Content-Type: text/html; charset=UTF-8');
header("Content-Security-Policy: default-src 'none'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'");
session_name('__Host-sqmail-login');
session_save_path(AUTH_DIR);
ini_set('session.use_strict_mode', '1');
ini_set('session.gc_maxlifetime', (string) AUTH_LIFETIME);
// Debian's external session cleanup does not visit our private save path.
ini_set('session.gc_probability', '1');
ini_set('session.gc_divisor', '100');
session_set_cookie_params(['path' => '/', 'secure' => true, 'httponly' => true, 'samesite' => 'Strict']);
session_start();
$_SESSION['csrf'] ??= bin2hex(random_bytes(32));

$error = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (!is_string($_POST['csrf'] ?? null) || !hash_equals($_SESSION['csrf'], $_POST['csrf'])) {
        http_response_code(403);
        $error = 'Session expired. Reload this page and try again.';
    } elseif (($_POST['action'] ?? '') === 'logout') {
        $token = $_COOKIE[AUTH_COOKIE] ?? '';
        if (is_string($token) && preg_match('/\A[a-f0-9]{64}\z/', $token)) {
            @unlink(AUTH_DIR . 'token-' . $token);
        }
        setcookie(AUTH_COOKIE, '', ['expires' => 1, 'path' => '/', 'secure' => true, 'httponly' => true, 'samesite' => 'Strict']);
        $_SESSION = [];
        session_destroy();
        header('Location: /login.php', true, 303);
        exit;
    } else {
        $user = is_string($_POST['username'] ?? null) ? $_POST['username'] : '';
        $password = is_string($_POST['password'] ?? null) ? $_POST['password'] : '';
        // PHP locks this session. Account-wide limits would let strangers lock out
        // admin; IP-based limits belong at the trusted HTTPS proxy, not X-Forwarded-For.
        $attempts = $_SESSION['attempts'] ?? ['until' => 0, 'count' => 0];
        if ($attempts['until'] <= time()) {
            $attempts = ['until' => time() + 300, 'count' => 0];
        }
        if ($attempts['count'] >= 10) {
            http_response_code(429);
            header('Retry-After: ' . ($attempts['until'] - time()));
            $error = 'Too many attempts. Try again in five minutes.';
        } else {
            $attempts['count']++;
            $_SESSION['attempts'] = $attempts;
            $records = @file('/var/qmail/control/lighttpd-admins.htdigest', FILE_IGNORE_NEW_LINES) ?: [];
            $digest = hash('sha256', $user . ':SQMail AIO Admin:' . $password);
            $valid = false;
            foreach ($records as $record) {
                $parts = explode(':', $record);
                if (count($parts) === 3 && $parts[0] === $user && $parts[1] === 'SQMail AIO Admin') {
                    $valid = hash_equals($parts[2], $digest) || $valid;
                }
            }
            if ($valid && $user !== '' && !preg_match('/[\x00-\x1f:\x7f]/', $user)) {
                unset($_SESSION['attempts']);
                session_regenerate_id(true);
                $_SESSION['csrf'] = bin2hex(random_bytes(32));
                $token = bin2hex(random_bytes(32));
                umask(0077);
                if (file_put_contents(AUTH_DIR . 'token-' . $token, $user . "\n" . (time() + AUTH_LIFETIME) . "\n" . $digest . "\n", LOCK_EX) === false) {
                    http_response_code(503);
                    $error = 'Login temporarily unavailable.';
                } else {
                    $previous = $_COOKIE[AUTH_COOKIE] ?? '';
                    if (is_string($previous) && preg_match('/\A[a-f0-9]{64}\z/', $previous)) {
                        @unlink(AUTH_DIR . 'token-' . $previous);
                    }
                    setcookie(AUTH_COOKIE, $token, ['path' => '/', 'secure' => true, 'httponly' => true, 'samesite' => 'Strict']);
                    // Bound storage growth without touching another application's sessions.
                    foreach (glob(AUTH_DIR . 'token-*') as $file) {
                        if (filemtime($file) < time() - AUTH_LIFETIME) @unlink($file);
                    }
                    header('Location: /', true, 303);
                    exit;
                }
            } else {
                http_response_code(401);
                $error = 'Invalid username or password.';
            }
        }
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SQMail AIO - Sign in</title>
    <link rel="stylesheet" href="/css/bootstrap.min.css">
    <link rel="stylesheet" href="/css/style.css">
</head>
<body class="login-page">
<main class="login-shell">
    <div class="login-brand" aria-label="SQMail All-in-One">
        <span class="login-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.6">
                <rect x="4" y="7" width="24" height="18" rx="4" />
                <path d="m5 9 11 9L27 9" />
            </svg>
        </span>
        <span>SQMail <span class="login-brand-edition">All-in-One</span></span>
    </div>
    <section class="login-card" aria-labelledby="login-title">
            <header class="login-heading">
                <p class="login-eyebrow">Mail administration</p>
                <h1 id="login-title">Welcome back.</h1>
                <p>Sign in to manage your mail server.</p>
            </header>
            <?php if ($error !== '') { ?>
            <p class="login-error" role="alert"><?= htmlspecialchars($error, ENT_QUOTES, 'UTF-8') ?></p>
            <?php } ?>
            <form class="login-form" method="post" action="/login.php">
                <input type="hidden" name="csrf" value="<?= htmlspecialchars($_SESSION['csrf'], ENT_QUOTES, 'UTF-8') ?>">
                <div class="login-field">
                    <label for="username">Username</label>
                    <input id="username" name="username" autocomplete="username" autocapitalize="none" spellcheck="false" required autofocus>
                </div>
                <div class="login-field">
                    <label for="password">Password</label>
                    <input id="password" name="password" type="password" autocomplete="current-password" required>
                </div>
                <button class="login-submit" type="submit">
                    Sign in
                    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                        <path d="M5 12h14m-6-6 6 6-6 6" />
                    </svg>
                </button>
            </form>
            <p class="login-note">
                <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                    <rect x="5" y="10" width="14" height="11" rx="2" />
                    <path d="M8 10V7a4 4 0 0 1 8 0v3m-4 4v3" />
                </svg>
                Administrator access only
            </p>
    </section>
    <p class="login-footer">Your domains. Your mail. Your control.</p>
</main>
</body>
</html>
