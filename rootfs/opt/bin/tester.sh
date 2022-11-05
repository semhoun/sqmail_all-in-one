#!/bin/bash
if [ "$2" != "-doit" ]; then
    cat<<EOF

Usage: ./tester.sh <recipient mail> -doit

To run, execute this script again with "-doit" option.

EOF
    exit
fi

restoreConfig() {
  if [ -n "${QS_SENDER}" ]; then
    /var/vpopmail/bin/vdeluser ${QS_SENDER}
  fi
  if [ -f "/var/qmail/control/rules.smtpd.testerback" ]; then
    cp /var/qmail/control/rules.smtpd.testerback /var/qmail/control/rules.smtpd
    rm -f /var/qmail/control/rules.smtpd.testerback
    /opt/bin/qmailctl cdb > /dev/null
    /opt/bin/qmailctl restart > /dev/null
  fi
}

updateRules() {
	cp /var/qmail/control/rules.smtpd /var/qmail/control/rules.smtpd.testerback
	cat > /var/qmail/control/rules.smtpd  << 'EOF'
:allow,QHPSI='clamdscan',QHPSIARG1='--verbose',MFDNSCHECK='',BADMIMETYPE='',BADLOADERTYPE='M',HELOCHECK='.',TARPITCOUNT='5',TARPITDELAY='20',QMAILQUEUE='bin/qmail-queuescan'
EOF
	/opt/bin/qmailctl cdb > /dev/null
	/opt/bin/qmailctl restart > /dev/null
}

die () {
  restoreConfig
  echo $*
  exit 1
}

let TEST_ID=1;
NB_TEST=10
INBOX_MAILS=""
SPAM_MAILS=""

PATH="/var/qmail/bin:$PATH"
export PATH

RFC822_DATE=`date +%a," "%d" "%h" "%Y" "%H:%M:%S" "%z`
QS_DESC="SQMail Infrastruture Test"
QS_TITLE="SQMail AIO Test "
QS_DOMAIN="`cat /var/qmail/control/defaultdomain 2>/dev/null`"
QS_RECIP="$1"
QS_SENDER="sqmail_tester@${QS_DOMAIN}"
QS_PASSWORD=$(echo $RANDOM | md5sum | head -c 20)
if [ "$QS_RECIP" = "" -o "$QS_DESC" = "" -o "$QS_DOMAIN" = "" ]; then
    cat<<EOF

An error has occured.

Cannot find any reference to the Q-S default domain
on your system!

Exiting....

EOF
    exit
fi
export QS_SENDER
export QS_PASSWORD
/var/vpopmail/bin/vadduser ${QS_SENDER} "${QS_PASSWORD}"

echo ""
echo "(${TEST_ID}/${NB_TEST}) Checking pop connection"
(cat<<'EOF'
log_user 0; # hide interaction, i.e. do not display to stdout
set timeout 10
match_max 100000

set server 127.0.0.1
set port 110
set user {${QS_SENDER}}
set pass {${QS_PASSWORD}}

spawn telnet $server $port
expect {
  timeout {puts stdout "timeout while connecting to $server"; exit 1}
  "+OK"
}

send "USER $user\r"
expect {
  timeout {puts stdout "timed out after login"; exit 1}
  "*ERR" {puts stdout "bad login"; exit 1}
  "+OK"
}

send "PASS $pass\r"
expect {
  timeout {puts stdout "timed out after login"; exit 1}
  "*ERR" {puts stdout "bad login"; exit 1}
  "+OK"
}

send "STAT\r"
expect {
  timeout {puts stdout "timed out after stat inbox"; exit 1}
  "*ERR" {puts stdout "could not stat inbox"; exit 1}
  "+OK"
}

send "QUIT\r"
expect {
  timeout {puts stdout "timed out after logout"; exit 1}
  "*ERR" {puts stdout "could not logout"; exit 1}
  "+OK"
}

exit
EOF
) | envsubst '$QS_SENDER $QS_PASSWORD' \
 | expect || die "Bad error."
