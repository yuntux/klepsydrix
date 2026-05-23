<template>
  <aside class="app-sidebar">
    <div class="sidebar-header">
      <h2 class="sidebar-title">
        Cours à planifier
        <span class="badge" v-if="unassignedCourses.length > 0">{{ unassignedCourses.length }}</span>
      </h2>
    </div>

    <div class="courses-list">
      <CourseCard
        v-for="course in unassignedCourses"
        :key="course.id"
        :course="course"
        :isSelected="(selectedCourseIds || []).includes(course.id)"
        :isPlaced="false"
        :backgroundColor="course.color || '#cbd5e1'"
        :height="getSidebarCourseHeight(course)"
        :teachersText="course.teacher_ids ? course.teacher_ids.map(id => getTeacherName(id)).join(', ') : ''"
        :divisionsText="course.division_ids ? course.division_ids.map(id => getDivisionName(id)).join(', ') : ''"
        :classroomsText="course.classroom_ids ? course.classroom_ids.map(id => getClassroomName(id)).join(', ') : ''"
        @dragstart="onDragStart"
        @click="(id, ev) => $emit('selectCourse', id, ev)"
      />

      <div v-if="unassignedCourses.length === 0" style="text-align: center; color: var(--text-muted); margin-top: 40px; font-size: 14px;">
        Tous les cours ont été planifiés ! 🎉
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Course, Teacher, Division, Classroom } from '../types';
import CourseCard from './CourseCard.vue';
import { useTimeslotGrid } from '../composables/useTimeslotGrid';

const props = defineProps<{
  courses: Course[];
  teachers: Teacher[];
  divisions: Division[];
  classrooms?: Classroom[];
  selectedCourseIds?: number[];
  currentStandardDuration?: number;
}>();

// Colors are now handled by course.color from database

function getSidebarCourseHeight(course: Course) {
  const duration = course.duration_minutes || 30;
  // La hauteur s'ajuste de façon 100% dynamique grâce à la variable CSS mise à jour par la grille
  return `calc(${duration} * (var(--grid-cell-height, 75px) / 60) - 8px)`; 
}

const emit = defineEmits<{
  (e: 'selectCourse', courseId: number, event: MouseEvent): void;
}>();

const unassignedCourses = computed(() => {
  return props.courses.filter(c => c.timeslot_id === null && !c.parent_id);
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

function getClassroomName(id: number) {
  if (!props.classrooms) return 'Salle inconnue';
  return props.classrooms.find(c => c.id === id)?.name || 'Salle inconnue';
}

function onDragStart(event: DragEvent, courseId: number) {
  if (event.dataTransfer) {
    event.dataTransfer.setData('text/plain', courseId.toString());
    event.dataTransfer.effectAllowed = 'move';
  }
}
</script>
