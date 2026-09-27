#!/usr/bin/bash
set -Eeuo pipefail
umask 077
export LC_ALL=C

usage() {
  echo "Usage: mksrs.sh [-p] [-m mailhost] -i public_ip [-i public_ip] domain"
  echo "  -p  Print DNS records only, without changing configuration"
  echo "  -m  Mail exchanger (default: /var/qmail/control/me)"
  echo "  -i  Public outgoing IPv4 or IPv6 address; may be repeated"
}

fail() { echo "mksrs: $*" >&2; exit 1; }

valid_host() {
  local label
  local -a labels
  [[ ${#1} -le 253 && $1 == *.* && $1 != *. && $1 =~ ^[a-z0-9.-]+$ ]] || return 1
  IFS=. read -r -a labels <<< "$1"
  for label in "${labels[@]}"; do
    [[ ${#label} -le 63 && $label =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] || return 1
  done
}

control=/var/qmail/control
alias_file=/var/qmail/alias/.qmail-srs-default
print_only=0
mx=
spf='v=spf1'
while getopts ':pm:i:h' option; do
  case "$option" in
    p) print_only=1 ;;
    m) mx=${OPTARG,,}; mx=${mx%.} ;;
    i)
      mechanism=$(php -n -r '
        if (filter_var($argv[1], FILTER_VALIDATE_IP, FILTER_FLAG_IPV4)) echo "ip4:" . $argv[1];
        elseif (filter_var($argv[1], FILTER_VALIDATE_IP, FILTER_FLAG_IPV6)) echo "ip6:" . $argv[1];
        else exit(1);
      ' "$OPTARG") || fail 'Invalid public IP address'
      spf+=" $mechanism"
      ;;
    h) usage; exit 0 ;;
    *) usage >&2; exit 1 ;;
  esac
done
shift "$((OPTIND - 1))"
[[ $# -eq 1 && $spf != 'v=spf1' ]] || { usage >&2; exit 1; }
domain=${1,,}; domain=${domain%.}
srs_domain=srs.$domain
valid_host "$domain" && valid_host "$srs_domain" || fail 'Invalid domain (use its ASCII/Punycode name)'
if [[ -z $mx ]]; then
  [[ -f $control/me && ! -L $control/me ]] || fail 'Supply -m or initialize the mail server first'
  IFS= read -r mx < "$control/me" || [[ -n $mx ]]
  mx=${mx,,}; mx=${mx%.}
fi
valid_host "$mx" || fail 'Invalid mail exchanger hostname'
spf+=' -all'
[[ ${#spf} -le 255 ]] || fail 'Too many addresses for one SPF TXT record'

print_dns() {
  printf '%s. IN MX 10 %s.\n' "$srs_domain" "$mx"
  printf '%s. IN TXT "%s"\n' "$srs_domain" "$spf"
}
if [[ $print_only -eq 1 ]]; then print_dns; exit 0; fi

[[ $EUID -eq 0 ]] || fail 'Run this command as root inside the mail container'
[[ -d $control && -d /var/qmail/alias && -f $control/rcpthosts ]] || fail 'Initialize the mail server first'
[[ -x /var/qmail/bin/srsforward && -x /var/qmail/bin/srsreverse ]] || fail 'SRS helpers are missing'
for file in "$control"/{srsdomains,rcpthosts,virtualdomains,locals,recipients,.aio-migration.lock} \
    /var/qmail/users/assign /var/qmail/users/assign.cdb "$alias_file"; do
  [[ ! -L $file && ( ! -e $file || -f $file ) ]] || fail "Not a regular file: $file"
done
exec 9> "$control/.aio-migration.lock"
flock -n 9 || fail 'Another configuration or migration command is running'

# Read only the requested record; never print secret values in diagnostics.
lookup() {
  local file=$1 key=$2 record
  [[ -f $file ]] || return 0
  record=$(awk -F: -v key="$key" '
    $0 !~ /^#/ && tolower($1) == key { record=$0; count++ }
    END { if (count > 1) exit 1; if (count == 1) print record }
  ' "$file") || fail "Duplicate entries for $key in $file"
  printf '%s' "$record"
}

[[ -z $(lookup "$control/locals" "$srs_domain") ]] || fail "$srs_domain is already a local domain"
route=$(lookup "$control/virtualdomains" "$srs_domain")
[[ -z $route || ${route#*:} == srs ]] || fail "$srs_domain already has a different virtual route"
recipient_host=$(lookup "$control/rcpthosts" "$srs_domain")
! getent passwd srs >/dev/null || fail 'The local srs user conflicts with the reverse alias'
if [[ -e /var/qmail/users/assign.cdb && ! -f /var/qmail/users/assign ]]; then
  fail 'Cannot check user routing without users/assign'
fi
if [[ -f /var/qmail/users/assign ]]; then
  while IFS=: read -r key rest; do
    prefix=${key:1}
    if [[ $key == +* && ( srs- == "$prefix"* || $prefix == srs-* ) ]] ||
       [[ $key == =* && $prefix == srs-* ]]; then
      fail 'A users/assign entry conflicts with the srs- address prefix'
    fi
  done < /var/qmail/users/assign
fi
if [[ -f $alias_file ]]; then
  [[ $(cat "$alias_file") == '|/var/qmail/bin/srsreverse' ]] || fail 'The SRS reverse alias already has different content'
fi

forward=$(lookup "$control/srsdomains" "$domain")
reverse=$(lookup "$control/srsdomains" "$srs_domain")
wildcard=$(lookup "$control/srsdomains" '*')
[[ -z $(lookup "$control/srsdomains" "!$domain") ]] || fail "SRS is explicitly disabled for $domain"
if [[ -e $control/srsdomains ]]; then
  [[ -s $control/srsdomains ]] || fail 'Empty srsdomains: restore the existing secret instead of regenerating it'
  for user in alias vpopmail; do
    s6-setuidgid "$user" test -r "$control/srsdomains" || fail "srsdomains is not readable by $user"
  done
fi

policy=${forward:-${wildcard:-$reverse}}
if [[ -n $policy ]]; then
  policy=${policy#*:}
else
  policy="$(openssl rand -hex 32)|-|srs."
fi
[[ $policy =~ ^([^|]+)\|([-+=])\|([^|]+)$ ]] || fail 'Unsupported SRS policy; existing configuration was left unchanged'
secret=${BASH_REMATCH[1]}
rewrite=${BASH_REMATCH[3]}
[[ -n ${secret// /} && ! $secret =~ [[:cntrl:]] ]] || fail 'Invalid existing SRS secret list'
[[ $rewrite == srs. || $rewrite == "$srs_domain" ]] || fail 'Existing SRS policy uses a different rewrite domain'
reverse_policy=${reverse:-$wildcard}
if [[ -n $reverse_policy ]]; then
  reverse_policy=${reverse_policy#*:}
  [[ ${reverse_policy%|*} == "${policy%|*}" ]] || fail 'Forward and reverse SRS secrets/separators differ; reconcile them first'
fi

temporary=
trap '[[ -z $temporary ]] || rm -f -- "$temporary"' EXIT
trap 'echo "SRS setup failed; resolve the error and rerun to complete configuration." >&2' ERR
append_line() {
  local file=$1 line=$2 owner=$3 existing
  if [[ -f $file ]]; then
    while IFS= read -r existing || [[ -n $existing ]]; do
      [[ $existing != "$line" ]] || return 0
    done < "$file"
  fi
  temporary=$(mktemp "${file}.XXXXXX")
  if [[ -f $file ]]; then
    cat "$file" > "$temporary"
    if [[ -s $file && -n $(tail -c 1 "$file") ]]; then printf '\n' >> "$temporary"; fi
  fi
  printf '%s\n' "$line" >> "$temporary"
  if [[ -f $file ]]; then
    chown --reference="$file" "$temporary"
    chmod --reference="$file" "$temporary"
  else
    chown "$owner" "$temporary"
    chmod 644 "$temporary"
  fi
  mv -T "$temporary" "$file"
  temporary=
}

# Keep wildcard policies intact: an exact forward entry changes alwaysrewrite.
if [[ -z $forward && -z $wildcard ]]; then
  append_line "$control/srsdomains" "$domain:$policy" qmaild:sqmail
fi
if [[ -z $reverse && -z $wildcard ]]; then
  append_line "$control/srsdomains" "$srs_domain:$policy" qmaild:sqmail
fi
[[ -n $route ]] || append_line "$control/virtualdomains" "$srs_domain:srs" qmaild:sqmail
[[ -f $alias_file ]] || append_line "$alias_file" '|/var/qmail/bin/srsreverse' alias:sqmail
# SRS recipients are dynamic; do not enable recipient checks on other domains.
if [[ -s $control/recipients ]]; then
  append_line "$control/recipients" "!$srs_domain" qmaild:sqmail
fi
[[ -n $recipient_host ]] || append_line "$control/rcpthosts" "$srs_domain" qmaild:sqmail

if s6-svok /service/qmail-send 2>/dev/null; then
  s6-svc -h /service/qmail-send
else
  echo 'Reload routing with /opt/bin/qmailctl reload once qmail-send is running.' >&2
fi
echo "SRS return routing prepared for $srs_domain. Publish these DNS records:"
print_dns
echo 'The vpopmail injector uses SRS for external-to-external forwards through this domain; publish DNS before enabling these forwards.' >&2
