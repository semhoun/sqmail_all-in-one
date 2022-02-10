# Description

This docker is a full qmail server with

- sqmail
- vpopmail
- dovecot



# Patch and sources

This docker use sources and patches from

- http://cr.yp.to/daemontools.html
- https://www.fehcom.de/sqmail/sqmail.html
- https://notes.sagredo.eu/ (https://notes.sagredo.eu/files/qmail/patches/)
- https://www.inter7.com/vpopmail-virtualized-email/



Current Links

https://notes.sagredo.eu/files/qmail/patches/

https://notes.sagredo.eu/en/qmail-notes-185/installing-and-configuring-vpopmail-81.html

https://wiki2.dovecot.org/HowTo/ConvertPasswordSchemes

https://notes.sagredo.eu/en/qmail-notes-185/installing-dovecot-and-sieve-on-a-vpopmail-qmail-server-28.html#sql



# Upgrade to try

- https://github.com/bruceg/qmail-autoresponder



# Docker environment config**s**

- **QMAIL_NB_REMOTE**: Max concurrency remote send (*5*)
- **QMAIL_NB_INCOMING**: Max concurrency incoming mail (*50*)
- **VPOPMAIL_QUOTA**: Default email quota (*1Go*)
- **VPOPMAIL_MYSQL_XXXX**: VPopmail mysql config
  - VPOPMAIL_MYSQL_HOST
  - VPOPMAIL_MYSQL_DB
  - VPOPMAIL_MYSQL_USER
  - VPOPMAIL_MYSQL_PASS







Now copy the startup script ro */etc/rc.d* (Slackware) or *init.d* and run it. This is a Slackware example:

```
cp contrib/rc.vusaged /etc/rc.d/
/etc/rc.d/rc.vusaged start
```



TODO:

https://notes.sagredo.eu/en/qmail-notes-185/sieve-interpreter-dovecot-managesieve-31.html