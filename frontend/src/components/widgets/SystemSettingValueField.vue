<template>
  <select v-if="config.type === 'select'" :value="modelValue" class="form-select" :disabled="disabled" @change="emitValue(($event.target as HTMLSelectElement).value)">
    <option v-for="opt in config.options" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
  </select>
  <input v-else-if="config.type === 'boolean'" type="checkbox" :checked="modelValue === 'true'" :disabled="disabled" @change="emitValue(($event.target as HTMLInputElement).checked ? 'true' : 'false')" />
  <input v-else-if="config.type === 'number'" type="number" :value="modelValue" class="form-input" :disabled="disabled" @change="emitValue(($event.target as HTMLInputElement).value)" />
  <input v-else type="text" :value="modelValue" class="form-input" :disabled="disabled" @change="emitValue(($event.target as HTMLInputElement).value)" />
</template>

<script setup lang="ts">
// Champ "Valeur" des paramètres système (SystemSetting.value) — un unique champ texte en base,
// dont le contrôle de saisie varie selon le paramètre choisi (SystemSetting.key). Pas de nouvel
// aller-retour serveur : la correspondance clé -> type de contrôle est une pure question d'affichage,
// tenue ici. Au-delà de cette liste (ex: les séparateurs), on retombe sur un simple champ texte.
import { computed } from 'vue';

const NUMBER_FORMAT_OPTIONS = [
  { value: 'numerique', label: 'Numérique' },
  { value: 'alphabetique', label: 'Alphabétique' },
];

const SETTING_FIELD_TYPES: Record<string, { type: string; options?: typeof NUMBER_FORMAT_OPTIONS }> = {
  STANDARD_TIMESLOT_DURATION: { type: 'number' },
  DIVISION_PART_NAME_HAS_DIV_CODE: { type: 'boolean' },
  DIVISION_PART_NAME_HAS_SUBJECT_CODE: { type: 'boolean' },
  DIVISION_PART_NAME_NUMBER_FORMAT: { type: 'select', options: NUMBER_FORMAT_OPTIONS },
  GROUP_NAME_HAS_DIV_CODE: { type: 'boolean' },
  GROUP_NAME_HAS_SUBJECT_CODE: { type: 'boolean' },
  GROUP_NAME_NUMBER_FORMAT: { type: 'select', options: NUMBER_FORMAT_OPTIONS },
};

const props = defineProps<{
  modelValue: string;
  field?: any;
  widgetParams?: any;
  disabled?: boolean;
  parentRecord?: { key?: string };
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void;
}>();

const config = computed(() => SETTING_FIELD_TYPES[props.parentRecord?.key || ''] || { type: 'text' });

function emitValue(value: string) {
  emit('update:modelValue', value);
}
</script>
