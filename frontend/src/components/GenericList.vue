<template>
  <div class="generic-list-container">
    <!-- Barre d'outils supérieure -->
    <div class="list-toolbar">
      <div class="toolbar-left">
        <h3 class="toolbar-title">{{ title }}</h3>
        <span class="toolbar-badge">{{ filteredItems.length }} éléments</span>
      </div>
      <div class="toolbar-right">
        <!-- Sélecteur de colonnes -->
        <div class="column-selector-wrapper" ref="dropdownRef">
          <button class="btn btn-secondary btn-sm" @click="toggleDropdown">
            <svg xmlns="http://www.w3.org/2000/svg" class="icon-selector" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
            </svg>
            Colonnes
          </button>
          
          <div v-if="showDropdown" class="column-dropdown glass-morphism">
            <div class="dropdown-header">Affichage des colonnes</div>
            <div class="dropdown-list">
              <label v-for="col in internalColumns" :key="col.key" class="dropdown-item">
                <input 
                  type="checkbox" 
                  :checked="col.visible" 
                  @change="toggleColumnVisibility(col.key)"
                />
                <span>{{ col.label }}</span>
              </label>
            </div>
          </div>
        </div>

        <!-- Bouton Ajouter -->
        <button class="btn btn-primary btn-sm" @click="$emit('add')">
          <svg xmlns="http://www.w3.org/2000/svg" class="icon-add" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          Ajouter
        </button>
      </div>
    </div>

    <!-- Conteneur de table avec scroll -->
    <div class="table-wrapper">
      <table class="premium-table">
        <thead>
          <tr class="header-tr">
            <th 
              v-for="(col, index) in visibleColumns" 
              :key="col.key"
              :style="{ width: col.width ? col.width + 'px' : 'auto' }"
              class="header-th"
              draggable="true"
              @dragstart="onDragStart($event, index)"
              @dragover.prevent="onDragOver($event, index)"
              @drop="onDrop($event, index)"
            >
              <!-- En-tête cliquable pour le tri -->
              <div class="th-content" @click="toggleSort(col.key)">
                <span class="th-label">{{ col.label }}</span>
                <span class="sort-indicator" v-if="sortBy === col.key">
                  {{ sortDesc ? '▼' : '▲' }}
                </span>
                <span class="sort-indicator-placeholder" v-else>↕</span>
              </div>
              
              <!-- Poignée de redimensionnement manuel -->
              <div 
                class="resize-handle" 
                @mousedown.stop.prevent="startResize($event, col.key)"
              ></div>
            </th>
            <th class="header-th actions-th">Actions</th>
          </tr>

          <!-- Ligne de filtrage / recherche spécifique par colonne -->
          <tr class="filter-tr">
            <td v-for="col in visibleColumns" :key="'filter-' + col.key" class="filter-td">
              <!-- Si c'est un champ couleur, on propose le composant swatch -->
              <color-swatch-picker
                v-if="col.key === 'color' || getFieldDef(col.key)?.type === 'color'"
                :model-value="filters[col.key] || ''"
                @change="filters[col.key] = $event"
              />
              <input 
                v-else
                type="text" 
                v-model="filters[col.key]" 
                :placeholder="'Filtrer...'" 
                class="filter-input"
              />
            </td>
            <td class="filter-td actions-td"></td>
          </tr>
        </thead>
        
        <tbody>
          <tr v-if="paginatedItems.length === 0" class="empty-tr">
            <td :colspan="visibleColumns.length + 1" class="empty-td">
              Aucune donnée à afficher.
            </td>
          </tr>
          <tr 
            v-for="item in paginatedItems" 
            :key="item.id" 
            class="body-tr"
          >
            <td 
              v-for="col in visibleColumns" 
              :key="col.key"
              class="body-td"
            >
              <!-- Formatage personnalisé des valeurs (Édition en ligne Airtable) -->
              <slot :name="'col-' + col.key" :item="item">
                <!-- ID est immuable -->
                <span v-if="col.key === 'id'" class="immutable-id">
                  {{ item[col.key] }}
                </span>

                <!-- Booléen (Switch / Checkbox en ligne) -->
                <div v-else-if="getFieldDef(col.key)?.type === 'boolean' || typeof item[col.key] === 'boolean'" class="inline-checkbox-wrapper">
                  <label class="inline-switch">
                    <input 
                      type="checkbox" 
                      :checked="!!item[col.key]" 
                      @change="updateInline(item, col.key, $event.target.checked)"
                    />
                    <span class="inline-slider inline-round"></span>
                  </label>
                </div>

                <!-- Couleur (Sélecteur premium en ligne avec palette finie et input hex) -->
                <!-- Couleur : composant standard vue3-swatches -->
                <div v-else-if="col.key === 'color' || getFieldDef(col.key)?.type === 'color'" class="inline-color-swatch-wrapper">
                  <color-swatch-picker
                    :model-value="item[col.key] || '#3B82F6'"
                    @change="updateInline(item, col.key, $event)"
                  />
                </div>

                <!-- Menu Déroulant Select (ex: école principale) -->
                <select 
                  v-else-if="getFieldDef(col.key)?.type === 'select'"
                  :value="item[col.key]" 
                  @change="updateInline(item, col.key, $event.target.value ? Number($event.target.value) : null)"
                  class="inline-select"
                >
                  <option :value="null">-- Choisir --</option>
                  <option 
                    v-for="opt in getFieldDef(col.key)?.options" 
                    :key="opt.value" 
                    :value="opt.value"
                  >
                    {{ opt.label }}
                  </option>
                </select>

                <!-- Nombre -->
                <input 
                  v-else-if="getFieldDef(col.key)?.type === 'number' || typeof item[col.key] === 'number'"
                  type="number" 
                  :value="item[col.key]" 
                  :min="getFieldDef(col.key)?.min"
                  :max="getFieldDef(col.key)?.max"
                  :step="getFieldDef(col.key)?.step || '1'"
                  @change="updateInline(item, col.key, $event.target.value !== '' ? Number($event.target.value) : null)"
                  class="inline-input inline-number"
                />

                <!-- Texte standard (ex: nom, code) -->
                <input 
                  v-else
                  type="text" 
                  :value="item[col.key] || ''" 
                  @change="updateInline(item, col.key, $event.target.value)"
                  class="inline-input"
                />
              </slot>
            </td>
            <td class="body-td actions-td">
              <div class="actions-group">
                <button class="btn-action btn-edit" @click="$emit('edit', item)">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                </button>
                <button class="btn-action btn-delete" @click="$emit('delete', item)">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Système de Pagination -->
    <div class="list-pagination">
      <div class="pagination-left">
        <label class="per-page-selector">
          Afficher
          <select v-model="perPage" class="select-custom">
            <option :value="10">10</option>
            <option :value="20">20</option>
            <option :value="30">30</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
          </select>
          par page
        </label>
      </div>
      <div class="pagination-right">
        <span class="pagination-info">
          Page {{ currentPage }} sur {{ totalPages }}
        </span>
        <div class="pagination-buttons">
          <button 
            class="btn btn-secondary btn-icon-only" 
            :disabled="currentPage === 1"
            @click="currentPage = 1"
          >
            «
          </button>
          <button 
            class="btn btn-secondary btn-icon-only" 
            :disabled="currentPage === 1"
            @click="currentPage--"
          >
            ‹
          </button>
          <button 
            class="btn btn-secondary btn-icon-only" 
            :disabled="currentPage === totalPages || totalPages === 0"
            @click="currentPage++"
          >
            ›
          </button>
          <button 
            class="btn btn-secondary btn-icon-only" 
            :disabled="currentPage === totalPages || totalPages === 0"
            @click="currentPage = totalPages"
          >
            »
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import ColorSwatchPicker from './ColorSwatchPicker.vue';

