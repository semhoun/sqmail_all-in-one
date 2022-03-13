-- phpMyAdmin SQL Dump
-- version 5.1.3
-- https://www.phpmyadmin.net/
--
-- Hôte : 192.168.13.1
-- Généré le : dim. 13 mars 2022 à 18:01
-- Version du serveur : 10.5.12-MariaDB-0+deb11u1-log
-- Version de PHP : 8.0.15

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Base de données : `qmail-aio`
--

-- --------------------------------------------------------

--
-- Structure de la table `rcb_cache`
--

CREATE TABLE `rcb_cache` (
  `user_id` int(10) UNSIGNED NOT NULL,
  `cache_key` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `expires` datetime DEFAULT NULL,
  `data` longtext COLLATE utf8mb4_unicode_ci NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

-- --------------------------------------------------------

--
-- Structure de la table `rcb_cache_index`
--

CREATE TABLE `rcb_cache_index` (
  `user_id` int(10) UNSIGNED NOT NULL,
  `mailbox` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `expires` datetime DEFAULT NULL,
  `valid` tinyint(1) NOT NULL DEFAULT 0,
  `data` longtext COLLATE utf8mb4_unicode_ci NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

-- --------------------------------------------------------

--
-- Structure de la table `rcb_cache_messages`
--

CREATE TABLE `rcb_cache_messages` (
  `user_id` int(10) UNSIGNED NOT NULL,
  `mailbox` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `uid` int(11) UNSIGNED NOT NULL DEFAULT 0,
  `expires` datetime DEFAULT NULL,
  `data` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `flags` int(11) NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

-- --------------------------------------------------------

--
-- Structure de la table `rcb_cache_shared`
--

CREATE TABLE `rcb_cache_shared` (
  `cache_key` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `expires` datetime DEFAULT NULL,
  `data` longtext COLLATE utf8mb4_unicode_ci NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

-- --------------------------------------------------------

--
-- Structure de la table `rcb_cache_thread`
--

CREATE TABLE `rcb_cache_thread` (
  `user_id` int(10) UNSIGNED NOT NULL,
  `mailbox` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `expires` datetime DEFAULT NULL,
  `data` longtext COLLATE utf8mb4_unicode_ci NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

-- --------------------------------------------------------

--
-- Structure de la table `rcb_collected_addresses`
--

CREATE TABLE `rcb_collected_addresses` (
  `address_id` int(10) UNSIGNED NOT NULL,
  `changed` datetime NOT NULL DEFAULT '1000-01-01 00:00:00',
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `email` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` int(10) UNSIGNED NOT NULL,
  `type` int(10) UNSIGNED NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

-- --------------------------------------------------------

--
-- Structure de la table `rcb_contactgroupmembers`
--

CREATE TABLE `rcb_contactgroupmembers` (
  `contactgroup_id` int(10) UNSIGNED NOT NULL,
  `contact_id` int(10) UNSIGNED NOT NULL,
  `created` datetime NOT NULL DEFAULT '1000-01-01 00:00:00'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC;

-- --------------------------------------------------------

--
-- Structure de la table `rcb_contactgroups`
--

CREATE TABLE `rcb_contactgroups` (
  `contactgroup_id` int(10) UNSIGNED NOT NULL,
  `user_id` int(10) UNSIGNED NOT NULL,
  `changed` datetime NOT NULL DEFAULT '1000-01-01 00:00:00',
  `del` tinyint(1) NOT NULL DEFAULT 0,
  `name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT ''
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

-- --------------------------------------------------------

--
-- Structure de la table `rcb_contacts`
--

CREATE TABLE `rcb_contacts` (
  `contact_id` int(10) UNSIGNED NOT NULL,
  `changed` datetime NOT NULL DEFAULT '1000-01-01 00:00:00',
  `del` tinyint(1) NOT NULL DEFAULT 0,
  `name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `email` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `firstname` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `surname` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `vcard` longtext COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `words` text COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `user_id` int(10) UNSIGNED NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

-- --------------------------------------------------------

--
-- Structure de la table `rcb_dictionary`
--

CREATE TABLE `rcb_dictionary` (
  `id` int(10) UNSIGNED NOT NULL,
  `user_id` int(10) UNSIGNED DEFAULT NULL,
  `language` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `data` longtext COLLATE utf8mb4_unicode_ci NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

-- --------------------------------------------------------

--
-- Structure de la table `rcb_filestore`
--

CREATE TABLE `rcb_filestore` (
  `file_id` int(10) UNSIGNED NOT NULL,
  `user_id` int(10) UNSIGNED NOT NULL,
  `context` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `filename` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `mtime` int(10) NOT NULL,
  `data` longtext COLLATE utf8mb4_unicode_ci NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

-- --------------------------------------------------------

--
-- Structure de la table `rcb_identities`
--

CREATE TABLE `rcb_identities` (
  `identity_id` int(10) UNSIGNED NOT NULL,
  `user_id` int(10) UNSIGNED NOT NULL,
  `changed` datetime NOT NULL DEFAULT '1000-01-01 00:00:00',
  `del` tinyint(1) NOT NULL DEFAULT 0,
  `standard` tinyint(1) NOT NULL DEFAULT 0,
  `name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `organization` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `email` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reply-to` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `bcc` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `signature` longtext COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `html_signature` tinyint(1) NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

-- --------------------------------------------------------

--
-- Structure de la table `rcb_searches`
--

CREATE TABLE `rcb_searches` (
  `search_id` int(10) UNSIGNED NOT NULL,
  `user_id` int(10) UNSIGNED NOT NULL,
  `type` int(3) NOT NULL DEFAULT 0,
  `name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `data` text COLLATE utf8mb4_unicode_ci DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

-- --------------------------------------------------------

--
-- Structure de la table `rcb_session`
--

CREATE TABLE `rcb_session` (
  `sess_id` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `changed` datetime NOT NULL DEFAULT '1000-01-01 00:00:00',
  `ip` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `vars` mediumtext COLLATE utf8mb4_unicode_ci NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

-- --------------------------------------------------------

--
-- Structure de la table `rcb_system`
--

CREATE TABLE `rcb_system` (
  `name` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `value` mediumtext COLLATE utf8mb4_unicode_ci DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

--
-- Déchargement des données de la table `rcb_system`
--

INSERT INTO `rcb_system` (`name`, `value`) VALUES
('roundcube-version', '2020122900');

-- --------------------------------------------------------

--
-- Structure de la table `rcb_users`
--

CREATE TABLE `rcb_users` (
  `user_id` int(10) UNSIGNED NOT NULL,
  `username` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `mail_host` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created` datetime NOT NULL DEFAULT '1000-01-01 00:00:00',
  `last_login` datetime DEFAULT NULL,
  `failed_login` datetime DEFAULT NULL,
  `failed_login_counter` int(10) UNSIGNED DEFAULT NULL,
  `language` varchar(16) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `preferences` longtext COLLATE utf8mb4_unicode_ci DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

--
-- Index pour les tables déchargées
--

--
-- Index pour la table `rcb_cache`
--
ALTER TABLE `rcb_cache`
  ADD PRIMARY KEY (`user_id`,`cache_key`),
  ADD KEY `rcb_expires_index` (`expires`);

--
-- Index pour la table `rcb_cache_index`
--
ALTER TABLE `rcb_cache_index`
  ADD PRIMARY KEY (`user_id`,`mailbox`),
  ADD KEY `rcb_expires_index` (`expires`);

--
-- Index pour la table `rcb_cache_messages`
--
ALTER TABLE `rcb_cache_messages`
  ADD PRIMARY KEY (`user_id`,`mailbox`,`uid`),
  ADD KEY `rcb_expires_index` (`expires`);

--
-- Index pour la table `rcb_cache_shared`
--
ALTER TABLE `rcb_cache_shared`
  ADD PRIMARY KEY (`cache_key`),
  ADD KEY `rcb_expires_index` (`expires`);

--
-- Index pour la table `rcb_cache_thread`
--
ALTER TABLE `rcb_cache_thread`
  ADD PRIMARY KEY (`user_id`,`mailbox`),
  ADD KEY `rcb_expires_index` (`expires`);

--
-- Index pour la table `rcb_collected_addresses`
--
ALTER TABLE `rcb_collected_addresses`
  ADD PRIMARY KEY (`address_id`),
  ADD UNIQUE KEY `rcb_user_email_collected_addresses_index` (`user_id`,`type`,`email`);

--
-- Index pour la table `rcb_contactgroupmembers`
--
ALTER TABLE `rcb_contactgroupmembers`
  ADD PRIMARY KEY (`contactgroup_id`,`contact_id`),
  ADD KEY `rcb_contactgroupmembers_contact_index` (`contact_id`);

--
-- Index pour la table `rcb_contactgroups`
--
ALTER TABLE `rcb_contactgroups`
  ADD PRIMARY KEY (`contactgroup_id`),
  ADD KEY `rcb_contactgroups_user_index` (`user_id`,`del`);

--
-- Index pour la table `rcb_contacts`
--
ALTER TABLE `rcb_contacts`
  ADD PRIMARY KEY (`contact_id`),
  ADD KEY `rcb_user_contacts_index` (`user_id`,`del`);

--
-- Index pour la table `rcb_dictionary`
--
ALTER TABLE `rcb_dictionary`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `rcb_uniqueness` (`user_id`,`language`);

--
-- Index pour la table `rcb_filestore`
--
ALTER TABLE `rcb_filestore`
  ADD PRIMARY KEY (`file_id`),
  ADD UNIQUE KEY `rcb_uniqueness` (`user_id`,`context`,`filename`);

--
-- Index pour la table `rcb_identities`
--
ALTER TABLE `rcb_identities`
  ADD PRIMARY KEY (`identity_id`),
  ADD KEY `rcb_user_identities_index` (`user_id`,`del`),
  ADD KEY `rcb_email_identities_index` (`email`,`del`);

--
-- Index pour la table `rcb_searches`
--
ALTER TABLE `rcb_searches`
  ADD PRIMARY KEY (`search_id`),
  ADD UNIQUE KEY `rcb_uniqueness` (`user_id`,`type`,`name`);

--
-- Index pour la table `rcb_session`
--
ALTER TABLE `rcb_session`
  ADD PRIMARY KEY (`sess_id`),
  ADD KEY `rcb_changed_index` (`changed`);

--
-- Index pour la table `rcb_system`
--
ALTER TABLE `rcb_system`
  ADD PRIMARY KEY (`name`);

--
-- Index pour la table `rcb_users`
--
ALTER TABLE `rcb_users`
  ADD PRIMARY KEY (`user_id`),
  ADD UNIQUE KEY `rcb_username` (`username`,`mail_host`);

--
-- AUTO_INCREMENT pour les tables déchargées
--

--
-- AUTO_INCREMENT pour la table `rcb_collected_addresses`
--
ALTER TABLE `rcb_collected_addresses`
  MODIFY `address_id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT pour la table `rcb_contactgroups`
--
ALTER TABLE `rcb_contactgroups`
  MODIFY `contactgroup_id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT pour la table `rcb_contacts`
--
ALTER TABLE `rcb_contacts`
  MODIFY `contact_id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT pour la table `rcb_dictionary`
--
ALTER TABLE `rcb_dictionary`
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT pour la table `rcb_filestore`
--
ALTER TABLE `rcb_filestore`
  MODIFY `file_id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT pour la table `rcb_identities`
--
ALTER TABLE `rcb_identities`
  MODIFY `identity_id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT pour la table `rcb_searches`
--
ALTER TABLE `rcb_searches`
  MODIFY `search_id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT pour la table `rcb_users`
--
ALTER TABLE `rcb_users`
  MODIFY `user_id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- Contraintes pour les tables déchargées
--

--
-- Contraintes pour la table `rcb_cache`
--
ALTER TABLE `rcb_cache`
  ADD CONSTRAINT `rcb_user_id_fk_cache` FOREIGN KEY (`user_id`) REFERENCES `rcb_users` (`user_id`) ON DELETE CASCADE ON UPDATE CASCADE;

--
-- Contraintes pour la table `rcb_cache_index`
--
ALTER TABLE `rcb_cache_index`
  ADD CONSTRAINT `rcb_user_id_fk_cache_index` FOREIGN KEY (`user_id`) REFERENCES `rcb_users` (`user_id`) ON DELETE CASCADE ON UPDATE CASCADE;

--
-- Contraintes pour la table `rcb_cache_messages`
--
ALTER TABLE `rcb_cache_messages`
  ADD CONSTRAINT `rcb_user_id_fk_cache_messages` FOREIGN KEY (`user_id`) REFERENCES `rcb_users` (`user_id`) ON DELETE CASCADE ON UPDATE CASCADE;

--
-- Contraintes pour la table `rcb_cache_thread`
--
ALTER TABLE `rcb_cache_thread`
  ADD CONSTRAINT `rcb_user_id_fk_cache_thread` FOREIGN KEY (`user_id`) REFERENCES `rcb_users` (`user_id`) ON DELETE CASCADE ON UPDATE CASCADE;

--
-- Contraintes pour la table `rcb_collected_addresses`
--
ALTER TABLE `rcb_collected_addresses`
  ADD CONSTRAINT `rcb_user_id_fk_collected_addresses` FOREIGN KEY (`user_id`) REFERENCES `rcb_users` (`user_id`) ON DELETE CASCADE ON UPDATE CASCADE;

--
-- Contraintes pour la table `rcb_contactgroupmembers`
--
ALTER TABLE `rcb_contactgroupmembers`
  ADD CONSTRAINT `rcb_contact_id_fk_contacts` FOREIGN KEY (`contact_id`) REFERENCES `rcb_contacts` (`contact_id`) ON DELETE CASCADE ON UPDATE CASCADE,
  ADD CONSTRAINT `rcb_contactgroup_id_fk_contactgroups` FOREIGN KEY (`contactgroup_id`) REFERENCES `rcb_contactgroups` (`contactgroup_id`) ON DELETE CASCADE ON UPDATE CASCADE;

--
-- Contraintes pour la table `rcb_contactgroups`
--
ALTER TABLE `rcb_contactgroups`
  ADD CONSTRAINT `rcb_user_id_fk_contactgroups` FOREIGN KEY (`user_id`) REFERENCES `rcb_users` (`user_id`) ON DELETE CASCADE ON UPDATE CASCADE;

--
-- Contraintes pour la table `rcb_contacts`
--
ALTER TABLE `rcb_contacts`
  ADD CONSTRAINT `rcb_user_id_fk_contacts` FOREIGN KEY (`user_id`) REFERENCES `rcb_users` (`user_id`) ON DELETE CASCADE ON UPDATE CASCADE;

--
-- Contraintes pour la table `rcb_dictionary`
--
ALTER TABLE `rcb_dictionary`
  ADD CONSTRAINT `rcb_user_id_fk_dictionary` FOREIGN KEY (`user_id`) REFERENCES `rcb_users` (`user_id`) ON DELETE CASCADE ON UPDATE CASCADE;

--
-- Contraintes pour la table `rcb_filestore`
--
ALTER TABLE `rcb_filestore`
  ADD CONSTRAINT `rcb_user_id_fk_filestore` FOREIGN KEY (`user_id`) REFERENCES `rcb_users` (`user_id`) ON DELETE CASCADE ON UPDATE CASCADE;

--
-- Contraintes pour la table `rcb_identities`
--
ALTER TABLE `rcb_identities`
  ADD CONSTRAINT `rcb_user_id_fk_identities` FOREIGN KEY (`user_id`) REFERENCES `rcb_users` (`user_id`) ON DELETE CASCADE ON UPDATE CASCADE;

--
-- Contraintes pour la table `rcb_searches`
--
ALTER TABLE `rcb_searches`
  ADD CONSTRAINT `rcb_user_id_fk_searches` FOREIGN KEY (`user_id`) REFERENCES `rcb_users` (`user_id`) ON DELETE CASCADE ON UPDATE CASCADE;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
