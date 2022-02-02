########################
# Mail
########################
apt-get -y purge exim4-base exim4-config exim4-daemon-light exim4
cd /tmp
wget http://qmailrocks.thibs.com/downloads/deb-packages/mta-local_1.0_all.deb
dpkg -i mta-local_1.0_all.deb
apt-get -y install libperl-dev libmariadb-dev libmariadbclient-dev csh maildrop bzip2 razor pyzor ksh libnet-dns-perl libio-socket-inet6-perl libdigest-sha-perl libnetaddr-ip-perl libmail-spf-perl libgeo-ip-perl libnet-cidr-lite-perl libmail-dkim-perl libnet-patricia-perl libencode-detect-perl libperl-dev libssl-dev libcurl4-gnutls-dev
mkdir -p /usr/local/src/backup-qmail
mkdir -p /package
chmod 1755 /package
########################
# SQMail
########################
## fehQlibs
cd /usr/local/src/backup-qmail
wget http://www.fehcom.de/ipnet/fehQlibs/fehQlibs-14.tgz
cd /usr/local/
tar xvzf /usr/local/src/backup-qmail/fehQlibs-14.tgz
mv fehQlibs-14 qlibs 
cd qlibs 
make
## Daemontools
cd /package
wget http://cr.yp.to/daemontools/daemontools-0.76.tar.gz
tar xvzf daemontools-0.76.tar.gz
mv daemontools-0.76.tar.gz /usr/local/src/backup-qmail
cd admin/daemontools-0.76
sed -i '1s/$/ -include \/usr\/include\/errno\.h/' src/conf-cc
package/install
## ucspi-ssl
cd /package
wget http://www.fehcom.de/ipnet/ucspi-ssl/ucspi-ssl-0.11.4.tgz
tar xvzf ucspi-ssl-0.11.4.tgzgrep
mv ucspi-ssl-0.11.4.tgz /usr/local/src/backup-qmail
cd host/superscript.com/net/ucspi-ssl-0.11.4
package/install
## ucspi-tcp6
cd /package
wget http://www.fehcom.de/ipnet/ucspi-tcp6/ucspi-tcp6-1.11.4.tgz
tar xvzf ucspi-tcp6-1.11.4.tgz
mv ucspi-tcp6-1.11.4.tgz /usr/local/src/backup-qmail
cd net/ucspi-tcp6/ucspi-tcp6-1.11.4/
package/install
## sqmail
cd /package
wget http://www.fehcom.de/sqmail/sqmail-4.0.06.tgz
tar xvzf sqmail-4.0.06.tgz
mv sqmail-4.0.06.tgz /usr/local/src/backup-qmail
cd mail/sqmail/sqmail-4.0.06
# Config modification
sed -i '1s/002/022/' conf-patrn
package/install
rm -rf /service/qmail-pop3*
rm -rf /var/log/qmail-pop3*
cp /var/qmail/bin/sendmail /usr/sbin/sendmail
rm /service/*/down
########################
### Qmail service perso
########################
mkdir -f /var/qmail/etc
echo 5 > /var/qmail/control/concurrencyremote
echo -n "50" > /var/qmail/control/concurrencyincoming
cat > /var/qmail/svc/qmail-smtpd/run << 'EOF'
#!/bin/sh
QMAILDUID=`id -u vpopmail`
QMAILDGID=`id -g vpopmail`
HOSTNAME=`cat /etc/mailname | head -1`
CONCURRENCY=`cat /var/qmail/control/concurrencyincoming`
export SMTPAUTH=""
export UCSPITLS=""
. /var/qmail/ssl/env
exec env PATH="/var/qmail/bin:$PATH" \
    sslserver \
    -4 -6 \
    -seVn -Rp -l $HOSTNAME -c $CONCURRENCY \
    -Xx /var/qmail/control/rules.smtpd.cdb \
    -u $QMAILDUID -g $QMAILDGID :0 smtp \
    /usr/local/bin/rblsmtpd -W -C -r sbl-xbl.spamhaus.org \
    /var/qmail/bin/qmail-smtpd /var/vpopmail/bin/vchkpw true maildir  2>&1
EOF
cat > /var/qmail/svc/qmail-smtpsd/run << 'EOF'
#!/bin/sh
QMAILDUID=`id -u vpopmail`
QMAILDGID=`id -g vpopmail`
HOSTNAME=`cat /etc/mailname | head -1`
CONCURRENCY=`cat /var/qmail/control/concurrencyincoming`
export SMTPAUTH=""
export UCSPITLS=""
. /var/qmail/ssl/env
exec env PATH="/var/qmail/bin:$PATH" \
    sslserver \
    -4 -6 \
    -seVn -Rp -l $HOSTNAME -c $CONCURRENCY \
    -Xx /var/qmail/control/rules.smtpsd.cdb \
    -u $QMAILDUID -g $QMAILDGID :0 smtps \
    /usr/local/bin/rblsmtpd -W -C -r sbl-xbl.spamhaus.org \
    /var/qmail/bin/qmail-smtpd /var/vpopmail/bin/vchkpw true maildir  2>&1
EOF
cat > /var/qmail/svc/qmail-smtpsub/run << 'EOF'
#!/bin/sh
QMAILDUID=`id -u vpopmail`
QMAILDGID=`id -g vpopmail`
HOSTNAME=`cat /etc/mailname | head -1`
CONCURRENCY=`cat /var/qmail/control/concurrencyincoming`
export SMTPAUTH="!"
export UCSPITLS=""
. /var/qmail/ssl/env
exec env PATH="/var/qmail/bin:$PATH" \
   sslserver \
    -4 -6 \
    -seVn -Rp -l $HOSTNAME -c $CONCURRENCY \
    -x /var/qmail/control/rules.smtpsub.cdb \
    -u $QMAILDUID -g $QMAILDGID :0 submission \
    /var/qmail/bin/qmail-smtpd /var/vpopmail/bin/vchkpw true 2>&1
EOF
cat > /var/qmail/svc/qmail-send/run << 'EOF'
#!/bin/sh
exec env - PATH="/var/qmail/bin:$PATH" \
    qmail-start ./Maildir/
EOF
########################
# Ram Disk pour QMAIL
########################
echo -e "tmpfs /var/qmail/tmp tmpfs defaults,size=256M,uid=qmaill,gid=sqmail,mode=777 0 0" >> /etc/fstab
mkdir -p /var/qmail/tmp
chown qmaill.sqmail /var/qmail/tmp
mount /var/qmail/tmp
########################
# VPopMail
########################
mkdir -p /var/vpopmail/etc
groupadd -g 2110 vchkpw
useradd -g vchkpw -u 7800 -s /usr/sbin/nologin -d /var/vpopmail vpopmail
chown -R vpopmail.vchkpw /var/vpopmail
cd /usr/local/src/
wget http://downloads.sourceforge.net/project/vpopmail/vpopmail-stable/5.4.33/vpopmail-5.4.33.tar.gz
tar xvzf vpopmail-5.4.33.tar.gz
mv vpopmail-5.4.33.tar.gz /usr/local/src/backup-qmail
cd vpopmail-5.4.33
sed -i 's#lmysqlclient#lmariadbclient#g' configure
./configure --enable-tcpserver-file=/var/qmail/control/relays.cdb --enable-valias --enable-auth-module=mysql --disable-mysql-limits --enable-auth-logging --enable-sql-logging --disable-roaming-users --enable-qmail-ext  --enable-incdir=/usr/include/mariadb --enable-libdir=/usr/lib
make
make install
echo "localhost|0|vpopmail|85p45r28zj654Vkp|vpopmail
localhost|0|vpopmail|85p45r28zj654Vkp|vpopmail" > /var/vpopmail/etc/vpopmail.mysql
echo "semhoun.net" > /var/vpopmail/etc/defaultdomain
chmod 644 /var/vpopmail/etc/vpopmail.mysql
chmod 644 /var/vpopmail/etc/defaultdomain
########################
# DoveCot
########################
groupadd dovecot
useradd -g dovecot -s /usr/sbin/nologin -d /var/run dovenull
useradd -g dovecot -s /usr/sbin/nologin -d /var/run dovecot
cd /usr/local/src/
wget https://dovecot.org/releases/2.3/dovecot-2.3.7.2.tar.gz
tar xvzf dovecot-2.3.7.2.tar.gz
mv dovecot-2.3.7.2.tar.gz /usr/local/src/backup-qmail
cd dovecot-2.3.7.2
./configure --sysconfdir=/etc --with-vpopmail
make
make install
openssl dhparam -out /etc/dovecot/dh.pem 2048
cp -r /usr/local/share/doc/dovecot/example-config/* /etc/dovecot/
sed -i 's@#!include auth-vpopmail.conf.ext@!include auth-vpopmail.conf.ext@' /etc/dovecot/conf.d/10-auth.conf
sed -i 's@!include auth-system.conf.ext@#!include auth-system.conf.ext@' /etc/dovecot/conf.d/10-auth.conf
sed -i 's@#disable_plaintext_auth = yes@disable_plaintext_auth = no@' /etc/dovecot/conf.d/10-auth.conf
sed -i 's@#log_path = syslog@log_path = /dev/stderr@' /etc/dovecot/conf.d/10-logging.conf
sed -i "s|#mail_max_userip_connections.*|mail_max_userip_connections = 25|" /etc/dovecot/conf.d/20-imap.conf
sed -i "s|#mail_max_userip_connections.*|mail_max_userip_connections = 25|" /etc/dovecot/conf.d/20-pop3.conf
cat > /etc/dovecot/conf.d/10-ssl.conf << 'EOF'
echo "ssl = yes
ssl_cert = </ssl/imap.crt
ssl_key = </ssl/imap.key
protocol imap {
  ssl_cert = </ssl/imap.crt
  ssl_key = <//ssl/imap.key
}
protocol pop3 {
  ssl_cert = </ssl/pop.crt
  ssl_key = <sl/pop.key
}
ssl_dh=</etc/dovecot/dh.pem
EOF
cat > /etc/dovecot/conf.d/90-stats.conf << EOF
mail_plugins = $mail_plugins old_stats
protocol imap {
  mail_plugins = $mail_plugins imap_old_stats
}
plugin {
  # how often to session statistics (must be set)
  old_stats_refresh = 30 secs
  # track per-IMAP command statistics (optional)
  old_stats_track_cmds = yes
}
service old-stats {
  fifo_listener old-stats-mail {
    user = vpopmail
    mode = 0600
  }
  fifo_listener old-stats-user {
    user = vpopmail
    mode = 0600
  }
  inet_listener {
    address = 127.0.0.1
    port = 24242
  }
}
EOF
mkdir -p /var/qmail/svc/dovecot/log
mkdir -p /var/log/dovecot
chown dovecot /var/log/dovecot
echo '#!/bin/sh
exec /usr/local/sbin/dovecot -F 2>&1' > /var/qmail/svc/dovecot/run
echo '#!/bin/sh
exec setuidgid dovecot multilog t s2000000 /var/log/dovecot' > /var/qmail/svc/dovecot/log/run
chmod 755 /var/qmail/svc/dovecot/run
chmod 755 /var/qmail/svc/dovecot/log/run
ln -s /var/qmail/svc/dovecot /service
########################
# Autorespond
########################
cd /usr/local/src/
wget http://qmail.ixip.net/download/autorespond-2.0.5.tar.gz
tar xvzf autorespond-2.0.5.tar.gz
mv autorespond-2.0.5.tar.gz /usr/local/src/backup-qmail
cd autorespond-2.0.5
make
cp autorespond /usr/local/bin
chown root.root /usr/local/bin/autorespond
########################
# ezmlm-idx
########################
cd /usr/local/src/
wget https://qmailrocks.thibs.com/downloads/ezmlm-idx-7.2.2.tar.gz
tar xvzf ezmlm-idx-7.2.2.tar.gz
mv ezmlm-idx-7.2.2.tar.gz /usr/local/src/backup-qmail
cd ezmlm-idx-7.2.2
make && make man && make install
########################
# QmailAdmin
########################
cd /usr/local/src/
wget http://downloads.sourceforge.net/project/qmailadmin/qmailadmin-devel/qmailadmin-1.2.16.tar.gz
tar xvzf qmailadmin-1.2.16.tar.gz
mv qmailadmin-1.2.16.tar.gz /usr/local/src/backup-qmail
cd qmailadmin-1.2.16
./configure --enable-cgibindir=/var/www/admin/cgi-bin --enable-htmldir=/var/www/admin/www --enable-imagedir=/var/www/admin/www/images/qmailadmin --disable-ezmlm-mysql --enable-modify-quota --enable-domain-autofill --enable-modify-spam --enable-spam-command="|/var/qmail/bin/preline /usr/bin/maildrop /var/qmail/bin/maildrop-filter" --enable-help
make
make install
########################
# vqadmin
########################
cd /usr/local/src/
wget https://qmailrocks.thibs.com/downloads/vqadmin-2.3.7.tar.gz
tar xvzf vqadmin-2.3.7.tar.gz
mv vqadmin-2.3.7.tar.gz /usr/local/src/backup-qmail
cd vqadmin-2.3.7
sed -i 's#global_error("invalid language file",1,0);#return (-1);#' lang.c
./configure --enable-cgibindir=/var/www/admin/cgi-bin --build=i386
base64 -d > vqpatch << 'EOF'
ZGlmZiAtdSAtciAuLi92cWFkbWluLTIuMy43Lm9yaWcvY2dpLmMgLi9jZ2kuYwotLS0gLi4vdnFh
ZG1pbi0yLjMuNy5vcmlnL2NnaS5jCTIwMDMtMDEtMjcgMTk6MjU6NTkuMDAwMDAwMDAwICswMTAw
CisrKyAuL2NnaS5jCTIwMTMtMDItMTggMTY6MTA6MTkuNDU2OTc4NDQwICswMTAwCkBAIC0yMjcs
MTMgKzIyNyw3IEBACiAKICAgY2dpX2VudigpOwogCi0gIGVudiA9IGNnaV9pc19lbnYoIlJFTU9U
RV9VU0VSIik7Ci0gIGlmICghZW52KSB7Ci0gICAgZ2xvYmFsX2Vycm9yKCJVc2VybmFtZSB1bmtu
b3duIiwgMCwgMSk7Ci0gICAgdF9vcGVuKFRfQVVUSF9GQUlMRUQsIDEpOwotICB9Ci0KLSAgbWVt
Y3B5KChjaGFyICopdnFhX3VzZXIsIChjaGFyICopZW52LCBNQVhfR0xPQkFMX0xFTkdUSCk7Cisg
IG1lbWNweSgoY2hhciAqKXZxYV91c2VyLCAiYWRtaW4iLCBNQVhfR0xPQkFMX0xFTkdUSCk7CiAg
ICAKICAgYWNsX2luaXQoKTsKIAo=
EOF
patch -p0 < vqpatch
make
make install
cat > /var/www/admin/cgi-bin/vqadmin/vqadmin.acl << EOF
default - ...
admin * admin
EOF
mkdir /var/www/admin/www/images/vqadmin
cp html/vqadmin.css /var/www/admin/www/images/vqadmin
########################
# clamav
########################
groupadd -g 5010 clamav
useradd -g clamav -u 5010 -s /usr/sbin/nologin -c "Clam AntiVirus" -d /var/empty clamav
cd /usr/local/src
wget -O clamav-0.102.2.tar.gz https://www.clamav.net/downloads/production/clamav-0.102.2.tar.gz
tar xvzf clamav-0.102.2.tar.gz
mv clamav-0.102.2.tar.gz /usr/local/src/backup-qmail
cd clamav-0.102.2
./configure --sysconfdir=/etc 
make
make install
sed -e "s/Example/#Exemple/" \
    -e "s/#PidFile .*/PidFile \/var\/run\/freshclam.pid/" \
    -e "s/#DNSDatabaseInfo .*/DNSDatabaseInfo current.cvd.clamav.net/" \
    -e "s/#DatabaseMirror .*/DatabaseMirror db.fr.clamav.net/" \
    /etc/freshclam.conf.sample > /etc/freshclam.conf
