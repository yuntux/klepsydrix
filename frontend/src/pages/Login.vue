<template>
  <div class="login-shell">
    <div class="login-card">
      <BaseLogo size="lg" class="page-logo" />

      <h1>Connexion</h1>

      <div v-if="inactiveReason" class="state-message error">Ce compte a été désactivé.</div>
      <div v-if="loading" class="state-message">Chargement des fournisseurs d'identité…</div>
      <div v-else-if="loadError" class="state-message error">{{ loadError }}</div>
      <div v-else-if="providers.length === 0" class="state-message error">
        Aucun fournisseur d'identité n'est actif sur cette instance.
      </div>
      <template v-else>
        <ul class="provider-list">
          <li v-for="p in providers" :key="p.key">
            <button
              v-if="p.protocol !== 'local_password'"
              class="provider-item"
              @click="loginOidc(p.key)"
            >
              <img v-if="p.logo" :src="p.logo" class="provider-logo" :alt="p.label" />
              <span class="provider-name">{{ p.label }}</span>
              <svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>
            </button>
            <button
              v-else
              class="provider-item"
              :class="{ active: showLocalForm }"
              @click="showLocalForm = !showLocalForm"
            >
              <span class="provider-name">{{ p.label }}</span>
              <svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>
            </button>
          </li>
        </ul>

        <form v-if="showLocalForm" class="local-form" @submit.prevent="loginLocal">
          <label>
            Base de données
            <input v-model="dbSlug" type="text" placeholder="ex: timetable" required />
          </label>
          <label>
            Identifiant
            <input v-model="identifier" type="text" autocomplete="username" required />
          </label>
          <label>
            Mot de passe
            <input v-model="password" type="password" autocomplete="current-password" required />
          </label>
          <div v-if="localError" class="state-message error">{{ localError }}</div>
          <BaseButton type="submit" :loading="submitting">Se connecter</BaseButton>
          <a class="forgot-link" :href="`/password-reset/request${dbSlug ? `?db=${encodeURIComponent(dbSlug)}` : ''}`">Mot de passe oublié ?</a>
        </form>
      </template>

      <a class="master-link" href="/login/master">Mot de passe maître (administrateur d'instance)</a>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import BaseButton from '../components/BaseButton.vue';
import BaseLogo from '../components/BaseLogo.vue';

interface Provider {
  key: string;
  label: string;
  logo: string | null;
  protocol: string;
}

const providers = ref<Provider[]>([]);
const loading = ref(true);
const loadError = ref('');
const showLocalForm = ref(false);
const dbSlug = ref('');
const identifier = ref('');
const password = ref('');
const localError = ref('');
const submitting = ref(false);
const inactiveReason = ref(false);

function nextUrl(): string {
  return new URLSearchParams(window.location.search).get('next') || '/';
}

function loginOidc(providerKey: string) {
  const next = encodeURIComponent(nextUrl());
  window.location.href = `/api/auth/oidc/login/${providerKey}?next=${next}`;
}

async function loginLocal() {
  submitting.value = true;
  localError.value = '';
  try {
    const response = await fetch('/api/auth/login/local', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Klepsydrix-Database': dbSlug.value,
      },
      body: JSON.stringify({ identifier: identifier.value, password: password.value }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(typeof data.detail === 'string' ? data.detail : 'Connexion impossible.');
    }
    window.location.href = nextUrl();
  } catch (e) {
    localError.value = e instanceof Error ? e.message : 'Erreur inconnue.';
  } finally {
    submitting.value = false;
  }
}

onMounted(async () => {
  const params = new URLSearchParams(window.location.search);
  const dbParam = params.get('db');
  if (dbParam) dbSlug.value = dbParam;
  inactiveReason.value = params.get('reason') === 'inactive';

  try {
    const response = await fetch('/api/auth/providers');
    if (!response.ok) throw new Error('Erreur lors de la récupération des fournisseurs d\'identité.');
    providers.value = await response.json();

    // Un seul fournisseur fédéré (OIDC) actif : redirection directe, l'utilisateur ne voit jamais
    // cette page. Le provider local, lui, a toujours besoin d'un formulaire (base + identifiant +
    // mot de passe) — jamais de redirection automatique pour lui.
    if (providers.value.length === 1 && providers.value[0].protocol !== 'local_password') {
      loginOidc(providers.value[0].key);
      return;
    }
    if (providers.value.length === 1 && providers.value[0].protocol === 'local_password') {
      showLocalForm.value = true;
    }
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : 'Erreur inconnue.';
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.login-shell {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-secondary);
  font-family: var(--font-sans);
}

.login-card {
  width: 420px;
  max-width: calc(100vw - 2 * var(--spacing-xl));
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  padding: var(--spacing-xl);
}

.page-logo {
  margin-bottom: var(--spacing-lg);
}

h1 {
  font-size: 1rem;
  font-weight: 500;
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-lg) 0;
}

.state-message {
  color: var(--text-muted);
  font-size: 0.9rem;
}
.state-message.error {
  color: var(--accent-danger);
}

.provider-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.provider-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  color: var(--text-primary);
  font-family: inherit;
  font-size: 0.95rem;
  cursor: pointer;
  transition: border-color var(--transition-fast), background var(--transition-fast);
}
.provider-item:hover,
.provider-item.active {
  border-color: var(--accent-primary);
  background: var(--bg-card);
}
.provider-item svg {
  width: 18px;
  height: 18px;
  color: var(--text-muted);
  margin-left: auto;
}
.provider-logo {
  width: 20px;
  height: 20px;
  object-fit: contain;
}
.provider-name {
  font-weight: 500;
}

.local-form {
  margin-top: var(--spacing-lg);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}
.local-form label {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  font-size: 0.85rem;
  color: var(--text-secondary);
}
.local-form input {
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: inherit;
  font-size: 0.95rem;
}
.local-form input:focus {
  outline: none;
  border-color: var(--accent-primary);
}

.master-link {
  display: block;
  margin-top: var(--spacing-lg);
  font-size: 0.75rem;
  color: var(--text-muted);
  text-decoration: none;
  text-align: center;
}
.master-link:hover {
  color: var(--accent-primary);
}

.forgot-link {
  align-self: center;
  font-size: 0.8rem;
  color: var(--text-muted);
  text-decoration: none;
}
.forgot-link:hover {
  color: var(--accent-primary);
}
</style>
