import { test, expect } from '@playwright/test';
import { loginAsMaster } from './helpers';

// Console d'administration d'instance (voir architecture.md §19) : authentifié via le mot de passe
// maître de dev (instance.yaml::master_db_local_auth), SEULE voie vers le statut super-admin en
// local — provider_key "local" est refusé dans super_admins (voir config.py::SuperAdminPair : un
// admin de base pourrait sinon se créer un compte local avec le même subject et usurper le statut
// super-admin sur toute l'instance) et aucun fournisseur OIDC fédéré n'est disponible sans
// dépendance externe. Cycle complet sur une base JETABLE créée puis détruite par le test lui-même :
// ne touche jamais "timetable" (la base de dev réelle).
//
// Un seul scénario séquentiel plutôt que plusieurs tests indépendants : créer/dupliquer/sauvegarder/
// supprimer une base sont des étapes qui dépendent toutes de la même ressource jetable, pas des
// parcours isolables — voir workers: 1 (playwright.config.ts), même logique que le partage du seul
// serveur de dev.
//
// Locators : jamais getByLabel() sur les champs de AdminConsole.vue/BaseInput.vue — le <label> y
// est un frère du <input>, pas un parent ni lié par for/id (pas d'association ARIA), donc getByLabel
// ne les trouverait pas. Boutons de formulaire dans une modale : toujours scopés à `.modal-container`
// plutôt que par texte seul — la ligne du tableau ET la modale ouverte au-dessus partagent souvent
// le même libellé ("Dupliquer", "Supprimer"), une recherche par texte non scopée serait ambiguë.

const SLUG = 'e2e_admin_test';
const DUP_SLUG = 'e2e_admin_test_dup';

// Filet de sécurité : si un run précédent a été interrompu avant son propre nettoyage, on repart
// d'un état propre plutôt que d'échouer sur un "cette base existe déjà" sans rapport avec ce qui
// est réellement testé ici.
async function deleteIfExists(page: import('@playwright/test').Page, slug: string) {
  await page.request.delete(`/api/instance/admin/databases/${slug}`, {
    params: { confirm: slug },
  }).catch(() => {});
}

test.beforeEach(async ({ page }) => {
  await page.context().clearCookies();
  await loginAsMaster(page);
  await deleteIfExists(page, DUP_SLUG);
  await deleteIfExists(page, SLUG);
});

test.afterEach(async ({ page }) => {
  await deleteIfExists(page, DUP_SLUG);
  await deleteIfExists(page, SLUG);
});

