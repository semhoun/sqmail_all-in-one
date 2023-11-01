#********************************************************************************
# Create/Handle domainkeys for openqmail/eQmail/(net)qmail and derivatives      #
#                                                                               #
# Author: Kai Peter (parts taken from Joerg Backschues), Â©2014                  #
# Version: 0.32 -> 0.46                                                         #
# Licence: This program is  Copyright(C) Â©2015 Kai Peter.  It can be copied and #
#          modified according to the GNU GENERAL PUBLIC LICENSE (GPL) Version 2 #
#          or a later version. This software comes without any warranty.        #
#                                                                               #
# Description: Creation of domain keys and DNS TXT records for bind             #
#                                                                               #
# Addendum for s/qmail:                                                         #
#                                                                               #
# a) This version is modified for s/qmail (etc/dkimkey -> ssl/domainkeys)       #
# b) RSA and Ed25519 private/public keys are considered (-> RFC 8463)           #
# c) tinydns supports DKIM records while just providing the public key;         #
#    beware of the 'selector'; it is set to 'default'                           #
# d) Unlike previous versions, the new private key is *not* automatically       #
#    linked to a file named 'default'; but rather to                            #
#    rsa|ed25519.private_<selector> -> <selector>                               #
# e) The ed25519 public key is stripped from the ASN1 header information        #
#    This base64 encoded key is available as 'ed25519.basekey_<Selector>        #
# f) RSA and Ed25519 private keys may share the same <Selector> name.           #
#    If identical, the Ed25519 private key is linked as '<Selector>_'           #
#    to be picked up automatically by qmail-dksign for simultaneous signing.    #
#                                                                               #
# Changelog:                                                                    #
#                                                                               #
# 0.46 Fix for RSA DKIM TXT file generation, compactified TXT data.             # 
#********************************************************************************
DKDIR="/var/qmail/ssl/domainkeys"
USR="qmailq"
GRP="sqmail"
MODULUS=2048
CURVE=0
VERBOSE=0
SELECTOR="default"
DOMAIN=""
ASN1="MCowBQYDK2VwAyEA"
PRINT=0

OPENSSL=$(which openssl 2>/dev/null)
if [ $? -ne 0 ] ; then
   echo "Couldn't find openssl! Aborting!" ; exit 0 ; 
fi

showHelp() {
echo "Usage:  $(basename $0) [-hpc] [-s selector] [-m modulus] domain"
echo
echo "-h   (show this help and exit)"
echo "-v   (verbose output)"
echo "-p   (print TXT record for domain)"
echo "-s   <selector> (set the selector)"
echo "-m   <N> (set RSA modulo size; default: 2048 bits)"
echo "-c   (generate Ed25519 keys)"
echo ""
echo "RSA key generation:"
echo "=================="
echo ""
echo "     mkdkimkey -s rsa-selector domain"
echo ""
echo "Ed25519 key generation:"
echo "======================"
echo ""
echo "     mkdkimkey -c -s ed-selector domain"
echo ""
echo "Key activation:"
echo "=============="
echo "     The created private key 'rsa|ed25519.private_<selector>'"
echo "     is automatically symlinked to '<selector>'."
echo "     If included in 'control/dkimdomains', this file name"
echo "     is picked up by qmail-dksign for signing outgoing mails."
echo "     The default name for '<selector>' is 'default'."
echo "     This is implicitely assumed if no particular '<selector>' is given."
echo ""
exit 1 ; 
}

readInit() {

FLAG=""
PARAMS="vhpcs:m:"

if [ $# -gt 0 ]; then
   while getopts ${PARAMS} FLAG
   do
     case ${FLAG} in
       v) VERBOSE=1;; 
       p) PRINT=1;;
       s) SELECTOR=${OPTARG};;
       m) MODULUS=${OPTARG};;
       c) CURVE=1;;
       h) showHelp;;
       *) showHelp;;
     esac
   done
   shift $((OPTIND-1))
fi 

# Validate the input a bit ...
DOMAIN=$1 ; if [ "x${DOMAIN}" = "x"  ] ; then showHelp ; fi
# Only one argument is allowed ($1) and have to follow any other options
if [ $2 ] ; then echo "Syntax ERROR!;" showHelp ; fi

# Create main DKIM directory for keys if required

if [ ! -d ${DKDIR} ] ; then mkdir -p ${DKDIR} ; fi
}

