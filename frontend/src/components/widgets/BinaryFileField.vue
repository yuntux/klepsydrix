<template>
  <div class="binary-field">
    <span class="binary-field-name" :title="modelValue?.filename || ''">
      {{ modelValue?.filename || 'Aucun fichier' }}
    </span>
    <button v-if="hasValue" type="button" class="btn-binary-action" title="Télécharger" @click.stop="download">📥</button>
    <button v-if="hasValue && !disabled" type="button" class="btn-binary-action" title="Effacer" @click.stop="clear">🗑</button>
    <button v-if="!disabled" type="button" class="btn-binary-action" title="Parcourir" @click.stop="browse">📁</button>
    <input ref="fileInput" type="file" class="binary-field-input" @change="onFileChange" />
  </div>
</template>

<script setup lang="ts">
// Widget par défaut de tout champ binaire générique (info={"type": "binary"}) : un fichier
// quelconque, stocké côté modèle sous la forme {filename, mime_type, data_base64} (voir
// architecture.md, champ binaire générique). Sert de base à ImageField.vue (widget="image"), qui
// se contente d'ajouter un aperçu au-dessus de ce même composant plutôt que de dupliquer la
// logique Télécharger/Effacer/Parcourir.
import { computed, ref } from 'vue';

export interface BinaryValue {
  filename: string;
  mime_type: string;
  data_base64: string;
}

const props = defineProps<{
  modelValue: BinaryValue | null;
  disabled?: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: BinaryValue | null): void;
}>();

const fileInput = ref<HTMLInputElement | null>(null);
const hasValue = computed(() => !!props.modelValue?.data_base64);

function browse() {
  fileInput.value?.click();
}

function clear() {
  emit('update:modelValue', null);
}

function download() {
  if (!props.modelValue?.data_base64) return;
  const link = document.createElement('a');
  link.href = `data:${props.modelValue.mime_type || 'application/octet-stream'};base64,${props.modelValue.data_base64}`;
  link.download = props.modelValue.filename || 'fichier';
  link.click();
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    const result = reader.result as string;
    const base64 = result.split(',')[1] || '';
    emit('update:modelValue', { filename: file.name, mime_type: file.type || 'application/octet-stream', data_base64: base64 });
  };
  reader.readAsDataURL(file);
  input.value = '';
}
</script>

<style scoped>
.binary-field {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  width: 100%;
}

.binary-field-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--text-secondary);
}

.btn-binary-action {
  flex-shrink: 0;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 13px;
  padding: 2px 4px;
  border-radius: var(--radius-md);
  line-height: 1;
}

.btn-binary-action:hover {
  background-color: var(--bg-secondary, rgba(0, 0, 0, 0.06));
}

.binary-field-input {
  display: none;
}
</style>
