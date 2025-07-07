#!/usr/bin/bash

LOCAL_VERSION=$(cat /var/qmail/control/aio-conf/sqmail_aio_version 2>/dev/null)
if [ "${LOCAL_VERSION}" == "${SQMAIL_AIO_VERSION}" ]; then
	exit 0
fi

function up_1.3_to_1.4 {
    echo "Upgrading S/QMAIL AIO to 1.4"
	. /var/qmail/control/roundcube.conf
	mkdir -p /var/qmail/control/aio-conf
	cat > /var/qmail/control/aio-conf/mysql.conf << EOF
export MYSQL_USER=${MYSQL_USER}
export MYSQL_PASS=${MYSQL_PASS}
export MYSQL_DB=${MYSQL_DB}
export MYSQL_HOST=${MYSQL_HOST}
EOF
	mv /var/qmail/control/roundcube.conf /var/qmail/control/aio-conf/roundcube.conf

	cat > /var/qmail/control/aio-conf/fetchmail.conf << EOF
\$db_host='${MYSQL_HOST}';
\$db_name='${MYSQL_DB}';
\$db_username='${MYSQL_USER}';
\$db_password='${MYSQL_PASS}';
EOF
	cat /opt/sql/fetchmail.sql | mysql -h ${MYSQL_HOST} -u ${MYSQL_USER} -p"${MYSQL_PASS}" ${MYSQL_DB}
}

function up_1.4_to_1.5 {
    echo "Upgrading S/QMAIL AIO to 1.5"
	. /var/qmail/control/aio-conf/mysql.conf

    cat > /var/qmail/control/aio-conf/mysql.php << EOF
<?php
\$MYSQL_CONF = [
    'MYSQL_USER' => "${MYSQL_USER}",
    'MYSQL_PASS' => "${MYSQL_PASS}",
    'MYSQL_DB' => '${MYSQL_DB}',
    'MYSQL_HOST' => "${MYSQL_HOST}",
];
EOF

    cat << 'EOF' | mysql -h ${MYSQL_HOST} -u ${MYSQL_USER} -p"${MYSQL_PASS}" ${MYSQL_DB}
ALTER TABLE `valias` ADD `valias_type` TINYINT NULL DEFAULT '1' COMMENT '1=forwarder 0=lda' FIRST;
ALTER TABLE `valias` ADD `id` INT NULL AUTO_INCREMENT FIRST, ADD PRIMARY KEY (`id`);
ALTER TABLE `valias` ADD `copy` TINYINT NULL DEFAULT '0' COMMENT '0=redirect 1=copy&redirect' AFTER `valias_line`;
ALTER TABLE `valias` ADD INDEX (alias, domain, valias_type);
EOF

    /opt/bin/upgrade/forward_sieves2valias.php
}

function up_1.5_to_1.6 {
    echo "Upgrading S/QMAIL AIO to 1.6"
    . /var/qmail/control/aio-conf/mysql.conf

    cat /opt/sql/dmarc.sql | mysql -h ${MYSQL_HOST} -u ${MYSQL_USER} -p"${MYSQL_PASS}" ${MYSQL_DB}

	sed -i '/MYSQL_/d' /var/qmail/control/aio-conf/roundcube.conf
    rm -f /var/qmail/control/aio-conf/fetchmail.conf
    rm -f /var/qmail/control/spamassassin_sql.cf
}

function up_1.6_to_1.7 {
    echo "Upgrading S/QMAIL AIO to 1.7"
    . /var/qmail/control/aio-conf/mysql.conf

    cat > /var/qmail/control/aio-conf/i8n.conf << EOF
export DEFAULT_LANGUAGE=${DEFAULT_LANGUAGE}
EOF

    export DEFAULT_DOMAIN=$(cat /var/qmail/control/defaultdomain)
    rm -f /ssl/dovecot-dhparam
    cat /opt/templates/dovecot-local.conf | envsubst \
          '$MYSQL_USER $MYSQL_PASS $MYSQL_HOST $MYSQL_DB $DEFAULT_DOMAIN' \
          > /var/qmail/control/dovecot-local.conf
    cat /opt/templates/dovecot-${DEFAULT_LANGUAGE}.conf >> /var/qmail/control/dovecot-local.conf
    chown root:root /var/qmail/control/dovecot-local.conf
    chmod 600 /var/qmail/control/dovecot-local.conf

    echo '|/var/qmail/bin/preline -f /usr/libexec/dovecot/deliver -d $EXT@$USER' > /var/qmail/control/defaultdelivery
    /var/vpopmail/bin/vmakedotqmail -r -A
    /var/vpopmail/bin/vmakedotqmail -A -q '|/var/qmail/bin/preline -f /usr/libexec/dovecot/deliver -d $EXT@$USER'
    
    for QMAIL_FILE in /var/vpopmail/domains/*/.qmail-default; do
      echo "|/var/qmail/bin/preline -f /usr/libexec/dovecot/deliver -d $EXT@$USER" > ${QMAIL_FILE}
      chown vpopmail:vchkpw ${QMAIL_FILE}
    done
  
    for SPAM_FOLDER in /var/vpopmail/domains/*/*/Maildir/.Spam; do
      JUNK_FOLDER=$(echo $SPAM_FOLDER | sed 's#/\.Spam#/.Junk#')
      echo "Moving ${SPAM_FOLDER} to ${JUNK_FOLDER}"
      mv "${SPAM_FOLDER}" "${JUNK_FOLDER}"
      if [ -d ${SPAM_FOLDER}.TeachNotSpam ]; then
        echo "Moving ${SPAM_FOLDER}.TeachNotSpam to ${JUNK_FOLDER}.TeachNotSpam"
        mv "${SPAM_FOLDER}.TeachNotSpam" "${JUNK_FOLDER}.TeachNotSpam"
      fi
      if [ -d ${SPAM_FOLDER}.TeachNotSpam ]; then
        echo "Moving ${SPAM_FOLDER}.TeachSpam to ${JUNK_FOLDER}.TeachSpam"
        mv "${SPAM_FOLDER}.TeachSpam" "${JUNK_FOLDER}.TeachSpam"
      fi
    done
}

if [ -z "${LOCAL_VERSION}" ]; then
	up_1.3_to_1.4
	LOCAL_VERSION="1.4"
fi

if [ "${LOCAL_VERSION}" == "1.4" ]; then
	up_1.4_to_1.5
	LOCAL_VERSION="1.5"
fi

if [ "${LOCAL_VERSION}" == "1.5" ]; then
	up_1.5_to_1.6
	LOCAL_VERSION="1.6"
fi

if [ "${LOCAL_VERSION}" == "1.6" ]; then
  if [ -z "${DEFAULT_LANGUAGE}" ]; then
    echo "!!!! Before upgrading to 1.7 DEFAULT_LANGUAGE variable must set !!!!";
    exit 1
  fi
  if [ "${DEFAULT_LANGUAGE}" != "en" ] && [ "${DEFAULT_LANGUAGE}" != "fr" ] && [ "${DEFAULT_LANGUAGE}" != "it" ]; then
    echo "!!!! DEFAULT_LANGUAGE must be en, fr or it !!!!";
    exit 1
  fi
  
	up_1.6_to_1.7
	LOCAL_VERSION="1.7"
fi

echo -n "${SQMAIL_AIO_VERSION}" > /var/qmail/control/aio-conf/sqmail_aio_version

exit 0
