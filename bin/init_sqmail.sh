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

cat > /var/qmail/control/spamassassin_sql.cf << 'EOF'
# User prefs
user_scores_dsn DBI:mysql:vpopmail:localhost
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


cat > /etc/cron.d/clamav << EOF
00 08 * * * root /usr/local/bin/freshclam --quiet
EOF
cat > /etc/cron.d/dccd << 'EOF'
15 02 * * * root /var/dcc/libexec/cron-dccd
EOF
cat >> /etc/cron.d/spamassassin << 'EOF'
# learnSpam
0 2 * * * root sudo -u vpopmail -H /var/qmail/bin/learnSpam >/dev/null
EOF
echo "# sa-update
11 03 */10 * * root /usr/local/bin/sa-update > /dev/null
" > /etc/cron.d/spamassassin
cat >> /etc/cron.d/spamassassin << 'EOF'
# learnSpam
0 2 * * * root sudo -u vpopmail -H /var/qmail/bin/learnSpam >/dev/null
EOF

# Fichier de conf dans /var/spamassassin/*

!!!!!!!!!!!!!! ca fait quoi:
/usr/local/bin/freshclam 
sa-update

# Import
	cd /var
	tar xvzf /tmp/oldLeto/var.spamassassin.tgz
	chmod -R 777 /var/
	
	sed -i "s/$OLDIP/$NEWIP/g" /var/qmail/control/rules.smtpd
sed -i "s#$OLDIP#$NEWIP#g" /var/qmail/control/badhelo
qmailctl cdb

cd /tmp/
tar xvzf /tmp/oldLeto/var.qmail.tgz
rm -f /var/qmail/control/*
cp /tmp/qmail/control/* /var/qmail/control/
cp /tmp/qmail/etc/* /var/qmail/control/
rm -f /var/qmail/control/*.lock
cp /tmp/qmail/users/assign /var/qmail/users/
/var/qmail/bin/qmail-newu #Eventuellement vérifier les users uid:gid
rm -f /var/qmail/alias/.qmail-*
cp -p /tmp/qmail/alias/.qmail* /var/qmail/alias/
cd /tmp/
cat /tmp/oldLeto/var.vpopmail.tgz.* | tar xvzfp -
mv /tmp/vpopmail/domains/* /var/vpopmail/domains
mv /tmp/vpopmail/domains/.dir-control /var/vpopmail/domains

########################
# Ram Disk pour QMAIL
########################
echo -e "tmpfs /var/qmail/tmp tmpfs defaults,size=256M,uid=qmaill,gid=sqmail,mode=777 0 0" >> /etc/fstab
mkdir -p /var/qmail/tmp
chown qmaill.sqmail /var/qmail/tmp
mount /var/qmail/tmp

##CHecker
sed -i 's/selector=default/selector=leto/' http://www.memoryhole.net/qmail/qmail-remote.sh


