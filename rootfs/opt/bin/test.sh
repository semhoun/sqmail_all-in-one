#!/bin/bash
#
#

#Pipe into bash if it's present

if [ "`bash --version 2>&1|grep 'GNU bash'`" != "" -a "$BASH_VERSION" = "" ]; then
    exec bash $0 $*
    exit
fi


RFC822_DATE=`date +%a," "%d" "%h" "%Y" "%H:%M:%S" "%z`


RECIP="root"

if [ "$QS_RECIP" ]; then
        RECIP="$QS_RECIP"
fi
PATH="/var/qmail/bin:$PATH"
export PATH

if [ "$QMAILQUEUE" = "" ]; then
DD="`echo $PATH|sed 's/:/ /g'`"
for path in $DD
do
  if [ -f "$path/qmail-queuescan" ]; then
    QMAILQUEUE="$path/qmail-queuescan"
    export QMAILQUEUE
  fi
done
fi


if [ "$QMAILQUEUE" = "" ]; then
    cat<<EOF

An error has occured.

Cannot find qmail-queue.scan on your system!

Exiting....

EOF
    exit
fi
QS_DESC="QMail AntiSpam Test"
QS_SENDER="`cat /var/qmail/control/defaultdomain 2>/dev/null`"
if [ "$RECIP" = "" -o "$QS_DESC" = "" -o "$QS_SENDER" = "" ]; then
    cat<<EOF

An error has occured.

Cannot find any reference to the Q-S administrator Email address in
$QMAILQUEUE on your system!

Exiting....

EOF
    exit
fi

if [ "$1" != "-doit" ]; then
    cat<<EOF

Usage: ./test_installation.sh -doit

This will simply send 3 Email messages to "$RECIP".

The first will be a "normal" message, which should be received untouched.

The third also contains the EICAR.COM test virus - but the filename is
different. It should be caught by any virus scanners.

The forth is a SPAM message. If you are running SpamAssassin  then this
message should be tagged (look for X-Spam-Status: header) as being spam.
Obviously if you filter your root mail, this won't end up in your inbox...

To run, execute this script again with "-doit" option.

EOF
    exit
fi

die () {
    echo $*
    exit 1
}


echo ""
echo "Sending standard test message - no viruses..."

export MAILFROM="$QS_SENDER"
export RCPTTO="$RECIP"
(cat<<EOF
From: Qmail-Scanner Test <$QS_SENDER>
To: Qmail-Scanner Test <$RECIP>
Subject: Qmail-Scanner test (1/3): inoffensive message
Date: $RFC822_DATE

Message 1/3

This is a test message. It should arrive unaffected.


EOF
)|qmail-inject -a -f "$RECIP" $RECIP || die "Bad error. qmail-inject died"

echo "done!"


echo ""
echo "Sending eicar test virus with altered filename - should only be caught by anti-virus modules (if you have any)..."

export MAILFROM="$QS_SENDER"
export RCPTTO="$RECIP"
(
cat<<EOF
From: Qmail-Queue.Scan Test <$QS_SENDER>
To: Qmail-Queue.Scan Test <$RECIP>
Subject: Qmail-Queue.Scan viral test (2/3): checking non-perlscanner AV...
Mime-Version: 1.0
Content-Type: multipart/mixed; boundary="gKMricLos+KVdGMg"
Content-Disposition: inline
Date: $RFC822_DATE

--gKMricLos+KVdGMg
Content-Type: text/plain; charset=us-ascii
Content-Disposition: inline

Message 3/4

This is an example of an Email message containing a virus. It should
trigger the Qmail-Queue.Scan system IF you have an anti virus scanner
installed. Note that this may fail on some AV packages if they decide
that the EICAR test virus must have a filename of "eicar.com".

If it is caught by AV software, it will not be delivered to it's
intended recipient.

--gKMricLos+KVdGMg
Content-Type: text/plain; charset=us-ascii
Content-Disposition: attachment; filename="sneaky.txt"

X5O!P%@AP[4\PZX54(P^)7CC)7}\$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!\$H+H*

--gKMricLos+KVdGMg--

EOF
)|qmail-inject -a -f "$RECIP" $RECIP || echo "Normal error. qmail-inject died because virus was detected"

echo ""
echo "Sending bad spam message for anti-spam testing - In case you are using SpamAssassin..."

export MAILFROM="sb55sb55@yahoo.com"
export RCPTTO="$RECIP"
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
Subject: Qmail-Queue.Scan anti-spam test (3/3): checking SpamAssassin [if present] (There yours for FREE!)
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
)|qmail-inject -a -f "$RECIP" $RECIP || echo "Normal error. qmail-inject died because spam was detected"

echo "Done!"

echo ""
echo "Finished test. Now go and check Email sent to $RECIP"
echo ""
