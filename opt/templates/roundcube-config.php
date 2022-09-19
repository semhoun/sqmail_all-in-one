<?php
$config['db_dsnw'] = 'mysql://${MYSQL_USER}:${MYSQL_PASS}@${MYSQL_HOST}/${MYSQL_DB}';
$config['db_prefix'] = 'rcb_';
$config['log_driver'] = 'stdout';
$config['log_logins'] = true;
$config['smtp_log'] = false;
$config['imap_host'] = 'localhost:143';
$config['smtp_host'] = 'localhost:25';
$config['smtp_auth_type'] = null;
$config['auto_create_user'] = true;
$config['des_key'] = 'PYZFYKPdvVKZFZtSvZHd15SV';
$config['plugins'] = ['additional_message_headers', 'archive', 'attachment_reminder', 'autologon', 'emoticons', 'gravatar', 'help', 'identity_select', 'jqueryui', 'markasjunk', 'newmail_notifier', 'password', 'thunderbird_labels', 'vcard_attachments', 'zipdownload'];
$config['language'] = 'fr_FR, en_US';
$config['junk_mbox'] = 'Spam';
$config['enable_spellcheck'] = true;
$config['imap_vendor'] = 'dovecot';

$config['spellcheck_engine'] = 'pspell';

$config['password_driver'] = 'sql';
$config['password_confirm_current'] = true;
$config['password_db_dsn'] = 'mysql://${MYSQL_USER}:${MYSQL_PASS}@${MYSQL_HOST}/${MYSQL_DB}';
$config['password_query'] = 'UPDATE vpopmail set pw_passwd=ENCRYPT(%p,concat("$1$",right(md5(rand()),8 ),"$")), pw_clear_passwd=%p where pw_name=%l and pw_domain=%d';
$config['password_crypt_hash'] = 'md5';

$config['product_name'] = '${PRODUCT_NAME}';
$config['support_url'] = '${SUPPORT_URL}';
