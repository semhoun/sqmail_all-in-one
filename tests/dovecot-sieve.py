#!/usr/bin/env python3
"""Sieve regression tests for a disposable SQMail image, never production volumes.

docker run --rm --network none --ulimit core=0 --entrypoint python3 \
  -e SQMAIL_DISPOSABLE_TEST=1 -v "$PWD/tests:/tests:ro" IMAGE \
  /tests/dovecot-sieve.py

Uses static test users, loopback ManageSieve and direct PREAUTH IMAP. This tests
the installed Sieve engine and shipped Sieve settings, not SQL, TLS or postlogin.
"""

import base64
import os
from pathlib import Path
import pwd
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import uuid


class SieveTests(unittest.TestCase):
    user = "probe@example.invalid"
    password = "synthetic-sieve-test-only"
    diagnostic_log = ""
    panic = re.compile(r"panic:|assertion.*failed|segmentation fault|killed with signal|core dumped", re.I)

    @classmethod
    def run_command(cls, command, data=None, expected=0):
        result = subprocess.run(command, input=data, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=30)
        output = result.stdout.decode(errors="replace")
        if result.returncode != expected or cls.panic.search(output):
            raise AssertionError(f"{command!r}: exit {result.returncode}, expected {expected}\n{output}")
        return output

    @classmethod
    def setUpClass(cls):
        if (not Path("/.dockerenv").exists()
                or os.environ.get("SQMAIL_DISPOSABLE_TEST") != "1"
                or os.geteuid() != 0
                or Path("/var/qmail/control/aio-conf/mysql.conf").exists()):
            raise RuntimeError("Use a fresh disposable Docker container as root, without mail volumes")

        account = pwd.getpwnam("vpopmail")
        cls.uid, cls.gid = account.pw_uid, account.pw_gid
        cls.temporary = tempfile.TemporaryDirectory(prefix="sqmail-sieve-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.root.chmod(0o755)
        cls.home = cls.root / "home"
        cls.personal = cls.home / ".sieve"
        cls.maildir = cls.home / "Maildir"
        cls.global_scripts = cls.root / "global"
        for directory in (cls.home, cls.personal, cls.maildir, cls.global_scripts):
            directory.mkdir()
            os.chown(directory, cls.uid, cls.gid)
        cls.home.chmod(0o700)
        cls.active = cls.personal / "dovecot.sieve"
        cls.log = cls.root / "dovecot.log"
        cls.config = cls.root / "dovecot.conf"
        versions = dict(re.findall(r"^dovecot_(config|storage)_version\s*=\s*(\S+)",
                                   Path("/etc/dovecot/dovecot.conf").read_text(), re.M))
        cls.config.write_text(f"""
dovecot_config_version = {versions['config']}
dovecot_storage_version = {versions['storage']}
base_dir = {cls.root}/run
state_dir = {cls.root}/state
log_path = {cls.log}
info_log_path = {cls.log}
log_debug = category=sieve
protocols {{
  imap = yes
  sieve = yes
}}
listen = 127.0.0.1
ssl = no
auth_allow_cleartext = yes
first_valid_uid = {cls.uid}
mail_uid = {cls.uid}
mail_gid = {cls.gid}
mail_home = {cls.home}
mail_driver = maildir
mail_path = ~/Maildir
mailbox_list_layout = Maildir++
passdb static {{
  password = {{PLAIN}}{cls.password}
}}
userdb static {{
  fields {{
    uid = {cls.uid}
    gid = {cls.gid}
    home = {cls.home}
  }}
}}
namespace inbox {{
  inbox = yes
  separator = .
  mailbox Junk {{
    auto = create
  }}
  mailbox Personal {{
    auto = create
  }}
  mailbox RegexMatched {{
    auto = create
  }}
}}
protocol lda {{
  mail_plugins {{
    sieve = yes
  }}
}}
protocol imap {{
  mail_plugins {{
    imap_sieve = yes
  }}
}}
service imap-login {{
  inet_listener imap {{
    port = 0
  }}
  inet_listener imaps {{
    port = 0
  }}
}}
service managesieve-login {{
  inet_listener sieve {{
    port = 4190
  }}
}}
postmaster_address = postmaster@example.invalid
hostname = sieve.example.invalid
!include /etc/dovecot/conf.d/90-sieve.conf
sieve_script global {{
  type = global
  driver = file
  path = {cls.global_scripts}
}}
""")
        cls.global_scripts.joinpath("proof.sieve").write_text('require "fileinto"; fileinto "Personal";')
        cls.global_scripts.joinpath("proof.sieve").chmod(0o644)
        print(cls.run_command(["dovecot", "--version"]).strip(), flush=True)
        cls.run_command(["doveconf", "-c", str(cls.config), "-n"])
        cls.master_output = cls.root.joinpath("master.log").open("wb")
        cls.addClassCleanup(cls.stop_master)
        cls.master = subprocess.Popen(["dovecot", "-F", "-c", str(cls.config)],
                                      stdout=cls.master_output, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if cls.master.poll() is not None:
                raise RuntimeError("Dovecot exited during test startup")
            if cls.root.joinpath("run/auth-userdb").exists():
                try:
                    with socket.create_connection(("127.0.0.1", 4190), timeout=1):
                        return
                except OSError:
                    pass
            time.sleep(0.05)
        raise RuntimeError("Test Dovecot did not become ready")

    @classmethod
    def stop_master(cls):
        crashed = hasattr(cls, "master") and cls.master.poll() is not None
        if hasattr(cls, "master") and cls.master.poll() is None:
            cls.master.terminate()
            try:
                cls.master.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.master.kill()
                cls.master.wait(timeout=5)
                crashed = True
        cls.master_output.close()
        cls.diagnostic_log = "\n".join(path.read_text(errors="replace") for path in
                                       (cls.log, cls.root / "master.log") if path.exists())
        expected_stop = f"master: Warning: Killed with signal 15 (by pid={os.getpid()} uid=0 code=kill)"
        crash_log = "\n".join(line for line in cls.diagnostic_log.splitlines() if expected_stop not in line)
        if crashed or cls.panic.search(crash_log):
            raise AssertionError("Dovecot exited unexpectedly or recorded a panic")

    def setUp(self):
        self.assertIsNone(self.master.poll(), "Dovecot master must remain alive")
        self.active.unlink(missing_ok=True)
        self.active.with_suffix(".svbin").unlink(missing_ok=True)

    def activate(self, script):
        self.active.unlink(missing_ok=True)
        self.active.with_suffix(".svbin").unlink(missing_ok=True)
        self.active.write_text(script)
        os.chown(self.active, self.uid, self.gid)

    @staticmethod
    def message(token, spam=False, body="Synthetic body", subject=None):
        headers = (f"From: sender@example.invalid\r\nTo: probe@example.invalid\r\n"
                   f"Subject: {subject or token}\r\nMessage-ID: <{token}@example.invalid>\r\n"
                   "MIME-Version: 1.0\r\nContent-Type: text/plain; charset=utf-8\r\n")
        if spam:
            headers += "X-Spam-Flag: YES\r\n"
        return (headers + f"\r\n{body}\r\nProof-token: {token}\r\n").encode()

    def deliver(self, folder, **options):
        token = uuid.uuid4().hex
        self.run_command(["/usr/libexec/dovecot/dovecot-lda", "-c", str(self.config),
                          "-d", self.user, "-f", "sender@example.invalid"], self.message(token, **options))
        self.assert_locations(token, [] if folder is None else [folder])

    def locations(self, token):
        marker = f"Proof-token: {token}".encode()
        return [path for path in self.maildir.rglob("*")
                if path.is_file() and path.parent.name in ("new", "cur") and marker in path.read_bytes()]

    def assert_locations(self, token, folders):
        paths = self.locations(token)
        actual = ["INBOX" if path.parent.parent == self.maildir else path.parent.parent.name[1:]
                  for path in paths]
        self.assertCountEqual(actual, folders, f"Unexpected delivery/duplicates: {paths}")
        return paths

    def imap(self, commands):
        # A real PREAUTH IMAP process, with no exposed port or SQL/postlogin hook.
        request = b"".join(f"t{i} ".encode() + command + b"\r\n"
                           for i, command in enumerate(commands, 1))
        response = self.run_command(["/usr/libexec/dovecot/imap", "-c", str(self.config),
                                     "-u", self.user], request)
        for i in range(1, len(commands) + 1):
            self.assertRegex(response, rf"(?m)^t{i} OK ", response)
        return response

    def test_default_script(self):
        self.assertFalse(self.active.exists())
        for _ in range(3):
            self.deliver("Junk", spam=True)
        self.deliver("INBOX")
        self.deliver(None, body="550 See http://spf.pobox.com/")
        self.deliver("INBOX", body="550 See http://other.example.invalid/")

    def test_personal_and_global_include(self):
        self.activate('require "fileinto"; fileinto "Personal";')
        self.deliver("Personal", spam=True)
        self.activate('require "include"; include :global "proof";')
        self.deliver("Personal")

    def test_regex_captures_regression(self):
        # 2.4.2 panics when the capture array grows past eight entries (group 0
        # counts too). Fixed upstream in 2034d9e7, released in Pigeonhole 2.4.5.
        for count in (7, 8, 10):
            with self.subTest(captures=count):
                pattern = "".join(f"({letter})" for letter in "abcdefghij"[:count])
                self.activate('require ["regex", "variables", "fileinto"];\n'
                              f'if header :regex "Subject" "^{pattern}$" {{ fileinto "RegexMatched"; }}')
                self.deliver("RegexMatched", subject="abcdefghij"[:count])
                self.deliver("INBOX", subject="abcdefghij"[:count - 1] + "X")

    def test_invalid_script_and_recovery(self):
        # Adjacent global commands after one without arguments used to crash
        # validation (upstream 197f2498, fixed in Pigeonhole 2.4.3).
        for script in ("this is not valid Sieve;",
                       'require ["include", "variables"]; global; global "value";'):
            with self.subTest(script=script):
                self.activate(script)
                output = self.run_command(["sievec", "-c", str(self.config), str(self.active),
                                           str(self.root / "invalid.svbin")], expected=89)
                self.assertIn("error", output.lower())
                self.deliver("INBOX", spam=True)
        self.active.unlink()
        self.active.with_suffix(".svbin").unlink(missing_ok=True)
        self.deliver("Junk", spam=True)

    def test_corrupt_cache_rebuild(self):
        self.activate('require "fileinto"; fileinto "Personal";')
        self.deliver("Personal")
        binary = self.active.with_suffix(".svbin")
        self.assertTrue(binary.is_file(), "A compiled cache must exist before corruption")
        binary.write_bytes(b"invalid compiled sieve cache\n")
        self.deliver("Personal")

    def test_imap_copy_move_and_flags(self):
        suffix = uuid.uuid4().hex[:8]
        source, copied, moved = [f"{name}{suffix}" for name in ("Source", "Copied", "Moved")]
        tokens = [uuid.uuid4().hex for _ in range(3)]
        commands = [f"CREATE {box}".encode() for box in (source, copied, moved)]
        for token in tokens:
            message = self.message(token, spam=True)
            commands.append(f"APPEND {source} {{{len(message)}}}\r\n".encode() + message)
        commands += [f"SELECT {source}".encode(), f"UID COPY 1:* {copied}".encode(),
                     f"SELECT {copied}".encode(), b"UID FETCH 1:* (BODY[])",
                     b"UID STORE 1:* +FLAGS (\\Flagged \\Answered)",
                     f"UID MOVE 1:* {moved}".encode(), f"SELECT {moved}".encode(),
                     b"UID FETCH 1:* (FLAGS BODY.PEEK[])", b"NOOP", b"LOGOUT"]
        response = self.imap(commands)
        for token in tokens:
            self.assertIn(token, response)
            paths = self.assert_locations(token, [source, moved])
            for path in paths:
                flags = path.name.partition(":2,")[2]
                if path.parent.parent.name == "." + source:
                    self.assertNotIn("S", flags, "BODY.PEEK/copy must not mark the original Seen")
                else:
                    self.assertTrue(set("FRS") <= set(flags), f"Flags not preserved: {path}")

    def test_managesieve_activation(self):
        # Exercise actual upload/activation, rather than only writing the script.
        def response(stream):
            lines = []
            for _ in range(100):
                line = stream.readline(65536)
                self.assertTrue(line, "ManageSieve disconnected unexpectedly")
                lines.append(line)
                if line.startswith((b"OK", b"NO", b"BYE")):
                    self.assertTrue(line.startswith(b"OK"), b"".join(lines))
                    return b"".join(lines)
            self.fail("Unbounded ManageSieve response")

        with socket.create_connection(("127.0.0.1", 4190), timeout=5) as connection:
            with connection.makefile("rwb", buffering=0) as stream:
                response(stream)
                credentials = base64.b64encode(f"\0{self.user}\0{self.password}".encode())
                stream.write(b'AUTHENTICATE "PLAIN" "' + credentials + b'"\r\n')
                response(stream)
                script = b'require "fileinto"; fileinto "Personal";'
                stream.write(f'PUTSCRIPT "managed" {{{len(script)}+}}\r\n'.encode() + script + b"\r\n")
                response(stream)
                stream.write(b'SETACTIVE "managed"\r\n')
                response(stream)
                stream.write(b'LISTSCRIPTS\r\n')
                self.assertIn(b'"managed" ACTIVE', response(stream))
                self.deliver("Personal", spam=True)
                stream.write(b'SETACTIVE ""\r\n')
                response(stream)
                stream.write(b'DELETESCRIPT "managed"\r\n')
                response(stream)
                stream.write(b'LOGOUT\r\n')
                response(stream)
        self.deliver("Junk", spam=True)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SieveTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        print("\nDovecot diagnostics:\n" + SieveTests.diagnostic_log[-16000:], file=sys.stderr)
    sys.exit(0 if result.wasSuccessful() else 1)
