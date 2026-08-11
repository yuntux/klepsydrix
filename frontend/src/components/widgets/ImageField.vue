<template>
  <div class="image-field">
    <img v-if="previewSrc" :src="previewSrc" class="image-field-preview" alt="" />
    <BinaryFileField :modelValue="modelValue" :disabled="disabled" @update:modelValue="$emit('update:modelValue', $event)" />
  </div>
</template>

<script setup lang="ts">
// Widget spécialisé sélectionné via info={"widget": "image"} sur un champ binaire générique (voir
// BinaryFileField.vue et architecture.md) : ajoute un aperçu visuel au-dessus des mêmes actions
// Télécharger/Effacer/Parcourir, sans dupliquer leur logique. Enregistré dans widgets/registry.ts,
// contexts: ['form'] uniquement — une liste (GenericList.vue) n'affiche jamais l'image elle-même,
// seulement un badge de présence, comme tout autre champ binaire.
import { computed } from 'vue';
import BinaryFileField, { type BinaryValue } from './BinaryFileField.vue';

const props = defineProps<{
  modelValue: BinaryValue | null;
  field?: any;
  widgetParams?: any;
  disabled?: boolean;
  parentRecord?: any;
}>();

defineEmits<{
  (e: 'update:modelValue', value: BinaryValue | null): void;
}>();

const previewSrc = computed(() => {
  if (!props.modelValue?.data_base64) return null;
  return `data:${props.modelValue.mime_type || 'image/png'};base64,${props.modelValue.data_base64}`;
});
</script>

<style scoped>
.image-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
}

.image-field-preview {
  max-width: 120px;
  max-height: 120px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  object-fit: cover;
}
</style>
