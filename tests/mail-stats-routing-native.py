#!/usr/bin/env python3
"""Verify the upstream qmailadmin log function and its narrow timezone patch."""

import datetime
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://raw.githubusercontent.com/sagredo-dev/qmailadmin/v1.2.28/qmailadmin.c'


def main():
    with urllib.request.urlopen(URL, timeout=30) as response:
        source = response.read().decode('utf-8')
    with tempfile.TemporaryDirectory(prefix='routing-native-', dir='/tmp/kilo') as temporary:
        directory = Path(temporary)
        (directory / 'qmailadmin.c').write_text(source)
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i',
                        str(ROOT / 'rootfs/opt/patches/qmailadmin-log-timezone.patch')],
                       cwd=directory, check=True)
        patched = (directory / 'qmailadmin.c').read_text()
        function = patched.split('static void log_auth(char *msg)\n', 1)[1].split('\n#endif', 1)[0]
        harness = '''#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#define MAX_BUFF 512
#define AUTH_LOGDIR "."
char Username[MAX_BUFF] = "synthetic";
char Domain[MAX_BUFF] = "example.invalid";
char StatusMessage[MAX_BUFF];
char *html_text[323];
void show_login(void) { abort(); }
static void log_auth(char *msg)
''' + function + '''
int main(void) { log_auth("failed [synthetic@example.invalid]"); return 0; }
'''
        (directory / 'probe.c').write_text(harness)
        subprocess.run(['gcc', '-Wall', '-Wextra', '-Werror', '-o', str(directory / 'probe'),
                        str(directory / 'probe.c')], check=True)
        log = directory / 'qmailadmin-auth.log'
        for timezone, offset in [('UTC0', '+0000'), ('CET-2', '+0200')]:
            subprocess.run([str(directory / 'probe')], cwd=directory, check=True,
                           env={**os.environ, 'TZ': timezone, 'REMOTE_ADDR': '192.0.2.1'})
            line = log.read_text().splitlines()[-1]
            stamp, details = line.split(' user:', 1)
            assert stamp.endswith(offset), line
            datetime.datetime.strptime(stamp, '%Y/%m/%d %H:%M:%S %z')
            assert details == 'synthetic@example.invalid ip:192.0.2.1 auth:failed [synthetic@example.invalid]'
            print('Verified qmailadmin fixture: ' + line)
        assert len(log.read_text().splitlines()) == 2
        log.rename(directory / 'archive')
        subprocess.run([str(directory / 'probe')], cwd=directory, check=True,
                       env={**os.environ, 'TZ': 'UTC0', 'REMOTE_ADDR': '192.0.2.1'})
        assert len(log.read_text().splitlines()) == 1
        assert len((directory / 'archive').read_text().splitlines()) == 2
    print('Native qmailadmin patch, explicit offsets, append and reopen after rotation passed')


if __name__ == '__main__':
    main()
