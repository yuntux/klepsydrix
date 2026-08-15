import { defineConfig, devices } from '@playwright/test';

// Suite end-to-end (voir architecture.md, lot 6 "Tests end-to-end frontend") — pas de CI pour ce
// chantier (voir architecture.md §16.B) : lancée manuellement en local, contre les serveurs déjà
// démarrés par start_services.sh (backend :8000, frontend :3000). N'essaie donc PAS de démarrer
// ses propres serveurs (pas de `webServer:` ici) : les flux testés (cookies, redirections
// multi-base) doivent s'exercer contre l'instance réelle telle qu'un développeur la fait tourner.
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  // Un seul serveur de dev partagé (pas d'instance isolée par worker) : plusieurs workers en
  // parallèle sollicitent la même instance et le même compte de démonstration en même temps,
  // source de flakiness observée (timeouts intermittents) sans rapport avec le code testé.
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
