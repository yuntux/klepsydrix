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
4. [Emploi du temps](#4-emploi-du-temps)
5. [Pré-rentrée](#5-pré-rentrée)
6. [Paramètres](#6-paramètres)
7. [Scénarios pas à pas](#7-scénarios-pas-à-pas)
8. [FAQ / Dépannage](#8-faq--dépannage)

## 1. Introduction

### Qu'est-ce que Klepsydrix

Klepsydrix est une application de gestion des emplois du temps scolaires. Elle couvre
l'ensemble du cycle : modélisation des ressources de l'établissement (classes, groupes,
enseignants, salles, matières, matériels), préparation de la rentrée (TRMD, services,
génération automatique des cours et des groupes), construction de l'emploi du temps annuel à
l'aide d'un moteur de contraintes (placement automatique des cours, attribution des salles,
optimisation), puis son exploitation au quotidien.

### À qui s'adresse ce manuel

Ce manuel s'adresse au **chef d'établissement**, ou plus largement à toute personne disposant du
profil **admin** sur une base Klepsydrix (une base = un établissement). C'est l'utilisateur
principal de l'application : il paramètre l'établissement, saisit ou importe ses ressources, et
construit l'emploi du temps. Un même établissement peut avoir plusieurs comptes admin (ex. un
adjoint en charge des emplois du temps) — voir [§6.3 Comptes & droits](#63-comptes--droits) pour
en créer.

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

## 4. Emploi du temps

### 4.1 Visualiseur (grille EDT)

<!-- SCREENSHOT: timetable-grid -->
![Grille de l'emploi du temps](screenshots/chef_etablissement/timetable-grid.png)

*TODO : lecture de la grille, filtres, impression.*

### 4.2 Classes

<!-- SCREENSHOT: divisions-list -->
![Classes — Liste](screenshots/chef_etablissement/divisions-list.png)

*TODO : créer/éditer une classe, parties de classe.*

#### Vœux et contraintes

<!-- SCREENSHOT: divisions-preferences -->
![Classes — Vœux et contraintes](screenshots/chef_etablissement/divisions-preferences.png)

*TODO : préférences horaires, contraintes dures/souples.*

### 4.3 Groupes

*TODO*

### 4.4 Enseignants

<!-- SCREENSHOT: teachers-list -->
![Enseignants — Liste](screenshots/chef_etablissement/teachers-list.png)

*TODO : fiche enseignant, vœux et contraintes.*

### 4.5 Personnel non enseignant

*TODO*

### 4.6 Salles

*TODO : types de salles, vœux d'occupation.*

### 4.7 Matières

*TODO : contraintes deux à deux entre matières.*

### 4.8 Matériels

*TODO*

### 4.9 Cours

<!-- SCREENSHOT: courses-list -->
![Cours — Liste](screenshots/chef_etablissement/courses-list.png)

*TODO : décomposition d'un cours, vœux, contraintes.*

### 4.10 Placement automatique, salles, optimisation

*TODO : lancer le solveur, interpréter les résultats, résoudre les conflits.*

## 5. Pré-rentrée

### 5.1 MEF et services

*TODO : MEF, services par classe, heures par discipline/professeur/division.*

### 5.2 TRMD

<!-- SCREENSHOT: trmd -->
![Synthèse TRMD](screenshots/chef_etablissement/trmd.png)

*TODO : synthèse TRMD, répartition des moyens.*

### 5.3 Élèves et seuils de spécialité

*TODO*

### 5.4 Génération automatique

*TODO : génération des cours, affectation des professeurs, groupes de spécialité.*

### 5.5 Import STS-web

*TODO : format attendu, étapes d'import, contrôle des anomalies.*

## 6. Paramètres

### 6.1 Grille horaire, établissement, disciplines, périodes

*TODO*

### 6.2 Référentiels

*TODO : liste des référentiels (corps, grades, villes, pays, etc.) et quand les modifier.*

### 6.3 Comptes & droits

<!-- SCREENSHOT: accounts-users -->
![Comptes & droits — Utilisateurs](screenshots/chef_etablissement/accounts-users.png)

*TODO : créer un utilisateur, groupes de droits, connexions/fournisseurs d'identité.*

## 7. Scénarios pas à pas

*TODO : parcours complets illustrés, ex. « créer une classe de A à Z », « générer puis placer les
cours d'une rentrée », « gérer le remplacement d'un professeur absent ».*

## 8. FAQ / Dépannage

*TODO : questions fréquentes, messages d'erreur courants et leur résolution.*
