<template>
  <div class="grid-container-layout" :class="{ 'cursor-brush': preferenceMode === 'edit' }">
    <!-- Top Filter Bar -->
    <GridFilterBar
      :mode="preferenceMode === 'edit' ? 'preference' : 'timetable'"
      :schools="schools"
      :teachers="teachers"
      :divisions="divisions"
      :classrooms="classrooms"
      :periodTypes="periodTypes"
      :periods="periods"
      :selectedTeacherIds="selectedTeacherIds"
      :selectedNonTeachingStaffIds="selectedNonTeachingStaffIds"
      :selectedDivisionIds="selectedDivisionIds"
      :selectedClassroomIds="selectedClassroomIds"
      :schoolId="schoolId"
      :weekType="weekType"
      :periodTypeId="periodTypeId"
      :periodIds="periodIds"
      :hideResourceSelectors="hideResourceSelectors"
      :hideSchoolSelector="hideSchoolSelector"
      :hideWeekSelector="hideWeekSelector"
      :hidePeriodSelector="hidePeriodSelector"
      @update:selectedTeacherIds="$emit('update:selectedTeacherIds', $event)"
      @update:selectedNonTeachingStaffIds="$emit('update:selectedNonTeachingStaffIds', $event)"
      @update:selectedDivisionIds="$emit('update:selectedDivisionIds', $event)"
      @update:selectedClassroomIds="$emit('update:selectedClassroomIds', $event)"
      @update:schoolId="$emit('update:schoolId', $event)"
      @update:weekType="$emit('update:weekType', $event)"
      @update:periodTypeId="$emit('update:periodTypeId', $event)"
      @update:periodIds="$emit('update:periodIds', $event)"
      :isDetailedView="isDetailedView"
      @update:isDetailedView="$emit('update:isDetailedView', $event)"
      :autoTarget="autoTarget"
      @update:autoTarget="$emit('update:autoTarget', $event)"
      :showAutoTargetToggle="showAutoTargetToggle"
      :layoutMode="layoutMode"
      @update:layoutMode="$emit('update:layoutMode', $event)"
      :showPlacementAssistantToggle="showPlacementAssistantToggle"
      :placementAssistantActive="placementAssistantActive"
      @update:placementAssistantActive="$emit('update:placementAssistantActive', $event)"
    >
      <template #actions>
        <slot name="actions">
          <BrushPalette 
            v-if="preferenceMode === 'edit'"
            :modelValue="brush" 
            @update:modelValue="$emit('update:brush', $event)" 
          />
        </slot>
      </template>
    </GridFilterBar>

    <!-- Main Workspace (Sidebar + Grid) -->
    <div class="workspace-layout">
      <!-- Sidebar Slot -->
      <div class="sidebar-wrapper" v-if="showSidebar" :style="{ width: `${sidebarWidth}px` }">
        <slot name="sidebar"></slot>
        <div class="sidebar-resize-handle" @mousedown.stop.prevent="startResizeSidebar"></div>
      </div>

      <!-- Base Grid -->
      <div class="grid-wrapper">
        <slot name="grid-content">
          <!-- Mode: Une grille par ressource (jusqu'à 4) -->
          <div v-if="layoutMode === 'resource_grids'" class="resource-grids-container" :class="`grid-count-${Math.min(4, activeResources.length)}`">
            <div v-for="res in activeResources.slice(0, 4)" :key="res.id" class="resource-grid-wrapper">
              <h3 class="resource-grid-title">{{ res.display_name }}</h3>
              <BaseGrid
                :timeslots="timeslots"
                :dragOverCells="dragOverCells"
                layoutMode="merged"
                @cell-dragover="(day, time, ev) => $emit('cell-dragover', day, time, ev)"
                @cell-dragleave="(day, time, ev) => $emit('cell-dragleave', day, time, ev)"
                @cell-drop="(day, time, ev) => $emit('cell-drop', day, time, ev)"
                @cell-mousedown="(day, time, ev) => $emit('cell-mousedown', day, time, ev)"
                @cell-mouseenter="(day, time, ev) => $emit('cell-mouseenter', day, time, ev)"
                @cell-mouseleave="(day, time, ev) => $emit('cell-mouseleave', day, time, ev)"
                @cell-mousemove="(day, time, ev) => $emit('cell-mousemove', day, time, ev)"
                style="height: calc(100% - 32px); border-top: 1px solid var(--border-color); border-radius: 0; overflow: hidden;"
              >
                <!-- Forward Slots to Parent -->
                <template #cell-background="{ day, time }">
                  <slot name="cell-background" :day="day" :time="time" :resource="res"></slot>
                </template>
                <template #cell-content="{ day, time }">
                  <slot name="cell-content" :day="day" :time="time" :resource="res"></slot>
                </template>
                <template #overlay>
                  <slot name="overlay"></slot>
                </template>
              </BaseGrid>
            </div>
            <div v-if="!activeResources || activeResources.length === 0" style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); padding: 2rem;">
              Veuillez sélectionner au moins une ressource pour afficher les grilles.
            </div>
          </div>

          <!-- Mode: Défaut ou Une colonne par ressource -->
          <BaseGrid v-else
            :timeslots="timeslots"
            :dragOverCells="dragOverCells"
            :layoutMode="layoutMode"
            :activeResources="activeResources"
            @cell-dragover="(day, time, ev) => $emit('cell-dragover', day, time, ev)"
            @cell-dragleave="(day, time, ev) => $emit('cell-dragleave', day, time, ev)"
            @cell-drop="(day, time, ev) => $emit('cell-drop', day, time, ev)"
            @cell-mousedown="(day, time, ev) => $emit('cell-mousedown', day, time, ev)"
            @cell-mouseenter="(day, time, ev) => $emit('cell-mouseenter', day, time, ev)"
            @cell-mouseleave="(day, time, ev) => $emit('cell-mouseleave', day, time, ev)"
            @cell-mousemove="(day, time, ev) => $emit('cell-mousemove', day, time, ev)"
            style="height: 100%; border: none; border-radius: 0;"
          >
            <!-- Forward Slots to Parent -->
            <template #cell-background="{ day, time, resource }">
              <slot name="cell-background" :day="day" :time="time" :resource="resource"></slot>
            </template>
            <template #cell-content="{ day, time, resource }">
              <slot name="cell-content" :day="day" :time="time" :resource="resource"></slot>
            </template>
            <template #overlay>
              <slot name="overlay"></slot>
            </template>
          </BaseGrid>
        </slot>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import GridFilterBar from './GridFilterBar.vue';
