#!/usr/bin/env python3
"""Test shipped delivery administration in an isolated, initialized mail image.

python3 -B tests/delivery-admin.py --image sqmail-aio:dev
Requires Docker and a local mariadb:11.4 image. Reuses MailEnvironment's internal
network, disposable database/volumes, read-only tests and no published ports.
"""

import argparse
from pathlib import Path
import signal
import subprocess
import sys

from mail import MailEnvironment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='sqmail-aio:dev')
    parser.add_argument('--database-image', default='mariadb:11.4')
    parser.add_argument('--debug-helper-overlay', action='store_true',
                        help='DEBUG ONLY: copy current helper into disposable container; not image proof')
    parser.add_argument('--vacation-only', action='store_true', help='run vacation delivery and persistence only')
    args = parser.parse_args()

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    environment = MailEnvironment(args.image, args.database_image)
    reader = environment.prefix + '-backup-reader'
    try:
        environment.prepare()
        if args.debug_helper_overlay:
            print('DEBUG OVERLAY: current helper replaces image helper; NOT final image proof', flush=True)
            helper = Path(__file__).resolve().parents[1] / 'rootfs/opt/libexec/delivery-admin'
            environment.docker('cp', str(helper), environment.mail + ':/opt/libexec/delivery-admin')
            environment.docker('exec', environment.mail, 'chmod', '0755', '/opt/libexec/delivery-admin')
        result = subprocess.run(['docker', 'exec', environment.mail, 'python3', '-B',
                                 '/tests/delivery-admin-probe.py',
                                 *(['--vacation-only'] if args.vacation_only else [])], timeout=600)
        if result.returncode:
            raise RuntimeError('Delivery administration probe failed')
        before = environment.docker('exec', environment.mail, 'python3', '-B',
                                    '/tests/delivery-admin-probe.py', '--backup-digest').stdout.strip()
        environment.docker('stop', '--time', '20', environment.mail)
        after = environment.docker(
            'run', '--rm', '--pull=never', '--name', reader,
            '--label', f'{environment.label}={environment.run_id}', '--network', 'none',
            '--volumes-from', environment.mail + ':ro', '--entrypoint', 'python3',
            '-e', 'SQMAIL_DISPOSABLE_TEST=1', '-e', f'SQMAIL_MAIL_TEST_RUN={environment.run_id}',
            environment.image, '-B', '/tests/delivery-admin-probe.py', '--backup-digest').stdout.strip()
        if before != after or not before:
            raise RuntimeError('Persistent backup records changed across fresh container readback')
        print('PASS: private backup snapshot survives stop and fresh read-only container', flush=True)
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        # Do not dump daemon logs: authentication and malformed-input tests carry
        # secrets and intentionally hostile strings. The probe emits safe labels.
        print(f'ERROR: {type(error).__name__}: delivery integration failed', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Interrupted; removing disposable delivery-test resources', file=sys.stderr)
        return 130
    finally:
        try:
            if environment.owned('container', reader):
                environment.docker('rm', '-f', reader)
        finally:
            environment.cleanup()
    print('PASS: delivery administration tests; disposable resources removed'
          + (' (DEBUG OVERLAY, not image proof)' if args.debug_helper_overlay else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
