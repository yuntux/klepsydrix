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
      :viewMode="viewMode"
      :selectedIds="selectedIds"
      :schoolId="schoolId"
      :weekType="weekType"
      :periodTypeId="periodTypeId"
      :periodIds="periodIds"
      :hideResourceSelectors="hideResourceSelectors"
      :hideSchoolSelector="hideSchoolSelector"
      @update:viewMode="$emit('update:viewMode', $event)"
      @update:selectedIds="$emit('update:selectedIds', $event)"
      @update:schoolId="$emit('update:schoolId', $event)"
      @update:weekType="$emit('update:weekType', $event)"
      @update:periodTypeId="$emit('update:periodTypeId', $event)"
      @update:periodIds="$emit('update:periodIds', $event)"
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
      <div class="sidebar-wrapper" v-if="showSidebar">
        <slot name="sidebar"></slot>
      </div>

      <!-- Base Grid -->
      <div class="grid-wrapper">
        <slot name="grid-content">
          <BaseGrid
            :dragOverCells="dragOverCells"
            @cell-dragover="(day, time, ev) => $emit('cell-dragover', day, time, ev)"
            @cell-dragleave="(day, time, ev) => $emit('cell-dragleave', day, time, ev)"
            @cell-drop="(day, time, ev) => $emit('cell-drop', day, time, ev)"
            @cell-mousedown="(day, time, ev) => $emit('cell-mousedown', day, time, ev)"
            @cell-mouseenter="(day, time, ev) => $emit('cell-mouseenter', day, time, ev)"
            @cell-mouseleave="(day, time, ev) => $emit('cell-mouseleave', day, time, ev)"
            @cell-mousemove="(day, time, ev) => $emit('cell-mousemove', day, time, ev)"
          >
            <!-- Forward Slots to Parent -->
            <template #cell-background="{ day, time }">
              <slot name="cell-background" :day="day" :time="time"></slot>
            </template>
            <template #cell-content="{ day, time }">
              <slot name="cell-content" :day="day" :time="time"></slot>
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
import GridFilterBar from './GridFilterBar.vue';
import BrushPalette from './BrushPalette.vue';
import BaseGrid from './BaseGrid.vue';

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
  
  viewMode?: string;
  selectedIds?: number[];
  schoolId?: number | null;
  weekType?: 'W' | 'A' | 'B';
  periodTypeId?: number | null;
  periodIds?: number[];
  
  hideResourceSelectors?: boolean;
  hideSchoolSelector?: boolean;
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
  viewMode: 'division',
  selectedIds: () => [],
  schoolId: null,
  weekType: 'W',
  periodTypeId: null,
  periodIds: () => [],
  hideResourceSelectors: false,
  hideSchoolSelector: false
});

defineEmits<{
  (e: 'update:brush', value: 'Preferred' | 'Undesirable' | 'Unsuited' | 'Neutral'): void;
  (e: 'update:viewMode', value: string): void;
  (e: 'update:selectedIds', value: number[]): void;
  (e: 'update:schoolId', value: number | null): void;
  (e: 'update:weekType', value: 'W' | 'A' | 'B'): void;
  (e: 'update:periodTypeId', value: number | null): void;
  (e: 'update:periodIds', value: number[]): void;
  
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
  width: 320px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
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
</style>
