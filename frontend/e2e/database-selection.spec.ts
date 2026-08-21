import { test, expect } from '@playwright/test';
import { loginAsDemo } from './helpers';

// Flux de sélection de base (voir architecture.md, multi-base) : c'est exactement le genre de
// parcours (redirections, cookies) qu'aucun test backend/curl ne peut vérifier honnêtement — la
// raison d'être de ce lot. Suppose une instance de dev avec une seule base ("timetable", voir
// instance.yaml) : le scénario "plusieurs bases, sélecteur visible" nécessite un second fichier
// SQLite dans le répertoire configuré, non couvert ici pour ne pas dépendre d'un état local
// éphémère — vérifié manuellement lors de l'implémentation (voir specs/).
//
// ⚠️ Ces parcours ont changé avec la suppression de la route publique qui listait toutes les bases
// de l'instance (voir instance_endpoints.py, instance_admin.py::databases_for_identity) : SANS
// session, aucune liste n'est servie, donc plus de sélection automatique avant connexion — c'est le
// formulaire de connexion qui porte le champ « base », saisi par l'utilisateur (§17.F).

test.beforeEach(async ({ context }) => {
  await context.clearCookies();
});

test('sans session, l\'arrivée sur l\'application mène au formulaire de connexion', async ({ page }) => {
  await page.goto('/');

  // /select-database interroge /api/instance/my-databases, obtient 401, et renvoie vers /login.
  await expect(page).toHaveURL(/\/login/);
  await expect(page).not.toHaveURL(/\/select-database/);

  // Aucune base n'a pu être devinée : le cookie ne sera posé qu'à la connexion, à partir du champ
  // « base » du formulaire (voir auth_endpoints.py::login_local).
  const cookies = await page.context().cookies();
  expect(cookies.find(c => c.name === 'klepsydrix_db')).toBeUndefined();
});

test('le sélecteur ne divulgue aucune base à un visiteur anonyme', async ({ page }) => {
  const response = await page.request.get('/api/instance/my-databases');

  expect(response.status()).toBe(401);
  expect(await response.text()).not.toContain('timetable');
});

test('une fois connecté, le sélecteur ne propose que la base de l\'utilisateur', async ({ page }) => {
  await loginAsDemo(page);

  const response = await page.request.get('/api/instance/my-databases');

  expect(response.ok()).toBeTruthy();
  expect((await response.json()).databases).toEqual(['timetable']);
});

test('changer de base depuis la barre latérale ramène au sélecteur puis à l\'application', async ({ page }) => {
  await loginAsDemo(page);
  await page.goto('/');
  await expect(page.locator('.sidebar-footer .label', { hasText: 'timetable' })).toBeVisible();

  await page.getByTitle('Changer de base de données').click();

  // Une seule base disponible pour cette identité : round-trip automatique. La session instance est
  // toujours valide (loginAsDemo a posé le cookie), donc retour direct dans l'application.
  await expect(page).not.toHaveURL(/\/select-database/);
  await expect(page).not.toHaveURL(/\/login/);
  const cookies = await page.context().cookies();
  expect(cookies.find(c => c.name === 'klepsydrix_db')?.value).toBe('timetable');
});
