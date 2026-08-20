<template>
  <!-- click.stop (sauf si disabled) : voir SearchableSelect.vue — un clic sur une option/tag
       (pas de vrai <input>/<select>) remonterait sinon jusqu'à la ligne de GenericList.vue et
       déclencherait une resélection/rechargement qui écrase l'édition locale avant son envoi au
       backend. -->
  <div class="searchable-multiselect-container" :class="{ 'is-inline': inline, 'is-disabled': disabled, 'is-open': isOpen }" ref="containerRef" @click="!disabled && $event.stopPropagation()">
    <div class="input-tags-wrapper" @click="focusInput">
      <div v-for="val in selectedOptions" :key="val.value" class="tag-badge" :class="{ 'tag-badge-highlight': isHighlighted(val.value) }">
        <span class="tag-label">{{ val.label }}</span>
        <!-- Sélecteur de sous-mode par item (capacité optionnelle itemModeOptions, voir script) :
             select natif plutôt qu'un dropdown maison — pas de positionnement Teleport/Floating UI
             à gérer, comportement natif clavier/accessibilité gratuit. @click.stop seul (jamais
             .prevent, qui empêcherait l'ouverture native du select) : suffit à ne pas remonter vers
             input-tags-wrapper (@click="focusInput" ouvrirait le dropdown principal en plus). -->
        <select
          v-if="!disabled && itemModeOptions"
          class="tag-mode-select"
          :value="val.mode"
          @click.stop
          @mousedown.stop
          @change="setItemMode(val.value, ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="modeOpt in itemModeOptions" :key="modeOpt.value" :value="modeOpt.value">{{ modeOpt.label }}</option>
        </select>
        <!-- mousedown.prevent (pas click) : voir SearchableSelect.vue, même piège avec le
             focusout de ligne de GenericList.vue qui flush avant que le clic ne s'exécute. -->
        <span v-if="!disabled" class="tag-remove" @mousedown.prevent.stop="removeOption(val.value)">×</span>
      </div>

      <input
        v-if="!disabled"
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

      <span v-if="selectedOptions.length === 0 && disabled" class="empty-placeholder">
        Aucun
      </span>

      <span v-if="!disabled" class="chevron-icon" @click.stop="toggleDropdown">
        ▼
      </span>
    </div>

    <Teleport to="body">
      <div v-if="isOpen && !disabled" class="options-dropdown glass-morphism" :style="dropdownStyle" @scroll="onScroll" ref="dropdownRef">
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
              'is-selected': isSelected(option.value),
              'is-highlighted': option.index === highlightedIndex
            }"
            @mousedown.prevent="toggleOption(option)"
          >
            <span class="checkbox-indicator">{{ isSelected(option.value) ? '✓' : '' }}</span>
            <span class="option-label">{{ option.label }}</span>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { fetchGenericList } from '../services/api';
import { useFloatingDropdown } from '../composables/useFloatingDropdown';

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
  // Signale (fond rouge) une valeur sélectionnée jugée insuffisamment précisée par l'appelant
  // (ex: Fiche T — ressource d'un cours composé absente de tous ses enfants). Optionnelle,
  // rétrocompatible : aucun effet si omise.
  highlightValues?: any[];
  // Capacité standard du widget many2many, symétrique de SearchableSelect.vue (many2one) — voir
  // architecture.md §15.R : options recherchées côté serveur, filtrées par un champ frère, plutôt
  // que préchargées en entier. `options`, si fourni, sert alors uniquement de repli pour garder
  // visibles les libellés des valeurs déjà sélectionnées sorties du filtre courant.
  dynamicSource?: { resource: string; filterQueryParam: string; filterValue: any };
  // Capacité optionnelle : quand fournie, chaque tag sélectionné porte un petit select natif pour
  // choisir un "sous-mode" propre à cet item (ex: wizard de composition de cours — une classe
  // ciblée peut être "classe entière"/"dédoublement F-G"/"dédoublement Alpha"). Change la forme de
  // `modelValue` de `id[]` à `{id, mode}[]` — voir currentEntries/emitEntries ci-dessous. Absente :
  // comportement strictement inchangé (immense majorité des usages actuels de ce composant).
  itemModeOptions?: { value: string; label: string }[];
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
const dropdownRef = ref<HTMLElement | null>(null);

