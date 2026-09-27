#!/bin/bash
# Container-only fixture; tests/mail.py owns isolation and disposable volumes.
set -Eeuo pipefail
die() { printf 'Mail fixture refused: %s\n' "$*" >&2; exit 1; }
[[ -f /.dockerenv && $EUID == 0 && ${SQMAIL_DISPOSABLE_TEST:-} == 1 ]] || die 'not a disposable Docker test'
[[ ${SQMAIL_MAIL_TEST_RUN:-} =~ ^[a-zA-Z0-9-]{16,64}$ ]] || die 'missing run ID'
marker=/tmp/sqmail-mail-test-run

test_database() {
    # shellcheck disable=SC1091
    . /var/qmail/control/aio-conf/mysql.conf
    [[ $MYSQL_HOST == db && $MYSQL_DB == sqmail_test && $MYSQL_USER == sqmail_test && $MYSQL_PASS == SyntheticDbOnly927 ]] || die 'unexpected database'
}
sql() { mysql -h "$MYSQL_HOST" -u "$MYSQL_USER" -p"$MYSQL_PASS" "$MYSQL_DB" "$@"; }

if [[ ${1:-} == threshold ]]; then
    [[ $# == 2 && ( $2 == 0 || $2 == 10 ) ]] || die 'expected threshold 0 or 10'
    [[ -f $marker && ! -L $marker && $(<"$marker") == "$SQMAIL_MAIL_TEST_RUN" ]] || die 'run marker mismatch'
    test_database
    sql -e "UPDATE spam_prefs SET value='$2' WHERE username='bob@examples.invalid' AND preference='refuse_threshold'"
    exit 0
fi
[[ $# == 0 && $$ == 1 ]] || die 'bootstrap must be the container entrypoint'
[[ ! -e $marker && ! -L $marker ]] || die 'already bootstrapped'
# Refuse persisted installations before creating files, certificates, or accounts.
shopt -s nullglob dotglob
for directory in /var/qmail/control /var/vpopmail/domains /ssl /var/qmail/ssl/domainkeys; do
    [[ -d $directory && ! -L $directory ]] || die "invalid volume: $directory"
    contents=("$directory"/*)
    [[ ${#contents[@]} == 0 ]] || die "nonempty volume: $directory"
done
# vpopmail.mysql is shipped as a template even before initialization.
for file in /var/qmail/users/assign /etc/fetchmail.conf; do
    [[ ! -e $file && ! -L $file ]] || die "existing state: $file"
done
[[ -d /var/lib/spamassassin/4.000002 ]] || die 'signed SpamAssassin rules volume missing'
shopt -u nullglob dotglob

install -m 755 /tests/fixtures/mail-whiptail /usr/local/bin/whiptail
export DEFAULT_LANGUAGE=en
unset SKIP_INIT_ENV DEV_MODE
/opt/bin/init.sh
[[ $(</var/qmail/control/aio-conf/sqmail_aio_version) == "$SQMAIL_AIO_VERSION" ]] || die 'wizard did not complete'
test_database
for service in smtp imap pop http; do
    openssl req -x509 -newkey rsa:2048 -nodes -days 2 \
        -subj /CN=mail.examples.invalid \
        -addext subjectAltName=DNS:mail.examples.invalid,DNS:localhost,IP:127.0.0.1 \
        -keyout "/ssl/$service.key" -out "/ssl/$service.crt"
    chmod 600 "/ssl/$service.key"
done
chown vpopmail:vchkpw /ssl/smtp.key /ssl/smtp.crt
# A standard group avoids concurrent, slow prime generation by TLS listeners.
openssl genpkey -genparam -algorithm DH -pkeyopt group:ffdhe4096 -out /ssl/qmail-dhparam
bash /opt/bin/mkdkimkey.sh examples.invalid >/dev/null
for user in alice bob; do
    /var/vpopmail/bin/vadduser -q 20000000S "$user@examples.invalid" SyntheticMailOnly927
done
/var/vpopmail/bin/valias -i bob@examples.invalid team@examples.invalid
sql <<'SQL'
INSERT INTO spam_prefs(username,preference,value) VALUES
('bob@examples.invalid','required_score','5'),
('bob@examples.invalid','refuse_threshold','0'),
('bob@examples.invalid','dns_available','no'),
('bob@examples.invalid','skip_rbl_checks','1'),
('bob@examples.invalid','use_razor2','0'),
('bob@examples.invalid','use_pyzor','0'),
('bob@examples.invalid','use_dcc','0'),
('bob@examples.invalid','use_bayes','0'),
('bob@examples.invalid','bayes_auto_learn','0');
SQL

# Keep classification deterministic without external DNS or reputation services.
cat >> /etc/mail/spamassassin/local.cf <<'CONF'
dns_available no
skip_rbl_checks 1
use_razor2 0
use_pyzor 0
use_dcc 0
use_bayes 0
bayes_auto_learn 0
CONF

# Only this exact loopback source gets scanners without relay or DNS checks.
rules=/var/qmail/control/rules.smtpd
original=$(<"$rules")
printf '%s\n%s\n' "127.0.0.2:allow,QHPSI='clamdscan',QHPSIARG1='--no-summary',QMAILQUEUE='bin/qmail-queuescan'" "$original" > "$rules"
/opt/bin/qmailctl cdb
printf '%s\n' 'destination.invalid:127.0.0.1;2526' > /var/qmail/control/smtproutes

# Synthetic EICAR marker signature, NOT an official ClamAV feed/update test.
mkdir -p /var/lib/clamav
printf '%s\n' 'MailTest.Eicar.Synthetic:0:*:45494341522d5354414e444152442d414e544956495255532d544553542d46494c45' > /var/lib/clamav/mail-test.ndb
chmod 644 /var/lib/clamav/mail-test.ndb
# No scheduled ACME, external feed updates, or other periodic jobs.
touch /service/fcron/down
export RBLSMTPD=''
printf '%s\n' "$SQMAIL_MAIL_TEST_RUN" > "$marker"
chmod 600 "$marker"
exec /opt/bin/entrypoint.sh /bin/s6-svscan /service