sed -e "s/Example/#Exemple/" \
    -e "s/#LogVerbose .*/LogVerbose yes/" \
    -e "s/#LogClean .*/LogClean yes/" \
    -e "s/#LocalSocket .*/LocalSocket \/tmp\/clamd.socket/" \
    -e "s/#TCPSocket .*/TCPSocket 3310/" \
    -e "s/#TCPAddr .*/TCPAddr 127.0.0.1/" \
    -e "s/#ScanOLE2 .*/ScanOLE2 yes/" \
    -e "s/#OLE2BlockMacros .*/OLE2BlockMacros yes/" \
    -e "s/#ScanPDF .*/ScanPDF yes/" \
    -e "s/#ScanSWF .*/ScanSWF yes/" \
    -e "s/#ScanXMLDOCS .*/ScanXMLDOCS yes/" \
    -e "s/#ScanMail .*/ScanMail yes/" \
    -e "s/#Foreground .*/Foreground yes/" \
    /etc/clamd.conf.sample > /etc/clamd.conf
mkdir -p /var/qmail/svc/clamd/log
mkdir -p /var/log/clamd
chown clamav /var/log/clamd  
echo '#!/bin/sh
exec /usr/local/sbin/clamd 2>&1' > /var/qmail/svc/clamd/run
echo '#!/bin/sh
exec setuidgid clamav multilog t s2000000 /var/log/clamd' > /var/qmail/svc/clamd/log/run
chmod 755 /var/qmail/svc/clamd/run
chmod 755 /var/qmail/svc/clamd/log/run
ln -s /var/qmail/svc/clamd /service
mkdir /usr/local/share/clamav
chown clamav.clamav /usr/local/share/clamav
ldconfig -v
/usr/local/bin/freshclam 
cat > /etc/cron.d/clamav << EOF
00 08 * * * root /usr/local/bin/freshclam --quiet
EOF
echo "Html.Exploit.CVE_2016_0228-6327291-1" > /usr/local/share/clamav/whitelist-web.ign2
########################
# DCC
########################
cd /usr/local/src
wget https://www.dcc-servers.net/dcc/source/dcc.tar.Z
tar xvzf dcc.tar.Z
mv dcc.tar.Z /usr/local/src/backup-qmail
cd dcc-2.3.167
./configure --disable-dccm
make 
make install
cat > /etc/cron.d/dccd << 'EOF'
15 02 * * * root /var/dcc/libexec/cron-dccd
EOF
########################
# SpamAssassin
########################
cd /usr/local/src
wget http://miroir.univ-lorraine.fr/apache/spamassassin/source/Mail-SpamAssassin-3.4.2.tar.gz
tar xvzf Mail-SpamAssassin-3.4.5.tar.gz
mv Mail-SpamAssassin-3.4.2.tar.gz /usr/local/src/backup-qmail
cd Mail-SpamAssassin-3.4.2
perl Makefile.PL CONTACT_ADDRESS="http://www.e-dune.info/spam"
make
make install
mkdir -p /etc/mail/spamassassin
echo "# sa-update
11 03 */10 * * root /usr/local/bin/sa-update > /dev/null
" > /etc/cron.d/spamassassin
sed -i \
    -e "s/# rewrite_header .*/rewrite_header subject [SPAM]/" \
    -e "s/# rewrite_header .*/rewrite_header subject [SPAM]/" \
    -e "s/# report_safe .*/report_safe 1/" \
    -e "s/# use_bayes .*/use_bayes 1/" \
    -e "s/# bayes_auto_learn .*/bayes_auto_learn 1/" \
    /etc/mail/spamassassin/local.cf
