import { test, expect } from '@playwright/test';
import { loginAsDemo, DEMO_DB, DEMO_IDENTIFIER, DEMO_PASSWORD } from './helpers';

// Gestion des comptes/groupes/droits (voir database.py::current_db_user, models/user.py,
// models/access.py, init_db.py::seed_readonly_access) : changement de mot de passe connecté,
// changement forcé (must_change_password), protection des groupes système (is_system_generated),
// refus de vider le dernier membre du groupe "Admin".
//
// Portée volontairement limitée sur un point : aucun scénario ici ne crée un SECOND utilisateur
// LOCAL avec un mot de passe connu et ne tente de s'y connecter (ex: pour vérifier qu'un compte
// désactivé — User.active=false — est bien rejeté à la connexion). Il n'existe aujourd'hui aucune
// voie API pour poser soi-même le mot de passe initial d'un tiers : seul le flux "mot de passe
// oublié" par email le permet (jeton à usage unique jamais renvoyé par l'API, voir
// auth_endpoints.py::password_reset_request — anti-énumération délibérée), inexploitable depuis un
// test sans boîte mail réelle. Désactiver le compte demo LUI-MÊME pour tester ce rejet est encore
// plus risqué : `active` coupe l'accès à TOUTE requête authentifiée, y compris celle qui
// réactiverait le compte — contrairement à must_change_password (qui laisse volontairement une
// échappatoire, voir /api/auth/password/change), il n'existe aucune voie de récupération si demo se
// désactive lui-même. Le rejet de connexion d'un compte inactif est donc couvert uniquement côté
// backend (voir backend/tests/test_auth_endpoints.py::TestInactiveUserLogin), où une base de test
// isolée permet de le vérifier sans aucun risque pour le compte partagé par le reste de cette suite.
//
// Comme admin-console.spec.ts, plusieurs tests ici mutent TEMPORAIREMENT l'état du compte demo
// partagé (mot de passe, must_change_password) — jamais son appartenance au groupe Admin, jamais son
// `active`. Chaque mutation est restaurée dans un `finally`, garanti même si le test échoue en cours
// de route (workers: 1, voir playwright.config.ts : jamais deux tests de cette suite en vol en même
// temps).

test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }) => {
  await page.context().clearCookies();
});

test('un utilisateur connecté peut changer son mot de passe depuis le formulaire dédié', async ({ page }) => {
  const NEW_PASSWORD = 'PwTest9!Change';
  await loginAsDemo(page);

  try {
    await page.goto('/');
    await page.locator('.sidebar-footer a', { hasText: 'Changer mon mot de passe' }).click();
    await expect(page).toHaveURL(/\/password-change/);

    await page.locator('input[autocomplete="current-password"]').fill(DEMO_PASSWORD);
    const newPasswordInputs = page.locator('input[autocomplete="new-password"]');
    await newPasswordInputs.nth(0).fill(NEW_PASSWORD);
    await newPasswordInputs.nth(1).fill(NEW_PASSWORD);
    await page.locator('button[type="submit"]').click();

    await expect(page.getByText('Mot de passe mis à jour.')).toBeVisible();

    // L'ancien mot de passe ne fonctionne plus, le nouveau si (vérifié directement via l'API,
    // comme loginAsDemo — pas la peine de redérouler le formulaire, déjà couvert par auth.spec.ts).
    const oldAttempt = await page.request.post('/api/auth/login/local', {
      headers: { 'X-Klepsydrix-Database': DEMO_DB },
      data: { identifier: DEMO_IDENTIFIER, password: DEMO_PASSWORD },
    });
    expect(oldAttempt.ok()).toBeFalsy();

    const newAttempt = await page.request.post('/api/auth/login/local', {
      headers: { 'X-Klepsydrix-Database': DEMO_DB },
      data: { identifier: DEMO_IDENTIFIER, password: NEW_PASSWORD },
    });
    expect(newAttempt.ok()).toBeTruthy();
  } finally {
    // Restauration résiliente à l'état exact atteint par le test (a-t-il réussi à changer le mot
    // de passe avant d'échouer ?) : retente avec le nouveau mot de passe (cas nominal), sans effet
    // si le changement n'a en réalité jamais eu lieu (le mot de passe est alors toujours DEMO_PASSWORD).
    const reLogin = await page.request.post('/api/auth/login/local', {
      headers: { 'X-Klepsydrix-Database': DEMO_DB },
      data: { identifier: DEMO_IDENTIFIER, password: NEW_PASSWORD },
    });
    if (reLogin.ok()) {
      await page.request.post('/api/auth/password/change', {
        headers: { 'X-Klepsydrix-Database': DEMO_DB },
        data: { current_password: NEW_PASSWORD, new_password: DEMO_PASSWORD },
      });
    }
  }
});

