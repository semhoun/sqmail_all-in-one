#!/bin/bash

set -e

if [ ! -f "/var/qmail/control/docker_config_done" ]; then
    # QMAIL
    echo "${QMAIL_NB_REMOTE}" > /var/qmail/control/concurrencyremote
    echo -n "${QMAIL_NB_INCOMING}" > /var/qmail/control/concurrencyincoming
    
    # VPopmail
    echo "default_quota ${VPOPMAIL_QUOTA}" > /var/vpopmail/etc/vlimits.default
    echo "${VPOPMAIL_MYSQL_HOST}|0|${VPOPMAIL_MYSQL_USER}|${VPOPMAIL_MYSQL_PASS}|${VPOPMAIL_MYSQL_DB}" > /var/vpopmail/etc/vpopmail.mysql
    echo "${VPOPMAIL_DEFAULT_DOMAIN}" > /var/vpopmail/etc/defaultdomain
    chown 644 /var/vpopmail/etc/*
    
    # Dovecot
    openssl dhparam -out /etc/dovecot/dh.pem 2048
fi

$@