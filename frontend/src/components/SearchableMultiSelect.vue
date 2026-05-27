<template>
  <div class="searchable-multiselect-container" :class="{ 'is-inline': inline, 'is-disabled': disabled, 'is-open': isOpen }" ref="containerRef">
    <div class="input-tags-wrapper" @click="focusInput">
      <div v-for="val in selectedOptions" :key="val.value" class="tag-badge">
        <span class="tag-label">{{ val.label }}</span>
        <span v-if="!disabled" class="tag-remove" @click.stop="removeOption(val.value)">×</span>
      </div>
      
      <input
        ref="inputRef"
        type="text"
        class="search-input"
        :placeholder="selectedOptions.length === 0 ? (placeholder || '-- Choisir --') : ''"
        v-model="searchQuery"
        :disabled="disabled"
        @focus="handleFocus"
        @keydown.down.prevent="navigateOptions(1)"
        @keydown.up.prevent="navigateOptions(-1)"
        @keydown.enter.prevent="selectHighlighted"
        @keydown.backspace="handleBackspace"
        @keydown.escape.prevent="closeDropdown"
      />
      
      <span class="chevron-icon" @click.stop="toggleDropdown">
        ▼
      </span>
    </div>

    <div v-if="isOpen && !disabled" class="options-dropdown glass-morphism">
      <div v-if="filteredOptions.length === 0" class="no-options">
        Aucun résultat trouvé
      </div>
      <div
        v-else
        v-for="(option, index) in filteredOptions"
        :key="option.value"
        class="option-item"
        :class="{
          'is-selected': isSelected(option.value),
          'is-highlighted': index === highlightedIndex
        }"
        @mousedown.prevent="toggleOption(option)"
      >
        <span class="checkbox-indicator">{{ isSelected(option.value) ? '✓' : '' }}</span>
        <span class="option-label">{{ option.label }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';

interface Option {
  value: any;
  label: string;
}

const props = defineProps<{
  modelValue: any[] | null | undefined;
  options: Option[];
  disabled?: boolean;
  placeholder?: string;
  required?: boolean;
  inline?: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: any[]): void;
  (e: 'change', value: any[]): void;
}>();

const isOpen = ref(false);
const searchQuery = ref('');
const highlightedIndex = ref(-1);
const containerRef = ref<HTMLElement | null>(null);
const inputRef = ref<HTMLInputElement | null>(null);

// Normaliser modelValue en tableau
const currentValues = computed(() => {
  if (!props.modelValue) return [];
  if (Array.isArray(props.modelValue)) return props.modelValue;
  return [props.modelValue];
});

// Trouver les options sélectionnées
const selectedOptions = computed(() => {
  return currentValues.value
    .map(val => props.options.find(opt => String(opt.value) === String(val)))
    .filter((opt): opt is Option => !!opt);
});

// Vérifier si une option est sélectionnée
function isSelected(value: any) {
  return currentValues.value.some(val => String(val) === String(value));
}

// Filtrer les options par recherche
const filteredOptions = computed(() => {
  if (!searchQuery.value) return props.options;
  const query = searchQuery.value.toLowerCase();
  return props.options.filter(opt =>
    opt.label.toLowerCase().includes(query)
  );
});

// Réinitialiser le focus lors du filtrage
watch(filteredOptions, () => {
  highlightedIndex.value = 0;
});

function focusInput() {
  if (props.disabled) return;
  inputRef.value?.focus();
}

function handleFocus() {
  if (props.disabled) return;
  isOpen.value = true;
  highlightedIndex.value = 0;
}

function toggleDropdown() {
  if (props.disabled) return;
  if (isOpen.value) {
    closeDropdown();
  } else {
    isOpen.value = true;
    focusInput();
  }
}

function closeDropdown() {
  isOpen.value = false;
  searchQuery.value = '';
}

function toggleOption(option: Option) {
  let newValues = [...currentValues.value];
  const idx = newValues.findIndex(val => String(val) === String(option.value));
  if (idx > -1) {
    newValues.splice(idx, 1);
  } else {
    newValues.push(option.value);
  }
  emit('update:modelValue', newValues);
  emit('change', newValues);
  searchQuery.value = ''; // Vider la recherche pour enchaîner
  focusInput();
}

function removeOption(value: any) {
  const newValues = currentValues.value.filter(val => String(val) !== String(value));
  emit('update:modelValue', newValues);
  emit('change', newValues);
}

function selectHighlighted() {
  if (highlightedIndex.value >= 0 && highlightedIndex.value < filteredOptions.value.length) {
    toggleOption(filteredOptions.value[highlightedIndex.value]);
  }
}