test('un mot de passe trop faible est refusé avec un message explicite', async ({ page }) => {
  await loginAsDemo(page);
  await page.goto('/');
  await page.locator('.sidebar-footer a', { hasText: 'Changer mon mot de passe' }).click();

  await page.locator('input[autocomplete="current-password"]').fill(DEMO_PASSWORD);
  const newPasswordInputs = page.locator('input[autocomplete="new-password"]');
  await newPasswordInputs.nth(0).fill('faible123');
  await newPasswordInputs.nth(1).fill('faible123');
  await page.locator('button[type="submit"]').click();

  await expect(page.locator('.state-message.error')).toBeVisible();
  // Toujours connecté avec l'ancien mot de passe : la tentative refusée n'a rien modifié.
  const stillWorks = await page.request.post('/api/auth/login/local', {
    headers: { 'X-Klepsydrix-Database': DEMO_DB },
    data: { identifier: DEMO_IDENTIFIER, password: DEMO_PASSWORD },
  });
  expect(stillWorks.ok()).toBeTruthy();
});

test('must_change_password redirige de force et bloque le reste de l\'application jusqu\'au changement', async ({ page }) => {
  await loginAsDemo(page);

  // Pose le flag via l'API générique (droit d'écriture sur user_identity_providers, réservé au
  // groupe Admin — demo en est membre) plutôt que de dérouler le formulaire "Comptes & droits" :
  // seul l'EFFET du flag (redirection + blocage) est sous test ici, pas ce panneau lui-même (voir
  // le test dédié plus bas).
  const idpResponse = await page.request.get(`/api/generic/user_identity_providers?user_id=1&provider_key=local`, {
    headers: { 'X-Klepsydrix-Database': DEMO_DB },
  });
  const idp = (await idpResponse.json()).items[0];

  try {
    await page.request.patch(`/api/generic/user_identity_providers/${idp.id}`, {
      headers: { 'X-Klepsydrix-Database': DEMO_DB },
      data: { must_change_password: true },
    });

    // Une navigation fraîche (nouvelle session applicative) doit rediriger AVANT tout rendu du
    // reste de l'IHM (voir NotebooksTree.vue, défense en profondeur côté client).
    await page.goto('/');
    await expect(page).toHaveURL(/\/password-change/);
    await expect(page.getByText('Un administrateur a demandé')).toBeVisible();

    // Défense en profondeur côté SERVEUR (voir database.py::current_db_user) : même en forçant la
    // navigation directement vers une autre route applicative, l'appel API sous-jacent reste bloqué.
    const blocked = await page.request.get('/api/generic/users', { headers: { 'X-Klepsydrix-Database': DEMO_DB } });
    expect(blocked.status()).toBe(403);

    // Sortie légitime : le formulaire de changement (exempté du blocage) lève l'obligation.
    await page.locator('input[autocomplete="current-password"]').fill(DEMO_PASSWORD);
    const newPasswordInputs = page.locator('input[autocomplete="new-password"]');
    await newPasswordInputs.nth(0).fill('PwUnlock9!');
    await newPasswordInputs.nth(1).fill('PwUnlock9!');
    await page.locator('button[type="submit"]').click();
    await expect(page.getByText('Accéder à l\'application')).toBeVisible();

    const unblocked = await page.request.get('/api/generic/users', { headers: { 'X-Klepsydrix-Database': DEMO_DB } });
    expect(unblocked.status()).toBe(200);
  } finally {
    // Restaure le mot de passe ET le flag, résilient au point d'échec exact du test.
    const reLogin = await page.request.post('/api/auth/login/local', {
      headers: { 'X-Klepsydrix-Database': DEMO_DB },
      data: { identifier: DEMO_IDENTIFIER, password: 'PwUnlock9!' },
    });
    if (reLogin.ok()) {
      await page.request.post('/api/auth/password/change', {
        headers: { 'X-Klepsydrix-Database': DEMO_DB },
        data: { current_password: 'PwUnlock9!', new_password: DEMO_PASSWORD },
      });
    }
    // set_local_password purge déjà must_change_password, mais au cas où le test aurait échoué
    // avant d'atteindre cette étape (flag posé, mot de passe jamais changé) : le repose à false
    // explicitement, avec le mot de passe nominal retrouvé.
    await page.request.post('/api/auth/login/local', {
      headers: { 'X-Klepsydrix-Database': DEMO_DB },
      data: { identifier: DEMO_IDENTIFIER, password: DEMO_PASSWORD },
    }).then(async (r) => {
      if (r.ok()) {
        await page.request.patch(`/api/generic/user_identity_providers/${idp.id}`, {
          headers: { 'X-Klepsydrix-Database': DEMO_DB },
          data: { must_change_password: false },
        });
      }
    });
  }
});

