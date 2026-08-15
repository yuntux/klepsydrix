import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { VueQueryPlugin } from '@tanstack/vue-query'
import { createRouter, createWebHistory, RouterView } from 'vue-router'
import App from './App.vue'
import SelectDatabase from './pages/SelectDatabase.vue'
import Login from './pages/Login.vue'
import MasterLogin from './pages/MasterLogin.vue'
import AdminConsole from './pages/AdminConsole.vue'
import PasswordResetRequest from './pages/PasswordResetRequest.vue'
import PasswordResetConfirm from './pages/PasswordResetConfirm.vue'
import './assets/main.css'

// Routeur limité aux pages "hors application" (sélection de base, authentification, console
// d'administration — voir architecture.md, "Architecture de routage HTTP") : App.vue garde sa
// propre navigation interne (urlState.ts, NotebooksTree.vue), inchangée, montée derrière une route
// générique qui capture tout le reste.
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/select-database', component: SelectDatabase },
    { path: '/login', component: Login },
    { path: '/login/master', component: MasterLogin },
    { path: '/password-reset/request', component: PasswordResetRequest },
    { path: '/password-reset/confirm', component: PasswordResetConfirm },
    { path: '/admin', component: AdminConsole },
    { path: '/:pathMatch(.*)*', component: App },
  ],
})

// RouterView directement comme composant racine (pas de gabarit compilé au runtime, ce build de
// Vue est "runtime-only" — voir vite.config.ts, alias par défaut de @vitejs/plugin-vue).
const app = createApp(RouterView)
app.use(router)
app.use(createPinia())
app.use(VueQueryPlugin, {
  queryClientConfig: {
    defaultOptions: {
      queries: {
        staleTime: 60 * 1000, // 1 minute
        refetchOnWindowFocus: false,
      },
    },
  },
})
app.mount('#app')
