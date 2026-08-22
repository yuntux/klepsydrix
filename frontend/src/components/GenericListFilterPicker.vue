<template>
  <div class="filter-picker-wrapper" ref="wrapperRef">
    <button type="button" class="filter-trigger-btn" :class="{ 'is-active': activeCount > 0 }" @click.stop="showPopover = !showPopover">
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4h18M6 8h12M10 12h4" />
      </svg>
      <span>Filtrer</span>
      <span v-if="activeCount > 0" class="filter-count-badge">{{ activeCount }}</span>
    </button>

    <Teleport to="body">
      <div v-if="showPopover" class="filter-popover glass-morphism" :style="dropdownStyle" ref="popoverRef">
        <div v-if="predefinedFilters.length" class="filter-section">
          <div class="filter-section-header">Filtres prédéfinis</div>
          <label v-for="f in predefinedFilters" :key="f.name" class="filter-row">
            <input type="checkbox" :checked="activePredefinedNames.has(f.name)" @change="$emit('toggle-predefined', f.name)" />
            <span class="filter-row-label">{{ f.name }}</span>
          </label>
        </div>

        <div class="filter-section">
          <div class="filter-section-header">Filtres personnalisés</div>
          <div v-if="customFilters.length === 0" class="filter-empty">Aucun filtre enregistré.</div>
          <div v-for="f in customFilters" :key="f.id" class="filter-row filter-row-custom">
            <label class="filter-row-checkbox-label">
              <input type="checkbox" :checked="activeCustomIds.has(f.id)" @change="$emit('toggle-custom', f.id)" />
              <span class="filter-row-label">{{ f.name }}</span>
              <span v-if="f.is_shared" class="filter-shared-badge" title="Partagé">⇄</span>
            </label>
            <button
              v-if="currentUserId != null && f.user_id === currentUserId"
              type="button"
              class="filter-delete-btn"
              title="Supprimer ce filtre"
              @click="$emit('delete-custom-filter', f.id)"
            >🗑</button>
          </div>
          <button type="button" class="filter-custom-btn" @click="onOpenCustomBuilder">Filtre personnalisé…</button>
        </div>

        <div v-if="hasCustomDomain" class="filter-section filter-adhoc-row">
          <span class="filter-row-label">Filtre personnalisé actif (non enregistré)</span>
          <div class="filter-adhoc-actions">
            <!-- Rouvre la popin avec l'arbre du domaine actif déjà chargé (voir
                 GenericList.vue::adhocCustomDomain passé en initial-domain à la popin — même
                 événement que "Filtre personnalisé…", la popin se pré-remplit d'elle-même). -->
            <button type="button" class="filter-clear-btn" @click="onOpenCustomBuilder">Modifier</button>
            <button type="button" class="filter-clear-btn" @click="$emit('clear-custom-domain')">Effacer</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
// Widget "Filtrer" (barre du haut, à côté de "Regrouper par") — voir GenericList.vue. Combine
// filtres prédéfinis (déclarés côté vue, listConfig.predefinedFilters) et filtres personnalisés
// (modèle CustomFilter, CRUD générique) ; l'assemblage réel des domaines cochés en un domaine actif
// unique se fait côté GenericList.vue (ce composant ne fait qu'exposer l'état coché/décoché).
//
// Popover téléporté <body> + positionné via Floating UI (voir useFloatingDropdown.ts, même patron
// que widgets/ReportPrintMenu.vue) : sans ça, l'overflow du panneau (SplitPanel) qui héberge
// GenericList.vue coupait ce popover en `position: absolute` classique dès que le panneau était
// trop étroit.
import { ref, computed, onMounted, onUnmounted } from 'vue';
import type { DomainNode } from '../utils/domain';
import { useFloatingDropdown } from '../composables/useFloatingDropdown';

interface PredefinedFilterDef {
  name: string;
  domain: DomainNode;
}

interface CustomFilterRecord {
  id: number;
  name: string;
  domain: string | null;
  is_shared: boolean;
  is_auto_apply: boolean;
  user_id: number;
}

