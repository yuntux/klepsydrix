<template>
  <div class="app-container">
    <!-- Header -->
    <HeaderControls
      v-model:activeTab="activeTab"
      v-model:viewMode="viewMode"
      v-model:selectedId="selectedId"
      :divisions="divisions"
      :teachers="teachers"
      :classrooms="classrooms"
      :loading="loading"
      :scoreData="scoreData"
      @solve="onSolve"
      @stop="onStopSolve"
      @reset="onReset"
    />

    <!-- Vue Emploi du Temps -->
    <main class="main-layout" v-if="activeTab === 'timetable'">
      <!-- Panneau latéral (Cours à planifier) -->
      <Sidebar
        :courses="courses"
        :teachers="teachers"
        :divisions="divisions"
        :selectedCourseIds="selectedCourseIds"
        @selectCourse="toggleCourseSelection"
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
        :selectedCourseIds="selectedCourseIds"
        @move="onMoveCourse"
        @unassign="onUnassignCourse"
        @togglePin="onTogglePinCourse"
        @selectCourse="toggleCourseSelection"
      />
    </main>

    <!-- Vue Saisie des Voeux (T024) -->
    <main class="main-layout" v-else-if="activeTab === 'preferences'">
      <PreferenceGrid
        :teachers="teachers"
        :classrooms="classrooms"
        :divisions="divisions"
        :timeslots="timeslots"
      />
    </main>

    <!-- Vue Gestion du Socle (CRUD Générique) -->
    <main class="main-layout admin-layout" v-else>
      <!-- Barre latérale de choix de la ressource -->
      <aside class="app-sidebar admin-sidebar">
        <div class="sidebar-header">
          <h2 class="sidebar-title">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="icon-title">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.43l-1.003.828c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.43l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128c.332-.183.582-.495.644-.869l.214-1.28Z" />
              <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
            </svg>
            Données du Socle
          </h2>
        </div>
        <div class="admin-menu-list">
          <button
            v-for="model in adminModels"
            :key="model.key"
            class="admin-menu-btn"
            :class="{ active: activeAdminModel === model.key }"
            @click="activeAdminModel = model.key"
          >
            {{ model.label }}
          </button>
        </div>
      </aside>

      <!-- Zone de liste générique -->
      <section class="admin-main-content">
        <div v-if="genericLoading" class="loader-container">
          <div class="spinner"></div>
          <span>Chargement en cours...</span>
        </div>
        <GenericList
          v-else
          :title="adminModels.find(m => m.key === activeAdminModel)?.label || ''"
          :columns="columnsConfig"
          :fields="formFieldsConfig"
          :items="genericItems"
          @add="onAddGeneric"
          @edit="onEditGeneric"
          @delete="onDeleteGeneric"
          @update-item="onUpdateGenericInline"
        />
      </section>
    </main>

    <!-- Modal Formulaire Générique -->
    <GenericForm
      v-if="showFormModal"
      :title="formTitle"
      :fields="formFieldsConfig"
      v-model="formModel"
      @submit="onSubmitGeneric"
      @cancel="showFormModal = false"
    />

    <!-- Boîte de dialogue de confirmation d'impact de dépositionnement (T018b) -->
    <ImpactConfirmDialog
      :show="showImpactModal"
      :title="impactModalTitle"
      :impactedCount="impactedSessionsCount"
      :impactedSessions="impactedSessions"
      @confirm="onConfirmImpactDelete"
      @cancel="showImpactModal = false"
    />

    <!-- Fiche T Cumulée (T020) -->
    <CoursePopin
      :show="selectedCourseIds.length > 0"
      :courses="courses.filter(c => selectedCourseIds.includes(c.id))"
      :teachers="teachers"
      :divisions="divisions"
      :classrooms="classrooms"
      :timeslots="timeslots"
      @close="selectedCourseIds = []"
    />

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
            {{ notif.type === 'error' ? 'Alerte' : 'Succès' }}
          </div>
          <div class="notification-desc">{{ notif.message }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue';
import HeaderControls from './components/HeaderControls.vue';
import Sidebar from './components/Sidebar.vue';
import TimetableGrid from './components/TimetableGrid.vue';
import GenericList from './components/GenericList.vue';
import GenericForm from './components/GenericForm.vue';
import ImpactConfirmDialog from './components/ImpactConfirmDialog.vue';
import CoursePopin from './components/CoursePopin.vue';
import PreferenceGrid from './components/PreferenceGrid.vue';
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

const selectedCourseIds = ref<number[]>([]);

function toggleCourseSelection(id: number) {
  if (selectedCourseIds.value.includes(id)) {
    selectedCourseIds.value = selectedCourseIds.value.filter(x => x !== id);
  } else {
    selectedCourseIds.value.push(id);
  }
}

// Onglet actif
const activeTab = ref<string>('timetable');

// Administration
const adminModels = [
  { key: 'schools', label: '🏫 Établissements' },
  { key: 'disciplines', label: '📚 Disciplines' },
  { key: 'subjects', label: '📖 Matières' },
  { key: 'teachers', label: '👨‍🏫 Enseignants' },
  { key: 'divisions', label: '🎒 Classes (Divisions)' },
  { key: 'classrooms', label: '🏢 Salles' },
  { key: 'materials', label: '🛠️ Matériels' },
  { key: 'missions', label: '🎯 Missions' },
  { key: 'election_methods', label: '🗳️ Méthodes d\'élection' },
  { key: 'periods', label: '📅 Périodes' }
];
const activeAdminModel = ref('schools');
const genericItems = ref<any[]>([]);
const genericLoading = ref(false);
const schoolsList = ref<any[]>([]);

// États pour la boîte de dialogue de confirmation d'impact
const showImpactModal = ref(false);
const impactModalTitle = ref('');
const impactedSessionsCount = ref(0);
const impactedSessions = ref<any[]>([]);
const pendingDeleteCallback = ref<(() => Promise<void>) | null>(null);

const modelToResourceType: Record<string, string> = {
  teachers: 'Teacher',
  classrooms: 'Classroom',
  divisions: 'Division',
  schools: 'School',
};

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

const scoreData = ref<{ hard_score: number; soft_score: number; summary: string; matches: Record<string, { hard: number; soft: number; count: number }> } | null>(null);

// Chargement initial des données
async function loadData() {
  try {
    const data = await api.fetchTimetable();
    courses.value = data.courses;
    timeslots.value = data.timeslots;
    teachers.value = data.teachers;
    divisions.value = data.divisions;
    classrooms.value = data.classrooms;

    updateDefaultSelection();

    try {
      scoreData.value = await api.fetchTimetableScore();
    } catch (e) {
      console.error("Score could not be fetched", e);
    }
  } catch (err: any) {
    showNotification('error', err.message || 'Impossible de charger les données');
  }
}

async function loadSchools() {
  try {
    const res = await api.fetchGenericList('schools', 0, 1000);
    schoolsList.value = res.items;
  } catch (e) {
    console.error("Échec du chargement des écoles", e);
  }
}

async function loadGenericItems() {
  genericLoading.value = true;
  try {
    const res = await api.fetchGenericList(activeAdminModel.value, 0, 1000);
    genericItems.value = res.items;
  } catch (err: any) {
    showNotification('error', err.message || 'Erreur lors du chargement des ressources');
  } finally {
    genericLoading.value = false;
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

// Watchers
watch(viewMode, () => {
  updateDefaultSelection();
});

watch(activeAdminModel, () => {
  if (activeTab.value === 'admin') {
    loadGenericItems();
  }
});

watch(activeTab, (newVal) => {
  if (newVal === 'admin') {
    loadGenericItems();
  } else {
    loadData();
  }
});

// Modal CRUD générique
const showFormModal = ref(false);
const formTitle = ref('');
const formModel = ref<Record<string, any>>({});
const isEditing = ref(false);

function onAddGeneric() {
  formTitle.value = `Ajouter un élément`;
  formModel.value = {};
  isEditing.value = false;
  showFormModal.value = true;
}

function onEditGeneric(item: any) {
  formTitle.value = `Modifier l'élément`;
  formModel.value = { ...item };
  isEditing.value = true;
  showFormModal.value = true;
}

async function onSubmitGeneric(value: Record<string, any>) {
  try {
    if (isEditing.value) {
      await api.updateGenericItem(activeAdminModel.value, value.id, value);
      showNotification('success', 'Ressource modifiée avec succès !');
    } else {
      await api.createGenericItem(activeAdminModel.value, value);
      showNotification('success', 'Ressource créée avec succès !');
    }
    showFormModal.value = false;
    loadGenericItems();
    if (activeAdminModel.value === 'schools') {
      loadSchools();
    }
  } catch (err: any) {
    showNotification('error', err.message || 'Impossible d\'enregistrer la ressource.');
  }
}

async function onUpdateGenericInline(item: any) {
  try {
    await api.updateGenericItem(activeAdminModel.value, item.id, item);
    showNotification('success', 'Élément mis à jour directement !');
    if (activeAdminModel.value === 'schools') {
      loadSchools();
    } else if (['teachers', 'classrooms', 'divisions'].includes(activeAdminModel.value)) {
      loadData();
    }
  } catch (err: any) {
    showNotification('error', err.message || 'Échec de l\'enregistrement en ligne.');
    loadGenericItems();
  }
}

async function onDeleteGeneric(item: any) {
  const resourceType = modelToResourceType[activeAdminModel.value];
  if (resourceType) {
    try {
      const sim = await api.simulateChange("DELETE_RESOURCE", resourceType, item.id);
      if (sim.impacted_sessions_count > 0) {
        impactModalTitle.value = `Suppression de ${item.name || item.code || 'la ressource'}`;
        impactedSessionsCount.value = sim.impacted_sessions_count;
        impactedSessions.value = sim.impacted_sessions;
        showImpactModal.value = true;
        
        pendingDeleteCallback.value = async () => {
          await api.applyChange("DELETE_RESOURCE", resourceType, item.id);
          await api.deleteGenericItem(activeAdminModel.value, item.id);
          showNotification('success', 'Ressource supprimée et séances dépositionnées avec succès !');
          loadGenericItems();
          loadTimetableData();
        };
        return;
      }
    } catch (err: any) {
      console.error("Simulation error", err);
    }
  }

  if (confirm(`Êtes-vous sûr de vouloir supprimer définitivement cet élément ?`)) {
    try {
      await api.deleteGenericItem(activeAdminModel.value, item.id);
      showNotification('success', 'Ressource supprimée avec succès !');
      loadGenericItems();
      if (activeAdminModel.value === 'schools') {
        loadSchools();
      }
    } catch (err: any) {
      showNotification('error', err.message || 'Échec de la suppression de la ressource.');
    }
  }
}

async function onConfirmImpactDelete() {
  showImpactModal.value = false;
  if (pendingDeleteCallback.value) {
    try {
      await pendingDeleteCallback.value();
    } catch (err: any) {
      showNotification('error', err.message || 'Échec de l\'opération de suppression.');
    } finally {
      pendingDeleteCallback.value = null;
    }
  }
}

// Configurations dynamiques de colonnes pour GenericList
const columnsConfig = computed(() => {
  const model = activeAdminModel.value;
  if (model === 'schools') {
    return [
      { key: 'uai', label: 'UAI (RNE)', width: 120 },
      { key: 'name', label: 'Nom de l\'établissement', width: 250 },
      { key: 'standard_timeslot_duration', label: 'Durée créneau (min)', width: 150 }
    ];
  } else if (model === 'disciplines') {
    return [
      { key: 'code', label: 'Code', width: 150 },
      { key: 'name', label: 'Nom de la discipline', width: 300 }
    ];
  } else if (model === 'subjects') {
    return [
      { key: 'code', label: 'Code', width: 120 },
      { key: 'code_nomenclature', label: 'Code Nomenclature', width: 150 },
      { key: 'short_label', label: 'Libellé Court', width: 150 },
      { key: 'long_label', label: 'Libellé Long', width: 250 },
      { key: 'color', label: 'Couleur', width: 120 },
      { key: 'is_etp', label: 'Est ETP', width: 100 },
      { key: 'is_specialty', label: 'Spécialité', width: 120 },
      { key: 'pedagogic_weight', label: 'Poids Péd.', width: 120 }
    ];
  } else if (model === 'teachers') {
    return [
      { key: 'code', label: 'Code', width: 120 },
      { key: 'first_name', label: 'Prénom', width: 150 },
      { key: 'last_name', label: 'Nom', width: 150 },
      { key: 'name', label: 'Nom Complet', width: 200 },
      { key: 'max_weekly_hours', label: 'Heures Max', width: 120 }
    ];
  } else if (model === 'divisions') {
    return [
      { key: 'code', label: 'Code', width: 120 },
      { key: 'name', label: 'Nom', width: 150 },
      { key: 'student_count', label: 'Nombre d\'élèves', width: 150 },
      { key: 'color', label: 'Couleur', width: 120 }
    ];
  } else if (model === 'classrooms') {
    return [
      { key: 'code', label: 'Code', width: 120 },
      { key: 'name', label: 'Nom', width: 150 },
      { key: 'capacity', label: 'Capacité', width: 120 },
      { key: 'quantity', label: 'Quantité', width: 120 }
    ];
  } else if (model === 'materials') {
    return [
      { key: 'code', label: 'Code', width: 150 },
      { key: 'name', label: 'Nom du matériel', width: 250 },
      { key: 'quantity', label: 'Quantité', width: 120 }
    ];
  } else if (model === 'missions') {
    return [
      { key: 'code', label: 'Code', width: 150 },
      { key: 'name', label: 'Nom de la mission', width: 300 }
    ];
  } else if (model === 'election_methods') {
    return [
      { key: 'code', label: 'Code', width: 150 },
      { key: 'name', label: 'Nom de la méthode', width: 300 }
    ];
  } else if (model === 'periods') {
    return [
      { key: 'code', label: 'Code', width: 120 },
      { key: 'name', label: 'Nom de la période', width: 200 },
      { key: 'start_date', label: 'Date Début', width: 150 },
      { key: 'end_date', label: 'Date Fin', width: 150 }
    ];
  }
  return [];
});

// Configurations dynamiques de champs pour GenericForm
const formFieldsConfig = computed(() => {
  const model = activeAdminModel.value;
  const schoolOptions = schoolsList.value.map(s => ({ value: s.id, label: s.name }));

  if (model === 'schools') {
    return [
      { key: 'uai', label: 'Code UAI (RNE)', type: 'text', required: true, placeholder: 'ex: 0750001A' },
      { key: 'name', label: 'Nom de l\'établissement', type: 'text', required: true, placeholder: 'ex: Collège Jean Jaurès' },
      { key: 'standard_timeslot_duration', label: 'Durée standard de créneau (min)', type: 'number', required: true, min: 5, max: 120, step: '5' }
    ];
  } else if (model === 'disciplines') {
    return [
      { key: 'code', label: 'Code de la discipline', type: 'text', required: true, placeholder: 'ex: L0100' },
      { key: 'name', label: 'Nom complet', type: 'text', required: true, placeholder: 'ex: Mathématiques' }
    ];
  } else if (model === 'subjects') {
    return [
      { key: 'code', label: 'Code de la matière', type: 'text', required: true, placeholder: 'ex: MATHS' },
      { key: 'code_nomenclature', label: 'Code nomenclature', type: 'text', placeholder: 'ex: 006600' },
      { key: 'short_label', label: 'Libellé court', type: 'text', required: true, placeholder: 'ex: Maths' },
      { key: 'long_label', label: 'Libellé long', type: 'text', placeholder: 'ex: Mathématiques' },
      { key: 'color', label: 'Code couleur', type: 'color', placeholder: 'ex: #3498DB' },
      { key: 'is_etp', label: 'Matière ETP', type: 'boolean' },
      { key: 'is_specialty', label: 'Matière de Spécialité', type: 'boolean' },
      { key: 'pedagogic_weight', label: 'Poids Pédagogique', type: 'number', min: 0.1, max: 10, step: '0.1' }
    ];
  } else if (model === 'teachers') {
    return [
      { key: 'code', label: 'Code Enseignant', type: 'text', required: true, placeholder: 'ex: T1' },
      { key: 'first_name', label: 'Prénom', type: 'text', placeholder: 'ex: Marc' },
      { key: 'last_name', label: 'Nom de famille', type: 'text', placeholder: 'ex: Dupont' },
      { key: 'name', label: 'Nom d\'usage complet', type: 'text', required: true, placeholder: 'ex: M. Dupont' },
      { key: 'max_weekly_hours', label: 'Heures max hebdomadaires', type: 'number', min: 1, max: 40, step: '0.5' },
      { key: 'school_id', label: 'Établissement Principal', type: 'select', required: true, options: schoolOptions }
    ];
  } else if (model === 'divisions') {
    return [
      { key: 'code', label: 'Code de la classe', type: 'text', required: true, placeholder: 'ex: 6EME_A' },
      { key: 'name', label: 'Nom de la classe', type: 'text', required: true, placeholder: 'ex: 6ème A' },
      { key: 'student_count', label: 'Nombre d\'élèves', type: 'number', required: true, min: 1, max: 50 },
      { key: 'color', label: 'Couleur', type: 'color', placeholder: 'ex: #3498DB' },
      { key: 'school_id', label: 'Établissement', type: 'select', required: true, options: schoolOptions }
    ];
  } else if (model === 'classrooms') {
    return [
      { key: 'code', label: 'Code de la salle', type: 'text', required: true, placeholder: 'ex: S101' },
      { key: 'name', label: 'Nom de la salle', type: 'text', required: true, placeholder: 'ex: Salle 101' },
      { key: 'capacity', label: 'Capacité de places', type: 'number', required: true, min: 1, max: 200 },
      { key: 'quantity', label: 'Quantité', type: 'number', required: true, min: 1, max: 10 },
      { key: 'school_id', label: 'Établissement', type: 'select', required: true, options: schoolOptions }
    ];
  } else if (model === 'materials') {
    return [
      { key: 'code', label: 'Code du matériel', type: 'text', required: true, placeholder: 'ex: IPAD' },
      { key: 'name', label: 'Nom du matériel', type: 'text', required: true, placeholder: 'ex: Valise iPad Pro' },
      { key: 'quantity', label: 'Quantité disponible', type: 'number', required: true, min: 1, max: 500 }
    ];
  } else if (model === 'missions') {
    return [
      { key: 'code', label: 'Code de la mission', type: 'text', required: true, placeholder: 'ex: PP' },
      { key: 'name', label: 'Nom complet', type: 'text', required: true, placeholder: 'ex: Professeur Principal' }
    ];
  } else if (model === 'election_methods') {
    return [
      { key: 'code', label: 'Code de la méthode', type: 'text', required: true, placeholder: 'ex: STS' },
      { key: 'name', label: 'Nom de la méthode', type: 'text', required: true, placeholder: 'ex: STSWEB' }
    ];
  } else if (model === 'periods') {
    return [
      { key: 'code', label: 'Code de la période', type: 'text', required: true, placeholder: 'ex: S1' },
      { key: 'name', label: 'Nom de la période', type: 'text', required: true, placeholder: 'ex: Semestre 1' },
      { key: 'start_date', label: 'Date de début', type: 'date', required: true },
      { key: 'end_date', label: 'Date de fin', type: 'date', required: true }
    ];
  }
  return [];
});

const constraintTranslations: Record<string, string> = {
  "Teacher conflict": "Ce déplacement crée un conflit d'emploi du temps pour le professeur.",
  "Classroom conflict": "Ce déplacement crée une double réservation pour cette salle.",
  "Division conflict": "Ce déplacement crée un conflit pour cette classe (ils ont déjà cours).",
  "Minimize timetable disruption": "Vous avez éloigné le cours de son créneau d'origine.",
  "Teacher room stability": "Ce déplacement oblige le professeur à changer de salle.",
  "Student group subject variety": "Ce déplacement force les élèves à suivre deux cours de suite de la même matière.",
  "Teacher time efficiency": "Ce déplacement crée un 'trou' dans l'emploi du temps du professeur.",
  "Division time efficiency": "Ce déplacement crée un 'trou' dans l'emploi du temps des élèves."
};

// Actualisation centralisée du score
async function refreshScoreAndNotify(oldScore: any, actionName: string = 'Modification appliquée') {
  try {
    const newScore = await api.fetchTimetableScore();
    scoreData.value = newScore;
    
    if (!oldScore) {
      showNotification('success', actionName);
      return;
    }
    
    if (newScore.hard_score < oldScore.hard_score || newScore.soft_score < oldScore.soft_score) {
      let brokenRule = "Le planning a été dégradé.";
      if (newScore.matches) {
        for (const [ruleName, detail] of Object.entries(newScore.matches)) {
          const oldDetail = oldScore.matches?.[ruleName] || { count: 0 };
          if (detail.count > oldDetail.count) {
             brokenRule = constraintTranslations[ruleName] || `Règle enfreinte : ${ruleName}`;
             break;
          }
        }
      }
      
      if (newScore.hard_score < oldScore.hard_score) {
        showNotification('error', `🚨 Attention : ${brokenRule}`);
      } else {
        showNotification('error', `⚠️ Info : ${brokenRule}`);
      }
    } else if (newScore.hard_score > oldScore.hard_score || newScore.soft_score > oldScore.soft_score) {
      showNotification('success', `✨ Amélioration du planning ! Nouveau score : ${newScore.hard_score}H / ${newScore.soft_score}S.`);
    } else {
      showNotification('success', actionName);
    }
  } catch (e) {
    console.error("Score could not be fetched", e);
    showNotification('success', actionName);
  }
}

// Actions de planification
async function onMoveCourse(courseId: number, timeslotId: number, classroomId: number | null) {
  const previousCoursesState = JSON.parse(JSON.stringify(courses.value));
  const oldScore = scoreData.value ? { ...scoreData.value } : null;
  
  const courseIndex = courses.value.findIndex(c => c.id === courseId);
  const courseObj = courseIndex !== -1 ? courses.value[courseIndex] : null;
  
  if (courseIndex !== -1) {
    courses.value[courseIndex].timeslot_id = timeslotId;
    courses.value[courseIndex].classroom_id = classroomId;
  }

  try {
    await api.updateCourse(courseId, timeslotId, classroomId);
    await refreshScoreAndNotify(oldScore, 'Le cours a été planifié avec succès.');
    
    // Alerte en cas de placement sur un créneau indisponible (Rouge / Unsuited) - T025b
    if (courseObj) {
      try {
        const prefRes = await fetch(`/api/timetable/preferences`).then(res => res.json());
        const unsuitedPref = prefRes.find((p: any) => 
          p.timeslot_id === timeslotId && 
          p.preference_level === 'Unsuited' && (
            (p.resource_type === 'Teacher' && p.resource_id === courseObj.teacher_id) ||
            (p.resource_type === 'Classroom' && p.resource_id === classroomId) ||
            (p.resource_type === 'Division' && p.resource_id === courseObj.division_id)
          )
        );
        if (unsuitedPref) {
          showNotification('error', `🚨 Alerte : Créneau verrouillé ou indisponible (Rouge) pour cette ressource !`);
        }
      } catch (e) {
        console.warn("Could not check preferences", e);
      }
    }
  } catch (err: any) {
    courses.value = previousCoursesState;
    showNotification('error', err.message || 'Créneau horaire ou salle indisponible.');
  }
}

async function onUnassignCourse(courseId: number) {
  const previousCoursesState = JSON.parse(JSON.stringify(courses.value));
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

async function onTogglePinCourse(courseId: number) {
  const previousCoursesState = JSON.parse(JSON.stringify(courses.value));
  const oldScore = scoreData.value ? { ...scoreData.value } : null;
  const courseIndex = courses.value.findIndex(c => c.id === courseId);
  if (courseIndex === -1) return;

  const currentPinState = courses.value[courseIndex].is_pinned;
  const newPinState = !currentPinState;

  courses.value[courseIndex].is_pinned = newPinState;

  try {
    const course = courses.value[courseIndex];
    await api.updateCourse(courseId, course.timeslot_id, course.classroom_id, newPinState);
    await refreshScoreAndNotify(oldScore, newPinState ? 'Le cours a été verrouillé.' : 'Le cours a été déverrouillé.');
  } catch (err: any) {
    courses.value = previousCoursesState;
    showNotification('error', err.message || 'Impossible de modifier le verrouillage du cours.');
  }
}

let pollingInterval: number | undefined;

async function checkStatus() {
  try {
    const res = await api.fetchTimetableStatus();
    if (res.status === 'SOLVING') {
      loading.value = true;
    } else {
      if (loading.value) {
        loading.value = false;
        loadData();
      }
    }
  } catch (err) {
    console.error('Erreur lors de la vérification du statut', err);
  }
}

async function onSolve() {
  try {
    const result = await api.solveTimetable();
    showNotification('success', result.message || 'Résolution démarrée en arrière-plan.');
    loading.value = true;
    if (!pollingInterval) {
      pollingInterval = window.setInterval(checkStatus, 2000);
    }
  } catch (err: any) {
    showNotification('error', err.message || 'Erreur lors du lancement de la résolution');
  }
}

async function onStopSolve() {
  try {
    const result = await api.stopTimetable();
    showNotification('success', result.message || 'Interruption demandée...');
  } catch (err: any) {
    showNotification('error', err.message || 'Erreur lors de l\'interruption');
  }
}

async function onReset() {
  loading.value = true;
  const oldScore = scoreData.value ? { ...scoreData.value } : null;
  try {
    await api.resetTimetable();
    courses.value.forEach(c => {
      c.timeslot_id = null;
      c.classroom_id = null;
    });
    await refreshScoreAndNotify(oldScore, 'Tous les cours ont été retirés de la grille.');
  } catch (err: any) {
    showNotification('error', err.message || 'Erreur lors de la réinitialisation');
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadData();
  loadSchools();
  checkStatus();
  if (!pollingInterval) {
    pollingInterval = window.setInterval(checkStatus, 3000);
  }
});
</script>

<style scoped>
/* Extension des styles de mise en page pour l'admin */
.admin-layout {
  display: flex;
  background-color: var(--bg-primary);
  height: calc(100vh - 70px);
}

.admin-sidebar {
  width: 280px;
  background-color: rgba(23, 28, 36, 0.7);
  border-right: 1px solid var(--border-color);
  backdrop-filter: blur(12px);
}

.admin-menu-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  overflow-y: auto;
}

.admin-menu-btn {
  background: transparent;
  border: 1px solid transparent;
  color: var(--text-secondary);
  padding: 12px 16px;
  border-radius: 8px;
  cursor: pointer;
  text-align: left;
  font-family: var(--font-sans);
  font-size: 14px;
  font-weight: 600;
  transition: all var(--transition-fast);
  display: flex;
  align-items: center;
}

.admin-menu-btn:hover {
  color: #fff;
  background-color: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.05);
}

.admin-menu-btn.active {
  color: #fff;
  background-color: rgba(99, 102, 241, 0.15);
  border-color: rgba(99, 102, 241, 0.3);
}

.icon-title {
  width: 18px;
  height: 18px;
  margin-right: 8px;
  color: var(--accent-primary);
}

.admin-main-content {
  flex: 1;
  padding: 24px;
  overflow: hidden;
  position: relative;
}

.loader-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
  gap: 16px;
}
</style>
