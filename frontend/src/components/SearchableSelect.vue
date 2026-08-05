<template>
  <div class="searchable-select-container" :class="{ 'is-inline': inline }" ref="containerRef">
    <div class="input-wrapper">
      <input
        v-if="!disabled"
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
      <span v-else class="disabled-text">
        {{ searchQuery || 'Aucun' }}
      </span>

      <span v-if="modelValue !== null && modelValue !== '' && !disabled" class="clear-btn" @click.stop="clearSelection">
        ×
      </span>
      <span v-if="!disabled" class="chevron-icon" @click.stop="toggleDropdown">
        ▼
      </span>
    </div>

    <div v-if="isOpen && !disabled" class="options-dropdown glass-morphism" @scroll="onScroll" ref="dropdownRef">
      <div v-if="filteredOptions.length === 0" class="no-options">
        Aucun résultat trouvé
      </div>
      <div
        v-else
        class="virtual-scroller-inner"
        :style="{ height: `${filteredOptions.length * itemHeight}px` }"
      >
        <div
          v-for="option in visibleOptions"
          :key="option.value"
          class="option-item"
          :style="{ transform: `translateY(${option.index * itemHeight}px)` }"
          :class="{
            'is-selected': option.value === modelValue,
            'is-highlighted': option.index === highlightedIndex
          }"
          @mousedown.prevent="selectOption(option)"
        >
          {{ option.label }}
        </div>
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
const dropdownRef = ref<HTMLElement | null>(null);

// Virtual scrolling variables
const itemHeight = 32; // Fixed height per option
const scrollTop = ref(0);

function onScroll(e: Event) {
  scrollTop.value = (e.target as HTMLElement).scrollTop;
}

const visibleOptions = computed(() => {
  const start = Math.max(0, Math.floor(scrollTop.value / itemHeight) - 2);
  const end = Math.min(filteredOptions.value.length, start + Math.ceil(220 / itemHeight) + 4);

  return filteredOptions.value.slice(start, end).map((opt, i) => ({
    ...opt,
    index: start + i
  }));
});

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
    scrollTop.value = 0;
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

  // Auto-scroll pour garder l'élément en surbrillance visible
  if (dropdownRef.value) {
    const el = dropdownRef.value;
    const top = highlightedIndex.value * itemHeight;
    const bottom = top + itemHeight;
    if (top < el.scrollTop) {
      el.scrollTop = top;
    } else if (bottom > el.scrollTop + el.clientHeight) {
      el.scrollTop = bottom - el.clientHeight;
    }
  }
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

.disabled-text {
  padding: 4px 8px;
  color: var(--text-primary);
  font-size: 13px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.disabled-text:empty::after,
.disabled-text:contains('Aucun') {
  color: var(--text-muted);
  font-style: italic;
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
  border-radius: var(--radius-md);
  z-index: 1000;
  box-shadow: var(--shadow-lg);
  animation: slideDown 0.15s ease-out;
}

.virtual-scroller-inner {
  position: relative;
  width: 100%;
}

.option-item {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 32px;
  box-sizing: border-box;
  padding: 0 12px;
  line-height: 32px;
  font-size: 13px;
  color: var(--text-primary);
  cursor: pointer;
  transition: background-color 0.15s, color 0.15s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.option-item:hover, .option-item.is-highlighted {
  background-color: rgba(99, 102, 241, 0.15);
  color: var(--accent-primary);
}

.option-item.is-selected {
  background-color: var(--accent-primary);
  color: var(--bg-card);
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
.is-inline .input-wrapper {
  min-width: 0;
}

.is-inline .form-input {
  background-color: transparent;
  border-color: transparent;
  padding: 4px 8px;
  height: 28px;
  font-size: 13px;
  border-radius: var(--radius-sm);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  border-radius: var(--radius-lg);
  z-index: 9999 !important; /* Force le dropdown au-dessus du tableau */
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2); /* Ombre extra forte */
  padding: 4px;
}

.is-inline .option-item {
  border-radius: var(--radius-md);
  margin-bottom: 0;
  padding: 0 10px;
}

.is-inline .option-item:last-child {
  margin-bottom: 0;
}
</style>
