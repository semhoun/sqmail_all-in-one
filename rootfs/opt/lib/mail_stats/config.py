"""Private configuration; never interpret shell-escaped credential files."""

import json
import os
from pathlib import Path
import re
import stat
import tempfile
import uuid


RUNTIME = Path('/run/mail-stats')
IDENTITY = Path('/var/qmail/control/aio-conf/mail-stats-instance')


def settings(environment):
    enabled = environment.get('MAIL_STATS_ENABLED', '1')
    months = environment.get('MAIL_STATS_HISTORY_MONTHS', '6')
    if enabled not in ('0', '1'):
        raise ValueError('MAIL_STATS_ENABLED must be 0 or 1')
    if not re.fullmatch(r'[0-9]{1,16}', months) or not 1 <= int(months) <= 120:
        raise ValueError('MAIL_STATS_HISTORY_MONTHS must be a decimal integer from 1 to 120')
    return enabled == '1', int(months)


def reject_symlinks(path):
    path = Path(path)
    for part in [*reversed(path.parents), path]:
        if part.is_symlink():
            raise ValueError('Symbolic links are not permitted in statistics storage')


def private_directory(path, gid=0, mode=0o700):
    path = Path(path)
    reject_symlinks(path)
    path.mkdir(mode=mode, exist_ok=True)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0:
        raise ValueError('Unsafe statistics storage owner')
    os.chown(path, 0, gid)
    os.chmod(path, mode)


def atomic_json(path, value, gid=0, mode=0o600):
    path = Path(path)
    reject_symlinks(path)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            os.fchown(stream.fileno(), 0, gid)
            os.fchmod(stream.fileno(), mode)
            json.dump(value, stream, ensure_ascii=True, separators=(',', ':'))
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def instance_identity(path=IDENTITY):
    path = Path(path)
    reject_symlinks(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        value = uuid.uuid4().hex
        # Exclusive creation prevents two startup processes from replacing identity.
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            return instance_identity(path)
        with os.fdopen(fd, 'w', encoding='ascii') as stream:
            stream.write(value + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        return value
    with os.fdopen(fd, 'r', encoding='ascii') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
            raise ValueError('Unsafe statistics identity permissions')
        value = stream.read(64).strip()
    if not re.fullmatch(r'[a-f0-9]{32}', value):
        raise ValueError('Invalid statistics instance identity')
    return value


def load_private(path=RUNTIME / 'config.json'):
    reject_symlinks(path)
    with open(path, encoding='utf-8') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
            raise ValueError('Unsafe statistics configuration permissions')
        config = json.loads(stream.read(16384))
    if config.get('enabled') is not True:
        raise ValueError('Statistics collection is disabled')
    if type(config.get('history_months')) is not int or not 1 <= config['history_months'] <= 120:
        raise ValueError('Invalid statistics retention configuration')
    if not re.fullmatch(r'[a-f0-9]{32}', config.get('instance_id', '')):
        raise ValueError('Invalid statistics instance configuration')
    return config


CRON_BEGIN = '# BEGIN SQMAIL MAIL STATS'
CRON_END = '# END SQMAIL MAIL STATS'
CRON_JOB = '* * * * * /usr/bin/python3 -I /opt/libexec/mail-stats-collect'


def cron_text(text, enabled):
    """Replace only our block, retaining every other byte of the crontab."""
    lines = text.splitlines(keepends=True)
    result = []
    inside = False
    for line in lines:
        marker = line.rstrip('\r\n')
        if marker == CRON_BEGIN:
            if inside:
                raise ValueError('Invalid statistics crontab block')
            inside = True
        elif marker == CRON_END:
            if not inside:
                raise ValueError('Invalid statistics crontab block')
            inside = False
        elif not inside:
            result.append(line)
    if inside:
        raise ValueError('Unterminated statistics crontab block')
    text = ''.join(result)
    if enabled:
        if text and not text.endswith('\n'):
            text += '\n'
        text += f'{CRON_BEGIN}\n{CRON_JOB}\n{CRON_END}\n'
    return text
