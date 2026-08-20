<template>
  <span v-if="disabled" class="clock-time-display">{{ formatClockTime(modelValue) }}</span>
  <input
    v-else
    type="time"
    class="clock-time-input"
    :value="minutesToTimeInputValue(modelValue)"
    :min="minBoundTime"
    :max="maxBoundTime"
    @change="onChange"
  />
</template>

<script setup lang="ts">
// Widget "heure" HTML5 natif générique (minutes depuis minuit en interne) — AUCUNE connaissance
// de créneau, de grille ou de pas horaire ici : les bornes min/max sont calculées par l'APPELANT
// (ex: wizard_grid_settings.py::_render_display_rows) et simplement LUES sur deux champs frères
// de la même ligne (parentRecord — voir GenericList.vue::isColumnReadOnly pour la même convention
// "model = ligne courante"), désignés par leur nom via widgetParams.{minField, maxField}. Ce
// widget est donc réutilisable pour n'importe quel champ heure borné par deux valeurs d'une même
// ligne, sans rapport avec une grille horaire.
import { computed } from 'vue';
import { formatClockTime, minutesToTimeInputValue, timeInputValueToMinutes } from '../../utils/date';

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

function fieldValue(fieldName?: string): number | undefined {
  if (!fieldName || !props.parentRecord) return undefined;
  const v = props.parentRecord[fieldName];
  return typeof v === 'number' ? v : undefined;
}

const minBound = computed(() => fieldValue(props.widgetParams?.minField));
const maxBound = computed(() => fieldValue(props.widgetParams?.maxField));
const minBoundTime = computed(() => (minBound.value !== undefined ? minutesToTimeInputValue(minBound.value) : undefined));
const maxBoundTime = computed(() => (maxBound.value !== undefined ? minutesToTimeInputValue(maxBound.value) : undefined));

function onChange(event: Event) {
  const raw = (event.target as HTMLInputElement).value;
  let value = timeInputValueToMinutes(raw);
  // Bornage RÉELLEMENT appliqué (pas juste l'attribut HTML min/max, qui ne fait que teinter le
  // champ en ":invalid" sans empêcher la saisie ni l'émission de la valeur) : on écrête vers la
  // borne dépassée. Le format 00:00-23:59, lui, est déjà garanti par le natif <input type="time">
  // (aucune saisie hors plage n'est représentable par ce contrôle).
  if (value !== null) {
    if (minBound.value !== undefined && value < minBound.value) value = minBound.value;
    if (maxBound.value !== undefined && value > maxBound.value) value = maxBound.value;
  }
  emit('update:modelValue', value);
}
</script>

<style scoped>
.clock-time-display {
  display: block;
  width: 100%;
  padding: 6px 10px;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-primary);
}

.clock-time-input {
  width: 100%;
  background-color: transparent;
  border: 1px solid transparent;
  color: var(--text-primary);
  padding: 5px 8px;
  border-radius: var(--radius-sm);
  outline: none;
  font-family: var(--font-sans);
  font-size: 13px;
  transition: all var(--transition-fast);
}

.clock-time-input:hover {
  background-color: var(--bg-secondary);
  border-color: var(--border-color);
}

.clock-time-input:focus {
  background-color: var(--bg-card);
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.15);
}
</style>
