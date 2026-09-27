#!/usr/bin/bash
# Disposable, uninitialized image only; replaces both injectors with capture stubs.
set -Eeuo pipefail
[[ -f /.dockerenv && ${SQMAIL_DISPOSABLE_TEST:-} == 1 ]]
[[ ! -e /var/qmail/control/aio-conf/mysql.conf ]]
control=/var/qmail/control
fixture=/tmp/vpopmail-inject-fixture
mkdir -p "$control" /var/qmail/alias "$fixture"
chown vpopmail:vchkpw "$fixture"
chmod 700 "$fixture"
cat > /var/qmail/bin/qmail-inject <<'EOF'
#!/bin/bash
printf 'normal\n' >> /tmp/vpopmail-inject-fixture/calls
printf '%s\0' "$@" > /tmp/vpopmail-inject-fixture/args
cat > /tmp/vpopmail-inject-fixture/message
exit "${INJECT_STATUS:-0}"
EOF
cat > /var/qmail/bin/srsforward <<'EOF'
#!/bin/bash
printf 'srs\n' >> /tmp/vpopmail-inject-fixture/calls
printf '%s\0' "$@" > /tmp/vpopmail-inject-fixture/args
printf '%s' "$DTLINE" > /tmp/vpopmail-inject-fixture/dtline
cat > /tmp/vpopmail-inject-fixture/message
exit "${SRS_STATUS:-0}"
EOF
chmod 755 /var/qmail/bin/qmail-inject /var/qmail/bin/srsforward
export HOST=examples.invalid NEWSENDER=sender@outside.invalid SENDER=sender@outside.invalid
export RPLINE=$'Return-Path: <sender@outside.invalid>\n'
export DTLINE=$'Delivered-To: forward@examples.invalid\n'
printf '%sSubject: fixture\nFrom: Original <sender@outside.invalid>\nDKIM-Signature: synthetic-unchanged\n\nBinary\000payload\377\n' "$DTLINE" > /tmp/inject-expected-srs
{ printf '%s' "$RPLINE"; cat /tmp/inject-expected-srs; } > /tmp/inject-input

reset_controls() {
  printf 'mail.examples.invalid\n' > "$control/locals"
  printf 'examples.invalid:examples.invalid\nsrs.examples.invalid:srs\n' > "$control/virtualdomains"
  printf 'examples.invalid\nsrs.examples.invalid\n' > "$control/rcpthosts"
  printf '*:synthetic-secret|-|srs.\n' > "$control/srsdomains"
  printf '|/var/qmail/bin/srsreverse\n' > /var/qmail/alias/.qmail-srs-default
  chmod 644 "$control"/{locals,virtualdomains,rcpthosts,srsdomains} /var/qmail/alias/.qmail-srs-default
}
run_case() {
  local expected=$1 mode=$2 status=0
  shift 2
  rm -f "$fixture"/{calls,args,message,dtline}
  s6-setuidgid vpopmail /opt/bin/vpopmail-inject.sh "$@" < /tmp/inject-input > /tmp/inject-output 2>/tmp/inject-error || status=$?
  [[ $status -eq $expected ]]
  if [[ $mode == none ]]; then
    [[ ! -e $fixture/calls ]]
  else
    [[ $(cat "$fixture/calls") == "$mode" ]]
    printf '%s\0' "$@" > /tmp/inject-expected-args
    cmp "$fixture/args" /tmp/inject-expected-args
    if [[ $mode == normal ]]; then cmp "$fixture/message" /tmp/inject-input; fi
    if [[ $mode == srs ]]; then
      cmp "$fixture/message" /tmp/inject-expected-srs
      [[ ! -s $fixture/dtline ]]
    fi
  fi
}

reset_controls
run_case 0 srs -- target@remote.invalid
run_case 0 srs -- -target@remote.invalid
run_case 0 normal -- user@examples.invalid
run_case 0 normal -- user@mail.examples.invalid
NEWSENDER=local@examples.invalid SENDER=local@examples.invalid run_case 0 normal -- target@remote.invalid
NEWSENDER='' SENDER='' run_case 0 normal -- target@remote.invalid
HOST=unconfigured.invalid run_case 0 normal -- target@remote.invalid
run_case 0 normal -f sender@outside.invalid -- target@remote.invalid
run_case 0 normal -- one@remote.invalid two@remote.invalid
run_case 0 normal -- $'bad\naddress@remote.invalid'
(unset NEWSENDER; run_case 0 normal -- target@remote.invalid)
echo 'PASS SRS selection, exact arguments, binary message preservation and normal delivery fallbacks'

printf '.hosted.invalid:tenant\n' >> "$control/virtualdomains"
run_case 0 normal -- user@sub.hosted.invalid
printf 'remote.hosted.invalid:\n' >> "$control/virtualdomains"
run_case 0 srs -- user@remote.hosted.invalid
printf ':catchall\n' >> "$control/virtualdomains"
run_case 0 normal -- user@unlisted.invalid
echo 'PASS virtual-domain suffix, explicit remote exception and catchall semantics'

reset_controls
printf '!examples.invalid:\n' >> "$control/srsdomains"
run_case 0 normal -- target@remote.invalid
reset_controls
printf 'unrelated.invalid:other|-|srs.\n' > "$control/srsdomains"
run_case 0 normal -- target@remote.invalid
rm "$control/srsdomains"
run_case 0 normal -- target@remote.invalid
reset_controls
printf 'examples.invalid\n' > "$control/rcpthosts"
run_case 0 normal -- target@remote.invalid
echo 'PASS disabled, absent and incomplete SRS activation fall back before reading input'

reset_controls
printf 'examples.invalid:broken\n' >> "$control/srsdomains"
run_case 111 none -- target@remote.invalid
reset_controls
printf 'examples.invalid:new-secret|-|srs.\nsrs.examples.invalid:old-secret|-|srs.\n' > "$control/srsdomains"
run_case 111 none -- target@remote.invalid
printf 'examples.invalid:new-secret|-|srs.\nsrs.examples.invalid:new-secret old-secret|-|srs.\n' > "$control/srsdomains"
run_case 0 srs -- target@remote.invalid
reset_controls
chmod 600 "$control/srsdomains"
run_case 111 none -- target@remote.invalid
reset_controls
printf '*:duplicate|-|srs.\n' >> "$control/srsdomains"
run_case 111 none -- target@remote.invalid
reset_controls
RPLINE=$'Return-Path: <unexpected@outside.invalid>\n' run_case 111 none -- target@remote.invalid
SRS_STATUS=100 run_case 111 srs -- target@remote.invalid
SRS_STATUS=111 run_case 111 srs -- target@remote.invalid
INJECT_STATUS=100 run_case 100 normal -- user@examples.invalid
echo 'PASS policy/header errors and helper failures defer without a second plain injection'
