<?php
$config['db_dsnw'] = 'mysqli://${MYSQL_USER}:${MYSQL_PASS}@${MYSQL_HOST}/${MYSQL_DB}';
$config['db_prefix'] = 'rcb_';
$config['log_driver'] = 'stdout';
$config['log_logins'] = true;
$config['smtp_log'] = false;
$config['imap_host'] = 'localhost:143';
$config['smtp_host'] = 'localhost:25';
$config['smtp_auth_type'] = null;
$config['auto_create_user'] = true;
$config['des_key'] = 'PYZFYKPdvVKZFZtSvZHd15SV';
$config['plugins'] = [
  'additional_message_headers',
  'archive',
  'attachment_reminder',
  'emoticons',
  'gravatar',
  'help',
  'identity_select',
  'jqueryui',
  'sauserprefs',
  'markasjunk',
  'newmail_notifier',
  'password',
  'thunderbird_labels', 
  'vcard_attachments',
  'zipdownload',
  'managesieve',
  'contextmenu',
  'swipe'
];
$config['language'] = 'fr_FR, en_US';
$config['junk_mbox'] = 'Spam';
$config['imap_vendor'] = 'dovecot';

$config['enable_spellcheck'] = true;
$config['spellcheck_engine'] = 'pspell';

$config['swipe_actions'] = [ 
  'messagelist' => [ 
    'left'  => 'delete', 
    'right' => 'reply-all', 
    'down'  => 'checkmail' 
  ], 
  'contactlist' => [ 
    'left'  => 'compose', 
    'right' => 'compose', 
    'down'  => 'vcard_attachments' 
  ] 
];