cat >> /etc/mail/spamassassin/local.cf << 'EOF'
skip_rbl_checks 0
razor_config /var/spamassassin/razor/razor-agent.conf
EOF
cat > /etc/mail/spamassassin/sql.cf << 'EOF'
# User prefs
user_scores_dsn DBI:mysql:vpopmail:localhost
user_scores_sql_username vpopmail
user_scores_sql_password 85p45r28zj654Vkp
user_scores_sql_custom_query     SELECT preference, value FROM spam_prefs WHERE username = _USERNAME_ OR username = '$GLOBAL' OR username = CONCAT('%',_DOMAIN_) ORDER BY username ASC
EOF
cat >  /etc/mail/spamassassin/directory.cf << 'EOF'
#Directory
auto_whitelist_path /var/spamassassin/auto-whitelist/auto-whitelist
bayes_path /var/spamassassin/bayes/bayes
EOF
sed -i \
    -e "s/#loadplugin Mail::SpamAssassin::Plugin::DCC/loadplugin Mail::SpamAssassin::Plugin::DCC/" \
    -e "s/#loadplugin Mail::SpamAssassin::Plugin::AWL/loadplugin Mail::SpamAssassin::Plugin::AWL/" \
    -e "s/#loadplugin Mail::SpamAssassin::Plugin::TextCat/loadplugin Mail::SpamAssassin::Plugin::TextCat/" \
    /etc/mail/spamassassin/v310.pre
