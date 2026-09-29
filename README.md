# SQMail All-In-One

![License](https://img.shields.io/github/license/semhoun/sqmail_all-in-one) ![OpenIssues](https://img.shields.io/github/issues-raw/semhoun/sqmail_all-in-one) ![Version](https://img.shields.io/github/v/tag/semhoun/sqmail_all-in-one) ![Docker Size](https://img.shields.io/docker/image-size/semhoun/sqmail_all-in-one) ![Docker Pull](https://img.shields.io/docker/pulls/semhoun/sqmail_all-in-one) [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/semhoun/sqmail_all-in-one)

> A Docker mail-server stack for hosting virtual domains, with webmail, filtering and administration.

## Overview

SQMail All-In-One packages SMTP, IMAP/POP3, filtering, webmail and administration in one image. s6 supervises services; an **external MySQL/MariaDB database is required**.
This repository builds a mail-server image, not a standalone PHP application.

## Tech Stack

The [Dockerfile](Dockerfile) is authoritative for versions, build options, users and installed paths.

| Component | Version / Source | Role |
|---|---|---|
| Debian / PHP | trixie-slim / PHP 8.5 from [Sury](https://packages.sury.org/php/) | Operating system and web runtime |
| [S/QMail](https://www.fehcom.de/sqmail/sqmail.html) | 4.4.14 beta | SMTP transport, DKIM and SRS |
| [vpopmail](https://github.com/sagredo-dev/vpopmail) | 5.6.14 | Virtual domains and accounts |
| [Dovecot / Pigeonhole](https://www.dovecot.org/) | 2.4.5 | IMAP, POP3, local delivery and Sieve |
| [Roundcube](https://roundcube.net/) | 1.7.4 | Webmail and ManageSieve client |
| [SpamAssassin](https://spamassassin.apache.org/) / DCC | 4.0.2 / 2.3.169 | Spam filtering |
| [ClamAV](https://www.clamav.net/) | 1.5.4 | Antivirus scanning |
| [QmailAdmin](https://github.com/sagredo-dev/qmailadmin) / [vqadmin](https://github.com/sagredo-dev/vqadmin) | 1.2.28 / 2.4.7 | Mailbox and domain administration |
| [DmarcSrg](https://github.com/liuch/dmarc-srg) | 2.3 | DMARC report viewer |
| [ezmlm-idx](https://github.com/sagredo-dev/ezmlm-idx) / [qmail-autoresponder](https://untroubled.org/qmail-autoresponder) | Pinned fork / 2.0 | Mailing lists and automatic replies |
| Fetchmail / Lighttpd | Debian packages | Remote mail retrieval and HTTP serving |
| [s6](https://github.com/skarnet/s6) / [fcron](https://github.com/yo8192/fcron) | 2.15.1.0 / 3.4.1 | Supervision and scheduled jobs |
| [acme.sh](https://github.com/acmesh-official/acme.sh) | 3.1.6 | TLS certificate management |

S/QMail uses the **4.3.25a SRS modules** temporarily, plus a local SMTP recipient-handling fix. Reevaluate the backport and run forwarding/bounce tests on upgrades.

## Architecture

Typical inbound delivery follows this path; aliases and forwarding can bypass local storage:

```text
SMTP -> S/QMail -> SpamAssassin / ClamAV -> vpopmail
vpopmail -> valias / individual .qmail / defaultdelivery
local delivery -> Dovecot LDA -> Sieve when enabled -> Maildir
Maildir -> Dovecot IMAP / POP3 -> mail clients or Roundcube
```

`rootfs/` is copied to `/` in the image. The entrypoint prepares runtime state and runs migrations before starting s6.
The setup wizard is separate; most third-party code is downloaded during the build. The delivery helper runs mailbox operations as vpopmail and keeps backups private to root.

## Project Structure

```text
Dockerfile               # Dependencies, compilation, users and installed paths
rootfs/etc/              # Daemon, PHP, Lighttpd and Dovecot configuration
rootfs/opt/bin/           # Setup, maintenance and upgrade scripts
rootfs/opt/libexec/       # Restricted delivery-administration helper
rootfs/opt/templates/     # Configuration templates used during initialization
rootfs/opt/i8n/           # Localized messages; this spelling is intentional
rootfs/opt/sql/           # Initial database schemas
rootfs/service/          # s6 service and logging scripts
rootfs/var/qmail/         # Queue filtering and TLS environment settings
rootfs/var/www/           # Administration code and Roundcube configuration
tests/                   # Host runners, disposable-container probes and fixtures
.github/workflows/       # Build, test and publish pipeline
```

Local `data/`, `sources/` and `compose.yml` are ignored deployment artifacts, not test fixtures. Never commit mail, credentials, keys or archives.

## Getting Started

### Prerequisites

- A Linux Docker host with BuildKit and the Docker Compose plugin.
- A dedicated, **empty** MySQL/MariaDB database reachable from the container on port **3306**.
- A dedicated database account with data and schema-management privileges for initialization and upgrades.
- For public mail: appropriate DNS records, reachable service ports and outbound SMTP connectivity.
- A public HTTP/HTTPS reverse proxy with separate webmail and administration hostnames; see [Administration Login](#administration-login).

Do not use the database root account or expose the database publicly. Do not import schemas before the wizard.
For a database container, configure a shared Docker network first. `localhost` refers to the mail container, not your host/database.

### Build From Source

```sh
git clone https://github.com/semhoun/sqmail_all-in-one.git
cd sqmail_all-in-one
docker build --progress=plain -t sqmail-aio:dev .
```

The build downloads and compiles dependencies. `getSources.sh` is optional; no host-side npm or Composer installation is needed.

### Configure the Deployment

Create a local `compose.yml` using this example. It uses the source-built image behind a host proxy owning public ports 80/443.
Alternatively, use a pinned release of `semhoun/sqmail_all-in-one`. Adjust database networking and publish only the protocols you need.
Route HTTP-01 to `http://127.0.0.1:8080`, webmail to `https://127.0.0.1:8443`, and administration to `http://127.0.0.1:88`. Preserve Host and the configured webmail TLS hostname.

```yaml
services:
  sqmail-aio:
    image: sqmail-aio:dev
    restart: unless-stopped
    ports:
      - "127.0.0.1:8080:80"
      - "127.0.0.1:8443:443"
      - "127.0.0.1:88:88"
      - "25:25"
      - "465:465"
      - "587:587"
      - "110:110"
      - "995:995"
      - "143:143"
      - "993:993"
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
```

### Initialize and Start

**Run the wizard only for a fresh installation. Never execute runtime scripts directly on the host.**
Reuse the same Compose project, volumes and database network. Use a private, non-recorded terminal: the wizard displays credentials.

```sh
docker compose config --quiet
docker compose run --rm -e SKIP_INIT_ENV=1 sqmail-aio /opt/bin/init.sh
docker compose run --rm --service-ports -e SKIP_INIT_ENV=1 sqmail-aio /opt/bin/init_certs.sh
docker compose up -d sqmail-aio
docker compose logs --tail=100 sqmail-aio
```

The wizard imports schemas and configures the initial domain, postmaster, administrator, service hostnames and language.
Review relay defaults to avoid unintended LAN/Docker relay access. The wizard refuses existing/partial installations; normal startup does not replace setup.

Certificate setup starts temporary Lighttpd and uses HTTP-01. All requested hostnames must resolve and be reachable on port 80.
Keep the normal service stopped and mapped ports free. The proxy must already route service-host `/.well-known/acme-challenge/` requests through host port 8080 to container port 80.
Verify issuance and certificates, not just the final banner. For renewal, preserve `/ssl/acme` and use scheduled `acme_cron.sh`, not reinitialization.

### Environment Variables

| Variable | Meaning |
|---|---|
| `SKIP_INIT_ENV` | Bypasses entrypoint preparation and migrations for explicit setup/diagnostic commands. Leave unset during normal operation. |
| `DEV_MODE` | Removes selected ClamAV databases for development. Never enable it in production. |
| `DEFAULT_LANGUAGE` | `en`, `fr` or `it`; required when crossing the historical 1.6-to-1.7 migration. Fresh setup selects and persists the language interactively. |
| `MAIL_STATS_ENABLED` | `1` by default; only `0` and `1` are valid. `0` disables statistics collection, consultation and retention purge, without deleting tables. |
| `MAIL_STATS_HISTORY_MONTHS` | `6` by default; decimal integer from `1` to `120`, in calendar months UTC. No unlimited-retention value. |

Both `SKIP_INIT_ENV` and `DEV_MODE` are enabled by **any nonempty value, including `0`**.
Database credentials and service settings are collected by the wizard, not supplied through a documented database environment-variable API.

## Volumes

Back up the external database and persistent volumes together. Preserve ownership and permissions.

| Container Path | Persistent State |
|---|---|
| `/var/qmail/control` | Configuration, credentials, migration checkpoints and private delivery backups |
| `/ssl` | Service certificates, private keys and ACME account/configuration state |
| `/var/vpopmail/domains` | Mailboxes, individual delivery rules and personal Sieve scripts |
| `/var/vpopmail/etc` | vpopmail configuration |
| `/var/qmail/users` | Virtual-domain/user assignments |
| `/var/qmail/queue` | Queued mail; persist explicitly even though it is not a Dockerfile `VOLUME` |
| `/var/qmail/alias` | Local-user aliases and SRS reverse routing; also requires explicit persistence |
| `/var/qmail/ssl/domainkeys` | DKIM private and public keys |
| `/var/spamassassin` | SpamAssassin data |
| `/log` | Service logs |

`/var/qmail/tmp` may use tmpfs; the queue must not. Do not persist `/run/sqmail-admin` session files.
Certificates use `/ssl/http.{crt,key}`, `/ssl/smtp.{crt,key}`, `/ssl/imap.{crt,key}` and `/ssl/pop.{crt,key}`.

## Ports

| Container Ports | Service |
|---|---|
| `80`, `443` | HTTP/HTTPS webmail; port 80 also handles ACME challenges |
| `88` | Internal HTTP administration backend, not a public browser endpoint |
| `25`, `465`, `587` | SMTP, implicit-TLS SMTP and submission |
| `143`, `993` | IMAP and IMAP over TLS |
| `110`, `995` | POP3 and POP3 over TLS |
| `4190` | ManageSieve listener; not published by the example |

## Administration Login

Proxy a dedicated HTTPS hostname at `/` to port 88, including `/cgi/` and `/dmarc/`. Preserve Host, disable caching; a host proxy can use `127.0.0.1:88`.
A container proxy needs a shared private network, not loopback. Never expose port 88 publicly; the container's port 443 serves **webmail**, not administration.

Existing SHA256 credentials in `/var/qmail/control/lighttpd-admins.htdigest` work with the login form, not browser HTTP authentication.
Cookies require HTTPS and use `Secure`, `HttpOnly` and `SameSite=Strict`. Forwarded identity headers cannot authenticate requests.
Sessions expire after one hour; logout or removal/replacement of the matching credential record revokes them. Runtime files stay outside the document root.
The login limiter allows ten failures per session in five minutes; a new session bypasses it. Add IP-based limiting at the proxy.

| Portal Feature | Route |
|---|---|
| Domain administration through vqadmin | `/cgi/vqadmin/vqadmin.cgi` |
| Mailbox administration through QmailAdmin | `/cgi/qmailadmin` |
| Mail queue | `/cgi/qmail-queue.php` |
| Individual delivery and Sieve | `/delivery/` |
| Statistics and service diagnostics | `/stats/` |
| DMARC reports, after setup | `/dmarc/` |
| PHP diagnostics | `/info.php` |

vqadmin enforces its own ACL using Lighttpd's authenticated `REMOTE_USER`; its default administrator is `admin`.
**Every authenticated portal user can administer every mailbox through Delivery & Sieve**, even when mailbox login is disabled.
Delivery & Sieve does not inherit vqadmin's domain ACLs. Grant portal credentials accordingly.

### Individual Delivery and Sieve

- Domains only locate users here. This feature cannot modify domain `.qmail-default`, domain catch-alls or global `defaultdelivery`.
- Each user can inherit the default, deliver locally with/without Sieve, forward, retain a local copy with/without Sieve, or discard.
- Generated executable paths are absolute. Without-Sieve delivery still uses Dovecot and retains its other plugins and quota settings.
- It does not change quota limits or enable enforcement. Individual `vdelivermail` commands are refused because they recurse.
- Changes require a diff and confirmation. Discard permanently drops mail and needs a separate acknowledgment when saving or restoring.
- Unknown/unsafe rules, empty files and ordinary comment-only files remain read-only; only the explicit discard marker is editable.
- Read-only `valias` rules take priority over individual `.qmail`. Direct Fetchmail/Dovecot delivery can bypass those `.qmail` settings.
- Native Dovecot validates Sieve. Drafts are not automatically activated; active edits require confirmation, and deactivation restores the global fallback.
- Vacation templates create separate drafts, not merged Roundcube filters. Sieve redirects and indirect forwarding loops are not analyzed.
- `default` is reserved for new/inactive drafts because native saving can activate it implicitly. Unsupported storage configurations disable writes.

Backups are root-private in `/var/qmail/control/delivery-admin-backups/`; preserve the control volume. Unsafe storage blocks writes; restored script content is not automatically reactivated.
Version checks detect observed concurrent edits but cannot coordinate atomically with QmailAdmin or ManageSieve clients.
Inspect uncertain results before retrying; there is no silent rollback over another writer's changes or SRS guarantee for Sieve redirects.

### Statistics and Journals

The existing admin portal provides transport, Dovecot, filtering, web/admin, maintenance and source-health views.
Access is global for authenticated portal administrators, not delegated by domain. Exact address/IP/account searches use POST with CSRF protection.
The web interface never launches the collector or reads mailboxes, message bodies or queue files.
Overview is an aggregate dashboard, not a log listing: top 10 envelope senders, recorded recipients, directional domain traffic and destination domains with delivery problems. Rank by message count or known message bytes; detailed events remain in the service views.
The sender and recipient panels also open complete address lists, 50 rows per page, with the same period, filters, ranking order and eligibility rules. Pagination uses protected POST cursors, never addresses in URLs. Late collection or retention purge can change rankings between requests. PDF reports remain top-10 summaries rather than exports of every address-list page.
For proven local qmail delivery, a leading prefix matching the destination domain is removed once: `example.invalid-bob@example.invalid` becomes `bob@example.invalid`. Normalization happens before recipient grouping and pagination, and also applies to searches and event/PDF details. Raw stored events and attempt links remain unchanged; senders and remote or unproven recipient addresses are not rewritten.
Received domain counts mean proven local deliveries grouped by envelope sender domain; sent counts mean remote-server acceptances grouped by destination domain. Messages/minute is the average over the entire selected period, not an instantaneous rate. Each retained message counts once per domain per direction, so retries and multiple recipients do not inflate that direction; one message may count in both directions.
Failure and deferral rankings count distinct affected messages. The categories can overlap and do not imply the destination domain caused the problem or that it remains unresolved. Rankings require retained proven links; unlinked, unknown, SRS/redacted and unsupported identities are excluded. Unknown sizes are not measured zero, and known bytes are not wire-traffic measurements.

Startup verifies the component's own schema and persists validated settings for fcron and PHP.
Collection runs every minute into `mail_stats_*` tables in the wizard's existing `MYSQL_DB`; events, correlations, aggregates and cursors use MySQL/MariaDB only.
Invalid settings or installation failures disable statistics without blocking mail startup. Installation is retried at the next startup, including on existing version-1.8 installations.
The SQL account retains its existing write/schema privileges. PHP statistics queries use read-only transactions; this is not a separate SELECT-only account or a security boundary against other PHP applications.

Retention uses `UTC_TIMESTAMP() - INTERVAL N MONTH`, not a fixed number of days.
Queries and ingestion exclude expired records; indexed, bounded purge batches also remove nominal message/attempt metadata, including unfinished messages.
The hourly bucket overlapping the cutoff is excluded, losing at most one additional hour of aggregates.
Technical cursors remain to prevent replay; they do not retain addresses or message contents.
Reducing retention irreversibly deletes older data at subsequent collections. Increasing it cannot restore purged history.
Purge can lag during a backlog, database outage or disabled collection; the portal reports its last successful completion.
Retention is **not a disk-space quota**, and does not manage original service logs or downloaded reports.

| Source | Coverage and Limits |
|---|---|
| `qmail-send`, three SMTP services | Observed queue messages, attempts/results and recognized SMTP/auth/TLS diagnostics. SMTP acceptance is distinct from delivery. |
| Dovecot and embedded LDA/Sieve traces | Recognized sessions/authentication/mail operations; an LDA trace and its qmail result are not two deliveries. |
| Spamd, ClamAV, vusaged | Recognized verdicts, daemon diagnostics and quota activity. Spam does not imply rejection; old quota logs are not current usage. |
| Lighttpd and PHP-FPM | HTTP/error diagnostics and structured delivery-admin audits; no query strings, cookies, session tokens or raw error payloads are imported. |
| Roundcube | Worker-output logging routes through PHP-FPM. SMTP/protocol/debug logs remain disabled; no debug mode is enabled for statistics. |
| QmailAdmin | Compiled auth log is routed to `/log/qmailadmin/current`, without startup truncation. Only emitted/recognized authentication events are represented. |
| Fcron and local syslog | Scheduled maintenance and future structured Fetchmail outcomes; attribution requires a verified component. The Unix-only receiver accepts selected internal emitters, not host logs. |
| DMARC report log | Mutable-table observations, not an immutable audit history. Updates/deletions between observations cannot be reconstructed. Source tables are never purged by statistics. |
| `lastauth`, `fetchmail.returned_text` | Latest-state sources only, never historical connection/collection counters. Raw fetched output is not imported. |
| Initialization/startup/migrations | Minimal structured lifecycle records in `/log/lifecycle`; no blind capture of interactive output or secrets. |

The source registry distinguishes unavailable, conditional, disabled and nonhistorical sources from an observed zero count.
Unknown lines contribute only technical parser-health information; logs are not copied wholesale into the database.
New events omit repetitive parser bookkeeping (`recognized`, `time_format`, validated `time_uncertain`) and a sub-source identical to the component. Useful outcomes, error codes, measurements and incomplete-correlation warnings remain; existing historical rows are not rewritten. The screen presents a concise diagnostic, with technical details available on demand.
New s6 records combine `t T` timestamps with the logger forced to UTC; existing rotation limits are preserved.
Legacy yearless or timezone-ambiguous records are not assigned an invented time or used to reintroduce potentially expired personal data.
Initial coverage is partial and limited to usable retained archives. Missing archives cannot always be detected, and lost history cannot be recovered.
Late changes to known, already crossed archives do not alter live correlation. Arbitrary archive restores under new file identities and byte-identical inode reuse cannot be reliably recognized.

"Observed messages" means queue observations, not incoming email. Message bytes and delivered bytes are distinct measures.
Retries are attempts, not new messages; temporary deferrals are not final failures. Remote success means acceptance by the remote server, not inbox placement or reading.
Historical queue IDs may be reused. Unproven links remain incomplete; neither matching addresses/times nor Message-ID alone proves identity across services.
SRS parent/child links are not guaranteed, and the logs are not an authoritative live queue inventory.
External database, Docker/host and reverse-proxy logs are outside coverage; no Docker socket is used.

The persistent identity is `/var/qmail/control/aio-conf/mail-stats-instance`. Preserve it with the control volume and database.
Two active containers must not share it. Local and database locks prevent overlapping collectors for one instance.
For rollback, set `MAIL_STATS_ENABLED=0` and restart; schema/data remain for reactivation and older images ignore these tables.

**PDF export:** authenticated POST exports use the same bounded query snapshot as the screen, rendered locally by Dompdf 3.1.6 with locked dependencies.
Summary reports mask personal fields; diagnostic inclusion requires an explicit choice. Tokens and secrets remain excluded in both modes.
The PDF includes the same bounded top-10 rankings, with every ranking identity (including domains) masked unless nominal diagnostic export was explicitly selected.
Reports include UTC period, instance, generation time and coverage warnings. Detailed exports refuse more than 1,000 events; category lists are capped at 50, daily series at 366 points before monthly aggregation, and documents at 60 pages.
The existing PHP-FPM service gives exports a separate local Unix-socket pool with one worker and a 30-second wall-time budget. Its termination setting is 20 seconds to allow for FPM's periodic checks; rendering also has a bounded memory budget.
No remote resources, embedded PHP/JavaScript or user-supplied HTML/URLs are rendered. Private temporary files are removed normally and orphan directories cleaned at startup.
PDF failures do not disable normal statistics views. **Downloaded PDFs are outside server retention and must be managed by their recipients.**

## Operations

Run maintenance tools **inside the initialized container**, not against host paths. Logs are under `/log/<service>`.

```sh
docker compose exec sqmail-aio s6-svstat /service/dovecot
docker compose exec sqmail-aio /opt/bin/qmailctl queue
```

| Tool / Path | Purpose |
|---|---|
| `/opt/bin/lighttpd_admin.sh` | Add a portal credential; requires username and password arguments |
| `/opt/bin/init_dmarc.sh` | Configure the DMARC mailbox/report viewer; requires email and password, then a container restart |
| `/opt/bin/mkdkimkey.sh` | Generate DKIM keys; `-p` prints the public DNS record without generating a new private key |
| `/var/qmail/control/dkimdomains` | Enable signing domains, including additional domains with their own keys |
| `/opt/bin/mksrs.sh` | Set up SRS return routing; `-p` prints DNS only, `-m` selects MX, repeated `-i` supplies public outgoing IPs |

Publish SRS MX/SPF records using `-p` before configuring without it. Secrets are retained; only external-to-external forwards are rewritten, not local deliveries or bounce senders.
DKIM references: [qmail-dksign](https://www.fehcom.de/sqmail/man/qmail-dksign.html) and [DNS record splitter](https://www.mailhardener.com/tools/dns-record-splitter).
Some legacy helpers accept or display secrets. Avoid shell history, recordings and shared logs when using them.

## Upgrade

Back up the database and mail/configuration volumes, retain the old image, and test upgrades on a copy first.
Startup runs persisted-data migrations; failures prevent normal startup. Inspect logs and repair the cause before restarting.
**Do not rerun `init.sh` for upgrades.** An image rollback alone does not restore compatible database or Dovecot storage/index state.

- **1.6 to 1.7:** set the service environment `DEFAULT_LANGUAGE` to `en`, `fr` or `it` for the first upgrade startup.
  This migration updates delivery/Dovecot configuration and renames `.Spam*` folders to `.Junk*`; collisions stop migration.
- **1.7 to 1.8:** startup migrates historical DMARC and Roundcube schemas automatically; no manual schema import is needed.

For TLS failures, check logs, DNS and HTTP-01 routing; preserve `/ssl/acme`. For permissions, follow Dockerfile/startup ownership rather than recursively relaxing access.

## Testing

Python runners and shell fixtures include mail, administration and statistics probes. Runners need Python 3 and Docker; browser tests also need Playwright/Chromium.
Use disposable containers, synthetic mail and a separate database, never the local production Compose deployment.

```sh
python3 -B tests/delivery-helper.py
python3 -B tests/admin-auth.py --image sqmail-aio:dev
docker pull mariadb:11.4
python3 -B tests/mail.py --image sqmail-aio:dev
python3 -B tests/delivery-admin.py --image sqmail-aio:dev
python3 -B tests/mail-stats-config.py
python3 -B tests/mail-stats-install.py --image sqmail-aio:dev
python3 -B tests/mail-stats-e2e.py --image sqmail-aio:dev --database-image mariadb:11.4
```

Statistics also have isolated parser, database, collector, routing, web and PDF runners under `tests/mail-stats-*`.
The database/web/collector runners accept a separate disposable MySQL 8.4 or MariaDB image; none uses the deployment database.
See [TESTING.md](TESTING.md) for Sieve, forwarding/SRS, quota, restoration, security and browser suites, plus syntax checks.
Tests are excluded from the image. `/opt/bin/tester.sh` is intrusive; it is not a lint command or a production health check.

## Building and Deployment

Promote a tested image or pin a [Docker Hub](https://hub.docker.com/r/semhoun/sqmail_all-in-one) release. Reuse mounts and database; review [Upgrade](#upgrade) first.
The [release workflow](.github/workflows/docker.yml) runs on tags matching `*.*.*`, builds with provenance, tests, then pushes the same image.
Statistics contract/database/collector checks and real mail, HTTP/PDF and isolated fcron integration run before publication.
Do not assume the `latest` tag is updated by every release. Source documentation may describe features newer than your deployed tag.

## Contributing

Fork the repository, create a focused branch, run relevant checks from [TESTING.md](TESTING.md), and submit a pull request.
Discuss major changes first and follow [AGENTS.md](AGENTS.md). Keep tests outside `rootfs/`, edit source templates, and exclude secrets and real mail.

## Authors

**Nathanaël Semhoun**, Docker creation. [GitHub](https://github.com/semhoun/) | [DockerHub](https://hub.docker.com/u/semhoun)

## License

[MIT](LICENSE.md), copyright 2020 Nathanael Semhoun. Bundled components retain their own licenses.

## Acknowledgments

Sources and patches build on work from [D. J. Bernstein](http://cr.yp.to), [S/QMail](https://www.fehcom.de/sqmail/sqmail.html),
[Sagredo](https://notes.sagredo.eu), [Bruno's vpopmail](https://github.com/brunonymous/vpopmail),
[s6](http://skarnet.org/software/s6/index.html), [fcron](http://fcron.free.fr) and [qmail-autoresponder](http://untroubled.org/qmail-autoresponder/).
