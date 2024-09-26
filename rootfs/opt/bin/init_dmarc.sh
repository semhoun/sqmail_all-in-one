#!/bin/bash

if [ -z "$1" ] || [ -z "$2" ]; then
    cat << EOF

Usage: ./init_dmarc.sh <email> <password>

EOF
    exit
fi

DMARC_EMAIL_ADDR="$1"
DMARC_EMAIL_PASS="$2"

echo "Creating DMARC user and configure html interface"
echo "  email: ${DMARC_EMAIL_ADDR}"
echo "  password: ${DMARC_EMAIL_PASS}"
echo ""
echo "Press Enter to continue, CTRL+C to cancel"
read dummy

echo "# Adding dmarc user"
/var/vpopmail/bin/vadduser -q "NOQUOTA" -c "DMARC" ${DMARC_EMAIL_ADDR} ${DMARC_EMAIL_PASS}

echo "# Creation dmarc config"
cat > /var/qmail/control/aio-conf/dmarc.conf << EOF
export DMARC_EMAIL_ADDR="${DMARC_EMAIL_ADDR}"
export DMARC_EMAIL_PASS="${DMARC_EMAIL_PASS}"
EOF

rm -rf /etc/fcrontab

echo "Add an entry TXT _dmarc like this to your domain:"
echo "  v=DMARC1; p=quarantine; rua=mailto:${DMARC_EMAIL_ADDR}; rua=mailto:${DMARC_EMAIL_ADDR}; fo=1; ri=86400"

echo ""
echo "--------"
echo "Please, restart this docker to activate DMARC"
