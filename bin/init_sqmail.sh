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
whiptail --textbox "${RESUME}" 20 78
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

# Creation directory and setting permissions
mkdir -p /var/qmail/control/domainkeys
chown -R qmailr:qmail /var/qmail/control
chmod 644 /var/qmail/control/*
mkdir -p /var/spamassassin/auto-whitelist
mkdir -p /var/spamassassin/bayes
mkdir -p /var/spamassassin/razor
chown -R vpopmail.vchkpw /var/spamassassin
chown 644 /var/vpopmail/etc/*

# Add domain in vpopmail
/var/vpopmail/bin/vadddomain ${DEFAULT_DOMAIN} "${POSTMASTER_PWD}"

exit

echo "*:" >> /var/qmail/control/tlsdestinations !!! not in prod