// Voir SearchableSelect.vue/useFloatingDropdown.ts — même correctif, même raison (dropdown
// téléporté hors du flux + positionné via Floating UI, pour échapper à l'overflow de tout ancêtre
// scrollable).
const { dropdownStyle } = useFloatingDropdown(containerRef, dropdownRef, isOpen);

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

interface TaggedValue { id: any; mode: string }

// Normalise modelValue en tableau {id, mode} interne, quelle que soit la forme reçue :
// - itemModeOptions fourni : modelValue est {id, mode}[] (ou une valeur brute pour un item pas
//   encore doté d'un mode explicite — repli sur la première option de mode).
// - itemModeOptions absent (immense majorité des usages) : modelValue reste id[] comme toujours,
//   mode vaut '' et n'est jamais lu/émis.
const currentEntries = computed<TaggedValue[]>(() => {
  if (!props.modelValue) return [];
  const raw = Array.isArray(props.modelValue) ? props.modelValue : [props.modelValue];
  if (!props.itemModeOptions) return raw.map((v: any) => ({ id: v, mode: '' }));
  const defaultMode = props.itemModeOptions[0]?.value ?? '';
  return raw.map((v: any) => (v !== null && typeof v === 'object' && 'id' in v)
    ? { id: v.id, mode: v.mode ?? defaultMode }
    : { id: v, mode: defaultMode });
});

// Vue plate (juste les ids) pour tout ce qui n'a pas besoin du mode : isSelected, comparaisons,
// fallback d'options — inchangé par rapport à l'ancien currentValues pour ces usages.
const currentValues = computed(() => currentEntries.value.map(e => e.id));

// Émission dans la forme attendue par l'appelant selon itemModeOptions — seul point d'écriture de
// modelValue de tout le composant, pour ne jamais désynchroniser les deux formes possibles.
function emitEntries(entries: TaggedValue[]) {
  const value = props.itemModeOptions ? entries.map(e => ({ id: e.id, mode: e.mode })) : entries.map(e => e.id);
  emit('update:modelValue', value);
  emit('change', value);
}

function setItemMode(id: any, mode: string) {
  emitEntries(currentEntries.value.map(e => (String(e.id) === String(id) ? { ...e, mode } : e)));
}

const dynamicOptions = ref<Option[]>([]);
let dynamicDebounce: ReturnType<typeof setTimeout> | null = null;

function currentValuesFallback(): Option[] {
  return currentValues.value
    .map(val => props.options.find(opt => String(opt.value) === String(val)))
    .filter((opt): opt is Option => !!opt);
}

async function refreshDynamicOptions() {
  if (!props.dynamicSource) return;
  const { resource, filterQueryParam, filterValue } = props.dynamicSource;
  if (!resource || filterValue === undefined || filterValue === null || filterValue === '') {
    dynamicOptions.value = currentValuesFallback();
    return;
  }
  try {
    const res = await fetchGenericList(resource, 0, 50, undefined, { [filterQueryParam]: filterValue });
    const fetched: Option[] = (res.items || []).map((item: any) => ({
      value: item.id,
      label: item.display_name || item.name || item.code || String(item.id)
    }));
    for (const fb of currentValuesFallback()) {
      if (!fetched.some(o => String(o.value) === String(fb.value))) fetched.push(fb);
    }
    dynamicOptions.value = fetched;
  } catch (e) {
    console.error(`Échec du chargement filtré de ${resource}`, e);
    dynamicOptions.value = currentValuesFallback();
  }
}

watch(() => props.dynamicSource?.filterValue, () => {
  if (!props.dynamicSource) return;
  if (dynamicDebounce) clearTimeout(dynamicDebounce);
  dynamicDebounce = setTimeout(refreshDynamicOptions, 300);
});

onMounted(() => {
  if (props.dynamicSource) refreshDynamicOptions();
});

const activeOptions = computed(() => props.dynamicSource ? dynamicOptions.value : props.options);

// Trouver les options sélectionnées — porte aussi `mode` (chaîne vide si itemModeOptions absent),
// lu par le select de sous-mode dans le template.
const selectedOptions = computed(() => {
  return currentEntries.value
    .map(entry => {
      const opt = activeOptions.value.find(o => String(o.value) === String(entry.id));
      return opt ? { ...opt, mode: entry.mode } : null;
    })
    .filter((opt): opt is Option & { mode: string } => !!opt);
});

