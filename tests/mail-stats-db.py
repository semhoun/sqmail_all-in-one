#!/usr/bin/env python3
"""Storage integration tests, exclusively in newly created disposable databases.

python3 tests/mail-stats-db.py --database-image mariadb:latest
python3 tests/mail-stats-db.py --database-image mysql:8.4

Builds a disposable Python/PyMySQL runner image, then creates a UUID-labelled
internal network and tmpfs database with no published ports or existing mounts.
Only our four source/test files are mounted read-only. No host DB connection.
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import sys
import time
import unittest
import uuid


def inside():
    sys.path.insert(0, "/opt/lib")
    from mail_stats import db
    import pymysql

    config = dict(host="db", user="stats", password="SyntheticStats927", database="stats")
    deadline = time.monotonic() + 120
    while True:
        try:
            connection = db.connect(config)
            break
        except pymysql.err.OperationalError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)
    # The image entrypoint's SQL interpolation is not the client under test.
    # Set a difficult synthetic password through our parameterized connection.
    config["password"] = "Synthetic!'\\$Stats927"
    connection.close()
    root_config = dict(config, user="root", password="SyntheticRootOnly927")
    with db.connect(root_config) as admin, admin.cursor() as cursor:
        cursor.execute("ALTER USER 'stats'@'%%' IDENTIFIED BY %s", (config["password"],))
        cursor.execute("CREATE USER 'stats_read'@'%%' IDENTIFIED BY %s", ("SyntheticRead927",))
        cursor.execute("GRANT SELECT ON stats.* TO 'stats_read'@'%'")
    connection = db.connect(config)
    with connection.cursor() as cursor:
        cursor.execute("SELECT VERSION() AS version")
        print("Database:", cursor.fetchone()["version"], flush=True)

    class StorageTests(unittest.TestCase):
        @classmethod
        def tearDownClass(cls):
            connection.close()

        def setUp(self):
            self.conn = connection
            with self.conn.cursor() as cursor:
                for table in reversed(db.TABLES):
                    cursor.execute("DROP TABLE IF EXISTS mail_stats_" + table)
            db.install_schema(self.conn)
            self.instance = b"a" * 32
            self.now = datetime(2026, 9, 28, 12, 30)
            self.cutoff = datetime(2026, 3, 28, 12, 30)
            self.source = self.add_source(self.instance)

        def sql(self, sql, args=()):
            with self.conn.cursor() as cursor:
                cursor.execute(sql, args)
                return cursor.fetchall()

        def add_source(self, instance):
            with self.conn.cursor() as cursor:
                cursor.execute("INSERT INTO mail_stats_sources "
                               "(instance_id,source_key,family,status,coverage,first_seen_at) "
                               "VALUES (%s,%s,%s,%s,%s,%s)",
                               (instance, b"qmail-send", b"transport", b"active", b"partial", self.now))
                return cursor.lastrowid

        def event(self, position=b"1", **changes):
            event = dict(source_id=self.source, source_position=position, event_at=self.now,
                         observed_at=self.now, component=b"qmail-send", event_type=b"delivery",
                         severity=b"info", parser=b"qmail-send", parser_version=1,
                         metadata={"outcome": "success"}, queue_id=b"123", sender=b"a@example.test",
                         recipient=b"b@example.test", ip=b"192.0.2.1", account=b"a@example.test")
            event.update(changes)
            return event

        def test_schema_idempotence_and_partial_ddl(self):
            db.verify_schema(self.conn)
            db.install_schema(self.conn)
            self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM mail_stats_schema")[0]["n"], 1)
            self.sql("DELETE FROM mail_stats_schema")
            self.sql("DROP TABLE mail_stats_hourly")
            db.install_schema(self.conn)
            db.verify_schema(self.conn)
            self.sql("ALTER TABLE mail_stats_events DROP KEY event_account")
            with self.assertRaises(db.SchemaError):
                db.verify_schema(self.conn)
            self.sql("DELETE FROM mail_stats_schema")
            self.sql("DROP TABLE mail_stats_hourly")
            with self.assertRaises(db.SchemaError):
                db.install_schema(self.conn)
            self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM mail_stats_schema")[0]["n"], 0)
            self.assertEqual(self.sql("SHOW TABLES LIKE 'mail\\_stats\\_hourly'"), ())

        def test_schema_columns_defaults_collation_and_version(self):
            mutations = [
                "ALTER TABLE mail_stats_files MODIFY file_offset BIGINT NOT NULL DEFAULT 0",
                "ALTER TABLE mail_stats_files MODIFY file_offset BIGINT UNSIGNED NOT NULL DEFAULT 1",
                "ALTER TABLE mail_stats_files ADD unexpected INT NULL",
                "ALTER TABLE mail_stats_files DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin",
                "UPDATE mail_stats_schema SET version=2",
                "INSERT INTO mail_stats_schema VALUES (2,1,UTC_TIMESTAMP(6))",
            ]
            for mutation in mutations:
                with self.subTest(mutation=mutation):
                    self.sql(mutation)
                    with self.assertRaises(db.SchemaError):
                        db.install_schema(self.conn)
                    self.sql("DROP TABLE mail_stats_files")
                    self.sql("DELETE FROM mail_stats_schema")
                    db.install_schema(self.conn)

        def test_schema_disabled_index_trigger_and_permissions(self):
            mariadb = "MariaDB" in self.conn.get_server_info()
            self.sql("ALTER TABLE mail_stats_events ALTER INDEX event_account " +
                     ("IGNORED" if mariadb else "INVISIBLE"))
            with self.assertRaises(db.SchemaError):
                db.verify_schema(self.conn)
            self.sql("ALTER TABLE mail_stats_events ALTER INDEX event_account " +
                     ("NOT IGNORED" if mariadb else "VISIBLE"))
            with db.connect(root_config) as admin, admin.cursor() as cursor:
                cursor.execute("CREATE TRIGGER stats_test BEFORE INSERT ON mail_stats_events "
                               "FOR EACH ROW SET NEW.metadata='{}'")
            with self.assertRaises(db.SchemaError):
                db.verify_schema(self.conn)
            self.sql("DROP TRIGGER stats_test")
            self.sql("DELETE FROM mail_stats_schema")
            self.sql("DROP TABLE mail_stats_hourly")
            with db.connect(dict(config,user="stats_read",password="SyntheticRead927")) as readonly:
                with self.assertRaises(pymysql.err.OperationalError):
                    db.install_schema(readonly)
            self.assertFalse(self.sql("SELECT * FROM mail_stats_schema"))
            self.assertFalse(self.sql("SHOW TABLES LIKE 'mail\\_stats\\_hourly'"))

        def test_connection_timeout_no_implicit_reconnect(self):
            with db.connect(dict(config,read_timeout=1)) as short:
                with short.cursor() as cursor:
                    cursor.execute("SELECT @@session.time_zone AS tz, @@session.sql_mode AS mode")
                    state = cursor.fetchone()
                    self.assertEqual(state["tz"], "+00:00")
                    self.assertIn("STRICT_ALL_TABLES", state["mode"])
                    with self.assertRaises(pymysql.err.OperationalError):
                        cursor.execute("SELECT SLEEP(2)")
                self.assertFalse(short.open)
                with self.assertRaises(pymysql.err.InterfaceError):
                    short.cursor().execute("SELECT 1")

        def test_transactions_dedup_and_instance_scope(self):
            with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                with db.transaction(self.conn):
                    self.assertIsNotNone(db.insert_event(self.conn, self.instance, self.event(), self.cutoff))
                    raise RuntimeError("simulated crash")
            self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM mail_stats_events")[0]["n"], 0)
            with db.transaction(self.conn):
                first = db.insert_event(self.conn, self.instance, self.event(), self.cutoff)
                self.assertIsNotNone(first)
                self.assertIsNone(db.insert_event(self.conn, self.instance, self.event(), self.cutoff))
                self.assertIsNotNone(db.insert_event(self.conn, self.instance, self.event(b"2"), self.cutoff))
                with self.assertRaises(RuntimeError):
                    with db.transaction(self.conn):
                        pass
            other = b"b" * 32
            other_source = self.add_source(other)
            with db.transaction(self.conn):
                with self.assertRaises(ValueError):
                    db.insert_event(self.conn, other, self.event(), self.cutoff)
                self.assertIsNotNone(db.insert_event(self.conn, other,
                                                     self.event(source_id=other_source), self.cutoff))
            # Binary queue identity is case-sensitive on both engines.
            with db.transaction(self.conn):
                db.insert_event(self.conn, self.instance, self.event(b"3", queue_id=b"AbC"), self.cutoff)
            self.assertFalse(self.sql("SELECT id FROM mail_stats_events WHERE queue_id=%s", (b"abc",)))

        def test_file_offset_and_cursor_rollback(self):
            self.sql("INSERT INTO mail_stats_files (instance_id,source_id,generation,device,inode,"
                     "first_seen_at,last_seen_at) VALUES (%s,%s,%s,1,2,%s,%s)",
                     (self.instance, self.source, b"generation", self.now, self.now))
            file_id = self.sql("SELECT id FROM mail_stats_files")[0]["id"]
            with self.assertRaises(RuntimeError):
                with db.transaction(self.conn):
                    db.insert_event(self.conn, self.instance, self.event(file_id=file_id,file_offset=0), self.cutoff)
                    self.sql("UPDATE mail_stats_files SET file_offset=20 WHERE id=%s", (file_id,))
                    raise RuntimeError("crash before commit")
            self.assertEqual(self.sql("SELECT file_offset FROM mail_stats_files")[0]["file_offset"], 0)
            with db.transaction(self.conn):
                db.insert_event(self.conn, self.instance, self.event(file_id=file_id,file_offset=0), self.cutoff)
                self.sql("UPDATE mail_stats_files SET file_offset=20 WHERE id=%s", (file_id,))
            with db.transaction(self.conn):
                self.assertIsNone(db.insert_event(self.conn, self.instance,
                                                 self.event(b"changed",file_id=file_id,file_offset=0), self.cutoff))
            self.assertEqual(self.sql("SELECT file_offset FROM mail_stats_files")[0]["file_offset"], 20)
            # A normalized logical alias retains its physical file provenance.
            self.sql("INSERT INTO mail_stats_sources "
                     "(instance_id,source_key,family,status,coverage,first_seen_at) "
                     "VALUES (%s,%s,%s,%s,%s,%s)",
                     (self.instance,b"alias",b"transport",b"active",b"partial",self.now))
            alias = self.sql("SELECT id FROM mail_stats_sources WHERE source_key=%s",(b"alias",))[0]["id"]
            with db.transaction(self.conn):
                self.assertIsNotNone(db.insert_event(self.conn,self.instance,
                    self.event(b"alias2",source_id=alias,file_id=file_id,file_offset=20),self.cutoff))

        def test_sql_locks_release_on_error_and_disconnect(self):
            other = db.connect(config)
            try:
                with self.assertRaises(ValueError):
                    with db.instance_lock(self.conn, self.instance):
                        self.conn.commit()
                        with self.assertRaises(db.LockBusy):
                            with db.instance_lock(other, self.instance):
                                pass
                        with db.instance_lock(other, b"different"):
                            pass
                        raise ValueError("test release")
                with db.instance_lock(other, self.instance):
                    pass
                lock_name = "mail-stats:instance:" + __import__("hashlib").sha256(self.instance).hexdigest()[:40]
                with other.cursor() as cursor:
                    cursor.execute("SELECT GET_LOCK(%s,0)", (lock_name,))
                other.close()
                # Server sees disconnect before this independently established session.
                time.sleep(0.1)
                with db.instance_lock(self.conn, self.instance):
                    pass
            finally:
                if other.open:
                    other.close()

        def test_retention_validation_calendar_and_hour_boundary(self):
            for invalid in (0, 121, -1, True, "", "-1", "1.5", " 6", "6 ", "never", None):
                with self.subTest(value=invalid), self.assertRaises(ValueError):
                    db.retention_cutoff(self.conn, invalid)
            for months in (1, 6, 120, "6"):
                self.assertIsInstance(db.retention_cutoff(self.conn, months), datetime)
            for instant, expected in (("2024-03-31 12:30:00", datetime(2024,2,29,12,30)),
                                      ("2025-03-31 12:30:00", datetime(2025,2,28,12,30)),
                                      ("2025-01-31 12:30:00", datetime(2024,12,31,12,30))):
                self.assertEqual(self.sql("SELECT CAST(%s AS DATETIME(6)) - INTERVAL 1 MONTH AS c", (instant,))[0]["c"], expected)
            self.assertEqual(db.hourly_cutoff(self.cutoff), datetime(2026,3,28,13))
            exact = self.cutoff.replace(minute=0)
            self.assertEqual(db.hourly_cutoff(exact), exact)
            with db.transaction(self.conn):
                self.assertIsNone(db.insert_event(self.conn, self.instance,
                                                 self.event(event_at=self.cutoff-timedelta(microseconds=1)), self.cutoff))
                self.assertIsNotNone(db.insert_event(self.conn, self.instance,
                                                     self.event(event_at=self.cutoff), self.cutoff))

        def test_bounded_retention_orphans_open_messages_and_cursors(self):
            expired = self.cutoff - timedelta(days=1)
            self.sql("INSERT INTO mail_stats_messages (instance_id,source_id,generation,queue_id,"
                     "started_at,last_event_at,sender) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                     (self.instance,self.source,b"gen",b"1",expired,self.now,b"old@example.test"))
            message = self.sql("SELECT id FROM mail_stats_messages")[0]["id"]
            self.sql("INSERT INTO mail_stats_attempts (instance_id,source_id,message_id,generation,"
                     "attempt_key,started_at,recipient) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                     (self.instance,self.source,message,b"gen",b"a",expired,b"old@example.test"))
            attempt = self.sql("SELECT id FROM mail_stats_attempts")[0]["id"]
            self.sql("INSERT INTO mail_stats_files (instance_id,source_id,generation,device,inode,"
                     "file_offset,first_seen_at,last_seen_at) VALUES (%s,%s,%s,1,2,999,%s,%s)",
                     (self.instance,self.source,b"gen",expired,expired))
            self.sql("UPDATE mail_stats_sources SET sql_cursor=%s WHERE id=%s", (b"999",self.source))
            for n in range(7):
                with db.transaction(self.conn):
                    db.insert_event(self.conn,self.instance,self.event(str(n).encode(),message_id=message,
                                                                     attempt_id=attempt), self.cutoff)
                    db.insert_event(self.conn,self.instance,self.event(f"old{n}".encode(),event_at=expired), expired)
            other = b"b" * 32
            other_source = self.add_source(other)
            with db.transaction(self.conn):
                db.insert_event(self.conn,other,self.event(source_id=other_source,event_at=expired),expired)
            for hour in (12, 13):
                self.sql("INSERT INTO mail_stats_hourly (instance_id,source_id,hour_at,category,count) "
                         "VALUES (%s,%s,%s,%s,1)",
                         (self.instance,self.source,datetime(2026,3,28,hour),b"delivery"))
            with self.assertRaises(db.LockBusy):
                db.purge_batch(self.conn,self.instance,self.cutoff,2)
            with db.instance_lock(self.conn,self.instance):
                first = db.purge_batch(self.conn,self.instance,self.cutoff,2)
                self.assertTrue(all(0 <= n <= 2 for n in first.values()))
                self.assertEqual(first["messages"], 0)
                self.assertEqual(first["attempts"], 0)
                # Interrupt/restart and converge, without unbounded parent fanout.
                for _ in range(10):
                    counts = db.purge_batch(self.conn,self.instance,self.cutoff,2)
                    self.assertTrue(all(0 <= n <= 2 for n in counts.values()))
                    if not any(counts.values()):
                        break
                else:
                    self.fail("Purge did not converge")
            self.assertFalse(self.sql("SELECT id FROM mail_stats_messages"))
            self.assertFalse(self.sql("SELECT id FROM mail_stats_attempts"))
            self.assertFalse(self.sql("SELECT id FROM mail_stats_events WHERE message_id IS NOT NULL OR attempt_id IS NOT NULL"))
            self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM mail_stats_events WHERE instance_id=%s", (self.instance,))[0]["n"],7)
            self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM mail_stats_events WHERE instance_id=%s", (other,))[0]["n"],1)
            self.assertEqual(self.sql("SELECT hour_at FROM mail_stats_hourly")[0]["hour_at"],datetime(2026,3,28,13))
            self.assertEqual(self.sql("SELECT file_offset FROM mail_stats_files")[0]["file_offset"],999)
            self.assertEqual(self.sql("SELECT sql_cursor FROM mail_stats_sources WHERE id=%s", (self.source,))[0]["sql_cursor"],b"999")
            with db.instance_lock(self.conn,self.instance):
                # Reducing history is irreversible; enlarging it restores nothing.
                for _ in range(6):
                    db.purge_batch(self.conn,self.instance,self.now+timedelta(seconds=1),2)
                self.assertFalse(self.sql("SELECT id FROM mail_stats_events WHERE instance_id=%s",(self.instance,)))
                db.purge_batch(self.conn,self.instance,expired-timedelta(days=100),2)
                self.assertFalse(self.sql("SELECT id FROM mail_stats_events WHERE instance_id=%s",(self.instance,)))
                self.assertEqual(self.sql("SELECT file_offset FROM mail_stats_files")[0]["file_offset"],999)

        def test_metadata_and_identifiers(self):
            for metadata in ({"raw": "secret"}, {"reason_code": "line\nsecret"},
                             {"action": "x" * 257}, {"score": float("nan")}, {"action": []}):
                with self.assertRaises(ValueError):
                    db.encode_metadata(metadata)
            self.assertIn("success", db.encode_metadata({"outcome":"success"}))
            with db.transaction(self.conn):
                for event in (self.event(source_position="not bytes"), self.event(raw="secret"),
                              self.event(file_id=1), self.event(metadata={"password":"x"})):
                    with self.assertRaises(ValueError):
                        db.insert_event(self.conn,self.instance,event,self.cutoff)
            with self.assertRaises(ValueError):
                with db.instance_lock(self.conn,"not bytes"):
                    pass

        def test_explain_representative_search_and_retention(self):
            values = []
            for n in range(4000):
                values.append((self.instance,self.source,str(n).encode(),self.now+timedelta(seconds=n),self.now,
                               b"qmail-send",b"delivery",b"info",b"fixture",1,
                               str(n % 100).encode(), f"s{n % 100}@example.test".encode(),
                               f"r{n % 100}@example.test".encode(),f"192.0.2.{n % 100}".encode(),
                               f"a{n % 100}".encode(),"{}"))
            with self.conn.cursor() as cursor:
                cursor.executemany("INSERT INTO mail_stats_events (instance_id,source_id,source_position,"
                                   "event_at,observed_at,component,event_type,severity,parser,parser_version,"
                                   "queue_id,sender,recipient,ip,account,metadata) VALUES ("+
                                   ",".join(["%s"]*16)+")",values)
                cursor.execute("ANALYZE TABLE mail_stats_events")
            for column,value,key in (("queue_id",b"1","event_queue"),
                                     ("sender",b"s1@example.test","event_sender"),
                                     ("recipient",b"r1@example.test","event_recipient"),
                                     ("ip",b"192.0.2.1","event_ip"), ("account",b"a1","event_account")):
                plan = self.sql(f"EXPLAIN SELECT id FROM mail_stats_events WHERE instance_id=%s "
                                f"AND {column}=%s AND event_at>=%s ORDER BY event_at,id LIMIT 50",
                                (self.instance,value,self.cutoff))[0]
                self.assertEqual(plan["key"],key,plan)
                self.assertNotEqual(plan["type"],"ALL",plan)
                print("EXPLAIN",column,plan["key"],plan["type"])
            plan = self.sql("EXPLAIN DELETE FROM mail_stats_events WHERE instance_id=%s AND event_at<%s "
                            "ORDER BY event_at,id LIMIT 50",(self.instance,self.now+timedelta(seconds=2)))[0]
            self.assertEqual(plan["key"],"event_retention",plan)
            print("EXPLAIN purge",plan["key"],plan["type"])
            with self.conn.cursor() as cursor:
                cursor.executemany("INSERT INTO mail_stats_hourly "
                                   "(instance_id,source_id,hour_at,category,count) VALUES (%s,%s,%s,%s,1)",
                                   [(self.instance,self.source,self.now.replace(minute=0)+timedelta(hours=n),b"delivery")
                                    for n in range(4000)])
                cursor.execute("ANALYZE TABLE mail_stats_hourly")
            plan = self.sql("EXPLAIN SELECT hour_at,SUM(count) FROM mail_stats_hourly WHERE instance_id=%s "
                            "AND source_id=%s AND hour_at>=%s AND hour_at<%s GROUP BY hour_at",
                            (self.instance,self.source,self.now,self.now+timedelta(hours=24)))[0]
            self.assertEqual(plan["key"],"hourly_identity",plan)
            print("EXPLAIN series",plan["key"],plan["type"])

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(StorageTests))
    return 0 if result.wasSuccessful() else 1


def isolated(args):
    root = Path(__file__).resolve().parents[1]
    run_id = uuid.uuid4().hex
    prefix = "sqmail-stats-db-" + run_id[:12]
    network, database, runner = prefix+"-net", prefix+"-db", prefix+"-runner"
    image = prefix+":test"
    label_key = "sqmail.stats-db-test"
    label = label_key+"="+run_id

    def docker(*arguments, check=True, timeout=180, input=None):
        result = subprocess.run(["docker",*arguments],text=True,input=input,
                                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
        if check and result.returncode:
            raise RuntimeError(f"docker {arguments[0]} failed:\n{result.stdout}")
        return result

    def owned(kind,name):
        field = ".Labels" if kind == "network" else ".Config.Labels"
        result = docker(kind,"inspect","--format",'{{index '+field+' "'+label_key+'"}}',name,check=False)
        return result.returncode == 0 and result.stdout.strip() == run_id

    try:
        for existing in (args.database_image,args.base_image):
            if existing.startswith("-") or "\n" in existing or " " in existing:
                raise ValueError("Invalid image name")
            docker("image","inspect","--format","{{.Id}}",existing)
        docker("build","--label",label,"-t",image,"-",timeout=600,
               input=f"FROM {args.base_image}\nRUN apt-get update && apt-get install -y --no-install-recommends python3-pymysql python3-cryptography\n")
        docker("network","create","--internal","--label",label,network)
        assert docker("network","inspect","--format","{{.Internal}}",network).stdout.strip() == "true"
        docker("run","-d","--name",database,"--label",label,"--network",network,"--network-alias","db",
               "--tmpfs","/var/lib/mysql:rw,nosuid,size=1g",
               "-e","MYSQL_ROOT_PASSWORD=SyntheticRootOnly927","-e","MYSQL_DATABASE=stats",
               "-e","MYSQL_ROOT_HOST=%",
               "-e","MYSQL_USER=stats","-e","MYSQL_PASSWORD=SyntheticStats927",args.database_image)
        mounts = []
        for source,target in ((root/"rootfs/opt/lib/mail_stats/db.py","/opt/lib/mail_stats/db.py"),
                              (root/"rootfs/opt/lib/mail_stats/__init__.py","/opt/lib/mail_stats/__init__.py"),
                              (root/"rootfs/opt/sql/mail-stats.sql","/opt/sql/mail-stats.sql"),
                              (Path(__file__).resolve(),"/tests/mail-stats-db.py")):
            mounts += ["--mount",f"type=bind,src={source},dst={target},readonly"]
        result = docker("run","--name",runner,"--label",label,"--network",network,
                        *mounts,"--entrypoint","python3",image,"-B","/tests/mail-stats-db.py","--inside",
                        check=False,timeout=300)
        print(result.stdout,end="")
        if result.returncode and owned("container",database):
            print(docker("logs",database,check=False).stdout)
        return result.returncode
    finally:
        for name in (runner,database):
            if owned("container",name):
                docker("rm","-f","-v",name)
        if owned("network",network):
            docker("network","rm",network)
        if owned("image",image):
            docker("image","rm",image)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-image",default="mariadb:latest")
    parser.add_argument("--base-image",default="sqmail_aio-sqmail_aio:latest")
    parser.add_argument("--inside",action="store_true",help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.inside and not Path("/.dockerenv").exists():
        parser.error("Internal test mode must run inside the disposable runner")
    sys.exit(inside() if args.inside else isolated(args))
