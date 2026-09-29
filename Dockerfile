# syntax=docker/dockerfile:1.27.0

FROM debian:trixie-slim
LABEL maintainer="nathanael@semhoun.net"

ARG DEBIAN_FRONTEND=noninteractive
ENV TERM=linux

ENV SQMAIL_AIO_VERSION="1.8"

# Explicitly selected despite upstream's beta designation.
ARG SQMAIL_TAG=4.4.14
ARG FEHQLIBS_TAG=31
ARG MESS822X_TAG=1.27
ARG UCSPISSL_TAG=0.13.08
ARG UCSPITCP6_TAG=1.13.08

ARG VPOPMAIL_TAG=5.6.14
ARG EZMLM_COMMIT=231d62d42ad11d62c0e6afec5d07cb077d657587

ARG EXECLINE_TAG=2.9.9.2
ARG SKALIB_TAG=2.15.1.0
ARG S6_TAG=2.15.1.0

ARG ACMESH_TAG=3.1.6
ARG FCRON_TAG=3.4.1
ARG FCRON_ARCHIVE_TAG=ver3_4_1
ARG CLAMAV_TAG=1.5.4
ARG RUST_TAG=1.98.1
ARG RUSTUP_TAG=1.29.1

ARG DOVECOT_TAG=2.4.5

ARG SPAMASSASSIN_TAG=4.0.2
ARG DCC_TAG=2.3.169

ARG QMAILADMIN_TAG=1.2.28
ARG VQADMIN_TAG=2.4.7

ARG ROUNDCUBEMAIL_TAG=1.7.4
ARG QMAILFORWARD_TAG=1.0.5

ARG DMARCSRG_TAG=2.3

WORKDIR "/opt/src"

########################  
# Base install
########################
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
  mkdir -p /opt/src /opt/templates \
  && apt-get update \
  && apt-get install -y --no-install-recommends build-essential libtool-bin equivs bash ca-certificates dnsutils unzip git curl wget sudo ksh vim whiptail cmake apg gpg gpg-agent gpgv openssh-client groff-base \
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
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
  apt-get update \
  && apt-get install -y --no-install-recommends locales \
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
# PHP 8.5 is supplied by Sury, not Debian trixie's PHP 8.4 packages.
RUN curl -fsSL https://packages.sury.org/php/apt.gpg -o /usr/share/keyrings/debsuryorg-archive-keyring.gpg \
  && gpg --batch --show-keys --with-colons /usr/share/keyrings/debsuryorg-archive-keyring.gpg \
     | grep -qx 'fpr:::::::::15058500A0235D97F5D10063B188E2B695BD4743:' \
  && echo 'deb [signed-by=/usr/share/keyrings/debsuryorg-archive-keyring.gpg] https://packages.sury.org/php/ trixie main' > /etc/apt/sources.list.d/php.list
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
  apt-get update \
  && apt-get install -y --no-install-recommends bsd-mailx \
    libperl-dev libmariadb-dev libmariadb-dev-compat csh bzip2 razor pyzor ksh libclass-dbi-mysql-perl libnet-dns-perl libio-socket-inet6-perl libdigest-sha-perl libnetaddr-ip-perl libmail-spf-perl libgeo-ip-perl libnet-cidr-lite-perl libnet-patricia-perl libencode-detect-perl libssl-dev libcurl4-gnutls-dev \
    check libbz2-dev libxml2-dev libpcre2-dev libjson-c-dev libncurses-dev pkg-config \
    libhtml-parser-perl re2c libdbi-perl libgeoip2-perl libio-string-perl libbsd-resource-perl libmilter-dev libidn2-dev \
    mariadb-client \
    socat inetutils-ping \
    swaks expect telnet \
    lighttpd lighttpd-mod-openssl lighttpd-mod-magnet php8.5-fpm php8.5-cli \
    libev-dev automake \
    fetchmail liblockfile-simple-perl  \
    libbg-dev \
# For dovecot
  && apt-get install -y --no-install-recommends libxapian-dev python3 \
    # libldap2 must be removed in future
    libldap2-dev \
# For roundcube
  && apt-get install -y --no-install-recommends php8.5-zip php8.5-pspell php8.5-mysql php8.5-gd php8.5-xml php8.5-mbstring php8.5-intl php8.5-imagick php8.5-imap aspell-fr php8.5-curl \
  && cpan -i IP::Country::DB_File MaxMind::DB::Reader Geo::IP IP::Country::Fast Digest::SHA1 Net::LibIDN2 Email::Address::XS \
  && mkdir -p /usr/local/share/sqmail-aio \
  && perl -e 'for my $m (@ARGV) { eval "require $m"; die $@ if $@; printf "%s %s\n", $m, $m->VERSION; }' \
    IP::Country::DB_File MaxMind::DB::Reader Geo::IP IP::Country::Fast Digest::SHA1 Net::LibIDN2 Email::Address::XS \
    > /usr/local/share/sqmail-aio/cpan-versions.txt \
