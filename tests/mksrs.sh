#!/usr/bin/bash
# Run only in a disposable image, with no existing mail mounts or network:
# docker run --rm --network none --entrypoint bash -e SQMAIL_DISPOSABLE_TEST=1 \
#   -v "$PWD/tests:/tests:ro" \
#   -v "$PWD/rootfs/opt/bin/mksrs.sh:/opt/bin/mksrs.sh:ro" IMAGE /tests/mksrs.sh
set -Eeuo pipefail
[[ -f /.dockerenv && ${SQMAIL_DISPOSABLE_TEST:-} == 1 ]]
[[ ! -e /var/qmail/control/aio-conf/mysql.conf ]]
control=/var/qmail/control
alias_file=/var/qmail/alias/.qmail-srs-default
tool=/opt/bin/mksrs.sh
mkdir -p "$control" /var/qmail/alias /var/qmail/users

reset_fixture() {
  rm -f "$control"/{srsdomains,recipients,.aio-migration.lock} "$alias_file" /var/qmail/users/assign.cdb
  printf 'mail.examples.invalid\n' > "$control/me"
  printf '# Keep this comment\nexamples.invalid\n' > "$control/rcpthosts"
  printf 'examples.invalid:examples.invalid\n' > "$control/virtualdomains"
  printf 'mail.examples.invalid\n' > "$control/locals"
  printf '.\n' > /var/qmail/users/assign
  chmod 644 "$control"/{me,rcpthosts,virtualdomains,locals} /var/qmail/users/assign
}
state() {
  local file
  for file in "$control"/{me,srsdomains,rcpthosts,virtualdomains,locals,recipients} "$alias_file"; do
    if [[ -f $file ]]; then
      sha256sum "$file"
      stat -c '%i:%u:%g:%a' "$file"
    else
      printf 'absent: %s\n' "$file"
    fi
  done
}
configure() {
  "$tool" -i 203.0.113.10 examples.invalid > /tmp/mksrs-output 2>/tmp/mksrs-errors
}
expect_failure() {
  local before
  before=$(state)
  if configure; then echo 'Expected setup failure' >&2; exit 1; fi
  [[ $(state) == "$before" ]]
}

reset_fixture
before=$(state)
"$tool" -p -m MAIL.Examples.Invalid. -i 203.0.113.10 -i 2001:db8::10 Examples.Invalid. > /tmp/mksrs-output
grep -Fxq 'srs.examples.invalid. IN MX 10 mail.examples.invalid.' /tmp/mksrs-output
grep -Fxq 'srs.examples.invalid. IN TXT "v=spf1 ip4:203.0.113.10 ip6:2001:db8::10 -all"' /tmp/mksrs-output
[[ $(state) == "$before" && ! -e $control/.aio-migration.lock ]]
s6-setuidgid www-data "$tool" -p -m mail.examples.invalid -i 203.0.113.10 examples.invalid >/dev/null
[[ $(state) == "$before" && ! -e $control/.aio-migration.lock ]]
for domain in 'examples.invalid..' '-bad.invalid' 'bad..invalid' 'bad.invalid:route'; do
  if "$tool" -p -m mail.examples.invalid -i 203.0.113.10 "$domain" >/dev/null 2>&1; then exit 1; fi
done
if "$tool" -p -m mail.examples.invalid -i 999.0.0.1 examples.invalid >/dev/null 2>&1; then exit 1; fi
[[ $(state) == "$before" ]]
echo 'PASS read-only DNS, IPv4/IPv6, hostname normalization and invalid input'

configure
secret=$(awk -F'[:|]' '$1 == "examples.invalid" {print $2}' "$control/srsdomains")
[[ $secret =~ ^[0-9a-f]{64}$ ]]
grep -Fxq "srs.examples.invalid:$secret|-|srs." "$control/srsdomains"
! grep -Fq "$secret" /tmp/mksrs-output /tmp/mksrs-errors
grep -Fxq 'srs.examples.invalid:srs' "$control/virtualdomains"
grep -Fxq '|/var/qmail/bin/srsreverse' "$alias_file"
grep -Fxq 'srs.examples.invalid' "$control/rcpthosts"
grep -Fxq 'examples.invalid' "$control/rcpthosts"
[[ ! -e $control/recipients ]]
[[ $(stat -c '%U:%G:%a' "$control/srsdomains") == qmaild:sqmail:644 ]]
[[ $(stat -c '%U:%G:%a' "$alias_file") == alias:sqmail:644 ]]
before=$(state)
configure
[[ $(state) == "$before" ]]
echo 'PASS new per-domain secret, reverse routing, permissions and idempotence'

