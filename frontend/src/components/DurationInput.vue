<template>
  <span v-if="disabled" class="duration-display">{{ formatDurationMinutes(modelValue) }}</span>
  <select
    v-else
    class="duration-select"
    :value="modelValue ?? ''"
    @change="onChange"
  >
    <option v-for="opt in options" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
  </select>
</template>

<script setup lang="ts">
// Widget générique pour le type de champ "duration" (voir architecture.md) : la valeur stockée
// est toujours des minutes entières côté backend (voir backend/app/core/time_utils.py). En lecture
// seule, affiche le format Xh/XhYY (formatDurationMinutes, mirroir JS de minutes_to_hours) ; sinon,
// une liste déroulante de multiples du pas de créneau standard (getDurationOptions, mirroir JS de
// get_duration_options) — jamais de saisie libre, une durée ne peut être qu'un multiple exact du
// créneau (contrainte imposée côté backend, voir validate_multiple_of_standard_timeslot).
import { computed } from 'vue';
import { useTimeslotGrid } from '../composables/useTimeslotGrid';
import { formatDurationMinutes, getDurationOptions } from '../utils/duration';

const props = defineProps<{
  modelValue: number | null;
  disabled?: boolean;
  includeZero?: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: number | null): void;
  (e: 'change', value: number | null): void;
}>();

const { currentStandardDuration } = useTimeslotGrid();

const options = computed(() => getDurationOptions(currentStandardDuration.value, props.includeZero));

function onChange(event: Event) {
  const raw = (event.target as HTMLSelectElement).value;
  const value = raw === '' ? null : Number(raw);
  emit('update:modelValue', value);
  emit('change', value);
}
</script>

<style scoped>
.duration-display {
  display: block;
  width: 100%;
  padding: 6px 10px;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-primary);
  text-align: right;
}

.duration-select {
  width: 100%;
  background-color: transparent;
  border: 1px solid transparent;
  color: var(--text-primary);
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  outline: none;
  font-family: var(--font-sans);
  font-size: 13px;
  /* Convention comptable, cohérente avec .inline-number (GenericList.vue) : les durées, comme les
     nombres, calées à droite de leur colonne. */
  text-align: right;
  transition: all var(--transition-fast);
}

.duration-select:hover {
  background-color: var(--bg-secondary);
  border-color: var(--border-color);
}

.duration-select:focus {
  background-color: var(--bg-card);
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.15);
}
</style>
