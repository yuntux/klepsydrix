<template>
  <div class="admin-shell">
    <header class="admin-header">
      <BaseLogo size="lg" label="Klepsydrix — Console d'administration" />
      <button class="link-button" @click="logout">Se déconnecter</button>
    </header>

    <main class="admin-main">
      <div v-if="loading" class="state-message">Chargement…</div>
      <div v-else-if="loadError" class="state-message error">{{ loadError }}</div>
      <template v-else>
        <div class="toolbar">
          <span class="scope-badge" :class="{ super: isSuperAdmin }">
            {{ isSuperAdmin ? 'Super-administrateur — accès à toutes les bases' : 'Administrateur de vos bases uniquement' }}
          </span>
          <BaseButton v-if="isSuperAdmin" @click="showCreateModal = true">Créer une base</BaseButton>
        </div>

        <div v-if="actionError" class="state-message error">{{ actionError }}</div>
        <div v-if="actionSuccess" class="state-message success">{{ actionSuccess }}</div>

        <div v-if="databases.length === 0" class="state-message">
          Aucune base administrable pour cette identité.
        </div>
        <table v-else class="db-table">
          <thead>
            <tr>
              <th>Base</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="slug in databases" :key="slug">
              <td class="db-name">{{ slug }}</td>
              <td class="db-actions">
                <button class="link-button" @click="downloadBackup(slug)">Sauvegarder</button>
                <button v-if="isSuperAdmin" class="link-button" @click="openDuplicate(slug)">Dupliquer</button>
                <button class="link-button" @click="openRestore(slug)">Restaurer</button>
                <button class="link-button danger" @click="openDelete(slug)">Supprimer</button>
              </td>
            </tr>
          </tbody>
        </table>
      </template>
    </main>

    <!-- Créer une base (super-admin) -->
    <BaseModal v-model="showCreateModal" title="Créer une base" width="420px">
      <form class="modal-form" @submit.prevent="submitCreate">
        <BaseInput v-model="createSlug" label="Nom de la base" placeholder="ex: college-jean-jaures" required />
        <BaseInput v-model="createAdminEmail" type="email" label="Email de l'administrateur désigné" placeholder="ex: proviseur@ac-exemple.fr" required />
        <p class="hint">
          L'administrateur désigné n'a pas besoin d'avoir déjà un compte : sa ligne d'identité sera
          rapprochée automatiquement lors de sa première connexion (email correspondant).
        </p>
        <BaseToggle v-if="isLocalProviderActive" v-model="createSendPasswordReset">
          <template #right>Envoyer un lien de réinitialisation de mot de passe</template>
        </BaseToggle>
        <p v-if="isLocalProviderActive && createSendPasswordReset" class="hint">
          Un compte local sera créé pour cet email, sans mot de passe, et un lien de
          réinitialisation lui sera envoyé pour qu'il en définisse un.
        </p>
        <div v-if="createError" class="state-message error">{{ createError }}</div>
        <div class="modal-actions">
          <BaseButton type="submit" :loading="submitting">Créer</BaseButton>
        </div>
      </form>
    </BaseModal>

    <!-- Dupliquer une base (super-admin) -->
    <BaseModal v-model="showDuplicateModal" title="Dupliquer une base" width="420px">
      <form class="modal-form" @submit.prevent="submitDuplicate">
        <p class="hint">Source : <strong>{{ targetSlug }}</strong></p>
        <BaseInput v-model="duplicateNewSlug" label="Nom de la nouvelle base" placeholder="ex: college-jean-jaures-test" required />
        <div v-if="duplicateError" class="state-message error">{{ duplicateError }}</div>
        <div class="modal-actions">
          <BaseButton type="submit" :loading="submitting">Dupliquer</BaseButton>
        </div>
      </form>
    </BaseModal>

    <!-- Restaurer une base (destructif) -->
    <BaseModal v-model="showRestoreModal" title="Restaurer une base" width="440px">
      <form class="modal-form" @submit.prevent="submitRestore">
        <p class="hint warning">
          ⚠️ « Annule et remplace » — le contenu actuel de <strong>{{ targetSlug }}</strong> sera
          intégralement perdu et remplacé par le fichier importé.
        </p>
        <label class="file-label">
          Fichier de sauvegarde
          <input type="file" required @change="onRestoreFileChange" />
        </label>
        <BaseInput
          v-model="restoreConfirm"
          :label="`Tapez « ${targetSlug} » pour confirmer`"
          :placeholder="targetSlug || ''"
          required
        />
        <div v-if="restoreError" class="state-message error">{{ restoreError }}</div>
        <div class="modal-actions">
          <BaseButton type="submit" :loading="submitting" :disabled="restoreConfirm !== targetSlug">Restaurer</BaseButton>
        </div>
      </form>
    </BaseModal>

    <!-- Supprimer une base (destructif) -->
    <BaseModal v-model="showDeleteModal" title="Supprimer une base" width="420px">
      <form class="modal-form" @submit.prevent="submitDelete">
        <p class="hint warning">
          ⚠️ Suppression définitive de <strong>{{ targetSlug }}</strong> et de toutes ses données.
        </p>
        <BaseInput
          v-model="deleteConfirm"
          :label="`Tapez « ${targetSlug} » pour confirmer`"
          :placeholder="targetSlug || ''"
          required
        />
        <div v-if="deleteError" class="state-message error">{{ deleteError }}</div>
        <div class="modal-actions">
          <BaseButton type="submit" :loading="submitting" :disabled="deleteConfirm !== targetSlug">Supprimer</BaseButton>
        </div>
      </form>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { apiFetch } from '../services/api';
