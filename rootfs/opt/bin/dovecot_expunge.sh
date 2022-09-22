#!/bin/bash
#

DOVEADM="/usr/local/dovecot/bin/doveadm";

$DOVEADM expunge -A mailbox Trash savedbefore 90d
$DOVEADM expunge -A mailbox Junk  savedbefore 60d