test('le dernier utilisateur du groupe Admin ne peut pas être retiré', async ({ page }) => {
  await loginAsDemo(page);

  const adminGroupResponse = await page.request.get('/api/generic/res_groups?name=Admin', {
    headers: { 'X-Klepsydrix-Database': DEMO_DB },
  });
  const adminGroup = (await adminGroupResponse.json()).items[0];
  expect(adminGroup.user_ids).toEqual([1]); // demo, seul membre au départ de ce test

  // Utilisateur temporaire (aucun mot de passe nécessaire : jamais utilisé pour se connecter,
  // seulement pour peupler/dépeupler le groupe Admin) — nettoyé en fin de test.
  const tempUser = await (await page.request.post('/api/generic/users', {
    headers: { 'X-Klepsydrix-Database': DEMO_DB },
    data: { first_name: 'E2E', last_name: 'TempAdmin', email: null },
  })).json();

  try {
    // 2 membres : retirer l'un d'eux (pas le dernier) doit fonctionner.
    const addRes = await page.request.patch(`/api/generic/res_groups/${adminGroup.id}`, {
      headers: { 'X-Klepsydrix-Database': DEMO_DB },
      data: { user_ids: [1, tempUser.id] },
    });
    expect(addRes.ok()).toBeTruthy();

    // Vider ENTIÈREMENT le groupe (les 2 membres à la fois) doit être refusé.
    const emptyRes = await page.request.patch(`/api/generic/res_groups/${adminGroup.id}`, {
      headers: { 'X-Klepsydrix-Database': DEMO_DB },
      data: { user_ids: [] },
    });
    expect(emptyRes.status()).toBe(400);
    expect((await emptyRes.json()).detail).toContain('dernier utilisateur du groupe Admin');

    // Le groupe n'a pas bougé : toujours les 2 membres (la mise à jour rejetée n'a rien persisté).
    const afterResponse = await page.request.get(`/api/generic/res_groups/${adminGroup.id}`, {
      headers: { 'X-Klepsydrix-Database': DEMO_DB },
    });
    expect((await afterResponse.json()).user_ids.sort()).toEqual([1, tempUser.id].sort());
  } finally {
    // Retire le temporaire du groupe (demo redevient seul membre, état de départ), puis le supprime.
    await page.request.patch(`/api/generic/res_groups/${adminGroup.id}`, {
      headers: { 'X-Klepsydrix-Database': DEMO_DB },
      data: { user_ids: [1] },
    });
    await page.request.delete(`/api/generic/users/${tempUser.id}`, {
      headers: { 'X-Klepsydrix-Database': DEMO_DB },
    });
  }
});

