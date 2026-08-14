<template>
  <div class="groupby-picker-wrapper" ref="wrapperRef">
    <button type="button" class="groupby-trigger-btn" :class="{ 'is-active': modelValue.length > 0 }" @click.stop="showPopover = !showPopover">
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4h18M3 12h18M3 20h18" />
      </svg>
      <span>Regrouper par</span>
      <span v-if="modelValue.length > 0" class="groupby-count-badge">{{ modelValue.length }}</span>
    </button>

    <div v-if="showPopover" class="groupby-popover glass-morphism">
      <div class="groupby-popover-header">Regrouper par</div>

      <div v-if="modelValue.length === 0" class="groupby-empty">Aucun regroupement actif.</div>

      <div v-for="(level, index) in modelValue" :key="level.key" class="groupby-level-row">
        <span class="groupby-level-order">{{ index + 1 }}</span>
        <span class="groupby-level-label">{{ fieldLabel(level.key) }}</span>
        <select
          v-if="isDateField(level.key)"
          class="groupby-granularity-select"
          :value="level.granularity || 'day'"
          @change="setGranularity(index, ($event.target as HTMLSelectElement).value)"
        >
          <option value="day">Jour</option>
          <option value="week">Semaine</option>
          <option value="month">Mois</option>
          <option value="quarter">Trimestre</option>
          <option value="year">Année</option>
        </select>
        <button type="button" class="groupby-move-btn" :disabled="index === 0" @click="moveLevel(index, -1)" title="Monter">▲</button>
        <button type="button" class="groupby-move-btn" :disabled="index === modelValue.length - 1" @click="moveLevel(index, 1)" title="Descendre">▼</button>
        <button type="button" class="groupby-remove-btn" @click="removeLevel(index)" title="Retirer">✕</button>
      </div>

      <div class="groupby-add-row" v-if="availableFields.length">
        <select v-model="selectedToAdd" class="groupby-add-select">
          <option :value="null" disabled>-- Ajouter un champ --</option>
          <option v-for="f in availableFields" :key="f.key" :value="f.key">{{ f.label }}</option>
        </select>
        <button type="button" class="groupby-add-btn" :disabled="!selectedToAdd" @click="addLevel">Ajouter</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Widget de sélection des champs de regroupement (voir listConfig.groupBy / showGroupByWidget,
// architecture.md) — l'utilisateur choisit, dans l'ordre, les champs sur lesquels regrouper les
// lignes. N'écrit jamais directement listConfig (une prop) : émet vers internalGroupBy côté
// GenericList.vue (voir son patron internalColumns, une copie locale mutable). Modélisé sur le
// comportement de widgets/Many2ManyOrderedList.vue (liste ordonnée, ajout/retrait/réordonnancement)
// mais pas son gabarit visuel (table pleine largeur, inadapté à une insertion dans la barre de
// pagination) — un bouton compact ouvrant un popover.
import { ref, computed, onMounted, onUnmounted } from 'vue';

interface GroupByLevel {
  key: string;
  granularity?: 'day' | 'week' | 'month' | 'quarter' | 'year';
}

const props = defineProps<{
  modelValue: GroupByLevel[];
  // Champs compatibles avec le regroupement (voir isFieldGroupable dans GenericList.vue) — déjà
  // filtrés par l'appelant, y compris les champs dont la colonne n'est pas affichée.
  candidateFields: Array<{ key: string; label: string; type: string }>;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: GroupByLevel[]): void;
}>();

const showPopover = ref(false);
const wrapperRef = ref<HTMLElement | null>(null);
const selectedToAdd = ref<string | null>(null);

function handleClickOutside(event: MouseEvent) {
  if (wrapperRef.value && !wrapperRef.value.contains(event.target as Node)) {
    showPopover.value = false;
  }
}

onMounted(() => document.addEventListener('mousedown', handleClickOutside));
onUnmounted(() => document.removeEventListener('mousedown', handleClickOutside));

function fieldLabel(key: string): string {
  return props.candidateFields.find(f => f.key === key)?.label || key;
}

function isDateField(key: string): boolean {
  return props.candidateFields.find(f => f.key === key)?.type === 'date';
}

const availableFields = computed(() => {
  const chosen = new Set(props.modelValue.map(l => l.key));
  return props.candidateFields.filter(f => !chosen.has(f.key));
});

function addLevel() {
  if (!selectedToAdd.value) return;
  const field = props.candidateFields.find(f => f.key === selectedToAdd.value);
  const entry: GroupByLevel = { key: selectedToAdd.value };
  if (field?.type === 'date') entry.granularity = 'day';
  emit('update:modelValue', [...props.modelValue, entry]);
  selectedToAdd.value = null;
}

function removeLevel(index: number) {
  const next = [...props.modelValue];
  next.splice(index, 1);
  emit('update:modelValue', next);
}

function moveLevel(index: number, delta: number) {
  const target = index + delta;
  if (target < 0 || target >= props.modelValue.length) return;
  const next = [...props.modelValue];
  const [item] = next.splice(index, 1);
  next.splice(target, 0, item);
  emit('update:modelValue', next);
}

function setGranularity(index: number, granularity: string) {
  const next = [...props.modelValue];
  next[index] = { ...next[index], granularity: granularity as GroupByLevel['granularity'] };
  emit('update:modelValue', next);
}
</script>

<style scoped>
.groupby-picker-wrapper {
  position: relative;
}

.groupby-trigger-btn {
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
.groupby-trigger-btn:hover {
  background-color: var(--bg-secondary);
}
.groupby-trigger-btn.is-active {
  color: var(--accent-primary);
  border-color: var(--accent-primary);
}

.groupby-count-badge {
  background-color: rgba(99, 102, 241, 0.2);
  color: var(--accent-primary);
  border-radius: var(--radius-full);
  padding: 0 6px;
  font-size: 11px;
}

.groupby-popover {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  width: 300px;
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  z-index: 100;
  padding: 12px;
}

.groupby-popover-header {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
  text-transform: uppercase;
  margin-bottom: 8px;
}

.groupby-empty {
  font-size: 13px;
  color: var(--text-muted);
  font-style: italic;
  padding: 4px 0 10px;
}

.groupby-level-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
}

.groupby-level-order {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background-color: var(--accent-primary);
  color: white;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.groupby-level-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--text-primary);
}

.groupby-granularity-select {
  font-size: 12px;
  padding: 2px 4px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background-color: var(--bg-card);
  color: var(--text-primary);
}

.groupby-move-btn, .groupby-remove-btn {
  flex-shrink: 0;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 11px;
  color: var(--text-secondary);
  padding: 2px 4px;
  border-radius: var(--radius-sm);
}
.groupby-move-btn:hover:not(:disabled), .groupby-remove-btn:hover {
  background-color: var(--bg-secondary);
}
.groupby-move-btn:disabled {
  opacity: 0.3;
  cursor: default;
}
.groupby-remove-btn {
  color: var(--accent-danger, #e74c3c);
}

.groupby-add-row {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border-color);
}

.groupby-add-select {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  padding: 4px 6px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background-color: var(--bg-card);
  color: var(--text-primary);
}

.groupby-add-btn {
  padding: 4px 12px;
  background-color: var(--accent-primary);
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-weight: 500;
  font-size: 12px;
}
.groupby-add-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