interface ColumnDef {
  key: string;
  label: string;
  width?: number;
  visible?: boolean;
}

interface FormField {
  key: string;
  label: string;
  type: 'text' | 'number' | 'boolean' | 'date' | 'select' | 'color';
  required?: boolean;
  placeholder?: string;
  min?: number;
  max?: number;
  step?: string;
  options?: Array<{ value: any; label: string }>;
}

const props = defineProps<{
  title: string;
  columns: ColumnDef[];
  items: any[];
  fields?: FormField[];
}>();

const emit = defineEmits<{
  (e: 'add'): void;
  (e: 'edit', item: any): void;
  (e: 'delete', item: any): void;
  (e: 'update-item', item: any): void;
}>();

function getFieldDef(key: string): FormField | undefined {
  return props.fields?.find(f => f.key === key);
}

function updateInline(item: any, key: string, value: any) {
  if (item[key] === value) return;
  const updatedItem = { ...item };
  updatedItem[key] = value;
  emit('update-item', updatedItem);
}

// Palette unifiée de 30 couleurs premium
const colorPalette = [
  '#F87171', '#F97316', '#F59E0B', '#EAB308', '#84CC16', '#22C55E', '#10B981', '#14B8A6', '#06B6D4', '#0EA5E9',
  '#3B82F6', '#6366F1', '#8B5CF6', '#A855F7', '#D946EF', '#EC4899', '#F43F5E', '#6B7280', '#4F46E5', '#059669',
  '#DC2626', '#D97706', '#0891B2', '#2563EB', '#7C3AED', '#DB2777', '#0284C7', '#4B5563', '#9CA3AF', '#374151'
];



