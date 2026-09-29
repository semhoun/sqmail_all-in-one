"""Bounded, transactional collection from the fixed mail statistics registry.

File positions are technical state, not retained history. They deliberately
survive retention. No log text is persisted, executed, or used as a SQL name.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
import re
import stat
import time
import uuid

from . import db


MAX_LINE = 16384
SOURCE_BYTES = 1048576
SOURCE_LINES = 1000
SOURCE_SECONDS = 3
PURGE_SECONDS = 10
PURGE_BATCHES = 64
MAX_FILES = 4096
CHECK_BYTES = 256
ARCHIVE = re.compile(r"@[0-9a-f]{24}\.[su]\Z")


def binary(value):
    return value.encode("utf-8") if isinstance(value, str) else value


def generation():
    return uuid.uuid4().hex.encode("ascii")


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def open_directory(path):
    """Walk all path components without following symlinks, including parents."""
    if not path.startswith("/") or ".." in path.split("/"):
        raise ValueError("Invalid registered directory")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in filter(None, path.split("/")):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW |
                            os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


@contextmanager
def local_lock(path="/run/mail-stats/collect.lock"):
    parent, name = os.path.split(path)
    directory = open_directory(parent)
    try:
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=directory)
    finally:
        os.close(directory)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise PermissionError("Unsafe collector lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise db.LockBusy("Mail statistics local lock unavailable") from None
        yield
    finally:
        os.close(fd)


@contextmanager
def source_files(source):
    """Only current/s6 archives or explicitly named application log rotations."""
    path = source["path"]
    parent, base = (path, None) if source["kind"] == "s6" else os.path.split(path)
    directory = open_directory(parent)
    try:
        current_name = "current" if base is None else base
        try:
            before = os.stat(current_name, dir_fd=directory, follow_symlinks=False)
            before = (before.st_dev, before.st_ino)
        except FileNotFoundError:
            before = None
        names = []
        with os.scandir(directory) as entries:
            for entry in entries:
                name = entry.name
                allowed = (name == "current" or ARCHIVE.fullmatch(name)) if base is None else (
                    name == base or re.fullmatch(re.escape(base) + r"\.(?:0|[1-9][0-9]{0,3})", name))
                if allowed:
                    info = entry.stat(follow_symlinks=False)
                    if info.st_ino != entry.inode():
                        raise OSError("Source rotated during discovery")
                    names.append((name, info.st_dev, info.st_ino))
                    if len(names) > MAX_FILES:
                        raise ValueError("Registered source has too many archives")
        try:
            after = os.stat(current_name, dir_fd=directory, follow_symlinks=False)
            after = (after.st_dev, after.st_ino)
        except FileNotFoundError:
            after = None
        if before != after:
            raise OSError("Source rotated during enumeration")
        if base is None:
            names.sort(key=lambda item: (item[0] == "current", item[0]))
        else:
            names.sort(key=lambda item: (2, 0) if item[0] == base else (
                (0, 0) if item[0] == base + ".0" else (1, -int(item[0][len(base) + 1:]))))
        yield directory, names
    finally:
        os.close(directory)


def fingerprint(fd, offset, length):
    data = os.pread(fd, length, offset)
    return hashlib.sha256(data).digest() if len(data) == length else None


def valid_checkpoint(fd, row, size):
    if size < row["file_offset"]:
        return False
    for start, length, digest in ((0, row["prefix_length"], row["prefix_hash"]),
                                  (row["checkpoint_offset"], row["checkpoint_length"],
                                   row["checkpoint_hash"])):
        if length and fingerprint(fd, start, length) != digest:
            return False
    return True


def read_batch(fd, row, byte_budget, line_budget, deadline):
    """Return complete records and a provisional cursor; incomplete tails wait.

    Oversized records are discarded in bounded chunks. Persisting skip state is
    necessary: advancing without it would parse a tail as a new legitimate line.
    """
    offset = row["file_offset"]
    skipping = bool(row["skipping_long_line"])
    long_start = row["long_line_start"]
    lines, used, oversized = [], 0, []
    while used < byte_budget and len(lines) + len(oversized) < line_budget and time.monotonic() < deadline:
        amount = min(MAX_LINE + 1, byte_budget - used)
        data = os.pread(fd, amount, offset)
        used += len(data)
        if not data:
            break
        consumed = 0
        while consumed < len(data) and len(lines) + len(oversized) < line_budget:
            end = data.find(b"\n", consumed)
            if skipping:
                step = len(data) - consumed if end < 0 else end + 1 - consumed
                offset += step
                consumed += step
                if end >= 0:
                    skipping, long_start = False, None
            elif end >= 0:
                lines.append((offset, data[consumed:end + 1]))
                offset += end + 1 - consumed
                consumed = end + 1
            elif len(data) - consumed > MAX_LINE:
                long_start = offset
                offset += len(data) - consumed
                consumed = len(data)
                skipping = True
                oversized.append(long_start)
            else:
                break
        if not consumed:
            break
    state = {"file_offset": offset, "skipping_long_line": int(skipping),
             "long_line_start": long_start}
    return lines, state, used, oversized


def ensure_source(conn, instance, source):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO mail_stats_sources (instance_id,source_key,family,status,coverage,"
            "reason_code,generation,first_seen_at) VALUES (%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(6)) "
            "ON DUPLICATE KEY UPDATE family=VALUES(family)",
            (instance, binary(source["key"]), binary(source["family"]),
             binary(source.get("status", "unavailable")), binary(source.get("coverage", "partial")),
             binary(source.get("reason_code")), generation()),
        )
        cur.execute("SELECT * FROM mail_stats_sources WHERE instance_id=%s AND source_key=%s",
                    (instance, binary(source["key"])))
        return cur.fetchone()


def health(conn, instance, source_id, status, reason=None, success=False):
    with conn.cursor() as cur:
        cur.execute("UPDATE mail_stats_sources SET status=%s,reason_code=%s,"
                    "last_observed_at=UTC_TIMESTAMP(6),"
                    "last_success_at=IF(%s,UTC_TIMESTAMP(6),last_success_at) "
                    "WHERE instance_id=%s AND id=%s",
                    (binary(status), binary(reason), success, instance, source_id))


def correlation_gap(conn, instance, source):
    """A dropped queue record may hide an ID lifetime boundary: fail closed."""
    if source["source_key"] != b"qmail-send":
        return
    source["generation"] = generation()
    with conn.cursor() as cur:
        cur.execute("UPDATE mail_stats_sources SET generation=%s,discontinuities=discontinuities+1 "
                    "WHERE instance_id=%s AND id=%s", (source["generation"], instance, source["id"]))


def file_cursor(conn, instance, source, fd):
    info = os.fstat(fd)
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM mail_stats_files WHERE instance_id=%s AND source_id=%s "
                    "AND device=%s AND inode=%s ORDER BY id DESC LIMIT 1",
                    (instance, source["id"], info.st_dev, info.st_ino))
        row = cur.fetchone()
        if row and valid_checkpoint(fd, row, info.st_size):
            return row
        sealed = row is not None and row["fragment_offset"] is not None
        if row:
            # Rewrites of a known sealed archive remain historical, including
            # when a new technical file generation starts at offset zero.
            if not sealed:
                source["generation"] = generation()
            cur.execute("UPDATE mail_stats_sources SET discontinuities=discontinuities+1,"
                        "generation=%s,coverage='partial',reason_code='file_discontinuity' "
                        "WHERE instance_id=%s AND id=%s",
                        (source["generation"], instance, source["id"]))
        cur.execute("INSERT INTO mail_stats_files (instance_id,source_id,generation,device,inode,"
                    "fragment_offset,fragment_hash,first_seen_at,last_seen_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))",
                    (instance, source["id"], generation(), info.st_dev, info.st_ino,
                     0 if sealed else None, hashlib.sha256(b"").digest() if sealed else None))
        cur.execute("SELECT * FROM mail_stats_files WHERE instance_id=%s AND id=%s",
                    (instance, cur.lastrowid))
        return cur.fetchone()


def save_cursor(cur, instance, row, fd, state):
    offset = state["file_offset"]
    prefix_length = min(CHECK_BYTES, offset)
    check_length = min(CHECK_BYTES, offset)
    prefix = fingerprint(fd, 0, prefix_length)
    checkpoint = fingerprint(fd, offset - check_length, check_length)
    if prefix is None or checkpoint is None:
        raise OSError("Log truncated during collection")
    cur.execute("UPDATE mail_stats_files SET file_offset=%s,checkpoint_offset=%s,"
                "checkpoint_length=%s,checkpoint_hash=%s,prefix_length=%s,prefix_hash=%s,"
                "skipping_long_line=%s,long_line_start=%s,last_seen_at=UTC_TIMESTAMP(6) "
                "WHERE instance_id=%s AND id=%s",
                (offset, offset - check_length, check_length, checkpoint, prefix_length,
                 prefix, state["skipping_long_line"], state["long_line_start"], instance, row["id"]))


def correlate(cur, instance, source, parsed, event, cutoff):
    """Only same-generation, explicit qmail message/attempt identities link.

    A restart deliberately leaves surviving messages orphaned in the new
    generation. Without an upstream lifetime identity, guessing is incorrect.
    """
    action = parsed.get("action")
    when, queue = event["event_at"], event.get("queue_id")
    scope = (instance, source["id"], source["generation"])
    if action == "message_info" and queue:
        cur.execute("UPDATE mail_stats_attempts a JOIN mail_stats_messages m "
                    "ON m.instance_id=a.instance_id AND m.id=a.message_id "
                    "SET a.finished_at=%s,a.outcome='incomplete' WHERE m.instance_id=%s "
                    "AND m.source_id=%s AND m.generation=%s AND m.queue_id=%s "
                    "AND m.finished_at IS NULL AND a.finished_at IS NULL", (when, *scope, queue))
        cur.execute("UPDATE mail_stats_messages SET finished_at=%s WHERE instance_id=%s "
                    "AND source_id=%s AND generation=%s AND queue_id=%s AND finished_at IS NULL",
                    (when, *scope, queue))
        cur.execute("INSERT INTO mail_stats_messages (instance_id,source_id,generation,queue_id,"
                    "started_at,last_event_at,sender,bytes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (*scope, queue, when, when, event.get("sender"), parsed.get("bytes")))
        event["message_id"] = cur.lastrowid
    elif action in ("attempt_start", "message_end"):
        if queue:
            cur.execute("SELECT id FROM mail_stats_messages WHERE instance_id=%s AND source_id=%s "
                        "AND generation=%s AND queue_id=%s AND finished_at IS NULL AND started_at>=%s LIMIT 2",
                        (*scope, queue, cutoff))
            messages = cur.fetchall()
            if len(messages) == 1:
                event["message_id"] = messages[0]["id"]
        if action == "message_end" and event.get("message_id"):
            cur.execute("UPDATE mail_stats_messages SET finished_at=%s,last_event_at=%s "
                        "WHERE instance_id=%s AND id=%s", (when, when, instance, event["message_id"]))
        elif action == "attempt_start" and parsed.get("attempt_key"):
            key = binary(parsed["attempt_key"])
            cur.execute("UPDATE mail_stats_attempts SET finished_at=%s,outcome='incomplete' "
                        "WHERE instance_id=%s AND source_id=%s AND generation=%s "
                        "AND attempt_key=%s AND finished_at IS NULL", (when, *scope, key))
            cur.execute("INSERT INTO mail_stats_attempts (instance_id,source_id,generation,"
                        "attempt_key,message_id,recipient,started_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (*scope, key, event.get("message_id"), event.get("recipient"), when))
            event["attempt_id"] = cur.lastrowid
    elif action == "attempt_result" and parsed.get("attempt_key"):
        cur.execute("SELECT id,message_id,recipient FROM mail_stats_attempts WHERE instance_id=%s "
                    "AND source_id=%s AND generation=%s AND attempt_key=%s "
                    "AND finished_at IS NULL AND started_at>=%s LIMIT 2", (*scope, binary(parsed["attempt_key"]), cutoff))
        attempts = cur.fetchall()
        if len(attempts) == 1:
            attempt = attempts[0]
            event.update(attempt_id=attempt["id"], message_id=attempt["message_id"],
                         recipient=attempt["recipient"])
            cur.execute("UPDATE mail_stats_attempts SET finished_at=%s,outcome=%s "
                        "WHERE instance_id=%s AND id=%s",
                        (when, binary(parsed.get("outcome", "unknown")), instance, attempt["id"]))
            cur.execute("SELECT metadata FROM mail_stats_events WHERE instance_id=%s AND attempt_id=%s "
                        "AND event_type='attempt_started' ORDER BY id LIMIT 2", (instance, attempt["id"]))
            starts = cur.fetchall()
            if len(starts) == 1:
                channel = json.loads(starts[0]["metadata"]).get("delivery_kind")
                if channel in ("local", "remote"):
                    event["metadata"]["delivery_kind"] = channel
                    if event["event_type"] == b"delivery_success":
                        event["event_type"] = binary("delivery_" + channel + "_success")
    if event.get("message_id"):
        cur.execute("SELECT queue_id,sender,bytes FROM mail_stats_messages WHERE instance_id=%s AND id=%s AND started_at>=%s",
                    (instance, event["message_id"], cutoff))
        message = cur.fetchone()
        if message:
            event["queue_id"], event["sender"] = message["queue_id"], message["sender"]
            if event["event_type"] in (b"delivery_local_success", b"delivery_remote_success"):
                event["metadata"]["bytes"] = message["bytes"]
            cur.execute("UPDATE mail_stats_messages SET last_event_at=GREATEST(last_event_at,%s) "
                        "WHERE instance_id=%s AND id=%s", (when, instance, event["message_id"]))
        else:
            event["message_id"] = None
    if action in ("attempt_start", "attempt_result", "message_end") and not event.get("message_id"):
        event["metadata"]["incomplete"] = True


def ingest(conn, instance, source, parsed, cutoff, position, file_id=None, offset=None, digest=None,
           *, allow_correlation=True):
    observed = utcnow()
    metadata = dict(parsed.get("metadata", {}))
    uncertain = parsed.get("event_at") is None or metadata.get("time_uncertain", False)
    if uncertain:
        return  # Unknown age must never resurrect expired nominal information.
    # Keep parser bookkeeping in memory, not repeated in every stored diagnostic.
    for key in ("recognized", "time_format", "time_uncertain"):
        metadata.pop(key, None)
    if metadata.get("subsource") == parsed.get("component"):
        metadata.pop("subsource", None)
    if not allow_correlation:
        metadata.update(incomplete=True, reason_code="late_archive_append")
    event = {key: binary(parsed[key]) for key in ("component", "event_type", "severity", "queue_id",
             "sender", "recipient", "ip", "account") if parsed.get(key) is not None}
    event.update(source_id=source["id"], source_position=position, file_id=file_id, file_offset=offset,
                 generation=source["generation"] if allow_correlation else None, event_at=parsed.get("event_at") or observed,
                 observed_at=observed, parser=b"mail-stats", parser_version=1,
                 line_hash=digest, metadata=metadata)
    event.setdefault("component", source["source_key"])
    event.setdefault("severity", b"info")
    if parsed.get("channel") in ("local", "remote"):
        metadata["delivery_kind"] = parsed["channel"]
    event_id = db.insert_event(conn, instance, event, cutoff)
    if event_id is None and event["event_at"] >= cutoff:
        return  # A replay must not mutate correlations or process generations.
    # Restart is technical state and must advance even for an expired record.
    if allow_correlation and parsed.get("action") == "restart":
        source["generation"] = generation()
        event["generation"] = source["generation"]
        with conn.cursor() as cur:
            cur.execute("UPDATE mail_stats_sources SET generation=%s WHERE instance_id=%s AND id=%s",
                        (source["generation"], instance, source["id"]))
            if event_id is not None:
                cur.execute("UPDATE mail_stats_events SET generation=%s WHERE instance_id=%s AND id=%s",
                            (source["generation"], instance, event_id))
    if event_id is None:
        return
    with conn.cursor() as cur:
        if allow_correlation:
            correlate(cur, instance, source, parsed, event, cutoff)
        cur.execute("UPDATE mail_stats_events SET message_id=%s,attempt_id=%s,event_type=%s,queue_id=%s,"
                    "sender=%s,recipient=%s,metadata=%s WHERE instance_id=%s AND id=%s",
                    (event.get("message_id"), event.get("attempt_id"), event["event_type"],
                     event.get("queue_id"), event.get("sender"), event.get("recipient"),
                     db.encode_metadata(metadata), instance, event_id))
        hour = event["event_at"].replace(minute=0, second=0, microsecond=0)
        if hour >= db.hourly_cutoff(cutoff):
            amount = metadata.get("bytes") if event["event_type"] in (
                b"message_observed", b"delivery_local_success", b"delivery_remote_success") else 0
            cur.execute("INSERT INTO mail_stats_hourly (instance_id,source_id,hour_at,category,count,bytes) "
                        "VALUES (%s,%s,%s,%s,1,%s) ON DUPLICATE KEY UPDATE count=count+1,bytes=bytes+VALUES(bytes)",
                        (instance, source["id"], hour, event["event_type"], amount or 0))
        cur.execute("UPDATE mail_stats_sources SET last_event_at=GREATEST(COALESCE(last_event_at,%s),%s),"
                    "lag_seconds=%s WHERE instance_id=%s AND id=%s",
                    (event["event_at"], event["event_at"],
                     max(0, int((observed - event["event_at"]).total_seconds())), instance, source["id"]))


def collect_file_source(conn, instance, definition, source, cutoff, parse, aliases=None):
    deadline = time.monotonic() + SOURCE_SECONDS
    remaining_bytes, remaining_lines = SOURCE_BYTES, SOURCE_LINES
    found, pending, archive_fragment, late_append = False, False, False, False
    with source_files(definition) as (directory, names):
        for name, device, inode in names:
            if remaining_bytes <= MAX_LINE or remaining_lines <= 0 or time.monotonic() >= deadline:
                pending = True
                break
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                         dir_fd=directory)
            defer_archive = False
            try:
                info = os.fstat(fd)
                if (info.st_dev, info.st_ino) != (device, inode):
                    # Do not read a new current before the old current's archive
                    # has appeared in the next chronological discovery snapshot.
                    raise OSError("Source rotated after discovery")
                if not stat.S_ISREG(info.st_mode):
                    continue
                found = True
                with db.transaction(conn):
                    row = file_cursor(conn, instance, source, fd)
                    # fragment_offset/hash also seals a clean archive EOF (the
                    # hash of an empty tail). Once crossed, later bytes cannot
                    # be ordered before already observed newer current records.
                    allow_correlation = row["fragment_offset"] is None
                    records, state, used, oversized = read_batch(
                        fd, row, remaining_bytes, remaining_lines, deadline)
                    unknown, processed = 0, []
                    gaps = iter(oversized)
                    next_gap = next(gaps, None)
                    for offset, line in records:
                        if processed and time.monotonic() >= deadline:
                            state = dict(file_offset=offset, skipping_long_line=0, long_line_start=None)
                            break
                        while next_gap is not None and next_gap < offset:
                            if allow_correlation:
                                correlation_gap(conn, instance, source)
                            next_gap = next(gaps, None)
                        parsed = parse(definition["key"], line, timezone=None)
                        if parsed is None or parsed.get("event_at") is None or parsed.get("metadata", {}).get("time_uncertain"):
                            unknown += 1
                            if allow_correlation:
                                correlation_gap(conn, instance, source)
                        elif parsed.get("component") != "mail-stats":
                            late_append |= not allow_correlation
                            logical = (aliases or {}).get((definition["key"], parsed.get("component")), source)
                            ingest(conn, instance, logical, parsed, cutoff,
                                   binary(str(row["id"]) + ":" + str(offset)), row["id"], offset,
                                   hashlib.sha256(line).digest(), allow_correlation=allow_correlation)
                            if logical is not source:
                                health(conn, instance, logical["id"], "active", "routed", success=True)
                        processed.append((offset, line))
                    while next_gap is not None and next_gap < state["file_offset"]:
                        if allow_correlation:
                            correlation_gap(conn, instance, source)
                        next_gap = next(gaps, None)
                    oversized = sum(start < state["file_offset"] for start in oversized)
                    unknown += oversized
                    # Check both old identity anchors and every parsed byte before
                    # committing; rename is harmless, destructive rewrites are not.
                    if not valid_checkpoint(fd, row, os.fstat(fd).st_size) or any(
                            os.pread(fd, len(line), offset) != line for offset, line in processed):
                        raise OSError("Log changed during collection")
                    with conn.cursor() as cur:
                        save_cursor(cur, instance, row, fd, state)
                        cur.execute("UPDATE mail_stats_sources SET lines_seen=lines_seen+%s,"
                                    "lines_unknown=lines_unknown+%s WHERE instance_id=%s AND id=%s",
                                    (len(processed) + oversized, unknown, instance, source["id"]))
                    remaining_bytes -= used
                    remaining_lines -= len(processed) + oversized
                    is_archive = name != ("current" if definition["kind"] == "s6" else os.path.basename(definition["path"]))
                    size = os.fstat(fd).st_size
                    if state["file_offset"] < size:
                        pending = True
                        tail = os.pread(fd, MAX_LINE + 1, state["file_offset"])
                        if is_archive and len(tail) <= MAX_LINE and b"\n" not in tail:
                            archive_fragment = True
                            digest = hashlib.sha256(tail).digest()
                            if row["fragment_offset"] != state["file_offset"] or row["fragment_hash"] != digest:
                                if allow_correlation:
                                    correlation_gap(conn, instance, source)
                                with conn.cursor() as cur:
                                    cur.execute("UPDATE mail_stats_files SET fragment_offset=%s,fragment_hash=%s "
                                                "WHERE instance_id=%s AND id=%s",
                                                (state["file_offset"], digest, instance, row["id"]))
                        elif is_archive:
                            # Growth after the read snapshot can leave complete
                            # unread records. Do not cross them into newer files.
                            defer_archive = True
                    elif is_archive and allow_correlation:
                        # Seal only archives, never current: a just-rotated
                        # current must first finish its legitimate continuation.
                        with conn.cursor() as cur:
                            cur.execute("UPDATE mail_stats_files SET fragment_offset=%s,fragment_hash=%s "
                                        "WHERE instance_id=%s AND id=%s",
                                        (state["file_offset"], hashlib.sha256(b"").digest(), instance, row["id"]))
            finally:
                os.close(fd)
            if defer_archive:
                break
    health(conn, instance, source["id"], "active" if found else "unavailable",
           "archive_fragment" if archive_fragment else "late_archive_append" if late_append else (
               "backlog_or_partial_line" if pending else (None if found else "no_files")), success=found)


def purge(conn, instance, cutoff):
    source = ensure_source(conn, instance, {"key": "retention", "family": "maintenance"})
    health(conn, instance, source["id"], "active", "purge_pending")
    deadline = time.monotonic() + PURGE_SECONDS
    for _ in range(PURGE_BATCHES):
        counts = db.purge_batch(conn, instance, cutoff, 500)
        if not any(counts.values()) or time.monotonic() >= deadline:
            break
    pending = False
    with conn.cursor() as cur:
        for table, column, boundary in (("events", "event_at", cutoff),
                                       ("hourly", "hour_at", db.hourly_cutoff(cutoff)),
                                       ("attempts", "started_at", cutoff),
                                       ("messages", "started_at", cutoff)):
            cur.execute(f"SELECT id FROM mail_stats_{table} WHERE instance_id=%s AND {column}<%s LIMIT 1",
                        (instance, boundary))
            pending |= cur.fetchone() is not None
    health(conn, instance, source["id"], "active", "purge_pending" if pending else None,
           success=not pending)


def collect_dmarc(conn, instance, source, cutoff):
    """Observe bounded revisions of the audited mutable table, never raw logs.

    ID pagination wraps to observe updates to older IDs. These observations do
    not assert a complete report history; upstream updates/deletions can occur
    between scans. Hashes contain only timestamp and numeric verdict/source.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT COLUMN_NAME,DATA_TYPE,COLUMN_TYPE,IS_NULLABLE,EXTRA FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='dmarc_reportlog' "
                    "AND COLUMN_NAME IN ('id','event_time','source','success')")
        columns = {row["COLUMN_NAME"]: row for row in cur.fetchall()}
        if (set(columns) != {"id", "event_time", "source", "success"} or
                columns["event_time"]["DATA_TYPE"] != "datetime" or
                any(row["IS_NULLABLE"] != "NO" for row in columns.values()) or
                columns["id"]["DATA_TYPE"] != "int" or "unsigned" not in columns["id"]["COLUMN_TYPE"] or
                "auto_increment" not in columns["id"]["EXTRA"] or
                columns["source"]["DATA_TYPE"] != "tinyint" or "unsigned" not in columns["source"]["COLUMN_TYPE"] or
                columns["success"]["DATA_TYPE"] != "tinyint"):
            health(conn, instance, source["id"], "unavailable", "upstream_schema_unverified")
            return
    position, highwater = map(int, (source["sql_cursor"] or b"0:0").split(b":"))
    deadline = time.monotonic() + SOURCE_SECONDS
    with db.transaction(conn), conn.cursor() as cur:
        if highwater == 0:
            cur.execute("SELECT COALESCE(MAX(id),0) AS highwater FROM dmarc_reportlog")
            highwater = cur.fetchone()["highwater"]
        cur.execute("SELECT id,event_time,source,success FROM dmarc_reportlog WHERE id>%s AND id<=%s ORDER BY id LIMIT 100",
                    (position, highwater))
        rows = cur.fetchall()
        processed = 0
        for row in rows:
            if processed and time.monotonic() >= deadline:
                break
            processed += 1
            position = row["id"]
            if not isinstance(row["event_time"], datetime) or row["source"] not in (1, 2, 3, 4) or row["success"] not in (0, 1):
                continue
            signature = hashlib.sha256((row["event_time"].isoformat() + ":" + str(row["source"]) +
                                        ":" + str(row["success"])).encode("ascii")).digest()
            cur.execute("SELECT id,prefix_hash FROM mail_stats_files WHERE instance_id=%s AND source_id=%s "
                        "AND device=0 AND inode=%s AND generation='sql-v1'", (instance, source["id"], position))
            previous = cur.fetchone()
            if previous and previous["prefix_hash"] == signature:
                continue
            parsed = dict(event_at=row["event_time"], event_type="dmarc_observed", component="dmarc",
                          severity="info" if row["success"] else "warning",
                          metadata={"outcome": "success" if row["success"] else "failure",
                                    "direction": {1: "upload", 2: "mailbox", 3: "directory", 4: "remote"}[row["source"]]})
            ingest(conn, instance, source, parsed, cutoff,
                   binary("sql:" + str(position) + ":" + signature.hex()))
            cur.execute("INSERT INTO mail_stats_files (instance_id,source_id,generation,device,inode,prefix_hash,"
                        "first_seen_at,last_seen_at) VALUES (%s,%s,'sql-v1',0,%s,%s,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6)) "
                        "ON DUPLICATE KEY UPDATE prefix_hash=VALUES(prefix_hash),last_seen_at=UTC_TIMESTAMP(6)",
                        (instance, source["id"], position, signature))
        complete = processed == len(rows) and (len(rows) < 100 or position >= highwater)
        next_cursor = b"0:0" if complete else binary(str(position) + ":" + str(highwater))
        cur.execute("UPDATE mail_stats_sources SET sql_cursor=%s,coverage='state_observed' "
                    "WHERE instance_id=%s AND id=%s", (next_cursor, instance, source["id"]))
        health(conn, instance, source["id"], "active", "mutable_snapshot_not_history", success=True)


