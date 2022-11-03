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

DELETE FROM `spam_prefs` WHERE `id` < 50;

INSERT INTO `spam_prefs` (`id`, `username`, `preference`, `value`, `added`, `modified`) VALUES
(1, '$GLOBAL', 'required_score', '7', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(2, '$GLOBAL', 'ok_locales', 'en fr', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(3, '$GLOBAL', 'ok_languages', 'en fr', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(4, '$GLOBAL', 'use_razor1', '0', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(5, '$GLOBAL', 'use_razor2', '1', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(6, '$GLOBAL', 'use_pyzor', '1', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(7, '$GLOBAL', 'use_dcc', '1', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(8, '$GLOBAL', 'skip_rbl_checks', '0', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(9, '$GLOBAL', 'use_bayes', '1', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(10, '$GLOBAL', 'bayes_auto_learn', '1', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(11, '$GLOBAL', 'bayes_auto_learn_threshold_nonspam', '0.1', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(12, '$GLOBAL', 'bayes_auto_learn_threshold_spam', '12', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(13, '$GLOBAL', 'use_bayes_rules', '1', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(14, '$GLOBAL', 'fold_headers', '1', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(15, '$GLOBAL', 'add_header all Level', '_STARS(*)_', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(16, '$GLOBAL', 'remove_header all', '0', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(17, '$GLOBAL', 'report_safe', '0', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(18, '$GLOBAL', 'rewrite_header Subject', '', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(19, '$GLOBAL', 'use_auto_whitelist', '0', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(20, '$GLOBAL', 'score USER_IN_BLACKLIST', '10', '2003-10-11 00:00:00', '2013-09-09 22:00:00'),
(21, '$GLOBAL', 'score USER_IN_WHITELIST', '-10', '2003-10-11 00:00:00', '2013-09-09 22:00:00');

ALTER TABLE `spam_prefs`
  MODIFY `id` int(8) UNSIGNED NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=50;