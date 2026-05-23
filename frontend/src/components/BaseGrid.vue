<template>
  <div class="grid-container">
    <div class="grid-wrapper">
      <div class="timetable-grid" :style="{ gridTemplateColumns: computedGridTemplateColumns }">
        <!-- Coin supérieur gauche -->
        <div class="grid-header-cell" style="position: sticky; left: 0; z-index: 4;">Horaire</div>

        <!-- En-têtes des jours (Lundi au Samedi) -->
        <div v-for="day in days" :key="day.value" class="grid-header-cell" style="position: relative;">
          {{ day.label }}
          <div
            class="resize-handle"
            @mousedown.stop.prevent="startResize($event, day.value)"
          ></div>
        </div>

        <!-- Lignes d'heures (8h à 17h) -->
        <template v-for="(hour, index) in hours" :key="hour">
          <!-- Cellule d'heure à gauche -->
          <div class="grid-time-cell" :ref="el => { if (index === 0) gridCellRef = el }">
            {{ hour }}h00 - {{ hour + 1 }}h00
          </div>

          <!-- Cellules de la grille pour chaque jour -->
          <div
            v-for="day in days"
            :key="day.value"
            class="grid-cell"
            :style="{ display: 'flex', flexDirection: 'column', alignItems: 'stretch' }"
          >
            <div
              v-for="idx in subCellCount"
              :key="idx"
              class="sub-cell"
              :class="{ 'drag-over': dragOverCells[getCellKey(day.value, hour + (idx - 1) * (currentStandardDuration / 60))] }"
              @dragover.prevent="$emit('cell-dragover', day.value, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
              @dragleave="$emit('cell-dragleave', day.value, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
              @drop="$emit('cell-drop', day.value, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
              @mousedown="$emit('cell-mousedown', day.value, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
              @mouseenter="$emit('cell-mouseenter', day.value, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
              @mouseleave="$emit('cell-mouseleave', day.value, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
              @mousemove="$emit('cell-mousemove', day.value, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
            >
              <!-- Layer 1: Background (Preferences/Constraints) -->
              <div class="layer-bg">
                <slot name="cell-background" :day="day.value" :time="hour + (idx - 1) * (currentStandardDuration / 60)"></slot>
              </div>

              <!-- Layer 2: Foreground (Courses) -->
              <div class="layer-fg">
                <slot name="cell-content" :day="day.value" :time="hour + (idx - 1) * (currentStandardDuration / 60)"></slot>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- Overlay de chargement -->
      <slot name="overlay"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue';
import { useTimeslotGrid } from '../composables/useTimeslotGrid';

const { days, hours, currentStandardDuration, subCellCount, getCellKey } = useTimeslotGrid();

// === Redimensionnement des colonnes (jours) ===
const columnWidths = ref<Record<number, number>>({});
const defaultColWidth = 160;

function getColWidth(dayVal: number) {
  return columnWidths.value[dayVal] || defaultColWidth;
}

const computedGridTemplateColumns = computed(() => {
  const timeCol = '80px';
  // Si la colonne a été redimensionnée manuellement, on fixe sa taille exacte.
  // Sinon, on la laisse fluide avec un minmax pour occuper l'espace.
  const dayCols = days.map(d => {
    if (columnWidths.value[d.value]) {
      return `${columnWidths.value[d.value]}px`;
    }
    return `minmax(${defaultColWidth}px, 1fr)`;
  }).join(' ');
  return `${timeCol} ${dayCols}`;
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

withDefaults(defineProps<{
  dragOverCells?: Record<string, boolean>;
}>(), {
  dragOverCells: () => ({})
});

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
</style>
