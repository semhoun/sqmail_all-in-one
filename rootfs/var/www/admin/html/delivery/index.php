<?php
declare(strict_types=1);
require dirname(__DIR__, 2) . '/lib/delivery.php';
delivery_boot();
$error = $notice = $mailbox = $script = $domain = $query = '';
$state = $listing = $preview = null;
$editor = null;
$editorVersion = null;
$page = 1;
$operation = '';
try {
    $input = $_SERVER['REQUEST_METHOD'] === 'POST' ? $_POST : $_GET;
    $mailbox = delivery_string($input, 'mailbox');
    $script = delivery_string($input, 'script');
    $domain = delivery_string($input, 'domain');
    $query = delivery_string($input, 'query');
    $pageText = delivery_string($input, 'page', '1');
    if (!preg_match('/\A[1-9][0-9]{0,5}\z/', $pageText)) throw new RuntimeException('Invalid page number.');
    $page = (int) $pageText;
    if ($_SERVER['REQUEST_METHOD'] === 'POST') {
        $operation = delivery_string($_POST, 'operation');
        $fields = ['mailbox' => $mailbox, 'script' => $script];
        if ($operation === 'sieve_save') {
            $editor = delivery_string($_POST, 'content');
            $editorVersion = delivery_string($_POST, 'version');
            if (strlen($editor) > DELIVERY_SCRIPT_MAX) throw new RuntimeException('Script exceeds the 128 KiB limit. Your text is retained below.');
        }
        if (in_array($operation, ['qmail_preview', 'qmail_restore_preview', 'sieve_restore_preview'], true)) {
            if ($operation === 'qmail_preview') {
                $fields['mode'] = delivery_string($_POST, 'mode');
                $fields['destinations'] = array_values(array_filter(array_map('trim', explode("\n", delivery_string($_POST, 'destinations'))), static fn($v) => $v !== ''));
            }
            $preview = delivery_call($operation, $fields);
            $state = $preview['state'];
            $fields['mailbox'] = $state['mailbox'];
            $fields['script'] = $state['sieve']['selected']['name'] ?? $script;
            if ($operation === 'qmail_preview') {
                $fields['mode'] = $preview['mode'];
                $fields['destinations'] = $preview['destinations'];
            } else {
                $fields['backup_version'] = delivery_string($preview, 'backup_version');
                if (!preg_match('/\A[a-f0-9]{64}\z/', $fields['backup_version'])) throw new RuntimeException('Invalid backup version. Reload and preview again.');
            }
            $confirmation = bin2hex(random_bytes(24));
            $_SESSION['delivery_confirmation'] = ['id' => $confirmation, 'expires' => time() + 600, 'operation' => match ($operation) {
                'qmail_preview' => 'qmail_save', 'qmail_restore_preview' => 'qmail_restore', default => 'sieve_restore',
            }, 'fields' => $fields + ['version' => $state['version'], 'valias_fingerprint' => $state['valias']['fingerprint']]];
        } elseif (in_array($operation, ['qmail_save', 'qmail_restore', 'sieve_restore'], true)) {
            $pending = $_SESSION['delivery_confirmation'] ?? null;
            if (!is_array($pending) || $pending['expires'] < time() || !hash_equals($pending['id'], delivery_string($_POST, 'confirmation')) || $pending['operation'] !== $operation || $pending['fields']['mailbox'] !== $mailbox || $pending['fields']['script'] !== $script) {
                throw new RuntimeException('Confirmation expired or changed. Preview the operation again.');
            }
            if (delivery_string($_POST, 'confirm') !== 'yes') throw new RuntimeException('Explicit confirmation is required. Preview again to continue.');
            unset($_SESSION['delivery_confirmation']);
            $fields = $pending['fields'];
            if ($operation === 'sieve_restore') {
                unset($fields['valias_fingerprint']);
                $fields['confirm_active'] = delivery_string($_POST, 'confirm_active') === 'yes';
            } else {
                $fields['confirm_valias'] = delivery_string($_POST, 'confirm_valias') === 'yes';
                $fields['confirm_discard'] = delivery_string($_POST, 'confirm_discard') === 'yes';
            }
            $state = delivery_call($operation, $fields);
            $notice = $operation === 'sieve_restore' ? 'Script content restored. The previously active script was not automatically reactivated. Review and activate separately if needed.' : 'Delivery configuration updated. Review the observed state below.';
        } elseif (in_array($operation, ['sieve_save', 'sieve_activate', 'sieve_deactivate', 'sieve_delete'], true)) {
            $fields['version'] = delivery_string($_POST, 'version');
            if ($operation === 'sieve_save') {
                $fields['content'] = $editor;
                $fields['confirm_active'] = delivery_string($_POST, 'confirm_active') === 'yes';
            } elseif (delivery_string($_POST, 'confirm') !== 'yes') throw new RuntimeException('Explicit confirmation is required.');
            $state = delivery_call($operation, $fields);
            $editor = $editorVersion = null;
            $notice = match ($operation) {
                'sieve_save' => 'Script compiled and saved. Saving a draft does not activate it.',
                'sieve_activate' => 'Personal script activated. It replaces the global default fallback.',
                'sieve_deactivate' => 'Personal script deactivated. The global default fallback may now run.',
                default => 'Inactive script deleted.',
            };
        } elseif ($operation === 'vacation') {
            $state = delivery_call('inspect', $fields);
            if (!$state['sieve']['available']) throw new RuntimeException($state['sieve']['reason']);
            $days = delivery_string($_POST, 'days', '7');
            if (!preg_match('/\A(?:[1-9]|[12][0-9]|30)\z/', $days)) throw new RuntimeException('Vacation interval must be between 1 and 30 days.');
            $names = array_column($state['sieve']['scripts'], 'name');
            do { $script = 'vacation-' . bin2hex(random_bytes(8)); } while (in_array($script, $names, true));
            $mailbox = $state['mailbox'];
            $state = delivery_call('inspect', ['mailbox' => $mailbox, 'script' => $script]);
            if ($state['sieve']['selected']['exists']) throw new RuntimeException('Draft name was created concurrently. Generate another draft.');
            $editor = 'require ["vacation"];' . "\n\nvacation :days " . $days . "\n    :addresses [" . delivery_sieve_string($mailbox) . "]\n    :subject " . delivery_sieve_string(delivery_string($_POST, 'subject')) . "\n    " . delivery_sieve_string(delivery_string($_POST, 'message')) . ";\n";
            if (strlen($editor) > DELIVERY_SCRIPT_MAX) throw new RuntimeException('Generated script exceeds the 128 KiB limit.');
            $notice = 'Vacation draft generated locally in this editor only. Nothing has been saved or activated.';
        } else throw new RuntimeException('Unknown operation.');
    }
    if ($mailbox !== '' && $state === null) $state = delivery_call('inspect', ['mailbox' => $mailbox, 'script' => $script]);
    if ($mailbox === '') $listing = delivery_call($domain === '' ? 'domains' : 'mailboxes', ['query' => $query, 'page' => $page - 1] + ($domain === '' ? [] : ['domain' => $domain]));
} catch (Throwable $exception) {
    $error = $exception instanceof RuntimeException ? $exception->getMessage() : 'Delivery service unavailable. Reload before retrying.';
    if ($mailbox !== '' && $state === null) {
        try { $state = delivery_call('inspect', ['mailbox' => $mailbox, 'script' => $script]); } catch (Throwable) { /* Keep the original error and submitted editor text. */ }
    }
}
if ($state !== null) { $mailbox = $state['mailbox']; $script = $state['sieve']['selected']['name'] ?? $script; }
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Delivery &amp; Sieve - SQMail AIO</title>
    <link rel="stylesheet" href="/css/bootstrap.min.css">
    <link rel="stylesheet" href="/css/style.css">
    <link rel="stylesheet" href="/delivery/style.css">