echo "done!"
let TEST_ID++

echo ""
echo "(${TEST_ID}/${NB_TEST}) Checking pop/ssl connection"
(cat<<'EOF'
log_user 0; # hide interaction, i.e. do not display to stdout
set timeout 10
match_max 100000

set server 127.0.0.1
set port 995
set user {${QS_SENDER}}
set pass {${QS_PASSWORD}}

spawn openssl s_client -crlf -connect $server:$port
expect {
  timeout {puts stdout "timeout while connecting to $server"; exit 1}
  "+OK"
}

send "USER $user\r"
expect {
  timeout {puts stdout "timed out after login"; exit 1}
  "*ERR" {puts stdout "bad login"; exit 1}
  "+OK"
}

send "PASS $pass\r"
expect {
  timeout {puts stdout "timed out after login"; exit 1}
  "*ERR" {puts stdout "bad login"; exit 1}
  "+OK"
}

send "STAT\r"
expect {
  timeout {puts stdout "timed out after stat inbox"; exit 1}
  "*ERR" {puts stdout "could not stat inbox"; exit 1}
  "+OK"
}

send "QUIT\r"
expect {
  timeout {puts stdout "timed out after logout"; exit 1}
  "*ERR" {puts stdout "could not logout"; exit 1}
  "+OK"
}

exit
EOF
) | envsubst '$QS_SENDER $QS_PASSWORD' \
 | expect || die "Bad error."
echo "done!"
let TEST_ID++

echo ""
echo "(${TEST_ID}/${NB_TEST}) Checking imap connection"
(cat<<'EOF'
log_user 0; # hide interaction, i.e. do not display to stdout
set timeout 10
match_max 100000

set server 127.0.0.1
set port 143
set user {${QS_SENDER}}
set pass {${QS_PASSWORD}}

spawn telnet $server $port
expect {
  timeout {puts stdout "timeout while connecting to $server"; exit 1}
  "* OK"
}

send "a001 login $user $pass\r"
expect {
  timeout {puts stdout "timed out after login"; exit 1}
  "a001 NO" {puts stdout "bad login"; exit 1}
  "a001 OK"
}

send "a002 examine inbox\r"
expect {
  timeout {puts stdout "timed out after examining inbox"; exit 1}
  "a002 NO" {puts stdout "could not examine inbox"; exit 1}
  "a002 OK"
}

#parray expect_out

set buffer_to_parse $expect_out(buffer)
regexp {([0-9]+) RECENT} $buffer_to_parse -> new_msgs
#puts "new: $new_msgs"

send "a003 logout\r"
expect {
  timeout {puts stdout "timed out after logout"; exit 1}
  "a003 NO" {puts stdout "could not logout"; exit 1}
  "a003 OK"
}

exit
EOF
) | envsubst '$QS_SENDER $QS_PASSWORD' \
 | expect || die "Bad error."
echo "done!"
let TEST_ID++

echo ""
echo "(${TEST_ID}/${NB_TEST}) Checking imap/ssl connection"
(cat<<'EOF'
log_user 0; # hide interaction, i.e. do not display to stdout
set timeout 10
match_max 100000

set server 127.0.0.1
set port 993
set user {${QS_SENDER}}
set pass {${QS_PASSWORD}}

spawn openssl s_client -crlf -connect $server:$port
expect {
  timeout {puts stdout "timeout while connecting to $server"; exit 1}
  "* OK"
}

send "a001 login $user $pass\r"
expect {
  timeout {puts stdout "timed out after login"; exit 1}
  "a001 NO" {puts stdout "bad login"; exit 1}
  "a001 OK"
}

send "a002 examine inbox\r"
expect {
  timeout {puts stdout "timed out after examining inbox"; exit 1}
  "a002 NO" {puts stdout "could not examine inbox"; exit 1}
  "a002 OK"
}

#parray expect_out

set buffer_to_parse $expect_out(buffer)
regexp {([0-9]+) RECENT} $buffer_to_parse -> new_msgs
#puts "new: $new_msgs"

send "a003 logout\r"
expect {
  timeout {puts stdout "timed out after logout"; exit 1}
  "a003 NO" {puts stdout "could not logout"; exit 1}
  "a003 OK"
}

exit
EOF
) | envsubst '$QS_SENDER $QS_PASSWORD' \
 | expect || die "Bad error."
