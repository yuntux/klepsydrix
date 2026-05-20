<template>
  <div class="grid-container">
    <div class="grid-wrapper">
      <div class="timetable-grid">
        <!-- Coin supérieur gauche -->
        <div class="grid-header-cell" style="position: sticky; left: 0; z-index: 4;">Horaire</div>

        <!-- En-têtes des jours (Lundi au Samedi) -->
        <div v-for="day in days" :key="day.value" class="grid-header-cell">
          {{ day.label }}
        </div>

        <!-- Lignes d'heures (8h à 17h) -->
        <template v-for="hour in hours" :key="hour">
          <!-- Cellule d'heure à gauche -->
          <div class="grid-time-cell">
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
import { useTimeslotGrid } from '../composables/useTimeslotGrid';

const { days, hours, currentStandardDuration, subCellCount, getCellKey } = useTimeslotGrid();

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
</style>