test('cycle complet : créer, sauvegarder, dupliquer, puis supprimer une base (avec garde de confirmation)', async ({ page }) => {
  // Créer une base recrée tout le schéma (Base.metadata.drop_all()+create_all(), voir init_db.py::
  // init_prod_data) — mesuré à ~3s en local, contre <200ms pour les autres opérations (dupliquer,
  // supprimer). Délai de test et timeout d'assertion élargis en conséquence, seulement autour de
  // cette étape, pour ne pas masquer une VRAIE régression de lenteur sur les autres actions.
  test.setTimeout(60000);

  await page.goto('/admin');
  await expect(page.getByText('Super-administrateur')).toBeVisible();

  // --- Créer ---
  await page.getByRole('button', { name: 'Créer une base', exact: true }).click();
  const createModal = page.locator('.modal-container');
  await createModal.getByPlaceholder('ex: college-jean-jaures').fill(SLUG, { timeout: 10000 });
  await createModal.getByPlaceholder('ex: proviseur@ac-exemple.fr').fill('nouvel.admin@example.fr');
  await createModal.locator('button[type="submit"]').click();

  const createdRow = page.locator('tr', { has: page.locator('.db-name', { hasText: SLUG }) });
  await expect(createdRow).toBeVisible({ timeout: 10000 });
  await expect(page.getByText('Base créée avec succès.')).toBeVisible();

  // --- Sauvegarder (téléchargement via navigation navigateur standard, voir instance_endpoints.py) ---
  const downloadPromise = page.waitForEvent('download');
  await createdRow.getByRole('button', { name: 'Sauvegarder' }).click();
  const download = await downloadPromise;
  // Extension dépendante du backend (.db pour SQLite, .dump pour PostgreSQL — voir
  // db_admin_ops.py::backup_database) : on vérifie le nom SANS l'extension, pas le fichier exact.
  expect(download.suggestedFilename()).toMatch(new RegExp(`^${SLUG}\\.`));

  // --- Dupliquer ---
  await createdRow.getByRole('button', { name: 'Dupliquer' }).click();
  const duplicateModal = page.locator('.modal-container');
  await duplicateModal.getByPlaceholder('ex: college-jean-jaures-test').fill(DUP_SLUG);
  await duplicateModal.locator('button[type="submit"]').click();

  const dupRow = page.locator('tr', { has: page.locator('.db-name', { hasText: DUP_SLUG }) });
  await expect(dupRow).toBeVisible();
  await expect(page.getByText(`Base « ${SLUG} » dupliquée avec succès.`)).toBeVisible();

  // --- Supprimer la copie : garde de confirmation (ressaisie exacte du nom, voir AdminConsole.vue) ---
  await dupRow.getByRole('button', { name: 'Supprimer' }).click();
  const deleteDupModal = page.locator('.modal-container');
  const dupConfirmInput = deleteDupModal.getByPlaceholder(DUP_SLUG, { exact: true });
  await dupConfirmInput.fill('mauvaise-confirmation');
  const dupDeleteSubmit = deleteDupModal.locator('button[type="submit"]');
  await expect(dupDeleteSubmit).toBeDisabled();

  await dupConfirmInput.fill(DUP_SLUG);
  await expect(dupDeleteSubmit).toBeEnabled();
  await dupDeleteSubmit.click();

  await expect(dupRow).not.toBeVisible();
  await expect(page.getByText(`Base « ${DUP_SLUG} » supprimée.`)).toBeVisible();

  // --- Supprimer la base d'origine ---
  await createdRow.getByRole('button', { name: 'Supprimer' }).click();
  const deleteOriginalModal = page.locator('.modal-container');
  await deleteOriginalModal.getByPlaceholder(SLUG, { exact: true }).fill(SLUG);
  await deleteOriginalModal.locator('button[type="submit"]').click();
  await expect(createdRow).not.toBeVisible();
});

test("un admin de base (non super-admin) ne voit pas les actions réservées au super-admin", async ({ page }) => {
  // L'identité réelle derrière la session n'a pas d'importance ici (même le mot de passe maître,
  // qui EST super-admin en réalité — voir instance_admin.py::is_super_admin) : la réponse de la
  // liste est interceptée et remplacée par un is_super_admin=false simulé, aucun second compte de
  // test "admin de base non-super" à créer/maintenir juste pour ce cas. Interception réseau
  // (persiste à travers la navigation, contrairement à une réécriture de window.fetch via
  // page.evaluate) : seule la réponse de LISTE est remplacée, le reste (assets, autres appels) suit
  // son chemin normal. Le comportement serveur réel pour un vrai admin de base non-super est couvert
  // côté backend (backend/tests/test_instance_admin.py::TestDbAdmin) — ici on vérifie seulement que
  // l'IHM masque bien les actions réservées quand is_super_admin est faux.
  await page.route('**/api/instance/admin/databases', async (route) => {
    if (route.request().method() !== 'GET') return route.continue();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ databases: ['timetable'], is_super_admin: false }),
    });
  });
  await page.goto('/admin');

  await expect(page.getByText('Administrateur de vos bases uniquement')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Créer une base', exact: true })).not.toBeVisible();
  const timetableRow = page.locator('tr', { has: page.locator('.db-name', { hasText: 'timetable' }) });
  await expect(timetableRow.getByRole('button', { name: 'Dupliquer' })).not.toBeVisible();
  // Toujours autorisé pour un admin de SA base : sauvegarder/restaurer/supprimer.
  await expect(timetableRow.getByRole('button', { name: 'Sauvegarder' })).toBeVisible();
});
