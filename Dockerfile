FROM debian:bullseye-slim

ENV DEBIAN_FRONTEND noninteractive
ENV TERM=linux

ARG SQMAIL_TAG
ARG FEHQLIBS_TAG
ARG EXECLINE_TAG
ARG SKALIB_TAG
ARG S6_TAG
ARG UCSPISSL_TAG
ARG UCSPITCP6_TAG
ARG DOVECOT_TAG
ARG CLAMAV_TAG
ARG SPAMASSASSIN_TAG
ARG FCRON_TAG
ARG ROUNDCUBEMAIL_TAG
ARG VPOPMAIL_TAG
ARG ACMESH_TAG

########################  
# Base install
########################
COPY opt /opt/
WORKDIR "/opt/src"

RUN mkdir -p /opt/src \
  && chmod 755 /opt/bin/* \
  && apt-get update \
  && apt-get -y install build-essential equivs bash dnsutils unzip git curl wget sudo ksh vim whiptail cmake apg \
## Add docker group for logs
  && groupadd -g 998 docker \
## Add MTA Local (equivs is needed)
  && equivs-build /opt/patches/mail-transport-agent.ctl \
  && dpkg -i mta-local*.deb \
  && rm -f /opt/src/* \
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
    libperl-dev libmariadb-dev libmariadb-dev-compat csh maildrop bzip2 razor pyzor ksh libclass-dbi-mysql-perl libnet-dns-perl libio-socket-inet6-perl libdigest-sha-perl libnetaddr-ip-perl libmail-spf-perl libgeo-ip-perl libnet-cidr-lite-perl libmail-dkim-perl libnet-patricia-perl libencode-detect-perl libperl-dev libssl-dev libcurl4-gnutls-dev \
    check libbz2-dev libxml2-dev libpcre2-dev libjson-c-dev libncurses-dev pkg-config \
    libhtml-parser-perl re2c libdigest-sha-perl libdbi-perl libgeoip2-perl libio-string-perl libbsd-resource-perl libmilter-dev \
    mariadb-client \
    socat \
    lighttpd php7.4-fpm \
# For roundcube
  && apt-get install -y php7.4-zip php7.4-pspell php7.4-mysql php7.4-gd php7.4-imap php7.4-xml php7.4-mbstring php7.4-intl php-imagick aspell-fr php7.4-intl php7.4-curl \
  && cpan -i IP::Country::DB_File Digest::SHA1 \
  && rm -rf /root/.local

########################
# Skarnet S6
########################
RUN wget -O skalibs-${SKALIB_TAG}.tar.gz https://github.com/skarnet/skalibs/archive/refs/tags/v${SKALIB_TAG}.tar.gz \
  && tar xzf skalibs-${SKALIB_TAG}.tar.gz \
  && cd skalibs-${SKALIB_TAG} \
  && ./configure \
  && make \
  && make install \
  && cd /opt/src/ \
  && wget -O execline-${EXECLINE_TAG}.tar.gz https://github.com/skarnet/execline/archive/refs/tags/v${EXECLINE_TAG}.tar.gz \
  && tar xzf execline-${EXECLINE_TAG}.tar.gz \
  && cd execline-${EXECLINE_TAG} \
  && ./configure \
  && make \
  && make install \
  && cd /opt/src/ \
  && wget -O s6-${S6_TAG}.tar.gz https://github.com/skarnet/s6/archive/refs/tags/v${S6_TAG}.tar.gz \
  && tar xzf s6-${S6_TAG}.tar.gz \
  && cd s6-${S6_TAG} \
  && ./configure \
  && make \
  && make install \
## cleaning
  && rm -rf /opt/src/* \
  && rm -rf /var/qmail/svc /service/*

########################
# SQMail
########################
RUN mkdir -p /package \
	&& chmod 1755 /package \
## fehQlibs
	&& cd /opt/src \
	&& wget https://www.fehcom.de/ipnet/fehQlibs/fehQlibs-${FEHQLIBS_TAG}.tgz \
	&& cd /usr/local \
	&& tar xzf /opt/src/fehQlibs-${FEHQLIBS_TAG}.tgz \
	&& mv fehQlibs-${FEHQLIBS_TAG} qlibs  \
	&& cd qlibs \
	&& make \
## ucspi-ssl    
	&& cd /opt/src \
	&& wget https://www.fehcom.de/ipnet/ucspi-ssl/ucspi-ssl-${UCSPISSL_TAG}.tgz \
	&& cd /package \
	&& tar xzf /opt/src/ucspi-ssl-${UCSPISSL_TAG}.tgz \
	&& cd host/superscript.com/net/ucspi-ssl-${UCSPISSL_TAG} \
	&& package/install \
## ucspi-tcp6
	&& cd /opt/src \
	&& wget https://www.fehcom.de/ipnet/ucspi-tcp6/ucspi-tcp6-${UCSPITCP6_TAG}.tgz \
	&& cd /package \
	&& tar xzf /opt/src/ucspi-tcp6-${UCSPITCP6_TAG}.tgz \
	&& cd net/ucspi-tcp6/ucspi-tcp6-${UCSPITCP6_TAG} \
	&& package/install \
## sqmail
	&& cd /opt/src \
	&& wget https://www.fehcom.de/sqmail/sqmail-${SQMAIL_TAG}.tgz \
	&& cd /package \
	&& tar xzf /opt/src/sqmail-${SQMAIL_TAG}.tgz \
	&& cd mail/sqmail/sqmail-${SQMAIL_TAG} \
	&& sed -i '/service/d' package/install \
	&& sed -i '/run/d' package/install \
	&& package/install #; echo "Otherwise return 1" \
## cleaning
	&& rm -rf /opt/src/* \
	&& rm -rf /var/qmail/svc /service/*
# SSL Config
COPY conf/ssl_env /var/qmail/ssl_env
    
########################
# VPopMail
########################
# Libev for vusaged
RUN wget http://dist.schmorp.de/libev/libev-4.33.tar.gz \
	&& tar xzvf libev-4.33.tar.gz \
	&& cd libev-4.33 \
	&& ./configure \
	&& make \
	&& make install \
	&& ldconfig \
# vpopmail
	&& cd /opt/src \
	&& mkdir -p /var/vpopmail \
	&& groupadd -g 89 vchkpw \
	&& useradd -g vchkpw -u 89 -s /usr/sbin/nologin -d /var/vpopmail vpopmail \
	&& chown -R vpopmail.vchkpw /var/vpopmail \
	&& wget -O vpopmail-${VPOPMAIL_TAG}.tar.gz https://github.com/semhoun/vpopmail/archive/refs/tags/${VPOPMAIL_TAG}.tar.gz  \
	&& mkdir vpopmail \
	&& cd vpopmail \
	&& tar xzf ../vpopmail-${VPOPMAIL_TAG}.tar.gz --strip 1 \
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
		--enable-sqmail-ext \
		--enable-mysql-limits \
		--enable-sql-aliasdomains \
		--enable-defaultdelivery \
		--enable-valias \
		--enable-md5-passwords \
		--enable-min-pwd-length=6 \
	&& make \
	&& make install \
# vusaged
	&& cd vusaged \
	&& LIBS=`head -1 /var/vpopmail/etc/lib_deps` \
		./configure \
		--with-vpopmail=/var/vpopmail \
	&& make \
	&& cp -f vusaged /var/vpopmail/bin \
	&& cp -f etc/vusaged.conf /var/vpopmail/etc \
# cleaning
	&& rm -rf /opt/src/*
	
########################
# Dovecot
########################
	RUN groupadd -g 2110 dovecot \
	&& useradd -g dovecot -u 7798 -s /usr/sbin/nologin -d /var/run dovenull \
	&& useradd -g dovecot -u 7799 -s /usr/sbin/nologin -d /var/run dovecot \
	&& wget https://dovecot.org/releases/2.3/dovecot-${DOVECOT_TAG}.tar.gz \
	&& tar xzf dovecot-${DOVECOT_TAG}.tar.gz \
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
		&& rm -rf /opt/src/*
	# Config files
	COPY conf/dovecot-etc/ /etc/

########################
# Autorespond
########################
RUN wget http://qmail.ixip.net/download/autorespond-2.0.5.tar.gz \
  && tar xzf autorespond-2.0.5.tar.gz \
  && cd autorespond-2.0.5 \
  && make \
  && cp autorespond /usr/local/bin \
  && chown root.root /usr/local/bin/autorespond \
# cleaning
  && rm -rf /opt/src/*

########################
# ezmlm-idx
########################
RUN wget https://qmailrocks.thibs.com/downloads/ezmlm-idx-7.2.2.tar.gz \
  && tar xzf ezmlm-idx-7.2.2.tar.gz \
  && cd ezmlm-idx-7.2.2 \
  && make && make man && make install \
# cleaning
  && rm -rf /opt/src/*
  
########################
# QmailAdmin
########################
RUN wget http://downloads.sourceforge.net/project/qmailadmin/qmailadmin-devel/qmailadmin-1.2.16.tar.gz \
  && tar xzf qmailadmin-1.2.16.tar.gz\
  && cd qmailadmin-1.2.16 \
  && patch -p1 < /opt/patches/roberto-qmailadmin-1.2.16.patch \
  && cp /opt/patches/qmailadmin/* images/ \
  && ./configure \
    --enable-cgibindir=/var/www/admin/cgi \
    --enable-htmldir=/var/www/admin/html/ \
    --enable-imagedir=/var/www/admin/html/images/qmailadmin \
    --enable-cgipath=/cgi/qmailadmin \
    --enable-imageurl=/images/qmailadmin \
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
  && cp images/* /var/www/admin/html/images/qmailadmin/ \
# cleaning
  && rm -rf /opt/src/*

########################
# vqadmin
########################
RUN wget https://qmailrocks.thibs.com/downloads/vqadmin-2.3.7.tar.gz \
  && tar xzf vqadmin-2.3.7.tar.gz \
  && cd vqadmin-2.3.7 \
  && patch -p0 < /opt/patches/vqadmin-2.3.7.patch \
  && sed 's#/cgi-bin/#/cgi/#g' -i user.c cedit.c domain.c html/* \
  && ./configure --enable-cgibindir=/var/www/admin/cgi --build=i386 \
  && make \
  && make install \
  && mkdir -p /var/www/admin/html/images/vqadmin \
  && cp html/vqadmin.css /var/www/admin/html/images/vqadmin \
# cleaning
  && rm -rf /opt/src/*
  
########################
# clamav
########################
RUN groupadd -g 5010 clamav \
  && useradd -g clamav -u 5010 -s /usr/sbin/nologin -c "Clam AntiVirus" -d /var/empty clamav \
  && curl https://sh.rustup.rs -sSf | sh -s -- -y \
  && wget https://www.clamav.net/downloads/production/clamav-${CLAMAV_TAG}.tar.gz \
  && tar xzf clamav-${CLAMAV_TAG}.tar.gz \
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
    -e "s/#ConcurrentDatabaseReload no/ConcurrentDatabaseReload no/" \
    /etc/clamav/clamd.conf.sample > /etc/clamav/clamd.conf \
# cleaning
  && rm -rf /opt/src/*

########################
# DCC
########################
RUN wget https://www.dcc-servers.net/dcc/source/dcc.tar.Z \
  && tar xzf dcc.tar.Z \
  && cd dcc-2.3.168 \
  && ./configure --disable-dccm \
  && make \
  && make install \
# cleaning
  && rm -rf /opt/src/*

########################
# SpamAssassin
########################
RUN wget https://dlcdn.apache.org//spamassassin/source/Mail-SpamAssassin-${SPAMASSASSIN_TAG}.tar.gz \
  && tar xzf Mail-SpamAssassin-${SPAMASSASSIN_TAG}.tar.gz \
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
  && rm -rf /opt/src/*
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
  && tar xzf libdomainkeys-0.69.tar.gz \
  && cd libdomainkeys-0.69 \
  && patch -p1 < /opt/patches/dkim/libdomainkeys-openssl-1.1.patch \
  && patch < /opt/patches/dkim/libdomainkeys-0.69.diff \
  && make \
  && cp dktest /usr/local/bin/ \
  && install /opt/src/dkimsign.pl /usr/local/bin/ \
  && mv /var/qmail/bin/qmail-remote /var/qmail/bin/qmail-remote.orig \
  && install -T /opt/src/qmail-remote.sh /var/qmail/bin/qmail-remote \
# cleaning
  && rm -rf /opt/src/*

########################
# Qmail Remove https://www.fehcom.de/sqmail/man/qmail-qmaint.html
########################
RUN wget http://www.linuxmagic.com/opensource/qmail/qmail-remove/qmail-remove-0.95.tar.gz \
  && tar xzf qmail-remove-0.95.tar.gz \
  && cd qmail-remove-0.95 \
  && make \
  && make install \
# cleaning
  && rm -rf /opt/src/*
  
########################
# mess822
########################
RUN wget http://cr.yp.to/software/mess822-0.58.tar.gz \
  && tar xzf mess822-0.58.tar.gz \
  && cd mess822-0.58 \
  && sed -i "s#extern int errno;#\#include <errno.h>#" error.h \
  && make \
  && make setup \
# cleaning
  && rm -rf /opt/src/*
  
###########################
# FCRON
###########################
#http://fcron.free.fr/download.php
RUN wget http://fcron.free.fr/archives/fcron-${FCRON_TAG}.src.tar.gz \
  && tar xzf fcron-${FCRON_TAG}.src.tar.gz \
  && cd fcron-${FCRON_TAG} \
  && ./configure \
    --prefix=/usr \
    --sysconfdir=/etc \
    --localstatedir=/var \
    --with-sysfcrontab=no \
    --with-answer-all \
    --with-sendmail=/var/qmail/bin/sendmail \
    --with-boot-install=no \
    --with-systemdsystemunitdir=no \  
  && make \
  && make install \
# cleaning
  && rm -rf /opt/src/*

###########################
# ACME.SH
###########################
RUN wget -O acmesh-${ACMESH_TAG}.tar.gz https://github.com/acmesh-official/acme.sh/archive/refs/tags/${ACMESH_TAG}.tar.gz \
  && mkdir acmesh \
  && cd acmesh \
  && tar xzf ../acmesh-${ACMESH_TAG}.tar.gz --strip 1 \
  && ./acme.sh --install  \
    --home /usr/bin \
    --config-home /ssl/acme \
    --cert-home /ssl/acme/certs \
    --accountemail "_ACCOUNT_EMAIL_" \
    --no-cron \
    --no-profile \
  && mv /ssl/acme /opt/templates/ \
  && rm -rf /ssl \
# cleaning
  && rm -rf /opt/src/*
  
###########################
# Web parts
# we have to fix qmail-send s6-svc
###########################
COPY conf/lighttpd.conf /etc/lighttpd/lighttpd.conf
COPY conf/php.ini /etc/php/7.4/fpm/conf.d/99-qmail-aio.ini
COPY www/ /var/www/
RUN mkdir -p /run/php \
  && chown -R www-data.www-data /var/www/admin/html/ /var/www/admin/cgi/qmail-queue.php \
# Admin patches
  && cp /usr/bin/php7.4 /usr/bin/qmailq-php \ 
  && chmod 4755 /usr/bin/qmailq-php
  
###########################
# Roundcube
###########################
RUN cd /var/www/html \
  && curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/bin --filename=composer \
  && wget -O roundcubemail-${ROUNDCUBEMAIL_TAG}.tar.gz https://github.com/roundcube/roundcubemail/releases/download/${ROUNDCUBEMAIL_TAG}/roundcubemail-${ROUNDCUBEMAIL_TAG}-complete.tar.gz \
  && tar -xzf roundcubemail-${ROUNDCUBEMAIL_TAG}.tar.gz --strip 1 \
  && rm -f index.lighttpd.html roundcubemail-${ROUNDCUBEMAIL_TAG}.tar.gz \
  && cp composer.json-dist composer.json \
  && composer \
      --working-dir=/var/www/html/ \
      --no-interaction \
      update \
  && composer \
      --working-dir=/var/www/html/ \
			--no-interaction \
			--no-scripts \
      require \
          weird-birds/thunderbird_labels \
          prodrigestivill/gravatar \
  && rm -rf installer \
  && chown -R www-data.www-data /var/www/html

###########################
# Binaries
###########################
COPY bin/maildrop-filter /var/qmail/bin/maildrop-filter
COPY bin/qmail-queuescan /var/qmail/bin/qmail-queuescan
COPY bin/qmailctl /usr/local/bin/qmailctl
COPY bin/qmHandle /usr/local/bin/qmHandle
RUN chown vpopmail.vchkpw /var/qmail/bin/maildrop-filter \
  && chmod 600 /var/qmail/bin/maildrop-filter \
  && chown qmailq.sqmail /var/qmail/bin/qmail-queuescan \
  && chmod 1755 /var/qmail/bin/qmail-queuescan \
  && chmod 755 /usr/local/bin/qmailctl /usr/local/bin/qmHandle

###########################
# Services config
###########################
COPY bin/run/qmail-smtpd /service/qmail-smtpd/run
COPY bin/log/default /service/qmail-smtpd/log/run
COPY bin/run/qmail-smtpsd /service/qmail-smtpsd/run
COPY bin/log/default /service/qmail-smtpsd/log/run
COPY bin/run/qmail-smtpsub /service/qmail-smtpsub/run
COPY bin/log/default /service/qmail-smtpsub/log/run
COPY bin/run/qmail-send /service/qmail-send/run
COPY bin/log/default /service/qmail-send/log/run
COPY bin/run/dovecot /service/dovecot/run
COPY bin/log/default /service/dovecot/log/run
COPY bin/run/clamd /service/clamd/run
COPY bin/log/default /service/clamd/log/run
COPY bin/run/spamd /service/spamd/run
COPY bin/log/default /service/spamd/log/run
COPY bin/run/lighttpd /service/lighttpd/run
COPY bin/log/lighttpd /service/lighttpd/log/run
COPY bin/run/php-fpm /service/php-fpm/run
COPY bin/log/default /service/php-fpm/log/run
COPY bin/run/fcron /service/fcron/run
COPY bin/log/default /service/fcron/log/run
# For qmail-queue.php
RUN chown -R qmailq /service/qmail-send
  
###########################
# Templates
###########################
RUN cp -a /var/qmail/queue /opt/templates/ \
  && mv /var/qmail/control/ /opt/templates/

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
WORKDIR "/opt"
RUN rm -rf /opt/patches /opt/src \
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
EXPOSE 80 88

COPY bin/docker-entrypoint.sh /bin/
ENTRYPOINT ["/bin/docker-entrypoint.sh"]
CMD ["/bin/s6-svscan", "/service", "2>&1"]
