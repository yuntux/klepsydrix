<!--
### Sync Impact Report
- Version: 1.0.0 -> 1.1.0
- Ratified: 2026-05-16
- Principles Added/Modified:
  - I. Clean Architecture & Code Quality
  - II. Rigorous Testing Standards
  - III. Premium Modern UX (Glassmorphism & React)
  - IV. High-Performance Solving (Timefold/OR-Tools)
  - V. French Documentation & Pedagogical Rigor
- Modified Templates:
  - .specify/templates/plan-template.md (✅ aligned)
  - .specify/templates/spec-template.md (✅ aligned)
  - .specify/templates/tasks-template.md (✅ aligned)
-->

# Klepsydrix Constitution

Ce document définit les principes fondamentaux et les règles de développement du projet Klepsydrix.

## Core Principles

### I. Clean Architecture & Code Quality
Toutes les contributions doivent respecter une architecture claire séparant strictement le backend (API de calcul et données) du frontend (interface utilisateur interactive). Le code doit être typé (TypeScript pour le front, Type Hints pour Python/Java), lisible, et auto-documenté.

### II. Rigorous Testing Standards
Le développement doit suivre une méthodologie guidée par les tests (TDD). Les tests unitaires et d'intégration doivent couvrir toutes les fonctionnalités du graphe de données et du solveur de contraintes. L'agent AI a l'**INTERDICTION STRICTE** d'utiliser des navigateurs pour tester l'UI de manière automatisée.

### III. Premium Modern UX (React & CSS)
L'interface utilisateur doit être exceptionnelle ("WOW factor"). Elle sera développée en React (via Vite) avec une charte graphique premium (Glassmorphism, mode sombre profond, couleurs vibrantes). L'expérience utilisateur doit inclure des micro-animations fluides, et la grille horaire doit gérer le Drag & Drop massif de manière instantanée, comme une application bureau.

### IV. High-Performance Solving
La résolution d'emplois du temps (problème NP-complet) exige des performances critiques. Le moteur de calcul (solveur) doit opérer entièrement en mémoire vive pour évaluer des millions de combinaisons (via une librairie de type Timefold ou OR-Tools). La persistance doit se fonder sur une base SQL classique.
L'architecture doit permettre de gérer de nombreux établissements scolaires et leurs contraintes spécifiques.

### V. French Documentation & Pedagogical Rigor
Toutes les documentations (Specs, Plan, Tâches) et les échanges doivent être rédigés en français, avec un ton très pédagogique et détaillé. Le code source en lui-même (noms de variables, classes) sera en anglais.

## Additional Constraints

### Sécurité et Performance
- **Temps de réponse** : L'interface ne doit pas geler pendant les calculs du solveur (utilisation de WebWorkers ou d'appels asynchrones).
- **Intégrité** : Le système ne doit jamais autoriser l'enregistrement d'un emploi du temps avec un chevauchement temporel strict ("Hard Constraint") sur une ressource.

## Development Workflow

### Spec-Driven Development (SDD)
Chaque fonctionnalité doit transiter par :
1. **Spécification (`spec.md`)** : Définition des besoins.
2. **Plan Technique (`plan.md`)** : Architecture.
3. **Tâches (`tasks.md`)** : Tâches atomiques.
4. **Implémentation** : Réalisation stricte des tâches.

## Governance
Toute modification doit être justifiée et versionnée (SemVer).

**Version**: 1.1.0 | **Ratified**: 2026-05-16 | **Last Amended**: 2026-05-16
