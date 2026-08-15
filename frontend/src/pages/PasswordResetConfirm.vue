<template>
  <div class="login-shell">
    <div class="login-card">
      <BaseLogo size="lg" class="page-logo" />

      <h1>Nouveau mot de passe</h1>

      <div v-if="!token || !dbSlug" class="state-message error">
        Lien invalide — il manque le jeton ou la base.
      </div>
      <template v-else-if="!submitted">
        <form class="local-form" @submit.prevent="submit">
          <label>
            Nouveau mot de passe
            <input v-model="newPassword" type="password" autocomplete="new-password" required minlength="8" />
          </label>
          <label>
            Confirmer le mot de passe
            <input v-model="confirmPassword" type="password" autocomplete="new-password" required minlength="8" />
          </label>
          <div v-if="error" class="state-message error">{{ error }}</div>
          <BaseButton type="submit" :loading="submitting">Valider</BaseButton>
        </form>
      </template>
      <template v-else>
        <p class="hint">Mot de passe mis à jour.</p>
        <a class="back-link" :href="`/login?db=${encodeURIComponent(dbSlug)}`">Se connecter →</a>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import BaseButton from '../components/BaseButton.vue';
import BaseLogo from '../components/BaseLogo.vue';

const token = ref('');
const dbSlug = ref('');
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
    const response = await fetch('/api/auth/password-reset/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Klepsydrix-Database': dbSlug.value },
      body: JSON.stringify({ token: token.value, new_password: newPassword.value }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(typeof data.detail === 'string' ? data.detail : 'Lien invalide ou expiré.');
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
  token.value = params.get('token') || '';
  dbSlug.value = params.get('db') || '';
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

.hint {
  font-size: 0.9rem;
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
