#!/usr/bin/bash

set -Eeuo pipefail
trap 'echo "Migration failed at line $LINENO; the last completed checkpoint is retained." >&2' ERR
. /opt/bin/upgrade/common.sh
umask 077
exec 9>/var/qmail/control/.aio-migration.lock
flock -n 9 || { echo "Another initialization/migration is running" >&2; exit 1; }
VERSION_FILE=/var/qmail/control/aio-conf/sqmail_aio_version
[ "${SQMAIL_AIO_VERSION:-}" = 1.8 ] || { echo "Unsupported migration target" >&2; exit 1; }
LOCAL_VERSION=1.3
if [ -e "$VERSION_FILE" ] || [ -L "$VERSION_FILE" ]; then
  if [ ! -f "$VERSION_FILE" ] || [ -L "$VERSION_FILE" ]; then
    echo "Migration marker must be a regular file" >&2
    exit 1
  fi
  LOCAL_VERSION=$(cat "$VERSION_FILE")
fi
case "$LOCAL_VERSION" in
  1.3|1.4|1.5|1.6|1.7|1.8) ;;
  *) echo "Invalid or unsupported migration marker" >&2; exit 1 ;;
esac

checkpoint() {
  printf '%s\n' "$1" | atomic_write "$VERSION_FILE"
  LOCAL_VERSION=$1
}

function up_1.3_to_1.4 {
  echo "Upgrading S/QMAIL AIO to 1.4"
	if [ -e /var/qmail/control/roundcube.conf ]; then
    if [ -e /var/qmail/control/aio-conf/roundcube.conf ]; then
      cmp /var/qmail/control/roundcube.conf /var/qmail/control/aio-conf/roundcube.conf
    fi
    load_roundcube_settings /var/qmail/control/roundcube.conf
  else
    load_roundcube_settings /var/qmail/control/aio-conf/roundcube.conf
  fi
	mkdir -p /var/qmail/control/aio-conf
  printf 'export %s=%q\n' MYSQL_USER "$MYSQL_USER" MYSQL_PASS "$MYSQL_PASS" MYSQL_DB "$MYSQL_DB" MYSQL_HOST "$MYSQL_HOST" |
    atomic_write /var/qmail/control/aio-conf/mysql.conf
  if [ -e /var/qmail/control/roundcube.conf ]; then
    mv -fT /var/qmail/control/roundcube.conf /var/qmail/control/aio-conf/roundcube.conf
  fi
  mysql -h "$MYSQL_HOST" -u "$MYSQL_USER" -p"$MYSQL_PASS" "$MYSQL_DB" < /opt/sql/fetchmail.sql
  mysql -h "$MYSQL_HOST" -u "$MYSQL_USER" -p"$MYSQL_PASS" "$MYSQL_DB" -e 'SELECT src_port FROM fetchmail LIMIT 0'
}

function up_1.4_to_1.5 {
  echo "Upgrading S/QMAIL AIO to 1.5"
	. /var/qmail/control/aio-conf/mysql.conf

  export MYSQL_USER MYSQL_PASS MYSQL_DB MYSQL_HOST
  write_mysql_php
  php /opt/bin/upgrade/historical-schema.php valias

  /opt/bin/upgrade/forward_sieves2valias.php
}

function up_1.5_to_1.6 {
  echo "Upgrading S/QMAIL AIO to 1.6"
  . /var/qmail/control/aio-conf/mysql.conf

  export MYSQL_USER MYSQL_PASS MYSQL_DB MYSQL_HOST
  php /opt/bin/upgrade/historical-schema.php dmarc

  sed -i '/MYSQL_/d' /var/qmail/control/aio-conf/roundcube.conf
  rm -f /var/qmail/control/aio-conf/fetchmail.conf
  rm -f /var/qmail/control/spamassassin_sql.cf
}

