<template>
  <div class="grid-container">
    <div class="grid-wrapper" :class="{ 'mini-grid': isMini }">
      <div v-if="days.length > 0" class="timetable-grid" :style="{ gridTemplateColumns: computedGridTemplateColumns, gridTemplateRows: computedGridTemplateRows, minWidth: isMini ? '0' : undefined }">
        <!-- Coin supérieur gauche -->
        <div class="grid-header-cell" style="position: sticky; left: 0; z-index: 12;" :style="{ gridRow: layoutMode === 'resource_columns' && activeResources && activeResources.length > 0 ? '1 / span 2' : '1' }">Horaire</div>

        <!-- En-têtes des jours -->
        <div v-for="day in days" :key="'day-'+day.value" class="grid-header-cell" :style="{ gridColumn: `span ${(layoutMode === 'resource_columns' && activeResources && activeResources.length > 0) ? activeResources.length : 1}` }">
          {{ day.label }}
          <div
            class="resize-handle"
            @mousedown.stop.prevent="startResize($event, day.value)"
          ></div>
        </div>

        <!-- En-têtes des ressources (si activé) -->
        <template v-if="layoutMode === 'resource_columns' && activeResources && activeResources.length > 0">
          <template v-for="day in days" :key="'res-row-'+day.value">
            <div v-for="res in activeResources" :key="res.id" class="grid-header-cell resource-header-cell" style="top: 50px; z-index: 11; font-size: 0.85em; font-weight: normal; border-top: none; background-color: var(--bg-surface);">
              {{ res.display_name }}
            </div>
          </template>
        </template>

        <!-- Lignes d'heures (8h à 17h) -->
        <template v-for="(hour, index) in hours" :key="hour">
          <!-- Cellule d'heure à gauche -->
          <div class="grid-time-cell" :ref="el => { if (index === 0) gridCellRef = el }">
            {{ hour }}h00 - {{ hour + 1 }}h00
          </div>

          <!-- Cellules de la grille pour chaque colonne -->
          <div
            v-for="col in gridColumns"
            :key="col.id"
            class="grid-cell"
            :style="{ display: 'flex', flexDirection: 'column', alignItems: 'stretch', position: 'relative' }"
          >
            <div
              v-for="idx in subCellCount"
              :key="idx"
              class="sub-cell"
              :class="{ 
                'drag-over': dragOverCells[getCellKey(col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60))],
                'pref-level-off-hashed': !isTimeslotActive(col.dayValue, hour, idx - 1)
              }"
              @dragover.prevent="$emit('cell-dragover', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
              @dragleave="$emit('cell-dragleave', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
              @drop="$emit('cell-drop', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
              @mousedown="$emit('cell-mousedown', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
              @mouseenter="$emit('cell-mouseenter', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
              @mouseleave="$emit('cell-mouseleave', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
              @mousemove="$emit('cell-mousemove', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
            >
              <!-- Layer 1: Background (Preferences/Constraints) -->
              <div class="layer-bg">
                <slot name="cell-background" :day="col.dayValue" :time="hour + (idx - 1) * (currentStandardDuration / 60)" :resource="col.resource"></slot>
              </div>

              <!-- Layer 2: Foreground (Courses) -->
              <div class="layer-fg">
                <slot name="cell-content" :day="col.dayValue" :time="hour + (idx - 1) * (currentStandardDuration / 60)" :resource="col.resource"></slot>
              </div>
            </div>
          </div>
        </template>
      </div>
      
      <div v-else class="no-timeslots-error">
        <div class="error-icon">⚠️</div>
        <div class="error-title">Aucun créneau horaire configuré</div>
        <div class="error-desc">Veuillez configurer les créneaux horaires afin d'afficher la grille.</div>
      </div>

      <!-- Overlay de chargement -->
      <slot name="overlay"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue';
import { useTimeslotGrid } from '../composables/useTimeslotGrid';

const props = withDefaults(defineProps<{
  timeslots: any[];
  dragOverCells?: Record<string, boolean>;
  layoutMode?: string;
  activeResources?: any[];
  isMini?: boolean;
}>(), {
  dragOverCells: () => ({}),
  layoutMode: 'merged',
  activeResources: () => [],
  isMini: false
});

const { days, hours, currentStandardDuration, subCellCount, getCellKey, isTimeslotActive } = useTimeslotGrid(computed(() => props.timeslots));

const gridColumns = computed(() => {
  if (props.layoutMode === 'resource_columns' && props.activeResources && props.activeResources.length > 0) {
    const cols: any[] = [];
    days.value.forEach(day => {
      props.activeResources!.forEach(res => {
        cols.push({ id: `${day.value}-${res.type}-${res.id}`, dayValue: day.value, resource: res });
      });
    });
    return cols;
  }
  return days.value.map(day => ({ id: `${day.value}`, dayValue: day.value, resource: null }));
});

