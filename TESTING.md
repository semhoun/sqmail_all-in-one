# Testing SQMail All-In-One

The automated tests use synthetic messages and disposable containers. They are
kept in `tests/`, excluded from the Docker build context and mounted read-only
when needed. They are not part of the final mail-server image.

## Before You Start

- Run the commands below from the repository root, using a POSIX shell.
- Docker with BuildKit support is required. The mail integration runner also needs Python 3 on the host; no third-party Python packages are required.
- Never attach production volumes, use real accounts or run these tests through the local deployment's Compose file.
- Container tests deliberately alter their own configuration, accounts or binaries. Use a fresh container for each command.
- Rebuild the image after changing runtime code. Mounting `tests/` does not replace the code installed in the image.

Build the image once:

```shell
docker build --progress=plain -t sqmail-aio:dev .
```

The build downloads and compiles dependencies and can take some time. Review
`.dockerignore` before building; Git ignore rules do not control Docker's build
context.

## Dovecot and Sieve

```shell
docker run --rm --network none --ulimit core=0 --entrypoint python3 \
  -e SQMAIL_DISPOSABLE_TEST=1 \
  --mount "type=bind,src=$PWD/tests,dst=/tests,readonly" \
  sqmail-aio:dev /tests/dovecot-sieve.py
```

This runs seven test groups against the installed Dovecot/Pigeonhole binaries:

| Group | Checks |
|-------|--------|
| Default filters | Spam goes to `Junk`, clean mail reaches INBOX, matching discard rules remove only the intended message. |
| Personal filters | A personal script overrides the default; global includes execute. |
| Regular expressions | Matching and nonmatching inputs with 7, 8 and 10 capture groups. |
| Invalid scripts | Compilation fails normally, delivery falls back safely, and valid delivery works afterward. Includes the malformed `global` command regression. |
| Compiled cache | A corrupt Sieve cache is rebuilt from its valid source. |
| IMAP operations | APPEND, COPY, MOVE and flag changes preserve message contents and the expected number of copies. |
| ManageSieve | Upload, activate, list, deactivate and delete a filter, checking its effect on real LDA delivery. |

The regex case detects a crash present in Pigeonhole 2.4.2 and fixed in 2.4.5.
The IMAP cases are useful smoke tests, but do not reproduce every condition of
the historical COPY/MOVE assertion.

The fixture uses temporary mailboxes, static authentication, loopback ManageSieve
and direct PREAUTH IMAP. It checks actual delivery, subprocess status and panic
logs, not just successful compilation. It does not test SQL authentication, TLS,
postlogin hooks or the complete generated server configuration.

## Administration Authentication

```shell
python3 tests/admin-auth.py --image sqmail-aio:dev
```

This uses real Lighttpd, PHP-FPM and vqadmin in a disposable container, without
published ports, production mounts or a database. It checks anonymous access to
every admin route family, forged identity headers, existing credentials, CSRF,
session rotation, logout, expiry, credential revocation, ordinary PHP identity and vqadmin's username
and ACL handling. It also checks session-based login throttling without blocking
the same account in another browser session.

The default command tests the installed image without network access. For a
focused development check against an older image, add `--source-overlay` to
copy the working-tree authentication files and install the magnet module if
missing. This mode needs network access and does not validate the image build.

The fixture manually sends Secure cookies over loopback HTTP to simulate the
proxy-to-container hop. It does not validate browser cookie enforcement, the
external HTTPS proxy, page rendering or database-backed vqadmin operations.

## Delivery Administration

The native contracts and privileged helper use separate disposable instances
of the initialized mail fixture, with real SQL-backed vpopmail/Dovecot lookups:

