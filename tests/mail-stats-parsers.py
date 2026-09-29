#!/usr/bin/env python3
"""Offline parser regression tests; synthetic examples only, no runtime data.

Native contracts: audit of da45a09a9a66 and its retained SQMail 4.4.14 sources.
The separate observed corpus is grammar evidence, never a correlation stream.
"""

from datetime import datetime
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rootfs/opt/lib"))
from mail_stats.parsers import MAX_LINE_BYTES, parse  # noqa: E402
from mail_stats.sources import SOURCES, SOURCE_BY_KEY  # noqa: E402


STAMP = "@400000006abaee1e35a8c946 2026-09-28 22:45:13.900254022  "
LEGACY = "2026-09-28 22:45:13.900254022  "


def event(source, text, prefix=STAMP, zone=None):
    return parse(source, (prefix + text + "\n").encode(), zone)


class ParserTests(unittest.TestCase):
    def test_registry_is_explicit_and_unique(self):
        self.assertEqual(len(SOURCES), len(SOURCE_BY_KEY))
        self.assertEqual({s["family"] for s in SOURCES}, {"transport", "dovecot", "filtering", "web", "maintenance"})
        expected = {"qmail-send", "qmail-smtpd", "qmail-smtpsd", "qmail-smtpsub", "clamd", "dovecot", "fcron", "lighttpd", "php-fpm", "spamd", "vusaged"}
        self.assertTrue(expected <= {s["key"] for s in SOURCES if s["kind"] == "s6"})
        self.assertEqual(SOURCE_BY_KEY["qmailadmin"]["path"], "/log/qmailadmin/current")
        self.assertEqual(SOURCE_BY_KEY["lifecycle"]["kind"], "file")
        for key in ("roundcube-smtp", "roundcube-debug"):
            self.assertEqual(SOURCE_BY_KEY[key]["status"], "disabled")
        for key in ("lastauth", "fetchmail", "dmarc"):
            self.assertEqual(SOURCE_BY_KEY[key]["coverage"], "state_observed")
        self.assertTrue(SOURCE_BY_KEY["dmarc"]["mutable"])

    def test_combined_timestamp_uses_verified_utc_human_half(self):
        result = event("qmail-send", "new msg 1")
        self.assertEqual(result["event_at"], datetime(2026, 9, 28, 22, 45, 13, 900254))
        self.assertFalse(result["metadata"]["time_uncertain"])
        # Do not use a hardcoded TAI offset: tables may include leap seconds.
        altered_tai = STAMP.replace("6abaee1e", "6abaee39")
        self.assertEqual(event("qmail-send", "new msg 1", altered_tai)["event_at"], result["event_at"])

    def test_legacy_clock_requires_proven_zone(self):
        result = event("qmail-send", "new msg 1", LEGACY)
        self.assertIsNone(result["event_at"])
        self.assertTrue(result["metadata"]["time_uncertain"])
        result = event("qmail-send", "new msg 1", LEGACY, "Europe/Paris")
        self.assertEqual(result["event_at"], datetime(2026, 9, 28, 20, 45, 13, 900254))
        self.assertIsNone(event("qmail-send", "new msg 1", LEGACY, "not/a-zone")["event_at"])

    def test_dst_ambiguity_and_nonexistent_time_remain_uncertain(self):
        for stamp in ("2026-10-25 02:30:00.000000000  ", "2026-03-29 02:30:00.000000000  "):
            with self.subTest(stamp=stamp):
                self.assertIsNone(event("qmail-send", "new msg 1", stamp, "Europe/Paris")["event_at"])

    def test_invalid_absolute_timestamp_rejected(self):
        for prefix in (
            STAMP.replace("900254022", "900254023"),
            STAMP.replace("35a8c946", "ffffffff"),
            STAMP.replace("2026-09-28", "2026-02-30"),
            "@400000006abaee1e35a8c946 ",
        ):
            with self.subTest(prefix=prefix):
                self.assertIsNone(event("qmail-send", "new msg 1", prefix))

    def test_queue_lifecycle(self):
        examples = (
            ("mail-stats: qmail-send generation start", "service_started", "restart"),
            ("new msg 7", "queue_status", None),
            ("info msg 7: bytes 42 from <sender@example.invalid> qp 123 uid 89", "message_observed", "message_info"),
            ("starting delivery 1: msg 7 to local user@example.invalid", "attempt_started", "attempt_start"),
            ("starting delivery 2: msg 7 to remote other@example.invalid", "attempt_started", "attempt_start"),
            ("delivery 1: success: PRIVATE LDA BODY SUBJECT password=SECRET", "delivery_success", "attempt_result"),
            ("delivery 2: deferral: PRIVATE SMTP CREDENTIAL", "delivery_deferral", "attempt_result"),
            ("delivery 3: failure: PRIVATE BODY", "delivery_failure", "attempt_result"),
            ("bounce msg 7 qp 987", "bounce_created", None),
            ("end msg 7", "message_finished", "message_end"),
            ("status: qmail-send exiting", "service_stopped", "restart"),
        )
        for line, kind, action in examples:
            with self.subTest(line=line):
                result = event("qmail-send", line)
                self.assertEqual(result["event_type"], kind)
                self.assertEqual(result.get("action"), action)
                self.assertNotIn("PRIVATE", repr(result))
                self.assertNotIn("SECRET", repr(result))

    def test_result_does_not_guess_channel_or_message(self):
        result = event("qmail-send", "delivery 8: success: remote_accepted/")
        self.assertNotIn("queue_id", result)
        self.assertNotIn("channel", result)
        self.assertNotIn("recipient", result)
        self.assertEqual(result["event_type"], "delivery_success")

    def test_parsers_have_no_correlation_state(self):
        before = event("qmail-send", "delivery 1: success: delivered/")
        event("qmail-send", "starting delivery 1: msg 7 to remote user@example.invalid")
        after = event("qmail-send", "delivery 1: success: delivered/")
        self.assertEqual(before, after)

    def test_srs_mask_and_null_sender(self):
        for local in ("SRS0=SECRET=AB=origin.invalid=user", "SRS1+SECRET+relay.invalid+token", "srs0-SECRET-more"):
            result = event("qmail-send", f"info msg 1: bytes 1 from <{local}@relay.invalid> qp 1 uid 89")
            self.assertEqual(result["sender"], "[srs-redacted]@relay.invalid")
            self.assertNotIn("SECRET", repr(result))
        result = event("qmail-send", "info msg 1: bytes 1 from <> qp 1 uid 89")
        self.assertEqual(result["sender"], "<>")

    def test_smtp_exact_labels_and_acceptance_semantics(self):
        for source in ("qmail-smtpd", "qmail-smtpsd", "qmail-smtpsub"):
            with self.subTest(source=source):
                result = event(source, "qmail-smtpd: pid 100 Accept::AUTH::plain P:ESMTPSA S:192.0.2.1:unknown H:client.invalid F:alice@example.invalid T:recipient@example.invalid ?~ 'SECRET-TOKEN'")
                self.assertEqual(result["event_type"], "smtp_accepted")
                self.assertEqual(result["metadata"]["action"], "authenticated_recipient")
                self.assertEqual(result["ip"], "192.0.2.1")
                self.assertNotIn("SECRET", repr(result))
        result = event("qmail-smtpsub", "qmail-smtpd: pid 100 Reject::AUTH::plain P:ESMTPSA S:192.0.2.1:unknown H:client.invalid ?~ 'SECRET'")
        self.assertEqual(result["event_type"], "smtp_auth_failure")
        self.assertIsNone(event("qmail-smtpd", "qmail-smtpd: pid 1 Reject::DATA::NEW_UNVERIFIED P:ESMTP S:192.0.2.1:unknown H:client.invalid"))

    def test_dovecot_yearless_and_new_outer_timestamp(self):
        text = "Sep 28 22:41:07 imap-login: Info: Logged in: user=<alice@example.invalid>, method=PLAIN, rip=192.0.2.1, lip=127.0.0.1, mpid=100, TLS, session=<SECRET>"
        old = event("dovecot", text, "", "UTC")
        self.assertIsNone(old["event_at"])
        self.assertEqual(old["metadata"]["time_format"], "yearless")
        fresh = event("dovecot", text)
        self.assertFalse(fresh["metadata"]["time_uncertain"])
        self.assertNotIn("SECRET", repr(fresh))
        self.assertEqual(fresh["event_type"], "auth_success")

    def test_spam_verdict_is_not_rejection(self):
        result = event("spamd", "Sep 28 22:41:15.761 [100] info: spamd: identified spam (1000.0/5.0) for bob@example.invalid:89 in 0.1 seconds, 407 bytes.")
        self.assertEqual(result["event_type"], "spam_verdict")
        self.assertEqual(result["metadata"]["score"], 1000.0)
        self.assertEqual(result["metadata"]["duration_ms"], 100)
        self.assertEqual(result["metadata"]["verdict"], "spam")
        self.assertIsNone(event("spamd", "Sep 28 22:41:15.761 [100] info: spamd: result: Y 999 - GTUBE SECRET-MESSAGE-ID"))

    def test_clamd_no_path_or_signature_leak(self):
        result = event("clamd", "/var/qmail/queue/mess/2/123: Synthetic.Signature.SECRET FOUND")
        self.assertEqual(result["event_type"], "virus_detected")
        self.assertNotIn("SECRET", repr(result))
        self.assertNotIn("/var/qmail", repr(result))

    def test_http_discards_all_url_and_header_data(self):
        text = '192.0.2.1 private.invalid private-user [28/Sep/2026:22:42:40 +0200] "GET /SECRET?token=SECRET HTTP/1.1" 404 158 "https://SECRET" "SECRET"'
        result = event("lighttpd", text, "")
        self.assertEqual(result["event_type"], "http_access")
        self.assertEqual(result["event_at"], datetime(2026, 9, 28, 20, 42, 40))
        self.assertEqual(result["metadata"]["http_status"], 404)
        self.assertNotIn("SECRET", repr(result))
        self.assertNotIn("private", repr(result))

    def test_php_audit_routes_via_lighttpd(self):
        audit = json.dumps(dict(actor="SECRET", operation="sieve_save", mailbox="user@example.invalid", result="ok", before="SECRET", after="SECRET"))
        result = event("lighttpd", "2026-09-28 22:40:23: (mod_fastcgi.c.444) FastCGI-stderr:PHP message: delivery-admin: " + audit)
        self.assertEqual(result["component"], "delivery-admin")
        self.assertEqual(result["metadata"]["action"], "sieve_save")
        self.assertNotIn("SECRET", repr(result))

    def test_roundcube_worker_routing(self):
        text = '[28-Sep-2026 22:40:23] WARNING: [pool www] child 8 said into stdout: "userlogins: <SECRET>Successful login for alice@example.invalid (ID: 1) from 192.0.2.1 in session SECRET"'
        # Upstream puts a space after the optional session prefix.
        text = text.replace("<SECRET>Successful", "<SECRET> Successful")
        result = event("php-fpm", text)
        self.assertEqual(result["event_type"], "auth_success")
        self.assertEqual(result["component"], "roundcube")
        self.assertNotIn("SECRET", repr(result))
        error = '[28-Sep-2026 22:40:23] WARNING: [pool www] child 8 said into stdout: "errors: SECRET"'
        result = event("php-fpm", error)
        self.assertEqual(result["event_type"], "service_error")
        self.assertEqual(result["component"], "roundcube")
        self.assertNotIn("SECRET", repr(result))

    def test_all_native_service_clock_contracts(self):
        examples = (
            ("fcron", "2026-09-28 22:38:17  INFO fcron[13] 3.4.1 started"),
            ("vusaged", "vusaged: begin"),
            ("php-fpm", "[28-Sep-2026 22:40:23] NOTICE: fpm is running, pid 8"),
            ("lighttpd", "2026-09-28 22:40:23: (server.c.1974) server started (lighttpd/1.4.79)"),
        )
        for source, text in examples:
            with self.subTest(source=source):
                self.assertEqual(event(source, text)["event_type"], "service_started")
                self.assertIsNone(event(source, text, "")["event_at"])

    def test_qmailadmin_actual_format(self):
        text = "2026/09/28 22:40:23 user:alice@example.invalid ip:192.0.2.1 auth:failed [alice@example.invalid]"
        result = event("qmailadmin", text, "")
        self.assertEqual(result["event_type"], "auth_failure")
        self.assertIsNone(result["event_at"])
        self.assertIsNone(event("qmailadmin", text.replace("auth:failed", "auth:success"), ""))

    def test_qmailadmin_patched_explicit_offset(self):
        text = "2026/09/28 22:40:23 +0200 user:alice@example.invalid ip:192.0.2.1 auth:failed [alice@example.invalid]"
        result = event("qmailadmin", text, "")
        self.assertEqual(result["event_at"], datetime(2026, 9, 28, 20, 40, 23))
        self.assertEqual(result["metadata"]["time_format"], "explicit")
        self.assertFalse(result["metadata"]["time_uncertain"])

    def test_native_syslog_auth(self):
        result = event("local-syslog", "<21>Sep 28 22:40:23 vpopmail[7]: vchkpw-smtp: null password given alice@example.invalid:2001:db8::1")
        self.assertEqual(result["event_type"], "auth_failure")
        self.assertEqual(result["ip"], "2001:db8::1")
        self.assertEqual(result["account"], "alice@example.invalid")
        result = event("local-syslog", "<21>Sep 28 22:40:23 vpopmail[7]: vchkpw-smtp: null password given alice@example.invalid:fe80::1%SECRET")
        self.assertNotIn("ip", result)
        self.assertNotIn("SECRET", repr(result))

    def test_dcc_syslog_never_copies_freeform_diagnostics(self):
        result = event("local-syslog", "<19>Sep 28 22:40:23 cron-dccd: PRIVATE SECRET /mail/path")
        self.assertEqual(result["component"], "dcc")
        self.assertEqual(result["event_type"], "service_error")
        self.assertNotIn("SECRET", repr(result))
        self.assertNotIn("/mail/path", repr(result))
        self.assertIsNone(event("local-syslog", "<19>Sep 28 22:40:23 unknown: PRIVATE SECRET"))

    def test_structured_producer_contract(self):
        for source, prefix, kind, component in (
            ("lifecycle", "", "lifecycle", "entrypoint"),
            ("local-syslog", STAMP + "<14>", "fetchmail_result", "fetchmail"),
            ("fcron", STAMP, "maintenance_run", "freshclam"),
        ):
            data = dict(v=1, event=kind, component=component, at="2026-09-28T22:00:00+02:00", status="success", count=2, exit_code=0)
            result = event(source, "mail-stats: " + json.dumps(data), prefix)
            self.assertEqual(result["event_at"], datetime(2026, 9, 28, 20))
            self.assertEqual(result["event_type"], kind)
            self.assertEqual(result["metadata"]["count"], 2)

    def test_structured_rejects_unknown_keys_and_values(self):
        base = dict(v=1, event="maintenance_run", component="acme", at="2026-09-28T22:00:00Z", status="success")
        mutations = ({"message": "SECRET"}, {"count": True}, {"count": -1}, {"exit_code": 256}, {"v": True}, {"status": "SECRET"}, {"component": "SECRET"}, {"at": "2026-09-28T22:00:00"})
        for change in mutations:
            with self.subTest(change=change):
                self.assertIsNone(event("local-syslog", "<14>mail-stats: " + json.dumps(base | change)))
        self.assertIsNone(event("lifecycle", 'mail-stats: {"v":1,"v":1}', ""))

    def test_unknown_inputs_have_no_raw_fallback(self):
        for source in SOURCE_BY_KEY:
            self.assertIsNone(event(source, "UNVERIFIED SECRET PASSWORD BODY"))
        for line in (b"\xff", b"new msg 1\nnew msg 2", b"new msg 1\x00", b"a" * (MAX_LINE_BYTES + 1)):
            self.assertIsNone(parse("qmail-send", line))
        self.assertIsNone(parse("not-a-source", b"new msg 1"))

    def test_numeric_bounds(self):
        self.assertIsNone(event("qmail-send", "info msg 1: bytes 99999999999999999999 from <a@example.invalid> qp 1 uid 89"))
        self.assertIsNone(event("qmail-send", "info msg 1: bytes -1 from <a@example.invalid> qp 1 uid 89"))

    def test_separately_captured_native_corpus(self):
        fixture = ROOT / "tests/fixtures/mail-stats-runtime.json"
        corpus = json.loads(fixture.read_text())
        self.assertEqual(corpus["runtime_clock"], "UTC +0000")
        expected = {
            "qmail-send": {"message_observed", "attempt_started", "delivery_success", "delivery_failure", "delivery_deferral", "bounce_created", "service_stopped"},
            "qmail-smtpd": {"smtp_accepted", "smtp_rejected"},
            "qmail-smtpsd": {"smtp_accepted"},
            "qmail-smtpsub": {"smtp_auth_failure", "smtp_accepted"},
            "dovecot": {"auth_success", "session_closed"},
            "spamd": {"spam_verdict", "service_started"},
            "clamd": {"virus_detected"},
            "lighttpd": {"http_access"},
            "php-fpm": {"service_started"},
        }
        for source, kinds in expected.items():
            with self.subTest(source=source):
                parsed = [parse(source, line.encode(), "UTC")
                          for line in corpus["sources"][source]["lines"]]
                results = [result for result in parsed if result]
                self.assertTrue(kinds <= {result["event_type"] for result in results})
                for result in results:
                    self.assertNotIn("session-redacted", repr(result))
                    self.assertNotIn("message-id@", repr(result))
                    if source in {"dovecot", "spamd"}:
                        self.assertIsNone(result["event_at"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
