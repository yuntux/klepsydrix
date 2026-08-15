import { Page } from '@playwright/test';

// Identifiants du compte de démonstration seedé par backend/app/core/init_demo.py (voir
// architecture.md, provider "local") — le seul provider testable sans dépendance externe en local.
export const DEMO_DB = 'timetable';
export const DEMO_IDENTIFIER = 'demo@klepsydrix.fr';
export const DEMO_PASSWORD = 'demo1234';

// Authentifie directement via l'API (pas le formulaire /login) — plus rapide pour les tests qui ne
// portent pas spécifiquement sur le flux de connexion lui-même. `page.request` partage le même
// jar de cookies que `page`, donc les cookies posés par cet appel sont ensuite envoyés par le
// navigateur comme n'importe quelle navigation ultérieure.
export async function loginAsDemo(page: Page, db: string = DEMO_DB) {
  const response = await page.request.post('/api/auth/login/local', {
    headers: { 'X-Klepsydrix-Database': db },
    data: { identifier: DEMO_IDENTIFIER, password: DEMO_PASSWORD },
  });
  if (!response.ok()) {
    throw new Error(`Échec de connexion de démonstration : ${response.status()} ${await response.text()}`);
  }
}

// Mot de passe maître de dev (voir instance.yaml, jamais un vrai secret de prod) — SEULE voie vers
// la console super-admin en local : provider_key "local" est refusé dans super_admins (voir
// config.py::SuperAdminPair, usurpable par n'importe quel admin de base) et aucun fournisseur OIDC
// fédéré n'est configurable sans dépendance externe. Identité fantôme (__master__, voir
// core/master_auth.py) : n'a accès qu'à `instance_router` (console), jamais aux données applicatives
// d'une base — ne PAS utiliser pour des tests qui portent sur autre chose que la console.
export const MASTER_PASSWORD = 'e2e-master-test-password';

export async function loginAsMaster(page: Page) {
  const response = await page.request.post('/api/auth/login/master', {
    data: { password: MASTER_PASSWORD },
  });
  if (!response.ok()) {
    throw new Error(`Échec de connexion maître : ${response.status()} ${await response.text()}`);
  }
}
