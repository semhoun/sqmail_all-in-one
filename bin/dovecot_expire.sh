#!/bin/bash
#
# Author: Costel Balta
# Slightly modified by Roberto Puzzanghera
#

# Config and executables path
VPOPMAIL_MYSQL_CONFIG="/home/vpopmail/etc/vpopmail.mysql"

# Extract mysql params
HOST=$(sed -n "/#/! s/^\(.*\)|.*|.*|.*|.*/\1/p" $VPOPMAIL_MYSQL_CONFIG)
PORT=$(sed -n "/#/! s/^.*|\(.*\)|.*|.*|.*/\1/p" $VPOPMAIL_MYSQL_CONFIG)
USER=$(sed -n "/#/! s/^.*|.*|\(.*\)|.*|.*/\1/p" $VPOPMAIL_MYSQL_CONFIG)
 PWD=$(sed -n "/#/! s/^.*|.*|.*|\(.*\)|.*/\1/p" $VPOPMAIL_MYSQL_CONFIG)
  DB=$(sed -n "/#/! s/^.*|.*|.*|.*|\(.*\)/\1/p" $VPOPMAIL_MYSQL_CONFIG)

# dovecot details
DOVEADM="/usr/local/dovecot/bin/doveadm";

# Output sql to a file that we want to run
echo "USE vpopmail; select concat(pw_name,'@',pw_domain) as username from vpopmail;" > /tmp/query.sql;

# Run the query and get the results
results=`$MYSQL -h $HOST -u $USER -p$PWD -N < /tmp/query.sql`;

# Loop through each row
for row in $results
        do
        echo "Purging $row Trash and Junk mailbox..."
        # Purge expired Trash
        $DOVEADM -v expunge mailbox Trash -u $row savedbefore 90d
        # Purge expired Junk
        $DOVEADM -v expunge mailbox Junk  -u $row savedbefore 60d
done
