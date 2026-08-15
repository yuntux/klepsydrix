<template>
  <div class="login-shell">
    <div class="login-card">
      <BaseLogo size="lg" class="page-logo" />

      <h1>Mot de passe maître — console d'administration</h1>
      <p class="hint">
        Sans rapport avec un compte utilisateur normal — voir architecture.md §19.A.
      </p>

      <form class="local-form" @submit.prevent="submit">
        <label>
          Mot de passe maître
          <input v-model="password" type="password" autocomplete="off" required />
        </label>
        <div v-if="error" class="state-message error">{{ error }}</div>
        <BaseButton type="submit" :loading="submitting">Entrer</BaseButton>
      </form>

      <a class="back-link" href="/login">← Retour à la connexion normale</a>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import BaseButton from '../components/BaseButton.vue';
import BaseLogo from '../components/BaseLogo.vue';

const password = ref('');
const error = ref('');
const submitting = ref(false);

function nextUrl(): string {
  return new URLSearchParams(window.location.search).get('next') || '/admin';
}

async function submit() {
  submitting.value = true;
  error.value = '';
  try {
    const response = await fetch('/api/auth/login/master', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: password.value }),
    });
    if (!response.ok) {
      const message = response.status === 404
        ? "L'authentification par mot de passe maître n'est pas activée sur cette instance."
        : response.status === 403
          ? 'Accès refusé (adresse non autorisée ou trop de tentatives).'
          : 'Mot de passe incorrect.';
      throw new Error(message);
    }
    window.location.href = nextUrl();
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur inconnue.';
  } finally {
    submitting.value = false;
  }
}
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
  font-size: 0.8rem;
  color: var(--text-muted);
  margin: 0 0 var(--spacing-lg) 0;
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
  font-size: 0.8rem;
  color: var(--text-muted);
  text-decoration: none;
}
.back-link:hover {
  color: var(--accent-primary);
}
</style>