function getContrastYIQ(hexcolor: string) {
  if (!hexcolor || hexcolor.length < 6) return '#ffffff';
  const hex = hexcolor.replace('#', '');
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  const yiq = ((r * 299) + (g * 587) + (b * 114)) / 1000;
  return (yiq >= 128) ? '#000000' : '#ffffff';
}

// Gestion des colonnes internes (pour réordonner/redimensionner localement)
const internalColumns = ref<ColumnDef[]>([]);

watch(() => props.columns, (newVal) => {
  internalColumns.value = newVal.map(c => ({
    ...c,
    width: c.width || 150,
    visible: c.visible !== false
  }));
}, { immediate: true });

const visibleColumns = computed(() => {
  return internalColumns.value.filter(c => c.visible);
});

// Dropdown colonnes
const showDropdown = ref(false);
const dropdownRef = ref<HTMLElement | null>(null);

function toggleDropdown() {
  showDropdown.value = !showDropdown.value;
}

function toggleColumnVisibility(key: string) {
  const col = internalColumns.value.find(c => c.key === key);
  if (col) {
    col.visible = !col.visible;
  }
}

// Click outside pour fermer le dropdown
function handleClickOutside(event: MouseEvent) {
  if (dropdownRef.value && !dropdownRef.value.contains(event.target as Node)) {
    showDropdown.value = false;
  }
}

onMounted(() => {
  document.addEventListener('mousedown', handleClickOutside);
});

onUnmounted(() => {
  document.removeEventListener('mousedown', handleClickOutside);
});

// Pagination
const currentPage = ref(1);
const perPage = ref(30);

// Filtres
const filters = ref<Record<string, string>>({});
watch(() => props.columns, () => {
  filters.value = {};
  props.columns.forEach(c => {
    filters.value[c.key] = '';
  });
}, { immediate: true });

// Tri
const sortBy = ref<string | null>(null);
const sortDesc = ref(false);

function toggleSort(key: string) {
  if (sortBy.value === key) {
    if (!sortDesc.value) {
      sortDesc.value = true;
    } else {
      sortBy.value = null;
      sortDesc.value = false;
    }
  } else {
    sortBy.value = key;
    sortDesc.value = false;
  }
}

// Filtrage et Tri
const filteredItems = computed(() => {
  let result = [...props.items];

  // 1. Filtrage
  Object.keys(filters.value).forEach(key => {
    const val = filters.value[key];
    if (val) {
      const lowerVal = val.toLowerCase();
      result = result.filter(item => {
        const itemVal = item[key];
        if (itemVal === undefined || itemVal === null) return false;
        return String(itemVal).toLowerCase().includes(lowerVal);
      });
    }
  });

  // 2. Tri
  if (sortBy.value) {
    const key = sortBy.value;
    result.sort((a, b) => {
      let valA = a[key];
      let valB = b[key];

      if (valA === undefined || valA === null) return 1;
      if (valB === undefined || valB === null) return -1;

      if (typeof valA === 'string') {
        return sortDesc.value 
          ? valB.localeCompare(valA)
          : valA.localeCompare(valB);
      } else {
        return sortDesc.value 
          ? (valB - valA)
          : (valA - valB);
      }
    });
  }

  return result;
});

// Pagination
const totalPages = computed(() => {
  return Math.ceil(filteredItems.value.length / perPage.value);
});

const paginatedItems = computed(() => {
  const start = (currentPage.value - 1) * perPage.value;
  return filteredItems.value.slice(start, start + perPage.value);
});

// Reset page on filter/limit changes
watch([filters, perPage], () => {
  currentPage.value = 1;
}, { deep: true });

// Redimensionnement de colonnes
let startX = 0;
let startWidth = 0;
let resizingKey: string | null = null;

function startResize(event: MouseEvent, key: string) {
  startX = event.clientX;
  resizingKey = key;
  const col = internalColumns.value.find(c => c.key === key);
  if (col) {
    startWidth = col.width || 150;
  }
  document.addEventListener('mousemove', onResize);
  document.addEventListener('mouseup', stopResize);
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
}

function onResize(event: MouseEvent) {
  if (!resizingKey) return;
  const diff = event.clientX - startX;
  const col = internalColumns.value.find(c => c.key === resizingKey);
  if (col) {
    col.width = Math.max(50, startWidth + diff);
  }
}

