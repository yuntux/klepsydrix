<template>
  <aside class="app-sidebar">
    <div class="sidebar-header">
      <h2 class="sidebar-title">
        Cours à planifier
        <span class="badge" v-if="unassignedCourses.length > 0">{{ unassignedCourses.length }}</span>
      </h2>
    </div>

    <div class="courses-list">
      <div
        v-for="course in unassignedCourses"
        :key="course.id"
        class="course-card"
        :class="{ 'is-selected-card': (selectedCourseIds || []).includes(course.id) }"
        draggable="true"
        @dragstart="onDragStart($event, course.id)"
        @click.stop="$emit('selectCourse', course.id)"
      >
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
          <div class="course-subject">{{ course.subject }}</div>
          <span style="font-size: 11.5px; background: rgba(0, 0, 0, 0.05); padding: 2.5px 7px; border-radius: 6px; font-weight: bold; color: var(--text-secondary); font-family: monospace;">
            ⏱️ {{ formatDuration(course.duration_minutes) }}
          </span>
        </div>
        <div class="course-meta">
          <span class="meta-item">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
            </svg>
            {{ course.teacher_ids ? course.teacher_ids.map(id => getTeacherName(id)).join(", ") : "" }}
          </span>
          <span class="meta-separator">•</span>
          <span class="meta-item">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M4.26 10.147a60.438 60.438 0 0 0-.491 6.347A48.62 48.62 0 0 1 12 20.904a48.62 48.62 0 0 1 8.232-4.41 60.46 60.46 0 0 0-.491-6.347m-15.482 0a50.57 50.57 0 0 0-2.658-.813A5.905 5.905 0 0 1 1.75 9.149a4.89 4.89 0 0 1 4.409-4.891c1.85-.14 3.719-.211 5.591-.211 1.872 0 3.74.072 5.592.211a4.89 4.89 0 0 1 4.409 4.892 5.905 5.905 0 0 1-1.096 1.028m-15.482 0a48.584 48.584 0 0 1 15.482 0m-15.482 0v2.93m15.482-2.93v2.93m-15.482 0a50.58 50.58 0 0 1 2.658-.814m12.824.814a50.58 50.58 0 0 0-2.658-.814m-9.966.814v2.644m9.966-2.644v2.644m-9.966 0a48.58 48.58 0 0 1 9.966 0" />
            </svg>
            {{ course.division_ids ? course.division_ids.map(id => getDivisionName(id)).join(", ") : "" }}
          </span>
        </div>
      </div>

      <div v-if="unassignedCourses.length === 0" style="text-align: center; color: var(--text-muted); margin-top: 40px; font-size: 14px;">
        Tous les cours ont été planifiés ! 🎉
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Course, Teacher, Division } from '../types';

const props = defineProps<{
  courses: Course[];
  teachers: Teacher[];
  divisions: Division[];
  selectedCourseIds?: number[];
}>();

const emit = defineEmits<{
  (e: 'selectCourse', courseId: number): void;
}>();

const unassignedCourses = computed(() => {
  return props.courses.filter(c => c.timeslot_id === null);
});

function formatDuration(minutes: number) {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  const mStr = String(m).padStart(2, '0');
  return `${h}h${mStr}`;
}

function getTeacherName(id: number) {
  return props.teachers.find(t => t.id === id)?.name || 'Enseignant inconnu';
}

function getDivisionName(id: number) {
  return props.divisions.find(d => d.id === id)?.name || 'Classe inconnue';
}

function onDragStart(event: DragEvent, courseId: number) {
  if (event.dataTransfer) {
    event.dataTransfer.setData('text/plain', courseId.toString());
    event.dataTransfer.effectAllowed = 'move';
  }
}
</script>
