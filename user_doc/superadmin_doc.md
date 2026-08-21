# Guide super-administrateur

Ce document s'adresse au **super-administrateur** de l'instance Klepsydrix : la personne qui
héberge et exploite le serveur, distincte du chef d'établissement (voir
[chef_etablissement_doc.md](chef_etablissement_doc.md)), qui n'a lui accès qu'aux données de sa
propre base.

Un super-administrateur agit au niveau de l'**instance** (le serveur, potentiellement partagé par
plusieurs établissements/bases) ; un admin de base n'agit que sur **sa** base (sauvegarde,
restauration, suppression — ni création, ni duplication).

> Les captures d'écran de ce document sont générées automatiquement par
> `frontend/scripts/doc-screenshots/capture-superadmin.mjs`. Ne pas les remplacer à la main :
> relancer le script après une évolution de l'interface.

## Sommaire

1. [Introduction](#1-introduction)
2. [Installation et démarrage](#2-installation-et-démarrage)
3. [Configuration de l'instance (`instance.yaml`)](#3-configuration-de-linstance-instanceyaml)
4. [Sécurité](#4-sécurité)
5. [Fournisseurs d'identité](#5-fournisseurs-didentité)
6. [Accès à la console super-admin](#6-accès-à-la-console-super-admin)
7. [Console d'administration](#7-console-dadministration)
8. [Emails sortants (SMTP)](#8-emails-sortants-smtp)
9. [Sauvegardes — bonnes pratiques](#9-sauvegardes--bonnes-pratiques)
10. [Dépannage / logs](#10-dépannage--logs)

## 1. Introduction

### Qu'est-ce que Klepsydrix

Klepsydrix est une application de gestion des emplois du temps scolaires. Elle est déployée sous
forme d'une **instance** de serveur qui peut héberger plusieurs **bases** indépendantes, une base
par établissement, chacune avec ses propres ressources (classes, enseignants, salles, emplois du
temps) et ses propres comptes.

### À qui s'adresse ce manuel

Ce manuel s'adresse au **super-administrateur** : la personne qui installe, configure et
maintient le serveur (souvent un service informatique académique ou un prestataire
d'hébergement), par opposition au chef d'établissement (voir
[chef_etablissement_doc.md](chef_etablissement_doc.md)) qui, lui, ne travaille qu'à l'intérieur
d'une base pour construire l'emploi du temps de son établissement. Le super-administrateur n'a
normalement pas vocation à modifier les données métier d'une base — son rôle porte sur
l'instance : création/duplication/suppression des bases, fournisseurs d'identité, sécurité,
sauvegardes.

## 2. Installation et démarrage

Le script `start_services.sh` (racine du dépôt) pilote le backend (FastAPI/uvicorn, port 8000) et
le frontend (Vite, port 3000) :

```bash
./start_services.sh start
./start_services.sh status
./start_services.sh logs
./start_services.sh stop
```

*TODO : prérequis d'installation (Python venv backend, `npm install` frontend), déploiement en
production (reverse proxy, `deploy/fail2ban`).*

## 3. Configuration de l'instance (`instance.yaml`)

Fichier à la racine du dépôt (gitignoré), copié depuis `instance.example.yaml`. Sections
principales : `database` (sqlite/postgresql), `server` (origines autorisées, proxies de
confiance, `public_base_url`), `secret_key`.

*TODO : détailler chaque section avec un exemple commenté, et le cas PostgreSQL en production.*

## 4. Sécurité

- `secret_key` : signe les cookies de session — à surcharger impérativement en production.
- `master_db_local_auth.ip_allowlist` : restriction d'IP pour le mot de passe maître.
- `auth.session_idle_timeout_minutes` : durée d'inactivité avant expiration de session.
- `deploy/fail2ban` : protection contre le bruteforce au niveau serveur.

*TODO : checklist de mise en production.*

## 5. Fournisseurs d'identité

Déclarés dans `instance.yaml::identity_providers` — un provider `local` actif par défaut, et des
fournisseurs OIDC fédérés (ex. EduConnect) à configurer avec de vrais paramètres pour la
production.

*TODO : procédure d'ajout d'un fournisseur OIDC, mapping des claims.*

## 6. Accès à la console super-admin

Deux voies, non exclusives :

- **Mot de passe maître** (`instance.yaml::master_db_local_auth`) : voie de secours/dev, un
  secret partagé, désactivée par défaut.
- **Paires `super_admins` nommées** (`provider_key` + `subject` OIDC) : voie normale en
  production, nécessite un fournisseur fédéré actif.

<!-- SCREENSHOT: master-login -->
![Connexion maître (super-admin)](screenshots/superadmin/master-login.png)

*TODO : générer le hash Argon2id du mot de passe maître, procédure pour nommer un super-admin
OIDC.*

## 7. Console d'administration

Accessible sur `/admin` une fois authentifié. Liste les bases administrables et propose, selon le
niveau d'accès : sauvegarder, dupliquer, restaurer, supprimer, et (super-admin uniquement) créer
une base.

<!-- SCREENSHOT: admin-console -->
![Console d'administration — liste des bases](screenshots/superadmin/admin-console.png)

### Créer une base

<!-- SCREENSHOT: admin-console-create -->
![Créer une base](screenshots/superadmin/admin-console-create.png)

*TODO : détailler chaque action (créer, dupliquer, sauvegarder/restaurer, supprimer) avec ses
garde-fous (confirmation par saisie du nom de la base).*

## 8. Emails sortants (SMTP)

Configuré dans `instance.yaml::smtp`. Utilisé pour les emails de réinitialisation de mot de passe
(demande self-service et création de base avec admin désigné).

*TODO : paramètres attendus, comportement en cas d'échec d'envoi (jamais de repli silencieux).*

## 9. Sauvegardes — bonnes pratiques

*TODO : fréquence recommandée, où stocker les sauvegardes téléchargées, procédure de
restauration testée.*

## 10. Dépannage / logs

`backend.log` et `frontend.log` à la racine du dépôt (voir `start_services.sh logs`).

*TODO : messages d'erreur courants côté instance (401 `NOT_AUTHENTICATED`, 404/428
`DATABASE_UNKNOWN`, etc.) et leur résolution.*
