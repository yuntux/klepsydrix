import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        // `changeOrigin: false` (défaut de http-proxy, rendu explicite ici) : l'en-tête `Host`
        // reçu par le navigateur est transmis TEL QUEL au backend, au lieu d'être réécrit en
        // `localhost:8000`.
        //
        // Ce n'est pas un détail de confort. Deux mécanismes du backend lisent cet en-tête :
        // - `core/csrf.py` autorise l'origine de l'application elle-même, reconstruite depuis
        //   `Host` — avec la réécriture, toute écriture depuis une autre adresse que localhost
        //   (accès à la VM depuis la machine hôte, poste d'un collègue sur le réseau) partait en
        //   403 CROSS_ORIGIN_REFUSED, les lectures passant : symptôme déroutant s'il en est ;
        // - `auth_endpoints.py::oidc_login` construit le `redirect_uri` avec `request.url_for()`,
        //   donc depuis ce même `Host` : réécrit, il renvoyait le fournisseur d'identité vers
        //   `localhost:8000`, injoignable pour tout navigateur qui n'est pas sur la machine.
        //
        // Sans effet en production, où ce proxy n'existe pas (`vite build` ne produit que des
        // fichiers statiques, le relais de `/api` étant assuré par le reverse proxy — voir
        // architecture.md §20.C) : ce réglage aligne simplement le développement sur le
        // comportement d'un proxy correctement configuré, qui préserve `Host`.
        changeOrigin: false,
      }
    }
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor': ['vue', 'vue3-swatches']
        }
      }
    }
  }
})
