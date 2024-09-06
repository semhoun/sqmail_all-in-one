#!/bin/bash

if [ -z "$1" ] || [ -z "$2" ]; then
    cat << EOF

Usage: ./lighttpd_admin.sh <user> <password>

EOF
    exit
fi

realm='SQMail AIO Admin'
user=$1
pass=$2
printf "%s:%s:%s\n" "$user" "$realm" "$(printf "%s" "$user:$realm:$pass" | sha256sum | awk '{print $1}')" >> /var/qmail/control/lighttpd-admins.htdigest

echo "User $1 added to /var/qmail/control/lighttpd-admins.htdigest"
