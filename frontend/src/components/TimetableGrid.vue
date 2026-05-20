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
              :class="{ 'drag-over': isDragOver(day.value, hour + (idx - 1) * (currentStandardDuration / 60)) }"
              @dragover.prevent="onDragOver($event, day.value, hour + (idx - 1) * (currentStandardDuration / 60))"
              @dragleave="onDragLeave(day.value, hour + (idx - 1) * (currentStandardDuration / 60))"
              @drop="onDrop($event, day.value, hour + (idx - 1) * (currentStandardDuration / 60))"
            >
              <div
                v-for="course in getCoursesAt(day.value, hour + (idx - 1) * (currentStandardDuration / 60))"
                :key="course.id"
                class="placed-course"
                :class="{ 'is-pinned-card': course.is_pinned, 'is-selected-card': (selectedCourseIds || []).includes(course.id) }"
                :style="{
                  backgroundColor: getCourseColor(course.subject),
                  height: getCourseHeight(course),
                  bottom: 'auto',
                  zIndex: 10
                }"
                draggable="true"
                @dragstart="onDragStart($event, course.id)"
                @click.stop="$emit('selectCourse', course.id)"
              >
                <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 4px;">
                  <span class="placed-subject">{{ course.subject }}</span>
                  <div style="display: flex; align-items: center; gap: 2px;">
                    <!-- Bouton de verrouillage (Pin) -->
                    <button @click.stop="$emit('togglePin', course.id)" class="pin-btn" :class="{ 'is-pinned': course.is_pinned }" :title="course.is_pinned ? 'Déverrouiller le cours' : 'Verrouiller le cours'">
                      <svg v-if="course.is_pinned" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="lock-icon">
                        <path fill-rule="evenodd" d="M12 1.5a5.25 5.25 0 0 0-5.25 5.25v3a3 3 0 0 0-3 3v6.75a3 3 0 0 0 3 3h10.5a3 3 0 0 0 3-3v-6.75a3 3 0 0 0-3-3v-3c0-2.9-2.35-5.25-5.25-5.25Zm3.75 8.25v-3a3.75 3.75 0 1 0-7.5 0v3h7.5Z" clip-rule="evenodd" />
                      </svg>
                      <svg v-else xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor" class="lock-icon">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M13.5 10.5V6.75a4.5 4.5 0 1 1 9 0v3.75M3.75 21.75h16.5a1.5 1.5 0 0 0 1.5-1.5V12a1.5 1.5 0 0 0-1.5-1.5H3.75A1.5 1.5 0 0 0 2.25 12v8.25a1.5 1.5 0 0 0 1.5 1.5Z" />
                      </svg>
                    </button>
                    <!-- Bouton de retrait rapide (Unassign) -->
                    <button @click.stop="$emit('unassign', course.id)" class="unassign-btn" title="Retirer de la grille">
                      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                </div>

                <div class="placed-meta">
                  <span v-if="viewMode !== 'teacher'">👤 {{ getTeacherName(course.teacher_id) }}</span>
                  <span v-if="viewMode !== 'division'">👥 {{ getDivisionName(course.division_id) }}</span>
                  <span v-if="viewMode !== 'classroom'">📍 {{ getClassroomName(course.classroom_id) }}</span>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- Overlay de chargement -->
      <div class="loader-overlay" v-if="loading">
        <div class="spinner"></div>
        <div style="color: #fff; font-weight: 500; font-size: 16px;">Calcul de l'emploi du temps optimal...</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { Course, Timeslot, Teacher, Division, Classroom } from '../types';

const props = defineProps<{
  courses: Course[];
  timeslots: Timeslot[];
  teachers: Teacher[];
  divisions: Division[];
  classrooms: Classroom[];
  viewMode: string;
  selectedId: number | null;
  loading: boolean;
  selectedCourseIds?: number[];
  schools?: any[];
}>();

const emit = defineEmits<{
  (e: 'move', courseId: number, timeslotId: number, classroomId: number | null): void;
  (e: 'unassign', courseId: number): void;
  (e: 'togglePin', courseId: number): void;
  (e: 'selectCourse', courseId: number): void;
}>();

const days = [
  { value: 1, label: 'Lundi' },
  { value: 2, label: 'Mardi' },
  { value: 3, label: 'Mercredi' },
  { value: 4, label: 'Jeudi' },
  { value: 5, label: 'Vendredi' },
  { value: 6, label: 'Samedi' },
];

const hours = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17];

const currentStandardDuration = ref(30);

onMounted(async () => {
  try {
    const res = await fetch('/api/generic/system_settings').then(r => r.json());
    const items = res.items || [];
    const durationSetting = items.find((item: any) => item.key === 'STANDARD_TIMESLOT_DURATION');
    currentStandardDuration.value = durationSetting ? Number(durationSetting.value) : 30;
  } catch (e) {
    console.error("Failed to load standard timeslot duration", e);
  }
});

const subCellCount = computed(() => {
  return Math.round(60 / currentStandardDuration.value);
});

function getCourseHeight(course: Course) {
  const duration = course.duration_minutes || 30;
  const span = Math.ceil(duration / currentStandardDuration.value);
  return `calc(${span} * 100% - 8px + ${span - 1}px)`;
}

const activeDragCells = ref<Record<string, boolean>>({});

function getCellKey(day: number, hour: number): string {
  return `${day}-${hour}`;
}

function isDragOver(day: number, hour: number): boolean {
  return !!activeDragCells.value[getCellKey(day, hour)];
}

function onDragOver(event: DragEvent, day: number, hour: number) {
  activeDragCells.value[getCellKey(day, hour)] = true;
}

function onDragLeave(day: number, hour: number) {
  activeDragCells.value[getCellKey(day, hour)] = false;
}

function getTimeslot(day: number, hour: number): Timeslot | undefined {
  return props.timeslots.find(ts => ts.day_of_week === day && Math.abs(ts.hour - hour) < 0.001);
}

function getCoursesAt(day: number, hour: number): Course[] {
  const ts = getTimeslot(day, hour);
  if (!ts) return [];

  return props.courses.filter(course => {
    if (course.timeslot_id !== ts.id) return false;

    if (props.viewMode === 'division') {
      return course.division_id === props.selectedId;
    } else if (props.viewMode === 'teacher') {
      return course.teacher_id === props.selectedId;
    } else if (props.viewMode === 'classroom') {
      return course.classroom_id === props.selectedId;
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

function onDrop(event: DragEvent, day: number, hour: number) {
  activeDragCells.value[getCellKey(day, hour)] = false;
  const ts = getTimeslot(day, hour);
  if (!ts) return;

  const courseIdStr = event.dataTransfer?.getData('text/plain');
  if (!courseIdStr) return;

  const courseId = Number(courseIdStr);
  
  // Déterminer la salle
  let classroomId: number | null = null;
  if (props.viewMode === 'classroom') {
    classroomId = props.selectedId;
  } else {
    // Choisir la première salle disponible sur ce créneau
    const occupiedClassroomIds = props.courses
      .filter(c => c.timeslot_id === ts.id && c.id !== courseId)
      .map(c => c.classroom_id);
    const freeClassroom = props.classrooms.find(clr => !occupiedClassroomIds.includes(clr.id));
    classroomId = freeClassroom ? freeClassroom.id : (props.classrooms[0]?.id || null);
  }

  emit('move', courseId, ts.id, classroomId);
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
.sub-cell {
  flex: 1;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  position: relative;
  transition: all 0.2s;
  padding: 2px;
}

.sub-cell:not(:last-child) {
  border-bottom: 1px dotted var(--border-color);
}

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
