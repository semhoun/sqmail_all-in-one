#!/usr/bin/bash
# vpopmail's forwarding injector; normal injection remains the default.
set -Eeuo pipefail
export LC_ALL=C

normal_inject() { exec /var/qmail/bin/qmail-inject "$@"; }
defer() { echo "vpopmail-inject: $*; delivery deferred" >&2; exit 111; }
trap 'defer "unexpected configuration or processing error"' ERR

# Other qmail-inject invocations and missing delivery context are not SRS forwards.
[[ $# -eq 2 && $1 == -- ]] || normal_inject "$@"
[[ -v HOST && -v NEWSENDER && -v SENDER && -v DTLINE && -v RPLINE ]] || normal_inject "$@"
[[ -n $NEWSENDER && -n $SENDER ]] || normal_inject "$@"
recipient=$2
[[ $recipient == *@* && $NEWSENDER == *@* ]] || normal_inject "$@"
[[ ! $recipient =~ [[:cntrl:]] && ! $NEWSENDER =~ [[:cntrl:]] ]] || normal_inject "$@"
host=${HOST,,}; host=${host%.}
destination=${recipient##*@}; destination=${destination,,}; destination=${destination%.}
origin=${NEWSENDER##*@}; origin=${origin,,}; origin=${origin%.}
for domain in "$host" "$destination" "$origin"; do
  [[ $domain == *.* && $domain =~ ^[a-z0-9.-]+$ ]] || normal_inject "$@"
done

control=/var/qmail/control
declare -A virtual=() policies=() local_hosts=() accepted=()

read_control() {
  local file=$1 format=$3 line key value
  local -n entries=$2
  [[ -e $file || -L $file ]] || return 0
  [[ -f $file && -r $file ]] || defer "cannot read $file"
  while IFS= read -r line || [[ -n $line ]]; do
    line=${line%"${line##*[!$' \t\r']}"}
    [[ -n $line && $line != \#* ]] || continue
    if [[ $format == pairs ]]; then
      [[ $line == *:* ]] || defer "malformed entry in $file"
      key=${line%%:*}; value=${line#*:}
    else
      key=$line; value=1
    fi
    key=${key,,}; key=${key:-@default}
    [[ ! ${entries[$key]+present} || $format != pairs ]] || defer "duplicate entry in $file"
    entries[$key]=$value
  done < "$file"
}

read_control "$control/locals" local_hosts lines
if [[ ! -e $control/locals ]]; then read_control "$control/me" local_hosts lines; fi
read_control "$control/virtualdomains" virtual pairs

local_domain() {
  local suffix=$1
  [[ ! ${local_hosts[$suffix]+present} ]] || return 0
  while :; do
    if [[ ${virtual[$suffix]+present} ]]; then
      [[ -n ${virtual[$suffix]} ]]
      return
    fi
    [[ $suffix == .* ]] && suffix=${suffix#.}
    [[ $suffix == *.* ]] || break
    suffix=.${suffix#*.}
  done
  [[ -n ${virtual[@default]-} ]]
}

# Local senders already use our outgoing server; keep their signing identity.
if local_domain "$origin" || local_domain "$destination"; then normal_inject "$@"; fi

# The initial wildcard secret alone must not enable SRS on every hosted domain.
# mksrs.sh prepares this per-domain return route after DNS has been published.
srs_domain=srs.$host
[[ ${virtual[$srs_domain]-} == srs ]] || normal_inject "$@"
read_control "$control/rcpthosts" accepted lines
[[ ${accepted[$srs_domain]+present} ]] || normal_inject "$@"
alias_file=/var/qmail/alias/.qmail-srs-default
[[ -f $alias_file && -r $alias_file ]] || defer 'SRS reverse alias is missing or unreadable'
[[ $(cat "$alias_file") == '|/var/qmail/bin/srsreverse' ]] || defer 'SRS reverse alias has unexpected content'

read_control "$control/srsdomains" policies pairs
disabled=!$host
[[ ! ${policies[$disabled]+present} ]] || normal_inject "$@"
policy=${policies[$host]-${policies['*']-}}
[[ ${policies[$host]+present} || ${policies['*']+present} ]] || normal_inject "$@"
[[ $policy =~ ^([^|]+)\|([-+=])\|([^|]+)$ ]] || defer 'invalid SRS policy'
secrets=${BASH_REMATCH[1]}; separator=${BASH_REMATCH[2]}; rewrite=${BASH_REMATCH[3]}
[[ -n ${secrets// /} && ! $secrets =~ [[:cntrl:]] ]] || defer 'invalid SRS secret list'
[[ $rewrite != *. ]] || rewrite+=$host
[[ ${rewrite,,} == "$srs_domain" ]] || defer 'SRS policy does not match the prepared return route'
reverse=${policies[$srs_domain]-${policies['*']-}}
[[ $reverse =~ ^([^|]+)\|([-+=])\|([^|]+)$ ]] || defer 'missing or invalid reverse SRS policy'
reverse_secrets=${BASH_REMATCH[1]}; reverse_separator=${BASH_REMATCH[2]}
[[ $separator == "$reverse_separator" ]] || defer 'SRS separators differ'
first_secret=${secrets%% *}
[[ -n $first_secret && " $reverse_secrets " == *" $first_secret "* ]] || defer 'SRS reverse policy cannot verify the forwarding secret'

[[ -x /var/qmail/bin/srsforward ]] || defer 'SRS forward helper is unavailable'
# vdelivermail prepends RPLINE and its normalized Delivered-To header. Remove
# only that generated Return-Path; keep Delivered-To and the original message.
IFS= read -r first_line || defer 'missing forwarding message header'
[[ $RPLINE == 'Return-Path: '*$'\n' && $first_line == "${RPLINE%$'\n'}" ]] || defer 'unexpected forwarding message header'
export HOST=$host DTLINE=''
if /var/qmail/bin/srsforward -- "$recipient"; then
  exit 0
fi
# Never retry plain injection after consuming input or after an SRS failure.
defer 'SRS forwarding failed'
