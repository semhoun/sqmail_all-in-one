"""MySQL/MariaDB foundation. Callers own correlation and ingestion transactions.

Identifiers are bytes, UTC datetimes are naive, and SQL cursors contain only
technical positions (never upstream row contents). No helper reconnects a lost
connection: doing so would silently lose transactions and advisory locks.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re

import pymysql
from pymysql.constants.SERVER_STATUS import SERVER_STATUS_IN_TRANS


SCHEMA_VERSION = 1
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "sql" / "mail-stats.sql"
TABLES = ("schema", "sources", "files", "messages", "attempts", "events", "hourly")
METADATA_KEYS = frozenset({
    "outcome", "protocol", "direction", "delivery_kind", "bytes", "duration_ms",
    "smtp_code", "enhanced_status", "http_status", "method", "score", "threshold",
    "verdict", "signature", "reason_code", "tls_version", "cipher", "action",
    "service", "subsource", "recognized", "incomplete", "exit_code",
    "time_uncertain", "time_format", "count",
})
EVENT_COLUMNS = (
    "source_id", "file_id", "file_offset", "source_position", "generation",
    "message_id", "attempt_id", "event_at", "observed_at", "component",
    "event_type", "severity", "parser", "parser_version", "line_hash", "queue_id",
    "sender", "recipient", "ip", "account", "metadata",
)
BINARY_LENGTHS = {
    "source_position": 255, "generation": 64, "component": 64, "event_type": 64,
    "severity": 16, "parser": 64, "line_hash": 32, "queue_id": 128,
    "sender": 320, "recipient": 320, "ip": 45, "account": 320,
}


class SchemaError(RuntimeError):
    """The component schema is missing, incompatible, or from another version."""


class LockBusy(RuntimeError):
    """Another connection owns this installation's collector lock."""


def connect(config):
    """Open a reusable strict UTC connection from an already trusted mapping.

    Required keys: host, user, password, database. Optional: port, unix_socket,
    connect_timeout, read_timeout, write_timeout (positive seconds, max 300).
    Credentials are never formatted into SQL or exception messages here.
    """
    options = {key: config[key] for key in ("host", "user", "password", "database")}
    options["port"] = int(config.get("port", 3306))
    if not 1 <= options["port"] <= 65535:
        raise ValueError("Invalid SQL port")
    if config.get("unix_socket"):
        options["unix_socket"] = config["unix_socket"]
    for key, default in (("connect_timeout", 5), ("read_timeout", 15), ("write_timeout", 15)):
        value = config.get(key, default)
        if type(value) is not int or not 1 <= value <= 300:
            raise ValueError("Invalid SQL timeout")
        options[key] = value
    connection = pymysql.connect(
        **options, charset="utf8mb4", autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
        sql_mode="STRICT_ALL_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION",
        init_command="SET time_zone = '+00:00'", local_infile=False,
    )
    return connection


def _binary(value, name, maximum=64):
    if not isinstance(value, bytes) or not 1 <= len(value) <= maximum:
        raise ValueError(f"{name} must be nonempty bytes of at most {maximum} bytes")
    return value


def _datetime(value):
    if not isinstance(value, datetime) or value.tzinfo is not None:
        raise ValueError("Expected a naive UTC datetime")
    return value


