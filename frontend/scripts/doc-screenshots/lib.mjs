// Utilitaires partagés par les scripts de capture d'écran de la documentation utilisateur
// (user_doc/*.md). Ce ne sont pas des tests (voir frontend/e2e/ pour la suite e2e) : de simples
// scripts ponctuels, lancés à la main contre les serveurs de dev déjà démarrés par
// ../../start_services.sh (mêmes conventions que playwright.config.ts : pas de webServer ici).
import { chromium } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export const REPO_ROOT = path.resolve(__dirname, '../../..');
export const USER_DOC_DIR = path.join(REPO_ROOT, 'user_doc');
export const BASE_URL = process.env.KLEPSYDRIX_BASE_URL || 'http://localhost:3000';

// Compte de démonstration seedé par backend/app/core/init_demo.py — voir frontend/e2e/helpers.ts,
// mêmes identifiants (aucune raison de diverger, c'est le seul jeu de données stable disponible
// en local pour illustrer la documentation).
export const DEMO_DB = 'timetable';
export const DEMO_IDENTIFIER = 'demo@klepsydrix.fr';
export const DEMO_PASSWORD = 'Demo1234!';

// Mot de passe maître de dev (instance.yaml::master_db_local_auth) — voir frontend/e2e/helpers.ts.
export const MASTER_PASSWORD = 'e2e-master-test-password';

export async function loginAsDemo(page, db = DEMO_DB) {
  const response = await page.request.post(`${BASE_URL}/api/auth/login/local`, {
    headers: { 'X-Klepsydrix-Database': db },
    data: { identifier: DEMO_IDENTIFIER, password: DEMO_PASSWORD },
  });
  if (!response.ok()) {
    throw new Error(`Échec de connexion de démonstration : ${response.status()} ${await response.text()}`);
  }
}

export async function loginAsMaster(page) {
  const response = await page.request.post(`${BASE_URL}/api/auth/login/master`, {
    data: { password: MASTER_PASSWORD },
  });
  if (!response.ok()) {
    throw new Error(`Échec de connexion maître : ${response.status()} ${await response.text()}`);
  }
}

export async function withBrowser(fn) {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  try {
    await fn(page);
  } finally {
    await browser.close();
  }
}

// Ouvre un chemin dans l'arborescence de gauche (NotebooksTree.vue) par les libellés affichés,
// ex. openTreePath(page, ['Emploi du temps', 'Classes', 'Liste']). Reproduit la structure du
// composant (groupe l1 > sous-groupe l2 replié/à enfants > feuille l3, ou l2 directement feuille)
// plutôt que de dépendre d'ids CSS non exposés dans le DOM.
export async function openTreePath(page, titles) {
  const [l1Title, l2Title, l3Title] = titles;

  const l1Header = page.locator('.nav-group-header', { hasText: l1Title }).first();
  await l1Header.waitFor({ state: 'visible' });
  const l1Open = (await l1Header.getAttribute('class')) || '';
  if (!l1Open.includes('open')) {
    await l1Header.click();
  }
  if (!l2Title) return;

  const l1Submenu = l1Header.locator('xpath=following-sibling::*[1]');
  const l2Header = l1Submenu.locator('.submenu-item', { hasText: l2Title }).first();
  await l2Header.waitFor({ state: 'visible' });

  const l2Class = (await l2Header.getAttribute('class')) || '';
  if (l2Class.includes('has-children')) {
    if (!l2Class.includes('open')) {
      await l2Header.click();
    }
    if (!l3Title) return;
    const l2Submenu = l2Header.locator('xpath=following-sibling::*[1]');
    const l3Item = l2Submenu.locator('.sub-submenu-item', { hasText: l3Title }).first();
    await l3Item.click();
  } else {
    await l2Header.click();
  }
}

function escapeRegExp(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Capture une copie d'écran de `page` (pleine page par défaut, ou d'un `locator` si fourni) et
// l'injecte dans le markdown `docFile` à l'emplacement du marqueur `<!-- SCREENSHOT: id -->`.
// Idempotent : un ré-appel remplace la ligne d'image précédente plutôt que d'en empiler une
// nouvelle, donc rejouer un script après une évolution de l'IHM suffit à rafraîchir le document.
export async function capture(page, { docFile, id, caption, subdir, locator, waitMs = 300 }) {
  await page.waitForTimeout(waitMs);

  const dir = path.join(USER_DOC_DIR, 'screenshots', subdir);
  fs.mkdirSync(dir, { recursive: true });
  const absPath = path.join(dir, `${id}.png`);
  const target = locator ? page.locator(locator) : page;
  await target.screenshot({ path: absPath });

  const relPath = `screenshots/${subdir}/${id}.png`;
  const marker = `<!-- SCREENSHOT: ${id} -->`;
  const content = fs.readFileSync(docFile, 'utf8');
  if (!content.includes(marker)) {
    console.warn(`⚠️  Marqueur absent de ${path.relative(REPO_ROOT, docFile)} : ${marker} (image écrite sur disque, mais pas injectée)`);
    return;
  }
  const markerRegex = new RegExp(`(${escapeRegExp(marker)})\\n(!\\[[^\\n]*\\]\\([^\\n)]*\\)\\n)?`);
  const updated = content.replace(markerRegex, `$1\n![${caption}](${relPath})\n`);
  fs.writeFileSync(docFile, updated);
  console.log(`✅ ${id} → ${path.relative(REPO_ROOT, absPath)}`);
}
