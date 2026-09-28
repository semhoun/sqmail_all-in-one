#!/usr/bin/bash
# The wizard is for a new installation (documented SKIP_INIT_ENV=1 path),
# never a repair command for an existing or partially initialized installation.
if [ -e /var/qmail/control/aio-conf/mysql.conf ] || [ -e /var/qmail/control/roundcube.conf ]; then
  echo "Existing configuration found; use the startup migration, not the initialization wizard." >&2
  exit 1
fi
RESUME=$(mktemp /tmp/sqmail.XXXXXX)
: > "${RESUME}"

#########################
# Gui for params
#########################

#https://en.wikibooks.org/wiki/Bash_Shell_Scripting/Whiptail
whiptail --title "S/QMail AIO" --msgbox "Welcome in the S/QMail first time configuration\MYSQL database must already been created" 8 78

# MYSQL
MYSQL_HOST=$(whiptail --inputbox "MYSQL Host" 8 39 "" --title "MYSQL configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
MYSQL_DB=$(whiptail --inputbox "MYSQL Database" 8 39 "" --title "MYSQL configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
MYSQL_USER=$(whiptail --inputbox "MYSQL Username" 8 39 "" --title "MYSQL configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
MYSQL_PASS=$(whiptail --inputbox "MYSQL Password" 8 39 "" --title "MYSQL configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi

cat >> "${RESUME}" <<EOF
Mysql configration will be:
  - host : ${MYSQL_HOST}
  - database : ${MYSQL_DB}
  - username : ${MYSQL_USER}
  - password : ${MYSQL_PASS}
  
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
RELAY_IPS=$(whiptail --inputbox "IP or network to relay (separated by coma)" 8 39 "127.0.0.1,::1,192.168.1." --title "QMail/SMTP configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
RLSBSERVER=$(whiptail --inputbox "RBL-listed server" 8 39 "sbl-xbl.spamhaus.org" --title "QMail/SMTP configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi

cat >> "${RESUME}" << EOF
QMail/SMTP configuration will be:
  - concurrency incoming : ${CONCURRENCY_INCOMING}
  - concurrency remote : ${CONCURRENCY_REMOTE}
  - database : ${DATABYTES}
  - queue life time : ${QUEUELIFETIME}
  - spf behavior : ${SPFBEHAVIOR}
  - rslb server : ${RLSBSERVER}
  - relay allowed : ${RELAY_IPS}
  
EOF

SMTP_SERVER=$(whiptail --inputbox "SMTP server hostname, coud be different of the MX entry (must match the PTR entry or reverse DNS)" 12 50 "smtp.exemple.net" --title "Domain configuration" 3>&1 1>&2 2>&3)
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

ROUNDCUBE_SUPPORT=$(whiptail --inputbox "Roundcube support url (with https:// or mailto;" 12 50 "mailto:help@${DEFAULT_DOMAIN}" --title "Roundcube Webmail Configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
ROUNDCUBE_NAME=$(whiptail --inputbox "Roundcube name" 8 39 "Roundcube Webmail" --title "RoundCube Webmail Configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
cat >> "${RESUME}" << EOF
Roundcube Webmail configuration will be:
  - support url : ${ROUNDCUBE_SUPPORT}
  - roundcube name : ${ROUNDCUBE_NAME}
  
EOF

WEBADMIN_USER='admin'
WEBADMIN_PASSWORD=$(whiptail --inputbox "Webadmin password (user is ${WEBADMIN_USER})" 8 39 "" --title "Webadmin" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
cat >> "${RESUME}" << EOF
Webadmin configuration will be:
  - username : ${WEBADMIN_USER}
  - password : ${WEBADMIN_PASSWORD}

EOF

DEFAULT_LANGUAGE=$(whiptail --menu "Choose default language :" 15 50 3 --title "Language" "en" "English" "fr" "French" "it" "Italian" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
cat >> "${RESUME}" << EOF
Default language is : ${DEFAULT_LANGUAGE}

EOF

# Resume
whiptail --textbox "${RESUME}" 40 78
rm "${RESUME}"

if ! whiptail --title "Set configuration" --yesno "Apply the configuration." 8 78; then
  echo "You canceled the script"
  exit 0
fi

#-----------------------------------------------------------------------------#

#########################
# Create config
#########################
set -Eeuo pipefail
trap 'echo "Initialization failed; no completion marker was written. Preserve and inspect the partial installation before retrying." >&2' ERR
. /opt/bin/upgrade/common.sh
[ "${SQMAIL_AIO_VERSION:-}" = 1.8 ]
exec 9>/var/qmail/control/.aio-migration.lock
flock -n 9 || { echo "Another initialization/migration is running" >&2; exit 1; }
[ ! -e /var/qmail/control/aio-conf/mysql.conf ]
TABLES=$(mysql -N -B -h "$MYSQL_HOST" -u "$MYSQL_USER" -p"$MYSQL_PASS" "$MYSQL_DB" -e 'SHOW TABLES')
[ -z "$TABLES" ] || { echo "Initialization requires an empty database; nothing was imported." >&2; exit 1; }
mkdir -p /var/qmail/control/aio-conf
chmod 755 /var/qmail/control/aio-conf

export MYSQL_USER=${MYSQL_USER}
export MYSQL_PASS=${MYSQL_PASS}
export MYSQL_DB=${MYSQL_DB}
export MYSQL_HOST=${MYSQL_HOST}

export DEFAULT_DOMAIN=${DEFAULT_DOMAIN}

# Default config
echo "MAILER-DAEMON" > /var/qmail/control/bouncefrom
echo postmaster > /var/qmail/control/doublebounceto
echo '|/var/qmail/bin/preline -f /usr/libexec/dovecot/deliver -d $EXT@$USER' > /var/qmail/control/defaultdelivery

# SSL base Config
openssl dhparam -out /ssl/qmail-dhparam 2048

# Creation configuration
printf '%s=%q\n' MYSQL_USER "$MYSQL_USER" MYSQL_PASS "$MYSQL_PASS" MYSQL_DB "$MYSQL_DB" MYSQL_HOST "$MYSQL_HOST" |
  atomic_write /var/qmail/control/mysql.conf
printf 'export %s=%q\n' MYSQL_USER "$MYSQL_USER" MYSQL_PASS "$MYSQL_PASS" MYSQL_DB "$MYSQL_DB" MYSQL_HOST "$MYSQL_HOST" |
  atomic_write /var/qmail/control/aio-conf/mysql.conf
write_mysql_php

cat > /var/qmail/control/spamassassin_sql.cf << EOF
# User prefs
user_scores_dsn DBI:mysql:${MYSQL_DB}:${MYSQL_HOST}
user_scores_sql_username ${MYSQL_USER}
user_scores_sql_password ${MYSQL_PASS}
user_scores_sql_custom_query SELECT preference, value FROM spam_prefs WHERE username = _USERNAME_ OR username = '\$GLOBAL' OR username = CONCAT('%',_DOMAIN_) ORDER BY username ASC
EOF
echo -n "${CONCURRENCY_INCOMING}" > /var/qmail/control/concurrencyincoming
echo "${CONCURRENCY_REMOTE}" > /var/qmail/control/concurrencyremote
echo "${DATABYTES}" > /var/qmail/control/databytes
echo "${SPFBEHAVIOR}" > /var/qmail/control/spfbehavior
echo "${RLSBSERVER}" > /var/qmail/control/rslbserver
echo "${QUEUELIFETIME}" > /var/qmail/control/queuelifetime

# VPopmail configuration
echo "${MYSQL_HOST}|3306|${MYSQL_USER}|${MYSQL_PASS}|${MYSQL_DB}" > /var/vpopmail/etc/vpopmail.mysql
echo "${DEFAULT_DOMAIN}" > /var/vpopmail/etc/defaultdomain
cp /opt/templates/vlimits.default /var/vpopmail/etc/vlimits.default
cp /opt/templates/vusage* /var/vpopmail/etc/

# Qmail configuration from /package/mail/sqmail/sqmail/src/config-fast.sh
echo "${SMTP_SERVER}" > /var/qmail/control/me
echo "${DEFAULT_DOMAIN}" > /var/qmail/control/defaultdomain
echo "${DEFAULT_DOMAIN}" > /var/qmail/control/plusdomain
echo "${SMTP_SERVER}" >> /var/qmail/control/rcpthosts
echo "*:" >> /var/qmail/control/tlsdestinations
echo "=:" >> /var/qmail/control/dkimdomains

# Alias
cd /var/qmail/alias
echo "postmaster@${DEFAULT_DOMAIN}" > .qmail-postmaster
ln -s .qmail-postmaster .qmail-mailer-daemon
ln -s .qmail-postmaster .qmail-root
chown alias:sqmail .qmail*
chmod 644 .qmail*
 
# SRS
SRS_SECRET=$(openssl rand -hex 32)
cat > /var/qmail/control/srsdomains << EOF
*:${SRS_SECRET}|-|srs.
EOF
 
# Dovecot
cat /opt/templates/dovecot-local.conf | envsubst \
    '$MYSQL_USER $MYSQL_PASS $MYSQL_HOST $MYSQL_DB $DEFAULT_DOMAIN' \
    > /var/qmail/control/dovecot-local.conf
cat /opt/templates/dovecot-${DEFAULT_LANGUAGE}.conf >> /var/qmail/control/dovecot-local.conf
chown root:root /var/qmail/control/dovecot-local.conf
chmod 600 /var/qmail/control/dovecot-local.conf

# Creation directory and setting permissions
chown qmailq:sqmail /var/qmail/queue
# Administration backups must remain private, including their existing contents.
find /var/qmail/control -path /var/qmail/control/delivery-admin-backups -prune -o \
  -exec chown -h qmaild:sqmail {} +
for CONTROL_FILE in /var/qmail/control/*; do
  [ ! -f "$CONTROL_FILE" ] || chmod 644 "$CONTROL_FILE"
done
chown root:root /var/qmail/control/dovecot-local.conf
chmod 600 /var/qmail/control/dovecot-local.conf /var/qmail/control/aio-conf/mysql.conf
# qmail-queuescan runs as vpopmail and sources this legacy credential file.
chown root:vchkpw /var/qmail/control/mysql.conf
chmod 640 /var/qmail/control/mysql.conf
chown root:www-data /var/qmail/control/aio-conf/mysql.php
chmod 640 /var/qmail/control/aio-conf/mysql.php
if ! /opt/libexec/delivery-admin-init; then
  echo "[Delivery admin] Private storage unavailable; mutations remain disabled." >&2
fi
mkdir -p /var/qmail/ssl/domainkeys
chmod 755 /var/qmail/ssl/domainkeys
chown qmailq:sqmail /var/qmail/ssl/domainkeys
mkdir -p /var/spamassassin/bayes
mkdir -p /var/spamassassin/razor
echo "razorhome = /etc/mail/spamassassin/.razor/" > /var/spamassassin/razor/razor-agent.conf
chown -R vpopmail:vchkpw /var/spamassassin
for VPOPMAIL_FILE in /var/vpopmail/etc/*; do
  [ ! -f "$VPOPMAIL_FILE" ] || chmod 644 "$VPOPMAIL_FILE"
done
chown vpopmail:vchkpw /var/vpopmail/etc/vpopmail.mysql
chmod 640 /var/vpopmail/etc/vpopmail.mysql
chown -R vpopmail:vchkpw /var/vpopmail/domains

# Add domain in vpopmail
/var/vpopmail/bin/vadddomain "${DEFAULT_DOMAIN}" "${POSTMASTER_PWD}"

# SpamAssassin DB
mysql -h "$MYSQL_HOST" -u "$MYSQL_USER" -p"$MYSQL_PASS" "$MYSQL_DB" < /opt/sql/spamassassin.sql

# DMARC DB
php /opt/bin/upgrade/historical-schema.php dmarc

# Rules cdb
cat > /var/qmail/control/rules.smtpsub << EOF
:allow,RELAYCLIENT=''
EOF
: > /var/qmail/control/rules.smtpd
: > /var/qmail/control/rules.smtpsd
IPS=$(echo $RELAY_IPS | tr "," "\n")
for ip in ${IPS}; do
  echo "${ip}:allow,RELAYCLIENT=''" >> /var/qmail/control/rules.smtpd
  echo "${ip}:allow,RELAYCLIENT=''" >> /var/qmail/control/rules.smtpsd
done
echo ":allow,QHPSI='clamdscan',QHPSIARG1='--no-summary',MFDNSCHECK='',BADMIMETYPE='',BADLOADERTYPE='M',HELOCHECK='.',TARPITCOUNT='5',TARPITDELAY='20',QMAILQUEUE='bin/qmail-queuescan'" >> /var/qmail/control/rules.smtpd
echo ":allow,QHPSI='clamdscan',QHPSIARG1='--no-summary',MFDNSCHECK='',BADMIMETYPE='',BADLOADERTYPE='M',HELOCHECK='.',TARPITCOUNT='5',TARPITDELAY='20',QMAILQUEUE='bin/qmail-queuescan'" >> /var/qmail/control/rules.smtpsd
/opt/bin/qmailctl cdb

# Generate roundcube config
printf 'export %s=%q\n' SUPPORT_URL "$ROUNDCUBE_SUPPORT" PRODUCT_NAME "$ROUNDCUBE_NAME" |
  atomic_write /var/qmail/control/aio-conf/roundcube.conf

# Roundcube DB
mysql -h "$MYSQL_HOST" -u "$MYSQL_USER" -p"$MYSQL_PASS" "$MYSQL_DB" < /opt/sql/roundcube.sql
roundcube_config
php /opt/bin/upgrade/roundcube-schema.php

# Fetchmail DB
mysql -h "$MYSQL_HOST" -u "$MYSQL_USER" -p"$MYSQL_PASS" "$MYSQL_DB" < /opt/sql/fetchmail.sql

# lighttpd Password
/opt/bin/lighttpd_admin.sh "${WEBADMIN_USER}" "${WEBADMIN_PASSWORD}"

# i8n configuration
cat > /var/qmail/control/aio-conf/i8n.conf << EOF
export DEFAULT_LANGUAGE=${DEFAULT_LANGUAGE}
EOF

printf '%s\n' "$SQMAIL_AIO_VERSION" | atomic_write /var/qmail/control/aio-conf/sqmail_aio_version

echo "============================"
echo " QMail AllInOne initialized"
echo "============================"