@contextmanager
def transaction(connection):
    """Commit on success, roll back on error. Do not nest or perform DDL here."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        if connection.server_status & SERVER_STATUS_IN_TRANS:
            raise RuntimeError("Nested transactions are not supported")
    connection.begin()
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


@contextmanager
def _lock(connection, name):
    with connection.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK(%s, 0) AS acquired", (name,))
        if cursor.fetchone()["acquired"] != 1:
            raise LockBusy("Mail statistics SQL lock unavailable")
    try:
        yield connection
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (name,))


@contextmanager
def instance_lock(connection, instance_id):
    """Server-wide instance lock; independent of commit/rollback, never waits."""
    _binary(instance_id, "instance_id")
    name = "mail-stats:instance:" + hashlib.sha256(instance_id).hexdigest()[:40]
    with _lock(connection, name):
        yield connection


def _definitions(schema_path=None):
    """Read our deliberately simple, trusted DDL as the verification manifest."""
    text = Path(schema_path or SCHEMA_PATH).read_text(encoding="ascii")
    text = re.sub(r"--[^\n]*", "", text)
    definitions = {}
    for statement in text.split(";"):
        if not statement.strip():
            continue
        match = re.fullmatch(
            r"\s*CREATE TABLE IF NOT EXISTS (mail_stats_[a-z]+) \((.*)\) "
            r"ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci\s*",
            statement, re.S,
        )
        if not match:
            raise SchemaError("Invalid bundled schema definition")
        name, body = match.groups()
        columns, indexes = {}, {}
        for line in body.strip().splitlines():
            line = line.strip().rstrip(",")
            index = re.fullmatch(r"(PRIMARY KEY|UNIQUE KEY (\w+)|KEY (\w+)) \(([^)]+)\)", line)
            if index:
                kind, unique, ordinary, names = index.groups()
                indexes[unique or ordinary or "PRIMARY"] = (
                    1 if ordinary else 0, tuple(names.split(", ")),
                )
                continue
            column = re.fullmatch(
                r"(\w+) ([A-Z]+(?:\(\d+\))?(?: UNSIGNED)?) (NOT NULL|NULL)"
                r"( AUTO_INCREMENT)?(?: DEFAULT (\d+))?", line,
            )
            if not column:
                raise SchemaError("Invalid bundled column definition")
            key, data_type, nullable, auto, default = column.groups()
            columns[key] = (data_type.lower(), nullable == "NULL", default,
                            "auto_increment" if auto else "",
                            "utf8mb4_unicode_ci" if data_type == "TEXT" else None)
        definitions[name] = (statement.strip(), columns, indexes)
    if set(definitions) != {"mail_stats_" + name for name in TABLES}:
        raise SchemaError("Incomplete bundled schema definition")
    return definitions


def _verify_tables(connection, definitions, allow_missing=False):
    with connection.cursor() as cursor:
        for table, (_, columns, indexes) in definitions.items():
            cursor.execute(
                "SELECT ENGINE, TABLE_COLLATION FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s", (table,),
            )
            actual_table = cursor.fetchone()
            if actual_table is None and allow_missing:
                continue
            if actual_table != {"ENGINE": "InnoDB", "TABLE_COLLATION": "utf8mb4_unicode_ci"}:
                raise SchemaError(f"Incompatible or missing table: {table}")
            cursor.execute(
                "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA, "
                "COLLATION_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION", (table,),
            )
            actual_columns = {}
            for row in cursor.fetchall():
                # MariaDB retains integer display widths and spells NULL defaults.
                data_type = re.sub(r"\b(tinyint|bigint)\(\d+\)", r"\1", row["COLUMN_TYPE"].lower())
                default = row["COLUMN_DEFAULT"]
                if default == "NULL" and "MariaDB" in connection.get_server_info():
                    default = None
                actual_columns[row["COLUMN_NAME"]] = (
                    data_type, row["IS_NULLABLE"] == "YES",
                    str(default) if default is not None else None,
                    row["EXTRA"].lower(), row["COLLATION_NAME"],
                )
            if actual_columns != columns or list(actual_columns) != list(columns):
                raise SchemaError(f"Incompatible columns: {table}")
            cursor.execute(
                "SELECT INDEX_NAME, NON_UNIQUE, COLUMN_NAME, SUB_PART, INDEX_TYPE, COLLATION "
                "FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s ORDER BY INDEX_NAME, SEQ_IN_INDEX", (table,),
            )
            actual_indexes = {}
            for row in cursor.fetchall():
                if row["SUB_PART"] is not None or row["INDEX_TYPE"] != "BTREE" or row["COLLATION"] != "A":
                    raise SchemaError(f"Incompatible index: {table}")
                key = row["INDEX_NAME"]
                unique, names = actual_indexes.get(key, (row["NON_UNIQUE"], ()))
                actual_indexes[key] = (unique, names + (row["COLUMN_NAME"],))
            if actual_indexes != indexes:
                raise SchemaError(f"Incompatible indexes: {table}")
            cursor.execute(f"SHOW INDEX FROM {table}")
            if any(row.get("Visible", "YES") != "YES" or row.get("Ignored", "NO") != "NO"
                   for row in cursor.fetchall()):
                raise SchemaError(f"Disabled index: {table}")
            cursor.execute(
                "SELECT CONSTRAINT_TYPE FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s "
                "AND CONSTRAINT_TYPE NOT IN ('PRIMARY KEY', 'UNIQUE')", (table,),
            )
            if cursor.fetchone():
                raise SchemaError(f"Unexpected constraints: {table}")
            cursor.execute(
                "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS "
                "WHERE TRIGGER_SCHEMA=DATABASE() AND EVENT_OBJECT_TABLE=%s", (table,),
            )
            if cursor.fetchone():
                raise SchemaError(f"Unexpected triggers: {table}")


def _version(connection, allow_empty=False):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, version FROM mail_stats_schema")
        rows = cursor.fetchall()
    if not rows and allow_empty:
        return
    if rows != [{"id": 1, "version": SCHEMA_VERSION}]:
        raise SchemaError("Unsupported mail statistics schema version")


def verify_schema(connection, schema_path=None):
    """Require exact tables, columns, indexes, constraints and version."""
    _verify_tables(connection, _definitions(schema_path))
    _version(connection)


def install_schema(connection, schema_path=None):
    """Resume compatible partial DDL; never repair/overwrite incompatible tables.

    DDL implicitly commits. Use a dedicated autocommit connection, outside any
    ingestion transaction. A schema-scoped SQL lock serializes installers.
    """
    definitions = _definitions(schema_path)
    with connection.cursor() as cursor:
        cursor.execute("SELECT DATABASE() AS db")
        state = cursor.fetchone()
    if connection.server_status & SERVER_STATUS_IN_TRANS or not connection.get_autocommit():
        raise RuntimeError("Schema installation requires idle autocommit connection")
    name = "mail-stats:schema:" + hashlib.sha256(state["db"].encode()).hexdigest()[:40]
    with _lock(connection, name):
        _verify_tables(connection, definitions, allow_missing=True)
        with connection.cursor() as cursor:
            cursor.execute("SHOW TABLES LIKE 'mail\\_stats\\_schema'")
            if cursor.fetchone():
                _version(connection, allow_empty=True)
            for statement, _, _ in definitions.values():
                cursor.execute(statement)
        _verify_tables(connection, definitions)
        _version(connection, allow_empty=True)
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO mail_stats_schema (id, version, installed_at) "
                "SELECT 1, %s, UTC_TIMESTAMP(6) WHERE NOT EXISTS (SELECT 1 FROM mail_stats_schema)",
                (SCHEMA_VERSION,),
            )
        _version(connection)


def retention_cutoff(connection, months):
    """Compute one calendar-month UTC boundary, reusable for the entire cycle."""
    if isinstance(months, str) and re.fullmatch(r"[0-9]{1,3}", months):
        months = int(months)
    if type(months) is not int or not 1 <= months <= 120:
        raise ValueError("History months must be a decimal integer from 1 to 120")
    with connection.cursor() as cursor:
        cursor.execute("SELECT UTC_TIMESTAMP(6) - INTERVAL %s MONTH AS cutoff", (months,))
        return cursor.fetchone()["cutoff"]


def hourly_cutoff(cutoff):
    """First entirely retained hour; excludes a bucket overlapping the boundary."""
    _datetime(cutoff)
    floor = cutoff.replace(minute=0, second=0, microsecond=0)
    return floor if cutoff == floor else floor + timedelta(hours=1)


def encode_metadata(metadata):
    """Only bounded flat structured fields. Parsers must redact field contents."""
    if not isinstance(metadata, dict) or not set(metadata) <= METADATA_KEYS:
        raise ValueError("Unsupported event metadata")
    for value in metadata.values():
        if value is not None and type(value) not in (str, int, float, bool):
            raise ValueError("Metadata values must be scalar")
        if isinstance(value, str) and (len(value) > 256 or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            raise ValueError("Invalid metadata text")
    encoded = json.dumps(metadata, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    if len(encoded) > 4096:
        raise ValueError("Event metadata exceeds size limit")
    return encoded


def insert_event(connection, instance_id, event, cutoff):
    """Insert without committing; return new id, or None for expired/duplicate.

    Call inside the same transaction as aggregates/correlation/checkpoints;
    increment aggregates only for a returned id. Duplicate positions never mutate
    an existing event. `metadata` is a dict; technical text fields are bytes.
    """
    _binary(instance_id, "instance_id")
    _datetime(cutoff)
    if not isinstance(event, dict) or not set(event) <= set(EVENT_COLUMNS):
        raise ValueError("Unsupported event fields")
    for key in ("source_id", "source_position", "event_at", "observed_at", "component",
                "event_type", "severity", "parser", "parser_version"):
        if event.get(key) is None:
            raise ValueError(f"Missing event field: {key}")
    _datetime(event["event_at"])
    _datetime(event["observed_at"])
    for key, maximum in BINARY_LENGTHS.items():
        if event.get(key) is not None:
            _binary(event[key], key, maximum)
    if (event.get("file_id") is None) != (event.get("file_offset") is None):
        raise ValueError("File identity and offset must be provided together")
    metadata = encode_metadata(event.get("metadata", {}))
    if event["event_at"] < cutoff:
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        if not connection.server_status & SERVER_STATUS_IN_TRANS:
            raise RuntimeError("Event insertion requires an explicit transaction")
        for key, table in (("source_id", "sources"), ("file_id", "files"),
                           ("message_id", "messages"), ("attempt_id", "attempts")):
            if event.get(key) is None:
                continue
            cursor.execute(f"SELECT id FROM mail_stats_{table} WHERE instance_id=%s AND id=%s",
                           (instance_id, event[key]))
            parent = cursor.fetchone()
            if parent is None:
                raise ValueError("Invalid event reference")
        values = [metadata if key == "metadata" else event.get(key) for key in EVENT_COLUMNS]
        try:
            cursor.execute(
                "INSERT INTO mail_stats_events (instance_id," + ",".join(EVENT_COLUMNS) + ") "
                "VALUES (" + ",".join(["%s"] * (len(EVENT_COLUMNS) + 1)) + ")",
                [instance_id, *values],
            )
        except pymysql.err.IntegrityError as error:
            if error.args[0] != 1062:
                raise
            return None
        return cursor.lastrowid


def purge_batch(connection, instance_id, cutoff, limit=500):
    """One bounded pass; caller holds instance_lock on this idle connection.

    Each delete/unlink touches at most limit rows and commits separately. Parents
    with remaining children survive until a later pass; no dangling references,
    cascades, or huge fanout transaction. Sources/files are never age-purged.
    Return affected counts, including unlink work; repeat only within a time budget.
    """
    _binary(instance_id, "instance_id")
    _datetime(cutoff)
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise ValueError("Purge batch limit must be from 1 to 10000")
    name = "mail-stats:instance:" + hashlib.sha256(instance_id).hexdigest()[:40]
    with connection.cursor() as cursor:
        cursor.execute("SELECT IS_USED_LOCK(%s)=CONNECTION_ID() AS owned", (name,))
        if cursor.fetchone()["owned"] != 1:
            raise LockBusy("Purge requires the instance SQL lock")
    if connection.server_status & SERVER_STATUS_IN_TRANS or not connection.get_autocommit():
        raise RuntimeError("Purge requires idle autocommit connection")
    counts = {}
    for table, column, boundary in (("events", "event_at", cutoff),
                                     ("hourly", "hour_at", hourly_cutoff(cutoff))):
        with transaction(connection), connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM mail_stats_{table} WHERE instance_id=%s "
                           f"AND {column}<%s ORDER BY {column}, id LIMIT %s",
                           (instance_id, boundary, limit))
            counts[table] = cursor.rowcount
    for table, children in (("attempts", (("events", "attempt_id"),)),
                            ("messages", (("events", "message_id"), ("attempts", "message_id")))):
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT id FROM mail_stats_{table} WHERE instance_id=%s "
                           "AND started_at<%s ORDER BY started_at, id LIMIT %s",
                           (instance_id, cutoff, limit))
            ids = [row["id"] for row in cursor.fetchall()]
        counts[table] = 0
        if not ids:
            continue
        slots = ",".join(["%s"] * len(ids))
        for child, link in children:
            with transaction(connection), connection.cursor() as cursor:
                cursor.execute(f"UPDATE mail_stats_{child} SET {link}=NULL WHERE instance_id=%s "
                               f"AND {link} IN ({slots}) LIMIT %s", (instance_id, *ids, limit))
                counts[f"{child}.{link}"] = cursor.rowcount
        conditions = "".join(
            f" AND NOT EXISTS (SELECT 1 FROM mail_stats_{child} c WHERE "
            f"c.instance_id=mail_stats_{table}.instance_id AND c.{link}=mail_stats_{table}.id)"
            for child, link in children
        )
        with transaction(connection), connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM mail_stats_{table} WHERE instance_id=%s "
                           f"AND id IN ({slots})" + conditions, (instance_id, *ids))
            counts[table] = cursor.rowcount
    return counts
