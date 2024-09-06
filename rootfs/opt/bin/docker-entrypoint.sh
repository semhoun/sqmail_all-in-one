#!/usr/bin/bash

function delayedProcess {
	sleep 5
	echo "[DELAYED] Set qmail-send supervion perms"
	/bin/s6-svperms -G www-data /service/qmail-send
}

function writeRoundCubeConf {
	# Launch with &, so export will not in main env
	. /var/qmail/control/aio-conf/roundcube.conf
	for OCONF in /var/www/html/config/*.tpl /var/www/html/plugins/*/*.tpl; do
		DCONF=${OCONF:0:-4}
		cat $OCONF | envsubst '$MYSQL_USER $MYSQL_PASS $MYSQL_HOST $MYSQL_DB $PRODUCT_NAME $SUPPORT_URL' > $DCONF
	done
}

function fixDovecotConf {
	DEFAULT_DOMAIN=$(cat /var/qmail/control/defaultdomain)
	sed -i "s/auth_default_realm =.*/auth_default_realm = ${DEFAULT_DOMAIN}/" /etc/dovecot/conf.d/10-auth.conf
}

function fixHosts {
	SMTP_SERVER=$(cat /var/qmail/control/me)
	if [ -z $(grep "$SMTP_SERVER" "/etc/hosts") ]; then
		echo "$SMTP_SERVER" >> /etc/hosts
	fi
}

if [ -n "${SKIP_INIT_ENV}" ]; then
  exec $@
  exit
fi

if [ "$(cat /var/qmail/control/aio-conf/sqmail_aio_version)" != "1.4" ]; then
	/opt/bin/sqmail_aio_upgrade.sh
fi

if [ -n "${DEV_MODE}" ]; then
	sed '/^ExcludeDatabase/d' -i /etc/clamav/freshclam.conf
	echo "ExcludeDatabase main
ExcludeDatabase daily" >> /etc/clamav/freshclam.conf
fi

if [ ! -s "/var/qmail/queue/lock" ]; then
	echo "[QMail] Initializing queue directories ..."
	cp -a /opt/templates/queue /var/qmail/
fi

if [ ! -f "/var/spool/fcron/root" ]; then
	echo "[QMail] Initializing fcrontab ..."
	/usr/bin/fcrontab -n /opt/templates/fcrontab root
fi	

if [ ! -s "/var/lib/clamav" ]; then
	echo "[CLAMAV] Lanching first time freshclam ..."
	/usr/bin/freshclam 
fi

if [ ! -s "/var/lib/spamassassin/" ]; then
	echo "[SPAMASSASSIN] Lanching first time sa-update ..."
	/usr/local/bin/sa-update
fi

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

# Fix some config file who was not in volumes
cp /var/qmail/control/spamassassin_sql.cf /etc/mail/spamassassin/sql.cf
cp /var/qmail/control/me /etc/mailname

fixDovecotConf
fixHosts
writeRoundCubeConf

delayedProcess &

echo "#> Lauching $@"
exec $@