# Cleaning in the same layer keeps CPAN's build cache out of the image.
  && rm -rf /root/.cpan /root/.local

########################
# Skarnet S6
########################
RUN wget https://skarnet.org/software/skalibs/skalibs-${SKALIB_TAG}.tar.gz \
  && tar xzf skalibs-${SKALIB_TAG}.tar.gz \
  && cd skalibs-${SKALIB_TAG} \
  && ./configure \
  && make \
  && make install \
  && cd /opt/src/ \
  && wget https://skarnet.org/software/execline/execline-${EXECLINE_TAG}.tar.gz \
  && tar xzf execline-${EXECLINE_TAG}.tar.gz \
  && cd execline-${EXECLINE_TAG} \
  && ./configure \
  && make \
  && make install \
  && cd /opt/src/ \
  && wget https://skarnet.org/software/s6/s6-${S6_TAG}.tar.gz \
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
  && cd net/ucspi-tcp6-${UCSPITCP6_TAG} \
  && package/install \
## mess822x
  && cd /opt/src \
  && wget https://www.fehcom.de/ipnet/mess822x/mess822x-${MESS822X_TAG}.tgz \
  && cd /package \
  && tar xzf /opt/src/mess822x-${MESS822X_TAG}.tgz \
  && cd mail/mess822x-${MESS822X_TAG} \
  && package/install \
## sqmail
  && cd /opt/src \
  && wget https://www.fehcom.de/sqmail/sqmail-${SQMAIL_TAG}.tgz \
  && wget https://www.fehcom.de/sqmail/sqmail-4.3.25a.tgz \
  && cd /package \
  && mkdir -p mail/sqmail/sqmail-${SQMAIL_TAG} \
  && tar xzf /opt/src/sqmail-${SQMAIL_TAG}.tgz --strip-components=2 -C mail/sqmail/sqmail-${SQMAIL_TAG} \
  && cd mail/sqmail/sqmail-${SQMAIL_TAG} \
# Temporary 4.3.25a SRS backport; reevaluate on SQMail updates (see AGENTS.md).
  && tar xzf /opt/src/sqmail-4.3.25a.tgz --strip-components=2 \
    mail/sqmail-4.3.25a/src/srs2.c \
    mail/sqmail-4.3.25a/src/include/srs2.h \
    mail/sqmail-4.3.25a/src/srsforward.c \
    mail/sqmail-4.3.25a/src/srsreverse.c \
  && sed -i 's/srsq/srs2/g' src/Makefile package/files \
  && rm -f src/srsq.c src/include/srsq.h \
  && sed -i -e 's/ -lsocket//g' -e 's/ -m64//g' conf-ld \
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
COPY --link --chmod=755 rootfs/opt/bin/vpopmail-inject.sh /opt/bin/vpopmail-inject.sh
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
    --enable-qmail-inject=/opt/bin/vpopmail-inject.sh \
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
  && wget https://dovecot.org/releases/2.4/dovecot-${DOVECOT_TAG}.tar.gz.sig \
  && wget https://pigeonhole.dovecot.org/releases/2.4/dovecot-pigeonhole-${DOVECOT_TAG}.tar.gz.sig \
# Download the official signing key.
  && wget -O dovecot-key.asc https://repo.dovecot.org/DOVECOT-REPO-GPG-2.4 \
  && gpg --batch --dearmor -o dovecot-key.gpg dovecot-key.asc \
  && gpgv --keyring /opt/src/dovecot-key.gpg dovecot-${DOVECOT_TAG}.tar.gz.sig dovecot-${DOVECOT_TAG}.tar.gz \
  && gpgv --keyring /opt/src/dovecot-key.gpg dovecot-pigeonhole-${DOVECOT_TAG}.tar.gz.sig dovecot-pigeonhole-${DOVECOT_TAG}.tar.gz \
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
RUN wget https://untroubled.org/qmail-autoresponder/qmail-autoresponder-2.0.tar.gz \
  && wget https://untroubled.org/qmail-autoresponder/qmail-autoresponder-2.0.tar.gz.sig \
  && wget -O autoresponder-key.asc https://untroubled.org/pgpkey.txt \
  && gpg --batch --dearmor -o autoresponder-key.gpg autoresponder-key.asc \
  && gpgv --keyring /opt/src/autoresponder-key.gpg qmail-autoresponder-2.0.tar.gz.sig qmail-autoresponder-2.0.tar.gz \
  && tar xzf qmail-autoresponder-2.0.tar.gz \
  && cd qmail-autoresponder-2.0 \
  && make \
  && make install \
