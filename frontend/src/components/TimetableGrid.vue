<template>
  <div class="timetable-grid-wrapper" style="height: 100%; display: flex; flex-direction: column;">
    <GridContainer
      preferenceMode="readonly"
      :showSidebar="true"
      :schools="schools"
      :teachers="teachers"
      :divisions="divisions"
      :classrooms="classrooms"
      :schoolId="schoolId"
      @update:schoolId="$emit('update:schoolId', $event)"
      :periodTypes="periodTypes"
      :periods="periods"
      :periodTypeId="periodTypeId"
      @update:periodTypeId="$emit('update:periodTypeId', $event)"
      :periodIds="periodIds"
      @update:periodIds="$emit('update:periodIds', $event)"
      :viewMode="viewMode"
      @update:viewMode="$emit('update:viewMode', $event)"
      :selectedIds="selectedIds"
      @update:selectedIds="$emit('update:selectedIds', $event)"
      :weekType="weekType"
      @update:weekType="$emit('update:weekType', $event)"
      :hideResourceSelectors="false"
      :hideSchoolSelector="false"
      v-model:isDetailedView="isDetailedView"
    >
      <template #actions>
        <div class="controls-group" style="display: flex; gap: 12px; align-items: center;">
          <div class="score-pill" :class="{ 'score-perfect': scoreData && scoreData.hard_score === 0 && scoreData.soft_score === 0, 'score-warning': scoreData && (scoreData.hard_score < 0 || scoreData.soft_score < 0) }" :title="scoreData ? scoreData.summary : 'En attente...'">
            Score: {{ scoreData ? scoreData.hard_score : '?' }}H / {{ scoreData ? scoreData.soft_score : '?' }}S
          </div>

          <button class="btn btn-secondary" @click="$emit('reset')" :disabled="loading">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" width="16" height="16">
              <path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
            </svg>
            Réinitialiser
          </button>

          <button v-if="!loading" class="btn btn-primary" @click="$emit('solve')">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" width="16" height="16">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904 9 21l8.982-11.795M20.614 4c-.754.902-1.455 1.89-2.115 2.948m-2.115 2.948c-.07.112-.14.224-.21.336m-2.285 3.655A17.228 17.228 0 0 1 8.134 16m-4.82-4.48A17.185 17.185 0 0 1 11.25 8.134m0 0a17.185 17.185 0 0 1 4.82 4.48M11.25 8.134a17.228 17.228 0 0 1 4.82 4.48M11.25 8.134a17.228 17.228 0 0 0-3.116 7.866m0 0a17.22 17.22 0 0 0-4.819-4.48M12 8.5c.5-1 1.5-1.5 2.5-1.5s2 1 2.5 2c.5 1 .5 2-1 3.5s-2.5 2-3 3.5m0-7.5c-1-1-1.5-2.5-1.5-4s1-3 2.5-3s2.5 1.5 2.5 3c0 1.5-.5 3-1.5 4" />
            </svg>
            Résolution Auto
          </button>

          <button v-else class="btn btn-danger" @click="$emit('stop-solve')">
            <span class="spinner-small"></span>
            Arrêter
          </button>
        </div>
      </template>
      
      <template #sidebar>
        <Sidebar
          :courses="courses"
          :teachers="teachers"
          :divisions="divisions"
          :classrooms="classrooms"
          :selectedCourseIds="selectedCourseIds"
          :currentStandardDuration="currentStandardDuration"
          @selectCourse="$emit('selectCourse', $event)"
        />
      </template>

      <template #grid-content>
        <BaseGrid
          :dragOverCells="activeDragCells"
          @cell-dragover="onDragOver"
          @cell-dragleave="onDragLeave"
          @cell-drop="onDrop"
          style="height: 100%; border: none; border-radius: 0;"
        >
          <!-- Slot de contenu (Foreground) -->
          <template #cell-content="{ day, time }">
            <CourseCard
              v-for="course in getCoursesAt(day, time)"
              :key="course.id"
              :course="course"
              :isPlaced="true"
              :isSelected="(selectedCourseIds || []).includes(course.id)"
              :backgroundColor="getCourseColor(course.subject)"
              :height="getCourseHeight(course)"
              :teachersText="(viewMode !== 'teacher' || selectedIds.length > 1) ? (course.teacher_ids ? course.teacher_ids.map(id => getTeacherName(id)).join(', ') : '') : ''"
              :divisionsText="(viewMode !== 'division' || selectedIds.length > 1) ? (course.division_ids ? course.division_ids.map(id => getDivisionName(id)).join(', ') : '') : ''"
              :classroomsText="(viewMode !== 'classroom' || selectedIds.length > 1) ? (course.classroom_ids ? course.classroom_ids.map(id => getClassroomName(id)).join(', ') : '') : ''"
              @dragstart="onDragStart"
              @click="$emit('selectCourse', $event)"
              @togglePin="$emit('togglePin', $event)"
              @unassign="$emit('unassign', $event)"
            />
          </template>

          <!-- Overlay de chargement -->
          <template #overlay>
            <div class="loader-overlay" v-if="loading">
              <div class="spinner"></div>
              <div style="color: #fff; font-weight: 500; font-size: 16px;">Calcul de l'emploi du temps optimal...</div>
            </div>
          </template>
        </BaseGrid>
      </template>
    </GridContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { Course, Timeslot, Teacher, NonTeachingStaff, Division, Classroom } from '../types';
import BaseGrid from './BaseGrid.vue';
import GridContainer from './GridContainer.vue';
import Sidebar from './Sidebar.vue';
import CourseCard from './CourseCard.vue';
import { useTimeslotGrid } from '../composables/useTimeslotGrid';