// Vérifier si une option est sélectionnée
function isSelected(value: any) {
  return currentValues.value.some(val => String(val) === String(value));
}

function isHighlighted(value: any) {
  return (props.highlightValues || []).some(val => String(val) === String(value));
}

// Filtrer les options par recherche
const filteredOptions = computed(() => {
  if (!searchQuery.value) return activeOptions.value;
  const query = searchQuery.value.toLowerCase();
  return activeOptions.value.filter(opt =>
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
  const entries = [...currentEntries.value];
  const idx = entries.findIndex(e => String(e.id) === String(option.value));
  if (idx > -1) {
    entries.splice(idx, 1);
  } else {
    entries.push({ id: option.value, mode: props.itemModeOptions?.[0]?.value ?? '' });
  }
  emitEntries(entries);
  searchQuery.value = ''; // Vider la recherche pour enchaîner
  focusInput();
}

function removeOption(value: any) {
  emitEntries(currentEntries.value.filter(e => String(e.id) !== String(value)));
}

function selectHighlighted() {
  if (highlightedIndex.value >= 0 && highlightedIndex.value < filteredOptions.value.length) {
    toggleOption(filteredOptions.value[highlightedIndex.value]);
  }
}

function handleBackspace() {
  if (!searchQuery.value && currentEntries.value.length > 0) {
    const entries = [...currentEntries.value];
    entries.pop();
    emitEntries(entries);
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

  // Auto-scroll
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

// Voir SearchableSelect.vue::handleClickOutside — même raison (dropdown téléporté hors de containerRef).
function handleClickOutside(event: MouseEvent) {
  const target = event.target as Node;
  const insideContainer = containerRef.value?.contains(target);
  const insideDropdown = dropdownRef.value?.contains(target);
  if (!insideContainer && !insideDropdown) {
    closeDropdown();
  }
}

// Phase de CAPTURE (3e argument `true`) — voir SearchableSelect.vue::handleClickOutside pour le
// raisonnement complet (un widget voisin qui stoppe la propagation de ses propres clics en phase
// bubble ne doit jamais empêcher CE dropdown de détecter un clic extérieur).
onMounted(() => {
  document.addEventListener('click', handleClickOutside, true);
});

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside, true);
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
  border-radius: var(--radius-lg);
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
  border-radius: var(--radius-md);
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

.tag-mode-select {
  font-size: 11px;
  font-family: var(--font-sans);
  color: var(--accent-primary);
  background-color: rgba(99, 102, 241, 0.08);
  border: 1px solid rgba(99, 102, 241, 0.25);
  border-radius: var(--radius-sm);
  padding: 0 2px;
  max-width: 120px;
  cursor: pointer;
}

.tag-badge-highlight {
  background-color: rgba(239, 68, 68, 0.15);
  border-color: rgba(239, 68, 68, 0.4);
  color: var(--accent-danger, #dc2626);
}

.tag-badge-highlight .tag-remove {
  color: var(--accent-danger, #dc2626);
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
}

.options-dropdown {
  /* position/top/left/width : voir SearchableSelect.vue (même composant de positionnement) */
  max-height: 220px;
  overflow-y: auto;
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  z-index: 2000;
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
  display: flex;
  align-items: center;
  gap: 8px;
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
  background-color: transparent;
  border-color: transparent;
  cursor: default;
  padding: 0;
  min-height: auto;
}

.searchable-multiselect-container.is-disabled .tag-badge {
  background-color: rgba(99, 102, 241, 0.08);
  border-color: rgba(99, 102, 241, 0.2);
  color: var(--text-primary);
}

.empty-placeholder {
  color: var(--text-muted);
  font-style: italic;
  font-size: 13px;
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
  border-radius: var(--radius-sm);
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
  border-radius: var(--radius-sm);
  gap: 2px;
}

.is-inline .chevron-icon {
  right: 8px;
}

.is-inline .options-dropdown {
  /* position/top/left/width : voir .options-dropdown ci-dessus */
  max-height: 200px;
  background-color: var(--bg-card);
  border: 1.5px solid var(--accent-primary);
  border-radius: var(--radius-lg);
  z-index: 9999 !important;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2);
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
