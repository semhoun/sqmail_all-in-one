#!/bin/bash
#
# create Domainkey
#
# Author: Joerg Backschues
# Modified by: Roberto Puzzanghera
# Modified by: Tatsuya Yokota (https://github.com/kotaroman/domainkey)
#

CONFIGDIR="/var/qmail/control/domainkeys"

# DKIMSIGNOPTIONS="-z 2" is required when 2048 bit
BIT=2048
#BIT=1024

# Number of characters to split
SPLIT=255

# Comment out this if you are going to sign at qmail-remote level
CHOWN_USER_GROUP="qmailr:sqmail"
# Comment out this if you are going to sign at qmail-smtpd level. The domainkey dir must be owned by the user who runs qmail-smtpd
#CHOWN_USER_GROUP="vpopmail:vchkpw"

if [ "$1" = "" ] ; then
    echo;
    echo "Usage: $0 [-p] domain [selector]";
    echo "       Create domainkey";
    echo "       Print domainkey with -p";
    echo;
    exit 1;
fi

function split_str () {

    DOMAIN=$1
    STR="`grep -v -e "^-" $CONFIGDIR/$DOMAIN/rsa.public_$SELECTOR | tr -d "\n"`"
    STR="v=DKIM1; k=rsa; t=y; p=${STR}"

    if [ $BIT = 2048 ]; then
        echo -n "("
    fi

    STR_COUNT=0
    while true
    do
        START=$STR_COUNT
        STR_COUNT=`expr $STR_COUNT + $SPLIT`
        LINE=${STR:$START:$SPLIT}

        if [ ${#LINE} -eq 0 ]; then
            break
        fi

        if [ $START -ne 0 ]; then
            OPTION="-e"
            if [ ${#LINE} -ne $SPLIT ]; then
                OPTION="-en"
            fi
            echo $OPTION "\t\"${LINE}\""
        else
            echo \"${LINE}\"
        fi
    done

    if [ $BIT = 2048 ]; then
        echo -n ")"
    fi
}

case "$1" in

    "-p")
    #
    # print domainkey
    #

    SELECTOR=$3

    if [ "$SELECTOR" = "" ] ; then
        SELECTOR="default"
    fi

    test -f $CONFIGDIR/$2/rsa.public_$SELECTOR || { echo; echo "Domainkey for domain \"$2\" with selector \"$SELECTOR\" does not exist."; echo; exit 1;}

    # <selector>._domainkey.<domain>. IN TXT "<domainkey>"

    echo -e "\nTXT record for BIND:"
    echo -n "$SELECTOR._domainkey.$2. IN TXT "
    split_str "$2"
    echo
    exit 0

    ;;


    *)
    #
    # create domainkey
    #

    SELECTOR=$2

    if [ "$SELECTOR" = "" ] ; then
        SELECTOR="default"
    fi

    test -f $CONFIGDIR/$1/rsa.private_$SELECTOR && { echo; echo "Domainkey for domain \"$1\" with selector \"$SELECTOR\" already exists."; echo; exit 1;}

    mkdir -p $CONFIGDIR/$1

    echo $SELECTOR > $CONFIGDIR/$1/selector

    openssl genrsa -out $CONFIGDIR/$1/rsa.private_$SELECTOR $BIT
    openssl rsa -in $CONFIGDIR/$1/rsa.private_$SELECTOR -out $CONFIGDIR/$1/rsa.public_$SELECTOR -pubout -outform PEM

    cp $CONFIGDIR/$1/rsa.private_$SELECTOR $CONFIGDIR/$1/default

    chmod 0750 $CONFIGDIR
    chmod 0750 $CONFIGDIR/$1
    chmod 0640 $CONFIGDIR/$1/*

    chown -R $CHOWN_USER_GROUP $CONFIGDIR

    # <selector>._domainkey.<domain>. IN TXT "<domainkey>"

    echo -e "\nTXT record for BIND:"
    echo -n "$SELECTOR._domainkey.$1. IN TXT "
    split_str "$1"
    echo

    exit 0
    ;;

esac
