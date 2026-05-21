<template>
  <div class="app-container">
    <!-- Vue interactive principale orchestrée par NotebooksTree (T032) -->
    <NotebooksTree @change-leaf="onLeafChange">
      <template #panel="{ panel }">
        <!-- 1. Grille interactive de l'Emploi du Temps -->
        <!-- 1. Grille interactive de l'Emploi du Temps -->
        <main v-if="panel.component === 'TimetableGrid'" class="main-layout" style="height: 100vh; overflow: hidden; display: flex; flex-direction: column;">
          <TimetableGrid
            :courses="courses"
            :timeslots="timeslots"
            :teachers="teachers"
            :divisions="divisions"
            :classrooms="classrooms"
            :schools="schoolsList"
            v-model:viewMode="viewMode"
            v-model:selectedIds="selectedIds"
            v-model:weekType="weekType"
            :loading="loading"
            :scoreData="scoreData"
            :selectedCourseIds="selectedCourseIds"
            @move="onMoveCourse"
            @unassign="onUnassignCourse"
            @togglePin="onTogglePinCourse"
            @selectCourse="toggleCourseSelection"
            @solve="onSolve"
            @stop-solve="onStopSolve"
            @reset="onReset"
          />
        </main>

        <!-- 2. Grille interactive de saisie des vœux -->
        <main v-else-if="panel.component === 'PreferenceGrid'" class="main-layout">
          <PreferenceGrid
            :teachers="teachers"
            :classrooms="classrooms"
            :divisions="divisions"
            :timeslots="timeslots"
            :schools="schoolsList"
            :resourceTypeProp="activeAdminModel === 'teachers' ? 'Teacher' : (activeAdminModel === 'classrooms' ? 'Classroom' : (activeAdminModel === 'divisions' ? 'Division' : 'Teacher'))"
            :resourceIdProp="selectedParentIds && selectedParentIds.length === 1 ? selectedParentIds[0] : (formModel && formModel.id ? formModel.id : null)"
            :resourceIdsProp="selectedParentIds || []"
            :hideSelectors="['teachers_preferences_tab', 'classrooms_preferences_tab', 'divisions_preferences_tab'].includes(activeLeaf?.id)"
          />
        </main>

        <!-- 3. Composant Liste Générique introspectif -->
        <section v-else-if="panel.component === 'GenericList'" class="admin-main-content">
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
            :listConfig="panel.listConfig"
            @add="onAddGeneric"
            @edit="onEditGeneric"
            @delete="onDeleteGeneric"
            @update-item="onUpdateGenericInline"
            @row-click="onRowClickGeneric"
            @selection-change="onSelectionChangeGeneric"
          />
        </section>

        <!-- 4bis. Composant de gestion des transitions de periodes -->
        <div v-else-if="panel.component === 'PeriodTransitionManager'" class="panel-content-wrapper inline-form-panel">
          <PeriodTransitionManager
            :periodTypeId="selectedParentIds && selectedParentIds.length === 1 ? selectedParentIds[0] : null"
            :schools="schoolsList"
            @change="loadGenericItems"
          />
        </div>

        <!-- 4. Composant Formulaire Générique Inline -->
        <div v-else-if="panel.component === 'GenericForm'" class="panel-content-wrapper inline-form-panel">
          <div v-if="selectedParentIds.length === 0" class="pref-placeholder">
            <div class="placeholder-icon">👈</div>
            <div class="placeholder-title">Sélectionnez un élément</div>
            <div class="placeholder-subtitle">
              {{ panel.placeholderText || "Veuillez choisir un élément dans la liste de gauche." }}
            </div>
          </div>
          <GenericForm
            v-else
            :title="inlineFormTitle"
            :fields="getFormFieldsConfig(panel.resourceKey)"
            v-model="formModel"
            :inline="true"
            :formConfig="panel.formConfig"
            :selectedRecords="selectedRelatedRecords"
            @submit="onSubmitGeneric"
            @delete="onDeleteGeneric"
          />
        </div>
      </template>
    </NotebooksTree>

    <!-- Modal Formulaire Générique Fallback -->
    <GenericForm
      v-if="showFormModal"
      :title="formTitle"
      :fields="formFieldsConfig"
      v-model="formModel"
      :selectedRecords="selectedRelatedRecords"
      @submit="onSubmitGeneric"
      @cancel="showFormModal = false"
      @delete="onDeleteGeneric"
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
import Sidebar from './components/Sidebar.vue';
import TimetableGrid from './components/TimetableGrid.vue';
import GridContainer from './components/GridContainer.vue';
import GenericList from './components/GenericList.vue';
import GenericForm from './components/GenericForm.vue';
import ImpactConfirmDialog from './components/ImpactConfirmDialog.vue';
import CoursePopin from './components/CoursePopin.vue';
import PreferenceGrid from './components/PreferenceGrid.vue';
import PeriodTransitionManager from './components/PeriodTransitionManager.vue';
import NotebooksTree from './components/NotebooksTree.vue';
import { Course, Timeslot, Teacher, Division, Classroom } from './types';
import * as api from './services/api';