```shell
python3 -B tests/delivery-helper.py
python3 -B tests/native-sieve.py --image sqmail-aio:dev
python3 -B tests/individual-qmail.py --image sqmail-aio:dev
python3 -B tests/individual-delivery-modes.py --image sqmail-aio:dev
python3 -B tests/delivery-admin.py --image sqmail-aio:dev
docker run --rm --network none --entrypoint python3 \
  -e SQMAIL_DISPOSABLE_TEST=1 \
  --mount "type=bind,src=$PWD/tests,dst=/tests,readonly" \
  sqmail-aio:dev /tests/delivery-storage.py
```

The native Sieve suite checks canonical alias-domain resolution, disabled-account
lookup, enumeration, lifecycle operations and invalid-script preservation with
UID/GID 89 and no supplementary groups. Dovecot does not resolve alias domains
through this userdb: canonicalization must precede every mailbox operation.

The individual-delivery suite sends real SMTP messages through absent, empty,
comment-only, LDA and forwarding `.qmail` files, with and without `valias`.
It checks local/external forwarding, retained copies, SRS and reverse bounces,
delivery context and command failures. The tested precedence is `valias`, then a
nonempty individual `.qmail`, then `defaultdelivery`. Empty files fall back;
comment-only files consume mail without delivery. The editor deliberately does
not turn these ambiguous existing files into templates. Forwarding proof assumes
the tested domain has SRS configured; it is not a guarantee against duplicates
after a partially successful delivery is retried.

The individual-delivery-modes suite proves the fixed Dovecot LDA option
`mail_plugins/sieve=no` bypasses an active personal filter, while normal LDA runs it.
It checks without-Sieve local copies plus external SRS forwarding and reverse bounces,
and the explicit discard marker: no local delivery, forwarding or bounce, and no
replay of discarded messages after re-enabling delivery. Generic comment-only
files remain read-only. Helper and browser tests additionally require separate
discard acknowledgment for both save and restore, and reject the removed domain
management operations and page.
The native suite verifies that disabling Sieve retains the other configured
plugins. It first preserves the shipped quota behavior, then enables enforcement
only in the disposable fixture, flushes the auth cache and recalculates usage.
Normal and without-Sieve LDA must both refuse an oversized message when that
fixture is over quota. The original configuration is restored afterward; the
application itself does not change quota limits or enforcement.

The administration suite exercises the real helper through its sudo rule and
the real PHP/Lighttpd session boundary, including stale restore previews and
concurrent native edits. It also sends real SMTP vacation messages to check
reply suppression for repeated senders, automated messages and null senders,
while retaining every original message. Backup persistence is checked after
stopping the mail container, using a fresh image instance with its volumes
mounted read-only and comparing only hashes and private metadata.
The private-storage suite refuses an
initialized mail container and checks directory ownership, symlink refusal and
idempotent creation without altering existing backup contents. The helper unit
suite is host-safe: it exercises pure parsing and temporary files, never native
mail tools or installed runtime configuration.

### Browser Workflow

The optional browser runner requires Python Playwright and its Chromium browser
(or an installed Chromium supplied with `--chromium /usr/bin/chromium`):

```shell
python3 -B tests/delivery-browser.py --image sqmail-aio:dev
```

It provisions its own mail/database fixture and a synthetic HTTPS reverse proxy
on that fixture's internal Docker network. It publishes no ports and needs host
access to the fixture container's internal IP, as on a local Linux Docker host.
It tests real Secure cookies, the operator search/edit workflow, delivery diff
confirmation, Sieve compilation failures and restoration, vacation-draft quoting,
mobile layout and keyboard entry. Self-signed certificate verification is
disabled only for this synthetic browser context. `--artifacts` can point to an
existing directory for desktop/mobile screenshots containing only synthetic data.
The proxy and browser runner are test fixtures, never production services.
Prefer the Chromium build supplied by the installed Playwright version for
reproducible visual checks.

## Mail Delivery, Spam and Antivirus

```shell
docker pull mariadb:11.4
python3 tests/mail.py --image sqmail-aio:dev
```

