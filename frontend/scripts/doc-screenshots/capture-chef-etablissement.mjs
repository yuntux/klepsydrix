#!/usr/bin/env node
// Capture les copies d'écran illustrant user_doc/chef_etablissement_doc.md, à partir de la base de
// démonstration (backend/app/core/init_demo.py). Prérequis : backend + frontend démarrés
// (./start_services.sh start, voir ../../../user_doc/superadmin_doc.md §2).
//
//   node frontend/scripts/doc-screenshots/capture-chef-etablissement.mjs
//
// Idempotent : peut être rejoué après une évolution de l'IHM pour rafraîchir les images.
import path from 'node:path';
import {
  withBrowser, capture, openTreePath, loginAsDemo,
  USER_DOC_DIR, BASE_URL, DEMO_DB,
} from './lib.mjs';

const DOC_FILE = path.join(USER_DOC_DIR, 'chef_etablissement_doc.md');
const SUBDIR = 'chef_etablissement';

async function run() {
  await withBrowser(async (page) => {
    // --- Connexion (page de login, non authentifié) ---
    await page.goto(`${BASE_URL}/login?db=${DEMO_DB}`);
    await page.waitForSelector('text=Se connecter', { timeout: 15000 }).catch(() => {});
    await capture(page, { docFile: DOC_FILE, id: 'login', caption: 'Écran de connexion', subdir: SUBDIR });

    // --- Authentification réelle (API, comme frontend/e2e/helpers.ts::loginAsDemo) puis sélection
    // de la base courante (cookie klepsydrix_db, posé normalement par SelectDatabase.vue — voir
    // frontend/src/services/dbSession.ts) ---
    await loginAsDemo(page);
    await page.context().addCookies([
      { name: 'klepsydrix_db', value: DEMO_DB, url: BASE_URL },
    ]);

    await page.goto(BASE_URL);
    await page.waitForSelector('.sidebar', { timeout: 15000 });

    // --- Visualiseur (grille EDT), écran d'accueil par défaut. De nombreux composants (grille,
    // filtres, panneau "Cours à planifier") sont chargés en lazy et prennent plus que quelques
    // centaines de ms à apparaître sur un contexte de navigateur tout neuf — on attend un élément
    // réellement présent dans la grille rendue plutôt qu'un délai fixe trop court (observé : grille
    // capturée vide malgré des données bien chargées, uniquement un problème de timing du script).
    await page.waitForSelector('text=Cours à planifier', { timeout: 20000 }).catch(() => {});
    await capture(page, { docFile: DOC_FILE, id: 'timetable-grid', caption: "Grille de l'emploi du temps", subdir: SUBDIR, waitMs: 1000 });

    // --- Classes > Liste ---
    await openTreePath(page, ['Emploi du temps', 'Classes', 'Liste']);
    await capture(page, { docFile: DOC_FILE, id: 'divisions-list', caption: 'Classes — Liste', subdir: SUBDIR });

    // --- Classes > Vœux et contraintes (sélectionne la première classe pour illustrer un vrai
    // panneau de contraintes plutôt que l'état vide "Sélectionnez un élément") ---
    await openTreePath(page, ['Emploi du temps', 'Classes', 'Vœux et contraintes']);
    await page.getByText('6A', { exact: true }).first().click().catch(() => {});
    await capture(page, { docFile: DOC_FILE, id: 'divisions-preferences', caption: 'Classes — Vœux et contraintes', subdir: SUBDIR });

    // --- Enseignants > Liste ---
    await openTreePath(page, ['Emploi du temps', 'Enseignants', 'Liste']);
    await capture(page, { docFile: DOC_FILE, id: 'teachers-list', caption: 'Enseignants — Liste', subdir: SUBDIR });

    // --- Cours > Liste ---
    await openTreePath(page, ['Emploi du temps', 'Cours', 'Liste']);
    await capture(page, { docFile: DOC_FILE, id: 'courses-list', caption: 'Cours — Liste', subdir: SUBDIR });

    // --- Pré-rentrée > TRMD ---
    await openTreePath(page, ['Pré-rentrée', 'TRMD']);
    await capture(page, { docFile: DOC_FILE, id: 'trmd', caption: 'Synthèse TRMD', subdir: SUBDIR });

    // --- Paramètres > Comptes & droits > Utilisateurs ---
    await openTreePath(page, ['Paramètres', 'Comptes & droits', 'Utilisateurs']);
    await capture(page, { docFile: DOC_FILE, id: 'accounts-users', caption: 'Comptes & droits — Utilisateurs', subdir: SUBDIR });
  });
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
