# Agent Guidelines

## Scope and Architecture

These instructions apply to the entire repository.

SQMail All-In-One builds a Docker mail-server image, not a standalone web
application. The image combines S/QMail, vpopmail, Dovecot/Pigeonhole,
SpamAssassin, ClamAV, Fetchmail, Roundcube, web administration, and s6
supervision. It requires an external MySQL/MariaDB database.

- `Dockerfile` is the source of truth for dependency versions, build options,
  system users, ownership, and installed paths. It currently uses Debian
  trixie-slim, PHP 8.5 from Sury, and Dovecot 2.4. Do not assume README version tables
  are fully synchronized with it.
- `rootfs/` is copied onto `/` inside the image. Repository paths under this
  directory map directly to absolute container paths.
- `rootfs/opt/bin/` contains initialization, administration, and maintenance
  scripts. `entrypoint.sh` performs startup preparation and invokes migrations;
  `init.sh` is the separate interactive setup wizard.
- `rootfs/opt/bin/upgrade/` contains persisted-data and configuration migrations.
- `rootfs/service/<name>/run` and `log/run` define s6 services and logging.
- `rootfs/etc/` contains daemon configurations and Dovecot Sieve scripts.
- `rootfs/opt/templates/`, `rootfs/opt/i8n/`, and web `*.tpl` files provide
  generated configuration and localized messages. The spelling `i8n` is intentional.
- `rootfs/opt/sql/` contains initial database schemas.
- `rootfs/var/qmail/` contains filtering scripts and TLS environment settings.
- `rootfs/var/www/` contains admin PHP/assets and Roundcube configuration.
  Roundcube and most third-party application code are downloaded during build.
- `.github/workflows/docker.yml` builds and publishes on tags matching `*.*.*`.
  It runs `tests/dovecot-sieve.py` and the isolated `tests/mail.py` integration
  suite before publishing the same image. Keep automated regression tests outside
  `rootfs/`: `tests/` is excluded from the build context and mounted read-only for
  testing, never shipped in the image.

## Local Files and Safety

- `data/`, `sources/`, and `compose.yml` are ignored by Git. They are local
  runtime data, downloaded archives, and deployment configuration, respectively.
  Do not add them to version control or assume they exist in a fresh clone.
- Do not inspect `data/` unless explicitly needed for an authorized diagnostic
  task. It may contain mail, passwords, database settings, logs, and private keys.
  Never include their contents in documentation, patches, or diagnostic output.
- Limit searches to tracked files or relevant `rootfs/` subdirectories; avoid
  recursive searches through local mail data and dependency archives.
- The local Compose setup is not a portable test fixture. It may reference
  existing data, external networks, host-specific mounts, and published mail ports.
  Do not run `docker compose up` against it merely to validate a change.
- Never execute runtime scripts directly on the host. Their absolute paths,
  ownership changes, SQL operations, and queue maintenance target a container.
- Use disposable volumes, synthetic mail, and a separate database for runtime
  tests. Do not reset queues, import schemas, run migrations, renew certificates,
  or modify real mail accounts as a routine check.
- `.dockerignore` excludes local runtime data, archives, Compose and environment files. Review the build context for
  local secrets and unnecessary archives before building; Git ignore rules do
  not exclude files from Docker's build context.

## Change Conventions

- Keep changes focused and follow the surrounding file's style. Preserve script
  executable bits, service names, runtime paths, and ownership contracts.
- Respect each shebang: most administration scripts use Bash, s6 service scripts
  and `qmailctl` use POSIX shell, `qmail-queuescan` uses ksh, and Fetchmail uses
  Perl. Do not apply Bash-only syntax to POSIX shell scripts or validate ksh as Bash.
- Keep long-running s6 services in the foreground using `exec`; preserve their
  logging and privilege handling. When adding or renaming a service, also review
  the explicit service list in `rootfs/opt/bin/qmailctl` and startup permissions.
- Edit source templates rather than generated container configuration. Check
  `entrypoint.sh` and `init.sh` for the relevant generation path and explicit
  `envsubst` variable lists. Escape values for the target language or format.
- Some files are generated only when absent. A template change alone does not
  update an existing installation; consider a migration where required.
- Review initialization, migrations, SQL consumers, and templates together when
  changing database schemas, authentication, delivery paths, or configuration.
  Preserve existing installations and do not casually bump `SQMAIL_AIO_VERSION`.