showTXT() {
# backslashes MUST NOT be used in TXT records to quote semicolons !

cd ${DKDIR}/${DOMAIN}

echo "Domain's public key in '${DKDIR}/${DOMAIN}' used for TXT DNS record:"

echo -n "${SELECTOR}._domainkey.${DOMAIN}. IN TXT "
if [ -f rsa.public_${SELECTOR} ]; then
  key=`grep -v -e '^-' rsa.public_${SELECTOR} | tr -d '\n'`
  echo "\"v=DKIM1;k=rsa;t=y;p=${key}\""
elif [ -f ed25519.public_${SELECTOR} ]; then
  key=`grep -v -e '^-' ed25519.public_${SELECTOR} | tr -d '\n'`
  basekey=${key#${ASN1}}
  if [ `echo -n ${basekey} | wc -c | awk '{print $1}'` -eq 44 ]; then
    echo "\"v=DKIM1;k=ed25519;t=y;p=${basekey}\""
    echo ${basekey} > ed25519.basekey_${SELECTOR}
  else
    (errString="error generating Ed25519 public key" && showError; echo ${key}; echo ${basekey}; exit 1)
  fi
fi
echo -n "You need to publish this TXT record in the DNS before activating [rsa|ed25519].private_${SELECTOR} -> ${SELECTOR} for signing."

echo ; exit 0;
}

showError() {
  echo "Domainkey for domain '${DOMAIN}' with selector '${SELECTOR}' [${errString}]!";
}

###############################################################################
#  Main
###############################################################################

# Read input args; create dirs, do some validation

readInit ${@}

if [ ${PRINT} -eq 1 ]; then showTXT; fi

# Do some tests for existing keys

if [ ${VERBOSE} -eq 1 ] ; then
  if [ ${CURVE} -eq 0 ] ; then
    test -f ${DKDIR}/${DOMAIN}/rsa.private_${SELECTOR} && \
    (errString="already exists" && showError)
  else
    test -f ${DKDIR}/${DOMAIN}/ed25519.private_${SELECTOR} && \
    (errString="already exists" && showError)
  fi
fi

# Create a directory for domain and populate it with new keys
# Existing old keys are safed as 'previous'

mkdir -p ${DKDIR}/${DOMAIN}
cd ${DKDIR}/${DOMAIN}

if [ ${CURVE} -eq 0 ] ; then
  if [ -f rsa.public_${SELECTOR} ]; then
    cp rsa.public_${SELECTOR} rsa.public_${SELECTOR}.previous
    cp rsa.private_${SELECTOR} rsa.private_${SELECTOR}.previous
  fi
  ${OPENSSL} genrsa -out rsa.private_${SELECTOR} ${MODULUS}
  ${OPENSSL} rsa -in rsa.private_${SELECTOR} \
             -out rsa.public_${SELECTOR} -pubout -outform PEM
   ln -sf rsa.private_${SELECTOR} ${SELECTOR}
else
  if [ -f ed25519.public_${SELECTOR} ]; then
    cp ed25519.public_${SELECTOR}  ed25519.public_${SELECTOR}.previous
    cp ed25519.private_${SELECTOR} ed25519.private_${SELECTOR}.previous
  fi
  ${OPENSSL} genpkey -algorithm Ed25519 \
             -out ed25519.private_${SELECTOR}
  ${OPENSSL} pkey -in ed25519.private_${SELECTOR} \
             -out ed25519.public_${SELECTOR} -pubout 
  if [ -f ${SELECTOR} ]; then
    ln -sf ed25519.private_${SELECTOR} "${SELECTOR}_"
  else
    ln -sf ed25519.private_${SELECTOR} ${SELECTOR}
  fi
fi

# Set permissions

chmod 0711 ${DKDIR}
chmod 0700 ${DKDIR}/${DOMAIN}
chmod 0600 ${DKDIR}/${DOMAIN}/*
chown -R ${USR}:${GRP} ${DKDIR}

# Do some tests

if [ ${CURVE} -eq 0 ] ; then
  test -f rsa.public_${SELECTOR} || \
  (errString="does not exist" && showError)
else
  test -f ed25519.public_${SELECTOR} || \
  (errString="does not exist" && showError)
fi

# Done

[ "$?" = 0 ] && showTXT
exit 0