import BrushPalette from './BrushPalette.vue';
import BaseGrid from './BaseGrid.vue';

const sidebarWidth = ref(320);
let startX = 0;
let initialWidth = 0;

function startResizeSidebar(event: MouseEvent) {
  startX = event.clientX;
  initialWidth = sidebarWidth.value;
  document.addEventListener('mousemove', onResizeSidebar);
  document.addEventListener('mouseup', stopResizeSidebar);
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
}

function onResizeSidebar(event: MouseEvent) {
  const diff = event.clientX - startX;
  let newWidth = initialWidth + diff;
  if (newWidth < 200) newWidth = 200; // largeur minimale
  if (newWidth > 800) newWidth = 800; // largeur maximale
  sidebarWidth.value = newWidth;
}

function stopResizeSidebar() {
  document.removeEventListener('mousemove', onResizeSidebar);
  document.removeEventListener('mouseup', stopResizeSidebar);
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
}

withDefaults(defineProps<{
  preferenceMode?: 'none' | 'readonly' | 'edit';
  coursesMode?: 'none' | 'readonly' | 'edit';
  showSidebar?: boolean;
  
  // Brush state (v-model)
  brush?: 'Preferred' | 'Undesirable' | 'Unsuited' | 'Neutral';
  
  // Drag over state
  dragOverCells?: Record<string, boolean>;
  
  // Forwarded Filter Bar Props
  schools?: any[];
  teachers?: any[];
  divisions?: any[];
  classrooms?: any[];
  periodTypes?: any[];
  periods?: any[];
  timeslots?: any[];
  
  selectedTeacherIds?: number[];
  selectedNonTeachingStaffIds?: number[];
  selectedDivisionIds?: number[];
  selectedClassroomIds?: number[];
  schoolId?: number | null;
  weekType?: 'W' | 'A' | 'B';
  periodTypeId?: number | null;
  periodIds?: number[];
  
  hideResourceSelectors?: boolean;
  hideSchoolSelector?: boolean;
  hideWeekSelector?: boolean;
  hidePeriodSelector?: boolean;
  isDetailedView?: boolean;
  autoTarget?: boolean;
  showAutoTargetToggle?: boolean;
  layoutMode?: string;
  showPlacementAssistantToggle?: boolean;
  placementAssistantActive?: boolean;
  activeResources?: any[];
}>(), {
  preferenceMode: 'none',
  coursesMode: 'readonly',
  showSidebar: false,
  brush: 'Unsuited',
  dragOverCells: () => ({}),
  schools: () => [],
  teachers: () => [],
  divisions: () => [],
  classrooms: () => [],
  periodTypes: () => [],
  periods: () => [],
  timeslots: () => [],
  activeResources: () => [],
  selectedTeacherIds: () => [],
  selectedNonTeachingStaffIds: () => [],
  selectedDivisionIds: () => [],
  selectedClassroomIds: () => [],
  schoolId: null,
  weekType: 'W',
  periodTypeId: null,
  periodIds: () => [],
  hideResourceSelectors: false,
  hideSchoolSelector: false,
  hideWeekSelector: false,
  hidePeriodSelector: false,
  isDetailedView: false,
  autoTarget: false,
  showAutoTargetToggle: true,
  layoutMode: 'merged',
  showPlacementAssistantToggle: true,
  placementAssistantActive: false
});

