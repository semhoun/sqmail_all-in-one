#!/bin/bash

if [ -n "${SKIP_INIT_ENV}" ]; then
  exec $@
  exit
fi

if [ -n "${DEV_MODE}" ]; then
  sed -e "s/Example/#Exemple/" \
    -e "s/#PidFile .*/PidFile \/var\/run\/freshclam.pid/" \
    -e "s/#DNSDatabaseInfo .*/DNSDatabaseInfo current.cvd.clamav.net/" \
    -e "s/#DatabaseMirror .*/DatabaseMirror database.clamav.net/" \
    /etc/clamav/freshclam.conf.sample > /etc/clamav/freshclam.conf
    echo "
ExcludeDatabase main
ExcludeDatabase daily
" >> /etc/clamav/freshclam.conf
fi

if [ ! -s "/var/qmail/queue/lock" ]; then
	echo "[QMail] Initializing queue directories ..."
	cp -a /qmail-aio/templates/queue /var/qmail/
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
chown qmaill.sqmail -R /var/qmail/tmp

# Some fixes
rm -f /var/run/dovecot/master.pid
rm -f /var/run/lighttpd-log.pipe

# Fix some config file who was not in volumes
cp /var/qmail/control/spamassassin_sql.cf /etc/mail/spamassassin/sql.cf
cp /var/qmail/control/me /etc/mailname

echo "#> Lauching $@"
exec $@