- Keep `Junk` and training-folder names aligned across migrations, Sieve,
  Roundcube configuration, and `rootfs/var/qmail/bin/learnSpam`.
- Keep PHP version references aligned across the Dockerfile, PHP configuration,
  service scripts, and Lighttpd's FastCGI socket. Use Dovecot 2.4 configuration
  syntax rather than copying older 2.3 examples.
- Treat queue-admin PHP, SMTP authentication/relay rules, TLS, shell/SQL
  interpolation, and privileged wrappers as security-sensitive. Do not loosen
  permissions or introduce hardcoded secrets to make a test pass.
- Do not hand-edit bundled minified JS/CSS, source maps, or fonts for unrelated
  changes. There is no repository-level Node/Composer development workflow.
- For dependency updates, edit the Dockerfile download/build section and review
  related configuration and README documentation. `getSources.sh` is a download
  helper, not a prerequisite: the Dockerfile downloads its own dependencies.

## Temporary SRS Backport

- SQMail remains at 4.4.14, but the Dockerfile temporarily restores four SRS
  files from 4.3.25a, not from 4.4.13. The
  [4.4.13 announcement](https://www.fehcom.de/cgi-bin/ezmlm-cgi?sqmail+mss:813:202608:jpijkdebpnnffmlkecjf)
  recommends using the 4.3 SRS modules; see also the
  [SQMail mailing list](https://www.fehcom.de/cgi-bin/ezmlm-cgi?sqmail+dds:0:202609#b).
- On every SQMail version update, reevaluate this fallback: review the mailing
  list and upstream SRS fixes, run native SRS round-trip, old-token compatibility,
  and forwarding/bounce integration tests in an isolated environment. Remove the
  backport once the upstream implementation is verified; do not retain it blindly
  across future versions. Preserve existing SRS secrets and token compatibility.
- vpopmail forwards through `/opt/bin/vpopmail-inject.sh`. When updating vpopmail,
  recheck its injector arguments, delivery environment and generated headers;
  preserve normal-inject fallbacks and test the real forwarding/bounce path.

## Validation

There is no single unit-test command. Select checks for the files changed and
report exactly what ran, what passed, and what could not be tested.

From the repository root, examples of syntax-only checks are:

```sh
git diff --check
bash -n rootfs/opt/bin/entrypoint.sh
bash -n rootfs/opt/bin/init.sh
bash -n rootfs/opt/bin/upgrade/sqmail_aio_upgrade.sh
sh -n rootfs/opt/bin/qmailctl
sh -n rootfs/service/dovecot/run
ksh -n rootfs/var/qmail/bin/qmail-queuescan
php -n -l rootfs/var/www/admin/cgi/qmail-queue.php
```

Apply the appropriate check to every modified script, including extensionless
`run` and `log/run` files. Use PHP 8.5 for PHP validation. `perl -c` requires the
script's imported modules and can execute compile-time code; use the image when
host dependencies are missing. Syntax checks do not validate generated configs.

For Dockerfile or image integration changes, build with BuildKit support:

```sh
docker build --progress=plain -t sqmail-aio:dev .
```

The build downloads and compiles many dependencies, requires network access,
and can be expensive. Do not claim it succeeded without completing it.

In a disposable, initialized test container, relevant configuration checks are
`lighttpd -tt -f /etc/lighttpd/lighttpd.conf`, `php-fpm8.5 -t`, and `doveconf -n`.
They require image-specific modules and generated configuration/certificates.
Review output for secrets before sharing it. Use `s6-svstat /service/<name>`
to inspect a running service.

`/opt/bin/tester.sh <recipient_email> -doit` is an intrusive integration test,
not a safe lint command: it creates/deletes a mail user, changes SMTP rules,
restarts services, and sends normal, EICAR, and GTUBE messages. Run it only in
an explicitly approved isolated environment with a controlled recipient;
verify mail outcomes and restoration of configuration after it finishes.

`SKIP_INIT_ENV=1` bypasses entrypoint initialization and migrations when running
an explicit diagnostic command. It does not make that command harmless or
provide the configuration needed for a full runtime test. Both `SKIP_INIT_ENV`
and `DEV_MODE` are enabled by any nonempty value, including `0`.
