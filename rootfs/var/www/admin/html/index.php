<?php
session_name('__Host-sqmail-login');
session_save_path('/run/sqmail-admin/');
ini_set('session.use_strict_mode', '1');
ini_set('session.gc_maxlifetime', '3600');
session_set_cookie_params(['path' => '/', 'secure' => true, 'httponly' => true, 'samesite' => 'Strict']);
session_start();
$_SESSION['csrf'] ??= bin2hex(random_bytes(32));
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>SQMail AIO - Administration</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="/css/bootstrap.min.css">
    <link rel="stylesheet" href="/css/style.css">
</head>
<body class="admin-page">
<div class="admin-shell">
    <header class="admin-header">
        <div class="login-brand" aria-label="SQMail All-in-One">
            <span class="login-mark" aria-hidden="true">
                <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.6">
                    <rect x="4" y="7" width="24" height="18" rx="4" />
                    <path d="m5 9 11 9L27 9" />
                </svg>
            </span>
            <span>SQMail <span class="login-brand-edition">All-in-One</span></span>
        </div>
        <form method="post" action="/logout.php">
            <input type="hidden" name="csrf" value="<?= htmlspecialchars($_SESSION['csrf'], ENT_QUOTES, 'UTF-8') ?>">
            <button type="submit" class="admin-signout">Sign out</button>
        </form>
    </header>

    <main>
        <header class="login-heading admin-heading">
            <p class="login-eyebrow">Administration</p>
            <h1>Your mail server.</h1>
            <p>Manage your domains, mailboxes and message delivery.</p>
        </header>

        <nav class="admin-tools" aria-label="Mail administration tools">
            <a class="admin-tool" href="/cgi/vqadmin/vqadmin.cgi">
                <span class="admin-tool-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                        <circle cx="12" cy="12" r="9" /><ellipse cx="12" cy="12" rx="4" ry="9" /><path d="M3 12h18" />
                    </svg>
                </span>
                <h2>Domains</h2>
                <p>Add domains and manage their settings and limits.</p>
                <span class="admin-tool-link">VQAdmin <span aria-hidden="true">&rarr;</span></span>
            </a>
            <a class="admin-tool" href="/cgi/qmailadmin">
                <span class="admin-tool-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                        <rect x="3" y="5" width="18" height="14" rx="3" /><path d="m4 7 8 6 8-6" />
                    </svg>
                </span>
                <h2>Mailboxes</h2>
                <p>Manage email accounts, aliases and forwarding.</p>
                <span class="admin-tool-link">QMail Admin <span aria-hidden="true">&rarr;</span></span>
            </a>
            <a class="admin-tool" href="/cgi/qmail-queue.php">
                <span class="admin-tool-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                        <rect x="3" y="3" width="18" height="18" rx="3" /><path d="M7 8h10M7 12h10M7 16h6" />
                    </svg>
                </span>
                <h2>Mail queue</h2>
                <p>Inspect queued messages and manage pending delivery.</p>
                <span class="admin-tool-link">QMail Queue <span aria-hidden="true">&rarr;</span></span>
            </a>
            <a class="admin-tool" href="/delivery/">
                <span class="admin-tool-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                        <path d="M4 6h16M4 12h10M4 18h6m7-5 4 4-4 4m-5-4h9" />
                    </svg>
                </span>
                <h2>Delivery &amp; Sieve</h2>
                <p>Inspect delivery routes, manage filters and prepare vacation replies.</p>
                <span class="admin-tool-link">All mailboxes <span aria-hidden="true">&rarr;</span></span>
            </a>
        </nav>

        <section class="admin-diagnostics" aria-labelledby="diagnostics-title">
            <h2 id="diagnostics-title">Reports &amp; diagnostics</h2>
            <div class="admin-utilities">
                <a class="admin-utility" href="/stats/">
                    <span><strong>Statistics &amp; logs</strong><span>Explore delivery history, service events and source coverage.</span></span>
                    <span class="admin-utility-arrow" aria-hidden="true">&rarr;</span>
                </a>
                <?php if (file_exists('/var/qmail/control/aio-conf/dmarc.conf')) { ?>
                <a class="admin-utility" href="/dmarc/">
                    <span><strong>DMARC reports</strong><span>Review domain authentication reports.</span></span>
                    <span class="admin-utility-arrow" aria-hidden="true">&rarr;</span>
                </a>
                <?php } ?>
                <a class="admin-utility" href="/info.php">
                    <span><strong>System information</strong><span>Inspect the PHP environment and configuration.</span></span>
                    <span class="admin-utility-arrow" aria-hidden="true">&rarr;</span>
                </a>
            </div>
        </section>
    </main>

    <footer class="admin-footer">
        <span>Your domains. Your mail. Your control.</span>
        <a href="https://github.com/semhoun/qmail_all-in-one">SQMail All-in-One on GitHub <span aria-hidden="true">&nearr;</span></a>
    </footer>
</div>
</body>
</html>