test('le menu "Comptes & droits" est atteignable et le groupe système Consultation est protégé', async ({ page }) => {
  await loginAsDemo(page);
  await page.goto('/');

  // Idempotent : selon l'état déjà persisté du menu (NotebooksTree.vue), la section peut être
  // repliée OU déjà dépliée — ne (dé)clique que si nécessaire. { force: true } : la section
  // "Paramètres" (longue, en-tête sticky) chevauche visuellement son dernier élément pendant le
  // défilement automatique — comportement préexistant du composant, pas propre à cette entrée ;
  // la cible est bien présente/visible, seule la pré-vérification de survol de Playwright échoue.
  // "– " (tiret cadratin) : préfixe des enfants de second niveau, voir "– Liste"/"– Vœux" partout
  // ailleurs dans l'arbre — pas une particularité de cette entrée.
  const utilisateursButton = page.getByRole('button', { name: '– Utilisateurs', exact: true });
  if (!(await utilisateursButton.isVisible().catch(() => false))) {
    await page.getByRole('button', { name: 'Comptes & droits', exact: true }).click({ force: true });
  }
  await expect(utilisateursButton).toBeVisible();
  await expect(page.getByRole('button', { name: '– Groupes de droits', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '– Connexions', exact: true })).toBeVisible();

  // Groupe "Consultation" : lecture seule sur tout, sauf les tables de gestion des comptes/droits
  // (voir init_db.py::seed_readonly_access, SECURITY_SENSITIVE_TABLENAMES) — et protégé contre
  // toute modification de sa propre structure (is_system_generated, voir models/access.py).
  const consultationResponse = await page.request.get('/api/generic/res_groups?name=Consultation', {
    headers: { 'X-Klepsydrix-Database': DEMO_DB },
  });
  const consultation = (await consultationResponse.json()).items[0];
  expect(consultation.is_system_generated).toBe(true);

  const renameAttempt = await page.request.patch(`/api/generic/res_groups/${consultation.id}`, {
    headers: { 'X-Klepsydrix-Database': DEMO_DB },
    data: { name: 'Renommé par erreur' },
  });
  expect(renameAttempt.status()).toBe(400);
  expect((await renameAttempt.json()).detail).toContain('généré par le système');

  const deleteAttempt = await page.request.delete(`/api/generic/res_groups/${consultation.id}`, {
    headers: { 'X-Klepsydrix-Database': DEMO_DB },
  });
  expect(deleteAttempt.status()).toBe(400);

  // N'a pas accès aux tables sensibles (users, res_groups, ir_model_access,
  // user_identity_providers, password_reset_tokens) : aucune ligne ir_model_access pour elles.
  const droitsResponse = await page.request.get(`/api/generic/ir_model_access?group_id=${consultation.id}`, {
    headers: { 'X-Klepsydrix-Database': DEMO_DB },
  });
  const droits = (await droitsResponse.json()).items;
  const sensitiveModels = ['users', 'res_groups', 'ir_model_access', 'user_identity_providers', 'password_reset_tokens'];
  expect(droits.some((d: any) => sensitiveModels.includes(d.model))).toBe(false);
  // En revanche, largement accordée en lecture seule sur le reste (ex: schools).
  expect(droits.some((d: any) => d.model === 'schools' && d.perm_read && !d.perm_write)).toBe(true);
});
