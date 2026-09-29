-- Version is recorded by db.install_schema only after structural verification.
CREATE TABLE IF NOT EXISTS mail_stats_schema (
  id TINYINT UNSIGNED NOT NULL,
  version BIGINT UNSIGNED NOT NULL,
  installed_at DATETIME(6) NOT NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS mail_stats_sources (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  instance_id VARBINARY(64) NOT NULL,
  source_key VARBINARY(96) NOT NULL,
  family VARBINARY(32) NOT NULL,
  status VARBINARY(24) NOT NULL,
  coverage VARBINARY(32) NOT NULL,
  reason_code VARBINARY(64) NULL,
  generation VARBINARY(64) NULL,
  sql_cursor VARBINARY(255) NULL,
  first_seen_at DATETIME(6) NOT NULL,
  last_observed_at DATETIME(6) NULL,
  last_success_at DATETIME(6) NULL,
  last_event_at DATETIME(6) NULL,
  lag_seconds BIGINT UNSIGNED NOT NULL DEFAULT 0,
  lines_seen BIGINT UNSIGNED NOT NULL DEFAULT 0,
  lines_unknown BIGINT UNSIGNED NOT NULL DEFAULT 0,
  discontinuities BIGINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY source_identity (instance_id, source_key),
  KEY source_health (instance_id, status, last_success_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS mail_stats_files (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  instance_id VARBINARY(64) NOT NULL,
  source_id BIGINT UNSIGNED NOT NULL,
  generation VARBINARY(64) NOT NULL,
  device BIGINT UNSIGNED NOT NULL,
  inode BIGINT UNSIGNED NOT NULL,
  file_offset BIGINT UNSIGNED NOT NULL DEFAULT 0,
  checkpoint_offset BIGINT UNSIGNED NOT NULL DEFAULT 0,
  checkpoint_length BIGINT UNSIGNED NOT NULL DEFAULT 0,
  checkpoint_hash VARBINARY(32) NULL,
  fragment_offset BIGINT UNSIGNED NULL,
  fragment_hash VARBINARY(32) NULL,
  prefix_length BIGINT UNSIGNED NOT NULL DEFAULT 0,
  prefix_hash VARBINARY(32) NULL,
  skipping_long_line TINYINT UNSIGNED NOT NULL DEFAULT 0,
  long_line_start BIGINT UNSIGNED NULL,
  first_seen_at DATETIME(6) NOT NULL,
  last_seen_at DATETIME(6) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY file_identity (instance_id, source_id, device, inode, generation),
  KEY file_lookup (instance_id, source_id, device, inode)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS mail_stats_messages (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  instance_id VARBINARY(64) NOT NULL,
  source_id BIGINT UNSIGNED NOT NULL,
  generation VARBINARY(64) NOT NULL,
  queue_id VARBINARY(128) NOT NULL,
  started_at DATETIME(6) NOT NULL,
  last_event_at DATETIME(6) NOT NULL,
  finished_at DATETIME(6) NULL,
  sender VARBINARY(320) NULL,
  bytes BIGINT UNSIGNED NULL,
  PRIMARY KEY (id),
  KEY message_queue (instance_id, queue_id, started_at, id),
  KEY message_generation (instance_id, source_id, generation, queue_id, started_at),
  KEY message_sender (instance_id, sender, started_at, id),
  KEY message_retention (instance_id, started_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS mail_stats_attempts (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  instance_id VARBINARY(64) NOT NULL,
  source_id BIGINT UNSIGNED NOT NULL,
  message_id BIGINT UNSIGNED NULL,
  generation VARBINARY(64) NOT NULL,
  attempt_key VARBINARY(128) NOT NULL,
  recipient VARBINARY(320) NULL,
  started_at DATETIME(6) NOT NULL,
  finished_at DATETIME(6) NULL,
  outcome VARBINARY(32) NULL,
  PRIMARY KEY (id),
  KEY attempt_identity (instance_id, source_id, generation, attempt_key, started_at),
  KEY attempt_message (instance_id, message_id, started_at, id),
  KEY attempt_recipient (instance_id, recipient, started_at, id),
  KEY attempt_retention (instance_id, started_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS mail_stats_events (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  instance_id VARBINARY(64) NOT NULL,
  source_id BIGINT UNSIGNED NOT NULL,
  file_id BIGINT UNSIGNED NULL,
  file_offset BIGINT UNSIGNED NULL,
  source_position VARBINARY(255) NOT NULL,
  generation VARBINARY(64) NULL,
  message_id BIGINT UNSIGNED NULL,
  attempt_id BIGINT UNSIGNED NULL,
  event_at DATETIME(6) NOT NULL,
  observed_at DATETIME(6) NOT NULL,
  component VARBINARY(64) NOT NULL,
  event_type VARBINARY(64) NOT NULL,
  severity VARBINARY(16) NOT NULL,
  parser VARBINARY(64) NOT NULL,
  parser_version BIGINT UNSIGNED NOT NULL,
  line_hash VARBINARY(32) NULL,
  queue_id VARBINARY(128) NULL,
  sender VARBINARY(320) NULL,
  recipient VARBINARY(320) NULL,
  ip VARBINARY(45) NULL,
  account VARBINARY(320) NULL,
  metadata TEXT NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY event_position (instance_id, source_id, source_position),
  UNIQUE KEY event_file_offset (instance_id, file_id, file_offset),
  KEY event_retention (instance_id, event_at, id),
  KEY event_source (instance_id, source_id, event_at, id),
  KEY event_message (instance_id, message_id, event_at, id),
  KEY event_attempt (instance_id, attempt_id, event_at, id),
  KEY event_queue (instance_id, queue_id, event_at, id),
  KEY event_sender (instance_id, sender, event_at, id),
  KEY event_recipient (instance_id, recipient, event_at, id),
  KEY event_ip (instance_id, ip, event_at, id),
  KEY event_account (instance_id, account, event_at, id),
  KEY event_type_time (instance_id, event_type, event_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS mail_stats_hourly (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  instance_id VARBINARY(64) NOT NULL,
  source_id BIGINT UNSIGNED NOT NULL,
  hour_at DATETIME(6) NOT NULL,
  category VARBINARY(64) NOT NULL,
  count BIGINT UNSIGNED NOT NULL DEFAULT 0,
  bytes BIGINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY hourly_identity (instance_id, source_id, hour_at, category),
  KEY hourly_retention (instance_id, hour_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
