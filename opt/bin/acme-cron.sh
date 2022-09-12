#!/bin/bash

if [ ! -s "/ssl/acme" ]; then
	exit 0
fi

# Renew certs
/usr/bin/acme.sh --home /ssl/acme --cron

# Copy the certs
cat /ssl/acme/hosts.lst | while read LINE; do
	KIND=`echo $LINE | cut -d ';' -f 1`
	HOST=`echo $LINE | cut -d ';' -f 2`
	rm -f /ssl/${KIND}.crt /ssl/${KIND}.key 
	cp /ssl/acme/certs/${HOST}/fullchain.cer /ssl/${KIND}.crt
	cp /ssl/acme/certs/${HOST}/${HOST}.key /ssl/${KIND}.key
done

/usr/local/bin/qmailctl restart