const props = defineProps<{
  courses: Course[];
  timeslots: Timeslot[];
  teachers: Teacher[];
  nonTeachingStaffs: NonTeachingStaff[];
  divisions: Division[];
  classrooms: Classroom[];
  viewMode: string;
  selectedIds: number[];
  weekType?: 'W' | 'A' | 'B';
  loading: boolean;
  selectedCourseIds?: number[];
  schools?: any[];
  schoolId?: number | null;
  scoreData?: any;
  periodTypes?: any[];
  periods?: any[];
  periodTypeId?: number | null;
  periodIds?: number[];
}>();

const isDetailedView = ref(false);

const emit = defineEmits<{
  (e: 'move', courseId: number, timeslotId: number): void;
  (e: 'unassign', courseId: number): void;
  (e: 'togglePin', courseId: number): void;
  (e: 'selectCourse', courseId: number): void;
  (e: 'update:viewMode', value: string): void;
  (e: 'update:selectedIds', value: number[]): void;
  (e: 'update:weekType', value: 'W' | 'A' | 'B'): void;
  (e: 'reset'): void;
  (e: 'solve'): void;
  (e: 'stop-solve'): void;
  (e: 'update:periodTypeId', value: number | null): void;
  (e: 'update:periodIds', value: number[]): void;
  (e: 'update:schoolId', value: number | null): void;
}>();

const { currentStandardDuration, getCellKey } = useTimeslotGrid();

function getCourseHeight(course: Course) {
  const duration = course.duration_minutes || 30;
  const span = duration / currentStandardDuration.value;
  return `calc(${span} * 100% - 8px + ${span - 1}px)`;
}

const activeDragCells = ref<Record<string, boolean>>({});

function onDragOver(day: number, hour: number, event: DragEvent) {
  activeDragCells.value[getCellKey(day, hour)] = true;
}

function onDragLeave(day: number, hour: number, event: DragEvent) {
  activeDragCells.value[getCellKey(day, hour)] = false;
}

function getTimeslot(day: number, hour: number): Timeslot | undefined {
  return props.timeslots.find(ts => ts.day_of_week === day && Math.abs(ts.hour - hour) < 0.001);
}

const parentIdsSet = computed(() => {
  return new Set(props.courses.map(c => c.parent_id).filter(id => id != null));
});

function getCoursesAt(day: number, hour: number): Course[] {
  const ts = getTimeslot(day, hour);
  if (!ts) return [];

  const selectedWeek = props.weekType || 'W';

  return props.courses.filter(course => {
    if (course.timeslot_id !== ts.id) return false;

    // Filtre de granularité
    if (isDetailedView.value) {
      if (parentIdsSet.value.has(course.id)) return false; // detailed: exclut les parents
    } else {
      if (course.parent_id !== null) return false; // compact: exclut les enfants
    }

    // Filtre par semaine :
    // 'W' (toutes) -> on affiche tout
    // 'A' -> on affiche les cours de semaine A ou les cours toutes semaines (W)
    // 'B' -> on affiche les cours de semaine B ou les cours toutes semaines (W)
    if (selectedWeek !== 'W') {
      const courseWeek = course.week_type || 'W';
      if (courseWeek !== 'W' && courseWeek !== selectedWeek) return false;
    }

    if (props.viewMode === 'division') {
      return course.division_ids && course.division_ids.some(id => props.selectedIds.includes(id));
    } else if (props.viewMode === 'teacher') {
      return course.teacher_ids && course.teacher_ids.some(id => props.selectedIds.includes(id));
    } else if (props.viewMode === 'classroom') {
      return course.classroom_ids && course.classroom_ids.some(id => props.selectedIds.includes(id));
    } else if (props.viewMode === 'non_teaching_staff') {
      return course.non_teaching_staff_ids && course.non_teaching_staff_ids.some(id => props.selectedIds.includes(id));
    }
    return false;
  });
}

function getTeacherName(id: number) {
  return props.teachers.find(t => t.id === id)?.name || 'Prof';
}

function getDivisionName(id: number) {
  return props.divisions.find(d => d.id === id)?.name || 'Classe';
}

function getClassroomName(id: number | null) {
  if (id === null) return 'Non affectée';
  return props.classrooms.find(c => c.id === id)?.name || 'Salle';
}

function onDragStart(event: DragEvent, courseId: number) {
  if (event.dataTransfer) {
    event.dataTransfer.setData('text/plain', courseId.toString());
    event.dataTransfer.effectAllowed = 'move';
  }
}

function onDrop(day: number, hour: number, event: DragEvent) {
  activeDragCells.value[getCellKey(day, hour)] = false;
  const ts = getTimeslot(day, hour);
  if (!ts) return;

  const courseIdStr = event.dataTransfer?.getData('text/plain');
  if (!courseIdStr) return;

  const courseId = Number(courseIdStr);
  
  emit('move', courseId, ts.id);
}

// Couleurs harmonieuses et contrastées pour les matières
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
</script>

<style scoped>
.unassign-btn {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
  opacity: 0.6;
}
.unassign-btn:hover {
  color: var(--accent-danger);
  background-color: rgba(239, 68, 68, 0.15);
  opacity: 1;
}
.unassign-btn svg {
  width: 12px;
  height: 12px;
}
.pin-btn {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
  opacity: 0.6;
}
.pin-btn:hover, .pin-btn.is-pinned {
  color: var(--accent-warning, #f59e0b);
  opacity: 1;
}
.pin-btn.is-pinned {
  background-color: rgba(245, 158, 11, 0.15);
}
.lock-icon {
  width: 12px;
  height: 12px;
}
.placed-course.is-pinned-card {
  border-left: 3px solid var(--accent-warning, #f59e0b) !important;
}
</style>