</head>
<body class="admin-page">
<div class="admin-shell delivery-shell">
    <a class="delivery-skip" href="#main">Skip to content</a>
    <header class="admin-header">
        <a class="login-brand" href="/">SQMail <span class="login-brand-edition">All-in-One</span></a>
        <form method="post" action="/logout.php"><?php delivery_hidden('csrf', $_SESSION['csrf']); ?><button class="admin-signout" type="submit">Sign out</button></form>
    </header>
    <main id="main">
        <header class="login-heading admin-heading">
            <p class="login-eyebrow">Mail administration</p>
            <h1>Delivery &amp; Sieve</h1>
            <p><?= delivery_escape($mailbox !== '' ? $mailbox : 'Choose a domain, then a mailbox.') ?></p>
        </header>
        <p class="delivery-notice"><strong>Server-wide administrator access.</strong> Every portal user can administer every mailbox here, including mailboxes with login disabled. VQAdmin domain ACLs do not restrict this application.</p>
        <?php if ($error !== ''): ?><p class="delivery-notice delivery-error" role="alert"><?= delivery_escape($error) ?></p><?php endif; ?>
        <?php if ($notice !== ''): ?><p class="delivery-notice" role="status"><?= delivery_escape($notice) ?></p><?php endif; ?>
        <nav class="delivery-nav" aria-label="Delivery navigation">
            <a href="/">Administration</a><a href="/delivery/">Domains</a>
            <?php if ($state !== null): ?><a href="#delivery">Delivery</a><a href="#sieve">Sieve</a><a href="#diagnostic">Diagnostic</a><a href="<?= delivery_escape(delivery_url(['mailbox' => $mailbox, 'script' => $script])) ?>">Reload observed state</a><?php endif; ?>
        </nav>
        <?php if ($mailbox === ''): ?>
        <section class="delivery-panel" aria-labelledby="search-title">
            <h2 id="search-title"><?= $domain === '' ? 'Domains' : 'Mailboxes in ' . delivery_escape($domain) ?></h2>
            <?php if ($domain !== ''): ?><p>Select a mailbox below to change that user's individual delivery, forwarding and Sieve options. Domains are used only to find mailboxes; their delivery rules cannot be changed here.</p><?php endif; ?>
            <form method="get" action="/delivery/" class="delivery-form">
                <?php delivery_hidden('domain', $domain); ?>
                <label for="query">Search <?= $domain === '' ? 'domains' : 'mailboxes' ?></label>
                <input id="query" name="query" value="<?= delivery_escape($query) ?>" maxlength="254">
                <button type="submit" class="queue-button">Search</button>
            </form>
            <?php if ($listing !== null): ?>
            <ul class="delivery-list">
                <?php foreach ($listing['items'] as $item): ?><li><a href="<?= delivery_escape(delivery_url([$domain === '' ? 'domain' : 'mailbox' => $item])) ?>"><?= delivery_escape($item) ?></a></li><?php endforeach; ?>
            </ul>
            <?php if (!$listing['items']): ?><p>No matches. Try a different search.</p><?php endif; ?>
            <nav class="delivery-actions" aria-label="Search pages">
                <?php if ($page > 1): ?><a class="queue-button" href="<?= delivery_escape(delivery_url(['domain' => $domain, 'query' => $query, 'page' => $page - 1])) ?>">Previous page</a><?php endif; ?>
                <span>Page <?= $page ?></span>
                <?php if ($listing['next_page'] !== null): ?><a class="queue-button" href="<?= delivery_escape(delivery_url(['domain' => $domain, 'query' => $query, 'page' => $listing['next_page'] + 1])) ?>">Next page</a><?php endif; ?>
            </nav>
            <?php endif; ?>
        </section>
        <?php endif; ?>
        <?php if ($preview !== null && $state !== null): ?>
        <section class="delivery-panel" aria-labelledby="preview-title">
            <h2 id="preview-title">Review before confirming</h2>
            <?php if ($operation === 'sieve_restore_preview'): ?>
                <p>Restore <?= $preview['exists'] ? 'the saved script content' : 'the saved absence of this script' ?>. This does not automatically reactivate the previously active script: <strong><?= delivery_escape($preview['previous_active'] ?? 'none') ?></strong>.</p>
                <pre tabindex="0" aria-label="Script content to restore"><?= delivery_escape($preview['content']) ?></pre>
                <?php if (!empty($preview['previous_active_snapshot']['name'])): ?>
                    <details>
                        <summary>Archived previously active source: <?= delivery_escape($preview['previous_active_snapshot']['name']) ?></summary>
                        <p>For separate recovery, open a new draft name and use this archived source, then save and activate explicitly. Restoring the selected script below does not apply this other snapshot.</p>
                        <pre tabindex="0" aria-label="Archived previously active script source"><?= delivery_escape($preview['previous_active_snapshot']['content']) ?></pre>
                    </details>
                <?php endif; ?>
            <?php else: ?>
                <p>Review the complete delivery change below. Local delivery uses Dovecot, with or without Sieve, retaining its other configured checks. Forward-only has no local copy. Discard consumes messages without delivery or forwarding.</p>
                <pre tabindex="0" aria-label="Delivery configuration diff"><?= delivery_escape($preview['diff']) ?></pre>
                <?php if (($preview['mode'] ?? '') === 'discard'): ?><p class="delivery-notice delivery-warning"><strong>Messages on this mailbox's .qmail delivery path will be permanently discarded, without a local copy or forwarding.</strong> Existing valias rules take priority, and direct Dovecot/Fetchmail delivery bypasses this setting.</p><?php endif; ?>
            <?php endif; ?>
            <?php delivery_form($state, $_SESSION['delivery_confirmation']['operation']); delivery_hidden('confirmation', $confirmation); ?>
                <label><input type="checkbox" name="confirm" value="yes" required>I confirm this exact preview and want to apply it.</label>
                <?php if ($operation !== 'sieve_restore_preview' && ($preview['mode'] ?? '') === 'discard'): ?><label><input type="checkbox" name="confirm_discard" value="yes" required>I explicitly confirm permanent discard for this mailbox's .qmail delivery path.</label><?php endif; ?>
                <?php if ($operation !== 'sieve_restore_preview' && $state['valias']['lines']): ?><label><input type="checkbox" name="confirm_valias" value="yes" required>I understand the current valias rules take priority and override this individual .qmail configuration.</label><?php endif; ?>
                <?php if ($operation === 'sieve_restore_preview' && $state['sieve']['selected']['active']): ?><label><input type="checkbox" name="confirm_active" value="yes" required>I understand restoring the active script changes filtering immediately.</label><?php endif; ?>
                <button class="queue-button queue-button-primary" type="submit">Confirm <?= $operation === 'qmail_preview' ? 'delivery change' : 'restore' ?></button>
                <a href="<?= delivery_escape(delivery_url(['mailbox' => $mailbox, 'script' => $script])) ?>">Cancel and reload</a>
            </form>
        </section>
        <?php endif; ?>
        <?php if ($state !== null): $selected = $state['sieve']['selected']; ?>
        <section id="delivery" class="delivery-panel" aria-labelledby="delivery-title">
            <h2 id="delivery-title">Delivery</h2>
            <p>Observed mode: <strong><?= delivery_escape($state['qmail']['mode']) ?></strong>. <?= delivery_escape($state['qmail']['reason']) ?></p>
            <?php if ($state['valias']['lines']): ?><p class="delivery-notice delivery-warning"><strong>valias takes priority.</strong> The current SQL alias rules override the individual .qmail, rather than adding to it. This application never changes valias.</p><?php endif; ?>
            <p>Local delivery uses Dovecot with or without Sieve, retaining its other configured checks. Discard consumes messages without a local copy or forwarding. Indirect forwarding loops cannot all be detected. Fetchmail delivers directly through Dovecot LDA and does not follow this SMTP .qmail route.</p>
            <?php if ($state['qmail']['editable']): delivery_form($state, 'qmail_preview'); ?>
                <label for="mode">Delivery mode</label>
                <select id="mode" name="mode">
                    <?php foreach (['inherit' => 'Inherit server default (no .qmail)', 'local' => 'Local delivery (with Sieve)', 'local_no_sieve' => 'Local delivery (without Sieve)', 'forward' => 'Forward only (no local copy)', 'copy' => 'Forward + local copy (with Sieve)', 'copy_no_sieve' => 'Forward + local copy (without Sieve)', 'discard' => 'Discard messages (no delivery)'] as $value => $label): ?><option value="<?= $value ?>" <?= ($operation === 'qmail_preview' ? ($_POST['mode'] ?? '') : $state['qmail']['mode']) === $value ? 'selected' : '' ?>><?= delivery_escape($label) ?></option><?php endforeach; ?>
                </select>
                <label for="destinations">Forwarding destinations, one address per line</label>
                <textarea id="destinations" name="destinations" rows="4" aria-describedby="destination-help"><?= delivery_escape($operation === 'qmail_preview' && is_string($_POST['destinations'] ?? null) ? $_POST['destinations'] : implode("\n", $state['qmail']['destinations'])) ?></textarea>
                <p id="destination-help">Use destinations only for forwarding modes, with or without a local copy. Clear destinations for local delivery, inheritance or discard. Supported addresses have lowercase local parts; external recipient casing is never silently changed. Direct self-forwarding and duplicate destinations are not allowed.</p>
                <button class="queue-button" type="submit">Preview delivery diff</button>
            </form>
            <?php else: ?><p class="delivery-notice delivery-warning">This .qmail is read-only. Unknown, ambiguous or unsafe content cannot be replaced by a template.</p><?php endif; ?>
            <?php if ($state['backups']['qmail'] && $state['qmail']['editable']): delivery_form($state, 'qmail_restore_preview'); ?><button type="submit" class="queue-button">Preview last delivery backup</button></form><?php endif; ?>
        </section>
        <section id="sieve" class="delivery-panel" aria-labelledby="sieve-title">
            <h2 id="sieve-title">Sieve</h2>
            <p>A personal active script replaces the global default fallback. Deactivating it does not disable all filtering: the fallback may run again. Sieve runs only when the delivery route enables it; without-Sieve, forward-only and discard modes bypass it, as may valias. Direct Fetchmail delivery remains independent of these settings.</p>
            <p>Sieve redirect branches and includes are not analyzed here. No SRS guarantee is made for Sieve redirects. Roundcube and ManageSieve remain available; avoid simultaneous edits.</p>
            <?php if ($editor !== null && (!$state['sieve']['available'] || !$selected['supported'])): ?><label for="retained-content">Unsaved script text (retained)</label><textarea id="retained-content" class="form-control" rows="18" readonly><?= delivery_escape($editor) ?></textarea><?php endif; ?>
            <?php if (!$state['sieve']['available']): ?><p class="delivery-notice delivery-warning"><?= delivery_escape($state['sieve']['reason']) ?></p><?php else: ?>
            <ul class="delivery-list">
                <?php foreach ($state['sieve']['scripts'] as $item): ?><li><a href="<?= delivery_escape(delivery_url(['mailbox' => $mailbox, 'script' => $item['name']])) ?>#sieve"><?= delivery_escape($item['name']) ?></a> <span class="queue-badge"><?= $item['active'] ? 'Active' : 'Inactive' ?></span></li><?php endforeach; ?>
            </ul>
            <?php if (!$state['sieve']['scripts']): ?><p>No personal scripts. The global default fallback may run on local delivery.</p><?php endif; ?>
            <form method="get" action="/delivery/#sieve" class="delivery-form">
                <?php delivery_hidden('mailbox', $mailbox); ?>
                <label for="new-script">Open a new draft name</label>
                <input id="new-script" name="script" required maxlength="128" autocomplete="off" aria-describedby="draft-help">
                <p id="draft-help">Opening a name reads its current state without saving. Use a different name to save a copy instead of changing the active script. The name "default" is reserved: saving it while inactive may cause native implicit activation.</p>
                <button class="queue-button" type="submit">Open draft</button>
            </form>
            <?php if ($script !== ''): ?>
            <h3><?= delivery_escape($script) ?> <?= $selected['active'] ? '(active)' : '(draft / inactive)' ?></h3>
            <?php if ($selected['supported']): $editState = $state; if ($editorVersion !== null) $editState['version'] = $editorVersion; delivery_form($editState, 'sieve_save'); ?>
                <label for="content">Script source (maximum 128 KiB)</label>
                <textarea id="content" name="content" class="delivery-editor" rows="18" spellcheck="false" autocapitalize="none" aria-describedby="save-help"><?= delivery_escape($editor ?? $selected['content']) ?></textarea>
                <p id="save-help">Save compiles and validates the script. Invalid text stays in this editor and does not replace the stored script. A conflict requires reloading; preserve your edited text before leaving this page.</p>
                <?php if ($selected['active']): ?><label><input type="checkbox" name="confirm_active" value="yes" required>I understand saving this active script changes filtering immediately.</label><?php endif; ?>
                <button class="queue-button queue-button-primary" type="submit">Validate and save script</button>
            </form>
            <?php else: ?><p>This existing name is read-only because it is not supported for editing.</p><pre tabindex="0" aria-label="Read-only script source"><?= delivery_escape($selected['content']) ?></pre><?php endif; ?>
            <?php if ($selected['exists'] && $selected['supported']): ?>
                <?php delivery_form($state, $selected['active'] ? 'sieve_deactivate' : 'sieve_activate'); ?>
                    <label><input type="checkbox" name="confirm" value="yes" required><?= $selected['active'] ? 'Deactivate this script and allow the global default fallback to run.' : 'Activate this script, replacing the current personal filters and global default fallback.' ?></label>
                    <button class="queue-button" type="submit"><?= $selected['active'] ? 'Deactivate script' : 'Activate script' ?></button>
                </form>
                <?php if (!$selected['active']): delivery_form($state, 'sieve_delete'); ?><label><input type="checkbox" name="confirm" value="yes" required>Delete this inactive script.</label><button class="queue-button queue-remove" type="submit">Delete inactive script</button></form><?php else: ?><p>Active scripts cannot be deleted. Deactivate explicitly first.</p><?php endif; ?>
            <?php endif; ?>
            <?php if ($state['backups']['sieve'] && $selected['supported']): delivery_form($state, 'sieve_restore_preview'); ?><button class="queue-button" type="submit">Preview last script backup</button></form><?php endif; ?>
            <?php endif; ?>
            <details>
                <summary>Generate a vacation draft</summary>
                <p class="delivery-notice delivery-warning">This creates editor text only, with a unique draft name. It does not merge with Roundcube scripts. Activating the draft replaces your other personal filters and the global fallback. Copy the vacation block into the intended script yourself if you need to retain those filters.</p>
                <?php delivery_form($state, 'vacation'); ?>
                    <label for="subject">Reply subject</label><input id="subject" name="subject" maxlength="500" required value="<?= delivery_escape(is_string($_POST['subject'] ?? null) ? $_POST['subject'] : 'Out of office') ?>">
                    <label for="message">Reply message</label><textarea id="message" name="message" rows="5" required><?= delivery_escape(is_string($_POST['message'] ?? null) ? $_POST['message'] : 'I am away and will reply when I return.') ?></textarea>
                    <label for="days">Minimum days between replies to the same sender (1 to 30)</label><input id="days" name="days" type="number" min="1" max="30" value="<?= delivery_escape(is_string($_POST['days'] ?? null) ? $_POST['days'] : '7') ?>" required>
                    <button class="queue-button" type="submit">Generate local draft</button>
                </form>
            </details>
            <?php endif; ?>
            <details><summary>Global default fallback (read-only)</summary><pre tabindex="0" aria-label="Global fallback source"><?= delivery_escape($state['sieve']['default_content']) ?></pre></details>
        </section>
        <section id="diagnostic" class="delivery-panel" aria-labelledby="diagnostic-title">
            <h2 id="diagnostic-title">Diagnostic</h2>
            <p>This is an observed configuration, not a complete delivery simulation. The helper serializes its own operations, not external QmailAdmin or ManageSieve writers. Version checks detect observable conflicts but cannot guarantee atomic coordination across applications.</p>
            <dl><dt>Canonical mailbox</dt><dd><?= delivery_escape($mailbox) ?></dd><dt>Resolved home (diagnostic only)</dt><dd><?= delivery_escape($state['home']) ?></dd></dl>
            <h3>Individual .qmail</h3><pre tabindex="0" aria-label="Individual qmail source"><?= delivery_escape($state['qmail']['content'] ?? ($state['qmail']['mode'] === 'inherit' ? '(absent: inherit server default)' : '(not displayed: unsafe or unreadable file)')) ?></pre>
            <h3>Server default delivery</h3><pre tabindex="0" aria-label="Server default delivery"><?= delivery_escape($state['defaultdelivery']) ?></pre>
            <h3>valias rules (read-only, take priority)</h3><pre tabindex="0" aria-label="Valias rules"><?= delivery_escape($state['valias']['lines'] ? implode("\n", $state['valias']['lines']) : '(none)') ?></pre>
            <p>The latest backup is replaced by each successful backup before a change. Restoring content is separate from rolling back the image and does not automatically restore previous activation.</p>
        </section>
        <?php elseif ($editor !== null): ?>
        <section class="delivery-panel"><h2>Unsaved script text</h2><p>The mailbox could not be inspected. Your submitted text is retained here; no save is available until the mailbox state can be read.</p><label for="unsaved">Submitted script</label><textarea id="unsaved" class="form-control" rows="18" readonly><?= delivery_escape($editor) ?></textarea></section>
        <?php endif; ?>
    </main>
    <footer class="admin-footer"><span>Your domains. Your mail. Your control.</span><a href="/">Back to administration</a></footer>
</div>
</body>
</html>
