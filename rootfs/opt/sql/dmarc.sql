-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Hôte : mariadb.lan
-- Généré le : jeu. 26 sep. 2024 à 21:47
-- Version du serveur : 10.11.6-MariaDB-0+deb12u1-log
-- Version de PHP : 8.2.8

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Base de données : `mail`
--

-- --------------------------------------------------------

--
-- Structure de la table `dmarc_domains`
--

CREATE TABLE `dmarc_domains` (
  `id` int(10) UNSIGNED NOT NULL,
  `fqdn` varchar(255) NOT NULL,
  `active` tinyint(1) NOT NULL,
  `description` text DEFAULT NULL,
  `created_time` datetime NOT NULL,
  `updated_time` datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_general_ci;

-- --------------------------------------------------------

--
-- Structure de la table `dmarc_reportlog`
--

CREATE TABLE `dmarc_reportlog` (
  `id` int(10) UNSIGNED NOT NULL,
  `user_id` int(10) UNSIGNED NOT NULL DEFAULT 0,
  `domain` varchar(255) DEFAULT NULL,
  `external_id` varchar(255) DEFAULT NULL,
  `event_time` datetime NOT NULL,
  `filename` varchar(255) DEFAULT NULL,
  `source` tinyint(3) UNSIGNED NOT NULL,
  `success` tinyint(1) NOT NULL,
  `message` text DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_general_ci;

-- --------------------------------------------------------

--
-- Structure de la table `dmarc_reports`
--

CREATE TABLE `dmarc_reports` (
  `id` int(10) UNSIGNED NOT NULL,
  `domain_id` int(10) NOT NULL,
  `begin_time` datetime NOT NULL,
  `end_time` datetime NOT NULL,
  `loaded_time` datetime NOT NULL,
  `org` varchar(255) NOT NULL,
  `external_id` varchar(255) NOT NULL,
  `email` varchar(255) NOT NULL,
  `extra_contact_info` varchar(255) DEFAULT NULL,
  `error_string` text DEFAULT NULL,
  `policy_adkim` varchar(20) DEFAULT NULL,
  `policy_aspf` varchar(20) DEFAULT NULL,
  `policy_p` varchar(20) DEFAULT NULL,
  `policy_sp` varchar(20) DEFAULT NULL,
  `policy_np` varchar(20) DEFAULT NULL,
  `policy_pct` varchar(20) DEFAULT NULL,
  `policy_fo` varchar(20) DEFAULT NULL,
  `seen` tinyint(1) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_general_ci;

-- --------------------------------------------------------

--
-- Structure de la table `dmarc_rptrecords`
--

CREATE TABLE `dmarc_rptrecords` (
  `id` int(10) UNSIGNED NOT NULL,
  `report_id` int(10) UNSIGNED NOT NULL,
  `ip` varbinary(16) NOT NULL,
  `rcount` int(10) UNSIGNED NOT NULL,
  `disposition` tinyint(3) UNSIGNED NOT NULL,
  `reason` text DEFAULT NULL,
  `dkim_auth` text DEFAULT NULL,
  `spf_auth` text DEFAULT NULL,
  `dkim_align` tinyint(3) UNSIGNED NOT NULL,
  `spf_align` tinyint(3) UNSIGNED NOT NULL,
  `envelope_to` varchar(255) DEFAULT NULL,
  `envelope_from` varchar(255) DEFAULT NULL,
  `header_from` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_general_ci;

-- --------------------------------------------------------

--
-- Structure de la table `dmarc_system`
--

CREATE TABLE `dmarc_system` (
  `key` varchar(64) NOT NULL,
  `user_id` int(10) UNSIGNED NOT NULL DEFAULT 0,
  `value` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_general_ci;

--
-- Déchargement des données de la table `dmarc_system`
--

INSERT INTO `dmarc_system` (`key`, `user_id`, `value`) VALUES
('version', 0, '4.0');

-- --------------------------------------------------------

--
-- Structure de la table `dmarc_userdomains`
--

CREATE TABLE `dmarc_userdomains` (
  `domain_id` int(10) UNSIGNED NOT NULL,
  `user_id` int(10) UNSIGNED NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_general_ci;

-- --------------------------------------------------------

--
-- Structure de la table `dmarc_users`
--

CREATE TABLE `dmarc_users` (
  `id` int(10) UNSIGNED NOT NULL,
  `name` varchar(32) NOT NULL,
  `level` smallint(5) UNSIGNED NOT NULL,
  `enabled` tinyint(1) NOT NULL,
  `password` varchar(255) DEFAULT NULL,
  `email` varchar(64) DEFAULT NULL,
  `key` varchar(64) DEFAULT NULL,
  `session` int(10) UNSIGNED NOT NULL,
  `created_time` datetime NOT NULL,
  `updated_time` datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_general_ci;

--
-- Index pour les tables déchargées
--

--
-- Index pour la table `dmarc_domains`
--
ALTER TABLE `dmarc_domains`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `fqdn` (`fqdn`);

--
-- Index pour la table `dmarc_reportlog`
--
ALTER TABLE `dmarc_reportlog`
  ADD PRIMARY KEY (`id`),
  ADD KEY `event_time` (`event_time`),
  ADD KEY `user_id` (`user_id`,`event_time`);

--
-- Index pour la table `dmarc_reports`
--
ALTER TABLE `dmarc_reports`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `org_time_id_u` (`domain_id`,`begin_time`,`org`,`external_id`),
  ADD KEY `begin_time` (`begin_time`),
  ADD KEY `end_time` (`end_time`),
  ADD KEY `org` (`org`,`begin_time`);

--
-- Index pour la table `dmarc_rptrecords`
--
ALTER TABLE `dmarc_rptrecords`
  ADD PRIMARY KEY (`id`),
  ADD KEY `report_id` (`report_id`),
  ADD KEY `ip` (`ip`);

--
-- Index pour la table `dmarc_system`
--
ALTER TABLE `dmarc_system`
  ADD PRIMARY KEY (`user_id`,`key`);

--
-- Index pour la table `dmarc_userdomains`
--
ALTER TABLE `dmarc_userdomains`
  ADD PRIMARY KEY (`domain_id`,`user_id`);

--
-- Index pour la table `dmarc_users`
--
ALTER TABLE `dmarc_users`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `name` (`name`);

--
-- AUTO_INCREMENT pour les tables déchargées
--

--
-- AUTO_INCREMENT pour la table `dmarc_domains`
--
ALTER TABLE `dmarc_domains`
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT pour la table `dmarc_reportlog`
--
ALTER TABLE `dmarc_reportlog`
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT pour la table `dmarc_reports`
--
ALTER TABLE `dmarc_reports`
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT pour la table `dmarc_rptrecords`
--
ALTER TABLE `dmarc_rptrecords`
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT pour la table `dmarc_users`
--
ALTER TABLE `dmarc_users`
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