def collect(conn, config, registry=None, parse=None):
    """One fair bounded cycle. Caller owns the local lock; SQL lock spans cycle."""
    if not config["enabled"]:
        return
    if registry is None:
        from .sources import SOURCES
        registry = SOURCES
    if parse is None:
        from .parsers import parse
    instance = binary(config["instance_id"])
    with db.instance_lock(conn, instance):
        db.verify_schema(conn)
        cutoff = db.retention_cutoff(conn, config["history_months"])
        purge(conn, instance, cutoff)
        sources = {definition["key"]: ensure_source(conn, instance, definition)
                   for definition in registry if definition["key"] != "retention"}
        aliases = {}
        for definition in registry:
            if definition.get("routed_via"):
                component = "vpopmail" if definition["key"] == "vpopmail-auth" else definition["key"]
                aliases[(definition["routed_via"], component)] = sources[definition["key"]]
        for definition in registry:
            if definition["key"] == "retention" or definition.get("routed_via"):
                continue  # Synthetic health only; never ingest our own output.
            source = sources[definition["key"]]
            try:
                if definition["kind"] in ("s6", "file"):
                    collect_file_source(conn, instance, definition, source, cutoff, parse, aliases)
                elif definition["kind"] == "sql" and definition["key"] == "dmarc":
                    collect_dmarc(conn, instance, source, cutoff)
                else:
                    health(conn, instance, source["id"], definition.get("status", "unavailable"),
                           definition.get("reason_code", "not_historical"))
            except (FileNotFoundError, NotADirectoryError):
                health(conn, instance, source["id"], "unavailable", "source_absent")
            except Exception:
                # Do not log exceptions: database errors and log parser errors
                # can include credentials or raw input. Other sources still run.
                conn.rollback()
                health(conn, instance, source["id"], "error", "collection_failed")
        for definition in registry:
            if definition.get("routed_via") not in sources:
                continue
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM mail_stats_sources WHERE instance_id=%s AND id=%s",
                            (instance, sources[definition["routed_via"]]["id"]))
                route_status = cur.fetchone()["status"]
                cur.execute("SELECT last_event_at FROM mail_stats_sources WHERE instance_id=%s AND id=%s",
                            (instance, sources[definition["key"]]["id"]))
                observed = cur.fetchone()["last_event_at"] is not None
            health(conn, instance, sources[definition["key"]]["id"],
                   route_status if route_status in (b"error", b"unavailable") else ("active" if observed else "conditional"),
                   "route_unavailable" if route_status in (b"error", b"unavailable") else definition.get("reason_code", "routed"))


def main():
    from .config import load_private
    try:
        config = load_private()
        if not config["enabled"]:
            return 0
        with local_lock():
            conn = db.connect(config["database"])
            try:
                collect(conn, config)
            finally:
                conn.close()
        return 0
    except db.LockBusy:
        return 0
    except Exception:
        # Fixed diagnostic only. Parser ignores this to avoid self-ingestion.
        os.write(2, b"mail-stats collector unavailable\n")
        return 1
