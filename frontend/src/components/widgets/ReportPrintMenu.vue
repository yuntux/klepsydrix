<!--
  Point d'entrée unique "Imprimer" pour les actions __actions__ de type "report" (voir
  architecture.md §22.D) — un seul bouton, quelle que soit la vue (GenericList.vue, GenericForm.vue)
  qui le pose, déroulant la liste des rapports disponibles pour l'objet. Absent du DOM tant que
  `actions` est vide (porté par le `v-if` de l'appelant), donc sans effet sur une ressource qui ne
  déclare aucun rapport.

  La résolution des ids imprimés dépend du CONTEXTE d'appel (sélection de liste, enregistrement de
  formulaire...), pas de l'action elle-même (qui n'a plus de `scope`, voir course.py) — d'où
  `resolveIds`, fourni par l'appelant plutôt que codé ici.
-->
<template>
  <div class="report-print-menu" ref="containerRef">
    <BaseButton type="button" variant="secondary" :title="tooltip" :loading="pending" @click.stop="toggleDropdown">
      Imprimer<span v-if="badge">{{ ` (${badge})` }}</span>
    </BaseButton>

    <Teleport to="body">
      <div v-if="isOpen" class="report-print-dropdown glass-morphism" :style="dropdownStyle" ref="dropdownRef">
        <button
          v-for="action in actions"
          :key="action.id"
          type="button"
          class="report-print-item"
          @click="runAction(action)"
        >
          {{ action.label || action.name }}
        </button>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import BaseButton from '../BaseButton.vue';
import { useFloatingDropdown } from '../../composables/useFloatingDropdown';
import { useNotificationStore } from '../../stores/notifications';
import * as api from '../../services/api';

const props = defineProps<{
  actions: any[];
  resolveIds: () => number[];
  // Optionnels, réservés à GenericList.vue (badge du nombre de lignes sélectionnées + infobulle
  // explicitant le comportement "sélection sinon toute la liste") — GenericForm.vue n'en a pas
  // besoin, sa cible est toujours sans ambiguïté (l'enregistrement affiché, ou l'édition groupée).
  badge?: number | string;
  tooltip?: string;
}>();

const notificationStore = useNotificationStore();

const isOpen = ref(false);
// Génération PDF potentiellement longue (WeasyPrint, plusieurs secondes sur un rapport de
// plusieurs pages — voir architecture.md §22.A) : sans indicateur, un clic sans effet visible
// immédiat lit comme un bouton cassé. Réutilise le sablier déjà porté par BaseButton (voir son
// prop `loading`) plutôt que d'en inventer un nouveau ici.
const pending = ref(false);
const containerRef = ref<HTMLElement | null>(null);
const dropdownRef = ref<HTMLElement | null>(null);
const { dropdownStyle } = useFloatingDropdown(containerRef, dropdownRef, isOpen);

function toggleDropdown() {
  isOpen.value = !isOpen.value;
}

async function runAction(action: any) {
  isOpen.value = false;
  pending.value = true;
  try {
    await api.downloadReport(action.report, props.resolveIds());
  } catch (error: any) {
    notificationStore.showNotification('error', error?.message || "Erreur lors de la génération du document.");
  } finally {
    pending.value = false;
  }
}

// Dropdown téléporté hors de containerRef (voir SearchableMultiSelect.vue::handleClickOutside,
// même raison) — capture (3e argument `true`) pour se fermer avant qu'un autre gestionnaire de
// clic ne s'exécute.
function handleClickOutside(event: MouseEvent) {
  const target = event.target as Node;
  const insideContainer = containerRef.value?.contains(target);
  const insideDropdown = dropdownRef.value?.contains(target);
  if (!insideContainer && !insideDropdown) {
    isOpen.value = false;
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside, true);
});

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside, true);
});
</script>

<style scoped>
.report-print-menu {
  display: inline-flex;
}

.report-print-dropdown {
  position: fixed;
  z-index: 1000;
  min-width: 220px;
  max-width: 360px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  box-shadow: var(--shadow-md);
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  /* Fond explicite : la classe utilitaire "glass-morphism" (le flou dépoli) est déclarée en CSS
     NON scopé dans GenericForm.vue (voir son <style> sans "scoped") — un fichier sans rapport
     avec ce composant. En dépendre pour le SEUL fond, sans repli ici, rend ce menu fragile à toute
     réorganisation de ce fichier tiers (constaté : fond transparent, glass-morphism absent à un
     instant donné). --bg-card est la même variable que glass-morphism utilise, donc aucun double
     rendu visuel — juste un filet de sécurité si la classe externe venait à manquer. */
  background-color: var(--bg-card);
}

.report-print-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 8px 10px;
  border: none;
  background: transparent;
  border-radius: var(--radius-sm, 4px);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
}

.report-print-item:hover {
  background-color: var(--bg-hover, rgba(0, 0, 0, 0.05));
}
</style>