function up_1.6_to_1.7 {
  echo "Upgrading S/QMAIL AIO to 1.7"
  . /var/qmail/control/aio-conf/mysql.conf

  cat << EOF | atomic_write /var/qmail/control/aio-conf/i8n.conf
export DEFAULT_LANGUAGE=${DEFAULT_LANGUAGE}
EOF

  DEFAULT_DOMAIN=$(cat /var/qmail/control/defaultdomain)
  export DEFAULT_DOMAIN
  rm -f /ssl/dovecot-dhparam
  # Retain the original configuration before this historical replacement.
  if [ -e /var/qmail/control/dovecot-local.conf ] && [ ! -e /var/qmail/control/dovecot-local.conf.pre-1.7 ]; then
    cp -p /var/qmail/control/dovecot-local.conf /var/qmail/control/dovecot-local.conf.pre-1.7
  fi
  {
    envsubst \
        '$MYSQL_USER $MYSQL_PASS $MYSQL_HOST $MYSQL_DB $DEFAULT_DOMAIN' \
        < /opt/templates/dovecot-local.conf
    cat "/opt/templates/dovecot-${DEFAULT_LANGUAGE}.conf"
  } | atomic_write /var/qmail/control/dovecot-local.conf
  chown root:root /var/qmail/control/dovecot-local.conf
  chmod 600 /var/qmail/control/dovecot-local.conf

  echo '|/var/qmail/bin/preline -f /usr/libexec/dovecot/deliver -d $EXT@$USER' | atomic_write /var/qmail/control/defaultdelivery
  chown qmaild:sqmail /var/qmail/control/defaultdelivery
  chmod 644 /var/qmail/control/defaultdelivery
  echo "${MYSQL_HOST}|3306|${MYSQL_USER}|${MYSQL_PASS}|${MYSQL_DB}" | atomic_write /var/vpopmail/etc/vpopmail.mysql
  chown vpopmail:vchkpw /var/vpopmail/etc/vpopmail.mysql
  chmod 640 /var/vpopmail/etc/vpopmail.mysql
  /var/vpopmail/bin/vmakedotqmail -r -A

  shopt -s nullglob
  for SPAM_FOLDER in /var/vpopmail/domains/*/*/Maildir/.Spam*; do
    JUNK_FOLDER="${SPAM_FOLDER%/.Spam*}/.Junk${SPAM_FOLDER##*/.Spam}"
    if [ -d "${SPAM_FOLDER}" ]; then
      if [ -e "$JUNK_FOLDER" ] || [ -L "$JUNK_FOLDER" ]; then
        echo "Maildir collision: $SPAM_FOLDER and $JUNK_FOLDER; resolve without discarding mail before retrying." >&2
        exit 1
      fi
      echo "Moving ${SPAM_FOLDER} to ${JUNK_FOLDER}"
      mv -T "${SPAM_FOLDER}" "${JUNK_FOLDER}"
    fi
  done
  
  for DOTMAIL in /var/vpopmail/domains/*/*/.qmail; do
    CONTENT=$(cat "$DOTMAIL")
    if [[ "$CONTENT" == *'/var/qmail/bin/preline -f /usr/libexec/dovecot/deliver'* ]]; then
      if [ "$(wc -l < "$DOTMAIL")" -eq 1 ]; then
          echo "Removing old sieve .qmail file ${DOTMAIL}"
          rm -f "$DOTMAIL"
      fi
    fi
  done
  
  if [ ! -e /var/qmail/control/srsdomains ]; then
    SRS_SECRET=$(openssl rand -hex 32)
    cat << EOF | atomic_write /var/qmail/control/srsdomains
*:${SRS_SECRET}|-|srs.
EOF
    chown qmaild:sqmail /var/qmail/control/srsdomains
    # Preserve the historical read contract for non-setuid SRS delivery helpers.
    chmod 644 /var/qmail/control/srsdomains
  else
    [ -s /var/qmail/control/srsdomains ] || { echo "Empty SRS configuration; refusing secret rotation" >&2; exit 1; }
  fi

}

if [ "${LOCAL_VERSION}" = 1.3 ]; then
	up_1.3_to_1.4
	checkpoint 1.4
fi

if [ "${LOCAL_VERSION}" == "1.4" ]; then
	up_1.4_to_1.5
	checkpoint 1.5
fi

if [ "${LOCAL_VERSION}" == "1.5" ]; then
	up_1.5_to_1.6
	checkpoint 1.6
fi

if [ "${LOCAL_VERSION}" == "1.6" ]; then
  if [ -z "${DEFAULT_LANGUAGE:-}" ]; then
    echo "!!!! Before upgrading to 1.7 DEFAULT_LANGUAGE variable must set !!!!";
    exit 1
  fi
  if [ "${DEFAULT_LANGUAGE}" != "en" ] && [ "${DEFAULT_LANGUAGE}" != "fr" ] && [ "${DEFAULT_LANGUAGE}" != "it" ]; then
    echo "!!!! DEFAULT_LANGUAGE must be en, fr or it !!!!";
    exit 1
  fi
  
	up_1.6_to_1.7
	checkpoint 1.7
fi

roundcube_config
if [ "$LOCAL_VERSION" = 1.7 ]; then
  . /var/qmail/control/aio-conf/mysql.conf
  export MYSQL_USER MYSQL_PASS MYSQL_DB MYSQL_HOST
  php /opt/bin/upgrade/historical-schema.php dmarc
  php /opt/bin/upgrade/roundcube-schema.php
  checkpoint 1.8
fi
[ "$LOCAL_VERSION" = "$SQMAIL_AIO_VERSION" ]

exit 0
