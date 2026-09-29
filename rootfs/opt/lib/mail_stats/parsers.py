"""Strict, lossy parsers for verified SQMail image logging contracts.

No raw diagnostic text, URL, message identifier, session, subject or body is
returned. None means unrecognized: the caller retains only a line hash. A
missing event_at means the clock is uncertain, not that observation time is the
event time. The collector must not correlate such records or infer a year.
"""

from datetime import datetime, timezone as dt_timezone
import ipaddress
import json
import math
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .sources import SOURCE_BY_KEY


PARSER_VERSION = 1
MAX_LINE_BYTES = 65536
UTC = dt_timezone.utc
MONTHS = {name: index for index, name in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
NUMBER = r"[0-9]{1,20}"
S6_LOCAL = re.compile(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{9})  (.*)")
YEARLESS = re.compile(r"([A-Z][a-z]{2}) +([0-9]{1,2}) (\d\d:\d\d:\d\d)(?:\.(\d{1,6}))? (.*)")
EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,255}@[A-Za-z0-9.-]{1,253}")
STRUCTURED_COMPONENTS = frozenset({
    "entrypoint", "migration", "initialization", "fetchmail", "freshclam", "dcc",
    "sa-update", "acme", "sessionclean", "learn-spam", "dmarc", "mail-stats",
})
AUDIT_OPERATIONS = frozenset({
    "domains", "mailboxes", "inspect", "qmail_preview", "qmail_save",
    "qmail_restore_preview", "qmail_restore", "sieve_save", "sieve_activate",
    "sieve_deactivate", "sieve_delete", "sieve_restore_preview", "sieve_restore",
})
SMTP_REASONS = frozenset({
    "Invalid", "Method", "Missing", "Setup", "Required", "plain", "login",
    "cram-md5", "Bad_Loader", "Bad_MIME", "Invalid_Size", "MIME_Attach",
    "Spam_Message", "Virus_Infected", "Signature", "Bad_Mailfrom", "DNS_MF",
    "Invalid_Mailfrom", "Bad_Rcptto", "Failed_Rcptto", "Invalid_Rcptto",
    "Toomany_Rcptto", "Bad_Helo", "DNS_Helo", "Invalid_Relay", "Fail",
    "Grey_Listed", "Local_Sender", "Relay_Client", "Recipients_Cdb",
    "Recipients_Pam", "Recipients_Users", "Recipients_Wild", "Rcpthosts_Rcptto",
})


def _address(value):
    if not isinstance(value, str) or len(value.encode("utf-8")) > 320:
        return None
    if value == "":
        return "<>"
    if not EMAIL.fullmatch(value):
        return None
    local, domain = value.rsplit("@", 1)
    if re.search(r"srs[01][=+\-]", local, re.I):
        return "[srs-redacted]@" + domain.lower()
    return local + "@" + domain.lower()


def _ip(value):
    if not isinstance(value, str) or len(value) > 45 or "%" in value:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def _local(value, zone):
    if not zone:
        return None
    try:
        tz = UTC if zone in ("UTC", "UTC0", "Etc/UTC") else ZoneInfo(zone)
        first, second = value.replace(tzinfo=tz, fold=0), value.replace(tzinfo=tz, fold=1)
        # DST folds and nonexistent wall times cannot be resolved from a line.
        if first.utcoffset() != second.utcoffset():
            return None
        converted = first.astimezone(UTC)
        if converted.astimezone(tz).replace(tzinfo=None) != value:
            return None
        return converted.replace(tzinfo=None)
    except (ValueError, ZoneInfoNotFoundError, OverflowError):
        return None


def _iso(value):
    if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)", value):
        raise ValueError("Explicit timestamp required")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC).replace(tzinfo=None)


