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
      <template #icon>
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M6.72 13.829c-.24.03-.48.062-.72.096m.72-.096a42.415 42.415 0 0110.56 0m-10.56 0L6.34 18m10.94-4.171c.24.03.48.062.72.096m-.72-.096L17.66 18m0 0l.229 2.523a1.125 1.125 0 01-1.12 1.227H7.231c-.662 0-1.18-.568-1.12-1.227L6.34 18m11.318 0h1.091A2.25 2.25 0 0021 15.75V9.456c0-1.081-.768-2.015-1.837-2.175a48.055 48.055 0 00-1.913-.247M6.34 18H5.25A2.25 2.25 0 013 15.75V9.456c0-1.081.768-2.015 1.837-2.175a48.041 48.041 0 011.913-.247m10.5 0a48.536 48.536 0 00-10.5 0m10.5 0V3.375c0-.621-.504-1.125-1.125-1.125h-8.25c-.621 0-1.125.504-1.125 1.125v3.659M18 10.5h.008v.008H18V10.5zm-3 0h.008v.008H15V10.5z" />
        </svg>
      </template>
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
  /* Un <button> ne reçoit PAS la police du reste de la page par héritage CSS normal — la feuille
     de style par défaut du navigateur lui donne sa propre police système, jamais var(--font-sans)
     (voir body { font-family } dans main.css) : sans cette ligne, ce menu déroulant "Imprimer"
     rendait dans une police visiblement différente du bouton qui l'ouvre (.btn, qui déclare bien
     font-family explicitement). Même piège que pour n'importe quel <button>/<input>/<select>. */
  font-family: inherit;
  font-size: 13px;
  cursor: pointer;
}

.report-print-item:hover {
  background-color: var(--bg-hover, rgba(0, 0, 0, 0.05));
}
</style>
