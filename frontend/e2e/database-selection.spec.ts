import { test, expect } from '@playwright/test';
import { loginAsDemo } from './helpers';

// Flux de sélection de base (voir architecture.md, multi-base) : c'est exactement le genre de
// parcours (redirections, cookies) qu'aucun test backend/curl ne peut vérifier honnêtement — la
// raison d'être de ce lot. Suppose une instance de dev avec une seule base ("timetable", voir
// instance.yaml) : le scénario "plusieurs bases, sélecteur visible" nécessite un second fichier
// SQLite dans le répertoire configuré, non couvert ici pour ne pas dépendre d'un état local
// éphémère — vérifié manuellement lors de l'implémentation (voir specs/).

test.beforeEach(async ({ context }) => {
  await context.clearCookies();
});

test('sans cookie, redirige et sélectionne automatiquement l\'unique base disponible', async ({ page }) => {
  await page.goto('/');

  // Base unique -> sélection automatique, l'utilisateur ne voit jamais le sélecteur. Sans session
  // instance, l'étape suivante est /login (voir e2e/auth.spec.ts pour la suite du parcours).
  await expect(page).not.toHaveURL(/\/select-database/);
  await expect(page).toHaveURL(/\/login/);

  const cookies = await page.context().cookies();
  const dbCookie = cookies.find(c => c.name === 'klepsydrix_db');
  expect(dbCookie?.value).toBe('timetable');
});

test('la page de sélection liste les bases disponibles via l\'API publique', async ({ page }) => {
  await page.goto('/select-database');
  // Redirection automatique attendue (une seule base) — donc vers /login, cookie de base déjà posé.
  await expect(page).not.toHaveURL(/\/select-database/);
  const cookies = await page.context().cookies();
  expect(cookies.find(c => c.name === 'klepsydrix_db')?.value).toBe('timetable');
});

test('changer de base depuis la barre latérale ramène au sélecteur puis à l\'application', async ({ page }) => {
  await loginAsDemo(page);
  await page.goto('/');
  await expect(page.locator('.sidebar-footer .label', { hasText: 'timetable' })).toBeVisible();

  await page.getByTitle('Changer de base de données').click();

  // Une seule base disponible : round-trip automatique. La session instance est toujours valide
  // (loginAsDemo a posé le cookie de session), donc retour direct dans l'application authentifiée.
  await expect(page).not.toHaveURL(/\/select-database/);
  await expect(page).not.toHaveURL(/\/login/);
  const cookies = await page.context().cookies();
  expect(cookies.find(c => c.name === 'klepsydrix_db')?.value).toBe('timetable');
});