The runner creates its own MariaDB instance, initializes a fresh mail server
through the real setup wizard and starts the real services. It creates temporary
accounts, TLS certificates and DKIM keys. No ports are published and no
production data is mounted.

Eight scenarios are checked:

1. SMTP reception followed by IMAP retrieval of the expected message.
2. Delivery through a local alias.
3. Rejection of unauthenticated relaying.
4. Rejection of anonymous submission and incorrect passwords.
5. Authenticated submission through `qmail-remote` to a local SMTP collector.
6. GTUBE classified as spam and delivered to `Junk` when rejection is disabled.
7. GTUBE rejected with SMTP `554` when the rejection threshold is enabled.
8. A clean attachment accepted and an EICAR attachment rejected with SMTP `554`.

Content, Message-ID, attachments and duplicate delivery are checked. Clean and
EICAR attachments use the same filename and MIME type, so a filename restriction
cannot masquerade as antivirus detection. SpamAssassin's normal report wrapping
is supported, with the original message checked inside the report.

### Isolation and Dependencies

MariaDB must be available locally before running the suite. An alternative image
can be selected with `--database-image`; the default is `mariadb:11.4`.

Preparation downloads official SpamAssassin rules in a separate container with
GPG verification enabled. This step requires Internet access. The mail and
database containers then run on a new internal Docker network. Outbound test
messages go to a loopback collector, never to Internet recipients.

The runner removes its containers, anonymous volumes, rule volume and network on
completion or handled failure/interruption. Cleanup checks the run's unique
ownership label; it does not prune unrelated Docker resources. A forced kill or
Docker daemon failure can still require manual cleanup of that run's resources.

To identify leftovers, inspect the test ownership label:

```shell
docker ps -a --filter label=sqmail.mail-test
docker volume ls --filter label=sqmail.mail-test
docker network ls --filter label=sqmail.mail-test
```

Check which run owns each resource before removing it; do not use a global prune.
Failures return a nonzero status and print diagnostic output. A failure to pull
images or download signed rules is a preparation failure, not a completed mail
test.

`tests/mail-probe.py` and `tests/fixtures/mail-server.sh` are internal components
of this runner, not commands to execute against an existing mail server.

### Coverage Limits

- ClamAV is the real engine, but its test database contains a synthetic EICAR signature. This does not validate the official signature feed or its updates.
- Network-dependent reputation checks and scheduled jobs are disabled in the fixture. Public DNS, RBLs, ACME renewal and delivery to third-party providers are not tested.
- TLS uses temporary self-signed certificates; public certificate trust is not validated.
- Message absence and duplicate checks use bounded observation windows, not indefinite monitoring.
- These tests do not validate quota enforcement, browser workflows, Fetchmail or all persisted-data migrations.

## Focused Regression Tests

These checks do not require a database and are not currently run by release CI.
They modify only their disposable container. Do not combine them in a container
that you intend to keep or use for another suite.

### SRS Setup and Forwarding Wrapper

```shell
for test in mksrs vpopmail-inject; do
  docker run --rm --network none --ulimit core=0 --entrypoint bash \
    -e SQMAIL_DISPOSABLE_TEST=1 \
    --mount "type=bind,src=$PWD/tests,dst=/tests,readonly" \
    sqmail-aio:dev "/tests/$test.sh" || exit 1
done
```

`mksrs.sh` checks DNS-only output, secret preservation, routing, permissions,
conflicts, idempotence and recovery after an interrupted write.
`vpopmail-inject.sh` replaces injectors with capture stubs to check argument and
message preservation, normal-delivery fallbacks and temporary failure handling.
It is not a cryptographic SRS round-trip test.

### SMTP Recipient State

```shell
docker run --rm --network none --ulimit core=0 --entrypoint python3 \
  -e SQMAIL_DISPOSABLE_TEST=1 \
  --mount "type=bind,src=$PWD/tests,dst=/tests,readonly" \
  sqmail-aio:dev /tests/sqmail-rcptto.py
```