function stopResize() {
  document.removeEventListener('mousemove', onResize);
  document.removeEventListener('mouseup', stopResize);
  resizingKey = null;
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
}

// Drag & Drop de colonnes (Réordonnancement)
let draggedIdx: number | null = null;

function onDragStart(event: DragEvent, index: number) {
  draggedIdx = index;
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move';
  }
}

function onDragOver(event: DragEvent, index: number) {
  event.preventDefault();
}

function onDrop(event: DragEvent, index: number) {
  if (draggedIdx === null || draggedIdx === index) return;
  
  // Retrouver les colonnes réelles correspondantes
  const visibleCols = [...visibleColumns.value];
  const targetCol = visibleCols[index];
  const sourceCol = visibleCols[draggedIdx];
  
  // Repositionner dans le tableau internalColumns
  const sourceIdx = internalColumns.value.findIndex(c => c.key === sourceCol.key);
  const targetIdx = internalColumns.value.findIndex(c => c.key === targetCol.key);
  
  if (sourceIdx !== -1 && targetIdx !== -1) {
    const col = internalColumns.value.splice(sourceIdx, 1)[0];
    internalColumns.value.splice(targetIdx, 0, col);
  }
  
  draggedIdx = null;
}
</script>

<style scoped>
.generic-list-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  background-color: rgba(17, 20, 26, 0.45);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  overflow: visible;
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(12px);
}

.list-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
  background-color: rgba(23, 28, 36, 0.5);
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar-title {
  font-size: 18px;
  font-weight: 700;
  color: #fff;
}

.toolbar-badge {
  background-color: rgba(99, 102, 241, 0.15);
  color: var(--accent-primary);
  border: 1px solid rgba(99, 102, 241, 0.25);
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 600;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.icon-selector, .icon-add {
  width: 16px;
  height: 16px;
}

/* Dropdown Colonnes */
.column-selector-wrapper {
  position: relative;
}

.column-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 220px;
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  box-shadow: var(--shadow-lg);
  z-index: 100;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  animation: fadeIn var(--transition-fast);
}

.dropdown-header {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--text-muted);
  letter-spacing: 0.5px;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 6px;
}

.dropdown-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 200px;
  overflow-y: auto;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-primary);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: background-color var(--transition-fast);
}

.dropdown-item:hover {
  background-color: rgba(255, 255, 255, 0.05);
}

.dropdown-item input[type="checkbox"] {
  accent-color: var(--accent-primary);
  width: 15px;
  height: 15px;
}

/* Table */
.table-wrapper {
  flex: 1;
  position: relative;
  overflow: visible;
}

.premium-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  table-layout: fixed;
}

.header-tr {
  background-color: rgba(23, 28, 36, 0.7);
  border-bottom: 2px solid var(--border-color);
}

.header-th {
  position: sticky;
  top: 0;
  background-color: rgba(23, 28, 36, 0.85);
  backdrop-filter: blur(8px);
  z-index: 10;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
  padding: 12px 16px;
  position: relative;
  user-select: none;
  border-right: 1px solid rgba(255, 255, 255, 0.03);
}

.th-content {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  transition: color var(--transition-fast);
}

.th-content:hover {
  color: #fff;
}

.th-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sort-indicator {
  color: var(--accent-primary);
  font-size: 10px;
}

.sort-indicator-placeholder {
  color: var(--text-muted);
  font-size: 10px;
  opacity: 0.3;
}

.resize-handle {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 5px;
  cursor: col-resize;
  background-color: transparent;
  transition: background-color var(--transition-fast);
}

.resize-handle:hover {
  background-color: rgba(99, 102, 241, 0.5);
}

/* Filtres */
.filter-tr {
  background-color: rgba(17, 20, 26, 0.6);
}

.filter-td {
  padding: 6px 12px;
  border-bottom: 1px solid var(--border-color);
  border-right: 1px solid rgba(255, 255, 255, 0.03);
}

.filter-input {
  width: 100%;
  background-color: rgba(10, 12, 16, 0.5);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 5px 10px;
  color: #fff;
  font-size: 12px;
  outline: none;
  font-family: var(--font-sans);
  transition: border-color var(--transition-fast);
}

.filter-input:focus {
  border-color: var(--accent-primary);
}

/* Body */
.body-tr {
  border-bottom: 1px solid var(--border-color);
  transition: background-color var(--transition-fast);
}

.body-tr:hover {
  background-color: rgba(255, 255, 255, 0.015);
}

.body-td {
  padding: 14px 16px;
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  border-right: 1px solid rgba(255, 255, 255, 0.02);
}

