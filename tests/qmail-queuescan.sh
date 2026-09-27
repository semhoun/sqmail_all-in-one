#!/bin/sh
# Destructive fixture for a disposable, uninitialized image only:
# docker run --rm --network none --entrypoint sh -e SQMAIL_QUEUESCAN_TEST=1 \
#   -v "$PWD/tests:/tests:ro" sqmail-aio:dev /tests/qmail-queuescan.sh
set -eu
test -f /.dockerenv
test "${SQMAIL_QUEUESCAN_TEST:-}" = 1
test ! -e /var/qmail/control/aio-conf/mysql.conf
mkdir -p /var/qmail/control /var/qmail/tmp
printf 'MYSQL_USER=fixture\nMYSQL_PASS=fixture\nMYSQL_HOST=unused\nMYSQL_DB=fixture\n' > /var/qmail/control/mysql.conf
cat > /usr/bin/mysql <<'EOF'
#!/bin/sh
cat > /tmp/scanner-query
test "${MYSQL_STATUS:-0}" = 0 || exit "$MYSQL_STATUS"
printf '%s\n' "${SCAN_THRESHOLD:--1}"
EOF
cat > /var/qmail/bin/qmail-queue <<'EOF'
#!/bin/sh
cat >/dev/null
touch /tmp/queue-called
exit "${QUEUE_STATUS:?}"
EOF
cat > /usr/local/bin/spamc <<'EOF'
#!/bin/sh
printf '%s\n' "$@" > /tmp/spamc-args
test "${SPAMC_STATUS:-0}" = 0 || exit "$SPAMC_STATUS"
cat
EOF
cat > /usr/local/bin/822field <<'EOF'
#!/bin/sh
cat >/dev/null
printf '**********\n'
EOF
chmod 755 /usr/bin/mysql /var/qmail/bin/qmail-queue /usr/local/bin/spamc /usr/local/bin/822field
export RCPTTO=fixture@examples.invalid
unset RC
for expected in 0 32 53 255; do
    actual=0
    printf 'Subject: synthetic\n\nfixture\n' | QUEUE_STATUS=$expected /var/qmail/bin/qmail-queuescan || actual=$?
    test "$actual" = "$expected"
    test -e /tmp/queue-called
    rm /tmp/queue-called
done
actual=0
printf 'Subject: synthetic\n\nfixture\n' | SCAN_THRESHOLD=5 QUEUE_STATUS=0 /var/qmail/bin/qmail-queuescan || actual=$?
test "$actual" = 33
test ! -e /tmp/queue-called
for recipient in 'fixture@examples.invalid ' "o'hara@examples.invalid " 'first@examples.invalid second@examples.invalid '; do
    actual=0
    printf 'Subject: synthetic\n\nfixture\n' | RCPTTO="$recipient" SCAN_THRESHOLD=5 QUEUE_STATUS=0 /var/qmail/bin/qmail-queuescan || actual=$?
    test "$actual" = 33
    case "$recipient" in
        'fixture@examples.invalid ') expected=fixture@examples.invalid ;;
        "o'hara@examples.invalid ") expected="o'hara@examples.invalid" ;;
        *) expected='$GLOBAL' ;;
    esac
    test "$(cat /tmp/spamc-args)" = "$(printf '%s\n' -x -u "$expected")"
    case "$(cat /tmp/scanner-query)" in *"o'hara"*) exit 1 ;; esac
    test ! -e /tmp/queue-called
done
actual=0
printf 'fixture\n' | MYSQL_STATUS=1 QUEUE_STATUS=0 /var/qmail/bin/qmail-queuescan || actual=$?
test "$actual" = 53
test ! -e /tmp/queue-called
actual=0
printf 'fixture\n' | SCAN_THRESHOLD=5 SPAMC_STATUS=69 QUEUE_STATUS=0 /var/qmail/bin/qmail-queuescan || actual=$?
test "$actual" = 53
test ! -e /tmp/queue-called
test -z "$(ls -A /var/qmail/tmp)"
printf 'PASS: queue status, recipient profiles, SQL/spamd failures and spam rejection\n'
