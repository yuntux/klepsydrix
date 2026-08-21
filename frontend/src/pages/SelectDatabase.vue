<template>
  <div class="select-db-shell">
    <div class="select-db-card">
      <BaseLogo size="lg" class="page-logo" />

      <h1>Sélection de la base de données</h1>

      <div v-if="loading" class="state-message">Chargement des bases disponibles…</div>
      <div v-else-if="error" class="state-message error">{{ error }}</div>
      <!-- Liste vide = « aucune base où VOUS ayez un compte », jamais « aucune base sur
           l'instance » : la réponse est filtrée sur l'identité connectée (voir
           instance_admin.py::databases_for_identity), le message ne doit pas laisser croire
           à une instance vide. -->
      <div v-else-if="databases.length === 0" class="state-message error">
        Aucune base de données n'est associée à votre compte sur cette instance.
        Rapprochez-vous de l'administrateur de votre établissement.
      </div>
      <ul v-else class="database-list">
        <li v-for="slug in databases" :key="slug">
          <button class="database-item" @click="select(slug)">
            <span class="database-name">{{ slug }}</span>
            <svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>
          </button>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { setSelectedDatabase } from '../services/dbSession';
import BaseLogo from '../components/BaseLogo.vue';

const databases = ref<string[]>([]);
const loading = ref(true);
const error = ref('');

function nextUrl(): string {
  const params = new URLSearchParams(window.location.search);
  return params.get('next') || '/';
}

function select(slug: string) {
  setSelectedDatabase(slug);
  window.location.href = nextUrl();
}

onMounted(async () => {
  try {
    // Appel direct (pas apiFetch()) : cette page est justement celle où aucune base n'est encore
    // sélectionnée, et /api/instance/my-databases est de portée instance — il n'attend donc aucun
    // en-tête X-Klepsydrix-Database. Il exige en revanche une SESSION, et ne renvoie que les bases
    // où l'identité connectée a réellement un compte (voir instance_admin.py::
    // databases_for_identity) : plus aucune ressource anonyme ne divulgue la liste des
    // établissements hébergés.
    const response = await fetch('/api/instance/my-databases');
    if (response.status === 401) {
      // Pas encore connecté : c'est le formulaire de connexion qui porte le champ « base », saisi
      // par l'utilisateur (voir architecture.md §17.F). On y renvoie en conservant la destination.
      const next = new URLSearchParams(window.location.search).get('next') || '/';
      window.location.href = `/login?next=${encodeURIComponent(next)}`;
      return;
    }
    if (!response.ok) {
      throw new Error('Erreur lors de la récupération de la liste des bases.');
    }
    const data = await response.json();
    databases.value = data.databases || [];
    // Une seule base disponible : sélection automatique, l'utilisateur ne voit jamais cet écran.
    if (databases.value.length === 1) {
      select(databases.value[0]);
      return;
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur inconnue.';
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.select-db-shell {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-secondary);
  font-family: var(--font-sans);
}

.select-db-card {
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

.database-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.database-item {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
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
.database-item:hover {
  border-color: var(--accent-primary);
  background: var(--bg-card);
}
.database-item svg {
  width: 18px;
  height: 18px;
  color: var(--text-muted);
}
.database-name {
  font-weight: 500;
}
</style>
