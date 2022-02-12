#!/bin/bash
set -e

# QMAIL
echo "${QMAIL_NB_REMOTE}" > /var/qmail/control/concurrencyremote
echo -n "${QMAIL_NB_INCOMING}" > /var/qmail/control/concurrencyincoming

# VPopmail
echo "default_quota ${VPOPMAIL_QUOTA}" > /var/vpopmail/etc/vlimits.default
echo "${VPOPMAIL_MYSQL_HOST}|0|${VPOPMAIL_MYSQL_USER}|${VPOPMAIL_MYSQL_PASS}|${VPOPMAIL_MYSQL_DB}" > /var/vpopmail/etc/vpopmail.mysql
echo "${VPOPMAIL_DEFAULT_DOMAIN}" > /var/vpopmail/etc/defaultdomain
chown 644 /var/vpopmail/etc/*

####################################### TODO
### https://notes.sagredo.eu/en/qmail-notes-185/configuring-qmail-83.html
### https://notes.sagredo.eu/en/qmail-notes-185/testing-qmail-smtp-and-auth-22.html

cat > /var/mail/control/spamassassin_sql.cf << 'EOF'
# User prefs
user_scores_dsn DBI:mysql:vpopmail:mariadb
user_scores_sql_username vpopmail
user_scores_sql_password 85p45r28zj654Vkp
user_scores_sql_custom_query     SELECT preference, value FROM spam_prefs WHERE username = _USERNAME_ OR username = '$GLOBAL' OR username = CONCAT('%',_DOMAIN_) ORDER BY username ASC
EOF

# Dovecot
openssl dhparam -out /ssl/qmail-dhparam 2048
openssl dhparam -out /ssl/dovecot-dhparam 2048		

mkdir -p /var/qmail/control/domainkeys

mkdir -p /var/spamassassin/auto-whitelist
mkdir -p /var/spamassassin/bayes
mkdir -p /var/spamassassin/razor
chown -R vpopmail.vchkpw /var/spamassassin


/var/qmail/control/mailname 
