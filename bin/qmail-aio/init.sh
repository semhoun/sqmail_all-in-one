#!/bin/bash
RESUME=$(mktemp /tmp/sqmail.XXXXXX)
> ${RESUME}

#https://en.wikibooks.org/wiki/Bash_Shell_Scripting/Whiptail
whiptail --title "Semhoun's SQMail" --msgbox "Welcome in the SQMail first time configuration\MariaDB database must already been created" 8 78

# MariaDB
MARIADB_HOST=$(whiptail --inputbox "MariaDB Host" 8 39 "" --title "MariaDB configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
MARIADB_DB=$(whiptail --inputbox "MariaDB Database" 8 39 "" --title "MariaDB configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
MARIADB_USER=$(whiptail --inputbox "MariaDB Username" 8 39 "" --title "MariaDB configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
MARIADB_PASS=$(whiptail --inputbox "MariaDB Password" 8 39 "" --title "MariaDB configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi

cat >> "${RESUME}" <<EOF
Mysql configration will be:
  - host : ${MARIADB_HOST}
  - database : ${MARIADB_DB}
  - username : ${MARIADB_USER}
  - password : ${MARIADB_PASS}
  
EOF

# QMail params
CONCURRENCY_INCOMING=$(whiptail --inputbox "Concurrency incoming" 8 39 "50" --title "QMail/SMTP configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
CONCURRENCY_REMOTE=$(whiptail --inputbox "Concurrency remote" 8 39 "5" --title "QMail/SMTP configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
DATABYTES=$(whiptail --inputbox "Email max size in bytes (0 unlimited)" 8 39 "26214400" --title "QMail/SMTP configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
QUEUELIFETIME=$(whiptail --inputbox "Queue life time in seconds" 8 39 "604800" --title "QMail/SMTP configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
SPFBEHAVIOR=$(whiptail --title "Menu example" --menu "QMail/SMTP configuration" 25 78 16 \
  "3" "Reject mails when SPF resolves to fail (deny)" \
  "0" "Never do SPF lookups, don't create Received-SPF headers" \
  "1" "Only create Received-SPF headers, never block" \
  "2" "Use temporary errors when you have DNS lookup problems" \
  "4" "Reject mails when SPF resolves to softfail" \
  "5" "Reject mails when SPF resolves to neutral" \
  "6" "Reject mails when SPF does not resolve to pass" \
3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi

cat >> "${RESUME}" << EOF
QMail/SMTP configuration will be:
  - concurrency incoming : ${CONCURRENCY_INCOMING}
  - concurrency remote : ${CONCURRENCY_REMOTE}
  - database : ${DATABYTES}
  - queue life time : ${QUEUELIFETIME}
  - spf behavior : ${SPFBEHAVIOR}
  
EOF

SMTP_SERVER=$(whiptail --inputbox "SMTP server hostname" 8 39 "smtp.exemple.net" --title "Domain configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
DEFAULT_DOMAIN=$(whiptail --inputbox "Default domain" 8 39 "exemple.net" --title "Domain configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
POSTMASTER_PWD=$(whiptail --inputbox "Postmaster password" 8 39 "" --title "Domain configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
cat >> "${RESUME}" << EOF
Domain configuration will be:
  - smtp server : ${SMTP_SERVER}
  - default domain : ${DEFAULT_DOMAIN}
  - postmaster password : ${POSTMASTER_PWD}
  
EOF

# Resume
whiptail --textbox "${RESUME}" 25 78
rm "${RESUME}"

if !(whiptail --title "Set configuration" --yesno "Apply the configuration." 8 78); then
  echo "You canceled the script"
  exit 0
fi

#-----------------------------------------------------------------------------#

# Default config
echo "MAILER-DAEMON" > /var/qmail/control/bouncefrom
echo postmaster > /var/qmail/control/doublebounceto
echo "| /home/vpopmail/bin/vdelivermail '' delete" > /var/qmail/control/defaultdelivery

# SSL base Config
openssl dhparam -out /ssl/qmail-dhparam 2048
openssl dhparam -out /ssl/dovecot-dhparam 2048	

# Creation configuration
cat > /var/qmail/control/mysql.conf << EOF
MYSQL_USER=${MARIADB_USER}
MYSQL_PASS=${MARIADB_PASS}
MYSQL_DB=${MARIADB_DB}
MYSQL_HOST=${MARIADB_HOST}
EOF
echo "${MARIADB_HOST}|0|${MARIADB_USER}|${MARIADB_PASS}|${MARIADB_DB}" > /var/vpopmail/etc/vpopmail.mysql
cat > /var/qmail/control/spamassassin_sql.cf << EOF
# User prefs
user_scores_dsn DBI:mysql:${MARIADB_DB}:${MARIADB_HOST}
user_scores_sql_username ${MARIADB_USER}
user_scores_sql_password ${MARIADB_PASS}
user_scores_sql_custom_query     SELECT preference, value FROM spam_prefs WHERE username = _USERNAME_ OR username = '\$GLOBAL' OR username = CONCAT('%',_DOMAIN_) ORDER BY username ASC
EOF
echo -n "${CONCURRENCY_INCOMING}" > /var/qmail/control/concurrencyincoming
echo "${CONCURRENCY_REMOTE}" > /var/qmail/control/concurrencyincoming
echo "${DATABYTES}" > /var/qmail/control/databytes
echo "${SPFBEHAVIOR}" > /var/qmail/control/spfbehavior
echo "${QUEUELIFETIME}" > /var/qmail/control/queuelifetime

# VPopmail configuration
echo "${DEFAULT_DOMAIN}" > /var/vpopmail/etc/defaultdomain
cat > /var/vpopmail/etc/vlimits.default << 'EOF'
# Default limits file.  This file is used for domains without a
# .qmailadmin-limits file.

# maximums for each account type, -1 = unlimited
maxpopaccounts          -1
maxforwards             -1
maxautoresponders       -1
maxmailinglists         -1

# quota for entire domain, in megabytes
# example shows a domain with a 100MB quota and a limit of 10,000 messages
#quota                  100
#maxmsgcount            10000

# default quota for newly created users (in bytes)
# example shows a user with a 10MB quota and a limit of 1000 messages
#default_quota          10485760
#default_maxmsgcount    1000

# uncomment the following lines to disable certain features
#disable_pop
#disable_imap
#disable_dialup
#disable_password_changing
#disable_external_relay
#disable_smtp
#disable_webmail
#disable_spamassassin
#delete_spam
#disable_maildrop


# Set bitflags on account management for non-postmaster admins.
# To disable certain features, add the following bits:
#   Create = 1, Modify = 2, Delete = 4
# So, to allow modification but not creation or deletion of
# POP/IMAP accounts, set perm_account to 5.

perm_account            0
perm_alias              0
perm_forward            0
perm_autoresponder      0
perm_maillist           0
perm_quota              0
perm_defaultquota       0
EOF

# Qmail configuration from /package/mail/sqmail/sqmail/src/config-fast.sh
echo "${SMTP_SERVER}" > /var/qmail/control/me
echo "${DEFAULT_DOMAIN}" > /var/qmail/control/defaultdomain
echo "${DEFAULT_DOMAIN}" > /var/qmail/control/plusdomain
echo "${SMTP_SERVER}" >> /var/qmail/control/rcpthosts
echo "*:" >> /var/qmail/control/tlsdestinations

# Alias
cd /var/qmail/alias
echo "postmaster@${DEFAULT_DOMAIN}" > .qmail-postmaster
ln -s .qmail-postmaster .qmail-mailer-daemon
ln -s .qmail-postmaster .qmail-root
chown alias.sqmail .qmail*
chmod 644 .qmail*
 
# Dovecot
cat > /var/qmail/control/dovecot-sql.conf.ext << EOF
driver = mysql
connect = host=${MARIADB_HOST} dbname=${MARIADB_DB} user=${MARIADB_USER} password=${MARIADB_PASS}
default_pass_scheme = MD5-CRYPT

#  USER LIMITS via vpopmail.pw_gid filed was currently removed
password_query = \
	SELECT \
		CONCAT(vpopmail.pw_name, '@', vpopmail.pw_domain) AS user, \
  		vpopmail.pw_passwd AS password, \
                vpopmail.pw_dir AS userdb_home, \
                89 AS userdb_uid, \
                89 AS userdb_gid, \
                CONCAT('*:bytes=', REPLACE(SUBSTRING_INDEX(vpopmail.pw_shell, 'S', 1), 'NOQUOTA', '0')) AS userdb_quota_rule \
	FROM vpopmail \
		LEFT JOIN aliasdomains ON aliasdomains.alias='%d' \
		LEFT JOIN limits ON limits.domain = '%d' \
	WHERE \
		vpopmail.pw_name='%n' \
		AND \
		(vpopmail.pw_domain='%d' OR vpopmail.pw_domain=aliasdomains.domain)

user_query = \
	SELECT \
		vpopmail.pw_dir AS home, \
	  	89 AS uid, \
  		89 AS gid \
  	FROM vpopmail \
  	WHERE \
  		vpopmail.pw_name='%n' \
		AND \
		vpopmail.pw_domain='%d'

iterate_query = SELECT CONCAT(pw_name,'@',pw_domain) AS user FROM vpopmail
EOF
chown root.root /var/qmail/control/dovecot-sql.conf.ext
chmod 600 /var/qmail/control/dovecot-sql.conf.ext

# Creation directory and setting permissions
mkdir -p /var/qmail/control/domainkeys
chown -R qmaild:sqmail /var/qmail/control
chown -R qmailq:sqmail /var/qmail/queue
chmod 644 /var/qmail/control/*
mkdir -p /var/spamassassin/auto-whitelist
mkdir -p /var/spamassassin/bayes
mkdir -p /var/spamassassin/razor
chown -R vpopmail.vchkpw /var/spamassassin
chown 644 /var/vpopmail/etc/*
chown -R vpopmail.vchkpw /var/vpopmail/domains

# Add domain in vpopmail
/var/vpopmail/bin/vadddomain ${DEFAULT_DOMAIN} "${POSTMASTER_PWD}"

# SpamAssassin DB
echo "CREATE TABLE spam_prefs (
  id int(8) UNSIGNED NOT NULL,
  username varchar(128) NOT NULL DEFAULT '',
  preference varchar(64) NOT NULL DEFAULT '',
  value varchar(128) DEFAULT NULL,
  added datetime NOT NULL DEFAULT current_timestamp(),
  modified timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  UNIQUE KEY id (id),
  KEY preference (preference),
  KEY username (username)
) ENGINE=InnoDB DEFAULT CHARSET=latin1 COMMENT='Spamassassin Preferences';
INSERT INTO spam_prefs (id, username, preference, value, added, modified) VALUES
(1, '\$GLOBAL', 'required_hits', '7.0', '2003-10-11 00:00:00', '2013-09-10 00:00:00'),
(2, '\$GLOBAL', 'report_safe', '0', '2003-10-11 00:00:00', '2013-09-10 00:00:00'),
(3, '\$GLOBAL', 'fold_headers', '1', '2003-10-11 00:00:00', '2013-09-10 00:00:00'),
(4, '\$GLOBAL', 'add_header', 'all Level _STARS(*)_', '2003-10-11 00:00:00', '2013-09-10 00:00:000'),
(5, '\$GLOBAL', 'rewrite_header', 'Subject [SPAM]', '2003-10-11 00:00:00', '2013-09-10 00:00:00'),
(6, '\$GLOBAL', 'ok_languages', 'en fr', '2003-10-11 00:00:00', '2013-09-10 00:00:00'),
(7, '\$GLOBAL', 'refuse_threshold', '9', '2003-10-11 00:00:00', '2013-09-10 00:00:00');
" | mysql -h ${MARIADB_HOST} -u ${MARIADB_USER} -p"${MARIADB_PASS}" ${MARIADB_DB}

echo "============================"
echo " QMail AllInOne initialized"
echo "============================"
