# Statistics and Journals

See the [README](README.md#statistics-and-journals) for the overview and [environment variables](README.md#environment-variables) for collection and retention settings.

## Views and Metrics

The existing admin portal provides transport, Dovecot, filtering, web/admin, maintenance and source-health views.
Access is global for authenticated portal administrators, not delegated by domain. Exact address/IP/account searches use POST with CSRF protection.
The web interface never launches the collector or reads mailboxes, message bodies or queue files.
Overview is an aggregate dashboard, not a log listing: top 10 envelope senders, recorded recipients, directional domain traffic and destination domains with delivery problems. Rank by message count or known message bytes; detailed events remain in the service views.
The sender and recipient panels also open complete address lists, 50 rows per page, with the same period, filters, ranking order and eligibility rules. Pagination uses protected POST cursors, never addresses in URLs. Late collection or retention purge can change rankings between requests. PDF reports remain top-10 summaries rather than exports of every address-list page.
For proven local qmail delivery, a leading prefix matching the destination domain is removed once: `example.invalid-bob@example.invalid` becomes `bob@example.invalid`. Normalization happens before recipient grouping and pagination, and also applies to searches and event/PDF details. Raw stored events and attempt links remain unchanged; senders and remote or unproven recipient addresses are not rewritten.
Received domain counts mean proven local deliveries grouped by envelope sender domain; sent counts mean remote-server acceptances grouped by destination domain. Messages/minute is the average over the entire selected period, not an instantaneous rate. Each retained message counts once per domain per direction, so retries and multiple recipients do not inflate that direction; one message may count in both directions.
Failure and deferral rankings count distinct affected messages. The categories can overlap and do not imply the destination domain caused the problem or that it remains unresolved. Rankings require retained proven links; unlinked, unknown, SRS/redacted and unsupported identities are excluded. Unknown sizes are not measured zero, and known bytes are not wire-traffic measurements.

## Collection

Startup verifies the component's own schema and persists validated settings for fcron and PHP.
Collection runs every minute into `mail_stats_*` tables in the wizard's existing `MYSQL_DB`; events, correlations, aggregates and cursors use MySQL/MariaDB only.
Invalid settings or installation failures disable statistics without blocking mail startup. Installation is retried at the next startup, including on existing version-1.8 installations.
The SQL account retains its existing write/schema privileges. PHP statistics queries use read-only transactions; this is not a separate SELECT-only account or a security boundary against other PHP applications.

## Retention

Retention uses `UTC_TIMESTAMP() - INTERVAL N MONTH`, not a fixed number of days.
Queries and ingestion exclude expired records; indexed, bounded purge batches also remove nominal message/attempt metadata, including unfinished messages.
The hourly bucket overlapping the cutoff is excluded, losing at most one additional hour of aggregates.
Technical cursors remain to prevent replay; they do not retain addresses or message contents.
Reducing retention irreversibly deletes older data at subsequent collections. Increasing it cannot restore purged history.
Purge can lag during a backlog, database outage or disabled collection; the portal reports its last successful completion.
Retention is **not a disk-space quota**, and does not manage original service logs or downloaded reports.

## Source Coverage

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

## Persistence and Rollback

The persistent identity is `/var/qmail/control/aio-conf/mail-stats-instance`. Preserve it with the control volume and database.
Two active containers must not share it. Local and database locks prevent overlapping collectors for one instance.
For rollback, set `MAIL_STATS_ENABLED=0` and restart; schema/data remain for reactivation and older images ignore these tables.

## PDF Reports

**PDF export:** authenticated POST exports use the same bounded query snapshot as the screen, rendered locally by Dompdf 3.1.6 with locked dependencies.
Summary reports mask personal fields; diagnostic inclusion requires an explicit choice. Tokens and secrets remain excluded in both modes.
The PDF includes the same bounded top-10 rankings, with every ranking identity (including domains) masked unless nominal diagnostic export was explicitly selected.
Reports include UTC period, instance, generation time and coverage warnings. Detailed exports refuse more than 1,000 events; category lists are capped at 50, daily series at 366 points before monthly aggregation, and documents at 60 pages.
The existing PHP-FPM service gives exports a separate local Unix-socket pool with one worker and a 30-second wall-time budget. Its termination setting is 20 seconds to allow for FPM's periodic checks; rendering also has a bounded memory budget.
No remote resources, embedded PHP/JavaScript or user-supplied HTML/URLs are rendered. Private temporary files are removed normally and orphan directories cleaned at startup.
PDF failures do not disable normal statistics views. **Downloaded PDFs are outside server retention and must be managed by their recipients.**

## Testing

Build `sqmail-aio:dev` using the [README](README.md#build-from-source) instructions. Run these commands from the repository root with Python 3 and Docker:

```sh
python3 -B tests/mail-stats-config.py
python3 -B tests/mail-stats-parsers.py
python3 -B tests/mail-stats-install.py --image sqmail-aio:dev
docker pull mariadb:11.4
python3 -B tests/mail-stats-e2e.py --image sqmail-aio:dev --database-image mariadb:11.4
```

Additional parser, database, collector, routing, web, rankings, PDF and browser runners live under `tests/mail-stats-*`.
Use only disposable containers, synthetic mail and a separate database, never production volumes or the local deployment's Compose file.
See [TESTING.md](TESTING.md) for isolation requirements and mail-fixture limitations, and the [release workflow](.github/workflows/docker.yml) for CI commands.
