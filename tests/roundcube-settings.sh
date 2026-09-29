#!/usr/bin/bash
set -Eeuo pipefail

# Load helper definitions only; never run container initialization on the host.
. "$(dirname "$0")/../rootfs/opt/bin/upgrade/common.sh"
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT

cat > "$temporary/legacy.conf" <<'EOF'
export DES_KEY=prefix$UNSET_LEGACY_KEY$(touch "$temporary/executed")'`
export SUPPORT_URL="mailto:help@example.test"
export PRODUCT_NAME="Legacy Webmail"
export MYSQL_USER="legacy-user"
EOF
cp "$temporary/legacy.conf" "$temporary/original.conf"
load_roundcube_settings "$temporary/legacy.conf"
[[ "$SUPPORT_URL" == mailto:help@example.test ]]
[[ "$PRODUCT_NAME" == 'Legacy Webmail' ]]
[[ "$MYSQL_USER" == legacy-user ]]
[[ ! -e "$temporary/executed" ]]
[[ ! -v DES_KEY ]]
cmp "$temporary/original.conf" "$temporary/legacy.conf"

expected='Webmail $literal `text` with "quotes"'
printf 'export %s=%q\n' SUPPORT_URL '' PRODUCT_NAME "$expected" > "$temporary/current.conf"
load_roundcube_settings "$temporary/current.conf"
[[ "$PRODUCT_NAME" == "$expected" ]]
[[ "$SUPPORT_URL" == '' ]]

if bash -Eeuo pipefail -c '. "$1"; load_roundcube_settings "$2"' \
  bash "$(dirname "$0")/../rootfs/opt/bin/upgrade/common.sh" "$temporary/missing.conf" 2>/dev/null; then
  echo 'Missing configuration was not rejected' >&2
  exit 1
fi
echo 'Roundcube settings regression tests passed'