This uses the real SMTP daemon with a capture-only queue. It checks exact
recipient lists, multiple recipients, isolation between transactions, RSET and
preservation of the `DELIVERTO` prefix.

### Queue Scanner

```shell
docker run --rm --network none --ulimit core=0 --entrypoint sh \
  -e SQMAIL_QUEUESCAN_TEST=1 \
  --mount "type=bind,src=$PWD/tests,dst=/tests,readonly" \
  sqmail-aio:dev /tests/qmail-queuescan.sh
```

This replaces the queue, SQL client and spam client with capture stubs. It checks
exit-code propagation, recipient/profile handling and failures without submitting
unscanned messages. Use the mail integration suite to exercise the real engines.

### Advanced SRS Integration Fixture

[`tests/vpopmail-srs.py`](tests/vpopmail-srs.py) exercises real `valias`
forwarding, SRS rewriting and reverse-bounce routing. It is destructive and is
not a standalone runner: unlike `tests/mail.py`, it does not provision or clean
up its database and network.

It requires a separate internal test network with a fresh MariaDB service named
`db`, database/user `sqmail_test` and the synthetic password `SyntheticDbOnly927`.
It also needs an uninitialized mail container, a read-only `/tests` mount,
`SQMAIL_DISPOSABLE_TEST=1`, and vpopmail compiled to use the installed forwarding
wrapper. Do not run it inside the initialized mail integration fixture or a
deployment. Its synthetic DKIM header checks byte preservation, not DKIM signature
verification. It is not currently part of release CI.

## Release CI

The [Docker workflow](.github/workflows/docker.yml) runs on tags matching `*.*.*`.
It builds the image once, checks that the test mount/entrypoint paths are absent,
runs the Sieve, administration authentication, mail integration, native delivery
contracts and delivery-administration security suites, and
then pushes the tested image.
A failed check prevents the publication step. The image is not rebuilt between
testing and publication.

The runner uses Docker's containerd image store to retain provenance through
local loading and publication. Tests remain in the checkout and are mounted
read-only; `.dockerignore` excludes `tests/` from the image build context.

## Manual Diagnostics

### Swaks

Use [Swaks](https://github.com/jetmore/swaks) from a client on your isolated test
network. Adapt the server and addresses to accounts in that fixture:

```shell
swaks --to bob@examples.invalid --from sender@outside.invalid --server mail
```

### Legacy tester.sh

`/opt/bin/tester.sh` is an intrusive administration tool shipped in the image,
separate from the regression suites above. It creates and deletes a temporary
account, changes SMTP rules, restarts services, and sends normal, EICAR and GTUBE
messages. Some outcomes require manual inspection.

Use it only in an explicitly prepared, isolated test installation with a
controlled recipient. It does not create that isolation for you. For example,
if your disposable server is named `sqmail-test`:

```shell
docker exec -it sqmail-test /opt/bin/tester.sh recipient@example.test -doit
```

For a separate test-only Compose deployment, the equivalent is:

```shell
docker compose -f compose.test.yml exec sqmail-test /opt/bin/tester.sh recipient@example.test -doit
```

`compose.test.yml` is an example filename, not a supplied fixture. Never substitute
the local production Compose file. Check delivery results and restoration of the
SMTP rules after the script finishes.

## Syntax Checks

For changes that do not need a running server, use the appropriate interpreter:

```shell
git diff --check
bash -n rootfs/opt/bin/entrypoint.sh
bash -n rootfs/opt/bin/init.sh
bash -n rootfs/opt/bin/upgrade/sqmail_aio_upgrade.sh
sh -n rootfs/opt/bin/qmailctl
```

Use ksh for `qmail-queuescan`, PHP 8.5 for PHP files, and Perl with the required
modules installed. Syntax checks do not validate generated configuration, actual
delivery or migrations. Never execute runtime administration scripts on the host
as a substitute for these checks.