// États partagés
const courses = ref<Course[]>([]);
const timeslots = ref<Timeslot[]>([]);
const teachers = ref<Teacher[]>([]);
const divisions = ref<Division[]>([]);
const classrooms = ref<Classroom[]>([]);

const viewMode = ref<string>('division');
const selectedIds = ref<number[]>([]);
const weekType = ref<'W' | 'A' | 'B'>('W');
const loading = ref<boolean>(false);

const selectedCourseIds = ref<number[]>([]);

function toggleCourseSelection(id: number) {
  if (selectedCourseIds.value.includes(id)) {
    selectedCourseIds.value = selectedCourseIds.value.filter(x => x !== id);
  } else {
    selectedCourseIds.value.push(id);
  }
}

// Onglet actif et configuration des Notebooks (T032)
const activeTab = ref<string>('timetable');
const activeLeaf = ref<any>(null);

const isInlineMode = computed(() => {
  if (!activeLeaf.value || !activeLeaf.value.panels) return false;
  return activeLeaf.value.panels.some((p: any) => p.component === 'GenericForm');
});

const isListEditableInline = computed(() => {
  if (!activeLeaf.value || !activeLeaf.value.panels) return false;
  const listPanel = activeLeaf.value.panels.find((p: any) => p.component === 'GenericList');
  if (!listPanel) return false;
  return listPanel.listConfig?.editableInline !== false;
});

const inlineFormTitle = computed(() => {
  return isEditing.value ? `Modifier l'élément` : `Ajouter un élément`;
});

function onLeafChange(leaf: any) {
  activeLeaf.value = leaf;
  
  if (leaf.id === 'timetable_root') {
    activeTab.value = 'timetable';
  } else {
    activeTab.value = 'admin';
  }

  // Si l'onglet actif est une feuille administrative avec une ressource
  if (leaf.panels) {
    const listPanel = leaf.panels.find((p: any) => p.component === 'GenericList');
    if (listPanel && listPanel.resourceKey) {
      activeAdminModel.value = listPanel.resourceKey;
      loadGenericItems();
      
      // Réinitialiser le formulaire inline et la sélection
      formModel.value = {};
      isEditing.value = false;
      selectedParentIds.value = [];
    }
  }
}

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
  { key: 'periods', label: '📅 Périodes' },
  { key: 'period_types', label: '🏷️ Types de périodes' },
  { key: 'system_settings', label: '⚙️ Configuration globale' }
];
const activeAdminModel = ref('schools');
const genericItems = ref<any[]>([]);
const genericLoading = ref(false);
const schoolsList = ref<any[]>([]);
const periodTypesList = ref<any[]>([]);
const globalTimeslotDuration = ref(30);

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
  resource_constraints: 'ResourceConstraint',
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

