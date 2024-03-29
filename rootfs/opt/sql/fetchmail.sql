CREATE TABLE IF NOT EXISTS `fetchmail` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `mailbox` varchar(255) NOT NULL,
  `domain` varchar(255) NULL,
  `active` int(1) NOT NULL DEFAULT '1',
  `src_server` varchar(255) NOT NULL,
  `src_port` INT NOT NULL,
  `src_auth` enum('password','kerberos_v5','kerberos','kerberos_v4','gssapi','cram-md5','otp','ntlm','msn','ssh','any') NOT NULL DEFAULT 'password',
  `src_user` varchar(255) NOT NULL,
  `src_password` varchar(255) NOT NULL,
  `src_folder` varchar(255) NOT NULL,
  `poll_time` int(11) unsigned NOT NULL DEFAULT '10',
  `fetchall` tinyint(1) unsigned NOT NULL DEFAULT '0',
  `keep` tinyint(1) unsigned NOT NULL DEFAULT '1',
  `protocol` enum('POP3','IMAP','POP2','ETRN','AUTO') NOT NULL DEFAULT 'IMAP',
  `usessl` tinyint(1) unsigned NOT NULL DEFAULT '1',
  `sslcertck` boolean NULL DEFAULT true,
  `sslcertpath` varchar(255) /*!40100 CHARACTER SET utf8 */ DEFAULT '',
  `sslfingerprint` varchar(255) /*!40100 CHARACTER SET latin1 */ DEFAULT '',
  `extra_options` text,
  `returned_text` text,
  `mda` varchar(255) NOT NULL DEFAULT '',
  `date` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;
