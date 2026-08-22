# Guide utilisateur — Chef d'établissement

Ce document s'adresse au chef d'établissement (ou à toute personne disposant du profil
**admin** sur une base Klepsydrix), utilisateur principal de l'application au quotidien : c'est
lui qui construit, ajuste et publie l'emploi du temps de son établissement.

Pour la gestion du serveur lui-même (installation, création de bases, super-administration),
voir [superadmin_doc.md](superadmin_doc.md) — un profil distinct, généralement tenu par une
autre personne.

> Les captures d'écran de ce document sont générées automatiquement depuis la base de
> démonstration par `frontend/scripts/doc-screenshots/capture-chef-etablissement.mjs`. Ne pas
> les remplacer à la main : relancer le script après une évolution de l'interface.

## Sommaire

1. [Introduction](#1-introduction)
2. [Connexion et compte](#2-connexion-et-compte)
3. [Prise en main de l'interface](#3-prise-en-main-de-linterface)
4. [Paramétrer l'établissement (Étape 1)](#4-paramétrer-létablissement-étape-1)
5. [Constituer les données de base (Étape 2)](#5-constituer-les-données-de-base-étape-2)
6. [Préparer la rentrée (Étape 3)](#6-préparer-la-rentrée-étape-3)
7. [Définir les vœux et contraintes (Étape 4)](#7-définir-les-vœux-et-contraintes-étape-4)
8. [Construire l'emploi du temps (Étape 5)](#8-construire-lemploi-du-temps-étape-5)
9. [Consulter et exploiter l'emploi du temps (Étape 6)](#9-consulter-et-exploiter-lemploi-du-temps-étape-6)
10. [Administrer les comptes et les référentiels](#10-administrer-les-comptes-et-les-référentiels)
11. [Scénarios pas à pas](#11-scénarios-pas-à-pas)
12. [FAQ / Dépannage](#12-faq--dépannage)

## 1. Introduction

### Qu'est-ce que Klepsydrix

Klepsydrix est une application de gestion des emplois du temps scolaires. Elle couvre
l'ensemble du cycle : modélisation des ressources de l'établissement (classes, groupes,
enseignants, salles, matières, matériels), préparation de la rentrée (TRMD, services,
génération automatique des cours et des groupes), construction de l'emploi du temps annuel à
l'aide d'un moteur de contraintes (placement automatique des cours, attribution des salles,
optimisation).

### À qui s'adresse ce manuel

Ce manuel s'adresse au **chef d'établissement**, ou plus largement à toute personne disposant du
profil **admin** sur une base Klepsydrix (une base = un établissement). C'est l'utilisateur
principal de l'application : il paramètre l'établissement, saisit ou importe ses ressources, et
construit l'emploi du temps. Un même établissement peut avoir plusieurs comptes admin (ex. un
adjoint en charge des emplois du temps) — voir [§10.1](#101-comptes--droits) pour en créer.

### Le parcours en un coup d'œil

Ce manuel suit l'ordre dans lequel un établissement construit concrètement son emploi du temps,
d'une base toute neuve jusqu'à l'emploi du temps publié :

1. **[Paramétrer l'établissement](#4-paramétrer-létablissement-étape-1)** — calendrier de
   l'année, grille horaire, disciplines.
2. **[Constituer les données de base](#5-constituer-les-données-de-base-étape-2)** — importer
   depuis STS-web ou saisir classes, enseignants, salles, matières.
3. **[Préparer la rentrée](#6-préparer-la-rentrée-étape-3)** — MEF, TRMD, élèves, génération
   automatique des cours et des groupes.
4. **[Définir les vœux et contraintes](#7-définir-les-vœux-et-contraintes-étape-4)** — souhaits
   et contraintes de chaque ressource, avant placement.
5. **[Construire l'emploi du temps](#8-construire-lemploi-du-temps-étape-5)** — placement
   automatique, salles, optimisation.
6. **[Consulter et exploiter l'emploi du temps](#9-consulter-et-exploiter-lemploi-du-temps-étape-6)**
   — le visualiseur, au quotidien.

Les comptes utilisateurs et les référentiels RH
([§10](#10-administrer-les-comptes-et-les-référentiels)) se gèrent à part, au besoin — pas comme
une étape obligatoire de ce parcours.

*TODO : illustrer par une capture la page d'accueil / le tableau de bord si l'application en
propose un.*

## 2. Connexion et compte

- Se connecter avec un compte local ou via un fournisseur fédéré (ex. EduConnect) si configuré
  par le super-administrateur.
- Changer son mot de passe.
- Réinitialiser son mot de passe en cas d'oubli.

<!-- SCREENSHOT: login -->
![Écran de connexion](screenshots/chef_etablissement/login.png)

*TODO : détailler le formulaire de connexion et le choix de fournisseur d'identité.*

## 3. Prise en main de l'interface

L'application s'organise en une arborescence à gauche (Emploi du temps / Pré-rentrée /
Paramètres) et un ou plusieurs panneaux à droite selon l'écran sélectionné : listes, formulaires,
grille horaire, vœux et contraintes.

*TODO : décrire la navigation (groupes/sous-groupes repliables), le panneau maître/détail, et le
changement de base de données depuis le pied de l'arborescence.*

## 4. Paramétrer l'établissement (Étape 1)

Avant de saisir la moindre classe ou le moindre enseignant, quelques réglages structurent tout
le reste : le calendrier de l'année, les horaires de la grille, la liste des disciplines
enseignées. C'est la première chose à faire à l'ouverture d'une nouvelle base — vous pouvez aussi
dès maintenant créer des comptes pour vos collègues (voir [§10.1](#101-comptes--droits)).

### 4.1 Grille horaire, établissement, disciplines, périodes

*TODO*

## 5. Constituer les données de base (Étape 2)

Deux façons de peupler la base avec les classes, enseignants, salles et matières de
l'établissement : importer un flux STS-web existant (le plus rapide si l'académie le fournit),
ou saisir manuellement chaque ressource.

### 5.1 Importer depuis STS-web (recommandé)

*TODO : format attendu, étapes d'import, contrôle des anomalies.*

### 5.2 Classes

<!-- SCREENSHOT: divisions-list -->
![Classes — Liste](screenshots/chef_etablissement/divisions-list.png)

*TODO : créer/éditer une classe, parties de classe.*

### 5.3 Groupes

*TODO*

### 5.4 Enseignants

<!-- SCREENSHOT: teachers-list -->
![Enseignants — Liste](screenshots/chef_etablissement/teachers-list.png)

*TODO : fiche enseignant.*

### 5.5 Personnel non enseignant

*TODO*

### 5.6 Salles

*TODO : types de salles.*

### 5.7 Matières

*TODO*

### 5.8 Matériels

*TODO*

## 6. Préparer la rentrée (Étape 3)

Une fois les ressources de base en place, la pré-rentrée détermine les besoins en heures
d'enseignement et génère automatiquement l'essentiel des cours et des groupes à placer.

### 6.1 MEF et services

*TODO : MEF, services par classe, heures par discipline/professeur/division.*

### 6.2 TRMD

<!-- SCREENSHOT: trmd -->
![Synthèse TRMD](screenshots/chef_etablissement/trmd.png)

*TODO : synthèse TRMD, répartition des moyens.*

### 6.3 Élèves et seuils de spécialité

*TODO*

### 6.4 Génération automatique des cours et des groupes

*TODO : génération des cours, affectation des professeurs, groupes de spécialité.*

### 6.5 Cours — consulter et ajuster la liste générée

<!-- SCREENSHOT: courses-list -->
![Cours — Liste](screenshots/chef_etablissement/courses-list.png)

*TODO : décomposition d'un cours, ajustement de la liste générée automatiquement.*

## 7. Définir les vœux et contraintes (Étape 4)

Avant de lancer le placement automatique, indiquez les souhaits (créneaux préférés) et
contraintes (indisponibilités, interdictions) de chaque ressource — c'est ce qui guide le
solveur vers un emploi du temps réellement exploitable.

### 7.1 Classes — vœux et contraintes

<!-- SCREENSHOT: divisions-preferences -->
![Classes — Vœux et contraintes](screenshots/chef_etablissement/divisions-preferences.png)

*TODO : préférences horaires, contraintes dures/souples.*

### 7.2 Groupes — vœux et contraintes

*TODO*

### 7.3 Enseignants — vœux et contraintes

*TODO*

### 7.4 Personnel non enseignant — vœux

*TODO*

### 7.5 Salles — vœux

*TODO : vœux d'occupation.*

### 7.6 Matières — contraintes deux à deux

*TODO*

### 7.7 Cours — vœux et contraintes

*TODO*

## 8. Construire l'emploi du temps (Étape 5)

Les ressources, cours, vœux et contraintes en place, place à la construction proprement dite de
l'emploi du temps.

### 8.1 Placement automatique, attribution des salles, optimisation

*TODO : lancer le solveur, interpréter les résultats, résoudre les conflits.*

## 9. Consulter et exploiter l'emploi du temps (Étape 6)

Une fois l'emploi du temps construit, le visualiseur est l'écran que vous et vos équipes
consulterez le plus souvent au quotidien.

### 9.1 Visualiseur (grille EDT)

<!-- SCREENSHOT: timetable-grid -->
![Grille de l'emploi du temps](screenshots/chef_etablissement/timetable-grid.png)

*TODO : lecture de la grille, filtres, impression.*

## 10. Administrer les comptes et les référentiels

Tâches d'administration ponctuelles, pas des étapes du parcours de construction : gérer qui a
accès à la base, et tenir à jour les tables de référence RH utilisées ailleurs dans
l'application.

### 10.1 Comptes & droits

<!-- SCREENSHOT: accounts-users -->
![Comptes & droits — Utilisateurs](screenshots/chef_etablissement/accounts-users.png)

*TODO : créer un utilisateur, groupes de droits, connexions/fournisseurs d'identité.*

### 10.2 Référentiels

*TODO : liste des référentiels (corps, grades, villes, pays, etc.) et quand les modifier.*

## 11. Scénarios pas à pas

*TODO : parcours complets illustrés, ex. « créer une classe de A à Z », « générer puis placer les
cours d'une rentrée », « gérer le remplacement d'un professeur absent ».*

## 12. FAQ / Dépannage

*TODO : questions fréquentes, messages d'erreur courants et leur résolution.*
