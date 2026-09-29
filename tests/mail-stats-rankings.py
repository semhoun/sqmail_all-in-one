#!/usr/bin/env python3
"""Exercise rankings using only fresh, isolated synthetic databases."""
import argparse
from pathlib import Path
import subprocess
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-image', default='mariadb:11.4')
    parser.add_argument('--image', default='sqmail_aio-sqmail_aio:latest')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    run_id = uuid.uuid4().hex
    prefix = 'sqmail-rankings-' + run_id[:12]
    network, database, runner = (prefix + suffix for suffix in ('-net', '-db', '-php'))
    label_key = 'sqmail.rankings-test'
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
        for image in (args.database_image, args.image):
            docker('image', 'inspect', '--format', '{{.Id}}', image)
        docker('network', 'create', '--internal', '--label', label, network)
        docker('run', '-d', '--name', database, '--label', label, '--network', network, '--network-alias', 'db',
               '--tmpfs', '/var/lib/mysql:rw,nosuid,size=1g', '-e', 'MYSQL_ROOT_PASSWORD=SyntheticRoot927',
               '-e', 'MYSQL_DATABASE=stats', '-e', 'MYSQL_USER=stats', '-e', 'MYSQL_PASSWORD=SyntheticRankings927', args.database_image)
        mounts = []
        for source, target in [
            ('rootfs/var/www/admin/lib/mail-stats.php', '/var/www/admin/lib/mail-stats.php'),
            ('rootfs/opt/sql/mail-stats.sql', '/opt/sql/mail-stats.sql'),
            ('tests/mail-stats-rankings.php', '/tests/mail-stats-rankings.php'),
        ]:
            mounts += ['--mount', f'type=bind,src={root / source},dst={target},readonly']
        result = docker('run', '--name', runner, '--label', label, '--network', network,
                        '-e', 'MAIL_STATS_RANKINGS_FIXTURE=1', *mounts, '--entrypoint', 'php8.5',
                        args.image, '/tests/mail-stats-rankings.php', check=False, timeout=240)
        print(result.stdout, end='')
        if result.returncode == 0:
            print(f"Passed {sum(line.startswith('PASS ') for line in result.stdout.splitlines())} assertions on {args.database_image}.")
        return result.returncode
    finally:
        for name in (runner, database):
            if owned('container', name):
                docker('rm', '-f', '-v', name)
        if owned('network', network):
            docker('network', 'rm', network)


if __name__ == '__main__':
    raise SystemExit(main())
