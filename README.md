# klepsydrix
Scolar Timetabling module


## Lotissement des fonctionnalités à implémenter
Ce chapitre présente les différents lots fonctionnels envisagés pour l'implémentation complète de l'application.

### 1. Socle de l'architecture
Ce lot définit le périmètre d'une V1 "Tranche Verticale" pour Klepsydrix. L'objectif est de poser une première version fonctionnelle complète d'un flux d'emploi du temps, de sa persistance à son optimisation automatique via un moteur de contraintes, jusqu'à sa visualisation dans une interface utilisateur interactive de qualité professionnelle.

### 2. Emploi du temps annuel
- IHM
    - Composants d'IHM de base : onglets/pannels, tables et formulaires génériques
    - Composants d'IHM spécifiques : composant "préférences", composant emploi du temps / planning, fiche T (fiche récapitulative des cours d'une sélection)

- Modélisation des ressources de l'emploi du temps:
    - Classes / parties de classe / groupes d'élèves
    - Enseignants / équipes pédagogiques
    - Personnels non-enseignants (surveillance, vie scolaire)
    - Matières / Disciplines
    - Matériels
    - Salles / sites / groupes de salles
    - Créneaux temporels
    - Cours
    - Ajout d'un commentaire à l'objet préférence et à l'objet contrainte

- Calculs : 
    - Intégration du moteur de contraintes pour la résolution de l'emploi du temps
    - Planification avancée annuelle (Alternances A/B, Groupes)
    - Expliquer à l'utilisateur pourquoi il n'est pas possible de placer un cours sur tel créneau
    - Montrer sur le calendrier les "poids" des différentes créeaux sur lesquels on pourrait placer un cours
    - Lister tous les cours non placés qui peuvent aller dans ce créeaux (tet lees classer par "poiods")
    - Afficher els permuttaions possibles de cours déjà placés.
    - Voir les salles libres sur un créneau et les cours sans salles

- Paramétrage : 
    - du calendrier de l'année (jours travaillés, horaires, etc) de chaque établissement
    - de l'établissement
    - des disciplines et de leurs enseignants


### 3. Pré-rentrée
- Gestion du TRMD
- Paramétrage des spécificités et parcours de formation (Options 2ndes, Spécialités 1eres et Terminales...)
- Génération automatique des cours
- Affections automatique des élèves aux classes
- Génération automatique des groupes et affectation automatique des élèves aux groupes
- Fonction d'ajustement en masse des liens entre groupes en fonction de la répartition des élèvs dans les groupes

### 4. Emploi du temps opérationnel (hebdomadaire)
- Déclinaison de l'emploi du temps annuel en emploi du temps hebdomadaire
- Gestion des suppressions / ajouts de cours
- Gestion des remplacements et absences de professeurs/personnels
- Gestion des changements de salles
- Gestion des élèves et de leurs responsables
- Gestion de la pause déjeuner
- Gestion des permanences / CDI
- Recherche des salles disponibles
- Gestion des statistiques

### 5. Rencontres parents professeurs
- Paramétrage des rencontres parents professeurs
- Collecte des veoux des parents et des professeurs
- Génération automatique des créneaux de rencontre

### 6. Conseils de classe
- Paramétrage des délégués des parents et des élèves sur les classes
- Planification des conseils de classe
- Génération automatique des créneaux de conseil de classe

### 7. Imports et export des données
- Import des fichiers SIECLE / STSWeb
- Export des données vers STSWeb (groupe, affectation des élèves aux groupes, emploi du temps)
- Intégration des webservices Omogen (anciennement Netsynchro)
- Import / export génériqus (CSV et XML)
- Capacité à exporter des données tabulaires via CTR/Cmd + C / CTRL/Cmd + V dans un tableur (libreoffice / excel ...)
- Capacité à importer des données tabulaires via CTRL/Cmd + C / CTRL/Cmd + V depuis un tableur (libreoffice / excel ...)

### 8. Communication avec les acteurs
- Impression des emplois du temps (PDF)
- Publication des emplois du temps (portail intranet / ENT)
- Envoi d'emails / SMS / notifications aux parents / professeurs / élèves

### 9. Gestion des utilisateurs et des droits
- Intégration d'une gestion fine des droits d'accès
- Intégration d'une gestion des permissions par profil
- Connexion locale ou via SSO
- Traçabilité des actions (qui a fait quoi, quand)

### 10. Ergonomie / pilotage
- Intégration d'un "cockpit" pour visualiser les indicateurs clés du quotient
- Intégration de tableaux de bord de suivi de la qualité des emplois du temps

### 11. Gestion des gros volumes d'établissements
- Migration vers PostgreSQL
- Possibilité de versionner / snapshot de la base de données (que l'on travaille en local ou sur le serveur centralisé)
- IHM d'administration des bases de données et pilotage technique de l'infrastructure
- Mode "calcul annuel" en local : 
    - Verrouillage des données du serveur centralisé quand un planificateur travaille sur son poste en mode déconnecté.
    - Intégration dans la JVM locale ou bien capacité à faire tourner le moteur de calcul Timefold en local. Les résultats des calculs sont ensuite renvoyés au serveur centralisé à la reconnexion.
