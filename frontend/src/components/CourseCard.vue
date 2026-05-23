<template>
  <div
    class="placed-course"
    :class="{ 'is-pinned-card': course.is_pinned, 'is-selected-card': isSelected, 'is-sidebar': !isPlaced }"
    :style="{
      backgroundColor: backgroundColor || 'var(--bg-card)',
      height: height || 'auto',
      bottom: isPlaced ? 'auto' : undefined,
      zIndex: isPlaced ? 10 : undefined,
      position: isPlaced ? 'absolute' : 'relative',
      color: 'var(--text-primary)',
      borderLeftColor: backgroundColor ? 'rgba(0, 0, 0, 0.1)' : 'var(--accent-primary)',
      width: isPlaced && overlapCount && overlapCount > 1 ? `calc(${100 / overlapCount}% - ${(overlapIndex === overlapCount - 1) ? 8 : 4}px)` : undefined,
      left: isPlaced && overlapCount && overlapCount > 1 ? `calc(${(100 / overlapCount) * (overlapIndex || 0)}% + 4px)` : undefined,
      right: isPlaced && overlapCount && overlapCount > 1 ? 'auto' : undefined
    }"
    draggable="true"
    @dragstart="$emit('dragstart', $event, course.id)"
    @click.stop="$emit('click', course.id, $event)"
  >
    <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 4px;">
      <span class="placed-subject">{{ course.subject }}</span>
      <div v-if="isPlaced" style="display: flex; align-items: center; gap: 2px;">
        <button @click.stop="$emit('togglePin', course.id)" class="pin-btn" :class="{ 'is-pinned': course.is_pinned }" :title="course.is_pinned ? 'Déverrouiller le cours' : 'Verrouiller le cours'">
          <svg v-if="course.is_pinned" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="lock-icon">
            <path fill-rule="evenodd" d="M12 1.5a5.25 5.25 0 0 0-5.25 5.25v3a3 3 0 0 0-3 3v6.75a3 3 0 0 0 3 3h10.5a3 3 0 0 0 3-3v-6.75a3 3 0 0 0-3-3v-3c0-2.9-2.35-5.25-5.25-5.25Zm3.75 8.25v-3a3.75 3.75 0 1 0-7.5 0v3h7.5Z" clip-rule="evenodd" />
          </svg>
          <svg v-else xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor" class="lock-icon">
            <path stroke-linecap="round" stroke-linejoin="round" d="M13.5 10.5V6.75a4.5 4.5 0 1 1 9 0v3.75M3.75 21.75h16.5a1.5 1.5 0 0 0 1.5-1.5V12a1.5 1.5 0 0 0-1.5-1.5H3.75A1.5 1.5 0 0 0 2.25 12v8.25a1.5 1.5 0 0 0 1.5 1.5Z" />
          </svg>
        </button>
        <button @click.stop="$emit('unassign', course.id)" class="unassign-btn" title="Retirer de la grille">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      <div v-else>
        <span class="duration-badge">
          ⏱️ {{ formattedDuration }}
        </span>
      </div>
    </div>

    <div style="display: flex; justify-content: space-between; align-items: flex-end; flex: 1; min-height: 0; gap: 4px; overflow: hidden;">
      <div class="placed-meta" style="color: var(--text-secondary)">
        <div v-if="teachersText" class="text-truncate">👨‍🏫 {{ teachersText }}</div>
        <div style="display: flex; gap: 6px; flex-wrap: wrap;">
          <span v-if="divisionsText" class="text-truncate">👥 {{ divisionsText }}</span>
          <span v-if="classroomsText" class="text-truncate">📍 {{ classroomsText }}</span>
        </div>
      </div>

      <div v-if="course.week_type === 'A' || course.week_type === 'B'" class="week-indicator" :class="'week-' + course.week_type">
        {{ course.week_type }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Course } from '../types';

const props = defineProps<{
  course: Course;
  isPlaced?: boolean;
  isSelected?: boolean;
  backgroundColor?: string;
  height?: string;
  teachersText?: string;
  divisionsText?: string;
  classroomsText?: string;
  overlapIndex?: number;
  overlapCount?: number;
}>();

defineEmits<{
  (e: 'dragstart', event: DragEvent, id: number): void;
  (e: 'click', id: number, event: MouseEvent): void;
  (e: 'togglePin', id: number): void;
  (e: 'unassign', id: number): void;
}>();

const formattedDuration = computed(() => {
  const m = props.course.duration_minutes || 0;
  const h = Math.floor(m / 60);
  const min = m % 60;
  const mStr = String(min).padStart(2, '0');
  return `${h}h${mStr}`;
});
</script>

<style scoped>
.placed-course {
  position: absolute;
  top: 4px;
  left: 4px;
  right: 4px;
  bottom: 4px;
  border-radius: 3px;
  padding: 8px;
  font-size: 12px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  cursor: grab;
  box-shadow: var(--shadow-sm);
  transition: transform var(--transition-fast), box-shadow var(--transition-fast), filter var(--transition-fast);
  border: 1px solid var(--border-color);
  border-left-width: 4px;
  border-left-style: solid;
  overflow: hidden;
}

.placed-course:hover {
  transform: scale(1.02);
  box-shadow: var(--shadow-md);
  filter: brightness(1.1);
}

.is-sidebar {
  top: auto;
  left: auto;
  right: auto;
  bottom: auto;
  border-left-width: 4px;
  flex-shrink: 0;
}

.is-sidebar:hover {
  border-color: rgba(99, 102, 241, 0.6);
}

.placed-course.is-selected-card {
  outline: 2px solid var(--accent-primary) !important;
  outline-offset: 1px;
  box-shadow: 0 0 12px rgba(99, 102, 241, 0.6);
  z-index: 10;
}

.placed-subject {
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.placed-meta {
  font-size: 10px;
  display: flex;
  flex-direction: column;
  gap: 1px;
  overflow: hidden;
}

.text-truncate {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
  display: inline-block;
}

.pin-btn, .unassign-btn {
  background: rgba(255, 255, 255, 0.2);
  border: none;
  border-radius: 4px;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.2s;
}
.is-sidebar .pin-btn, .is-sidebar .unassign-btn {
  background: rgba(0, 0, 0, 0.05);
  color: var(--text-primary);
}

.pin-btn:hover {
  background: rgba(0, 0, 0, 0.1);
  color: var(--text-primary);
}
.pin-btn.is-pinned {
  background: rgba(0, 0, 0, 0.1);
  color: var(--accent-primary);
}

.unassign-btn:hover {
  background: rgba(239, 68, 68, 0.1);
  color: rgba(239, 68, 68, 1);
}
.unassign-btn svg, .pin-btn svg {
  width: 14px;
  height: 14px;
}

.duration-badge {
  font-size: 11.5px;
  background: rgba(0, 0, 0, 0.05);
  padding: 2.5px 7px;
  border-radius: 6px;
  font-weight: bold;
  font-family: monospace;
}

.week-indicator {
  font-size: 11px;
  font-weight: 800;
  padding: 2px 5px;
  border-radius: 4px;
  line-height: 1.1;
  background: rgba(0, 0, 0, 0.1);
}

.week-indicator.week-A {
  background: rgba(14, 165, 233, 0.2);
  color: rgb(2, 132, 199);
}

.week-indicator.week-B {
  background: rgba(245, 158, 11, 0.2);
  color: rgb(180, 83, 9);
}
</style>
