#!/usr/bin/bash

function delayedProcess {
	sleep 5
	echo "[DELAYED] Set qmail-send supervion perms"
	/bin/s6-svperms -G www-data /service/qmail-send
}

if [ -n "${SKIP_INIT_ENV}" ]; then
  exec $@
  exit
fi

/opt/bin/upgrade/sqmail_aio_upgrade.sh

if [ -n "${DEV_MODE}" ]; then
	sed '/^ExcludeDatabase/d' -i /etc/clamav/freshclam.conf
	echo "ExcludeDatabase main
ExcludeDatabase daily" >> /etc/clamav/freshclam.conf
fi

if [ ! -s "/var/qmail/queue/lock" ]; then
	echo "[QMail] Initializing queue directories ..."
	cp -a /opt/templates/queue /var/qmail/
fi

if [ -e "/var/qmail/control/aio-conf/dmarc.conf" ]; then
	echo "[DMARC] Setting config file  ..."
	. /var/qmail/control/aio-conf/mysql.conf
	. /var/qmail/control/aio-conf/dmarc.conf
    cat /opt/templates/dmarc.conf | envsubst '$MYSQL_USER $MYSQL_PASS $MYSQL_HOST $MYSQL_DB $DMARC_EMAIL_ADDR $DMARC_EMAIL_PASS' /var/www/admin/dmarc/config/conf.php
fi

if [ ! -e "/etc/fcrontab" ]; then
	echo "[QMail] Initializing fcrontab ..."
    cp /opt/templates/fcrontab /etc/fcrontab
    if [ -e "/var/qmail/control/aio-conf/dmarc.conf" ]; then
        cat /opt/templates/fcrontab-dmarc > /etc/fcrontab
    fi
    rm -rf /var/spool/fcron/root
	/usr/bin/fcrontab -n /opt/templates/fcrontab root
fi

if [ ! -e "/etc/fetchmail.conf" ]; then
    echo "[FETCHMAIL] Setting config file ..."
    . /var/qmail/control/aio-conf/mysql.conf
    cat > /etc/fetchmail.conf << EOF
\$db_host='${MYSQL_HOST}';
\$db_name='${MYSQL_DB}';
\$db_username='${MYSQL_USER}';
\$db_password='${MYSQL_PASS}';
EOF
fi

if [ ! -e "/etc/dovecot/conf.d/10-auth.conf" ]; then
    echo "[DOVECOT] Setting auth file ..."
    DEFAULT_DOMAIN=$(cat /var/qmail/control/defaultdomain)
	sed "s/auth_default_realm =.*/auth_default_realm = ${DEFAULT_DOMAIN}/" /opt/templates/dovecot-auth.conf > /etc/dovecot/conf.d/10-auth.conf
fi

if [ ! -s "/var/lib/clamav" ]; then
	echo "[CLAMAV] Lanching first time freshclam ..."
	/usr/bin/freshclam 
fi

if [ ! -e "/etc/mail/spamassassin/sql.cf" ]; then
	echo "[SPAMASSASSIN] Setting sql confog ..."
    . /var/qmail/control/aio-conf/mysql.conf
	cat > /var/qmail/control/spamassassin_sql.cf << EOF
# User prefs
user_scores_dsn DBI:mysql:${MYSQL_DB}:${MYSQL_HOST}
user_scores_sql_username ${MYSQL_USER}
user_scores_sql_password ${MYSQL_PASS}
user_scores_sql_custom_query SELECT preference, value FROM spam_prefs WHERE username = _USERNAME_ OR username = '\$GLOBAL' OR username = CONCAT('%',_DOMAIN_) ORDER BY username ASC
EOF
fi

if [ ! -s "/var/lib/spamassassin/" ]; then
	echo "[SPAMASSASSIN] Lanching first time sa-update ..."
	/usr/local/bin/sa-update
fi

if [ ! -e "/var/www/html/config/config.inc.php" ]; then
    echo "[ROUNDCUBE] Setting main and plugin config files ..."
   	. /var/qmail/control/aio-conf/mysql.conf
	. /var/qmail/control/aio-conf/roundcube.conf
	for OCONF in /var/www/html/config/*.tpl /var/www/html/plugins/*/*.tpl; do
		DCONF=${OCONF:0:-4}
		cat $OCONF | envsubst '$MYSQL_USER $MYSQL_PASS $MYSQL_HOST $MYSQL_DB $PRODUCT_NAME $SUPPORT_URL' > $DCONF
	done
fi

if [ ! -e "/etc/mailname" ]; then
    echo "[SYSTEM] Setting /etc/mailname file ..."
    cp /var/qmail/control/me /etc/mailname
fi

SMTP_SERVER=$(cat /var/qmail/control/me)
if [ -z $(grep "$SMTP_SERVER" "/etc/hosts") ]; then
    echo "[SYSTEM] Fix hosts file"
    echo "$SMTP_SERVER" >> /etc/hosts
fi

echo "[SYSTEM] Setting file permissions ..."

# Fix qmail tmp permissions
chown vpopmail:sqmail -R /var/qmail/tmp
chmod 777 /var/qmail/tmp

# Fix Fecthmail permissions
mkdir -p /var/run/fetchmail
chown vpopmail:sqmail /var/run/fetchmail

# Some fixes
rm -f /var/run/dovecot/master.pid
rm -f /var/run/lighttpd-log.pipe

# Fix for qmailadmin
> /var/log/qma-auth.log
chown vpopmail:vchkpw /var/log/qma-auth.log

delayedProcess &

echo "#> Lauching $@"
exec $@