#!/bin/bash

if [ ! -f "/var/qmail/control" ]; then
	init_sqmail.sh
fi

# Create log directories
mkdir -p /log/dovecot
chown dovecot:docker /log/dovecot
mkdir -p /log/clamd
chown clamav:docker /log/clamd 
mkdir -p /log/spamd /log/qmail-send /log/ /log/ /log/
chown qmaill:docker /log/spamd /log/qmail-send /log/ /log/ /log/

# Fix qmail tmp permissions
chown qmaill.sqmail -R /var/qmail/tmp

cp /var/qmail/control/spamassassin_sql.cf /etc/mail/spamassassin/sql.cf

$@