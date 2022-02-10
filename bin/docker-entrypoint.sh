#!/bin/bash

# Fix qmail tmp permissions
chown qmaill.sqmail -R /var/qmail/tmp

# Fix some config file who was not in volumes
cp /var/qmail/control/spamassassin_sql.cf /etc/mail/spamassassin/sql.cf
cp /var/qmail/control/mailname /etc/mailname

if [ ! -s "/var/lib/clamav" ]; then
	echo "[CLAMAV] Lanching first time freshclam ..."
	/usr/bin/freshclam 
fi

if [ ! -s "/var/lib/spamassassin/" ]; then
	echo "[SPAMASSASSIN] Lanching first time sa-update ..."
	/usr/local/bin/sa-update
fi

$@