import BaseButton from '../components/BaseButton.vue';
import BaseModal from '../components/BaseModal.vue';
import BaseInput from '../components/BaseInput.vue';
import BaseToggle from '../components/BaseToggle.vue';
import BaseLogo from '../components/BaseLogo.vue';

const databases = ref<string[]>([]);
const isSuperAdmin = ref(false);
const loading = ref(true);
const loadError = ref('');
const actionError = ref('');
const actionSuccess = ref('');
const submitting = ref(false);

// Voir architecture.md §17.G — la case "envoyer un lien de réinitialisation" n'a de sens que si le
// provider "local" est actif sur l'instance (sinon aucun compte local n'existera jamais pour
// l'admin désigné). Chargé une seule fois, indépendamment de loadDatabases().
const isLocalProviderActive = ref(false);
async function loadLocalProviderStatus() {
  try {
    const response = await fetch('/api/auth/providers');
    const providers = response.ok ? await response.json() : [];
    isLocalProviderActive.value = providers.some((p: any) => p.protocol === 'local_password');
  } catch {
    isLocalProviderActive.value = false;
  }
}

const showCreateModal = ref(false);
const createSlug = ref('');
const createAdminEmail = ref('');
const createSendPasswordReset = ref(false);
const createError = ref('');

const showDuplicateModal = ref(false);
const duplicateNewSlug = ref('');
const duplicateError = ref('');

const showRestoreModal = ref(false);
const restoreFile = ref<File | null>(null);
const restoreConfirm = ref('');
const restoreError = ref('');

const showDeleteModal = ref(false);
const deleteConfirm = ref('');
const deleteError = ref('');

const targetSlug = ref('');

async function loadDatabases() {
  loading.value = true;
  loadError.value = '';
  try {
    const response = await apiFetch('/api/instance/admin/databases');
    if (!response.ok) {
      throw new Error(response.status === 403 ? "Vous n'avez accès à la console d'administration d'aucune base." : 'Erreur lors du chargement des bases.');
    }
    const data = await response.json();
    databases.value = data.databases || [];
    isSuperAdmin.value = !!data.is_super_admin;
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : 'Erreur inconnue.';
  } finally {
    loading.value = false;
  }
}

function flashSuccess(message: string) {
  actionError.value = '';
  actionSuccess.value = message;
  setTimeout(() => { actionSuccess.value = ''; }, 4000);
}

async function submitCreate() {
  submitting.value = true;
  createError.value = '';
  try {
    const response = await apiFetch('/api/instance/admin/databases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        slug: createSlug.value,
        admin_email: createAdminEmail.value,
        send_password_reset: createSendPasswordReset.value,
      }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(typeof data.detail === 'string' ? data.detail : 'Erreur lors de la création.');
    }
    const data = await response.json();
    showCreateModal.value = false;
    createSlug.value = '';
    createAdminEmail.value = '';
    const requestedReset = createSendPasswordReset.value;
    createSendPasswordReset.value = false;
    flashSuccess(
      requestedReset && !data.password_reset_email_sent
        ? "Base créée, mais l'envoi de l'email de réinitialisation a échoué (voir les journaux du serveur)."
        : 'Base créée avec succès.',
    );
    await loadDatabases();
  } catch (e) {
    createError.value = e instanceof Error ? e.message : 'Erreur inconnue.';
  } finally {
    submitting.value = false;
  }
}

function openDuplicate(slug: string) {
  targetSlug.value = slug;
  duplicateNewSlug.value = '';
  duplicateError.value = '';
  showDuplicateModal.value = true;
}

