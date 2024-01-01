# SQMail All-In-One

![License](https://img.shields.io/github/license/semhoun/sqmail_all-in-one) ![OpenIssues](https://img.shields.io/github/issues-raw/semhoun/sqmail_all-in-one) ![Version](https://img.shields.io/github/v/tag/semhoun/sqmail_all-in-one) ![Docker Size](https://img.shields.io/docker/image-size/semhoun/sqmail_all-in-one)  ![Docker Pull](https://img.shields.io/docker/pulls/semhoun/sqmail_all-in-one)


All-in-one S/QMail server with
  - s/qmail
  - spam filter
  - dovecot (imap/pop)
  - web admin
  - Roundcube
  - Fetchmail

## Usage

#### Docker

```shell
docker run \
  --name sqmail-aio \
  --publish 80:80 \
  --publish 88:88 \
  --publish 25:25 \
  --publish 465:465 \
  --publish 587:587 \
  --publish 110:110 \
  --publish 995:995 \
  --publish 143:143 \
  --publish 993:993 \
  --volume /opt/mail_data/qcontrol:/var/qmail/control \
  --volume /opt/mail_data/ssl:/ssl \
  --volume /opt/mail_data/domains:/var/vpopmail/domains \
  --volume /opt/mail_data/vpopmail_etc:/var/vpopmail/etc \
  --volume /opt/mail_data/log:/log \
  --volume /opt/mail_data/spamassassin:/var/spamassassin \
  --volume /opt/mail_data/tmp:/var/qmail/tmp \
  --volume /opt/mail_data/qusers:/var/qmail/users \
  --volume /opt/mail_data/queue:/var/qmail/queue \
  --volume /opt/mail_data/qalias:/var/qmail/alias \
  --volume /opt/mail_data/domainkeys:/var/qmail/ssl/domainkeys
  semhoun/sqmail_all-in-one
```
#### Docker Compose
```yaml
version: '3.8'

services:
  sqmail-aio:
    image: semhoun/sqmail_all-in-one
    volumes:
      - ./data/qcontrol:/var/qmail/control
      - ./data/ssl:/ssl
      - ./data/domains:/var/vpopmail/domains
      - ./data/vpopmail_etc:/var/vpopmail/etc
      - ./data/log:/log
      - ./data/spamassassin:/var/spamassassin
      - ./data/tmp:/var/qmail/tmp
      - ./data/qusers:/var/qmail/users
      - ./data/queue:/var/qmail/queue
      - ./data/qalias:/var/qmail/alias
      - ./data/domainkeys:/var/qmail/ssl/domainkeys
    ports:
      - 80:80
      - 88:88
      - 443:443
      - 25:25
      - 465:465
      - 587:587
      - 110:110
      - 995:995
      - 143:143
      - 993:993
```

## Initialization
### Docker
```shell
docker run \
  --rm -it \
  --env SKIP_INIT_ENV=1 \
  --volume /opt/mail_data/qcontrol:/var/qmail/control \
  --volume /opt/mail_data/ssl:/ssl \
  --volume /opt/mail_data/domains:/var/vpopmail/domains \
  --volume /opt/mail_data/vpopmail_etc:/var/vpopmail/etc \
  --volume /opt/mail_data/spamassassin:/var/spamassassin \
  --volume /opt/mail_data/qusers:/var/qmail/users \
  --volume /opt/mail_data/queue:/var/qmail/queue \
  --volume /opt/mail_data/qalias:/var/qmail/alias \
  --volume /opt/mail_data/domainkeys:/var/qmail/ssl/domainkeys
  semhoun/sqmail_all-in-one /opt/bin/init.sh
  
docker run \
  --rm -it \
  --env SKIP_INIT_ENV=1 \
  --volume ./mail_data/ssl:/ssl \
  --publish 80:80 \
  semhoun/sqmail_all-in-one /opt/bin/init-certs.sh
```
### Docker Compose
```shell
docker compose run -e SKIP_INIT_ENV=1 --rm sqmail-aio /opt/bin/init.sh
docker compose run -e SKIP_INIT_ENV=1 --rm sqmail-aio /opt/bin/init-certs.sh
```

## Docker configuration
### Environment

* `SKIP_INIT_ENV` - Skip all initialization of docker_entrypoint (like directory, spamassassin, clamav)
* `DEV_MODE` - Currently remove some clamav databases

### Volumes

* `/ssl` - SSL Certificates
* `/var/qmail/control`- QMail config files
* `/var/vpopmail/domains` - Domains (mail) data
* `/var/vpopmail/etc`- vpopmail config files 
* `/log` - Log directoy
* `/var/spamassassin`- SpamAssassin
* `/var/qmail/tmp`- QMail temporary directory (best if tmpfs)
* `/var/qmail/users` - QMail user file
* `/var/qmail/queue` - QMail queue
* `/var/qmail/alias` - QMail alias (for local users) 
* `/var/qmail/ssl/domainkeys` - Domain DKIM private and public keys

## Ports

* `80` - Webmail (roundcube) and SSL Acme certs
* `88` - HTTP admin (https and security not provided)
* `443` - SSL Webmail (roundcube)
* `25` - SMTP
* `465` - SMTPs
* `587` - Submission
* `110` - POP3
* `995` - POP3s
* `143` - IMAP
* `993` - IMAPs

## Useful File Locations
* `/ssl`/acme - Letsencrypt SSL data (remove to renew certs installation)
* `/ssl` - SSL Certificates
  * `/ssl/http.key` - Webmail Key
  * `/ssl/http.crt` - Webmail Certificate
  * `/ssl/imap.key` - IMAP Key
  * `/ssl/imap.crt` - IMAP Certificate
  * `/ssl/pop.key` - POP3 Key
  * `/ssl/pop.crt` - POP3 Certificate
  * `/ssl/smtp.key` - SMTP Key
  * `/ssl/smtp.crt` - SMTP Certificate
* `/opt/bin/init.sh` - Initialisation script
* `/opt/bin/init-certs.sh` - Certs initialisation script
* `/opt/bin/mkdkimkey.sh` - DKIM key creation
  * usage `/opt/bin/mkdkimkey.sh [-p] <domain>`
  * Print domainkey with -p, without create domain keys
  * You can split the result here: https://www.mailhardener.com/tools/dns-record-splitter
*  `/var/qmail/control/dkimdomains` - DKIM domains
  * Sending domains other than the default domain and with they own key must be added in this file
  * For more information see https://www.fehcom.de/sqmail/man/qmail-dksign.html

* `/opt/bin/tester.sh` - Check is IMAP POP SMTP Clamav and SpamAssasin was working
  * usage `tester.sh <test mail recipient> -doit`

## Built With

* qmail-autoresponder 2.0
* clamav 1.2.1
* dovecot 2.3.21
* ezmlm-idx 7.2.2
* fehQlibs 23
* fcron 3.3.1
* [qmailadmin](https://github.com/semhoun/qmailadmin)
* qmail-autoresponder 2.0
* Roundcube 1.6.4
* SpamAssassin 4.0.0
* s6 2.11.3.2
* SQMail 4.2.28
* [VPopMail](https://github.com/semhoun/vpopmail)
* [vqadmin](https://github.com/semhoun/vqadmin)
* acme.sh 3.0.7
* fetchmail

## Testing
### Manual SMTP
You can test the SMTP part with [Swaks](https://github.com/jetmore/swaks) 
A simpe test mail could be done with this:
```shell
swaks --to <to mail> --from <from email> --server <qmail aio host name>
```
### Auto
You can check IMAP POP SMTP Clamav and SpamAssasin configuration inside the docker with tester.sh script. A valid mail account must used (a temporay is also created for testing).
Docker must be running during the tests.
#### Docker
```shell
docker exec -it sqmail-aio /opt/bin/tester.sh <receipient email> -doit
```
#### Docker compose
```shell
docker compose exec sqmail-aio /opt/bin/tester.sh <receipient email> -doit
```

## Find Me

* [GitHub](https://github.com/semhoun/)
* [DockerHub](https://hub.docker.com/u/semhoun)

## Authors

* **Nathanaël Semhoun** - *Docker creation* - [semhoun](https://github.com/semhoun/)


## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.

## Acknowledgments
This docker use sources and patches from

- http://cr.yp.to
- https://www.fehcom.de/sqmail/sqmail.html
- https://notes.sagredo.eu
- https://github.com/brunonymous/vpopmail
- http://skarnet.org/software/s6/index.html
- http://fcron.free.fr
- http://untroubled.org/qmail-autoresponder/