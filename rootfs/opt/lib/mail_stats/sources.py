"""Explicit source inventory; aliases are coverage records, never duplicate readers."""


def _source(key, family, kind, *, path=None, status="active", coverage="partial",
            reason_code="historical_clock_unknown", **extra):
    return dict(key=key, family=family, kind=kind, path=path, status=status,
                coverage=coverage, reason_code=reason_code, **extra)


SOURCES = tuple(
    _source(key, family, "s6", path="/log/" + key)
    for family, keys in (
        ("transport", ("qmail-send", "qmail-smtpd", "qmail-smtpsd", "qmail-smtpsub")),
        ("dovecot", ("dovecot",)),
        ("filtering", ("spamd", "clamd", "vusaged")),
        ("web", ("lighttpd", "php-fpm")),
        ("maintenance", ("fcron",)),
    ) for key in keys
) + (
    _source("qmailadmin", "web", "file", path="/log/qmailadmin/current",
            status="conditional", producer_path="/var/vpopmail/log/qmailadmin-auth.log",
            reason_code="requires_persistent_route"),
    _source("local-syslog", "maintenance", "s6", path="/log/local-syslog",
            status="conditional", reason_code="requires_local_receiver"),
    _source("roundcube", "web", "state", status="conditional", coverage="routed",
            routed_via="php-fpm", reason_code="requires_worker_capture"),
    _source("roundcube-smtp", "web", "disabled", status="disabled",
            coverage="none", reason_code="smtp_logging_disabled"),
    _source("roundcube-debug", "web", "disabled", status="disabled",
            coverage="none", reason_code="sensitive_debug_disabled"),
    _source("vpopmail-auth", "transport", "state", status="conditional",
            coverage="routed", routed_via="local-syslog", reason_code="syslog_errors_only"),
    _source("lifecycle", "maintenance", "file", path="/log/lifecycle/current",
            status="conditional", reason_code="structured_events_only"),
    _source("lastauth", "dovecot", "state", status="observed_only",
            coverage="state_observed", table="lastauth", reason_code="mutable_last_state"),
    _source("fetchmail", "maintenance", "state", status="observed_only",
            coverage="state_observed", table="fetchmail", reason_code="mutable_last_state"),
    _source("dmarc", "maintenance", "sql", status="conditional",
            coverage="state_observed", table="dmarc_reportlog", mutable=True,
            reason_code="mutable_report_log"),
    _source("dcc", "filtering", "state", status="conditional", coverage="partial",
            routed_via="local-syslog", reason_code="conditional_daemon_and_message_logs"),
    _source("retention", "maintenance", "state", status="conditional",
            coverage="none", reason_code="awaiting_purge"),
)

SOURCE_BY_KEY = {source["key"]: source for source in SOURCES}
