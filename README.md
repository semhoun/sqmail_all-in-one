# SQMail All-In-One

![License](https://img.shields.io/github/license/semhoun/sqmail_all-in-one) ![OpenIssues](https://img.shields.io/github/issues-raw/semhoun/sqmail_all-in-one) ![Version](https://img.shields.io/github/v/tag/semhoun/sqmail_all-in-one) ![Docker Size](https://img.shields.io/docker/image-size/semhoun/sqmail_all-in-one) ![Docker Pull](https://img.shields.io/docker/pulls/semhoun/sqmail_all-in-one) [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/semhoun/sqmail_all-in-one)


## Introduction

SQMail All-In-One is a comprehensive, Docker-based mail server solution that integrates the following components:

- **S/QMail**: A secure and efficient mail transfer agent.
- **Spam Filter**: Integrated SpamAssassin for filtering unwanted emails.
- **Dovecot**: IMAP and POP3 server for email retrieval.
- **Web Admin**: A web-based interface for managing the mail server.
- **Roundcube**: A webmail client for accessing emails via a browser.
- **Fetchmail**: A utility for retrieving emails from remote servers.

## Usage

### Docker

To run SQMail All-In-One using Docker, use the following command:
Refer to the [Ports](#ports) and [Volumes](#volumes) sections for details on the required configurations.

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
  --volume /opt/mail_data/qusers:/var/qmail/users \
  --volume /opt/mail_data/queue:/var/qmail/queue \
  --volume /opt/mail_data/qalias:/var/qmail/alias \
  --volume /opt/mail_data/domainkeys:/var/qmail/ssl/domainkeys
  semhoun/sqmail_all-in-one
```

### Docker Compose

To run SQMail All-In-One using Docker Compose, use the following configuration:
Refer to the [Ports](#ports) and [Volumes](#volumes) sections for details on the required configurations.

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

To initialize the environment and certificates, run the following commands:
Refer to the [Volumes](#volumes) section for details on the required configurations.

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
```

```shell
docker run \
  --rm -it \
  --env SKIP_INIT_ENV=1 \
  --volume ./mail_data/ssl:/ssl \
  --publish 80:80 \
  semhoun/sqmail_all-in-one /opt/bin/init-certs.sh
```

### Docker Compose

To initialize the environment and certificates using Docker Compose, run the following commands:
Refer to the [Volumes](#volumes) section for details on the required configurations.

```shell
docker compose run -e SKIP_INIT_ENV=1 --rm sqmail-aio /opt/bin/init.sh
docker compose run -e SKIP_INIT_ENV=1 --rm sqmail-aio /opt/bin/init-certs.sh
```

## Configuration

### Environment Variables

| Variable          | Description                                                                                     |
|-------------------|-------------------------------------------------------------------------------------------------|
| `SKIP_INIT_ENV`   | Skip all initialization of docker_entrypoint (e.g., directory, spamassassin, clamav).          |
| `DEV_MODE`        | Remove some ClamAV databases for development purposes.                                         |
| `DEFAULT_LANGUAGE`| Set the default language for the web interface. Valid values: `en`, `fr`, `it`. (Required for first launch) |

### Volumes

| Host Path                     | Container Path                     | Description                                      |
|-------------------------------|------------------------------------|--------------------------------------------------|
| `/ssl`                        | `/ssl`                          | SSL Certificates                                  |
| `/var/qmail/control`          | `/var/qmail/control`            | QMail configuration files                        |
| `/var/vpopmail/domains`       | `/var/vpopmail/domains`         | Domains and mail data                            |
| `/var/vpopmail/etc`           | `/var/vpopmail/etc`             | vpopmail configuration files                     |
| `/log`                        | `/log`                          | Log directory                                     |
| `/var/spamassassin`           | `/var/spamassassin`             | SpamAssassin data and configuration              |
| `/var/qmail/tmp`              | `/var/qmail/tmp`                | QMail temporary directory (best if tmpfs)        |
| `/var/qmail/users`            | `/var/qmail/users`              | QMail user files                                  |
| `/var/qmail/queue`            | `/var/qmail/queue`              | QMail queue                                       |
| `/var/qmail/alias`            | `/var/qmail/alias`              | QMail aliases for local users                    |
| `/var/qmail/ssl/domainkeys`   | `/var/qmail/ssl/domainkeys`     | Domain DKIM private and public keys              |

## Ports

| Port  | Service          | Description                                      |
|-------|------------------|--------------------------------------------------|
| `80`  | HTTP             | Webmail (Roundcube) and SSL ACME certificates    |
| `88`  | HTTP Admin       | Admin interface (HTTP only)                      |
| `443` | HTTPS            | SSL Webmail (Roundcube)                          |
| `25`  | SMTP             | Mail transfer                                    |
| `465` | SMTPS            | SMTP over SSL                                    |
| `587` | Submission       | SMTP for email clients                           |
| `110` | POP3             | Mail retrieval                                   |
| `995` | POP3S            | POP3 over SSL                                    |
| `143` | IMAP             | Mail retrieval                                   |
| `993` | IMAPS            | IMAP over SSL                                    |

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
* `/opt/bin/init_certs.sh` - Certs initialisation script
* `/opt/bin/init_dmarc.sh` - Create local dmarc user, and init web interface
  * usage `/opt/bin/init_dmarc.sh <email> <password>`
* `/opt/bin/lighttpd_admin.sh` - Add an user allowed to acces the admin web interface
  * usage `/opt/bin/lighttpd_admin.sh <user> <password>`
  * Administator user for `vqadmin` must be *admin*
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

| Component               | Version | Description                                                                                     |
|------------------------|---------|-------------------------------------------------------------------------------------------------|
| [ClamAV](https://www.clamav.net/)               | 1.5.1   | Antivirus engine for detecting threats.                                                        |
| [Dovecot](https://www.dovecot.org/)             | 2.4.1-4 | IMAP and POP3 server.                                                                          |
| ezmlm-idx               | 7.2.2   | Mailing list management tools.                                                                 |
| [fehQlibs](https://www.fehcom.de/ipnet/qlibs.html) | 29      | Libraries for QMail.                                                                           |
| [fcron](https://github.com/yo8192/fcron)         | 3.4.0   | Task scheduler.                                                                                |
| [qmailadmin](https://github.com/sagredo-dev/qmailadmin) | 1.2.27  | Web interface for managing QMail.                                                              |
| [qmail-autoresponder](https://untroubled.org/qmail-autoresponder) | 2.0     | Autoresponder for QMail.                                                                       |
| [Roundcube](https://roundcube.net/)             | 1.6.12  | Webmail client.                                                                                |
| [SpamAssassin](https://spamassassin.apache.org/) | 4.0.2   | Spam filter for email.                                                                         |
| [s6](https://github.com/skarnet/s6)             | 2.14.0.0| Process supervision suite.                                                                     |
| [SQMail](https://www.fehcom.de/)               | 4.3.25  | Secure and efficient mail transfer agent.                                                      |
| [VPopMail](https://github.com/semhoun/vpopmail) | 5.6.11  | Virtual domain management for QMail.                                                          |
| [vqadmin](https://github.com/sagredo-dev/vqadmin) | 2.4.4   | Web-based administration tool for VPopMail.                                                    |
| [acme.sh](https://github.com/acmesh-official/acme.sh) | 3.1.2   | ACME protocol client for SSL certificates.                                                     |
| fetchmail                | -       | Utility for retrieving emails from remote servers.                                             |
| [DmarcSrg](https://github.com/liuch/dmarc-srg)   | 2.3     | DMARC report generation tool.                                                                  |

## Testing

### Manual Testing

You can test the SMTP functionality using [Swaks](https://github.com/jetmore/swaks), a feature-rich SMTP test tool. Here’s an example command to send a test email:

```shell
swaks --to <recipient email> --from <sender email> --server <qmail-aio-hostname>
```

### Automated Testing

You can verify the IMAP, POP3, SMTP, ClamAV, and SpamAssassin configurations using the `tester.sh` script. A valid mail account must be used (a temporary account is created for testing). Ensure Docker is running during the tests.

#### Docker

```shell
docker exec -it sqmail-aio /opt/bin/tester.sh <recipient_email> -doit
```

#### Docker Compose

```shell
docker compose exec sqmail-aio /opt/bin/tester.sh <recipient_email> -doit
```

## Upgrade

### 1.6 to 1.7

When upgrading from version 1.6 to 1.7, you must add the `DEFAULT_LANGUAGE` environment variable at the first launch (and only at the first launch). Valid values are:
- `en` (English)
- `fr` (French)
- `it` (Italian)

Example:
```shell
docker run -e DEFAULT_LANGUAGE=en ...
```

## Troubleshooting

Here are some common issues and their solutions:

### 1. Port Conflicts
- **Issue**: Ports `80`, `443`, `25`, `465`, `587`, `110`, `995`, `143`, or `993` are already in use.
- **Solution**: Stop the service using the conflicting port or change the published ports in your Docker command. Refer to the [Ports](#ports) section for details.

### 2. SSL Certificate Issues
- **Issue**: SSL certificates are not being generated or renewed.
- **Solution**: Ensure port `80` is accessible and remove the `/ssl/acme` directory to force certificate regeneration.

### 3. Permission Issues
- **Issue**: Permission denied errors when accessing volumes.
- **Solution**: Ensure the host directories mounted as volumes have the correct permissions. Use `chmod` or `chown` to adjust permissions as needed. Refer to the [Volumes](#volumes) section for details.

### 4. Initialization Failures
- **Issue**: The initialization script (`init.sh`) fails to run.
- **Solution**: Ensure all required volumes are mounted and the `SKIP_INIT_ENV` variable is set correctly. Refer to the [Volumes](#volumes) section for details.

### 5. Mail Delivery Issues
- **Issue**: Emails are not being delivered.
- **Solution**: Check the logs in the `/log` directory for errors. Ensure DNS records (SPF, DKIM, DMARC) are correctly configured for your domain.

## Contributing

Contributions are welcome! To contribute to SQMail All-In-One:

1. Fork the repository on [GitHub](https://github.com/semhoun/sqmail_all-in-one).
2. Create a new branch for your feature or bugfix.
3. Commit your changes and push them to your fork.
4. Open a pull request with a clear description of your changes.

For major changes, please open an issue first to discuss your ideas.
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
