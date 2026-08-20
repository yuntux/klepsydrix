<template>
  <span v-if="disabled" class="timeslot-picker-display">{{ formatClockTime(modelValue) }}</span>
  <select v-else class="timeslot-picker-select" :value="modelValue ?? ''" @change="onChange">
    <option v-if="includeEmpty" value="">Aucune</option>
    <option v-for="opt in options" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
  </select>
</template>

<script setup lang="ts">
// Widget générique pour choisir un horaire (minutes depuis minuit) parmi les créneaux du pas
// horaire STANDARD courant — voir wizard_grid_settings.py (heures d'ouverture, récréations).
// Volontairement calé sur le pas horaire PERSISTÉ (useTimeslotGrid().currentStandardDuration,
// même source que DurationInput.vue), pas sur une valeur en cours de saisie dans un wizard : dans
// le seul cas où le pas horaire ET une heure sont modifiés dans le MÊME passage du wizard, la
// liste peut donc rester momentanément calée sur l'ancien pas jusqu'à la confirmation — sans
// conséquence, la validation réelle a de toute façon lieu côté serveur à l'application (voir
// SystemSetting._validate_break_start / GridDaySettings._validate_hours).
import { computed } from 'vue';
import { useTimeslotGrid } from '../../composables/useTimeslotGrid';
import { formatClockTime } from '../../utils/date';

const props = defineProps<{
  modelValue: number | null;
  field?: any;
  widgetParams?: any;
  disabled?: boolean;
  parentRecord?: any;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: number | null): void;
}>();

const { currentStandardDuration } = useTimeslotGrid();
const includeEmpty = computed(() => props.widgetParams?.includeEmpty === true);

const options = computed(() => {
  const step = currentStandardDuration.value;
  const count = Math.floor((24 * 60) / step);
  return Array.from({ length: count }, (_, i) => {
    const value = i * step;
    return { value, label: formatClockTime(value) };
  });
});

function onChange(event: Event) {
  const raw = (event.target as HTMLSelectElement).value;
  const value = raw === '' ? null : Number(raw);
  emit('update:modelValue', value);
}
</script>

<style scoped>
.timeslot-picker-display {
  display: block;
  width: 100%;
  padding: 6px 10px;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-primary);
}

.timeslot-picker-select {
  width: 100%;
  background-color: transparent;
  border: 1px solid transparent;
  color: var(--text-primary);
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  outline: none;
  font-family: var(--font-sans);
  font-size: 13px;
  transition: all var(--transition-fast);
}

.timeslot-picker-select:hover {
  background-color: var(--bg-secondary);
  border-color: var(--border-color);
}

.timeslot-picker-select:focus {
  background-color: var(--bg-card);
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.15);
}
</style>