# cleaning
  && rm -rf /opt/src/*

########################
# ezmlm-idx
########################
RUN git clone https://github.com/sagredo-dev/ezmlm-idx.git \
  && cd ezmlm-idx \
  && git checkout --detach ${EZMLM_COMMIT} \
  && tools/makemake \
  && make \
  && make man \
  && make install \
# cleaning
  && rm -rf /opt/src/*
  
########################
# QmailAdmin
COPY --link rootfs/opt/patches/qmailadmin-log-timezone.patch /opt/patches/qmailadmin-log-timezone.patch
RUN wget -O qmailadmin-${QMAILADMIN_TAG}.tar.gz https://github.com/sagredo-dev/qmailadmin/archive/refs/tags/v${QMAILADMIN_TAG}.tar.gz  \
########################
  && mkdir qmailadmin \
  && cd qmailadmin \
  && tar xzf ../qmailadmin-${QMAILADMIN_TAG}.tar.gz --strip 1 \
  && patch --batch --fuzz=0 -p1 < /opt/patches/qmailadmin-log-timezone.patch \
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
  && curl -fLsS -o rustup-init.sh https://raw.githubusercontent.com/rust-lang/rustup/${RUSTUP_TAG}/rustup-init.sh \
  && RUSTUP_ARCH=$(RUSTUP_INIT_SH_PRINT=arch sh rustup-init.sh) \
  && curl -fLsS -o rustup-init https://static.rust-lang.org/rustup/archive/${RUSTUP_TAG}/${RUSTUP_ARCH}/rustup-init \
  && chmod +x rustup-init \
  && ./rustup-init -y --no-modify-path --profile minimal --default-toolchain ${RUST_TAG} \
  && . /root/.cargo/env \
  && mkdir -p /usr/local/share/sqmail-aio \
  && { rustc --version; cargo --version; } > /usr/local/share/sqmail-aio/rust-version.txt \
  && wget https://www.clamav.net/downloads/production/clamav-${CLAMAV_TAG}.tar.gz \
  && wget https://www.clamav.net/downloads/production/clamav-${CLAMAV_TAG}.tar.gz.sig \
  && curl -fLsS -A 'Mozilla/5.0' -o clamav-key.asc https://www.clamav.net/downloads/gpg_public_key \
  && gpg --batch --dearmor -o clamav-key.gpg clamav-key.asc \
  && gpgv --keyring /opt/src/clamav-key.gpg clamav-${CLAMAV_TAG}.tar.gz.sig clamav-${CLAMAV_TAG}.tar.gz \
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
  && rm -rf /opt/src/* /root/.cargo /root/.rustup

########################
# DCC
########################
RUN wget https://www.dcc-servers.net/dcc/source/old/dcc-${DCC_TAG}.tar.Z \
  && tar xzf dcc-${DCC_TAG}.tar.Z \
  && cd dcc-${DCC_TAG} \
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
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
  apt-get update \
  && apt-get install -y --no-install-recommends docbook docbook-xsl docbook-xml docbook-utils manpages-dev \
  && wget -O fcron-${FCRON_TAG}.tar.gz https://github.com/yo8192/fcron/archive/refs/tags/${FCRON_ARCHIVE_TAG}.tar.gz \
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
  && apt-get purge -y --auto-remove \
    docbook \
    docbook-xsl \
    docbook-xml \
    docbook-utils \
    manpages-dev

###########################
# ACME.SH
###########################
RUN git clone --depth 1 --branch ${ACMESH_TAG} https://github.com/acmesh-official/acme.sh.git acmesh \
  && cd acmesh \
  && git -c gpg.ssh.program=ssh-keygen -c gpg.ssh.allowedSignersFile=allowed_signers verify-tag ${ACMESH_TAG} \
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
  && cp /usr/bin/php8.5 /usr/bin/qmailq-php \
  && chmod 4755 /usr/bin/qmailq-php
  
###########################
# Roundcube
###########################
ARG COMPOSER_VERSION=2.10.3
# No stable Fetchmail plugin release includes src_port; pin the required feature tree.
ARG FETCHMAIL_PLUGIN_COMMIT=3e3f212e51d01e0380b4297fbedf71857c031566
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
  apt-get update \
  && apt-get install -y --no-install-recommends php8.5-ldap \
  && cd /var/www/html \
  && curl -fsSLo /opt/src/composer-setup.php https://getcomposer.org/installer \
  && php8.5 /opt/src/composer-setup.php --version=${COMPOSER_VERSION} --install-dir=/usr/bin --filename=composer \
  && rm -f /opt/src/composer-setup.php \
  && wget -O roundcubemail-${ROUNDCUBEMAIL_TAG}.tar.gz https://github.com/roundcube/roundcubemail/releases/download/${ROUNDCUBEMAIL_TAG}/roundcubemail-${ROUNDCUBEMAIL_TAG}-complete.tar.gz \
  && tar -xzf roundcubemail-${ROUNDCUBEMAIL_TAG}.tar.gz --strip 1 \
  && rm -f index.lighttpd.html roundcubemail-${ROUNDCUBEMAIL_TAG}.tar.gz \
  && cp config/config.inc.php.sample config/config.inc.php \
  && if [ -f composer.json-dist ]; then cp composer.json-dist composer.json; fi \
# Database initialization and upgrades belong to container startup, not image construction.
  && export COMPOSER_ALLOW_SUPERUSER=1 SKIP_DB_INIT=1 SKIP_DB_UPDATE=1 \
  && composer config minimum-stability stable \
  && composer config prefer-stable true \
  && composer config allow-plugins.roundcube/plugin-installer true \
  && composer --no-interaction require --no-update \
      roundcube/plugin-installer:0.3.11 \
      weird-birds/thunderbird_labels:1.6.2 \
      prodrigestivill/gravatar:1.7 \
      johndoh/sauserprefs:1.21 \
      johndoh/contextmenu:3.3.1 \
      johndoh/swipe:0.6 \
      elm/identity_smtp:1.7.0 \
      hercegdoo/aicomposeplugin:3.0.0 \
  && composer --no-interaction update --no-dev --prefer-dist --with-all-dependencies \
  && composer check-platform-reqs --no-dev \
  && composer audit --locked --no-dev \
  && composer show --locked --no-dev \
# Manual fetchmail install
  && cd /var/www/html \
  && mkdir plugins/fetchmail \
  && cd plugins/fetchmail \
  && wget -O fetchmail.tgz https://github.com/semhoun/fetchmail/archive/${FETCHMAIL_PLUGIN_COMMIT}.tar.gz \
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
  && rm -f /var/www/html/config/config.inc.php /var/www/html/plugins/sauserprefs/config.inc.php \
# Cleaning
  && rm -rf /var/www/html/installer /var/www/html/public_html/installer.php /root/.composer/cache /root/.cache/composer

###########################
# Mail statistics database and PDF dependencies (outside the webroot)
###########################
COPY --link rootfs/opt/mail-stats-pdf/composer.json rootfs/opt/mail-stats-pdf/composer.lock /opt/mail-stats-pdf/
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
  apt-get update \
  && apt-get install -y --no-install-recommends python3-pymysql python3-cryptography \
  && cd /opt/mail-stats-pdf \
  && export COMPOSER_ALLOW_SUPERUSER=1 \
  && php8.5 /usr/bin/composer --no-interaction --no-plugins --no-scripts validate --strict --no-check-all \
  && php8.5 /usr/bin/composer --no-interaction --no-plugins --no-scripts install --no-dev --prefer-dist --optimize-autoloader \
  && php8.5 /usr/bin/composer --no-plugins --no-scripts check-platform-reqs --no-dev \
  && php8.5 /usr/bin/composer --no-plugins --no-scripts audit --locked --no-dev \
  && php8.5 /usr/bin/composer --no-plugins --no-scripts licenses --no-dev \
  && chown -R root:root /opt/mail-stats-pdf \
  && chmod -R u=rwX,go=rX /opt/mail-stats-pdf \
  && rm -rf /root/.composer/cache /root/.cache/composer

###########################
# DmarcSrg
###########################
RUN mkdir -p /var/www/admin/dmarc \
  && wget -O /opt/src/dmarcsrg.tgz https://github.com/liuch/dmarc-srg/archive/refs/tags/v${DMARCSRG_TAG}.tar.gz \
  && cd /var/www/admin/dmarc \
  && tar -xzf /opt/src/dmarcsrg.tgz --strip 1 \
  && export COMPOSER_ALLOW_SUPERUSER=1 \
  && composer config minimum-stability stable \
  && composer config prefer-stable true \
# Refresh transitives within the application's supported constraints, retaining the resolved lock.
  && composer --no-interaction update --no-dev --prefer-dist --with-all-dependencies \
  && composer check-platform-reqs --no-dev \
  && composer audit --locked --no-dev \
  && composer show --locked --no-dev \
  && chown www-data:www-data /var/www/admin/dmarc \
# Cleaning
  && rm -rf installer /root/.composer/cache /root/.cache/composer \
  && rm -f /opt/src/dmarcsrg.tgz

###########################
# SQMail RCPTTO compatibility
###########################
# Bound the non-NUL mailto copy; reset recipients while retaining DELIVERTO's prefix.
RUN cd /package/mail/sqmail/sqmail-${SQMAIL_TAG}/src \
  && sed -i \
      -e '/^stralloc mailto = {0};$/a unsigned int mailto_prefixlen = 0;' \
      -e '/^    if (!stralloc_cats(\&mailto," ")) die_nomem();$/a\    mailto_prefixlen = mailto.len;' \
      -e '/^  if (!stralloc_copys(\&rcptto,"")) die_nomem();$/a\  mailto.len = mailto_prefixlen;' \
      -e 's/stralloc_copys(\&deliverto,mailto.s)/stralloc_copyb(\&deliverto,mailto.s,mailto.len)/' qmail-smtpd.c \
  && make -C ../compile qmail-smtpd \
  && metadata=$(stat -c '%u:%g:%a' /var/qmail/bin/qmail-smtpd) \
  && cp ../compile/qmail-smtpd /var/qmail/bin/qmail-smtpd \
  && test "${metadata}" = "$(stat -c '%u:%g:%a' /var/qmail/bin/qmail-smtpd)"

###########################
# ROOT FS && Co
###########################
RUN mkdir -p /usr/local/share/sqmail-aio \
  && dpkg-query -W -f='${binary:Package}\t${Version}\n' > /usr/local/share/sqmail-aio/debian-packages.tsv \
  && php --version > /usr/local/share/sqmail-aio/php-version.txt \
  && printf '%s\n' "SQMail=${SQMAIL_TAG} (4.3.25a SRS backport; local RCPTTO bounds/reset fix)" \
    "fehQlibs=${FEHQLIBS_TAG}" "ucspi-ssl=${UCSPISSL_TAG}" "ucspi-tcp6=${UCSPITCP6_TAG}" \
    "mess822x=${MESS822X_TAG}" "vpopmail/vusaged=${VPOPMAIL_TAG}" "ezmlm-idx=${EZMLM_COMMIT}" \
    "skalibs=${SKALIB_TAG}" "execline=${EXECLINE_TAG}" "s6=${S6_TAG}" \
    "Dovecot/Pigeonhole=${DOVECOT_TAG}" "qmail-autoresponder=2.0" \
    "QmailAdmin=${QMAILADMIN_TAG}" "vqadmin=${VQADMIN_TAG}" "ClamAV=${CLAMAV_TAG}" \
    "DCC=${DCC_TAG}" "SpamAssassin=${SPAMASSASSIN_TAG}" "fcron=${FCRON_TAG}" \
    "acme.sh=${ACMESH_TAG}" "Roundcube=${ROUNDCUBEMAIL_TAG}" "qmailforward=${QMAILFORWARD_TAG}" \
    "Fetchmail-plugin=${FETCHMAIL_PLUGIN_COMMIT}" "DmarcSrg=${DMARCSRG_TAG}" "Composer=${COMPOSER_VERSION}" \
    > /usr/local/share/sqmail-aio/source-versions.txt
COPY --link rootfs /
RUN chown qmailq:sqmail /var/qmail/bin/qmail-queuescan \
  && chmod 1755 /var/qmail/bin/qmail-queuescan \
  && chmod 755 /opt/bin/* \
  && chown -R www-data:www-data /var/www/html /var/www/admin/html \
  && chown -R root:root /opt/libexec /var/www/admin/lib \
  && chmod 755 /opt /opt/libexec /opt/libexec/delivery-admin /opt/libexec/delivery-admin-init /var/www/admin/lib \
  && chmod 644 /var/www/admin/lib/delivery.php \
  && chown root:root /etc/sudoers.d/delivery-admin \
  && chmod 440 /etc/sudoers.d/delivery-admin \
  && /usr/sbin/visudo -cf /etc/sudoers.d/delivery-admin \
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