async function loadPeriodTypes() {
  try {
    const res = await api.fetchGenericList('period_types', 0, 1000);
    periodTypesList.value = res.items;
  } catch (e) {
    console.error("Échec du chargement des types de périodes", e);
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
    selectedIds.value = [divisions.value[0].id];
  } else if (viewMode.value === 'teacher' && teachers.value.length > 0) {
    selectedIds.value = [teachers.value[0].id];
  } else if (viewMode.value === 'classroom' && classrooms.value.length > 0) {
    selectedIds.value = [classrooms.value[0].id];
  } else {
    selectedIds.value = [];
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
const selectedParentIds = ref<any[]>([]);
const selectedRelatedRecords = ref<any[]>([]);

function onAddGeneric() {
  formTitle.value = `Ajouter un élément`;
  formModel.value = {};
  selectedRelatedRecords.value = [];
  isEditing.value = false;
  if (!isInlineMode.value) {
    showFormModal.value = true;
  }
}

function onEditGeneric(item: any) {
  formTitle.value = `Modifier l'élément`;
  formModel.value = { ...item };
  selectedRelatedRecords.value = [];
  isEditing.value = true;
  if (!isInlineMode.value && !isListEditableInline.value) {
    showFormModal.value = true;
  }
}

function onRowClickGeneric(item: any) {
  if (isInlineMode.value) {
    onEditGeneric(item);
  }
}

async function onSelectionChangeGeneric(ids: any[]) {
  selectedParentIds.value = ids;
  const formPanel = activeLeaf.value?.panels?.find((p: any) => p.component === 'GenericForm');

  if (ids.length > 1) {
    isEditing.value = true; // Activer le mode édition pour modification groupée
    if (formPanel && formPanel.relationName) {
      try {
        const resList = await Promise.all(
          ids.map(id => api.callInstanceMethod(activeAdminModel.value, id, 'ensure_related_record', {
            args: [formPanel.relationName]
          }))
        );
        selectedRelatedRecords.value = resList.filter(Boolean);
      } catch (e) {
        console.error("Échec de la récupération des relations liées", e);
        selectedRelatedRecords.value = [];
      }
    } else {
      selectedRelatedRecords.value = ids.map(id => genericItems.value.find(x => x.id === id)).filter(Boolean);
    }
    formModel.value = {};
  } else if (ids.length === 1) {
    selectedRelatedRecords.value = [];
    const item = genericItems.value.find(x => x.id === ids[0]);
    if (item) {
      if (formPanel && formPanel.relationName) {
        try {
          const res = await api.callInstanceMethod(activeAdminModel.value, item.id, 'ensure_related_record', {
            args: [formPanel.relationName]
          });
          if (res) {
            formModel.value = { ...res };
            isEditing.value = true;
          } else {
            formModel.value = {};
            isEditing.value = false;
          }
        } catch (e) {
          console.error("Échec de la récupération de la relation liée", e);
          formModel.value = {};
          isEditing.value = false;
        }
      } else if (!isListEditableInline.value) {
        onEditGeneric(item);
      }
    }
  } else {
    selectedRelatedRecords.value = [];
    formModel.value = {};
    isEditing.value = false;
  }
}

async function onSubmitGeneric(value: Record<string, any>) {
  // Déterminer la ressource réelle en fonction de l'inline form panel, sinon fallback sur activeAdminModel
  const formPanel = activeLeaf.value?.panels?.find((p: any) => p.component === 'GenericForm');
  const targetResource = (isInlineMode.value && formPanel?.resourceKey) || activeAdminModel.value;

  try {
    if (selectedParentIds.value.length > 1) {
      if (Object.keys(value).length === 0) {
        showNotification('info', 'Aucun champ modifié n\'a été détecté.');
        return;
      }
      if (formPanel && formPanel.relationName) {
        await Promise.all(
          selectedParentIds.value.map(async (parentId) => {
            const res = await api.callInstanceMethod(activeAdminModel.value, parentId, 'ensure_related_record', {
              args: [formPanel.relationName]
            });
            if (res && res.id) {
              await api.updateGenericItem(targetResource, res.id, value);
            }
          })
        );
      } else {
        await Promise.all(
          selectedParentIds.value.map(id => api.updateGenericItem(targetResource, id, value))
        );
      }
      showNotification('success', 'Ressources modifiées en masse avec succès !');
      await loadGenericItems();
      await onSelectionChangeGeneric([...selectedParentIds.value]);
    } else if (isEditing.value) {
      await api.updateGenericItem(targetResource, value.id, value);
      showNotification('success', 'Ressource modifiée avec succès !');
      
      // Recharger la liste de gauche (activeAdminModel)
      await loadGenericItems();
      
      if (isInlineMode.value) {
        // En mode inline, on conserve l'élément sélectionné actif
        if (formPanel?.relationName && selectedParentIds.value.length === 1) {
          // Recharger le record lié au parent actuellement sélectionné
          const res = await api.callInstanceMethod(activeAdminModel.value, selectedParentIds.value[0], 'ensure_related_record', {
            args: [formPanel.relationName]
          });
          if (res) {
            formModel.value = { ...res };
            isEditing.value = true;
          }
        } else {
          const updated = genericItems.value.find(x => x.id === value.id);
          if (updated) {
            formModel.value = { ...updated };
            isEditing.value = true;
          }
        }
      } else {
        showFormModal.value = false;
        formModel.value = {};
        isEditing.value = false;
      }
    } else {
      await api.createGenericItem(targetResource, value);
      showNotification('success', 'Ressource créée avec succès !');
      
      await loadGenericItems();
      
      showFormModal.value = false;
      formModel.value = {};
      isEditing.value = false;
    }
    if (activeAdminModel.value === 'schools') {
      loadSchools();
    } else if (activeAdminModel.value === 'period_types') {
      loadPeriodTypes();
    } else if (activeAdminModel.value === 'system_settings') {
      loadTimeslotConfig();
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
    } else if (activeAdminModel.value === 'period_types') {
      loadPeriodTypes();
    } else if (activeAdminModel.value === 'system_settings') {
      loadTimeslotConfig();
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
          showFormModal.value = false;
          formModel.value = {};
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
      showFormModal.value = false;
      formModel.value = {};
      loadGenericItems();
      if (activeAdminModel.value === 'schools') {
        loadSchools();
      } else if (activeAdminModel.value === 'period_types') {
        loadPeriodTypes();
      } else if (activeAdminModel.value === 'system_settings') {
        loadTimeslotConfig();
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
      { key: 'student_start_date', label: 'Début année élèves', width: 150 },
      { key: 'student_end_date', label: 'Fin année élèves', width: 150 }
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
      { key: 'school_id', label: 'ID Établissement', width: 150 },
      { key: 'period_type_id', label: 'ID Type Période', width: 150 },
      { key: 'start_date', label: 'Date Début', width: 150 },
      { key: 'end_date', label: 'Date Fin', width: 150 }
    ];
  } else if (model === 'period_types') {
    return [
      { key: 'label', label: 'Libellé', width: 250 }
    ];
  } else if (model === 'system_settings') {
    return [
      { key: 'key', label: 'Clé du paramètre', width: 250 },
      { key: 'value', label: 'Valeur', width: 300 }
    ];
  }
  return [];
});

// Configurations dynamiques de champs pour GenericForm
function getFormFieldsConfig(resourceKey?: string) {
  const model = resourceKey || activeAdminModel.value;
  const schoolOptions = schoolsList.value.map(s => ({ value: s.id, label: s.name }));
  const periodTypeOptions = periodTypesList.value.map(pt => ({ value: pt.id, label: pt.label }));

  const defaultDuration = globalTimeslotDuration.value;
  const timeOptions: Array<{ value: string; label: string }> = [];
  let currentMinutes = 8 * 60; // 8h
  const endMinutes = 18 * 60; // 18h
  while (currentMinutes <= endMinutes) {
    const hours = Math.floor(currentMinutes / 60);
    const minutes = currentMinutes % 60;
    const valString = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
    const labelString = `${String(hours).padStart(2, '0')}h${String(minutes).padStart(2, '0')}`;
    timeOptions.push({ value: valString, label: labelString });
    currentMinutes += defaultDuration;
  }

  if (model === 'schools') {
    return [
      { key: 'uai', label: 'Code UAI (RNE)', type: 'text', required: true, placeholder: 'ex: 0750001A' },
      { key: 'name', label: 'Nom de l\'établissement', type: 'text', required: true, placeholder: 'ex: Collège Jean Jaurès' },
      { key: 'student_start_date', label: 'Date de rentrée des élèves', type: 'date', required: false },
      { key: 'student_end_date', label: 'Date de sortie des élèves', type: 'date', required: false }
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
      { key: 'school_id', label: 'Établissement Principal', type: 'select', required: true, options: schoolOptions },
      // Contraintes (US3 / Preferences)
      { key: 'max_hours_per_day', label: 'Max Heures par Jour', type: 'number', min: 0, max: 12, step: '0.5' },
      { key: 'max_hours_per_am', label: 'Max Heures par Matinée', type: 'number', min: 0, max: 8, step: '0.5' },
      { key: 'max_hours_per_pm', label: 'Max Heures par Après-midi', type: 'number', min: 0, max: 8, step: '0.5' },
      { key: 'max_presence_days_per_week', label: 'Max Jours Présence par Semaine', type: 'number', min: 0, max: 6 },
      { key: 'max_presence_hours_per_day', label: 'Max Heures Présence par Jour', type: 'number', min: 0, max: 12, step: '0.5' },
      { key: 'late_start_days_per_week', label: 'Jours de démarrage tardif par Semaine', type: 'number', min: 0, max: 6 },
      { key: 'late_start_time', label: 'Heure de démarrage au plus tôt', type: 'select', options: timeOptions, placeholder: 'ex: 08h30' },
      { key: 'early_end_days_per_week', label: 'Jours de fin précoce par Semaine', type: 'number', min: 0, max: 6 },
      { key: 'early_end_time', label: 'Heure de fin au plus tard', type: 'select', options: timeOptions, placeholder: 'ex: 16h30' },
      { key: 'min_free_days_per_week', label: 'Jours libres minimum par Semaine', type: 'number', min: 0, max: 6 },
      { key: 'min_free_half_days_per_week', label: 'Demi-jours libres minimum par Semaine', type: 'number', min: 0, max: 12 },
      { key: 'max_worked_am_per_week', label: 'Max Matinées travaillées par Semaine', type: 'number', min: 0, max: 6 },
      { key: 'max_worked_pm_per_week', label: 'Max Après-midis travaillées par Semaine', type: 'number', min: 0, max: 6 },
      { key: 'only_one_half_day_per_day', label: 'Ne travailler qu\'une demi-journée par jour', type: 'boolean' },
      { key: 'max_gap_hours_per_week', label: 'Max heures creuses (trous) par Semaine', type: 'number', min: 0, max: 20 }
    ];
  } else if (model === 'resource_constraints') {
    return [
      { key: 'max_hours_per_day', label: 'Max Heures par Jour', type: 'number', min: 0, max: 12, step: '0.5' },
      { key: 'max_hours_per_am', label: 'Max Heures par Matinée', type: 'number', min: 0, max: 8, step: '0.5' },
      { key: 'max_hours_per_pm', label: 'Max Heures par Après-midi', type: 'number', min: 0, max: 8, step: '0.5' },
      { key: 'max_presence_days_per_week', label: 'Max Jours Présence par Semaine', type: 'number', min: 0, max: 6 },
      { key: 'max_presence_hours_per_day', label: 'Max Heures Présence par Jour', type: 'number', min: 0, max: 12, step: '0.5' },
      { key: 'late_start_days_per_week', label: 'Jours de démarrage tardif par Semaine', type: 'number', min: 0, max: 6 },
      { key: 'late_start_time', label: 'Heure de démarrage au plus tôt', type: 'select', options: timeOptions, placeholder: 'ex: 08h30' },
      { key: 'early_end_days_per_week', label: 'Jours de fin précoce par Semaine', type: 'number', min: 0, max: 6 },
      { key: 'early_end_time', label: 'Heure de fin au plus tard', type: 'select', options: timeOptions, placeholder: 'ex: 16h30' },
      { key: 'min_free_days_per_week', label: 'Jours libres minimum par Semaine', type: 'number', min: 0, max: 6 },
      { key: 'min_free_half_days_per_week', label: 'Demi-jours libres minimum par Semaine', type: 'number', min: 0, max: 12 },
      { key: 'max_worked_am_per_week', label: 'Max Matinées travaillées par Semaine', type: 'number', min: 0, max: 6 },
      { key: 'max_worked_pm_per_week', label: 'Max Après-midis travaillées par Semaine', type: 'number', min: 0, max: 6 },
      { key: 'only_one_half_day_per_day', label: 'Ne travailler qu\'une demi-journée par jour', type: 'boolean' },
      { key: 'max_gap_hours_per_week', label: 'Max heures creuses (trous) par Semaine', type: 'number', min: 0, max: 20 }
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
      { key: 'school_id', label: 'Établissement', type: 'select', required: true, options: schoolOptions },
      { key: 'period_type_id', label: 'Type de Période', type: 'select', required: true, options: periodTypeOptions },
      { key: 'start_date', label: 'Date de début', type: 'date', required: true },
      { key: 'end_date', label: 'Date de fin', type: 'date', required: true }
    ];
  } else if (model === 'period_types') {
    return [
      { key: 'label', label: 'Libellé du type de période', type: 'text', required: true, placeholder: 'ex: Trimestre' }
    ];
  } else if (model === 'system_settings') {
    return [
      { key: 'key', label: 'Clé du paramètre', type: 'text', required: true, placeholder: 'ex: STANDARD_TIMESLOT_DURATION' },
      { key: 'value', label: 'Valeur', type: 'text', required: true, placeholder: 'ex: 30' }
    ];
  }
  return [];
}

const formFieldsConfig = computed(() => {
  return getFormFieldsConfig();
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
async function onMoveCourse(courseId: number, timeslotId: number) {
  const previousCoursesState = JSON.parse(JSON.stringify(courses.value));
  const oldScore = scoreData.value ? { ...scoreData.value } : null;
  
  const courseIndex = courses.value.findIndex(c => c.id === courseId);
  const courseObj = courseIndex !== -1 ? courses.value[courseIndex] : null;
  
  if (courseIndex !== -1) {
    courses.value[courseIndex].timeslot_id = timeslotId;
  }

  try {
    await api.updateCourse(courseId, timeslotId);
    await refreshScoreAndNotify(oldScore, 'Le cours a été planifié avec succès.');
    
    // Alerte en cas de placement sur un créneau indisponible (Rouge / Unsuited) - T025b
    if (courseObj) {
      try {
        const prefResData = await fetch(`/api/generic/resource_preferences?timeslot_id=${timeslotId}&limit=1000`).then(res => res.json());
        const prefRes = prefResData.items || [];
        const unsuitedPref = prefRes.find((p: any) => 
          p.preference_level === 'Unsuited' && (
            (p.resource_type === 'Teacher' && courseObj.teacher_ids && courseObj.teacher_ids.includes(p.resource_id)) ||
            (p.resource_type === 'Classroom' && courseObj.classroom_ids && courseObj.classroom_ids.includes(p.resource_id)) ||
            (p.resource_type === 'Division' && courseObj.division_ids && courseObj.division_ids.includes(p.resource_id))
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
  }

  try {
    await api.updateCourse(courseId, null);
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
    await api.updateCourse(courseId, course.timeslot_id, newPinState);
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
      c.classroom_ids = [];
    });
    await refreshScoreAndNotify(oldScore, 'Tous les cours ont été retirés de la grille.');
  } catch (err: any) {
    showNotification('error', err.message || 'Erreur lors de la réinitialisation');
  } finally {
    loading.value = false;
  }
}

async function loadTimeslotConfig() {
  try {
    const res = await fetch('/api/generic/system_settings').then(r => r.json());
    const items = res.items || [];
    const durationSetting = items.find((item: any) => item.key === 'STANDARD_TIMESLOT_DURATION');
    globalTimeslotDuration.value = durationSetting ? Number(durationSetting.value) : 30;
  } catch (e) {
    console.error("Failed to load standard timeslot duration config", e);
  }
}

onMounted(async () => {
  await loadTimeslotConfig();
  loadData();
  loadSchools();
  loadPeriodTypes();
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
  height: 100%;
}

.timetable-tab-wrapper {
  display: flex;
  flex-direction: row;
  height: 100%;
  width: 100%;
  overflow: hidden;
}

.timetable-right-container {
  display: flex;
  flex-direction: column;
  flex: 1;
  height: 100%;
  overflow: hidden;
}

.timetable-controls-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 65px;
  padding: 0 24px;
  background-color: var(--bg-surface);
  border-bottom: 1px solid var(--border-color);
  box-sizing: border-box;
  gap: 16px;
}

.filters-bar-wrapper {
  display: flex;
  align-items: center;
  gap: 16px;
}

.filters-bar-wrapper .filter-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  color: var(--text-secondary);
}

.filters-bar-wrapper .select-custom {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 6px 12px;
  border-radius: 3px;
  font-family: var(--font-sans);
  font-size: 13px;
  cursor: pointer;
  outline: none;
}

.filters-bar-wrapper .select-custom:focus {
  border-color: var(--accent-primary);
}

.spinner-small {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.2);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  display: inline-block;
}

@keyframes spin {
  to { transform: rotate(360deg); }
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
  padding: 0;
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

.inline-form-panel, .panel-content-wrapper {
  height: 100%;
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

/* Styles pour le placeholder de selection */
.pref-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 40px;
  text-align: center;
  color: var(--text-secondary);
  background-color: var(--bg-card);
}

.placeholder-icon {
  font-size: 48px;
  margin-bottom: 16px;
  animation: float 2s ease-in-out infinite;
}

.placeholder-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.placeholder-subtitle {
  font-size: 13.5px;
  max-width: 320px;
}

@keyframes float {
  0%, 100% { transform: translateX(0); }
  50% { transform: translateX(-8px); }
}
</style>
