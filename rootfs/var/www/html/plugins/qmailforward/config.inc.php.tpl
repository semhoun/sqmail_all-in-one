<?php
/**
 * qmail_forward configuration file
 * overwritten by config.inc.php
 */

/********************************************************************
 * defauldelivery (vpopmail defaultdelivery patch)
 *
 * When an alias is created, and the msg copy is wanted, another 'alias_line'
 * field with the defaultdelivery will be added, in order to copy the msg to mailbox.
 ********************************************************************/

// The content of the valias for the delivery. Put here your value as if it was
// a dot-qmail file content.
$config['qmailforward_defaultdelivery'] = '| /var/qmail/bin/preline -f /usr/libexec/dovecot/deliver -d $EXT@$USER';


/********************************************************************
 * database settings
 ********************************************************************/
//                                 mysqli://user:pwd@host/database
$config['qmailforward_db_dsnw'] = 'mysqli://${MYSQL_USER}:${MYSQL_PASS}@${MYSQL_HOST}/${MYSQL_DB}';

// PEAR database DSN for read only operations (if empty write database will be used)
// useful for database replication
$config['qmailforward_db_dsnr'] = '';

// use persistent db-connections
// beware this will not "always" work as expected
// see: http://www.php.net/manual/en/features.persistent-connections.php
$config['qmailforward_db_persistent'] = false;

// table that holds valiases
$config['qmailforward_sql_table_name'] = 'valias';

// name of the alias field in the valias table
$config['qmailforward_sql_alias_field'] = 'alias';

// name of the domain field in the valias table
$config['qmailforward_sql_domain_field'] = 'domain';

// name of the valias field in the valias table, holds the destination address
$config['qmailforward_sql_valias_field'] = 'valias_line';

// name of the type field in the valias table, holds the information if the valias is
// a real valias or an info on the LDA (vpopmail defaultdelivery patch)
$config['qmailforward_sql_type_field'] = 'valias_type';

// name of the copy field in the valias table, holds the information if the valias
// will do a redirect or a forward and copy
$config['qmailforward_sql_copy_field'] = 'copy';


/*********************************************************************************/

// List of domains limiting destination emails in redirect action
// If not empty, user will need to select the domain from a list
$config['qmailforward_domains'] = array();

// Activate qmailforward for selected mail hosts only. If this is not set all mail hosts are allowed.
// example: $config['qmailforward_allowed_hosts'] = array('mail1.domain.tld', 'mail2.domain.tld');
$config['qmailforward_allowed_hosts'] = array();

// Enable the DNS check for the email entered. If enabled the forward won't be created on failures.
$config['qmailforward_dnscheck'] = true;