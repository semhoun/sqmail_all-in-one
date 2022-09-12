CREATE TABLE spam_prefs (
  id int(8) UNSIGNED NOT NULL,
  username varchar(128) NOT NULL DEFAULT '',
  preference varchar(64) NOT NULL DEFAULT '',
  value varchar(128) DEFAULT NULL,
  added datetime NOT NULL DEFAULT current_timestamp(),
  modified timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  UNIQUE KEY id (id),
  KEY preference (preference),
  KEY username (username)
) ENGINE=InnoDB DEFAULT CHARSET=latin1 COMMENT='Spamassassin Preferences';
INSERT INTO spam_prefs (id, username, preference, value, added, modified) VALUES
(1, '$GLOBAL', 'required_hits', '7.0', '2003-10-11 00:00:00', '2013-09-10 00:00:00'),
(2, '$GLOBAL', 'report_safe', '0', '2003-10-11 00:00:00', '2013-09-10 00:00:00'),
(3, '$GLOBAL', 'fold_headers', '1', '2003-10-11 00:00:00', '2013-09-10 00:00:00'),
(4, '$GLOBAL', 'add_header', 'all Level _STARS(*)_', '2003-10-11 00:00:00', '2013-09-10 00:00:000'),
(5, '$GLOBAL', 'rewrite_header', 'Subject [SPAM]', '2003-10-11 00:00:00', '2013-09-10 00:00:00'),
(6, '$GLOBAL', 'ok_languages', 'en fr', '2003-10-11 00:00:00', '2013-09-10 00:00:00'),
(7, '$GLOBAL', 'refuse_threshold', '9', '2003-10-11 00:00:00', '2013-09-10 00:00:00');
