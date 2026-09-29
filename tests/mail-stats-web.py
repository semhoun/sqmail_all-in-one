#!/usr/bin/env python3
"""Run the PHP query service against new, isolated, synthetic databases only."""
import argparse
from pathlib import Path
import subprocess
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-image', default='mariadb:latest')
    parser.add_argument('--budget-only', action='store_true', help='Run focused query-deadline checks without repeating the query suite')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    run_id = uuid.uuid4().hex
    prefix = 'sqmail-stats-web-' + run_id[:12]
    network, database, runner = prefix + '-net', prefix + '-db', prefix + '-php'
    label_key = 'sqmail.stats-web-test'
    label = label_key + '=' + run_id

    def docker(*command, check=True, timeout=180):
        result = subprocess.run(['docker', *command], text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout)
        if check and result.returncode:
            raise RuntimeError(result.stdout)
        return result

    def owned(kind, name):
        field = '.Labels' if kind == 'network' else '.Config.Labels'
        result = docker(kind, 'inspect', '--format', '{{index ' + field + ' "' + label_key + '"}}', name, check=False)
        return result.returncode == 0 and result.stdout.strip() == run_id

    try:
        docker('image', 'inspect', '--format', '{{.Id}}', args.database_image)
        docker('network', 'create', '--internal', '--label', label, network)
        docker('run', '-d', '--name', database, '--label', label, '--network', network, '--network-alias', 'db',
               '--tmpfs', '/var/lib/mysql:rw,nosuid,size=1g', '-e', 'MYSQL_ROOT_PASSWORD=SyntheticRoot927',
               '-e', 'MYSQL_DATABASE=stats', '-e', 'MYSQL_USER=stats', '-e', 'MYSQL_PASSWORD=SyntheticStatsWeb927', args.database_image)
        mounts = []
        for source, target in [
            (root / 'rootfs/var/www/admin/lib/mail-stats.php', '/var/www/admin/lib/mail-stats.php'),
            (root / 'rootfs/var/www/admin/html/stats/index.php', '/var/www/admin/html/stats/index.php'),
            (root / 'rootfs/opt/sql/mail-stats.sql', '/opt/sql/mail-stats.sql'),
            (root / 'tests/mail-stats-web.php', '/tests/mail-stats-web.php'),
        ]:
            mounts += ['--mount', f'type=bind,src={source},dst={target},readonly']
        result = docker('run', '--name', runner, '--label', label, '--network', network,
                        '-e', 'MAIL_STATS_WEB_FIXTURE=1', *mounts, '--entrypoint', 'php8.5',
                        'sqmail_aio-sqmail_aio:latest', '/tests/mail-stats-web.php', *(['budget'] if args.budget_only else []), check=False, timeout=240)
        print(result.stdout, end='')
        return result.returncode
    finally:
        for name in (runner, database):
            if owned('container', name):
                docker('rm', '-f', '-v', name)
        if owned('network', network):
            docker('network', 'rm', network)


if __name__ == '__main__':
    raise SystemExit(main())