def _json(value):
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("Duplicate key")
            result[key] = item
        return result
    result = json.loads(value, object_pairs_hook=unique,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite")))
    if not isinstance(result, dict):
        raise ValueError("Object required")
    return result


def _structured(text):
    if not text.startswith("mail-stats: "):
        return None
    data = _json(text[len("mail-stats: "):])
    required = {"v", "event", "component", "at", "status"}
    if not required <= data.keys() or data.keys() - required - {"count", "exit_code"}:
        return None
    if type(data["v"]) is not int or data["v"] != 1:
        return None
    event, component, status = data["event"], data["component"], data["status"]
    if not all(isinstance(item, str) for item in (event, component, status)):
        return None
    if component not in STRUCTURED_COMPONENTS or status not in {"started", "success", "failure", "skipped"}:
        return None
    if event == "lifecycle":
        if component not in {"entrypoint", "migration", "initialization", "mail-stats"}:
            return None
    elif event == "fetchmail_result":
        if component != "fetchmail":
            return None
    elif event == "maintenance_run":
        if component in {"entrypoint", "migration", "initialization", "mail-stats"}:
            return None
    else:
        return None
    metadata = {"outcome": status, "subsource": component}
    for key, maximum in (("count", 2**63 - 1), ("exit_code", 255)):
        if key in data:
            if type(data[key]) is not int or not 0 <= data[key] <= maximum:
                return None
            metadata[key] = data[key]
    return dict(event_type=event, component=component, event_at=_iso(data["at"]),
                severity="error" if status == "failure" else "info", metadata=metadata)


def _application(text):
    if re.fullmatch(r"errors: (?:<[^<>\s]{1,128}> )?.+", text):
        return dict(event_type="service_error", component="roundcube", severity="error",
                    metadata={"reason_code": "webmail_error"})
    if text.startswith("delivery-admin: "):
        data = _json(text[len("delivery-admin: "):])
        operation = data.get("operation")
        if not isinstance(operation, str) or operation not in AUDIT_OPERATIONS:
            return None
        result = data.get("result")
        if not isinstance(result, str):
            return None
        # Error codes are deliberately reduced, not copied from arbitrary text.
        return dict(event_type="admin_action", component="delivery-admin",
                    recipient=_address(data.get("mailbox")),
                    metadata={"action": operation, "outcome": "success" if result == "ok" else "failure"})
    match = re.fullmatch(
        r"userlogins: (?:<[^<>\s]{1,128}> )?Successful login for (\S+) \(ID: [0-9]+\) from (\S+) in session \S+", text)
    if match:
        return dict(event_type="auth_success", component="roundcube",
                    account=_address(match[1]), ip=_ip(match[2]), metadata={"protocol": "webmail"})
    match = re.fullmatch(
        r"userlogins: (?:<[^<>\s]{1,128}> )?Failed login for (\S+) from (\S+) in session \S+ \(error: [0-9]+\)", text)
    if match:
        return dict(event_type="auth_failure", component="roundcube", severity="warning",
                    account=_address(match[1]), ip=_ip(match[2]), metadata={"protocol": "webmail"})
    return None


def _queue(text):
    if text == "mail-stats: qmail-send generation start":
        return dict(event_type="service_started", action="restart")
    match = re.fullmatch(r"info msg (" + NUMBER + r"): bytes (" + NUMBER + r") from <([^<>]*)> qp " + NUMBER + r" uid " + NUMBER, text)
    if match:
        size = int(match[2])
        if size > 2**63 - 1:
            return None
        return dict(event_type="message_observed", action="message_info", queue_id=match[1],
                    sender=_address(match[3]), bytes=size, metadata={"bytes": size})
    match = re.fullmatch(r"starting delivery (" + NUMBER + r"): msg (" + NUMBER + r") to (local|remote) (\S+)", text)
    if match:
        return dict(event_type="attempt_started", action="attempt_start", attempt_key=match[1],
                    queue_id=match[2], channel=match[3], recipient=_address(match[4]),
                    metadata={"delivery_kind": match[3]})
    match = re.fullmatch(r"delivery (" + NUMBER + r"): (success|deferral|failure): .+", text)
    if match:
        return dict(event_type="delivery_" + match[2], action="attempt_result",
                    attempt_key=match[1], outcome=match[2],
                    severity="warning" if match[2] != "success" else "info",
                    metadata={"outcome": match[2]})
    match = re.fullmatch(r"end msg (" + NUMBER + r")", text)
    if match:
        return dict(event_type="message_finished", action="message_end", queue_id=match[1])
    match = re.fullmatch(r"new msg (" + NUMBER + r")", text)
    if match:
        return dict(event_type="queue_status", queue_id=match[1], metadata={"reason_code": "new_message"})
    match = re.fullmatch(r"bounce msg (" + NUMBER + r") qp " + NUMBER, text)
    if match:
        return dict(event_type="bounce_created", queue_id=match[1])
    if re.fullmatch(r"status: local [0-9]+/[0-9]+ remote [0-9]+/[0-9]+(?: exitasap)?", text):
        return dict(event_type="queue_status")
    if text == "status: qmail-send exiting":
        return dict(event_type="service_stopped", action="restart")
    if text == "status: qmail-todo stop processing asap":
        return dict(event_type="queue_status", metadata={"reason_code": "stopping"})
    if re.fullmatch(r"delivery " + NUMBER + r": report mangled, will defer", text):
        return dict(event_type="service_error", severity="warning", metadata={"reason_code": "mangled_delivery_report"})
    if re.fullmatch(r"(?:warning|alert): qmail-(?:send|todo|clean) .+", text):
        return dict(event_type="service_error", severity="error", metadata={"reason_code": "queue_diagnostic"})
    return None


def _smtp(text):
    match = re.fullmatch(
        r"qmail-smtpd: pid [0-9]+ (Accept|Reject|Deferred)::(AUTH|RCPT|SNDR|ORIG|DATA|DKIM|SPF|TLS)::([A-Za-z0-9_-]+) "
        r"P:(SMTP|ESMTP|ESMTPS|ESMTPA|ESMTPSA) S:(\S+):[^\s]+ H:\S*(?: F:(\S*) T:(\S*))?(?: \?~)?(?: '[^\r\n]*')?", text)
    if not match or match[3] not in SMTP_REASONS:
        return None
    outcome, stage, reason, protocol, address, sender, recipient = match.groups()
    # Accept::AUTH is emitted at RCPT acceptance, not once per login/session.
    event = "smtp_accepted" if outcome == "Accept" else "smtp_rejected"
    if stage == "AUTH" and outcome == "Reject":
        event = "smtp_auth_failure"
    return dict(event_type=event, component="qmail-smtpd",
                severity="info" if outcome == "Accept" else "warning",
                ip=_ip(address), sender=_address(sender), recipient=_address(recipient),
                metadata={"protocol": protocol, "reason_code": reason,
                          "action": "authenticated_recipient" if stage == "AUTH" and outcome == "Accept" else stage.lower(),
                          "outcome": outcome.lower()})


def _dovecot(text):
    match = re.fullmatch(r"(imap|pop3|managesieve)-login: Info: Logged in: user=<([^<>]*)>, method=([A-Z0-9_-]+), rip=([^,]+), lip=[^,]+, (.*)", text)
    if match:
        return dict(event_type="auth_success", account=_address(match[2]), ip=_ip(match[4]),
                    metadata={"protocol": match[1]})
    match = re.fullmatch(r"(imap|pop3|managesieve)\(([^()]*)\)<[0-9]+><[^<>]*>: Info: Disconnected: .+", text)
    if match:
        return dict(event_type="session_closed", account=_address(match[2]), metadata={"protocol": match[1]})
    if re.fullmatch(r"master: Info: Dovecot v2\.4\.5 \([a-f0-9]+\) starting up for .+", text):
        return dict(event_type="service_started")
    if re.fullmatch(r"master: Warning: Killed with signal [0-9]+ \(by pid=[0-9]+ uid=[0-9]+ code=[a-z]+\)", text):
        return dict(event_type="service_stopped")
    return None


def _spamd(text):
    match = re.fullmatch(r"\[[0-9]+\] info: spamd: (identified spam|clean message) \((-?[0-9]+(?:\.[0-9]+)?)/(-?[0-9]+(?:\.[0-9]+)?)\) for (\S+):[0-9]+ in ([0-9]+(?:\.[0-9]+)?) seconds, ([0-9]+) bytes\.", text)
    if match:
        score, threshold, duration, size = float(match[2]), float(match[3]), float(match[5]), int(match[6])
        if not all(math.isfinite(value) and abs(value) < 1e12 for value in (score, threshold, duration)) or size > 2**63 - 1:
            return None
        return dict(event_type="spam_verdict", account=_address(match[4]),
                    metadata={"verdict": "spam" if match[1] == "identified spam" else "ham",
                              "score": score, "threshold": threshold, "duration_ms": int(duration * 1000), "bytes": size})
    # result/processing lines describe the same scan and are not counted again.
    if re.fullmatch(r"\[[0-9]+\] info: spamd: server started on .+ \(running version 4\.0\.2\)", text):
        return dict(event_type="service_started")
    return None


def _clamd(text):
    if re.fullmatch(r"(?:instream\([^()]+\)|/var/qmail/queue/mess/[0-9]+/[0-9]+): [A-Za-z0-9_.-]{1,128} FOUND", text):
        return dict(event_type="virus_detected", severity="warning", metadata={"verdict": "infected"})
    if text in ("LibClamAV Error: cl_load: No such file or directory: /var/lib/clamav",
                "ERROR: Can't get file status"):
        return dict(event_type="service_error", severity="error", metadata={"reason_code": "clamav_database_unavailable"})
    if text == "Closing the main socket.":
        return dict(event_type="service_stopped")
    return None


def _web(text, source, zone):
    if source == "lighttpd":
        match = re.fullmatch(
            r'(\S+) \S+ \S+ \[([0-9]{2})/([A-Z][a-z]{2})/([0-9]{4}):([0-9:]{8}) ([+-][0-9]{4})\] '
            r'"(GET|POST|HEAD|PUT|DELETE|OPTIONS|PATCH|CONNECT|TRACE) [^"\r\n]* HTTP/[0-9.]+" ([1-5][0-9]{2}) ([0-9]+|-) "[^"\r\n]*" "[^"\r\n]*"', text)
        if match:
            stamp = datetime.strptime(f"{match[4]}-{MONTHS[match[3]]:02d}-{match[2]} {match[5]} {match[6]}", "%Y-%m-%d %H:%M:%S %z")
            return dict(event_type="http_access", ip=_ip(match[1]),
                        event_at=stamp.astimezone(UTC).replace(tzinfo=None),
                        metadata={"http_status": int(match[8]), "method": match[7]})
        match = re.fullmatch(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d): \(([a-z_]+\.c)\.[0-9]+\) (.*)", text)
        if not match:
            return None
        stamp, filename, payload = match.groups()
        event = None
        if payload.startswith("FastCGI-stderr:PHP message: "):
            event = _application(payload[len("FastCGI-stderr:PHP message: "):])
        elif filename == "server.c" and re.fullmatch(r"server started \(lighttpd/[0-9.]+\)", payload):
            event = dict(event_type="service_started")
        elif filename == "server.c" and re.fullmatch(r"server stopped by UID = [0-9]+ PID = [0-9]+", payload):
            event = dict(event_type="service_stopped")
        if event:
            event.setdefault("event_at", _local(datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S"), zone))
        return event
    match = re.fullmatch(r"\[([0-9]{2})-([A-Z][a-z]{2})-([0-9]{4}) (\d\d:\d\d:\d\d)\] (NOTICE|WARNING|ERROR|ALERT): (.*)", text)
    if not match:
        return None
    day, month, year, clock, severity, payload = match.groups()
    stamp = datetime.strptime(f"{year}-{MONTHS[month]:02d}-{day} {clock}", "%Y-%m-%d %H:%M:%S")
    event = None
    worker = re.fullmatch(r'\[pool [A-Za-z0-9_-]+\] child [0-9]+ said into (?:stdout|stderr): "(.*)"', payload)
    if worker:
        event = _application(worker[1]) or _structured(worker[1])
    elif re.fullmatch(r"fpm is running, pid [0-9]+", payload):
        event = dict(event_type="service_started")
    elif payload == "exiting, bye-bye!":
        event = dict(event_type="service_stopped")
    elif payload == "Terminating ...":
        event = dict(event_type="service_notice", metadata={"reason_code": "stopping"})
    elif severity in {"ERROR", "ALERT"}:
        event = dict(event_type="service_error", severity="error", metadata={"reason_code": "fpm_diagnostic"})
    if event:
        event.setdefault("event_at", _local(stamp, zone))
    return event


def parse(source_key, line, timezone=None):
    """Return a sanitized event or None. timezone must describe this generation.

    New s6 t T records contain an absolute timestamp. Old T records need a
    caller-proven zone; native yearless records never acquire a guessed year.
    Top-level action/attempt_key/channel/bytes/outcome are collector hints only.
    """
    if not isinstance(source_key, str) or source_key not in SOURCE_BY_KEY or not isinstance(line, bytes) or len(line) > MAX_LINE_BYTES:
        return None
    try:
        text = line.decode("utf-8", "strict").removesuffix("\n").removesuffix("\r")
        if not text or re.search(r"[\x00-\x1f\x7f]", text):
            return None
        outer, clock_format = None, "absent"
        absolute = re.fullmatch(r"@([0-9a-f]{16})([0-9a-f]{8}) (.*)", text)
        if absolute:
            nanos = int(absolute[2], 16)
            if not 0 <= nanos < 10**9 or int(absolute[1], 16) < 2**62:
                return None
            text = absolute[3]
        local = S6_LOCAL.fullmatch(text)
        if absolute and not local:
            return None
        if local:
            wall = datetime.strptime(local[1][:26], "%Y-%m-%d %H:%M:%S.%f")
            if absolute:
                if nanos != int(local[1][-9:]):
                    return None
                # t T is our new TZ=UTC0 logger contract. Decode its UTC human
                # half, not TAI using a guessed historical leap-second offset.
                outer, clock_format = wall, "explicit"
            else:
                outer, clock_format = _local(wall, timezone), "s6_local"
            text = local[2]
        event = None
        if source_key in {"local-syslog", "vpopmail-auth", "lifecycle"}:
            if text.startswith("<14>mail-stats: "):
                text = text[len("<14>"):]
            syslog = re.fullmatch(r"<([0-9]{1,3})>([A-Z][a-z]{2} +[0-9]{1,2} \d\d:\d\d:\d\d) (vpopmail|mail-stats|DCC|cron-dccd)(?:\[[0-9]+\])?: (.*)", text)
            if syslog:
                if int(syslog[1]) > 191:
                    return None
                ident, text = syslog[3], syslog[4]
                if ident == "mail-stats":
                    text = "mail-stats: " + text
                elif ident == "vpopmail":
                    match = re.fullmatch(r"vchkpw-smtp: (null password given|password fail) ([^\s:]+):(\S+)", text)
                    if match:
                        event = dict(event_type="auth_failure", component="vpopmail", severity="warning",
                                     account=_address(match[2]), ip=_ip(match[3]), metadata={"protocol": "smtp"})
                elif ident in {"DCC", "cron-dccd"}:
                    error = int(syslog[1]) % 8 <= 3
                    event = dict(event_type="service_error" if error else "service_notice", component="dcc",
                                 severity="error" if error else "info", metadata={"reason_code": "native_syslog"})
            event = event or _structured(text)
        elif source_key == "qmail-send":
            event = _queue(text)
        elif source_key in {"qmail-smtpd", "qmail-smtpsd", "qmail-smtpsub"}:
            event = _smtp(text)
        elif source_key in {"dovecot", "spamd"}:
            native = YEARLESS.fullmatch(text)
            if native:
                datetime.strptime(f"2000-{MONTHS[native[1]]:02d}-{int(native[2]):02d} {native[3]}", "%Y-%m-%d %H:%M:%S")
                text = native[5]
                if clock_format == "absent":
                    clock_format = "yearless"
            event = _dovecot(text) if source_key == "dovecot" else _spamd(text)
        elif source_key == "clamd":
            event = _clamd(text)
        elif source_key in {"lighttpd", "php-fpm"}:
            event = _web(text, source_key, timezone)
            if clock_format == "absent":
                clock_format = "native_local"
        elif source_key == "roundcube":
            event = _application(text)
        elif source_key == "qmailadmin":
            match = re.fullmatch(r"(\d{4}/\d\d/\d\d \d\d:\d\d:\d\d)( [+-]\d{4})? user:(\S+) ip:(\S+) auth:failed \[[^\[\]]+\]", text)
            if match:
                if match[2]:
                    stamp = datetime.strptime(match[1] + match[2], "%Y/%m/%d %H:%M:%S %z").astimezone(UTC).replace(tzinfo=None)
                    clock_format = "explicit"
                else:
                    stamp = _local(datetime.strptime(match[1], "%Y/%m/%d %H:%M:%S"), timezone)
                event = dict(event_type="auth_failure", severity="warning", account=_address(match[3]), ip=_ip(match[4]), event_at=stamp)
                if clock_format == "absent":
                    clock_format = "native_local"
        elif source_key == "vusaged":
            if text in {"vusaged: begin", "vusaged: end"}:
                event = dict(event_type="service_started" if text.endswith("begin") else "service_stopped")
        elif source_key == "fcron":
            event = _structured(text)
            match = re.fullmatch(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)  INFO (fcron\[[0-9]+\] 3\.4\.1 started|Exiting with code [0-9]+)", text)
            if match:
                event = dict(event_type="service_started" if match[2].startswith("fcron[") else "service_stopped",
                             event_at=_local(datetime.strptime(match[1], "%Y-%m-%d %H:%M:%S"), timezone))
                if clock_format == "absent":
                    clock_format = "native_local"
        if event is None:
            return None
        event = {key: value for key, value in event.items() if value is not None}
        event.setdefault("component", source_key)
        event.setdefault("severity", "info")
        # Producer-explicit UTC wins; otherwise a trusted outer s6 timestamp wins.
        if outer is not None and event["event_type"] not in {"http_access", "lifecycle", "maintenance_run", "fetchmail_result"}:
            event["event_at"] = outer
        elif event.get("event_at") is None:
            event["event_at"] = outer
        elif outer is None:
            clock_format = "explicit" if event["event_type"] in {"http_access", "lifecycle", "maintenance_run", "fetchmail_result"} else clock_format
        metadata = event.setdefault("metadata", {})
        metadata.update(recognized=True, time_uncertain=event["event_at"] is None, time_format=clock_format)
        event.update(parser=source_key, parser_version=PARSER_VERSION)
        return event
    except (ValueError, KeyError, TypeError, OverflowError, RecursionError):
        return None
