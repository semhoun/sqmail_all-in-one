#!/usr/bin/env python3
"""Run basic mail integration tests against a locally built image.

python3 tests/mail.py --image sqmail-aio:dev

Requires Docker and a local mariadb:11.4 image. Only SpamAssassin's signed-rule
preparation has Internet access. Mail and database containers use a new internal
network, no published ports, no production data and read-only test mounts.
"""

import argparse
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid


class MailEnvironment:
    label = "sqmail.mail-test"

    def __init__(self, image, database_image):
        self.image = image
        self.database_image = database_image
        self.run_id = uuid.uuid4().hex
        self.prefix = "sqmail-mail-test-" + self.run_id[:12]
        self.network = self.prefix + "-network"
        self.rules = self.prefix + "-rules"
        self.downloader = self.prefix + "-rules-download"
        self.database = self.prefix + "-database"
        self.mail = self.prefix + "-mail"
        self.tests = Path(__file__).resolve().parent

    @staticmethod
    def docker(*arguments, check=True, timeout=60):
        result = subprocess.run(["docker", *arguments], text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout)
        if check and result.returncode:
            raise RuntimeError(f"docker {arguments[0]} failed:\n{result.stdout}")
        return result

    def owned(self, kind, name):
        field = ".Config.Labels" if kind == "container" else ".Labels"
        result = self.docker(kind, "inspect", "--format",
                             '{{index ' + field + ' "' + self.label + '"}}', name, check=False)
        return result.returncode == 0 and result.stdout.strip() == self.run_id

    def cleanup(self):
        # Exact UUID ownership checks also cover a command timing out after create.
        failures = []
        for name in (self.mail, self.database, self.downloader):
            if self.owned("container", name):
                if self.docker("rm", "-f", "-v", name, check=False).returncode:
                    failures.append(name)
        for kind, name in (("volume", self.rules), ("network", self.network)):
            if self.owned(kind, name):
                if self.docker(kind, "rm", name, check=False).returncode:
                    failures.append(name)
        if failures:
            raise RuntimeError("Could not clean up test resources: " + ", ".join(failures))

    def logs(self):
        for name in (self.database, self.mail):
            if self.owned("container", name):
                output = self.docker("logs", "--tail", "50", name, check=False).stdout
                print(f"\n{name}:\n{output}", file=sys.stderr)
        if self.owned("container", self.mail):
            output = self.docker("exec", self.mail, "sh", "-c",
                                 'for service in qmail-send qmail-smtpd qmail-smtpsub dovecot clamd spamd; do '
                                 'printf "\\n=== %s ===\\n" "$service"; '
                                 'if [ -f "/log/$service/current" ]; then tail -c 4096 "/log/$service/current"; fi; done',
                                 check=False).stdout
            print(output, file=sys.stderr)

    def prepare(self):
        for image in (self.image, self.database_image):
            if image.startswith("-"):
                raise ValueError("Invalid image name")
            self.docker("image", "inspect", "--format", "{{.Id}}", image)

        label = f"{self.label}={self.run_id}"
        self.docker("network", "create", "--internal", "--label", label, self.network)
        internal = self.docker("network", "inspect", "--format", "{{.Internal}}", self.network)
        if internal.stdout.strip() != "true":
            raise RuntimeError("The mail test network must be internal")
        self.docker("volume", "create", "--label", label, self.rules)

        print("Preparing official, signature-verified SpamAssassin rules...", flush=True)
        # This downloader runs no mail services and mounts only its new rule volume.
        self.docker("run", "--pull=never", "--rm", "--name", self.downloader,
                    "--label", label, "--mount", f"type=volume,src={self.rules},dst=/var/lib/spamassassin",
                    "--entrypoint", "timeout", self.image, "180", "/usr/local/bin/sa-update",
                    "--gpg", timeout=210)

        print("Starting a disposable MariaDB instance...", flush=True)
        self.docker("run", "--pull=never", "-d", "--name", self.database,
                    "--label", label, "--network", self.network, "--network-alias", "db",
                    "--tmpfs", "/var/lib/mysql:rw,nosuid,size=512m",
                    "-e", "MARIADB_ROOT_PASSWORD=SyntheticRootOnly927",
                    "-e", "MARIADB_DATABASE=sqmail_test", "-e", "MARIADB_USER=sqmail_test",
                    "-e", "MARIADB_PASSWORD=SyntheticDbOnly927", self.database_image)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            result = self.docker("exec", self.database, "healthcheck.sh", "--connect",
                                 "--innodb_initialized", check=False, timeout=10)
            if result.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Test database did not become ready")

        print("Initializing the isolated mail server with synthetic accounts...", flush=True)
        self.docker("run", "--pull=never", "-d", "--name", self.mail, "--label", label,
                    "--network", self.network, "--network-alias", "mail",
                    "--hostname", "mail.examples.invalid", "--ulimit", "core=0",
                    "-e", "DEFAULT_LANGUAGE=en", "-e", "SQMAIL_DISPOSABLE_TEST=1",
                    "-e", f"SQMAIL_MAIL_TEST_RUN={self.run_id}",
                    "--mount", f"type=bind,src={self.tests},dst=/tests,readonly",
                    "--mount", f"type=volume,src={self.rules},dst=/var/lib/spamassassin,readonly",
                    "--entrypoint", "/bin/bash", self.image, "/tests/fixtures/mail-server.sh")
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            state = self.docker("inspect", "--format", "{{.State.Status}}", self.mail).stdout.strip()
            if state != "running":
                raise RuntimeError("Mail initialization or startup failed")
            result = self.docker("exec", self.mail, "sh", "-c",
                                 'test -f /tmp/sqmail-mail-test-run && '
                                 'for service in qmail-send qmail-smtpd qmail-smtpsub dovecot clamd spamd; do '
                                 'test "$(s6-svstat -o up /service/$service 2>/dev/null)" = true || exit 1; '
                                 'done', check=False, timeout=10)
            if result.returncode == 0:
                return
            time.sleep(1)
        raise RuntimeError("Mail services did not become ready")

    def test(self):
        result = subprocess.run(["docker", "exec", self.mail, "python3", "/tests/mail-probe.py"],
                                timeout=360)
        if result.returncode:
            raise RuntimeError("Mail integration tests failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="sqmail-aio:dev")
    parser.add_argument("--database-image", default="mariadb:11.4")
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    environment = MailEnvironment(args.image, args.database_image)
    try:
        environment.prepare()
        environment.test()
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        environment.logs()
        return 1
    except KeyboardInterrupt:
        print("Mail tests interrupted; removing disposable resources", file=sys.stderr)
        return 130
    finally:
        environment.cleanup()
    print("PASS: mail tests completed; disposable resources removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
