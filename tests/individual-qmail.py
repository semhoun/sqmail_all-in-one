#!/usr/bin/env python3
"""Prove individual .qmail contracts in MailEnvironment's disposable fixture.

python3 tests/individual-qmail.py --image sqmail_aio-sqmail_aio:latest
No production mounts, published ports, or external mail delivery are used.
"""

import argparse
import signal
import subprocess
import sys

from mail import MailEnvironment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='sqmail_aio-sqmail_aio:latest')
    parser.add_argument('--database-image', default='mariadb:11.4')
    args = parser.parse_args()
    environment = MailEnvironment(args.image, args.database_image)

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        print(environment.docker('image', 'inspect', '--format', '{{.Id}}', args.image).stdout,
              end='', flush=True)
        print('Resources: ' + environment.prefix, flush=True)
        environment.prepare()
        result = subprocess.run(['docker', 'exec', environment.mail, 'python3',
                                 '/tests/individual-qmail-probe.py'], timeout=600)
        if result.returncode:
            raise RuntimeError('Individual .qmail proof failed')
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        environment.logs()
        return 1
    except KeyboardInterrupt:
        return 130
    finally:
        environment.cleanup()
        print('CLEANUP complete: ' + environment.prefix, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
