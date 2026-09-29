#!/usr/bin/bash

# Callers use errexit and pipefail; never call migration functions in an if/|| list.
atomic_write() {
  local destination=$1 temporary
  [ ! -L "$destination" ] || { echo "Refusing symlink: $destination" >&2; return 1; }
  temporary=$(mktemp "${destination}.XXXXXX")
  if ! cat > "$temporary"; then rm -f "$temporary"; return 1; fi
  if [ -e "$destination" ]; then
    chown --reference="$destination" "$temporary"
    chmod --reference="$destination" "$temporary"
  fi
  mv -fT "$temporary" "$destination"
}

write_mysql_php() {
  php -r '$c = []; foreach (["MYSQL_USER", "MYSQL_PASS", "MYSQL_DB", "MYSQL_HOST"] as $k) {
    $c[$k] = getenv($k);
  } echo "<?php\n\$MYSQL_CONF = ", var_export($c, true), ";\n";' |
    atomic_write /var/qmail/control/aio-conf/mysql.php
  chown root:www-data /var/qmail/control/aio-conf/mysql.php
  chmod 640 /var/qmail/control/aio-conf/mysql.php
}

load_roundcube_settings() {
  local settings
  # Legacy installers wrote this unused random key without shell escaping.
  # Do not evaluate it or change the key in an existing Roundcube PHP config.
  settings=$(sed '/^export DES_KEY=/d' "$1")
  . <(printf '%s\n' "$settings")
}

roundcube_config() {
  . /var/qmail/control/aio-conf/mysql.conf
  load_roundcube_settings /var/qmail/control/aio-conf/roundcube.conf
  export MYSQL_USER MYSQL_PASS MYSQL_HOST MYSQL_DB
  local source destination temporary
  for source in /var/www/html/config/*.tpl /var/www/html/plugins/*/*.tpl; do
    [ -f "$source" ] || continue
    destination=${source%.tpl}
    if [ -e "$destination" ]; then
      [ -s "$destination" ] || { echo "Empty Roundcube config: $destination" >&2; return 1; }
      php -l "$destination" >/dev/null
      continue
    fi
    temporary=$(mktemp "${destination}.XXXXXX")
    # Credentials in these templates are URI components inside PHP strings.
    php -r '
      $s = file_get_contents($argv[1]);
      if ($s === false) exit(1);
      foreach (["MYSQL_USER", "MYSQL_PASS", "MYSQL_HOST", "MYSQL_DB", "PRODUCT_NAME", "SUPPORT_URL"] as $k) {
        $v = (string) getenv($k);
        $v = str_starts_with($k, "MYSQL_") ? rawurlencode($v) : str_replace(["\\", "\x27"], ["\\\\", "\\\x27"], $v);
        $s = str_replace(["\${" . $k . "}", "$" . $k], $v, $s);
      }
      echo $s;
    ' "$source" > "$temporary"
    php -l "$temporary" >/dev/null
    chown www-data:www-data "$temporary"
    chmod 600 "$temporary"
    mv -T "$temporary" "$destination"
  done
}
