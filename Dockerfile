FROM debian:bookworm-slim
LABEL maintainer="nathanael@semhoun.net"

ENV DEBIAN_FRONTEND=noninteractive
ENV TERM=linux

ENV SQMAIL_AIO_VERSION="1.7"

ARG SQMAIL_TAG=4.3.20
ARG FEHQLIBS_TAG=27
ARG MESS822X_TAG=1.23
ARG UCSPISSL_TAG=0.13.03
ARG UCSPITCP6_TAG=1.13.02

ARG VPOPMAIL_TAG=5.6.8

ARG EXECLINE_TAG=2.9.7.0
ARG SKALIB_TAG=2.14.4.0
ARG S6_TAG=2.13.2.0

ARG ACMESH_TAG=3.1.0
ARG FCRON_TAG=3.4.0
ARG CLAMAV_TAG=1.4.2

ARG DOVECOT_TAG=2.4.1-4

ARG SPAMASSASSIN_TAG=4.0.2

ARG QMAILADMIN_TAG=1.2.24
ARG VQADMIN_TAG=2.4.3

ARG ROUNDCUBEMAIL_TAG=1.6.11
ARG QMAILFORWARD_TAG=1.0.3

ARG DMARCSRG_TAG=2.3

WORKDIR "/opt/src"

########################  
# Base install
########################
RUN mkdir -p /opt/src /opt/templates \
  && apt-get update \
  && apt-get -y install build-essential libtool-bin equivs bash dnsutils unzip git curl wget sudo ksh vim whiptail cmake apg \
  && apt-get clean \
## Add docker group for logs
  && groupadd -g 998 docker \