reset_fixture
printf '# Existing policy\n*:synthetic-old synthetic-older|-|srs.\n' > "$control/srsdomains"
printf '*|/var/vpopmail/bin/vchkpw\n' > "$control/recipients"
cp "$control/srsdomains" /tmp/srs-before
configure
cmp "$control/srsdomains" /tmp/srs-before
grep -Fxq '*|/var/vpopmail/bin/vchkpw' "$control/recipients"
grep -Fxq '!srs.examples.invalid' "$control/recipients"
! grep -Fxq '!*' "$control/recipients"
before=$(state)
configure
[[ $(state) == "$before" ]]
echo 'PASS wildcard and rotated secrets retained; recipient exception stays domain-specific'

reset_fixture
printf 'examples.invalid:synthetic-existing|-|srs.\n' > "$control/srsdomains"
configure
grep -Fxq 'srs.examples.invalid:synthetic-existing|-|srs.' "$control/srsdomains"
echo 'PASS incomplete per-domain configuration resumes without rotating its secret'

reset_fixture
printf 'srs.examples.invalid\n' >> "$control/locals"
expect_failure
reset_fixture
printf 'srs.examples.invalid:other\n' >> "$control/virtualdomains"
expect_failure
reset_fixture
printf '|custom-handler\n' > "$alias_file"
expect_failure
reset_fixture
printf '+s:custom:89:89:/tmp:-::\n.\n' > /var/qmail/users/assign
expect_failure
reset_fixture
printf 'srs.examples.invalid\nsrs.examples.invalid\n' >> "$control/rcpthosts"
expect_failure
reset_fixture
touch "$control/srsdomains"
expect_failure
reset_fixture
printf 'examples.invalid:secret-one|-|srs.\nsrs.examples.invalid:secret-two|-|srs.\n' > "$control/srsdomains"
expect_failure
reset_fixture
printf '!examples.invalid:\n*:synthetic-secret|-|srs.\n' > "$control/srsdomains"
expect_failure
reset_fixture
printf '*:synthetic-secret|-|elsewhere.invalid\n' > "$control/srsdomains"
expect_failure
reset_fixture
printf '*:synthetic-secret|-|srs.\n' > "$control/srsdomains"
chmod 600 "$control/srsdomains"
expect_failure
reset_fixture
printf 'do not change\n' > /tmp/srs-symlink-target
ln -s /tmp/srs-symlink-target "$control/srsdomains"
expect_failure
grep -Fxq 'do not change' /tmp/srs-symlink-target
echo 'PASS conflicting routes, aliases, assignments and unsafe existing policies leave files unchanged'

reset_fixture
exec 8> "$control/.aio-migration.lock"
flock -n 8
expect_failure
flock -u 8
exec 8>&-
echo 'PASS concurrent migration/configuration lock'

reset_fixture
mkdir /tmp/mksrs-bin
cat > /tmp/mksrs-bin/mv <<'EOF'
#!/bin/bash
if [[ ${*: -1} == /var/qmail/control/virtualdomains ]]; then exit 1; fi
exec /usr/bin/mv "$@"
EOF
chmod 755 /tmp/mksrs-bin/mv
if PATH="/tmp/mksrs-bin:$PATH" configure; then exit 1; fi
[[ ! -e $alias_file ]]
! grep -Fxq 'srs.examples.invalid' "$control/rcpthosts"
cp "$control/srsdomains" /tmp/srs-before
configure
cmp "$control/srsdomains" /tmp/srs-before
echo 'PASS interrupted write resumes with the same secret'

mkdir /tmp/mksrs-service-bin
printf '#!/bin/sh\nexit 0\n' > /tmp/mksrs-service-bin/s6-svok
cat > /tmp/mksrs-service-bin/s6-svc <<'EOF'
#!/bin/sh
printf '%s\n' "$@" > /tmp/srs-reload
EOF
chmod 755 /tmp/mksrs-service-bin/*
PATH="/tmp/mksrs-service-bin:$PATH" configure
[[ $(cat /tmp/srs-reload) == "$(printf '%s\n' -h /service/qmail-send)" ]]
echo 'PASS routing reload request (capture-only supervisor)'
