#!/usr/bin/env python3
"""Prove stage-1 native contracts in disposable production-config containers.

python3 tests/native-sieve.py --image sqmail_aio-sqmail_aio:latest
No application writes or shared-fixture changes are performed.
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
        environment.prepare()
        result = subprocess.run(['docker', 'exec', environment.mail, 'python3',
                                 '/tests/native-sieve-probe.py'], timeout=180)
        return result.returncode
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    finally:
        environment.cleanup()
        print('Disposable native-contract resources removed', flush=True)


if __name__ == '__main__':
    sys.exit(main())
