#!/usr/bin/bash

function up_1.3_to_1.4 {
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

if ! [ -f /var/qmail/control/aio-conf/sqmail_aio_version ]; then
	up_1.3_to_1.4
fi

echo -n "1.4" > /var/qmail/control/aio-conf/sqmail_aio_version
