#!/bin/bash
# Spam Assassin Bayes Training

# Learn spam!
cd /var/vpopmail/domains/semhoun.net/nathanael/Maildir/.Spam.Learn/cur
/usr/local/bin/sa-learn --spam ./*
rm -f /var/vpopmail/domains/semhoun.net/nathanael/Maildir/.Spam.Learn/cur/*
cd /var/vpopmail/domains/semhoun.net/nathanael/Maildir/.Spam.Learn/new
/usr/local/bin/sa-learn --spam ./*
rm -f /var/vpopmail/domains/semhoun.net/nathanael/Maildir/.Spam.Learn/new/*

# Learn ham!
cd /var/vpopmail/domains/semhoun.net/nathanael/Maildir/.Spam.Forget/cur
/usr/local/bin/sa-learn --ham ./*
rm -f /var/vpopmail/domains/semhoun.net/nathanael/Maildir/.Spam.Forget/cur/*
cd /var/vpopmail/domains/semhoun.net/nathanael/Maildir/.Spam.Forget/new
/usr/local/bin/sa-learn --ham ./*
rm -f /var/vpopmail/domains/semhoun.net/nathanael/Maildir/.Spam.Forget/new/*

# Update the Bayes DB 
/usr/local/bin/sa-learn --sync