const props = defineProps<{
  predefinedFilters: PredefinedFilterDef[];
  customFilters: CustomFilterRecord[];
  activePredefinedNames: Set<string>;
  activeCustomIds: Set<number>;
  currentUserId: number | null;
  hasCustomDomain: boolean;
}>();

const emit = defineEmits<{
  (e: 'toggle-predefined', name: string): void;
  (e: 'toggle-custom', id: number): void;
  (e: 'open-custom-builder'): void;
  (e: 'delete-custom-filter', id: number): void;
  (e: 'clear-custom-domain'): void;
}>();

const showPopover = ref(false);
const wrapperRef = ref<HTMLElement | null>(null);
const popoverRef = ref<HTMLElement | null>(null);
const { dropdownStyle } = useFloatingDropdown(wrapperRef, popoverRef, showPopover);

const activeCount = computed(() =>
  props.activePredefinedNames.size + props.activeCustomIds.size + (props.hasCustomDomain ? 1 : 0)
);

// Le popover est téléporté hors de wrapperRef : un clic à l'intérieur doit être reconnu comme
// "dedans" même s'il n'est plus, dans le DOM réel, un descendant de wrapperRef.
function handleClickOutside(event: MouseEvent) {
  const target = event.target as Node;
  const insideWrapper = wrapperRef.value?.contains(target);
  const insidePopover = popoverRef.value?.contains(target);
  if (!insideWrapper && !insidePopover) {
    showPopover.value = false;
  }
}

onMounted(() => document.addEventListener('mousedown', handleClickOutside));
onUnmounted(() => document.removeEventListener('mousedown', handleClickOutside));

function onOpenCustomBuilder() {
  showPopover.value = false;
  emit('open-custom-builder');
}
</script>

<style scoped>
.filter-picker-wrapper {
  position: relative;
}

.filter-trigger-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-full);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}
.filter-trigger-btn:hover {
  background-color: var(--bg-secondary);
}
.filter-trigger-btn.is-active {
  color: var(--accent-primary);
  border-color: var(--accent-primary);
}

.filter-count-badge {
  background-color: rgba(99, 102, 241, 0.2);
  color: var(--accent-primary);
  border-radius: var(--radius-full);
  padding: 0 6px;
  font-size: 11px;
}

/* position: fixed + top/left/width fournis par dropdownStyle (voir useFloatingDropdown) — la
   largeur inline calée sur l'ancre (bouton compact, ~110px) est volontairement écrasée par
   min-width ci-dessous, même patron que ReportPrintMenu.vue::report-print-dropdown. */
.filter-popover {
  min-width: 320px;
  max-height: 400px;
  overflow-y: auto;
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  z-index: 1000;
  padding: 12px;
}

.filter-section {
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-color);
}
.filter-section:last-child {
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}

.filter-section-header {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
  text-transform: uppercase;
  margin-bottom: 6px;
}

.filter-empty {
  font-size: 13px;
  color: var(--text-muted);
  font-style: italic;
  padding: 2px 0 6px;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
  color: var(--text-primary);
  cursor: pointer;
}

.filter-row-custom {
  justify-content: space-between;
}

.filter-row-checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  min-width: 0;
  flex: 1;
}

.filter-row-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.filter-shared-badge {
  font-size: 11px;
  color: var(--accent-primary);
}

.filter-delete-btn {
  flex-shrink: 0;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 12px;
  padding: 2px 4px;
  border-radius: var(--radius-sm);
}
.filter-delete-btn:hover {
  background-color: var(--bg-secondary);
}

.filter-custom-btn {
  margin-top: 6px;
  width: 100%;
  padding: 6px 10px;
  font-size: 12px;
  font-weight: 600;
  border-radius: var(--radius-sm);
  border: 1px dashed var(--border-color);
  background: transparent;
  color: var(--accent-primary);
  cursor: pointer;
}
.filter-custom-btn:hover {
  background-color: var(--bg-secondary);
}

.filter-adhoc-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
}

.filter-adhoc-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.filter-clear-btn {
  flex-shrink: 0;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}
.filter-clear-btn:hover {
  background-color: var(--bg-secondary);
}
</style>
