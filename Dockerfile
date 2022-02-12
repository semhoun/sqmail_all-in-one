# Use patch and sources from:
#  - https://www.fehcom.de/sqmail/sqmail.html
#  - https://notes.sagredo.eu/
#  - https://notes.sagredo.eu/files/qmail/patches/
FROM debian:buster-slim

ENV DEBIAN_FRONTEND noninteractive
ENV TERM=linux

ARG SQMAIL_TAG
ARG FEHQLIBS_TAG
ARG DAEMONTOOLS_TAG
ARG UCSPISSL_TAG
ARG UCSPITCP6_TAG
ARG DOVECOT_TAG
ARG CLAMAV_TAG
ARG SPAMASSASSIN_TAG
ARG FCRON_TAG

########################  
# Base install
########################
COPY patches /qmail-patches
WORKDIR "/qmail-src"

RUN echo "deb http://deb.debian.org/debian buster-backports main contrib non-free" > /etc/apt/sources.list.d/backports.list \
  && apt-get update \
  && apt-get -y install build-essential equivs bash dnsutils unzip git curl wget sudo ksh vim \
  && apt-get -t buster-backports -y install cmake \
## Add docker group for logs
  && groupadd -g 998 docker \
## Add MTA Local (equivs is needed)
  && equivs-build /qmail-patches/mail-transport-agent.ctl \
  && dpkg -i mta-local*.deb \
  && rm -f /qmail-src/* \
# Fixes for slim install
  && mkdir -p /usr/share/man/man1 /usr/share/man/man5 /usr/share/man/man7 /usr/share/man/man8 \
  && touch /usr/share/man/man1/maildirmake.1.gz \
  && touch /usr/share/man/man8/deliverquota.8.gz \
  && touch /usr/share/man/man1/lockmail.1.gz \
  && touch /usr/share/man/man5/maildir.maildrop.5.gz \
  && touch /usr/share/man/man1/lockmail.maildrop.1.gz \
  && touch /usr/share/man/man7/maildirquota.maildrop.7.gz

########################  
# Encoding fix
########################
RUN apt-get -y install locales \
  && sed \
      -e 's/# fr_FR.UTF-8 UTF-8/fr_FR.UTF-8 UTF-8/' \
      -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' \
      -i /etc/locale.gen \
  && /usr/sbin/locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

########################  
# Additionnals packages
########################
RUN apt-get -y install bsd-mailx \
    libperl-dev libmariadb-dev libmariadb-dev-compat csh maildrop bzip2 razor pyzor ksh libnet-dns-perl libio-socket-inet6-perl libdigest-sha-perl libnetaddr-ip-perl libmail-spf-perl libgeo-ip-perl libnet-cidr-lite-perl libmail-dkim-perl libnet-patricia-perl libencode-detect-perl libperl-dev libssl-dev libcurl4-gnutls-dev \
    lighttpd \
    check libbz2-dev libxml2-dev libpcre2-dev libjson-c-dev libncurses-dev pkg-config \
    libhtml-parser-perl re2c libdigest-sha-perl libdbi-perl libgeoip2-perl libio-string-perl libbsd-resource-perl libmilter-dev \
  && cpan -i IP::Country::DB_File Digest::SHA1 \
  && rm -rf /root/.local

########################
# SQMail
########################
RUN mkdir -p /package \
    && chmod 1755 /package \
## fehQlibs
    && cd /qmail-src \
    && wget https://www.fehcom.de/ipnet/fehQlibs/fehQlibs-${FEHQLIBS_TAG}.tgz \
    && cd /usr/local \
    && tar xvzf /qmail-src/fehQlibs-${FEHQLIBS_TAG}.tgz \
    && mv fehQlibs-${FEHQLIBS_TAG} qlibs  \
    && cd qlibs \
    && make \
## Daemontools
    && cd /qmail-src \
    && wget https://cr.yp.to/daemontools/daemontools-${DAEMONTOOLS_TAG}.tar.gz \
    && cd /package \
    && tar xvzf /qmail-src/daemontools-${DAEMONTOOLS_TAG}.tar.gz \
    && cd admin \
    && patch -p0 < /qmail-patches/daemontools-0.76.errno.patch \
    && patch -p0 < /qmail-patches/daemontools-0.76-localtime.patch \
    && cd daemontools-${DAEMONTOOLS_TAG} \
    && package/install \
## ucspi-ssl    
    && cd /qmail-src \
    && wget https://www.fehcom.de/ipnet/ucspi-ssl/ucspi-ssl-${UCSPISSL_TAG}.tgz \
    && cd /package \
    && tar xvzf /qmail-src/ucspi-ssl-${UCSPISSL_TAG}.tgz \
    && cd host/superscript.com/net/ucspi-ssl-${UCSPISSL_TAG} \
    && package/install \
## ucspi-tcp6
    && cd /qmail-src \
    && wget https://www.fehcom.de/ipnet/ucspi-tcp6/ucspi-tcp6-${UCSPITCP6_TAG}.tgz \
    && cd /package \
    && tar xvzf /qmail-src/ucspi-tcp6-${UCSPITCP6_TAG}.tgz \
    && cd net/ucspi-tcp6/ucspi-tcp6-${UCSPITCP6_TAG} \
    && package/install \
## sqmail
    && cd /qmail-src \
    && wget https://www.fehcom.de/sqmail/sqmail-${SQMAIL_TAG}.tgz \
    && cd /package \
    && tar xvzf /qmail-src/sqmail-${SQMAIL_TAG}.tgz \
    && cd mail/sqmail/sqmail-${SQMAIL_TAG} \
    && package/install; echo "Otherwise return 1" \
## cleaning
    && rm -rf /qmail-src/* \
    && rm -rf /var/qmail/svc /service/*
# SSL Config
COPY conf/ssl_env /var/qmail/ssl_env
    
########################
# VPopMail
########################
# Libev for vusaged
RUN wget  http://dist.schmorp.de/libev/libev-4.33.tar.gz \
    && tar xzvf libev-4.33.tar.gz \
    && cd libev-4.33 \
    && ./configure \
    && make \
    && make install \
    && ldconfig \
# vpopmail
    && cd /qmail-src \
    && mkdir -p /var/vpopmail \
    && groupadd -g 89 vchkpw \
    && useradd -g vchkpw -u 89 -s /usr/sbin/nologin -d /var/vpopmail vpopmail \
    && chown -R vpopmail.vchkpw /var/vpopmail \
    && wget http://downloads.sourceforge.net/project/vpopmail/vpopmail-stable/5.4.33/vpopmail-5.4.33.tar.gz \
    && tar xzf vpopmail-5.4.33.tar.gz \
    && cd vpopmail-5.4.33 \
    && patch -p1 < /qmail-patches/roberto_vpopmail-5.4.33.patch \
    && autoreconf -f -i \
    && ./configure \
        --enable-qmaildir=/var/qmail/ \
        --enable-qmail-newu=/var/qmail/bin/qmail-newu \
        --enable-qmail-inject=/var/qmail/bin/qmail-inject \
        --enable-qmail-newmrh=/var/qmail/bin/qmail-newmrh \
        --enable-tcpserver-file=/var/qmail/control/relays.cdb \
        --disable-roaming-users \
        --enable-auth-module=mysql \
        --enable-incdir=/usr/include/mariadb \
        --enable-libdir=/usr/lib \
        --enable-logging=n \
        --disable-clear-passwd \
        --enable-auth-logging \
        --enable-sql-logging=e \
        --disable-passwd \
        --enable-qmail-ext \
        --enable-mysql-limits \
        --enable-sql-aliasdomains \
        --enable-defaultdelivery \
        --enable-valias \
    && make install-strip \
# vusaged
    && cd vusaged \
    && ./configure \
        --with-vpopmail=/var/vpopmail \
    && make \
    && cp -f vusaged /var/vpopmail/bin \
    && cp -f etc/vusaged.conf /var/vpopmail/etc \
# cleaning
    && rm -rf /qmail-src/*
    
########################
# Dovecot
########################
RUN groupadd -g 2110 dovecot \
    && useradd -g dovecot -u 7798 -s /usr/sbin/nologin -d /var/run dovenull \
    && useradd -g dovecot -u 7799 -s /usr/sbin/nologin -d /var/run dovecot \
    && wget https://dovecot.org/releases/2.3/dovecot-${DOVECOT_TAG}.tar.gz \
    && tar xvzf dovecot-${DOVECOT_TAG}.tar.gz \
    && cd dovecot-${DOVECOT_TAG} \
    && ./configure \
        --prefix=/usr \
        --sysconfdir=/etc \
        --localstatedir=/var \
        --with-sql \
        --with-mysql \
        --with-docs \
        --with-ssl \
        --without-shadow \
        --without-pam \
        --without-ldap \
        --without-pgsql \
        --without-sqlite \
    && make \
    && make install \
    && mkdir -p /etc/dovecot/ /var/run/dovecot \
# cleaning
    && rm -rf /qmail-src/*
# Config files
COPY conf/dovecot-etc/ /etc/

########################
# Autorespond
########################
RUN wget http://qmail.ixip.net/download/autorespond-2.0.5.tar.gz \
  && tar xvzf autorespond-2.0.5.tar.gz \
  && cd autorespond-2.0.5 \
  && make \
  && cp autorespond /usr/local/bin \
  && chown root.root /usr/local/bin/autorespond \
# cleaning
  && rm -rf /qmail-src/*

########################
# ezmlm-idx
########################
RUN wget https://qmailrocks.thibs.com/downloads/ezmlm-idx-7.2.2.tar.gz \
  && tar xvzf ezmlm-idx-7.2.2.tar.gz \
  && cd ezmlm-idx-7.2.2 \
  && make && make man && make install \
# cleaning
  && rm -rf /qmail-src/*
  
########################
# QmailAdmin
########################
RUN wget http://downloads.sourceforge.net/project/qmailadmin/qmailadmin-devel/qmailadmin-1.2.16.tar.gz \
  && tar xvzf qmailadmin-1.2.16.tar.gz\
  && cd qmailadmin-1.2.16 \
	&& patch -p1 < /qmail-patches/roberto-qmailadmin-1.2.16.patch \
	&& cp /qmail-patches/qmailadmin/* images/ \
  && ./configure \
		--enable-cgibindir=/var/www/cgi-bin \
		--enable-htmldir=/var/www/html \
		--enable-imagedir=/var/www/html/images/qmailadmin \
		--disable-ezmlm-mysql \
		--enable-modify-quota \
		--enable-domain-autofill \
		--enable-modify-spam \
		--enable-spam-command="|/var/qmail/bin/preline /usr/bin/maildrop /var/qmail/bin/maildrop-filter" \
		--enable-help \
		--enable-vpopuser=vpopmail \
		--enable-vpopgroup=vchkpw \
	 --enable-domain-autofill \
  && make \
  && make install \
# cleaning
  && rm -rf /qmail-src/*

########################
# vqadmin
########################
RUN wget https://qmailrocks.thibs.com/downloads/vqadmin-2.3.7.tar.gz \
  && tar xvzf vqadmin-2.3.7.tar.gz \
  && cd vqadmin-2.3.7 \
  && patch -p0 < /qmail-patches/vqadmin-2.3.7.patch \
  && ./configure --enable-cgibindir=/var/www/cgi-bin --build=i386 \
  && make \
  && make install \
  && mkdir -p /var/www/html/images/vqadmin \
  && cp html/vqadmin.css /var/www/html/images/vqadmin \
# cleaning
  && rm -rf /qmail-src/*
  
########################
# clamav
########################
RUN groupadd -g 5010 clamav \
  && useradd -g clamav -u 5010 -s /usr/sbin/nologin -c "Clam AntiVirus" -d /var/empty clamav \
  && echo "clamav: ${CLAMAV_TAG}" \
  && wget https://www.clamav.net/downloads/production/clamav-${CLAMAV_TAG}.tar.gz \
  && tar xvzf clamav-${CLAMAV_TAG}.tar.gz \
  && cd clamav-${CLAMAV_TAG} \
  && cmake . \
    -D CMAKE_BUILD_TYPE=Release \
    -D CMAKE_INSTALL_PREFIX=/usr \
    -D CMAKE_INSTALL_LIBDIR=/usr/lib \
    -D APP_CONFIG_DIRECTORY=/etc/clamav \
    -D DATABASE_DIRECTORY=/var/lib/clamav \
    -D ENABLE_JSON_SHARED=OFF \
    -D ENABLE_SHARED_LIB=OFF \
    -D ENABLE_STATIC_LIB=ON \
  && cmake --build . \
  && cmake --build . --target install \
  && sed -e "s/Example/#Exemple/" \
    -e "s/#PidFile .*/PidFile \/var\/run\/freshclam.pid/" \
    -e "s/#DNSDatabaseInfo .*/DNSDatabaseInfo current.cvd.clamav.net/" \
    -e "s/#DatabaseMirror .*/DatabaseMirror database.clamav.net/" \
    /etc/clamav/freshclam.conf.sample > /etc/clamav/freshclam.conf \
  && sed -e "s/Example/#Exemple/" \
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
    /etc/clamav/clamd.conf.sample > /etc/clamav/clamd.conf \