echo "razorhome = /etc/mail/spamassassin/.razor/" >> /var/spamassassin/razor/razor-agent.conf
mkdir -p /var/spamassassin/auto-whitelist
mkdir -p /var/spamassassin/bayes
mkdir -p /var/spamassassin/razor
cd /var
tar xvzf /tmp/oldLeto/var.spamassassin.tgz
chmod -R 777 /var/spamassassin
chown -R vpopmail.vchkpw /var/spamassassin
mkdir -p /var/qmail/svc/spamd/log
mkdir -p /var/log/spamd
chown qmaill /var/log/spamd
echo '#!/bin/sh
exec /usr/local/bin/spamd -x -q -v -m `cat /var/qmail/control/concurrencyincoming` -u vpopmail -q -s stderr 2>&1' > /var/qmail/svc/spamd/run
echo '#!/bin/sh
exec setuidgid qmaill multilog t s2000000 /var/log/spamd' > /var/qmail/svc/spamd/log/run
chmod 755 /var/qmail/svc/spamd/run
chmod 755 /var/qmail/svc/spamd/log/run
ln -s /var/qmail/svc/spamd /service/
sa-update
########################
#### Spamassin learn
########################
cat > /var/qmail/bin/learnSpam << 'EOF'
#!/bin/bash
# Spam Assassin Bayes Training

