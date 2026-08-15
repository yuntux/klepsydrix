import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

// Tests unitaires/composants rapides (voir architecture.md, lot 6 "Tests end-to-end frontend") —
// distinct de playwright.config.ts (parcours navigateur réels contre les serveurs de dev). Aucun
// serveur nécessaire ici : environnement DOM simulé (happy-dom), exécuté en isolation.
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'happy-dom',
    include: ['src/**/*.test.ts'],
  },
})
