# SQMail

[![License: MIT](https://img.shields.io/badge/License-MIT-brightgreen.svg)](https://opensource.org/licenses/MIT)  ![Docker Size](https://img.shields.io/docker/image-size/semhoun/sqmail)  ![Docker Pull](https://img.shields.io/docker/pulls/semhoun/sqmail)


This docker is a full qmail server with

- sqmail
- vpopmail
- dovecot
- spamassain

## Getting Started

These instructions will cover usage information and for the docker container 

### Prerequisities


In order to run this container you'll need docker installed.

* [Windows](https://docs.docker.com/windows/started)
* [OS X](https://docs.docker.com/mac/started/)
* [Linux](https://docs.docker.com/linux/started/)

### Usage

#### Docker

```shell
docker run \
  --name sqmail \
  --publish 25:25 \
  --publish 465:465 \
  --publish 587:587 \
  --publish 110:110 \
  --publish 995:995 \
  --publish 143:143 \
  --publish 993:993 \
  --volume ./mail_data/qcontrol:/var/qmail/control \
  --volume ./mail_data/ssl:/ssl \
  --volume ./mail_data/domains:/var/vpopmail/domains \
  --volume ./mail_data/vpopmail_etc:/var/vpopmail/etc \
  --volume ./mail_data/log:/log \
  --volume ./mail_data/spamassassin:/var/spamassassin \
  --volume ./mail_data/tmp:/var/qmail/tmp \
  --volume ./mail_data/qusers:/var/qmail/users \
  semhoun/sqmail
```
#### Docker Compose
```yaml
version: '3.2'

services:
  sqmail:
    image: semhoun/sqmail
    volumes:
      - ./mail_data/qcontrol:/var/qmail/control
      - ./mail_data/ssl:/ssl
      - ./mail_data/domains:/var/vpopmail/domains
      - ./mail_data/vpopmail_etc:/var/vpopmail/etc
      - ./mail_data/log:/log
      - ./mail_data/spamassassin:/var/spamassassin
      - ./mail_data/tmp:/var/qmail/tmp
      - ./mail_data/qusers:/var/qmail/users
    ports:
      - 8090:80
      - 25:25
      - 465:465
      - 587:587
      - 110:110
      - 995:995
      - 143:143
      - 993:993
```

#### Initialization


#### Volumes

* `/your/file/location` - File location

#### Useful File Locations

* `/some/special/script.sh` - List special scripts
  
* `/magic/dir` - And also directories

## Built With

* SQMail v4.1.13
* VPopMail v5.4.33

## Find Us

* [GitHub](https://github.com/semhoun/)
* [GitLab](https://gitlab.com/semhoun/docker_sqmail)
* [DockerHub](https://hub.docker.com/repository/docker/semhoun/sqmail)

## Authors

* **Nathanaël Semhoun** - *Initial work* - [semhoun](https://gitlab.com/semhoun)


## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.

## Acknowledgments
This docker use sources and patches from

- http://cr.yp.to/daemontools.html
- https://www.fehcom.de/sqmail/sqmail.html
- https://notes.sagredo.eu/
- https://www.inter7.com/vpopmail-virtualized-email/