defineEmits<{
  (e: 'update:brush', value: 'Preferred' | 'Undesirable' | 'Unsuited' | 'Neutral'): void;
  (e: 'update:selectedTeacherIds', value: number[]): void;
  (e: 'update:selectedNonTeachingStaffIds', value: number[]): void;
  (e: 'update:selectedDivisionIds', value: number[]): void;
  (e: 'update:selectedClassroomIds', value: number[]): void;
  (e: 'update:schoolId', value: number | null): void;
  (e: 'update:weekType', value: 'W' | 'A' | 'B'): void;
  (e: 'update:periodTypeId', value: number | null): void;
  (e: 'update:periodIds', value: number[]): void;
  (e: 'update:isDetailedView', value: boolean): void;
  (e: 'update:autoTarget', value: boolean): void;
  (e: 'update:layoutMode', value: string): void;
  (e: 'update:placementAssistantActive', value: boolean): void;
  
  // Grid events
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
.grid-container-layout {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
}

.workspace-layout {
  display: flex;
  flex: 1;
  gap: 1px;
  min-height: 0;
}

.sidebar-wrapper {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  position: relative;
}

.sidebar-resize-handle {
  position: absolute;
  top: 0;
  right: -3px;
  bottom: 0;
  width: 6px;
  cursor: col-resize;
  background-color: transparent;
  transition: background-color var(--transition-fast);
  z-index: 10;
}

.sidebar-resize-handle:hover, .sidebar-resize-handle:active {
  background-color: rgba(99, 102, 241, 0.5);
}

.grid-wrapper {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}


/* Custom brush cursor style */
.cursor-brush :deep(.sub-cell) {
  cursor: cell;
}

.resource-grids-container {
  display: grid;
  gap: 1px;
  height: 100%;
  background-color: var(--bg-body);
  overflow: auto;
}

.resource-grids-container.grid-count-1 {
  grid-template-columns: 1fr;
  grid-template-rows: 1fr;
}

.resource-grids-container.grid-count-2 {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr;
}

.resource-grids-container.grid-count-3,
.resource-grids-container.grid-count-4 {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
}

.resource-grid-wrapper {
  display: flex;
  flex-direction: column;
  min-height: 400px;
  background-color: var(--bg-surface);
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

.resource-grid-title {
  margin: 0;
  padding: 8px 16px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  background-color: var(--bg-surface-hover);
  border-bottom: 1px solid var(--border-color);
  text-align: center;
}
</style>