# cleaning
  && rm -rf /qmail-src/*

########################
# DCC
########################
RUN wget https://www.dcc-servers.net/dcc/source/dcc.tar.Z \
  && tar xvzf dcc.tar.Z \
  && cd dcc-2.3.168 \
  && ./configure --disable-dccm \
  && make \
  && make install \
# cleaning
  && rm -rf /qmail-src/*

########################
# SpamAssassin
########################
RUN wget https://dlcdn.apache.org//spamassassin/source/Mail-SpamAssassin-${SPAMASSASSIN_TAG}.tar.gz \
  && tar xvzf Mail-SpamAssassin-${SPAMASSASSIN_TAG}.tar.gz \
  && cd Mail-SpamAssassin-${SPAMASSASSIN_TAG} \
  && perl Makefile.PL CONTACT_ADDRESS="http://www.e-dune.info/spam" \
  && make \
  && make install \
  && mv /etc/mail/spamassassin/local.cf /etc/mail/spamassassin/local.cf.dist \
  && sed -i \
      -e "s/#loadplugin Mail::SpamAssassin::Plugin::DCC/loadplugin Mail::SpamAssassin::Plugin::DCC/" \
      -e "s/#loadplugin Mail::SpamAssassin::Plugin::AWL/loadplugin Mail::SpamAssassin::Plugin::AWL/" \
      -e "s/#loadplugin Mail::SpamAssassin::Plugin::TextCat/loadplugin Mail::SpamAssassin::Plugin::TextCat/" \
      /etc/mail/spamassassin/v310.pre \
# cleaning
  && rm -rf /qmail-src/*
# Config files
COPY conf/spamassin-local.cf /etc/mail/spamassassin/local.conf
COPY conf/spamassin-directory.cf /etc/mail/spamassassin/directory.cf 
# Binary
COPY bin/learnSpam.sh /var/qmail/bin/learnSpam

########################
# DKIM
########################
RUN wget http://www.memoryhole.net/qmail/dkimsign.pl \
  && wget http://www.memoryhole.net/qmail/qmail-remote.sh \
  && wget https://downloads.sourceforge.net/project/domainkeys/libdomainkeys/0.69/libdomainkeys-0.69.tar.gz \
  && wget https://notes.sagredo.eu/files/qmail/patches/libdomainkeys/libdomainkeys-openssl-1.1.patch \
  && wget https://notes.sagredo.eu/files/qmail/patches/libdomainkeys/libdomainkeys-0.69.diff \
  && tar xvzf libdomainkeys-0.69.tar.gz \
  && cd libdomainkeys-0.69 \
  && patch -p1 < /qmail-src/libdomainkeys-openssl-1.1.patch \
  && patch < /qmail-src/libdomainkeys-0.69.diff \
  && make \
  && cp dktest /usr/local/bin/ \
  && install /qmail-src/dkimsign.pl /usr/local/bin/ \
  && mv /var/qmail/bin/qmail-remote /var/qmail/bin/qmail-remote.orig \
  && install -T /qmail-src/qmail-remote.sh /var/qmail/bin/qmail-remote \
# cleaning
  && rm -rf /qmail-src/*

########################
# Qmail Remove https://www.fehcom.de/sqmail/man/qmail-qmaint.html
########################
RUN wget http://www.linuxmagic.com/opensource/qmail/qmail-remove/qmail-remove-0.95.tar.gz \
  && tar xvzf qmail-remove-0.95.tar.gz \
  && cd qmail-remove-0.95 \
  && make \
  && make install \
# cleaning
  && rm -rf /qmail-src/*
  
########################
# qmHandle  https://www.fehcom.de/sqmail/man/qmail-qmaint.html
########################
RUN wget http://downloads.sourceforge.net/project/qmhandle/qmhandle-1.3/qmhandle-1.3.2/qmhandle-1.3.2.tar.gz \
  && tar xvzf qmhandle-1.3.2.tar.gz \
  && cd qmhandle-1.3.2 \
  && install qmHandle /usr/local/bin\
# cleaning
  && rm -rf /qmail-src/*
  
########################
# mess822
########################
RUN wget http://cr.yp.to/software/mess822-0.58.tar.gz \
  && tar xvzf mess822-0.58.tar.gz \
  && cd mess822-0.58 \
  && sed -i "s#extern int errno;#\#include <errno.h>#" error.h \
  && make \
  && make setup \
# cleaning
  && rm -rf /qmail-src/*
  
###########################
# lighttpd
###########################
COPY conf/lighttpd.conf /etc/lighttpd/lighttpd.conf

###########################
# FCRON
###########################
#http://fcron.free.fr/download.php
RUN wget http://fcron.free.fr/archives/fcron-${FCRON_TAG}.src.tar.gz \
  && tar xvzf fcron-${FCRON_TAG}.src.tar.gz \
  && cd fcron-${FCRON_TAG} \
  && ./configure \
    --prefix=/usr \
    --sysconfdir=/etc \
    --localstatedir=/var \
    --with-sysfcrontab=no \
    --with-answer-all \
		--with-sendmail=/var/qmail/bin/sendmail \
  && make \
  && make install \
# cleaning
  && rm -rf /qmail-src/*
COPY conf/fcron-root /var/spool/fcron/root

###########################
# swaks (for test)
###########################
RUN wget http://www.jetmore.org/john/code/swaks/latest/swaks \
  && install swaks /usr/local/bin \
# cleaning
  && rm -rf /qmail-src/*  
  
###########################
# Binaries
###########################
COPY bin/maildrop-filter /var/qmail/bin/maildrop-filter
COPY bin/qmailctl /var/qmail/bin/qmailctl
COPY bin/qmail-queuescan /var/qmail/bin/qmail-queuescan
RUN chown vpopmail.vchkpw /var/qmail/bin/maildrop-filter \
  && chmod 600 /var/qmail/bin/maildrop-filter \
  && install /var/qmail/bin/qmailctl /usr/local/bin \
  && chown qmailq.sqmail /var/qmail/bin/qmail-queuescan \
  && chmod 1755 /var/qmail/bin/qmail-queuescan

###########################
# SVC Binaries
###########################
COPY bin/run/qmail-smtpd /service/qmail-smtpd/run
COPY bin/log/qmail /service/qmail-smtpd/log/run
COPY bin/run/qmail-smtpsd /service/qmail-smtpsd/run
COPY bin/log/qmail /service/qmail-smtpsd/log/run
COPY bin/run/qmail-smtpsub /service/qmail-smtpsub/run
COPY bin/log/qmail /service/qmail-smtpsub/log/run
COPY bin/run/qmail-send /service/qmail-send/run
COPY bin/log/qmail /service/qmail-send/log/run
COPY bin/run/dovecot /service/dovecot/run
COPY bin/log/dovecot /service/dovecot/log/run
COPY bin/run/clamd /service/clamd/run
COPY bin/log/clamd /service/clamd/log/run
COPY bin/run/spamd /service/spamd/run
COPY bin/log/spamd /service/spamd/log/run
COPY bin/run/lighttpd /service/lighttpd/run
COPY bin/log/lighttpd /service/lighttpd/log/run
COPY bin/run/fcron /service/fcron/run
COPY bin/log/fcron /service/fcron/log/run
    
###########################
# Templates
###########################
RUN mkdir /var/tpl \
  && mv /var/qmail/control/ /var/tpl/qmail
COPY message/quotawarn.msg /var/tpl/vpopmail/quotawarn.msg
COPY conf/dovecot-sql.conf.ext /var/tpl/qmail

###########################
# Volumes
###########################
RUN mkdir -p \
  /var/vpopmail/domains/ \
  /ssl \
  /var/vpopmail/etc \
  /var/qmail/control \
  /log \
  /var/spamassassin \
  /var/qmail/tmp

VOLUME [ \
  "/var/vpopmail/domains",\
  "/ssl",\
  "/var/vpopmail/etc",\
  "/var/qmail/control",\
  "/log",\
  "/var/spamassassin",\
  "/var/qmail/tmp", \
  "/var/qmail/users" \
]

###########################
# Final cleaning
###########################
WORKDIR "/log"
RUN rm -rf /qmail-patches /qmail-src \
    && rm -rf /service/qmail-pop3* \
    && rm -rf /var/log/qmail-pop3* \
    && cp /var/qmail/bin/sendmail /usr/sbin/sendmail \
    && rm -f /service/*/down

###########################
# Docker final parms
###########################
EXPOSE 25 465 587
EXPOSE 110 995
EXPOSE 143 993
EXPOSE 80

COPY bin/docker-entrypoint.sh /bin/
ENTRYPOINT ["/bin/docker-entrypoint.sh"]
CMD ["/command/svscan", "/service", "2>&1"]
