<template>
  <div class="login-shell">
    <div class="login-card">
      <BaseLogo size="lg" class="page-logo" />

      <h1>{{ forced ? 'Changement de mot de passe requis' : 'Changer mon mot de passe' }}</h1>
      <p v-if="forced" class="hint">
        Un administrateur a demandé que vous choisissiez un nouveau mot de passe avant de continuer.
      </p>

      <template v-if="!submitted">
        <form class="local-form" @submit.prevent="submit">
          <label>
            Mot de passe actuel
            <input v-model="currentPassword" type="password" autocomplete="current-password" required />
          </label>
          <label>
            Nouveau mot de passe
            <input v-model="newPassword" type="password" autocomplete="new-password" required minlength="8" />
          </label>
          <label>
            Confirmer le nouveau mot de passe
            <input v-model="confirmPassword" type="password" autocomplete="new-password" required minlength="8" />
          </label>
          <p class="hint">
            8 caractères minimum, combinant au moins 3 des 4 catégories suivantes : majuscules,
            minuscules, chiffres, caractères spéciaux.
          </p>
          <div v-if="error" class="state-message error">{{ error }}</div>
          <BaseButton type="submit" :loading="submitting">Valider</BaseButton>
        </form>
        <a v-if="!forced" class="back-link" href="/">← Retour à l'application</a>
      </template>
      <template v-else>
        <p class="hint">Mot de passe mis à jour.</p>
        <a class="back-link" :href="next">{{ forced ? "Accéder à l'application →" : "Retour à l'application →" }}</a>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import BaseButton from '../components/BaseButton.vue';
import BaseLogo from '../components/BaseLogo.vue';
import { apiFetch } from '../services/api';

const forced = ref(false);
const next = ref('/');
const currentPassword = ref('');
const newPassword = ref('');
const confirmPassword = ref('');
const submitting = ref(false);
const submitted = ref(false);
const error = ref('');

async function submit() {
  error.value = '';
  if (newPassword.value !== confirmPassword.value) {
    error.value = 'Les deux mots de passe ne correspondent pas.';
    return;
  }
  submitting.value = true;
  try {
    // apiFetch (pas un fetch() brut, contrairement aux autres pages /login*/password-reset/*) :
    // cette route est la SEULE de /api/auth/* qui exige une session applicative déjà ouverte (voir
    // auth_endpoints.py::password_change, Depends(current_db_user)) — elle a donc besoin de
    // l'en-tête X-Klepsydrix-Database qu'apiFetch attache automatiquement depuis le cookie de base.
    const response = await apiFetch('/api/auth/password/change', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_password: currentPassword.value, new_password: newPassword.value }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(typeof data.detail === 'string' ? data.detail : 'Impossible de changer le mot de passe.');
    }
    submitted.value = true;
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur inconnue.';
  } finally {
    submitting.value = false;
  }
}

onMounted(() => {
  const params = new URLSearchParams(window.location.search);
  forced.value = params.get('forced') === '1';
  next.value = params.get('next') || '/';
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
  margin: 0 0 var(--spacing-sm) 0;
}

.hint {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin: 0 0 var(--spacing-md) 0;
}

.state-message.error {
  color: var(--accent-danger);
  font-size: 0.9rem;
}

.local-form {
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

.back-link {
  display: block;
  margin-top: var(--spacing-lg);
  font-size: 0.9rem;
  color: var(--accent-primary);
  text-decoration: none;
}
.back-link:hover {
  text-decoration: underline;
}
</style>
