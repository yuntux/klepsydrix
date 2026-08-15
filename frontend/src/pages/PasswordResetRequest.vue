<template>
  <div class="login-shell">
    <div class="login-card">
      <BaseLogo size="lg" class="page-logo" />

      <h1>Mot de passe oublié</h1>

      <template v-if="!submitted">
        <p class="hint">Provider "local" uniquement — voir architecture.md §17.G.</p>
        <form class="local-form" @submit.prevent="submit">
          <label>
            Base de données
            <input v-model="dbSlug" type="text" placeholder="ex: timetable" required />
          </label>
          <label>
            Identifiant
            <input v-model="identifier" type="text" autocomplete="username" required />
          </label>
          <BaseButton type="submit" :loading="submitting">Envoyer le lien</BaseButton>
        </form>
      </template>
      <p v-else class="hint">
        Si un compte local correspond à cet identifiant, un email vient de lui être envoyé avec un
        lien de réinitialisation.
      </p>

      <a class="back-link" href="/login">← Retour à la connexion</a>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import BaseButton from '../components/BaseButton.vue';
import BaseLogo from '../components/BaseLogo.vue';

const dbSlug = ref('');
const identifier = ref('');
const submitting = ref(false);
const submitted = ref(false);

async function submit() {
  submitting.value = true;
  try {
    // Toujours la même issue (voir auth_endpoints.py::password_reset_request, énumération) —
    // aucun état d'erreur distinct à afficher, que l'identifiant existe ou non.
    await fetch('/api/auth/password-reset/request', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Klepsydrix-Database': dbSlug.value },
      body: JSON.stringify({ identifier: identifier.value }),
    });
  } finally {
    submitting.value = false;
    submitted.value = true;
  }
}

onMounted(() => {
  const dbParam = new URLSearchParams(window.location.search).get('db');
  if (dbParam) dbSlug.value = dbParam;
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
  margin: 0 0 var(--spacing-lg) 0;
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
