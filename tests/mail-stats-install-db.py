#!/usr/bin/env python3
"""Run the real statistics initializer against disposable MariaDB or MySQL.

No DB or fcrontab stubs. PHP credential generation, schema DDL, SQL locks and
fcrontab compilation run in a new root test container, never on the host. Only
the initializer's selected source files are mounted, read-only. The new database
uses tmpfs and an internal network with no published ports.
"""

import argparse
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import sys
import time
import unittest
import uuid


def inside():
    if (os.geteuid() != 0 or os.environ.get("SQMAIL_STATS_INSTALL_DB_TEST") != "1"
            or not Path("/.dockerenv").exists()):
        raise RuntimeError("Disposable root database test container required")
    sys.path.insert(0, "/opt/lib")
    from mail_stats import config, db
    import pymysql

    admin_config = dict(host="db",user="root",password="SyntheticRootOnly927",database="stats")
    deadline = time.monotonic()+120
    while True:
        try:
            admin = db.connect(admin_config)
            break
        except pymysql.err.OperationalError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)
    password = "SyntheticOnly \\ ' \" $() ;\n\t&%"
    with admin.cursor() as cursor:
        cursor.execute("ALTER USER 'stats'@'%%' IDENTIFIED BY %s", (password,))
        cursor.execute("CREATE USER 'stats_read'@'%%' IDENTIFIED BY %s", (password,))
        cursor.execute("GRANT SELECT ON stats.* TO 'stats_read'@'%'")
        cursor.execute("SELECT VERSION() AS version")
        print("Database:", cursor.fetchone()["version"], flush=True)

    loader = importlib.machinery.SourceFileLoader("stats_install", "/opt/libexec/mail-stats-init")
    spec = importlib.util.spec_from_loader(loader.name, loader)
    installer = importlib.util.module_from_spec(spec)
    loader.exec_module(installer)
    account = pwd.getpwnam("www-data")
    conf_dir = Path("/var/qmail/control/aio-conf")
    conf_dir.mkdir(parents=True,exist_ok=True)
    Path("/etc/fcrontab").mkdir(exist_ok=True)
    mysql = conf_dir/"mysql.php"
    cron = Path("/etc/fcrontab/root")
    original = "!stdout(yes),mail(no)\n# Synthetic custom jobs, untouched\n0 3 * * * /bin/true\n17 5 * * 2 /bin/false\n"

    class InstallDatabaseTests(unittest.TestCase):
        @classmethod
        def tearDownClass(cls):
            admin.close()

        def setUp(self):
            with admin.cursor() as cursor:
                for table in reversed(db.TABLES):
                    cursor.execute("DROP TABLE IF EXISTS mail_stats_"+table)
            for path in (config.RUNTIME, Path("/run/mail-stats-pdf")):
                if path.exists():
                    shutil.rmtree(path)
            config.IDENTITY.unlink(missing_ok=True)
            cron.write_text(original)
            cron.chmod(0o600)
            self.write_credentials()
            self.calls = 0

        def write_credentials(self,user="stats",host="db"):
            values = dict(MYSQL_HOST=host,MYSQL_USER=user,MYSQL_PASS=password,MYSQL_DB="stats")
            result = subprocess.run(["/usr/bin/php","-r",
                '$v=json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR); '
                'echo "<?php\\n\\$MYSQL_CONF = ",var_export($v,true),";\\n";'],
                input=json.dumps(values),text=True,capture_output=True,check=True)
            mysql.write_text(result.stdout)
            os.chown(mysql,0,account.pw_gid)
            mysql.chmod(0o640)

        def start(self,expected=0,**environment):
            env = dict(os.environ, MAIL_STATS_ENABLED="1",MAIL_STATS_HISTORY_MONTHS="6")
            env.update(environment)
            result = subprocess.run(["/usr/bin/python3","-I","/opt/libexec/mail-stats-init"],
                                    env=env,text=True,capture_output=True,timeout=60)
            self.calls += 1
            self.assertEqual(result.returncode,expected,result.stdout+result.stderr)
            self.assertNotIn(password,result.stdout+result.stderr)
            self.assertNotIn("SyntheticOnly",result.stdout+result.stderr)
            self.assertNotIn("Traceback",result.stdout+result.stderr)
            return result

        def sql(self,statement,args=None):
            with admin.cursor() as cursor:
                cursor.execute(statement,args)
                return cursor.fetchall()

        def public(self):
            return json.loads((config.RUNTIME/"web.json").read_text())

        def spool(self):
            result = subprocess.run(["/usr/bin/fcrontab","-l","root"],text=True,
                                    capture_output=True,timeout=15,check=True)
            return result.stdout

        def assert_disabled(self):
            self.assertIs(self.public()["enabled"],False)
            self.assertEqual(json.loads((config.RUNTIME/"config.json").read_text()),{"enabled":False})
            with self.assertRaises(ValueError):
                config.load_private()
            self.assertEqual(cron.read_text(),original)
            self.assertNotIn(config.CRON_JOB,self.spool())
            self.assertIn("17 5 * * 2 /bin/false",self.spool())

        def test_fresh_and_existing_startup_twice_real_php_sql_and_spool(self):
            self.assertEqual(installer.credentials()["password"],password)
            for _ in range(2):
                self.start()
                db.verify_schema(admin)
                self.assertTrue(self.public()["enabled"])
                self.assertEqual(config.load_private()["database"]["password"],password)
                self.assertEqual(cron.read_text(),config.cron_text(original,True))
                self.assertEqual(self.spool().count(config.CRON_JOB),1)
            instance = config.IDENTITY.read_bytes()
            installed = self.sql("SELECT installed_at FROM mail_stats_schema")[0]["installed_at"]
            self.sql("CREATE TABLE unrelated_application (id INT PRIMARY KEY, value VARCHAR(20))")
            try:
                self.sql("INSERT INTO unrelated_application VALUES (1,'preserved')")
                for _ in range(2):
                    self.start()
                    self.assertEqual(config.IDENTITY.read_bytes(),instance)
                    self.assertEqual(self.sql("SELECT installed_at FROM mail_stats_schema")[0]["installed_at"],installed)
                    self.assertEqual(self.sql("SELECT value FROM unrelated_application")[0]["value"],"preserved")
            finally:
                self.sql("DROP TABLE unrelated_application")
            for path,mode,gid in ((config.RUNTIME/"config.json",0o600,0),
                                  (config.RUNTIME/"web.json",0o640,account.pw_gid),
                                  (config.IDENTITY,0o600,0)):
                info = path.stat()
                self.assertEqual(stat.S_IMODE(info.st_mode),mode)
                self.assertEqual((info.st_uid,info.st_gid),(0,gid))
            self.assertNotIn("database",self.public())
            self.assertNotIn("Synthetic",(config.RUNTIME/"web.json").read_text())

        def test_partial_ddl_resumes_but_incompatible_schema_disables(self):
            definitions = db._definitions()
            self.sql(definitions["mail_stats_schema"][0])
            self.sql(definitions["mail_stats_sources"][0])
            self.start()
            db.verify_schema(admin)
            self.sql("ALTER TABLE mail_stats_events DROP KEY event_account")
            self.start(expected=1)
            self.assert_disabled()
            self.assertEqual(self.sql("SELECT version FROM mail_stats_schema")[0]["version"],1)
            self.assertFalse(self.sql("SHOW INDEX FROM mail_stats_events WHERE Key_name='event_account'"))
            # No blind repair. Explicit test-only restoration permits retry.
            self.sql("ALTER TABLE mail_stats_events ADD KEY event_account (instance_id,account,event_at,id)")
            self.start()
            self.assertTrue(self.public()["enabled"])

        def test_insufficient_sql_privileges_disable_existing_and_fresh(self):
            self.start()
            self.write_credentials(user="stats_read")
            self.start(expected=1)
            self.assert_disabled()
            db.verify_schema(admin)
            with admin.cursor() as cursor:
                for table in reversed(db.TABLES):
                    cursor.execute("DROP TABLE mail_stats_"+table)
            self.start(expected=1)
            self.assert_disabled()
            self.assertFalse(self.sql("SHOW TABLES LIKE 'mail\\_stats\\_%'"))
            self.write_credentials()
            self.start()
            db.verify_schema(admin)

        def test_disabled_invalid_and_database_outage_never_purge_or_drop(self):
            self.start()
            instance = config.load_private()["instance_id"].encode()
            self.sql("INSERT INTO mail_stats_sources (instance_id,source_key,family,status,coverage,first_seen_at) "
                     "VALUES (%s,'synthetic','maintenance','active','partial','2000-01-01')",(instance,))
            source = self.sql("SELECT id FROM mail_stats_sources")[0]["id"]
            self.sql("INSERT INTO mail_stats_events (instance_id,source_id,source_position,event_at,observed_at,"
                     "component,event_type,severity,parser,parser_version,metadata) "
                     "VALUES (%s,%s,'1','2000-01-01','2000-01-01','synthetic','test','info','test',1,'{}')",
                     (instance,source))
            tables_before = self.sql("SHOW TABLES")
            self.write_credentials(host="does-not-exist.invalid")
            for environment,expected in (({"MAIL_STATS_ENABLED":"0"},0),
                                         ({"MAIL_STATS_ENABLED":"1","MAIL_STATS_HISTORY_MONTHS":"0"},1),
                                         ({"MAIL_STATS_ENABLED":"garbage"},1)):
                with self.subTest(environment=environment):
                    self.start(expected=expected,**environment)
                    self.assert_disabled()
                    self.assertEqual(self.sql("SHOW TABLES"),tables_before)
                    self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM mail_stats_events")[0]["n"],1)
            # A real denied DB login, unlike the preceding no-DB disabled paths.
            self.write_credentials(user="nonexistent")
            self.start(expected=1)
            self.assert_disabled()
            self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM mail_stats_events")[0]["n"],1)
            self.write_credentials()
            self.start(MAIL_STATS_HISTORY_MONTHS="1")
            self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM mail_stats_events")[0]["n"],1)

        def test_unsafe_credentials_and_identity_fail_closed(self):
            self.start()
            for mode,uid in ((0o660,0),(0o640,account.pw_uid)):
                with self.subTest(mode=mode,uid=uid):
                    mysql.chmod(mode)
                    os.chown(mysql,uid,account.pw_gid)
                    self.start(expected=1)
                    self.assert_disabled()
                    self.write_credentials()
            saved = mysql.with_suffix(".saved")
            mysql.rename(saved)
            try:
                mysql.symlink_to(saved)
                self.start(expected=1)
                self.assert_disabled()
            finally:
                mysql.unlink()
                saved.rename(mysql)
            config.IDENTITY.chmod(0o644)
            self.start(expected=1)
            self.assert_disabled()
            config.IDENTITY.chmod(0o600)
            self.start()

        def test_real_fcrontab_retry_without_text_change(self):
            self.start()
            before = cron.read_bytes()
            # Real binary fault injection, not a subprocess/DB stub. Root cannot
            # exec a regular file with no executable bits, even in this fixture.
            binary = Path("/usr/bin/fcrontab")
            mode = stat.S_IMODE(binary.stat().st_mode)
            binary.chmod(0o600)
            try:
                with self.assertRaises(PermissionError):
                    installer.reconcile_cron(True)
                self.assertEqual(cron.read_bytes(),before)
                self.start(expected=1)
                self.assertFalse(self.public()["enabled"])
                self.assertEqual(json.loads((config.RUNTIME/"config.json").read_text()),{"enabled":False})
            finally:
                binary.chmod(mode)
            # Recreate exactly the already-written desired text, then make spool
            # deliberately stale. Retrying must compile even without a text edit.
            subprocess.run(["/usr/bin/fcrontab","-r","root"],check=True,capture_output=True,timeout=15)
            cron.write_bytes(before)
            self.start()
            self.assertEqual(cron.read_bytes(),before)
            self.assertEqual(self.spool().count(config.CRON_JOB),1)
            self.assertIn("17 5 * * 2 /bin/false",self.spool())

        def test_real_instance_lock_contention_disables_and_recovers(self):
            self.start()
            instance = config.load_private()["instance_id"].encode("ascii")
            installed = self.sql("SELECT installed_at FROM mail_stats_schema")[0]["installed_at"]
            with db.instance_lock(admin,instance):
                self.start(expected=1)
                self.assert_disabled()
                db.verify_schema(admin)
            self.start()
            self.assertTrue(self.public()["enabled"])
            self.assertEqual(self.sql("SELECT installed_at FROM mail_stats_schema")[0]["installed_at"],installed)

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(InstallDatabaseTests))
    return 0 if result.wasSuccessful() else 1


