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

# Base install
RUN apt-get update \
	&& apt-get -y install build-essential dnsutils unzip git curl wget equivs bash \
    && mkdir -p /qmail-src /qmail-patches
COPY patches /qmail-patches
WORKDIR "/qmail-src"

# Add MTA Local (equivs is needed)
COPY src/mail-transport-agent.ctl /qmail-src/mail-transport-agent.ctl
RUN equivs-build mail-transport-agent.ctl \
	&& dpkg -i mta-local*.deb
	
# Fixes for slim install
RUN mkdir -p /usr/share/man/man1 /usr/share/man/man5 /usr/share/man/man7 /usr/share/man/man8 \
    && touch /usr/share/man/man1/maildirmake.1.gz \
	&& touch /usr/share/man/man8/deliverquota.8.gz \
	&& touch /usr/share/man/man1/lockmail.1.gz \
	&& touch /usr/share/man/man5/maildir.maildrop.5.gz \
	&& touch /usr/share/man/man1/lockmail.maildrop.1.gz \
	&& touch /usr/share/man/man7/maildirquota.maildrop.7.gz

########################	
# Additionnals packages
########################
RUN apt-get -y install bsd-mailx \
	libperl-dev libmariadb-dev libmariadb-dev-compat csh maildrop bzip2 razor pyzor ksh libnet-dns-perl libio-socket-inet6-perl libdigest-sha-perl libnetaddr-ip-perl libmail-spf-perl libgeo-ip-perl libnet-cidr-lite-perl libmail-dkim-perl libnet-patricia-perl libencode-detect-perl libperl-dev libssl-dev libcurl4-gnutls-dev
    
########################
# SQMail
########################
RUN mkdir -p /package \
    && chmod 1755 /package \
## fehQlibs
    && cd /qmail-src \
    && wget http://www.fehcom.de/ipnet/fehQlibs/fehQlibs-${FEHQLIBS_TAG}.tgz \
    && cd /usr/local \
    && tar xvzf /qmail-src/fehQlibs-${FEHQLIBS_TAG}.tgz \
    && mv fehQlibs-${FEHQLIBS_TAG} qlibs  \
    && cd qlibs \
    && make \
## Daemontools
    && cd /qmail-src \
    && wget http://cr.yp.to/daemontools/daemontools-${DAEMONTOOLS_TAG}.tar.gz \
    && cd /package \
    && tar xvzf /qmail-src/daemontools-${DAEMONTOOLS_TAG}.tar.gz \
    && cd admin \
    && patch -p0 < /qmail-patches/daemontools/daemontools-0.76.errno.patch \
    && patch -p0 < /qmail-patches/daemontools/daemontools-0.76-localtime.patch \
    && cd daemontools-${DAEMONTOOLS_TAG} \
    && package/install \
## ucspi-ssl    
    && cd /qmail-src \
    && wget http://www.fehcom.de/ipnet/ucspi-ssl/ucspi-ssl-${UCSPISSL_TAG}.tgz \
    && cd /package \
    && tar xvzf /qmail-src/ucspi-ssl-${UCSPISSL_TAG}.tgz \
    && cd host/superscript.com/net/ucspi-ssl-${UCSPISSL_TAG} \
    && package/install \
## ucspi-tcp6
    && cd /qmail-src \
    && wget http://www.fehcom.de/ipnet/ucspi-tcp6/ucspi-tcp6-${UCSPITCP6_TAG}.tgz \
    && cd /package \
    && tar xvzf /qmail-src/ucspi-tcp6-${UCSPITCP6_TAG}.tgz \
    && cd net/ucspi-tcp6/ucspi-tcp6-${UCSPITCP6_TAG} \
    && package/install \
## sqmail
    && cd /qmail-src \
    && wget http://www.fehcom.de/sqmail/sqmail-${SQMAIL_TAG}.tgz \
    && cd /package \
    && tar xvzf /qmail-src/sqmail-${SQMAIL_TAG}.tgz \
    && cd mail/sqmail/sqmail-${SQMAIL_TAG} \
    && package/install; echo "Otherwise return 1" \
## cleaning
    && rm -rf /qmail-src/*
    
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
    && groupadd -g 2110 vchkpw \
    && useradd -g vchkpw -u 7800 -s /usr/sbin/nologin -d /var/vpopmail vpopmail \
    && chown -R vpopmail.vchkpw /var/vpopmail \
    && wget http://downloads.sourceforge.net/project/vpopmail/vpopmail-stable/5.4.33/vpopmail-5.4.33.tar.gz \
    && tar xzf vpopmail-5.4.33.tar.gz \
    && cd vpopmail-5.4.33 \
    && patch -p1 < /qmail-patches/roberto_vpopmail-5.4.33.patch \
    && autoreconf -f -i \
    && ./configure \
        --enable-tcpserver-file=/var/qmail/control/relays.cdb \
        --enable-incdir=/usr/include/mysql \
        --enable-libdir=/usr/lib \
        --enable-qmaildir=/var/qmail/ \
        --enable-qmail-newu=/var/qmail/bin/qmail-newu \
        --enable-qmail-inject=/var/qmail/bin/qmail-inject \
        --enable-qmail-newmrh=/var/qmail/bin/qmail-newmrh \
        --disable-roaming-users \
        --enable-auth-module=mysql \
        --enable-logging=p \
        --disable-clear-passwd \
        --enable-auth-logging \
        --enable-sql-logging \
        --disable-valias \
        --disable-passwd \
        --enable-qmail-ext \
        --enable-learn-passwords \
        --enable-mysql-limits \
        --enable-sql-aliasdomains \
        --enable-defaultdelivery \
    && make \
    && make install \
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
RUN groupadd -g 2111 dovecot \
    && useradd -g dovecot -u 7801 -s /usr/sbin/nologin -d /var/run dovenull \
    && useradd -g dovecot -u 7802 -s /usr/sbin/nologin -d /var/run dovecot \
    && wget https://dovecot.org/releases/2.3/dovecot-${DOVECOT_TAG}.tar.gz \
    && tar xvzf dovecot-${DOVECOT_TAG}.tar.gz \
    && cd dovecot-${DOVECOT_TAG} \
    && ./configure \
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
    && mkdir -p /etc/dovecot/ \
# cleaning
    && rm -rf /qmail-src/*

# Binaries
COPY bin/qmail-smtpd /var/qmail/svc/qmail-smtpd/run
COPY bin/qmail-smtpsd /var/qmail/svc/qmail-smtpsd/run
COPY bin/qmail-smtpsub /var/qmail/svc/qmail-smtpsub/run
COPY bin/qmail-send /var/qmail/svc/qmail-send/run

# Messages
COPY message/quotawarn.msg /var/vpopmail/domains/quotawarn.msg
    
# Config cleaning
RUN rm -rf /service/qmail-pop3* \
    && rm -rf /var/log/qmail-pop3* \
    && cp /var/qmail/bin/sendmail /usr/sbin/sendmail \
    && rm -f /service/*/down

EXPOSE 25 465 587
EXPOSE 110 995
EXPOSE 143 993
EXPOSE 80

# Move qmail config to default config
RUN mv /var/qmail/control/ /var/qmail/control.tmpl

# Add entrypoint
COPY bin/docker-entrypoint.sh /bin/
RUN chmod +x /bin/docker-entrypoint.sh
ENTRYPOINT ["/bin/docker-entrypoint.sh"]

CMD ["/command/svscanboot"]

VOLUME ["/var/vpopmail/domains/", "/ssl", "/var/qmail/control"]