## Add MTA Local (equivs is needed)
  && echo 'Package: mta-local\n\
Provides: mail-transport-agent\n\
Conflicts: mail-transport-agent\n\
Description: A local MTA package \n\
 A package, which can be used to establish a locally installed\n\
 mail transport agent.\n'\
  > /opt/src/mail-transport-agent.ctl \
  && equivs-build /opt/src/mail-transport-agent.ctl \
  && dpkg -i mta-local*.deb \
  && rm -f /opt/src/* \
# Fixes for slim install
  && mkdir -p /usr/share/man/man1 /usr/share/man/man5 /usr/share/man/man7 /usr/share/man/man8 \
  && touch /usr/share/man/man1/maildirmake.1.gz \
  && touch /usr/share/man/man8/deliverquota.8.gz \
  && touch /usr/share/man/man1/lockmail.1.gz

########################  
# Encoding fix
########################
RUN apt-get -y install locales \
  && apt-get clean \
  && sed \
      -e 's/# fr_FR.UTF-8 UTF-8/fr_FR.UTF-8 UTF-8/' \
      -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' \
      -i /etc/locale.gen \
  && /usr/sbin/locale-gen en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

########################  
# Fix certificates
########################
RUN curl -o /usr/share/ca-certificates/ZeroSSL_RSA_Domain_Secure_Site_CA.crt https://ssl-tools.net/certificates/c81a8bd1f9cf6d84c525f378ca1d3f8c30770e34.pem \
  && echo "ZeroSSL_RSA_Domain_Secure_Site_CA.crt" >> /etc/ca-certificates.conf \
  && update-ca-certificates
  
########################  
# Additionnals packages
########################
RUN apt-get -y install bsd-mailx \
    libperl-dev libmariadb-dev libmariadb-dev-compat csh bzip2 razor pyzor ksh libclass-dbi-mysql-perl libnet-dns-perl libio-socket-inet6-perl libdigest-sha-perl libnetaddr-ip-perl libmail-spf-perl libgeo-ip-perl libnet-cidr-lite-perl libnet-patricia-perl libencode-detect-perl libperl-dev libssl-dev libcurl4-gnutls-dev \
    check libbz2-dev libxml2-dev libpcre2-dev libjson-c-dev libncurses-dev pkg-config \
    libhtml-parser-perl re2c libdigest-sha-perl libdbi-perl libgeoip2-perl libio-string-perl libbsd-resource-perl libmilter-dev libidn2-dev \
    mariadb-client \
    socat inetutils-ping \
    swaks expect telnet \
    lighttpd php8.2-fpm \
	libev-dev automake1.11 automake \
	fetchmail liblockfile-simple-perl \
# For dovecot
  &&  apt-get -y install libxapian-dev \
	# libldap2 must be removed in future
	libldap2-dev \ 
# For roundcube
  && apt-get install -y php8.2-zip php8.2-pspell php8.2-mysql php8.2-gd php8.2-imap php8.2-xml php8.2-mbstring php8.2-intl php-imagick aspell-fr php8.2-intl php8.2-curl \
  && cpan -i IP::Country::DB_File MaxMind::DB::Reader Geo::IP IP::Country::Fast Digest::SHA1 Net::LibIDN2 Email::Address::XS \ 
  && rm -rf /root/.local \
# Cleaning
  && apt-get clean

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
  && mv fehQlibs-* qlibs \
  && cd qlibs \
  && make -C src \
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
## mess822x
  && cd /opt/src \
  && wget https://www.fehcom.de/ipnet/mess822x/mess822x-${MESS822X_TAG}.tgz \
  && cd /package \
  && tar xzf /opt/src/mess822x-${MESS822X_TAG}.tgz \
  && cd  mail/mess822x/mess822x-${MESS822X_TAG} \
  && package/install \
## sqmail
  && cd /opt/src \
  && wget https://www.fehcom.de/sqmail/sqmail-${SQMAIL_TAG}.tgz \
  && cd /package \
  && tar xzf /opt/src/sqmail-${SQMAIL_TAG}.tgz \
  && cd mail/sqmail/sqmail-${SQMAIL_TAG} \
  && sed -i 's/ -lsocket//g' conf-ld \
  && package/dir \
  && package/ids \
  && package/ucspissl \
  && package/compile \
#  && package/upgrade \
  && package/legacy \
  && package/man \
  && package/control \
  && package/sslenv \
#  && package/service \
  && package/scripts \
#  && package/run \
# Fix sendmail
  && cp /var/qmail/bin/sendmail /usr/sbin/sendmail \
## cleaning
  && rm -rf /opt/src/* \
  && rm -rf /var/qmail/svc /service/*
    
########################
# VPopMail
########################
RUN cd /opt/src \
  && mkdir -p /var/vpopmail \
  && groupadd -g 89 vchkpw \
  && useradd -g vchkpw -u 89 -s /usr/sbin/nologin -d /var/vpopmail vpopmail \
  && chown -R vpopmail:vchkpw /var/vpopmail \
  && wget -O vpopmail-${VPOPMAIL_TAG}.tar.gz https://github.com/sagredo-dev/vpopmail/archive/refs/tags/v${VPOPMAIL_TAG}.tar.gz \
  && mkdir vpopmail \
  && cd vpopmail \
  && tar xzf ../vpopmail-${VPOPMAIL_TAG}.tar.gz --strip 1 \
  && ./configure \
    --enable-qmaildir=/var/qmail/ \
    --enable-qmail-newu=/var/qmail/bin/qmail-newu \
    --enable-qmail-inject=/var/qmail/bin/qmail-inject \
    --enable-qmail-newmrh=/var/qmail/bin/qmail-newmrh \
    --disable-roaming-users \
    --enable-auth-module=mysql \
    --enable-incdir=/usr/include/mariadb \
    --enable-libdir=/usr/lib64 \
    --enable-logging=e \
    --disable-clear-passwd \
    --enable-auth-logging \
    --enable-sql-logging=e \
    --disable-passwd \
    --enable-qmail-ext \
    --enable-qmail-cdb-name=assign.cdb \
    --enable-learn-passwords \
    --enable-mysql-limits \
    --enable-valias \
    --enable-sql-aliasdomains \
    --enable-defaultdelivery \
    --enable-md5-passwords \
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
# Dovecot & PingeonHole
########################
RUN groupadd -g 2110 dovecot \
  && useradd -g dovecot -u 7798 -s /usr/sbin/nologin -d /var/run dovenull \
  && useradd -g dovecot -u 7799 -s /usr/sbin/nologin -d /var/run dovecot \
  && wget -O dovecot-${DOVECOT_TAG}.tar.gz https://dovecot.org/releases/2.4/dovecot-${DOVECOT_TAG}.tar.gz \
  && wget -O dovecot-pigeonhole-${DOVECOT_TAG}.tar.gz  https://pigeonhole.dovecot.org/releases/2.4/dovecot-pigeonhole-${DOVECOT_TAG}.tar.gz \
  && mkdir -p /opt/src/dovecot \
	/opt/src/dovecot-pigeonhole \
	/etc/dovecot /var/run/dovecot \
# Dovecot 
  && cd /opt/src/dovecot \
  && tar xzf ../dovecot-${DOVECOT_TAG}.tar.gz --strip 1 \
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
    --with-ldap \
    --without-pgsql \
    --without-sqlite \
	--with-flatcurve \
  && make \
  && make install \
# PingeonHole 
  && cd /opt/src/dovecot-pigeonhole \
  && tar xzf ../dovecot-pigeonhole-${DOVECOT_TAG}.tar.gz  --strip 1 \
  && ./configure \
    --prefix=/usr \
    --sysconfdir=/etc \
    --localstatedir=/var \
    --with-dovecot=/usr/lib/dovecot \
	--with-ldap=no \
  && make \
  && make install \
# cleaning
  && rm -rf /opt/src/*
  
########################
# qmail-autoresponder
########################
RUN wget http://untroubled.org/bglibs/bglibs-2.04.tar.gz \
  && tar xzf bglibs-2.04.tar.gz \
  && cd bglibs-2.04 \
  && sed -i 's/69,5,1,51/45,63,65,23/' net/resolve_ipv4addr.c \
  && sed -i 's/69.5.1.51 => .*/45.63.65.23 => vx0.untroubled.org/' net/resolve_ipv4addr.c \
  && make \
  && make install \
  && ldconfig \
  && cd /opt/src \
  && wget https://untroubled.org/qmail-autoresponder/qmail-autoresponder-2.0.tar.gz \
  && tar xzf qmail-autoresponder-2.0.tar.gz \
  && cd qmail-autoresponder-2.0 \
  && make \
  && make install \
# cleaning
  && rm -rf /opt/src/*

########################
# ezmlm-idx
########################
RUN wget http://notes.sagredo.eu/files/qmail/tar/ezmlm-idx-7.2.2.tar.gz \
  && tar xzf ezmlm-idx-7.2.2.tar.gz \
  && cd ezmlm-idx-7.2.2 \
  && make \
  && make man \
  && make install \
# cleaning
  && rm -rf /opt/src/*
  
########################
# QmailAdmin
RUN wget -O qmailadmin-${QMAILADMIN_TAG}.tar.gz https://github.com/sagredo-dev/qmailadmin/archive/refs/tags/v${QMAILADMIN_TAG}.tar.gz  \
########################
  && mkdir qmailadmin \
  && cd qmailadmin \
  && tar xzf ../qmailadmin-${QMAILADMIN_TAG}.tar.gz --strip 1 \
  && ./configure \
    --enable-cgibindir=/var/www/admin/cgi \
    --enable-htmldir=/var/www/admin/html/ \
    --enable-imagedir=/var/www/admin/html/images/qmailadmin \
    --enable-cgipath=/cgi/qmailadmin \
    --enable-imageurl=/images/qmailadmin \
    --enable-qmaildir=/var/qmail \
    --disable-ezmlm-mysql \
    --enable-modify-quota \
    --enable-domain-autofill \
    --enable-help \
    --enable-vpopuser=vpopmail \
    --enable-vpopgroup=vchkpw \
    --enable-domain-autofill \
    --enable-autoresponder-path=/usr/local/bin \
    --enable-qmail-autoresponder \
    --enable-maxusersperpage=100 \
    --enable-maxaliasesperpage=100 \
  && make \
  && make install \
# cleaning
  && rm -rf /opt/src/*

########################
# vqadmin
########################
RUN wget -O vqadmin-${VQADMIN_TAG}.tar.gz https://github.com/sagredo-dev/vqadmin/archive/refs/tags/v${VQADMIN_TAG}.tar.gz  \
  && mkdir vqadmin \
  && cd vqadmin \
  && tar xzf ../vqadmin-${VQADMIN_TAG}.tar.gz --strip 1 \
  && sed -i 's/cgi-bin/cgi/g' configure html/* \
  && ./configure \
    --enable-cgibindir=/var/www/admin/cgi \
    --enable-wwwroot=/var/www/admin/html \
  && make \
  && make install \
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
# cleaning
  && rm -rf /opt/src/*

########################
# DCC
########################
RUN wget https://www.dcc-servers.net/dcc/source/dcc.tar.Z \
  && tar xzf dcc.tar.Z \
  && cd dcc-2.3.169 \
  && ./configure --disable-dccm \
  && make \
  && make install \
# cleaning
  && rm -rf /opt/src/*

########################
# SpamAssassin
########################
RUN wget https://dlcdn.apache.org/spamassassin/source/Mail-SpamAssassin-${SPAMASSASSIN_TAG}.tar.gz \
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
 
###########################
# FCRON
###########################
#http://fcron.free.fr/download.php
RUN apt-get install -y docbook docbook-xsl docbook-xml docbook-utils manpages-dev \
  && wget -O fcron-${FCRON_TAG}.tar.gz https://github.com/yo8192/fcron/archive/refs/tags/ver$(echo $FCRON_TAG | sed 's/\./_/g').tar.gz \
  && mkdir fcron \
  && cd fcron \
  && tar xzf ../fcron-${FCRON_TAG}.tar.gz --strip 1 \
  && autoconf \
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
  && rm -rf /opt/src/* \
  && apt-get purge -y manpages-dev \
  && apt-get clean

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
###########################
RUN mkdir -p /run/php \
# Admin patches
  && cp /usr/bin/php8.2 /usr/bin/qmailq-php \ 
  && chmod 4755 /usr/bin/qmailq-php
  
###########################
# Roundcube
###########################
RUN cd /var/www/html \
  && curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/bin --filename=composer \
  && wget -O roundcubemail-${ROUNDCUBEMAIL_TAG}.tar.gz https://github.com/roundcube/roundcubemail/releases/download/${ROUNDCUBEMAIL_TAG}/roundcubemail-${ROUNDCUBEMAIL_TAG}-complete.tar.gz \
  && tar -xzf roundcubemail-${ROUNDCUBEMAIL_TAG}.tar.gz --strip 1 \
  && rm -f index.lighttpd.html roundcubemail-${ROUNDCUBEMAIL_TAG}.tar.gz \
  && cp config/config.inc.php.sample config/config.inc.php \
  && echo "$config['db_dsnw'] = 'sqlite:///var/www/html/installer/sqlite.db?mode=0646';" > config/config.inc.php \
  && cp composer.json-dist composer.json \
  && composer \
    --working-dir=/var/www/html/ \
    --no-interaction \
    update \
  && composer \
    --working-dir=/var/www/html/ \
    --no-interaction \
    require \
      weird-birds/thunderbird_labels \
      prodrigestivill/gravatar \
      johndoh/sauserprefs \
      johndoh/contextmenu \
      johndoh/swipe \
	  elm/identity_smtp \
  && composer \
    --working-dir=/var/www/html/ \
    --no-interaction \
    update \
# Manual fetchmail install
  && cd /var/www/html \
  && mkdir plugins/fetchmail \
  && cd plugins/fetchmail \
  && wget -O fetchmail.tgz  https://github.com/semhoun/fetchmail/archive/refs/heads/feature/server_port.tar.gz \
  && tar -xzf fetchmail.tgz --strip 1 \
  && rm -f fetchmail.tgz \
# Manual qmailforward install
  && cd /var/www/html \
  && mkdir plugins/qmailforward \
  && cd plugins/qmailforward \
  && wget -O qmailforward.tgz https://github.com/sagredo-dev/qmailforward/archive/refs/tags/v${QMAILFORWARD_TAG}.tar.gz \
  && tar -xzf qmailforward.tgz --strip 1 \
  && rm -f qmailforward.tgz \
# Remove config file for autoinit
  && rm -f /var/www/html/config/config.inc.php \
# Cleaning
  && rm -rf installer

###########################
# DmarcSrg
###########################
RUN mkdir -p /var/www/admin/dmarc \
  && wget -O /opt/src/dmarcsrg.tgz https://github.com/liuch/dmarc-srg/archive/refs/tags/v${DMARCSRG_TAG}.tar.gz \
  && cd /var/www/admin/dmarc \
  && tar -xzf /opt/src/dmarcsrg.tgz --strip 1 \
  && composer install \
  && chown www-data:www-data /var/www/admin/dmarc \
# Cleaning
  && rm -rf installer

###########################
# ROOT FS && Co
###########################
COPY rootfs /
RUN chown qmailq:sqmail /var/qmail/bin/qmail-queuescan \
  && chmod 1755 /var/qmail/bin/qmail-queuescan \
  && chmod 755 /opt/bin/* \
  && chown -R www-data:www-data /var/www/html /var/www/admin/html \
  && chown -R qmailq /service/qmail-send \
  && chown -R vpopmail:vchkpw /etc/dovecot/sieve \
  && chmod -R ug+w /etc/dovecot/sieve/* \
  && cd /etc/dovecot/sieve/ && /usr/bin/sievec . \
  && chown -R clamav:clamav /etc/clamav \
# Templates
  && cp -a /var/qmail/queue /opt/templates/ \
  && mv /var/qmail/control/ /opt/templates/ \
# Volumes 
  && mkdir -p \
    /var/vpopmail/domains/ \
    /ssl/ \
    /var/vpopmail/etc \
    /var/qmail/control \
    /var/qmail/ssl/domainkeys \
    /log \
    /var/spamassassin \
    /var/qmail/tmp \
# Final cleaning
  && rm -rf \
    /opt/src \
    /service/qmail-pop3* \
    /var/log/qmail-pop3* \
    /service/*/down

###########################
# Volumes
VOLUME [ \
  "/var/vpopmail/domains",\
  "/ssl",\
  "/var/vpopmail/etc",\
  "/var/qmail/control",\
  "/log",\
  "/var/spamassassin",\
  "/var/qmail/users", \
  "/var/qmail/ssl/domainkeys" \
]

###########################
# Docker final parms
###########################
WORKDIR "/opt"
ENV PATH="${PATH}:/opt/bin"
EXPOSE 25 465 587
EXPOSE 110 995
EXPOSE 143 993
EXPOSE 80 88

ENTRYPOINT ["/opt/bin/entrypoint.sh"]
CMD ["/bin/s6-svscan", "/service", "2>&1"]