async function submitDuplicate() {
  submitting.value = true;
  duplicateError.value = '';
  try {
    const response = await apiFetch(`/api/instance/admin/databases/${encodeURIComponent(targetSlug.value)}/duplicate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_slug: duplicateNewSlug.value }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(typeof data.detail === 'string' ? data.detail : 'Erreur lors de la duplication.');
    }
    showDuplicateModal.value = false;
    flashSuccess(`Base « ${targetSlug.value} » dupliquée avec succès.`);
    await loadDatabases();
  } catch (e) {
    duplicateError.value = e instanceof Error ? e.message : 'Erreur inconnue.';
  } finally {
    submitting.value = false;
  }
}

function downloadBackup(slug: string) {
  // Téléchargement via le flux HTTP standard du navigateur (Content-Disposition: attachment
  // posé par le backend, voir instance_endpoints.py) — le cookie de session httpOnly est envoyé
  // automatiquement par le navigateur pour cette navigation same-origin, pas besoin de fetch/blob.
  window.open(`/api/instance/admin/databases/${encodeURIComponent(slug)}/backup`, '_blank');
}

function openRestore(slug: string) {
  targetSlug.value = slug;
  restoreFile.value = null;
  restoreConfirm.value = '';
  restoreError.value = '';
  showRestoreModal.value = true;
}

function onRestoreFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  restoreFile.value = input.files?.[0] || null;
}

// Même lecture que BinaryFileField.vue (readAsDataURL puis découpe du préfixe "data:...;base64,")
// — un seul et même format d'échange pour tous les fichiers envoyés à l'API.
function toBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result as string).split(',')[1] || '');
    reader.onerror = () => reject(new Error('Lecture du fichier impossible.'));
    reader.readAsDataURL(file);
  });
}

async function submitRestore() {
  if (!restoreFile.value) {
    restoreError.value = 'Sélectionnez un fichier.';
    return;
  }
  submitting.value = true;
  restoreError.value = '';
  try {
    // Corps JSON avec le fichier en base64 (convention des champs binaires du produit, voir
    // widgets/BinaryFileField.vue) plutôt qu'un FormData : un envoi multipart est un type de
    // contenu "simple" au sens CORS, donc déclenchable par un formulaire d'un site tiers avec le
    // cookie de session de la victime — voir instance_endpoints.py::restore_database.
    const file = {
      filename: restoreFile.value.name,
      mime_type: restoreFile.value.type || 'application/octet-stream',
      data_base64: await toBase64(restoreFile.value),
    };
    const response = await apiFetch(`/api/instance/admin/databases/${encodeURIComponent(targetSlug.value)}/restore`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirm: restoreConfirm.value, file }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(typeof data.detail === 'string' ? data.detail : 'Erreur lors de la restauration.');
    }
    showRestoreModal.value = false;
    flashSuccess(`Base « ${targetSlug.value} » restaurée avec succès.`);
  } catch (e) {
    restoreError.value = e instanceof Error ? e.message : 'Erreur inconnue.';
  } finally {
    submitting.value = false;
  }
}

function openDelete(slug: string) {
  targetSlug.value = slug;
  deleteConfirm.value = '';
  deleteError.value = '';
  showDeleteModal.value = true;
}

async function submitDelete() {
  submitting.value = true;
  deleteError.value = '';
  try {
    const params = new URLSearchParams({ confirm: deleteConfirm.value });
    const response = await apiFetch(`/api/instance/admin/databases/${encodeURIComponent(targetSlug.value)}?${params}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(typeof data.detail === 'string' ? data.detail : 'Erreur lors de la suppression.');
    }
    showDeleteModal.value = false;
    flashSuccess(`Base « ${targetSlug.value} » supprimée.`);
    await loadDatabases();
  } catch (e) {
    deleteError.value = e instanceof Error ? e.message : 'Erreur inconnue.';
  } finally {
    submitting.value = false;
  }
}

async function logout() {
  await fetch('/api/auth/logout', { method: 'POST' });
  window.location.href = '/login';
}

onMounted(() => {
  loadDatabases();
  loadLocalProviderStatus();
});
</script>

<style scoped>
.admin-shell {
  min-height: 100vh;
  background: var(--bg-secondary);
  font-family: var(--font-sans);
}

.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-xl);
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-color);
}

.link-button {
  background: none;
  border: none;
  color: var(--text-secondary);
  font-family: inherit;
  font-size: 0.85rem;
  cursor: pointer;
  padding: 0;
}
.link-button:hover {
  color: var(--accent-primary);
}
.link-button.danger:hover {
  color: var(--accent-danger);
}

.admin-main {
  max-width: 900px;
  margin: 0 auto;
  padding: var(--spacing-xl);
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-lg);
}

.scope-badge {
  font-size: 0.85rem;
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
}
.scope-badge.super {
  color: var(--accent-primary);
  border-color: var(--accent-primary);
}

.state-message {
  color: var(--text-muted);
  font-size: 0.9rem;
  margin-bottom: var(--spacing-md);
}
.state-message.error {
  color: var(--accent-danger);
}
.state-message.success {
  color: var(--accent-success, #2e9e5b);
}

.db-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.db-table th,
.db-table td {
  padding: var(--spacing-md);
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}
.db-table th {
  font-size: 0.8rem;
  color: var(--text-muted);
  font-weight: 500;
}
.db-table tr:last-child td {
  border-bottom: none;
}
.db-name {
  font-weight: 500;
  color: var(--text-primary);
}
.db-actions {
  display: flex;
  gap: var(--spacing-md);
}

.modal-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}
.hint {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin: 0;
}
.hint.warning {
  color: var(--accent-danger);
}
.file-label {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  font-size: 0.85rem;
  color: var(--text-secondary);
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
}
</style>
