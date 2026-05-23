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
        :backgroundColor="getCourseColor(course.subject)"
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

const subjectColors: Record<string, string> = {
  'Mathématiques': 'rgba(99, 102, 241, 0.25)', // Indigo
  'Français': 'rgba(236, 72, 153, 0.25)', // Pink
  'Histoire-Géo': 'rgba(245, 158, 11, 0.25)', // Amber
  'Sciences': 'rgba(16, 185, 129, 0.25)', // Emerald
  'Anglais': 'rgba(6, 182, 212, 0.25)', // Cyan
  'Arts Plastiques': 'rgba(139, 92, 246, 0.25)', // Purple
  'Musique': 'rgba(244, 63, 94, 0.25)', // Rose
  'Technologie': 'rgba(14, 165, 233, 0.25)', // Sky
  'E.P.S.': 'rgba(101, 163, 13, 0.25)', // Lime
  'Physique-Chimie': 'rgba(20, 184, 166, 0.25)', // Teal
  'S.V.T.': 'rgba(34, 197, 94, 0.25)', // Green
};

function getCourseColor(subject: string): string {
  return subjectColors[subject] || 'rgba(107, 114, 128, 0.25)';
}

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