.empty-td {
  text-align: center;
  padding: 40px;
  color: var(--text-muted);
  font-size: 14px;
}

/* Actions */
.actions-th {
  width: 100px;
  text-align: center;
  position: sticky;
  right: 0;
  background-color: rgba(23, 28, 36, 0.85);
  z-index: 11;
  border-left: 1px solid var(--border-color);
}

.actions-td {
  width: 100px;
  text-align: center;
  position: sticky;
  right: 0;
  background-color: rgba(20, 26, 34, 0.95);
  backdrop-filter: blur(8px);
  z-index: 9;
  border-left: 1px solid var(--border-color);
}

.actions-group {
  display: flex;
  justify-content: center;
  gap: 8px;
}

.btn-action {
  background: transparent;
  border: none;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  transition: all var(--transition-fast);
}

.btn-action svg {
  width: 16px;
  height: 16px;
}

.btn-edit:hover {
  background-color: rgba(99, 102, 241, 0.15);
  color: var(--accent-primary);
}

.btn-delete:hover {
  background-color: rgba(239, 68, 68, 0.15);
  color: var(--accent-danger);
}

/* Badges */
.badge-boolean {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
}

.badge-true {
  background-color: rgba(16, 185, 129, 0.15);
  color: var(--accent-success);
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.badge-false {
  background-color: rgba(239, 68, 68, 0.15);
  color: var(--accent-danger);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

/* Pagination */
.list-pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  border-top: 1px solid var(--border-color);
  background-color: rgba(23, 28, 36, 0.5);
  font-size: 13px;
  color: var(--text-secondary);
}

.per-page-selector {
  display: flex;
  align-items: center;
  gap: 8px;
}

.select-custom {
  background-color: rgba(10, 12, 16, 0.6);
  border: 1px solid var(--border-color);
  color: #fff;
  padding: 4px 8px;
  border-radius: 6px;
  outline: none;
  cursor: pointer;
}

.pagination-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.pagination-buttons {
  display: flex;
  gap: 4px;
}

.btn-icon-only {
  width: 32px;
  height: 32px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
}

.btn-icon-only:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.glass-morphism {
  background: rgba(32, 38, 50, 0.85);
  backdrop-filter: blur(12px);
}

/* Styles Airtable-style pour l'édition en ligne */
.immutable-id {
  color: var(--text-muted);
  font-family: monospace;
  font-weight: 600;
  padding: 4px 8px;
}

.inline-input, .inline-select {
  width: 100%;
  background-color: transparent;
  border: 1px solid transparent;
  color: var(--text-primary);
  padding: 6px 10px;
  border-radius: 6px;
  outline: none;
  font-family: var(--font-sans);
  font-size: 13px;
  transition: all var(--transition-fast);
}

.inline-input:hover, .inline-select:hover {
  background-color: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.1);
}

.inline-input:focus, .inline-select:focus {
  background-color: rgba(10, 12, 16, 0.7);
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.15);
}

/* Sélecteur de couleur unifié standard */
.inline-color-select-wrapper {
  width: 100%;
  display: flex;
  align-items: center;
}

.inline-color-select {
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 6px;
  padding: 4px 8px;
  font-family: monospace;
  font-size: 12px;
  font-weight: bold;
  cursor: pointer;
  outline: none;
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-fast);
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
  appearance: none;
  -webkit-appearance: none;
  -moz-appearance: none;
  text-align: center;
}

.inline-color-select:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
  border-color: rgba(255, 255, 255, 0.4);
}

.inline-color-select:focus {
  border-color: #fff;
  box-shadow: 0 0 0 2px var(--accent-primary);
}

/* Filtre de couleur spécial */
.filter-color-select {
  cursor: pointer;
  font-weight: 600;
  font-size: 12px;
  padding: 4px 6px;
}

/* Switch toggle en ligne */
.inline-checkbox-wrapper {
  display: flex;
  align-items: center;
  height: 28px;
}

.inline-switch {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 18px;
}

.inline-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.inline-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-color);
  transition: .3s;
}

.inline-slider:before {
  position: absolute;
  content: "";
  height: 12px;
  width: 12px;
  left: 2px;
  bottom: 2px;
  background-color: var(--text-secondary);
  transition: .3s;
}

input:checked + .inline-slider {
  background-color: rgba(99, 102, 241, 0.2);
  border-color: var(--accent-primary);
}

input:checked + .inline-slider:before {
  transform: translateX(18px);
  background-color: var(--accent-primary);
}

.inline-slider.inline-round {
  border-radius: 18px;
}

.inline-slider.inline-round:before {
  border-radius: 50%;
}
</style>
