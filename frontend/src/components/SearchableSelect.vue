<template>
  <div class="searchable-select-container" :class="{ 'is-inline': inline }" ref="containerRef">
    <div class="input-wrapper">
      <input
        type="text"
        class="form-input searchable-select-input"
        :class="{ 'has-value': modelValue !== null && modelValue !== '' }"
        :placeholder="placeholder || '-- Choisir --'"
        :value="searchQuery"
        :disabled="disabled"
        @focus="handleFocus"
        @input="handleInput"
        @keydown.down.prevent="navigateOptions(1)"
        @keydown.up.prevent="navigateOptions(-1)"
        @keydown.enter.prevent="selectHighlighted"
        @keydown.escape.prevent="closeDropdown"
      />
      <span v-if="modelValue !== null && modelValue !== '' && !disabled" class="clear-btn" @click.stop="clearSelection">
        ×
      </span>
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
          'is-selected': option.value === modelValue,
          'is-highlighted': index === highlightedIndex
        }"
        @mousedown.prevent="selectOption(option)"
      >
        {{ option.label }}
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
  modelValue: any;
  options: Option[];
  disabled?: boolean;
  placeholder?: string;
  required?: boolean;
  inline?: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: any): void;
  (e: 'change', value: any): void;
}>();

const isOpen = ref(false);
const searchQuery = ref('');
const highlightedIndex = ref(-1);
const containerRef = ref<HTMLElement | null>(null);

// Trouver l'option courante
const selectedOption = computed(() => {
  return props.options.find(opt => opt.value === props.modelValue) || null;
});

// Mettre à jour la recherche quand la valeur change
watch(
  () => props.modelValue,
  () => {
    if (selectedOption.value) {
      searchQuery.value = selectedOption.value.label;
    } else {
      searchQuery.value = '';
    }
  },
  { immediate: true }
);

// Mettre à jour la recherche quand les options se chargent
watch(
  () => props.options,
  () => {
    if (selectedOption.value) {
      searchQuery.value = selectedOption.value.label;
    }
  },
  { deep: true }
);

// Filtrage des options
const filteredOptions = computed(() => {
  if (!isOpen.value) return props.options;
  // Si l'utilisateur n'a pas tapé, ou si la recherche correspond exactement à l'option sélectionnée, montrer toutes les options
  if (!searchQuery.value || (selectedOption.value && searchQuery.value === selectedOption.value.label)) {
    return props.options;
  }
  const query = searchQuery.value.toLowerCase();
  return props.options.filter(opt =>
    opt.label.toLowerCase().includes(query)
  );
});

// Réinitialiser l'index en surbrillance lors du filtrage
watch(filteredOptions, () => {
  highlightedIndex.value = 0;
});

function handleFocus() {
  if (props.disabled) return;
  isOpen.value = true;
  // Sélectionner tout le texte pour faciliter la saisie
  searchQuery.value = '';
  highlightedIndex.value = 0;
}

function handleInput(e: Event) {
  const target = e.target as HTMLInputElement;
  searchQuery.value = target.value;
  isOpen.value = true;
}

function toggleDropdown() {
  if (props.disabled) return;
  if (isOpen.value) {
    closeDropdown();
  } else {
    isOpen.value = true;
    searchQuery.value = '';
  }
}

function closeDropdown() {
  isOpen.value = false;
  // Restaurer le libellé si aucune option n'a été validée
  if (selectedOption.value) {
    searchQuery.value = selectedOption.value.label;
  } else {
    searchQuery.value = '';
  }
}

function selectOption(option: Option) {
  emit('update:modelValue', option.value);
  emit('change', option.value);
  searchQuery.value = option.label;
  isOpen.value = false;
}

function clearSelection() {
  if (props.disabled) return;
  emit('update:modelValue', null);
  emit('change', null);
  searchQuery.value = '';
  isOpen.value = false;
}

function selectHighlighted() {
  if (!isOpen.value) {
    isOpen.value = true;
    return;
  }
  if (filteredOptions.value.length > 0 && highlightedIndex.value >= 0) {
    selectOption(filteredOptions.value[highlightedIndex.value]);
  }
}

function navigateOptions(direction: number) {
  if (!isOpen.value) {
    isOpen.value = true;
    return;
  }
  const count = filteredOptions.value.length;
  if (count === 0) return;

  highlightedIndex.value = (highlightedIndex.value + direction + count) % count;
}

// Clic à l'extérieur pour fermer
function handleClickOutside(e: MouseEvent) {
  if (containerRef.value && !containerRef.value.contains(e.target as Node)) {
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
.searchable-select-container {
  position: relative;
  width: 100%;
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.searchable-select-input {
  width: 100%;
  padding-right: 45px !important;
}

.clear-btn {
  position: absolute;
  right: 28px;
  cursor: pointer;
  color: var(--text-muted);
  font-size: 16px;
  font-weight: bold;
  user-select: none;
  transition: color 0.15s;
}

.clear-btn:hover {
  color: var(--accent-danger);
}

.chevron-icon {
  position: absolute;
  right: 12px;
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
  padding: 8px 12px;
  font-size: 13px;
  color: var(--text-primary);
  cursor: pointer;
  transition: background-color 0.15s, color 0.15s;
}

.option-item:hover, .option-item.is-highlighted {
  background-color: rgba(99, 102, 241, 0.15);
  color: var(--accent-primary);
}

.option-item.is-selected {
  background-color: var(--accent-primary);
  color: #ffffff;
}

.no-options {
  padding: 12px;
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
  font-style: italic;
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
.is-inline .form-input {
  background-color: transparent;
  border-color: transparent;
  padding: 4px 8px;
  height: 28px;
  font-size: 13px;
  border-radius: 3px;
}

.is-inline .form-input:hover {
  background-color: var(--bg-secondary);
  border-color: var(--border-color);
}

.is-inline .form-input:focus {
  background-color: var(--bg-card);
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.15);
}

.is-inline .chevron-icon {
  right: 8px;
}

.is-inline .clear-btn {
  right: 20px;
}

.is-inline .searchable-select-input {
  padding-right: 32px !important;
}

.is-inline .options-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin-top: 6px;
  max-height: 200px;
  background-color: var(--bg-card);
  border: 1.5px solid var(--accent-primary); /* Bordure d'accent violette prononcée */
  border-radius: 6px;
  z-index: 9999 !important; /* Force le dropdown au-dessus du tableau */
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2); /* Ombre extra forte */
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
