import { test, expect } from '@playwright/test';
import { loginAsDemo, DEMO_DB, DEMO_IDENTIFIER, DEMO_PASSWORD } from './helpers';

// Authentification (provider local — voir architecture.md, "Architecture Multi-Base et Routage
// HTTP") : le seul flux testable ici sans dépendance externe (pas de vrai fournisseur OIDC en
// local). Couvre le formulaire réel (pas juste l'appel API direct, voir helpers.ts::loginAsDemo)
// pour au moins un scénario, exactement le genre de parcours qu'aucun test backend ne peut
// honnêtement vérifier (redirections, pré-remplissage depuis l'URL, cookies posés par le serveur).

test.beforeEach(async ({ context }) => {
  await context.clearCookies();
});

test('le formulaire de connexion locale authentifie et redirige vers la page demandée', async ({ page }) => {
  // Simule l'arrivée sur /login via une redirection depuis apiFetch() (base déjà connue, page
  // d'origine à retrouver après connexion) plutôt que de dérouler tout /select-database ici — déjà
  // couvert par database-selection.spec.ts, pas la peine de le repasser dans ce test.
  await page.goto(`/login?next=%2F&db=${DEMO_DB}`);

  // Plusieurs fournisseurs actifs (local + EduConnect, voir instance.yaml) : le formulaire local
  // n'est plus affiché automatiquement (ça ne vaut que pour un provider local UNIQUE) — il faut
  // d'abord cliquer sur "Compte local" pour le déplier, comme un vrai utilisateur le ferait.
  await page.getByRole('button', { name: 'Compte local' }).click();

  await expect(page.locator('.local-form')).toBeVisible();
  await expect(page.locator('.local-form input[type="text"]').first()).toHaveValue(DEMO_DB);

  await page.locator('.local-form input[autocomplete="username"]').fill(DEMO_IDENTIFIER);
  await page.locator('.local-form input[type="password"]').fill(DEMO_PASSWORD);
  await page.locator('.local-form button[type="submit"]').click();

  await expect(page).toHaveURL('http://localhost:3000/');
  await expect(page.locator('.sidebar-footer .label', { hasText: 'timetable' })).toBeVisible();

  const cookies = await page.context().cookies();
  expect(cookies.find(c => c.name === 'klepsydrix_session')).toBeTruthy();
});

test('mot de passe incorrect affiche une erreur sans authentifier', async ({ page }) => {
  await page.goto(`/login?db=${DEMO_DB}`);
  await page.getByRole('button', { name: 'Compte local' }).click();
  await page.locator('.local-form input[autocomplete="username"]').fill(DEMO_IDENTIFIER);
  await page.locator('.local-form input[type="password"]').fill('wrong-password');
  await page.locator('.local-form button[type="submit"]').click();

  await expect(page.locator('.local-form .state-message.error')).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
  const cookies = await page.context().cookies();
  expect(cookies.find(c => c.name === 'klepsydrix_session')).toBeFalsy();
});

test('se déconnecter efface la session et ramène au formulaire de connexion', async ({ page }) => {
  await loginAsDemo(page);
  await page.goto('/');
  await expect(page.locator('.sidebar-footer .label', { hasText: 'timetable' })).toBeVisible();

  await page.locator('.sidebar-footer .label', { hasText: 'Se déconnecter' }).click();

  await expect(page).toHaveURL(/\/login/);
  const cookies = await page.context().cookies();
  expect(cookies.find(c => c.name === 'klepsydrix_session')).toBeFalsy();
});
