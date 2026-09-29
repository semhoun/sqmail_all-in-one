#!/usr/bin/env python3
"""Collector tests in UUID-owned Docker/tmpfs databases only, never host logs.

python3 tests/mail-stats-collector.py --database-image mariadb:latest
python3 tests/mail-stats-collector.py --database-image mysql:8.4
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid


def inside():
    sys.path.insert(0, "/opt/lib")
    from mail_stats import collector as c, db
    import pymysql

    database_config = dict(host="db", user="stats", password="SyntheticStats927", database="stats")
    deadline = time.monotonic() + 120
    while True:
        try:
            conn = db.connect(database_config)
            break
        except pymysql.err.OperationalError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)
    db.install_schema(conn)

    def parse(key, line, timezone=None):
        record = json.loads(line)
        if record is None:
            return None
        if record.get("event_at"):
            record["event_at"] = datetime.fromisoformat(record["event_at"])
        return record

    class CollectorTests(unittest.TestCase):
        def setUp(self):
            self.temp = tempfile.TemporaryDirectory()
            self.root = Path(self.temp.name)
            self.current = self.root / "current"
            self.config = dict(enabled=True, history_months=6, instance_id=uuid.uuid4().hex,
                               database=database_config)
            self.instance = self.config["instance_id"].encode()
            self.registry = [dict(key="qmail-send", family="transport", kind="s6", path=str(self.root))]
            self.now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)

        def tearDown(self):
            self.temp.cleanup()

        def sql(self, statement, args=()):
            with conn.cursor() as cur:
                cur.execute(statement, args)
                return cur.fetchall()

        def rows(self, table):
            return self.sql("SELECT * FROM mail_stats_" + table + " WHERE instance_id=%s ORDER BY id", (self.instance,))

        def record(self, kind="service_started", **changes):
            value = dict(event_at=self.now.isoformat(), event_type=kind, component="qmail-send",
                         severity="info", metadata={})
            value.update(changes)
            return json.dumps(value).encode() + b"\n"

        def run_cycle(self, parser=parse):
            c.collect(conn, self.config, self.registry, parser)

        def test_complete_lines_and_duplicate_text(self):
            line = self.record()
            self.current.write_bytes(line * 2 + line[:30])
            self.run_cycle()
            self.assertEqual(len(self.rows("events")), 2)
            self.assertEqual(self.rows("files")[0]["file_offset"], len(line) * 2)
            self.current.write_bytes(line * 3)
            self.run_cycle()
            self.run_cycle()
            self.assertEqual(len(self.rows("events")), 3)
            self.assertEqual(sum(row["count"] for row in self.rows("hourly")), 3)

        def test_diagnostics_drop_bookkeeping_not_useful_values_or_history(self):
            useful = {"reason_code": "late_archive_append", "incomplete": True,
                      "exit_code": 0, "bytes": 0, "protocol": "smtp", "score": 0,
                      "threshold": 5, "delivery_kind": "local"}
            noisy = dict(useful, recognized=True, time_uncertain=False,
                         time_format="s6-utc", subsource="qmail-send")
            line = self.record("service_error", metadata=noisy)
            self.current.write_bytes(line)
            self.run_cycle()
            event = self.rows("events")[0]
            self.assertEqual(json.loads(event["metadata"]), useful)
            self.assertLess(len(event["metadata"]), len(json.dumps(noisy)))
            self.assertEqual(sum(row["count"] for row in self.rows("hourly")), 1)
            self.assertEqual(self.rows("files")[0]["file_offset"], len(line))
            # Existing retained rows are not rewritten or removed by this policy.
            self.sql("UPDATE mail_stats_events SET metadata=%s WHERE id=%s AND instance_id=%s",
                     (json.dumps(noisy), event["id"], self.instance))
            self.current.write_bytes(line * 2)
            self.run_cycle()
            self.run_cycle()
            events = self.rows("events")
            self.assertEqual(len(events), 2)
            self.assertEqual(json.loads(events[0]["metadata"]), noisy)
            self.assertEqual(json.loads(events[1]["metadata"]), useful)
            self.assertEqual(sum(row["count"] for row in self.rows("hourly")), 2)

        def test_distinct_diagnostic_subsource_is_preserved(self):
            self.current.write_bytes(self.record(metadata={"subsource": "worker", "outcome": "failure"}))
            self.run_cycle()
            self.assertEqual(json.loads(self.rows("events")[0]["metadata"]),
                             {"subsource": "worker", "outcome": "failure"})

        def test_uncertain_clock_is_rejected_before_diagnostic_minimization(self):
            with patch.object(db, "insert_event", side_effect=AssertionError("Uncertain event was persisted")):
                for event_at, uncertain in ((self.now, True), (None, False)):
                    c.ingest(conn, self.instance, {},
                             {"event_at": event_at, "metadata": {"time_uncertain": uncertain}},
                             self.now - timedelta(days=180), b"uncertain")
            self.assertFalse(self.rows("events"))

        def test_rollback_before_commit_and_resume(self):
            self.current.write_bytes(self.record("message_observed", action="message_info", queue_id="12", bytes=9,
                                                 sender="sender@example.invalid", metadata={"bytes": 9}))
            with patch.object(c, "save_cursor", side_effect=RuntimeError("synthetic crash")):
                self.run_cycle()
            for table in ("events", "messages", "hourly", "files"):
                self.assertFalse(self.rows(table), table)
            self.run_cycle()
            self.run_cycle()
            for table in ("events", "messages", "hourly", "files"):
                self.assertEqual(len(self.rows(table)), 1, table)

        def test_rotation_rename_identity(self):
            line = self.record()
            self.current.write_bytes(line)
            self.run_cycle()
            self.current.rename(self.root / ("@" + "1" * 24 + ".s"))
            self.current.write_bytes(line)
            self.run_cycle()
            self.run_cycle()
            self.assertEqual(len(self.rows("events")), 2)
            self.assertEqual(len(self.rows("files")), 2)

        def test_concurrent_rotation_keeps_descriptor(self):
            line = self.record()
            self.current.write_bytes(line)
            rotated = False

            def rotating(key, data, timezone=None):
                nonlocal rotated
                if not rotated:
                    self.current.rename(self.root / ("@" + "2" * 24 + ".s"))
                    self.current.write_bytes(line)
                    rotated = True
                return parse(key, data)

            self.run_cycle(rotating)
            self.run_cycle()
            self.assertEqual(len(self.rows("events")), 2)
            self.assertEqual(len(self.rows("files")), 2)

        def test_truncate_regrow_and_checkpoint_mismatch(self):
            line = self.record()
            self.current.write_bytes(line * 4)
            self.run_cycle()
            self.current.write_bytes(self.record("service_stopped") * 5)
            self.run_cycle()
            self.assertEqual(len(self.rows("events")), 9)
            self.assertEqual(len(self.rows("files")), 2)
            source = [r for r in self.rows("sources") if r["source_key"] == b"qmail-send"][0]
            self.assertEqual(source["discontinuities"], 1)
            # Simulate a recycled inode with a stale technical checkpoint.
            self.sql("UPDATE mail_stats_files SET checkpoint_hash=%s WHERE instance_id=%s",
                     (b"x" * 32, self.instance))
            self.run_cycle()
            self.assertEqual(len(self.rows("files")), 3)

        def test_oversize_progress_and_partial_skip_resume(self):
            self.current.write_bytes(b"x" * (c.SOURCE_BYTES * 2))
            self.run_cycle()
            first = self.rows("files")[0]
            self.assertTrue(first["skipping_long_line"])
            self.assertGreater(first["file_offset"], 0)
            with self.current.open("ab") as stream:
                stream.write(b"\n" + self.record())
            for _ in range(4):
                self.run_cycle()
            self.assertEqual(len(self.rows("events")), 1)
            self.assertFalse(self.rows("files")[0]["skipping_long_line"])
            source = [r for r in self.rows("sources") if r["source_key"] == b"qmail-send"][0]
            self.assertEqual(source["lines_unknown"], 1)

        def test_symlinks_and_nonregular_files_rejected(self):
            outside = self.root / "secret"
            outside.write_bytes(self.record())
            self.current.symlink_to(outside)
            self.run_cycle()
            self.assertFalse(self.rows("events"))
            self.current.unlink()
            os.mkfifo(self.current)
            self.run_cycle()
            self.assertFalse(self.rows("events"))

        def test_source_failure_and_busy_source_do_not_starve_peer(self):
            other = self.root / "peer"
            other.mkdir()
            (other / "current").write_bytes(self.record())
            self.registry.append(dict(key="clamd", family="filtering", kind="s6", path=str(other)))
            self.current.write_bytes(b"not json\n")
            self.run_cycle()
            self.assertEqual(len(self.rows("events")), 1)
            self.current.write_bytes(self.record() * 2000)
            with (other / "current").open("ab") as stream:
                stream.write(self.record())
            with patch.object(c, "SOURCE_LINES", 5):
                self.run_cycle()
            self.assertEqual(len(self.rows("events")), 7)

        def test_qmail_attempts_restart_and_queue_reuse(self):
            records = [
                self.record("message_observed", action="message_info", queue_id="7", bytes=42, metadata={"bytes": 42}),
                self.record("attempt_started", action="attempt_start", queue_id="7", attempt_key="1",
                            channel="local", recipient="one@example.invalid"),
                self.record("delivery_success", action="attempt_result", attempt_key="1", outcome="success"),
                self.record("attempt_started", action="attempt_start", queue_id="7", attempt_key="2",
                            channel="remote", recipient="two@example.invalid"),
                self.record("delivery_deferral", action="attempt_result", attempt_key="2", outcome="deferral"),
                self.record("message_finished", action="message_end", queue_id="7"),
                self.record("message_observed", action="message_info", queue_id="7", bytes=9, metadata={"bytes": 9}),
                self.record("attempt_started", action="attempt_start", queue_id="7", attempt_key="3", channel="remote"),
                self.record("service_stopped", action="restart"),
                self.record("delivery_success", action="attempt_result", attempt_key="3", outcome="success"),
            ]
            self.current.write_bytes(b"".join(records))
            self.run_cycle()
            events = self.rows("events")
            self.assertEqual(len(self.rows("messages")), 2)
            self.assertEqual(len(self.rows("attempts")), 3)
            self.assertEqual(events[2]["event_type"], b"delivery_local_success")
            self.assertEqual(events[2]["message_id"], events[0]["message_id"])
            self.assertNotEqual(events[6]["message_id"], events[0]["message_id"])
            self.assertIsNone(events[-1]["message_id"])
            self.assertIsNone(events[-1]["attempt_id"])
            self.assertEqual(events[-1]["event_type"], b"delivery_success")
            self.assertEqual(sum(row["bytes"] for row in self.rows("hourly") if row["category"] == b"message_observed"), 51)

        def test_unknown_age_and_expired_events_never_resurrect(self):
            self.current.write_bytes(self.record(event_at=None, sender="old@example.invalid") +
                                     self.record(event_at=(self.now - timedelta(days=800)).isoformat()))
            self.run_cycle()
            self.assertFalse(self.rows("events"))
            self.assertEqual(self.rows("files")[0]["file_offset"], self.current.stat().st_size)
            self.config["history_months"] = 120
            self.run_cycle()
            self.assertFalse(self.rows("events"))

        def test_local_and_database_locks(self):
            lock = str(self.root / "collect.lock")
            with c.local_lock(lock):
                with self.assertRaises(db.LockBusy):
                    with c.local_lock(lock):
                        pass
            other = db.connect(database_config)
            try:
                with db.instance_lock(conn, self.instance):
                    with self.assertRaises(db.LockBusy):
                        with db.instance_lock(other, self.instance):
                            pass
                with db.instance_lock(other, self.instance):
                    pass
            finally:
                other.close()

        def test_retention_heartbeat_and_technical_cursors(self):
            self.current.write_bytes(self.record() * 600)
            self.run_cycle()
            self.assertEqual(len(self.rows("events")), 600)
            self.sql("UPDATE mail_stats_events SET event_at=%s WHERE instance_id=%s",
                     (self.now - timedelta(days=800), self.instance))
            self.sql("UPDATE mail_stats_sources SET last_success_at=NULL WHERE instance_id=%s AND source_key='retention'",
                     (self.instance,))
            with patch.object(c, "PURGE_BATCHES", 1):
                self.run_cycle()
            retention = [r for r in self.rows("sources") if r["source_key"] == b"retention"][0]
            self.assertIsNone(retention["last_success_at"])
            self.assertEqual(len(self.rows("events")), 100)
            self.run_cycle()
            retention = [r for r in self.rows("sources") if r["source_key"] == b"retention"][0]
            self.assertIsNotNone(retention["last_success_at"])
            self.assertFalse(self.rows("events"))
            self.assertEqual(len(self.rows("files")), 1)

        def test_dmarc_mutable_revisions_no_raw_content(self):
            self.sql("CREATE TABLE IF NOT EXISTS dmarc_reportlog (id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,"
                     "event_time DATETIME NOT NULL,source TINYINT UNSIGNED NOT NULL,success BOOLEAN NOT NULL,message TEXT)")
            self.sql("DELETE FROM dmarc_reportlog")
            self.sql("INSERT INTO dmarc_reportlog (event_time,source,success,message) VALUES (%s,2,0,'SECRET BODY')", (self.now,))
            self.registry = [dict(key="dmarc", family="maintenance", kind="sql")]
            self.run_cycle()
            self.run_cycle()
            self.assertEqual(len(self.rows("events")), 1)
            self.sql("UPDATE dmarc_reportlog SET success=1")
            self.run_cycle()
            self.assertEqual(len(self.rows("events")), 2)
            self.assertNotIn("SECRET", str(self.rows("events")))
            self.sql("DELETE FROM dmarc_reportlog")
            self.run_cycle()
            self.assertEqual(len(self.rows("files")), 1)

        def test_logical_alias_single_ingestion(self):
            self.registry = [dict(key="local-syslog", family="maintenance", kind="s6", path=str(self.root)),
                             dict(key="vpopmail-auth", family="transport", kind="state", status="conditional",
                                  routed_via="local-syslog", coverage="routed")]
            self.current.write_bytes(self.record("auth_failure", component="vpopmail"))
            self.run_cycle()
            self.run_cycle()
            sources = {row["source_key"]: row for row in self.rows("sources")}
            event = self.rows("events")[0]
            self.assertEqual(event["source_id"], sources[b"vpopmail-auth"]["id"])
            self.assertEqual(self.rows("files")[0]["source_id"], sources[b"local-syslog"]["id"])
            self.assertEqual(self.rows("hourly")[0]["source_id"], sources[b"vpopmail-auth"]["id"])
            self.assertEqual(len(self.rows("events")), 1)

        def test_real_parser_transport_contract(self):
            from mail_stats.parsers import parse as actual_parse
            stamp = "@400000006abaee1e00000000 " + self.now.strftime("%Y-%m-%d %H:%M:%S") + ".000000000  "
            lines = ["info msg 71: bytes 42 from <sender@example.invalid> qp 25 uid 89",
                     "starting delivery 8: msg 71 to remote recipient@example.invalid",
                     "delivery 8: success: 192.0.2.1_accepted_message./",
                     "end msg 71", "starting delivery 9: msg 71 to local recipient@example.invalid",
                     "mail-stats: qmail-send generation start", "delivery 9: success: accepted"]
            self.current.write_bytes("".join(stamp + line + "\n" for line in lines).encode())
            self.run_cycle(actual_parse)
            self.assertEqual(len(self.rows("events")), 7)
            self.assertEqual(self.rows("events")[2]["event_type"], b"delivery_remote_success")
            self.assertEqual(self.rows("messages")[0]["bytes"], 42)
            self.assertIsNone(self.rows("events")[-1]["attempt_id"])

        def test_reused_queue_invalidates_unfinished_attempt(self):
            self.current.write_bytes(
                self.record("message_observed", action="message_info", queue_id="7") +
                self.record("attempt_started", action="attempt_start", queue_id="7", attempt_key="1", channel="local") +
                self.record("message_observed", action="message_info", queue_id="7") +
                self.record("delivery_success", action="attempt_result", attempt_key="1", outcome="success"))
            self.run_cycle()
            self.assertIsNone(self.rows("events")[-1]["attempt_id"])
            self.assertEqual(self.rows("attempts")[0]["outcome"], b"incomplete")

        def test_budget_commits_only_processed_records(self):
            self.current.write_bytes(self.record() * 3)

            def slow(key, data, timezone=None):
                time.sleep(0.1)
                return parse(key, data)

            with patch.object(c, "SOURCE_SECONDS", 0.05):
                self.run_cycle(slow)
            self.assertEqual(len(self.rows("events")), 1)
            self.assertEqual(self.rows("files")[0]["file_offset"], len(self.record()))
            self.run_cycle()
            self.assertEqual(len(self.rows("events")), 3)

        def test_unknown_queue_record_breaks_correlation(self):
            self.current.write_bytes(
                self.record("message_observed", action="message_info", queue_id="7") +
                self.record("attempt_started", action="attempt_start", queue_id="7", attempt_key="1", channel="local") +
                b"null\n" + self.record("delivery_success", action="attempt_result", attempt_key="1", outcome="success"))
            self.run_cycle()
            self.assertIsNone(self.rows("events")[-1]["attempt_id"])

        def test_concurrent_rewrite_rolls_back_and_missing_file_keeps_cursor(self):
            self.current.write_bytes(self.record())

            def rewriting(key, data, timezone=None):
                self.current.write_bytes(self.record("service_stopped"))
                return parse(key, data)

            self.run_cycle(rewriting)
            self.assertFalse(self.rows("events"))
            self.assertFalse(self.rows("files"))
            self.run_cycle()
            self.current.unlink()
            self.run_cycle()
            self.assertEqual(len(self.rows("files")), 1)
            self.assertEqual(len(self.rows("events")), 1)

        def test_cursor_replay_does_not_duplicate_correlations(self):
            self.current.write_bytes(self.record("message_observed", action="message_info", queue_id="7"))
            self.run_cycle()
            self.sql("UPDATE mail_stats_files SET file_offset=0 WHERE instance_id=%s", (self.instance,))
            self.run_cycle()
            self.assertEqual(len(self.rows("events")), 1)
            self.assertEqual(len(self.rows("messages")), 1)
            self.assertEqual(self.rows("hourly")[0]["count"], 1)

        def test_expired_correlation_backlog_cannot_resurrect_sender(self):
            self.current.write_bytes(self.record("message_observed", action="message_info", queue_id="7",
                                                 sender="expired@example.invalid"))
            self.run_cycle()
            source = [row for row in self.rows("sources") if row["source_key"] == b"qmail-send"][0]
            expired = self.now - timedelta(days=800)
            # Put 500 earlier records before the target in the bounded purge.
            with conn.cursor() as cur:
                cur.executemany("INSERT INTO mail_stats_messages (instance_id,source_id,generation,queue_id,"
                                "started_at,last_event_at) VALUES (%s,%s,%s,%s,%s,%s)",
                                [(self.instance, source["id"], source["generation"], b"other",
                                  expired - timedelta(days=1), expired) for _ in range(500)])
            self.sql("UPDATE mail_stats_messages SET started_at=%s WHERE instance_id=%s AND queue_id='7'",
                     (expired, self.instance))
            with self.current.open("ab") as stream:
                stream.write(self.record("attempt_started", action="attempt_start", queue_id="7",
                                         attempt_key="1", channel="local"))
            with patch.object(c, "PURGE_BATCHES", 1):
                self.run_cycle()
            fresh = self.rows("events")[-1]
            self.assertIsNone(fresh["message_id"])
            self.assertIsNone(fresh["sender"])

        def test_recent_attempt_with_expired_parent_is_orphan(self):
            self.current.write_bytes(
                self.record("message_observed", action="message_info", queue_id="7", sender="expired@example.invalid") +
                self.record("attempt_started", action="attempt_start", queue_id="7", attempt_key="1", channel="local"))
            self.run_cycle()
            self.sql("UPDATE mail_stats_messages SET started_at=%s WHERE instance_id=%s",
                     (self.now - timedelta(days=800), self.instance))
            with self.current.open("ab") as stream:
                stream.write(self.record("delivery_success", action="attempt_result", attempt_key="1", outcome="success"))
            # Simulate an interrupted purge leaving the expired parent present.
            with patch.object(db, "purge_batch", return_value={}):
                self.run_cycle()
            fresh = self.rows("events")[-1]
            self.assertIsNone(fresh["message_id"])
            self.assertIsNone(fresh["sender"])
            self.assertIsNotNone(fresh["attempt_id"])

        def test_expired_attempt_does_not_copy_recipient(self):
            self.current.write_bytes(self.record("attempt_started", action="attempt_start", queue_id="7",
                                                 attempt_key="1", channel="local", recipient="expired@example.invalid"))
            self.run_cycle()
            self.sql("UPDATE mail_stats_attempts SET started_at=%s WHERE instance_id=%s",
                     (self.now - timedelta(days=800), self.instance))
            with self.current.open("ab") as stream:
                stream.write(self.record("delivery_success", action="attempt_result", attempt_key="1", outcome="success"))
            with patch.object(db, "purge_batch", return_value={}):
                self.run_cycle()
            fresh = self.rows("events")[-1]
            self.assertIsNone(fresh["attempt_id"])
            self.assertIsNone(fresh["recipient"])

        def test_archive_fragment_does_not_repeat_generation_gap(self):
            archive = self.root / ("@" + "1" * 24 + ".u")
            archive.write_bytes(b"partial-without-newline")
            self.current.write_bytes(
                self.record("message_observed", action="message_info", queue_id="7") +
                self.record("attempt_started", action="attempt_start", queue_id="7", attempt_key="1", channel="local"))
            self.run_cycle()
            first = [row for row in self.rows("sources") if row["source_key"] == b"qmail-send"][0]
            with self.current.open("ab") as stream:
                stream.write(self.record("delivery_success", action="attempt_result", attempt_key="1", outcome="success"))
            self.run_cycle()
            second = [row for row in self.rows("sources") if row["source_key"] == b"qmail-send"][0]
            self.assertEqual(first["generation"], second["generation"])
            self.assertEqual(first["discontinuities"], second["discontinuities"])
            self.assertEqual(self.rows("events")[-1]["event_type"], b"delivery_local_success")
            self.assertEqual(self.rows("files")[0]["file_offset"], 0)

        def test_late_archive_info_cannot_replace_current_sender(self):
            # Numbered application archives can still be held open by a writer.
            self.registry[0].update(kind="file", path=str(self.current))
            archive = self.root / "current.1"
            old_time = (self.now - timedelta(hours=1)).isoformat()
            archive.write_bytes(self.record("message_observed", action="message_info", queue_id="7",
                                             sender="old@example.invalid", event_at=old_time)[:-1])
            self.current.write_bytes(self.record("message_observed", action="message_info", queue_id="7",
                                                 sender="new@example.invalid"))
            self.run_cycle()
            current_message = self.rows("messages")[0]["id"]
            with archive.open("ab") as stream:
                stream.write(b"\n")
            with self.current.open("ab") as stream:
                stream.write(self.record("attempt_started", action="attempt_start", queue_id="7", attempt_key="1",
                                         channel="local", recipient="new-recipient@example.invalid"))
            self.run_cycle()
            late, fresh = self.rows("events")[-2:]
            self.assertEqual(late["sender"], b"old@example.invalid")
            self.assertIsNone(late["message_id"])
            self.assertIsNone(late["generation"])
            self.assertEqual(json.loads(late["metadata"])["reason_code"], "late_archive_append")
            self.assertEqual(fresh["sender"], b"new@example.invalid")
            self.assertEqual(fresh["message_id"], current_message)
            # The marker remains effective after the original fragment completes.
            with archive.open("ab") as stream:
                stream.write(self.record("message_observed", action="message_info", queue_id="7",
                                         sender="older@example.invalid", event_at=old_time) +
                             self.record("attempt_started", action="attempt_start", queue_id="7", attempt_key="1",
                                         channel="remote", recipient="old-recipient@example.invalid", event_at=old_time))
            with self.current.open("ab") as stream:
                stream.write(self.record("delivery_success", action="attempt_result", attempt_key="1", outcome="success"))
            self.run_cycle()
            self.assertEqual(len(self.rows("messages")), 1)
            self.assertEqual(len(self.rows("attempts")), 1)
            self.assertEqual(self.rows("events")[-1]["sender"], b"new@example.invalid")
            self.assertEqual(self.rows("events")[-1]["recipient"], b"new-recipient@example.invalid")
            self.assertEqual(self.rows("events")[-1]["event_type"], b"delivery_local_success")

        def test_late_archive_result_cannot_consume_new_attempt(self):
            archive = self.root / ("@" + "1" * 24 + ".u")
            archive.write_bytes(self.record("delivery_success", action="attempt_result", attempt_key="1", outcome="success",
                                             event_at=(self.now - timedelta(hours=1)).isoformat())[:-1])
            self.current.write_bytes(
                self.record("message_observed", action="message_info", queue_id="7", sender="new@example.invalid") +
                self.record("attempt_started", action="attempt_start", queue_id="7", attempt_key="1",
                            channel="local", recipient="new-recipient@example.invalid"))
            self.run_cycle()
            live_attempt = self.rows("attempts")[0]["id"]
            with archive.open("ab") as stream:
                stream.write(b"\n")
            self.run_cycle()
            late = self.rows("events")[-1]
            self.assertIsNone(late["attempt_id"])
            self.assertIsNone(late["message_id"])
            self.assertIsNone(late["sender"])
            self.assertIsNone(late["recipient"])
            self.assertEqual(late["event_type"], b"delivery_success")
            self.assertIsNone(self.rows("attempts")[0]["finished_at"])
            with self.current.open("ab") as stream:
                stream.write(self.record("delivery_success", action="attempt_result", attempt_key="1", outcome="success"))
            self.run_cycle()
            self.assertEqual(self.rows("events")[-1]["attempt_id"], live_attempt)
            self.assertEqual(self.rows("events")[-1]["sender"], b"new@example.invalid")

        def test_late_archive_restart_and_damage_cannot_reset_current(self):
            archive = self.root / ("@" + "1" * 24 + ".u")
            archive.write_bytes(self.record("service_started", action="restart")[:-1])
            self.current.write_bytes(
                self.record("message_observed", action="message_info", queue_id="7") +
                self.record("attempt_started", action="attempt_start", queue_id="7", attempt_key="1", channel="local"))
            self.run_cycle()
            before = [row for row in self.rows("sources") if row["source_key"] == b"qmail-send"][0]
            with archive.open("ab") as stream:
                stream.write(b"\nnull\n" + b"x" * (c.MAX_LINE + 10) + b"\nanother incomplete tail")
            with self.current.open("ab") as stream:
                stream.write(self.record("delivery_success", action="attempt_result", attempt_key="1", outcome="success"))
            self.run_cycle()
            after = [row for row in self.rows("sources") if row["source_key"] == b"qmail-send"][0]
            self.assertEqual(before["generation"], after["generation"])
            self.assertEqual(before["discontinuities"], after["discontinuities"])
            self.assertEqual(self.rows("events")[-1]["event_type"], b"delivery_local_success")

        def test_clean_archive_eof_seals_late_info_and_result(self):
            self.registry[0].update(kind="file", path=str(self.current))
            archive = self.root / "current.1"
            archive.write_bytes(self.record("queue_status"))
            self.current.write_bytes(
                self.record("message_observed", action="message_info", queue_id="7", sender="new@example.invalid") +
                self.record("attempt_started", action="attempt_start", queue_id="7", attempt_key="1", channel="local"))
            self.run_cycle()
            before = [row for row in self.rows("sources") if row["source_key"] == b"qmail-send"][0]
            sealed = self.rows("files")[0]
            self.assertEqual(sealed["fragment_offset"], archive.stat().st_size)
            self.assertIsNone(self.rows("files")[1]["fragment_offset"])
            self.run_cycle()  # Unchanged sealed archives must not reset state.
            unchanged = [row for row in self.rows("sources") if row["source_key"] == b"qmail-send"][0]
            self.assertEqual(before["generation"], unchanged["generation"])
            self.assertEqual(before["discontinuities"], unchanged["discontinuities"])
            with archive.open("ab") as stream:
                stream.write(self.record("message_observed", action="message_info", queue_id="7", sender="old@example.invalid") +
                             self.record("delivery_success", action="attempt_result", attempt_key="1", outcome="success"))
            with self.current.open("ab") as stream:
                stream.write(self.record("attempt_started", action="attempt_start", queue_id="7", attempt_key="2", channel="local"))
            self.run_cycle()
            late_info, late_result, fresh = self.rows("events")[-3:]
            self.assertIsNone(late_info["message_id"])
            self.assertIsNone(late_result["attempt_id"])
            self.assertIsNone(late_result["sender"])
            self.assertEqual(fresh["sender"], b"new@example.invalid")
            self.assertEqual(len(self.rows("messages")), 1)
            self.assertIsNone(self.rows("attempts")[0]["finished_at"])
            with self.current.open("ab") as stream:
                stream.write(self.record("delivery_success", action="attempt_result", attempt_key="1", outcome="success"))
            self.run_cycle()
            self.assertEqual(self.rows("events")[-1]["sender"], b"new@example.invalid")

        def test_sealed_archive_rewrite_and_truncation_stay_isolated(self):
            archive = self.root / ("@" + "1" * 24 + ".s")
            archive.write_bytes(self.record("queue_status"))
            self.current.write_bytes(
                self.record("message_observed", action="message_info", queue_id="7", sender="new@example.invalid") +
                self.record("attempt_started", action="attempt_start", queue_id="7", attempt_key="1", channel="local"))
            self.run_cycle()
            before = [row for row in self.rows("sources") if row["source_key"] == b"qmail-send"][0]
            inode = archive.stat().st_ino
            replacements = [
                self.record("message_observed", action="message_info", queue_id="7", sender="old@example.invalid") +
                self.record("delivery_success", action="attempt_result", attempt_key="1", outcome="success"),
                self.record("delivery_success", action="attempt_result", attempt_key="1", outcome="success"),
            ]
            for replacement in replacements:
                archive.write_bytes(replacement)
                self.assertEqual(archive.stat().st_ino, inode)
                self.run_cycle()
                after = [row for row in self.rows("sources") if row["source_key"] == b"qmail-send"][0]
                self.assertEqual(before["generation"], after["generation"])
                self.assertIsNone(self.rows("events")[-1]["attempt_id"])
                self.assertIsNone(self.rows("events")[-1]["generation"])
                self.assertEqual(self.rows("files")[-1]["fragment_offset"], 0)
                self.assertEqual(len(self.rows("messages")), 1)
                self.assertIsNone(self.rows("attempts")[0]["finished_at"])
            with self.current.open("ab") as stream:
                stream.write(self.record("delivery_success", action="attempt_result", attempt_key="1", outcome="success"))
            self.run_cycle()
            self.assertEqual(self.rows("events")[-1]["sender"], b"new@example.invalid")

        def test_current_rotated_archive_continuation_precedes_seal(self):
            self.current.write_bytes(
                self.record("message_observed", action="message_info", queue_id="7", sender="sender@example.invalid") +
                self.record("attempt_started", action="attempt_start", queue_id="7", attempt_key="1", channel="local"))
            self.run_cycle()
            self.assertIsNone(self.rows("files")[0]["fragment_offset"])
            archive = self.root / ("@" + "1" * 24 + ".s")
            self.current.rename(archive)
            with archive.open("ab") as stream:
                stream.write(self.record("delivery_success", action="attempt_result", attempt_key="1", outcome="success"))
            self.current.write_bytes(self.record("message_finished", action="message_end", queue_id="7"))
            self.run_cycle()
            result = self.rows("events")[-2]
            self.assertEqual(result["event_type"], b"delivery_local_success")
            self.assertEqual(result["sender"], b"sender@example.invalid")
            self.assertIsNotNone(result["attempt_id"])
            self.assertEqual(self.rows("files")[0]["fragment_offset"], archive.stat().st_size)
            self.assertIsNone(self.rows("files")[1]["fragment_offset"])

        def test_archive_growth_after_read_defers_newer_current(self):
            archive = self.root / ("@" + "1" * 24 + ".s")
            archive.write_bytes(self.record("queue_status"))
            self.current.write_bytes(self.record("message_observed", action="message_info", queue_id="7",
                                                 sender="new@example.invalid"))
            appended = False

            def growing(key, data, timezone=None):
                nonlocal appended
                if not appended:
                    with archive.open("ab") as stream:
                        stream.write(self.record("message_observed", action="message_info", queue_id="7",
                                                 sender="old@example.invalid"))
                    appended = True
                return parse(key, data)

            self.run_cycle(growing)
            self.assertEqual(len(self.rows("events")), 1)
            self.assertIsNone(self.rows("files")[0]["fragment_offset"])
            self.run_cycle()
            with self.current.open("ab") as stream:
                stream.write(self.record("attempt_started", action="attempt_start", queue_id="7", attempt_key="1", channel="local"))
            self.run_cycle()
            self.assertEqual(self.rows("events")[-1]["sender"], b"new@example.invalid")

        def test_archive_seal_rolls_back_with_events_and_cursor(self):
            archive = self.root / ("@" + "1" * 24 + ".s")
            archive.write_bytes(self.record("message_observed", action="message_info", queue_id="7"))
            self.current.write_bytes(self.record("attempt_started", action="attempt_start", queue_id="7",
                                                 attempt_key="1", channel="local"))
            original = db.transaction

            @contextmanager
            def fail_after_seal(connection):
                with original(connection):
                    yield
                    if self.sql("SELECT id FROM mail_stats_files WHERE instance_id=%s AND fragment_offset IS NOT NULL",
                                (self.instance,)):
                        raise RuntimeError("synthetic crash after seal update")

            with patch.object(db, "transaction", fail_after_seal):
                self.run_cycle()
            for table in ("files", "events", "messages", "attempts", "hourly"):
                self.assertFalse(self.rows(table), table)
            self.run_cycle()
            self.assertEqual(len(self.rows("events")), 2)
            self.assertEqual(self.rows("events")[0]["message_id"], self.rows("events")[1]["message_id"])
            self.assertEqual(self.rows("files")[0]["fragment_offset"], archive.stat().st_size)

        def test_dmarc_hot_inserts_do_not_starve_revisions(self):
            self.sql("CREATE TABLE IF NOT EXISTS dmarc_reportlog (id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,"
                     "event_time DATETIME NOT NULL,source TINYINT UNSIGNED NOT NULL,success BOOLEAN NOT NULL,message TEXT)")
            self.sql("DELETE FROM dmarc_reportlog")
            with conn.cursor() as cur:
                cur.executemany("INSERT INTO dmarc_reportlog(event_time,source,success) VALUES (%s,2,0)", [(self.now,)] * 150)
            first_id = self.sql("SELECT MIN(id) AS id FROM dmarc_reportlog")[0]["id"]
            self.registry = [dict(key="dmarc", family="maintenance", kind="sql")]
            self.run_cycle()
            self.sql("UPDATE dmarc_reportlog SET success=1 WHERE id=%s", (first_id,))
            for _ in range(3):
                with conn.cursor() as cur:
                    cur.executemany("INSERT INTO dmarc_reportlog(event_time,source,success) VALUES (%s,2,0)", [(self.now,)] * 100)
                self.run_cycle()
            revisions = [row for row in self.rows("events") if row["source_position"].startswith(b"sql:" + str(first_id).encode() + b":")]
            self.assertEqual(len(revisions), 2)

        def test_rotation_between_enumeration_and_open_defers_new_current(self):
            self.current.write_bytes(self.record("message_observed", action="message_info", queue_id="7",
                                                 sender="old@example.invalid"))
            original = c.source_files

            @contextmanager
            def rotated(source):
                with original(source) as snapshot:
                    self.current.rename(self.root / ("@" + "1" * 24 + ".s"))
                    self.current.write_bytes(self.record("message_finished", action="message_end", queue_id="7") +
                                             self.record("message_observed", action="message_info", queue_id="7",
                                                         sender="new@example.invalid"))
                    yield snapshot

            with patch.object(c, "source_files", rotated):
                self.run_cycle()
            self.assertFalse(self.rows("events"))
            self.run_cycle()
            with self.current.open("ab") as stream:
                stream.write(self.record("attempt_started", action="attempt_start", queue_id="7", attempt_key="1", channel="local"))
            self.run_cycle()
            self.assertEqual(self.rows("events")[-1]["sender"], b"new@example.invalid")

        def test_purge_capacity_exceeds_single_ingestion_batch(self):
            self.current.write_bytes(self.record() * 2000)
            self.run_cycle()
            self.run_cycle()
            self.assertEqual(len(self.rows("events")), 2000)
            self.sql("UPDATE mail_stats_events SET event_at=%s WHERE instance_id=%s",
                     (self.now - timedelta(days=800), self.instance))
            self.run_cycle()
            self.assertFalse(self.rows("events"))

        def test_rotation_during_enumeration_defers_snapshot(self):
            self.current.write_bytes(self.record())
            original = os.scandir

            def rotating(directory):
                self.current.rename(self.root / ("@" + "1" * 24 + ".s"))
                self.current.write_bytes(self.record("service_stopped"))
                return original(directory)

            with patch.object(c.os, "scandir", rotating):
                self.run_cycle()
            self.assertFalse(self.rows("events"))
            self.run_cycle()
            self.assertEqual(len(self.rows("events")), 2)

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CollectorTests))
    conn.close()
    return 0 if result.wasSuccessful() else 1


def isolated(args):
    root = Path(__file__).resolve().parents[1]
    run_id = uuid.uuid4().hex
    prefix = "sqmail-stats-collector-" + run_id[:12]
    network, database, runner, image = prefix + "-net", prefix + "-db", prefix + "-runner", prefix + ":test"
    label_key = "sqmail.stats-collector-test"
    label = label_key + "=" + run_id

    def docker(*arguments, check=True, timeout=180, input=None):
        result = subprocess.run(["docker", *arguments], text=True, input=input, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout)
        if check and result.returncode:
            raise RuntimeError(f"docker {arguments[0]} failed:\n{result.stdout}")
        return result

    def owned(kind, name):
        field = ".Labels" if kind == "network" else ".Config.Labels"
        result = docker(kind, "inspect", "--format", '{{index ' + field + ' "' + label_key + '"}}', name, check=False)
        return result.returncode == 0 and result.stdout.strip() == run_id

    try:
        for existing in (args.database_image, args.base_image):
            if existing.startswith("-") or any(char.isspace() for char in existing):
                raise ValueError("Invalid image name")
            docker("image", "inspect", "--format", "{{.Id}}", existing)
        docker("build", "--label", label, "-t", image, "-", timeout=600,
               input=f"FROM {args.base_image}\nRUN apt-get update && apt-get install -y --no-install-recommends python3-pymysql python3-cryptography\n")
        docker("network", "create", "--internal", "--label", label, network)
        assert docker("network", "inspect", "--format", "{{.Internal}}", network).stdout.strip() == "true"
        docker("run", "-d", "--name", database, "--label", label, "--network", network, "--network-alias", "db",
               "--tmpfs", "/var/lib/mysql:rw,nosuid,size=1g", "-e", "MYSQL_ROOT_PASSWORD=SyntheticRootOnly927",
               "-e", "MYSQL_DATABASE=stats", "-e", "MYSQL_USER=stats", "-e", "MYSQL_PASSWORD=SyntheticStats927",
               args.database_image)
        mounts = []
        for source, target in ((root / "rootfs/opt/lib/mail_stats", "/opt/lib/mail_stats"),
                               (root / "rootfs/opt/sql/mail-stats.sql", "/opt/sql/mail-stats.sql"),
                               (Path(__file__).resolve(), "/tests/mail-stats-collector.py")):
            mounts += ["--mount", f"type=bind,src={source},dst={target},readonly"]
        result = docker("run", "--name", runner, "--label", label, "--network", network, *mounts,
                        "--entrypoint", "python3", image, "-B", "/tests/mail-stats-collector.py", "--inside",
                        check=False, timeout=300)
        print(result.stdout, end="")
        return result.returncode
    finally:
        for name in (runner, database):
            if owned("container", name):
                docker("rm", "-f", "-v", name)
        if owned("network", network):
            docker("network", "rm", network)
        if owned("image", image):
            docker("image", "rm", image)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-image", default="mariadb:latest")
    parser.add_argument("--base-image", default="sqmail_aio-sqmail_aio:latest")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.inside and not Path("/.dockerenv").exists():
        parser.error("Internal tests require the disposable Docker runner")
    sys.exit(inside() if args.inside else isolated(args))
