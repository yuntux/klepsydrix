<template>
  <div class="app-container">
    <!-- Header -->
    <HeaderControls
      v-model:viewMode="viewMode"
      v-model:selectedId="selectedId"
      :divisions="divisions"
      :teachers="teachers"
      :classrooms="classrooms"
      :loading="loading"
      @solve="onSolve"
      @reset="onReset"
    />

    <!-- Main Content -->
    <main class="main-layout">
      <!-- Panneau latéral (Cours à planifier) -->
      <Sidebar
        :courses="courses"
        :teachers="teachers"
        :divisions="divisions"
      />

      <!-- Grille -->
      <TimetableGrid
        :courses="courses"
        :timeslots="timeslots"
        :teachers="teachers"
        :divisions="divisions"
        :classrooms="classrooms"
        :viewMode="viewMode"
        :selectedId="selectedId"
        :loading="loading"
        @move="onMoveCourse"
        @unassign="onUnassignCourse"
      />
    </main>

    <!-- Système de notifications -->
    <div class="notification-container">
      <div
        v-for="notif in notifications"
        :key="notif.id"
        class="notification"
        :class="{
          'notification-error': notif.type === 'error',
          'notification-success': notif.type === 'success'
        }"
      >
        <div>
          <div class="notification-title">
            {{ notif.type === 'error' ? 'Conflit détecté' : 'Succès' }}
          </div>
          <div class="notification-desc">{{ notif.message }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import HeaderControls from './components/HeaderControls.vue';
import Sidebar from './components/Sidebar.vue';
import TimetableGrid from './components/TimetableGrid.vue';
import { Course, Timeslot, Teacher, Division, Classroom } from './types';
import * as api from './services/api';

// États partagés
const courses = ref<Course[]>([]);
const timeslots = ref<Timeslot[]>([]);
const teachers = ref<Teacher[]>([]);
const divisions = ref<Division[]>([]);
const classrooms = ref<Classroom[]>([]);

const viewMode = ref<string>('division');
const selectedId = ref<number | null>(null);
const loading = ref<boolean>(false);

// Notifications
interface Notification {
  id: number;
  type: 'success' | 'error';
  message: string;
}
const notifications = ref<Notification[]>([]);
let notificationId = 0;

function showNotification(type: 'success' | 'error', message: string) {
  const id = ++notificationId;
  notifications.value.push({ id, type, message });
  setTimeout(() => {
    notifications.value = notifications.value.filter(n => n.id !== id);
  }, 4500);
}

// Chargement initial des données
async function loadData() {
  try {
    const data = await api.fetchTimetable();
    courses.value = data.courses;
    timeslots.value = data.timeslots;
    teachers.value = data.teachers;
    divisions.value = data.divisions;
    classrooms.value = data.classrooms;

    // Définir la sélection par défaut pour le mode actif
    updateDefaultSelection();
  } catch (err: any) {
    showNotification('error', err.message || 'Impossible de charger les données');
  }
}

function updateDefaultSelection() {
  if (viewMode.value === 'division' && divisions.value.length > 0) {
    selectedId.value = divisions.value[0].id;
  } else if (viewMode.value === 'teacher' && teachers.value.length > 0) {
    selectedId.value = teachers.value[0].id;
  } else if (viewMode.value === 'classroom' && classrooms.value.length > 0) {
    selectedId.value = classrooms.value[0].id;
  } else {
    selectedId.value = null;
  }
}

// Mettre à jour l'ID sélectionné lorsque le mode de vue change
watch(viewMode, () => {
  updateDefaultSelection();
});

// Actions de planification
async function onMoveCourse(courseId: number, timeslotId: number, classroomId: number | null) {
  // Sauvegarde de l'état précédent en cas d'erreur de validation (Revert)
  const previousCoursesState = JSON.parse(JSON.stringify(courses.value));
  
  // Appliquer le déplacement localement de manière optimiste
  const courseIndex = courses.value.findIndex(c => c.id === courseId);
  if (courseIndex !== -1) {
    courses.value[courseIndex].timeslot_id = timeslotId;
    courses.value[courseIndex].classroom_id = classroomId;
  }

  try {
    await api.updateCourse(courseId, timeslotId, classroomId);
    showNotification('success', 'Le cours a été planifié avec succès.');
  } catch (err: any) {
    // Revert en cas de conflit 409 ou autre erreur serveur
    courses.value = previousCoursesState;
    showNotification('error', err.message || 'Créneau horaire ou salle indisponible.');
  }
}

async function onUnassignCourse(courseId: number) {
  const previousCoursesState = JSON.parse(JSON.stringify(courses.value));

  // Retirer localement
  const courseIndex = courses.value.findIndex(c => c.id === courseId);
  if (courseIndex !== -1) {
    courses.value[courseIndex].timeslot_id = null;
    courses.value[courseIndex].classroom_id = null;
  }

  try {
    await api.updateCourse(courseId, null, null);
    showNotification('success', 'Le cours a été retiré de la grille.');
  } catch (err: any) {
    courses.value = previousCoursesState;
    showNotification('error', err.message || 'Impossible de retirer le cours.');
  }
}

async function onSolve() {
  loading.value = true;
  try {
    const result = await api.solveTimetable();
    courses.value = result.courses;
    showNotification('success', 'Résolution optimale calculée avec succès par le moteur Timefold !');
  } catch (err: any) {
    showNotification('error', err.message || 'Erreur lors de la résolution automatique');
  } finally {
    loading.value = false;
  }
}

async function onReset() {
  loading.value = true;
  try {
    await api.resetTimetable();
    // Vider localement
    courses.value.forEach(c => {
      c.timeslot_id = null;
      c.classroom_id = null;
    });
    showNotification('success', 'Tous les cours ont été retirés de la grille.');
  } catch (err: any) {
    showNotification('error', err.message || 'Erreur lors de la réinitialisation');
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadData();
});
</script>
