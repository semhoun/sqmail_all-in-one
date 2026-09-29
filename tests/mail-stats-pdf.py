#!/usr/bin/env python3
"""Disposable PDF tests, no DB, mail accounts, published ports or local runtime data.

Network is used only to fetch locked Composer packages and PDF inspection tools.
The actual PHP tests run in a second container with --network none.
"""

import argparse
from pathlib import Path
import subprocess
import uuid


def run(*args):
    subprocess.run(args, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="sqmail_aio-sqmail_aio:latest")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    prefix = "sqmail-pdf-test-" + uuid.uuid4().hex
    volumes = [prefix + "-vendor", prefix + "-debs"]
    try:
        for volume in volumes:
            run("docker", "volume", "create", volume)
        run(
            "docker", "run", "--rm", "--entrypoint", "/bin/sh",
            "--mount", f"type=bind,src={root}/rootfs/opt/mail-stats-pdf,dst=/opt/mail-stats-pdf,readonly",
            "--mount", f"type=volume,src={volumes[0]},dst=/pdf-vendor",
            "--mount", f"type=volume,src={volumes[1]},dst=/var/cache/apt/archives",
            "--env", "COMPOSER_ALLOW_SUPERUSER=1", "--env", "COMPOSER_VENDOR_DIR=/pdf-vendor", "--workdir", "/opt/mail-stats-pdf", args.image,
            "-ec", "php8.5 /usr/bin/composer --no-interaction --no-plugins --no-scripts install --no-dev --prefer-dist --optimize-autoloader"
            " && apt-get update && apt-get --download-only --no-install-recommends -y install poppler-utils",
        )
        mounts = []
        for relative, destination in [
            ("rootfs/var/www/admin/lib/mail-stats-pdf.php", "/var/www/admin/lib/mail-stats-pdf.php"),
            ("rootfs/var/www/admin/lib/mail-stats.php", "/var/www/admin/lib/mail-stats.php"),
            ("rootfs/var/www/admin/html/stats/export.php", "/var/www/admin/html/stats/export.php"),
            ("tests/mail-stats-pdf-probe.php", "/tests/mail-stats-pdf-probe.php"),
        ]:
            mounts += ["--mount", f"type=bind,src={root / relative},dst={destination},readonly"]
        run(
            "docker", "run", "--rm", "--network", "none", "--entrypoint", "/bin/sh", *mounts,
            "--mount", f"type=volume,src={volumes[0]},dst=/opt/mail-stats-pdf/vendor,readonly",
            "--mount", f"type=volume,src={volumes[1]},dst=/deb,readonly", args.image,
            "-ec", "dpkg -i /deb/*.deb"
            " && install -d -o root -g root -m 0755 /run/mail-stats-pdf"
            " && install -d -o www-data -g www-data -m 0700 /run/mail-stats-pdf/work /run/sqmail-admin"
            " && install -o root -g www-data -m 0660 /dev/null /run/mail-stats-pdf/render.lock"
            " && php8.5 -l /var/www/admin/lib/mail-stats-pdf.php"
            " && php8.5 -l /var/www/admin/html/stats/export.php"
            " && php8.5 -l /tests/mail-stats-pdf-probe.php"
            " && s6-setuidgid www-data php8.5 -d memory_limit=256M -d error_reporting=E_ALL /tests/mail-stats-pdf-probe.php",
        )
    finally:
        for volume in reversed(volumes):
            subprocess.run(["docker", "volume", "rm", volume], check=False)


if __name__ == "__main__":
    main()
