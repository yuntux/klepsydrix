#!/usr/bin/env node
// Capture les copies d'écran illustrant user_doc/superadmin_doc.md. Authentification via le mot
// de passe maître de dev (instance.yaml::master_db_local_auth) — même voie que
// frontend/e2e/admin-console.spec.ts, seule disponible en local sans fournisseur OIDC fédéré.
// Prérequis : backend + frontend démarrés (./start_services.sh start).
//
//   node frontend/scripts/doc-screenshots/capture-superadmin.mjs
//
// Idempotent : peut être rejoué après une évolution de l'IHM pour rafraîchir les images.
import path from 'node:path';
import { withBrowser, capture, loginAsMaster, USER_DOC_DIR, BASE_URL } from './lib.mjs';

const DOC_FILE = path.join(USER_DOC_DIR, 'superadmin_doc.md');
const SUBDIR = 'superadmin';

async function run() {
  await withBrowser(async (page) => {
    // --- Page de connexion maître (non authentifié) ---
    await page.goto(`${BASE_URL}/login/master`);
    await page.waitForSelector('form, input[type="password"]', { timeout: 15000 }).catch(() => {});
    await capture(page, { docFile: DOC_FILE, id: 'master-login', caption: 'Connexion maître (super-admin)', subdir: SUBDIR });

    // --- Console d'administration (authentifié) ---
    await loginAsMaster(page);
    await page.goto(`${BASE_URL}/admin`);
    await page.waitForSelector('text=Super-administrateur', { timeout: 15000 });
    await capture(page, { docFile: DOC_FILE, id: 'admin-console', caption: "Console d'administration — liste des bases", subdir: SUBDIR, waitMs: 500 });

    // --- Modale "Créer une base" ---
    const createButton = page.getByRole('button', { name: 'Créer une base', exact: true });
    if (await createButton.count()) {
      await createButton.click();
      await page.waitForSelector('.modal-container', { timeout: 10000 });
      await capture(page, { docFile: DOC_FILE, id: 'admin-console-create', caption: 'Créer une base', subdir: SUBDIR });
    } else {
      console.warn('⚠️  Bouton "Créer une base" absent (identité non super-admin ?) — capture "admin-console-create" ignorée.');
    }
  });
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