echo "done!"
let TEST_ID++

echo ""
echo "(${TEST_ID}/${NB_TEST}) Sending standard message by qmail-inject - no viruses..."
(cat<<EOF
From: $QS_DESC <$QS_SENDER>
To: $QS_DESC <$QS_RECIP>
Subject: $QS_TITLE (${TEST_ID}/${NB_TEST}) Qmail-inject test : inoffensive message
Date: $RFC822_DATE

Message (${TEST_ID}/${NB_TEST})

This is a test message. It should arrive unaffected.


EOF
)|qmail-inject -a -f "$QS_RECIP" $QS_RECIP || die "Bad error. qmail-inject died."
echo "done!"
INBOX_MAILS="${INBOX_MAILS} ${TEST_ID}"
let TEST_ID++

echo ""
echo "(${TEST_ID}/${NB_TEST}) Sending standard message by smtp - no viruses..."
(
cat<<EOF
Message (${TEST_ID}/${NB_TEST})

This is a test message. It should arrive unaffected. 
EOF
) | swaks \
  --from $QS_SENDER \
  --to $QS_RECIP \
  --server 127.0.0.1:25 \
  --h-Subject "$QS_TITLE (${TEST_ID}/${NB_TEST}) SMTP test : inoffensive message" \
  --silent  \
  --body - \
  || die "Bad error."
echo "done!"
INBOX_MAILS="${INBOX_MAILS} ${TEST_ID}"
let TEST_ID++

echo ""
echo "(${TEST_ID}/${NB_TEST}) Sending standard message by smtp with tls - no viruses..."
(
cat<<EOF
Message (${TEST_ID}/${NB_TEST})

This is a test message. It should arrive unaffected. 
EOF
) | swaks \
  --from $QS_SENDER \
  --to $QS_RECIP \
  --server 127.0.0.1:25 -tls \
  --h-Subject "$QS_TITLE (${TEST_ID}/${NB_TEST}) SMTP TLS test : inoffensive message" \
  --silent  \
  --body - \
  || die "Bad error."
echo "done!"
INBOX_MAILS="${INBOX_MAILS} ${TEST_ID}"
let TEST_ID++

echo ""
echo "(${TEST_ID}/${NB_TEST}) Sending standard message by smtpsub with tls - no viruses..."
(
cat<<EOF
Message (${TEST_ID}/${NB_TEST})

This is a test message. It should arrive unaffected. 
EOF
) | swaks \
  --from $QS_SENDER \
  --to $QS_RECIP \
  --server 127.0.0.1:587 -tls \
  --auth-user $QS_SENDER --auth-password "$QS_PASSWORD" \
  --h-Subject "$QS_TITLE (${TEST_ID}/${NB_TEST}) SMTPSub TLS test : inoffensive message" \
  --silent  \
  --body - \
  || die "Bad error."
echo "done!"
INBOX_MAILS="${INBOX_MAILS} ${TEST_ID}"
let TEST_ID++


updateRules