// === Redimensionnement des colonnes (jours) ===
const columnWidths = ref<Record<number, number>>({});

function getColWidth(dayVal: number) {
  return columnWidths.value[dayVal] || 0;
}

const computedGridTemplateColumns = computed(() => {
  const timeCol = '60px'; // Slightly smaller time col to fit more content
  const dayCols = gridColumns.value.map(col => {
    if (columnWidths.value[col.dayValue]) {
      if (props.layoutMode === 'resource_columns' && props.activeResources && props.activeResources.length > 0) {
        return `${columnWidths.value[col.dayValue] / props.activeResources.length}px`;
      }
      return `${columnWidths.value[col.dayValue]}px`;
    }
    return `minmax(0, 1fr)`;
  }).join(' ');
  return `${timeCol} ${dayCols}`;
});

const computedGridTemplateRows = computed(() => {
  const hasResourceHeader = props.layoutMode === 'resource_columns' && props.activeResources && props.activeResources.length > 0;
  // Always adapt to container size using minmax(0, 1fr)
  return hasResourceHeader ? '40px 30px repeat(10, minmax(0, 1fr))' : '40px repeat(10, minmax(0, 1fr))';
});

let startX = 0;
let startWidth = 0;
let resizingDay: number | null = null;

function startResize(event: MouseEvent, dayVal: number) {
  startX = event.clientX;
  resizingDay = dayVal;
  startWidth = getColWidth(dayVal);
  
  document.addEventListener('mousemove', onResize);
  document.addEventListener('mouseup', stopResize);
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
}

function onResize(event: MouseEvent) {
  if (resizingDay === null) return;
  const diff = event.clientX - startX;
  let newWidth = startWidth + diff;
  if (newWidth < 100) newWidth = 100; // largeur minimale
  columnWidths.value[resizingDay] = newWidth;
}

function stopResize() {
  document.removeEventListener('mousemove', onResize);
  document.removeEventListener('mouseup', stopResize);
  resizingDay = null;
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
}
// ===============================================



defineEmits<{
  (e: 'cell-dragover', day: number, time: number, event: DragEvent): void;
  (e: 'cell-dragleave', day: number, time: number, event: DragEvent): void;
  (e: 'cell-drop', day: number, time: number, event: DragEvent): void;
  (e: 'cell-mousedown', day: number, time: number, event: MouseEvent): void;
  (e: 'cell-mouseenter', day: number, time: number, event: MouseEvent): void;
  (e: 'cell-mouseleave', day: number, time: number, event: MouseEvent): void;
  (e: 'cell-mousemove', day: number, time: number, event: MouseEvent): void;
}>();

const gridCellRef = ref<HTMLElement | null>(null);
let resizeObserver: ResizeObserver | null = null;

onMounted(() => {
  if (gridCellRef.value) {
    resizeObserver = new ResizeObserver(entries => {
      for (const entry of entries) {
        // Obtenir la hauteur réelle (y compris les bordures/padding)
        const height = entry.borderBoxSize?.[0]?.blockSize || entry.contentRect.height;
        document.documentElement.style.setProperty('--grid-cell-height', `${height}px`);
      }
    });
    resizeObserver.observe(gridCellRef.value);
  }
});

onUnmounted(() => {
  if (resizeObserver) {
    resizeObserver.disconnect();
  }
});
</script>

<style scoped>
.sub-cell {
  flex: 1;
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-areas: "stack";
  position: relative;
  transition: all 0.2s;
  padding: 0;
}

.sub-cell:not(:last-child) {
  border-bottom: 1px dotted var(--border-color);
}

.pref-level-off-hashed {
  background: repeating-linear-gradient(45deg, rgba(156, 163, 175, 0.05) 0px, rgba(156, 163, 175, 0.05) 6px, rgba(156, 163, 175, 0.2) 6px, rgba(156, 163, 175, 0.2) 12px) !important;
  border: 1px solid rgba(156, 163, 175, 0.3) !important;
  color: #9ca3af;
}

.layer-bg, .layer-fg {
  grid-area: stack;
  width: 100%;
  height: 100%;
  position: relative;
}

.layer-fg {
  z-index: 2;
  pointer-events: none;
}

.layer-fg :deep(*) {
  pointer-events: auto;
}

.layer-bg {
  z-index: 1;
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
  z-index: 10;
}

.resize-handle:hover {
  background-color: rgba(99, 102, 241, 0.5);
}

.no-timeslots-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  text-align: center;
  padding: 32px;
}
.no-timeslots-error .error-icon {
  font-size: 48px;
  margin-bottom: 16px;
}
.no-timeslots-error .error-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}
.mini-grid .grid-header-cell,
.mini-grid .grid-time-cell {
  font-size: 0.7em;
  padding: 4px;
}
</style>