# Learn spam!
cd /var/vpopmail/domains/semhoun.net/nathanael/Maildir/.Spam.Learn/cur
/usr/local/bin/sa-learn --spam ./*
rm -f /var/vpopmail/domains/semhoun.net/nathanael/Maildir/.Spam.Learn/cur/*
cd /var/vpopmail/domains/semhoun.net/nathanael/Maildir/.Spam.Learn/new
/usr/local/bin/sa-learn --spam ./*
rm -f /var/vpopmail/domains/semhoun.net/nathanael/Maildir/.Spam.Learn/new/*

# Learn ham!
cd /var/vpopmail/domains/semhoun.net/nathanael/Maildir/.Spam.Forget/cur
/usr/local/bin/sa-learn --ham ./*
rm -f /var/vpopmail/domains/semhoun.net/nathanael/Maildir/.Spam.Forget/cur/*
cd /var/vpopmail/domains/semhoun.net/nathanael/Maildir/.Spam.Forget/new
/usr/local/bin/sa-learn --ham ./*
rm -f /var/vpopmail/domains/semhoun.net/nathanael/Maildir/.Spam.Forget/new/*

# Update the Bayes DB 
/usr/local/bin/sa-learn --sync
EOF
chmod 755 /var/qmail/bin/learnSpam 
cat >> /etc/cron.d/spamassassin << 'EOF'
# learnSpam
0 2 * * * root sudo -u vpopmail -H /var/qmail/bin/learnSpam >/dev/null
EOF
########################
# Qmail Remove https://www.fehcom.de/sqmail/man/qmail-qmaint.html
########################
cd /usr/local/src
wget http://www.linuxmagic.com/opensource/qmail/qmail-remove/qmail-remove-0.95.tar.gz
tar xvzf qmail-remove-0.95.tar.gz
mv qmail-remove-0.95.tar.gz /usr/local/src/backup-qmail
cd qmail-remove-0.95
make
make install
########################
# qmHandle  https://www.fehcom.de/sqmail/man/qmail-qmaint.html
########################
cd /usr/local/src
wget http://downloads.sourceforge.net/project/qmhandle/qmhandle-1.3/qmhandle-1.3.2/qmhandle-1.3.2.tar.gz
tar xvzf qmhandle-1.3.2.tar.gz
mv qmhandle-1.3.2.tar.gz /usr/local/src/backup-qmail
cd qmhandle-1.3.2/
cp qmHandle /usr/local/bin
########################
# mess822
########################
cd /usr/local/src
wget http://cr.yp.to/software/mess822-0.58.tar.gz mess822x
tar xvzf mess822-0.58.tar.gz
mv mess822-0.58.tar.gz /usr/local/src/backup-qmail
cd mess822-0.58
sed -i "s#extern int errno;#\#include <errno.h>#" error.h
make
make setup
###########################
# maildrop-filter
###########################
cat > /var/qmail/bin/maildrop-filter << 'EOF'
import EXT
import HOST

SHELL=\"/bin/sh\"
QMAILDIRMAKE=\"/var/qmail/bin/maildirmake\"
VPOP=\"| /var/vpopmail/bin/vdelivermail '' bounce-no-mailbox\"

VHOME=`/var/vpopmail/bin/vuserinfo -d $EXT@$HOST`
VMAILDIR=\"$VHOME/Maildir\"
SPAMDIR=\"$VHOME/Maildir/.Spam\"


if ( $VHOME eq \"\" )
{
        to \"$VPOP\"
}
else
{
        # Creation d'un dossier \"Spam\" s'il n'existe pas encore
        DUMMY=`test -d $SPAMDIR`
        if ( $RETURNCODE == 1 )
        {
            DUMMY=`$QMAILDIRMAKE $SPAMDIR`
            DUMMY=`echo INBOX.Spam >> $VMAILDIR/courierimapsubscribed`
        }

        # Distribution suivant le marquage de Spamassassin
        if (/^X-Spam-Flag: *Yes/)
        {
            exception {
                to \"$SPAMDIR/\"
            }

        }
        else
        {
            to \"$VMAILDIR/\"
        }
}
EOF
chown vpopmail.vchkpw /var/qmail/bin/maildrop-filter
chmod 600 /var/qmail/bin/maildrop-filter
############################
# qmailctl
############################
mkdir -p /var/qmail/control/
cat > /var/qmail/bin/qmailctl << 'EOF'
#!/bin/sh
PATH=/var/qmail/bin:/bin:/usr/bin:/usr/local/bin:/usr/local/sbin
export PATH

QMAILDUID=`id -u qmaild`
NOFILESGID=`id -g qmaild`
svclist="qmail-send qmail-smtpd qmail-smtpsd qmail-smtpsub spamd clamd dovecot"

case "$1" in
  start)
    echo "Starting qmail"
    for svc in $svclist ; do
        if svok /service/$svc ; then
            svc -u /service/$svc
        else
            echo $svc service not running
        fi
    done
    ;;
  stop)
    echo "Stopping qmail..."
    for svc in $svclist ; do
      echo " $svc"
      svc -d /service/$svc
    done
    ;;
  stat)
    for svc in $svclist ; do
      svstat /service/$svc
      svstat /service/$svc/log
    done
    qmail-qstat
    ;;
  doqueue|alrm|flush)
    echo "Sending ALRM signal to qmail-send."
    svc -a /service/qmail-send
    ;;
  queue)
    qmail-qstat
    qmail-qread
    ;;
  reload|hup)
    echo "Sending HUP signal to qmail-send."
    svc -h /service/qmail-send
    ;;
  pause)
    for svc in $svclist ; do
      echo "Pausing $svc"
      svc -p /service/$svc
    done
    ;;
  cont)
    for svc in $svclist ; do
      echo "Continuing $svc"
      svc -c /service/$svc
    done
    ;;
  restart)
    echo "Restarting qmail:"
    for svc in $svclist ; do
      echo "* Stopping $svc."
      svc -d /service/$svc
    done
    echo "* Sending qmail-send SIGTERM and restarting."
    svc -t /service/qmail-send
    for svc in $svclist ; do
      echo "* Restarting $svc."
      svc -u /service/$svc
    done
    ;;
  cdb)
    /usr/local/bin/tcprules /var/qmail/control/rules.smtpd.cdb /var/qmail/control/rules.smtpd.tmp < /var/qmail/control/rules.smtpd
    chmod 644 /var/qmail/control/rules.smtpd.cdb
    /usr/local/bin/tcprules /var/qmail/control/rules.smtpsd.cdb /var/qmail/control/rules.smtpsd.tmp < /var/qmail/control/rules.smtpsd
    chmod 644 /var/qmail/control/rules.smtpsd.cdb
    /usr/local/bin/tcprules /var/qmail/control/rules.smtpsub.cdb /var/qmail/control/rules.smtpsub.tmp < /var/qmail/control/rules.smtpsub
    chmod 644 /var/qmail/control/rules.smtpsub.cdb
    echo "Reloaded rules.smtp(s).cdb ."
    ;;
  help)
    cat <<HELP
    stop -- stops mail service (smtp connections refused, nothing goes out)
   start -- starts mail service (smtp connection accepted, mail can go out)
   pause -- temporarily stops mail service (connections accepted, nothing leaves)
    cont -- continues paused mail service
    stat -- displays status of mail service
     cdb -- rebuild the tcpserver cdb file for smtp
 restart -- stops and restarts smtp, sends qmail-send a TERM & restarts it
 doqueue -- sends qmail-send ALRM, scheduling queued messages for delivery
  reload -- sends qmail-send HUP, rereading locals and virtualdomains
   queue -- shows status of queue
    alrm -- same as doqueue
   flush -- same as doqueue
     hup -- same as reload
   clear -- clear the readproctitle service errors with ............
    kill -- svc -d processes in svclist, the do 'killall -KILL '
HELP
    ;;
  clear)
    echo "Clearing readproctitle service errors with ................."
    svc -o /service/clear
    ;;
  kill)
    echo "First stopping services ... "
    for svc in $svclist ; do
        if svok /service/$svc ; then
            svc -d /service/$svc
        fi
    done
    echo "Now sending processes the kill signal ... "
    killall -KILL qmail-send qmail-lspawn qmail-remote qmail-rspawn qmail-smtpd
    echo "done"
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|doqueue|flush|reload|stat|pause|cont|cdb|queue|help|clear|kill}"
    exit 1
    ;;
esac

exit 0
EOF
chmod 755 /var/qmail/bin/qmailctl 
ln -s /var/qmail/bin/qmailctl /usr/bin
########################
### qmail-queuescan
########################
cat > /var/qmail/bin/qmail-queuescan << 'EOF'
#!/bin/ksh
QMAIL="/var/qmail"
#
alias -x SCANNER='/usr/local/bin/clamdscan'
alias -x SPAMMER='/usr/local/bin/spamc'
alias -x 822FIELD='/usr/local/bin/822field'
#
SCANNERARGS="--no-summary"
SPAMMERARGS="-u $RCPTTO"
VERBOSE=0
#
## No code change necessary from here
#
typeset SPAM
integer SPAMC=0
integer SPAMTHRESHOLD=-1
integer SPAMTH
typeset SPAMDOMAINS

ID="${RANDOM}$$"
MESSAGE="${QMAIL}/tmp/msg.${ID}"
export DTLINE="spam-queue"

#
[[ ! -d ${QMAIL}/tmp ]] && exit 53
cat > ${MESSAGE} || exit 53

#
## Check Spamlevel for each domain
#
DOMAIN=$(echo ${RCPTTO} | cut -d '@' -f 2)
SPAMTHRESHOLD=$(echo "SELECT value FROM spam_prefs WHERE (username = '${RCPTTO}' OR username = '$GLOBAL' OR username = '%${DOMAIN}') AND preference = 'refuse_threshold' ORDER BY username DESC LIMIT 1;"  | mysql -N -B -u vpopmail -p85p45r28zj654Vkp -h localhost vpopmail)

[[ ${VERBOSE} -gt 0 ]] && print -u2 "User ${RCPTTO} / Domain ${DOMAIN} -- Threshold: {$SPAMTHRESHOLD}"

if [[ ${SPAMTHRESHOLD} -ge 0 ]]; then
#
## Spam recognition -- the following codes is only useful for SpamAssassins spamc version 3.x
#
        SPAM=$(SPAMMER ${SPAMMERARGS} < ${MESSAGE} > ${MESSAGE}_$$ && mv ${MESSAGE}_$$ ${MESSAGE} || exit 53)
        SPAM=$(822FIELD "X-Spam-Level" < ${MESSAGE} | head -1)
        SPAM=${SPAM# }

        if [[ "x${SPAM}" != "x" ]]; then
                [[ $(echo "${SPAM}" | grep -c "\*") -gt 0 ]] && SPAMC=$(echo "${SPAM}" | wc -c)
        else
                SPAMC=$(echo "${SPAM}" | awk -F"/" '{print $1}' | awk -F"." '{print $1}')
        fi
        [[ ${VERBOSE} -gt 0 ]] && print -u2 "Spam: $SPAM - Spamc: $SPAMC"
#
## Spam rejection
#
        if [[ ${SPAMTHRESHOLD} -gt 0 && ${SPAMC} -gt 0 && ${SPAMC} -gt ${SPAMTHRESHOLD} ]]; then
            export SPAMSCORE="${SPAMC}"
            RC=33
        fi
fi

[[ ${RC} -eq 0 ]] && ${QMAIL}/bin/qmail-queue < ${MESSAGE}

rm ${MESSAGE}
exit ${RC}
EOF
chown qmailq.sqmail /var/qmail/bin/qmail-queuescan
chmod 1755 /var/qmail/bin/qmail-queuescan
########################
### Qmail ancienne conf
########################
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
rm -f /var/qmail/ssl/*
cat > /var/qmail/ssl/env << 'EOF'
SSL_USER="vpopmail"
SSL_GROUP="vchkpw"
SSL_CHROOT="/var/qmail/ssl"
CERTFILE="/var/qmail/ssl/smtp.crt"
KEYFILE="/var/qmail/ssl/smtp.key"
DHFILE="/var/qmail/ssl/dhparam"
CIPHERS="TLSv1+HIGH:!SSLv2:!MD5" 
SSL_UID=`id -u $SSL_USER`
if [ $? -ne 0 ] ; then echo "No such user '$SSL_USER'" >&2 ; exit; fi
SSL_GID=`id -g $SSL_USER`
if [ $? -ne 0 ] ; then echo "No such group '$SSL_GROUP'" >&2 ; exit; fi
export SSL_UID SSL_GID SSL_CHROOT CERTFILE KEYFILE DHFILE CIPHERS
EOF
openssl dhparam -out /var/qmail/ssl/dhparam 2048
cat /opt/certs/smtp.e-dune.info/key.pem > /var/qmail/ssl/smtp.key
cat /opt/certs/smtp.e-dune.info/fullchain.pem > /var/qmail/ssl/smtp.crt
chown -R qmaill.sqmail /var/qmail/ssl
cat /opt/certs/imap.e-dune.info/key.pem > /var/qmail/ssl/imap.key
cat /opt/certs/imap.e-dune.info/fullchain.pem > /var/qmail/ssl/imap.crt
cat /opt/certs/pop.e-dune.info/key.pem > /var/qmail/ssl/pop.key
cat /opt/certs/pop.e-dune.info/fullchain.pem > /var/qmail/ssl/pop.crt
chown -R vpopmail.sqmail /var/qmail/ssl/imap* /var/qmail/ssl/pop*
sed -i "s/$OLDIP/$NEWIP/g" /var/qmail/control/rules.smtpd
sed -i "s#$OLDIP#$NEWIP#g" /var/qmail/control/badhelo
qmailctl cdb
########################
# DKIM
########################
wget -O /usr/local/src/backup-qmail/dkimsign.pl http://www.memoryhole.net/qmail/dkimsign.pl 
wget -O /usr/local/src/backup-qmail/qmail-remote.sh http://www.memoryhole.net/qmail/qmail-remote.sh
chmod 755 /usr/local/src/backup-qmail/dkimsign.pl /usr/local/src/backup-qmail/qmail-remote.sh
wget -O /usr/local/src/backup-qmail/libdomainkeys-0.69.tar.gz https://downloads.sourceforge.net/project/domainkeys/libdomainkeys/0.69/libdomainkeys-0.69.tar.gz
wget -O /usr/local/src/backup-qmail/libdomainkeys-openssl-1.1.patch https://notes.sagredo.eu/files/qmail/patches/libdomainkeys/libdomainkeys-openssl-1.1.patch
wget -O /usr/local/src/backup-qmail/libdomainkeys-0.69.diff https://notes.sagredo.eu/files/qmail/patches/libdomainkeys/libdomainkeys-0.69.diff
sed -i 's/selector=default/selector=leto/' /usr/local/src/backup-qmail/qmail-remote.sh
cd /usr/local/src/
tar xvzf /usr/local/src/backup-qmail/libdomainkeys-0.69.tar.gz
cd libdomainkeys-0.69
patch -p1 < /usr/local/src/backup-qmail/libdomainkeys-openssl-1.1.patch
patch < /usr/local/src/backup-qmail/libdomainkeys-0.69.diff
make
cp dktest /usr/local/bin/
cp /usr/local/src/backup-qmail/dkimsign.pl /usr/local/bin/
mv /var/qmail/bin/qmail-remote /var/qmail/bin/qmail-remote.orig
cp /usr/local/src/backup-qmail/qmail-remote.sh /var/qmail/bin/qmail-remote
cat > /var/qmail/svc/qmail-send/run << 'EOF'
#!/bin/sh
exec env - \
    PATH="/var/qmail/bin:$PATH" \
    DKREMOTE="/var/qmail/bin/qmail-remote.orig" \
    DKSIGN="/var/qmail/control/domainkeys/%" \
    qmail-start ./Maildir/
EOF
mkdir -p /var/qmail/control/domainkeys

########################
# Clamscan cron
########################
# to check do: echo 'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*' > /tmp/clam-test
cat > /etc/cron.daily/clamscan << "EOF"
#!/bin/bash
CV_MAILTO="sup@e-dune.info"
CV_LOGFILE="/var/log/clamav-cron.log"

echo -e ClamAV scan report - $(date) '\n' > $CV_LOGFILE
echo -e Scanned: $CV_TARGET on $HOSTNAME'\n' >> $CV_LOGFILE

/usr/bin/nice -n 0 /usr/local/bin/clamscan --infected --log=$CV_LOGFILE --quiet --recursive /var/www
CLAMSCAN=$?

if [ "$CLAMSCAN" -eq "1" ]; then
    (
        echo "Subject: ClamAV scan report"
        echo "To: $CV_MAILTO"
        echo ""
        cat $CV_LOGFILE
    ) | /usr/sbin/sendmail $CV_MAILTO
fi
EOF
chmod 755 /etc/cron.daily/clamscan

########################
#### Qmail compil locale
########################
cd /usr/local/src
rm -rf qmailadmin-1.2.16
tar xvzf /usr/local/src/backup-qmail/qmailadmin-1.2.16.tar.gz 
cd qmailadmin-1.2.16
./configure --enable-cgibindir="/var/www/e-dune/mail/admin/cgi-bin/" --enable-htmldir="/var/www/e-dune/mail/admin" --enable-imagedir="/var/www/e-dune/mail/admin/images/qmailadmin" --enable-imageurl="/admin/images/qmailadmin" --enable-htmllibdir="/admin" --disable-ezmlm-mysql --enable-modify-spam --enable-spam-command="|/var/qmail/bin/preline /usr/bin/maildrop /var/qmail/bin/maildrop-filter" --disable-catchall  --disable-user-index
sed -i 's#printf("postmaster");#printf("");#' template.c
sed -i 's#DOMAIN_ADMIN#USER_ADMIN#g' auth.c
sed -i "s#Compte Ma&icirc;tre#Nom d'utilisateur#g" lang/fr
makeuse	
make install








# TO RUN:
/command/svscanboot &