echo ""
echo "(${TEST_ID}/${NB_TEST}) Sending eicar test virus - should be caught by clamav..."
(
cat<<EOF
Mime-Version: 1.0
Content-Type: multipart/mixed; boundary="gKMricLos+KVdGMg"
Content-Disposition: inline
Date: $RFC822_DATE

--gKMricLos+KVdGMg
Content-Type: text/plain; charset=us-ascii
Content-Disposition: inline

Message (${TEST_ID}/${NB_TEST})

This is an example of an Email message containing a virus. It should
trigger the QHPSI system, and as such not be delivered to it's
intended recipient.

If this message is received in mailbox there is an error in clamav configuration.



--gKMricLos+KVdGMg
Content-Type: text/plain; charset=us-ascii
Content-Disposition: attachment; filename="sneaky.txt"

X5O!P%@AP[4\PZX54(P^)7CC)7}\$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!\$H+H*

--gKMricLos+KVdGMg--

EOF
) | swaks \
  --from $QS_SENDER \
  --to $QS_RECIP \
  --server 127.0.0.1:25 \
  --h-Subject "$QS_TITLE (${TEST_ID}/${NB_TEST}) viral test : checking clamav..." \
  --silent  \
  --data -
echo "done!"
let TEST_ID++

echo ""
echo "(${TEST_ID}/${NB_TEST}) Sending bad spam message for anti-spam (SpamAssassin) testing"
(cat<<EOF
Return-Path: <sb55sb55@yahoo.com>
Delivered-To: jm@netnoteinc.com
Received: from webnote.net (mail.webnote.net [193.120.211.219])
  by mail.netnoteinc.com (Postfix) with ESMTP id 09C18114095
  for <jm7@netnoteinc.com>; Mon, 19 Feb 2001 13:57:29 +0000 (GMT)
Received: from netsvr.Internet (USR-157-050.dr.cgocable.ca [24.226.157.50] (may be forged))
  by webnote.net (8.9.3/8.9.3) with ESMTP id IAA29903
  for <jm7@netnoteinc.com>; Sun, 18 Feb 2001 08:28:16 GMT
From: sb55sb55@yahoo.com
Received: from R00UqS18S (max1-45.losangeles.corecomm.net [216.214.106.173]) by netsvr.Internet with SMTP (Microsoft Exchange Internet Mail Service Version 5.5.2653.13)
  id 1429NTL5; Sun, 18 Feb 2001 03:26:12 -0500
Date: $RFC822_DATE
Message-ID: <9PS291LhupY>
Subject: $QS_TITLE (${TEST_ID}/${NB_TEST}) anti-spam test (4/4): checking SpamAssassin (There yours for FREE!)
X-Qmail-Scanner-Comment: the following XSS header should be moved
  aside by your "fast_spamassassin" install - this message should 
  NOT come out of your system with a score below 5!
X-Spam-Status: No
To: undisclosed-recipients:;

Congratulations! You have been selected to receive 2 FREE 2 Day VIP Passes to Universal Studios!

Click here http://209.61.190.180

As an added bonus you will also be registered to receive vacations discounted 25%-75%!

The following line should also trigger your SpamAssassin anti-spam system!!!!! 

For free!!!!!

XJS*C4JDBQADN1.NSBN3*2IDNEN*GTUBE-STANDARD-ANTI-UBE-TEST-EMAIL*C.34X


@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
This mailing is done by an independent marketing co.
We apologize if this message has reached you in error.
Save the Planet, Save the Trees! Advertise via E mail.
No wasted paper! Delete with one simple keystroke!
Less refuse in our Dumps! This is the new way of the new millennium
To be removed please reply back with the word "remove" in the subject line.
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@

EOF
) | swaks \
  --server 127.0.0.1:25 \
  --from $QS_SENDER \
  --to $QS_RECIP \
  --silent  \
  --data -
echo "Done!"
SPAM_MAILS="${SPAM_MAILS} ${TEST_ID}"
let TEST_ID++

restoreConfig

echo ""
echo "Finished test. Now go and check Email sent to $QS_RECIP"
echo "  - Messages${INBOX_MAILS} must be in INBOX"
echo "  - Message${SPAM_MAILS} must be detected has spam"
echo ""
