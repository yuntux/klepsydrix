# Klepsydrix - Frontend Vue 3

Ce dossier contient l'interface utilisateur web moderne et premium de Klepsydrix, construite en Vue 3 avec TypeScript, Vite et CSS Vanilla.

## Fonctionnalités

- **Abonnement temps réel & Thème sombre** : Palette sombre futuriste avec effets de glassmorphism et de glows néon.
- **Grille interactive hebdomadaire** : Affichage multi-mode (par classe/division, par enseignant, par salle).
- **Drag & Drop HTML5** : Permet de planifier des cours en les glissant depuis le panneau latéral vers la grille, ou de les réorganiser directement sur la grille.
- **Gestion des Conflits** : Retour visuel immédiat et système de reversion en cas d'erreur de conflit (409) renvoyée par le serveur.

## Démarrage rapide

1. Installer les dépendances :
   ```bash
   npm install
   ```
2. Lancer l'application en mode développement :
   ```bash
   npm run dev -- --port 3000
   ```
3. Compiler pour la production :
   ```bash
   npm run build
   ```