function handleBackspace() {
  if (!searchQuery.value && currentValues.value.length > 0) {
    const newValues = [...currentValues.value];
    newValues.pop();
    emit('update:modelValue', newValues);
    emit('change', newValues);
  }
}

function navigateOptions(direction: number) {
  if (!isOpen.value) {
    isOpen.value = true;
    highlightedIndex.value = 0;
    return;
  }
  const len = filteredOptions.value.length;
  if (len === 0) return;
  highlightedIndex.value = (highlightedIndex.value + direction + len) % len;
}

function handleClickOutside(event: MouseEvent) {
  if (containerRef.value && !containerRef.value.contains(event.target as Node)) {
    closeDropdown();
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside);
});

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside);
});
</script>

<style scoped>
.searchable-multiselect-container {
  position: relative;
  width: 100%;
}

.input-tags-wrapper {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-height: 38px;
  padding: 5px 35px 5px 12px;
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  cursor: text;
  transition: all var(--transition-fast);
  position: relative;
}

.input-tags-wrapper:hover {
  border-color: var(--text-muted);
}

.searchable-multiselect-container.is-open .input-tags-wrapper {
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.15);
}

.search-input {
  flex: 1;
  min-width: 60px;
  border: none;
  background: transparent;
  outline: none;
  font-family: var(--font-sans);
  font-size: 14px;
  color: var(--text-primary);
  padding: 2px 0;
}

.search-input::placeholder {
  color: var(--text-muted);
}

.tag-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background-color: rgba(99, 102, 241, 0.12);
  border: 1px solid rgba(99, 102, 241, 0.2);
  color: var(--accent-primary);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
  user-select: none;
}

.tag-remove {
  cursor: pointer;
  color: var(--accent-primary);
  opacity: 0.7;
  font-weight: bold;
  transition: opacity 0.15s;
}

.tag-remove:hover {
  opacity: 1;
  color: var(--accent-danger);
}

.chevron-icon {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  cursor: pointer;
  color: var(--text-muted);
  font-size: 9px;
  user-select: none;
  pointer-events: none;
}

.options-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin-top: 4px;
  max-height: 220px;
  overflow-y: auto;
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  z-index: 1000;
  box-shadow: var(--shadow-lg);
  animation: slideDown 0.15s ease-out;
}

.option-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  font-size: 13px;
  color: var(--text-primary);
  cursor: pointer;
  transition: background-color 0.15s, color 0.15s;
}

.checkbox-indicator {
  width: 14px;
  height: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: bold;
  color: var(--accent-primary);
}

.option-item:hover, .option-item.is-highlighted {
  background-color: rgba(99, 102, 241, 0.15);
  color: var(--accent-primary);
}

.option-item.is-selected {
  background-color: rgba(99, 102, 241, 0.08);
  font-weight: 500;
}

.no-options {
  padding: 12px;
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
  font-style: italic;
}

.searchable-multiselect-container.is-disabled .input-tags-wrapper {
  background-color: var(--bg-secondary);
  border-color: var(--border-color);
  cursor: not-allowed;
}

.searchable-multiselect-container.is-disabled .tag-badge {
  background-color: var(--bg-secondary);
  border-color: var(--border-color);
  color: var(--text-secondary);
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Styles pour l'édition en ligne dans les tableaux */
.is-inline .input-tags-wrapper {
  background-color: transparent;
  border-color: transparent;
  padding: 2px 24px 2px 4px;
  min-height: 28px;
  border-radius: 3px;
  gap: 4px;
}

.is-inline .input-tags-wrapper:hover {
  background-color: var(--bg-secondary);
  border-color: var(--border-color);
}

.is-inline.is-open .input-tags-wrapper,
.is-inline .search-input:focus ~ .input-tags-wrapper {
  background-color: var(--bg-card);
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.15);
}

.is-inline .search-input {
  height: 22px;
  font-size: 13px;
}

.is-inline .tag-badge {
  font-size: 11px;
  padding: 1px 4px;
  border-radius: 2px;
  gap: 2px;
}

.is-inline .chevron-icon {
  right: 8px;
}

.is-inline .options-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin-top: 6px;
  max-height: 200px;
  background-color: var(--bg-card);
  border: 1.5px solid var(--accent-primary);
  border-radius: 6px;
  z-index: 9999 !important;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2);
  padding: 4px;
}

.is-inline .option-item {
  border-radius: 4px;
  margin-bottom: 2px;
  padding: 6px 10px;
}

.is-inline .option-item:last-child {
  margin-bottom: 0;
}
</style>