def isolated(args):
    root = Path(__file__).resolve().parents[1]
    run_id = uuid.uuid4().hex
    prefix = "sqmail-stats-install-db-"+run_id[:12]
    database,network,runner,image = prefix+"-db",prefix+"-net",prefix+"-runner",prefix+":test"
    label_key = "sqmail.stats-install-db-test"
    label = label_key+"="+run_id

    def docker(*arguments,check=True,timeout=180,input=None):
        result = subprocess.run(["docker",*arguments],input=input,text=True,stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,timeout=timeout)
        if check and result.returncode:
            raise RuntimeError(f"docker {arguments[0]} failed:\n{result.stdout}")
        return result

    def owned(kind,name):
        field = ".Labels" if kind == "network" else ".Config.Labels"
        result = docker(kind,"inspect","--format",'{{index '+field+' "'+label_key+'"}}',name,check=False)
        return result.returncode == 0 and result.stdout.strip() == run_id

    try:
        for existing in (args.database_image,args.base_image):
            if existing.startswith("-") or any(c.isspace() for c in existing):
                raise ValueError("Invalid image name")
            docker("image","inspect","--format","{{.Id}}",existing)
        docker("build","--label",label,"-t",image,"-",timeout=600,
               input=f"FROM {args.base_image}\nRUN apt-get update && apt-get install -y --no-install-recommends python3-pymysql python3-cryptography\n")
        docker("network","create","--internal","--label",label,network)
        assert docker("network","inspect","--format","{{.Internal}}",network).stdout.strip() == "true"
        docker("run","-d","--name",database,"--label",label,"--network",network,"--network-alias","db",
               "--tmpfs","/var/lib/mysql:rw,nosuid,size=1g","-e","MYSQL_ROOT_HOST=%",
               "-e","MYSQL_ROOT_PASSWORD=SyntheticRootOnly927","-e","MYSQL_DATABASE=stats",
               "-e","MYSQL_USER=stats","-e","MYSQL_PASSWORD=SyntheticStats927",args.database_image)
        mounts = []
        for source,target in (("rootfs/opt/libexec/mail-stats-init","/opt/libexec/mail-stats-init"),
                              ("rootfs/opt/lib/mail_stats/__init__.py","/opt/lib/mail_stats/__init__.py"),
                              ("rootfs/opt/lib/mail_stats/config.py","/opt/lib/mail_stats/config.py"),
                              ("rootfs/opt/lib/mail_stats/db.py","/opt/lib/mail_stats/db.py"),
                              ("rootfs/opt/sql/mail-stats.sql","/opt/sql/mail-stats.sql"),
                              ("tests/mail-stats-install-db.py","/tests/mail-stats-install-db.py")):
            mounts += ["--mount",f"type=bind,src={root/source},dst={target},readonly"]
        result = docker("run","--name",runner,"--label",label,"--network",network,*mounts,
                        "-e","SQMAIL_STATS_INSTALL_DB_TEST=1","--entrypoint","python3",image,
                        "-B","/tests/mail-stats-install-db.py","--inside",check=False,timeout=300)
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
    arguments = parser.parse_args()
    sys.exit(inside() if arguments.inside else isolated(arguments))
