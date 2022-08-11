#!/bin/bash
RESUME=$(mktemp /tmp/sqmail.XXXXXX)
> ${RESUME}

#########################
# Gui for params
#########################

#https://en.wikibooks.org/wiki/Bash_Shell_Scripting/Whiptail
whiptail --title "Semhoun's SQMail Certs" --msgbox "Welcome in the SQMail Certs configuration" 8 78

LETSENCRYPT_EMAIL=$(whiptail --inputbox "Let's Encrypt account email" 8 39 "" --title "Let's Encrypt configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
HOST_WEBMAIL=$(whiptail --inputbox "Webmail domain name" 8 39 "" --title "Let's Encrypt configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
HOST_SMTP=$(whiptail --inputbox "SMTP domain name" 8 39 "" --title "Let's Encrypt configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
HOST_IMAP=$(whiptail --inputbox "IMAP domain name" 8 39 "" --title "Let's Encrypt configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi
HOST_POP=$(whiptail --inputbox "POP domain name" 8 39 "" --title "Let's Encrypt configuration" 3>&1 1>&2 2>&3)
if [ $? != 0 ]; then echo "You canceled the script"; exit 0; fi

ACME_SERVER="https://acme-v02.api.letsencrypt.org/directory"

cat >> "${RESUME}" <<EOF
Let's encrypt account email will be ${LETSENCRYPT_EMAIL}

Domains will be:
  - webmail : ${HOST_WEBMAIL}
  - smtp : ${HOST_SMTP}
  - imap : ${HOST_IMAP}
  - pop : ${HOST_POP}
	
EOF

# Resume
whiptail --textbox "${RESUME}" 30 78
rm "${RESUME}"

if !(whiptail --title "Set configuration" --yesno "Apply the configuration." 8 78); then
  echo "You canceled the script"
  exit 0
fi

#-----------------------------------------------------------------------------#

#########################
# Start lighttpd 
#########################
openssl req -new -x509 -keyout /ssl/http.key -out /ssl/http.crt -days 365 -nodes -subj '/CN=${HOST_WEBMAIL}'
touch /var/run/lighttpd-log.pipe
chown www-data.www-data /var/run/lighttpd-log.pipe
/usr/sbin/lighttpd -D -f /etc/lighttpd/lighttpd.conf &
LPID=$!

#########################
# Initialize acme directory
#########################
cp -a /qmail-aio/templates/acme /ssl/acme

#########################
# Configure email account
#########################
sed -i "s/_ACCOUNT_EMAIL_/${LETSENCRYPT_EMAIL}/" /ssl/acme/account.conf

#########################
# Get the certs
#########################
> /ssl/acme/hosts.lst
if [ -n "${HOST_WEBMAIL}" ]; then
	if [ ! -s "/ssl/acme/certs/${HOST_WEBMAIL}/fullchain.cer" ]; then
		acme.sh --home /ssl/acme --issue --server ${ACME_SERVER} --webroot /var/www/html -d ${HOST_WEBMAIL}
	fi
	echo "http;${HOST_WEBMAIL}" >> /ssl/acme/hosts.lst
fi
if [ -n "${HOST_SMTP}" ]; then
	if [ ! -s "/ssl/acme/certs/${HOST_SMTP}/fullchain.cer" ]; then
		acme.sh --home /ssl/acme --issue --server ${ACME_SERVER} --webroot /var/www/html -d ${HOST_SMTP}
	fi
	echo "smtp;${HOST_SMTP}" >> /ssl/acme/hosts.lst
fi
if [ -n "${HOST_IMAP}" ]; then
	if [ ! -s "/ssl/acme/certs/${HOST_SMTP}/fullchain.cer" ]; then
		acme.sh --home /ssl/acme --issue --server ${ACME_SERVER} --webroot /var/www/html -d ${HOST_IMAP}
	fi
	echo "imap;${HOST_IMAP}" >> /ssl/acme/hosts.lst
fi
if [ -n "${HOST_POP}" ]; then
	if [ ! -s "/ssl/acme/certs/${HOST_POP}/fullchain.cer" ]; then
		acme.sh --home /ssl/acme --issue --server ${ACME_SERVER} --webroot /var/www/html -d ${HOST_POP}
	fi
	echo "pop;${HOST_POP}" >> /ssl/acme/hosts.lst
fi

#########################
# Copy the certs
# !!!!!! Same as in acme-cron.sh
#########################
cat /ssl/acme/hosts.lst | while read LINE; do
	KIND=`echo $LINE | cut -d ';' -f 1`
	HOST=`echo $LINE | cut -d ';' -f 2`
	rm -f /ssl/${KIND}.crt /ssl/${KIND}.key 
	cp /ssl/acme/certs/${HOST}/fullchain.cer /ssl/${KIND}.crt
	cp /ssl/acme/certs/${HOST}/${HOST}.key /ssl/${KIND}.key
done

#########################
# Stop lighttpd 
#########################
kill -9 $LPID

echo "===========================------="
echo " QMail AllInOne certs initialized"
echo "============================------"
