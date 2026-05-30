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
            :nonTeachingStaffs="nonTeachingStaffs"
            :divisions="divisions"
            :classrooms="classrooms"
            :schools="schoolsList"
            v-model:schoolId="schoolId"
            v-model:selectedTeacherIds="selectedTeacherIds"
            v-model:selectedNonTeachingStaffIds="selectedNonTeachingStaffIds"
            v-model:selectedDivisionIds="selectedDivisionIds"
            v-model:selectedClassroomIds="selectedClassroomIds"
            v-model:weekType="weekType"
            v-model:periodTypeId="periodTypeId"
            v-model:periodIds="periodIds"
            v-model:autoTarget="autoTarget"
            v-model:layoutMode="layoutMode"
            v-model:placementAssistantActive="placementAssistantActive"
            :periodTypes="periodTypesList"
            :periods="periodsList"
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
            :nonTeachingStaffs="nonTeachingStaffs"
            :classrooms="classrooms"
            :divisions="divisions"
            :timeslots="timeslots"
            :courses="courses"
            :schools="schoolsList"
            :resourceTypeProp="activeAdminModel === 'teachers' ? 'Teacher' : (activeAdminModel === 'non_teaching_staffs' ? 'NonTeachingStaff' : (activeAdminModel === 'classrooms' ? 'Classroom' : (activeAdminModel === 'divisions' ? 'Division' : (activeAdminModel === 'courses' ? 'Course' : 'Teacher'))))"
            :resourceIdProp="selectedParentIds && selectedParentIds.length === 1 ? selectedParentIds[0] : (formModel && formModel.id ? formModel.id : null)"
            :resourceIdsProp="selectedParentIds || []"
            :hideSelectors="['teachers_preferences_tab', 'non_teaching_staffs_preferences_tab', 'classrooms_preferences_tab', 'divisions_preferences_tab', 'courses_preferences_tab'].includes(activeLeaf?.id)"
            :hideWeekSelectorProp="panel.gridConfig?.hideWeekSelector || false"
            :hidePeriodSelectorProp="panel.gridConfig?.hidePeriodSelector || false"
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
            :title="activeAdminModel"
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
          <div v-if="selectedParentIds.length === 0 && !isAddingInline" class="pref-placeholder">
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
            :resourceKey="panel.resourceKey || activeAdminModel"
            @submit="onSubmitGeneric"
            @delete="onDeleteGeneric"
            @cancel="isAddingInline = false"
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
      :resourceKey="activeAdminModel"
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
      :nonTeachingStaffs="nonTeachingStaffs"
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
          'notification-success': notif.type === 'success',
          'notification-info': notif.type === 'info'
        }"
      >
        <div style="flex: 1;">
          <div class="notification-title">
            {{ notif.type === 'error' ? 'Alerte' : (notif.type === 'info' ? 'Info' : 'Succès') }}
          </div>
          <div class="notification-desc" style="white-space: pre-wrap;">{{ notif.message }}</div>
        </div>
        <button class="notification-close" @click="removeNotification(notif.id)" title="Fermer">✕</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed, provide } from 'vue';
import type { Component } from 'vue';
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
import { Course, Timeslot, Teacher, NonTeachingStaff, Division, Classroom } from './types';
import * as api from './services/api';

// États partagés
const courses = ref<Course[]>([]);
const timeslots = ref<Timeslot[]>([]);
const teachers = ref<Teacher[]>([]);
const nonTeachingStaffs = ref<NonTeachingStaff[]>([]);
const divisions = ref<Division[]>([]);
const classrooms = ref<Classroom[]>([]);

const selectedTeacherIds = ref<number[]>([]);
const selectedNonTeachingStaffIds = ref<number[]>([]);
const selectedDivisionIds = ref<number[]>([]);
const selectedClassroomIds = ref<number[]>([]);
const weekType = ref<'W' | 'A' | 'B'>('W');
const periodTypeId = ref<number | null>(null);
const periodIds = ref<number[]>([]);
const periodsList = ref<any[]>([]);
const schoolId = ref<number | null>(null);
const loading = ref<boolean>(false);
const autoTarget = ref<boolean>(false);
const layoutMode = ref<string>('merged');
const placementAssistantActive = ref<boolean>(false);

const selectedCourseIds = ref<number[]>([]);

watch(schoolId, () => {
  selectedTeacherIds.value = [];
  selectedNonTeachingStaffIds.value = [];
  selectedDivisionIds.value = [];
  selectedClassroomIds.value = [];
});

function toggleCourseSelection(id: number, event?: MouseEvent) {
  const isMulti = event && (event.ctrlKey || event.metaKey);
  const isSelected = selectedCourseIds.value.includes(id);

  if (isMulti) {
    if (isSelected) {
      selectedCourseIds.value = selectedCourseIds.value.filter(x => x !== id);
    } else {
      selectedCourseIds.value.push(id);
    }
  } else {
    // Single selection mode
    if (isSelected && selectedCourseIds.value.length === 1) {
      selectedCourseIds.value = [];
    } else {
      selectedCourseIds.value = [id];
    }
  }
  
  // Auto target logic : Si activé, le clic met à jour les filtres
  if (autoTarget.value) {
    if (selectedCourseIds.value.length > 0) {
      const targetId = selectedCourseIds.value[selectedCourseIds.value.length - 1];
      const course = courses.value.find(c => c.id === targetId);
      if (course) {
        selectedTeacherIds.value = [...(course.teacher_ids || [])];
        selectedNonTeachingStaffIds.value = [...(course.non_teaching_staff_ids || [])];
        selectedDivisionIds.value = [...(course.division_ids || [])];
        selectedClassroomIds.value = [...(course.classroom_ids || [])];
      }
    } else {
      // Si on a tout désélectionné
      selectedTeacherIds.value = [];
      selectedNonTeachingStaffIds.value = [];
      selectedDivisionIds.value = [];
      selectedClassroomIds.value = [];
    }
  }
}

watch(autoTarget, (newVal) => {
  if (newVal && selectedCourseIds.value.length > 0) {
    // Appliquer le ciblage immédiatement sur le dernier cours sélectionné
    const id = selectedCourseIds.value[selectedCourseIds.value.length - 1];
    const course = courses.value.find(c => c.id === id);
    if (course) {
      selectedTeacherIds.value = [...(course.teacher_ids || [])];
      selectedNonTeachingStaffIds.value = [...(course.non_teaching_staff_ids || [])];
      selectedDivisionIds.value = [...(course.division_ids || [])];
      selectedClassroomIds.value = [...(course.classroom_ids || [])];
    }
  }
});

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

const isEditModalDisabled = computed(() => {
  if (!activeLeaf.value || !activeLeaf.value.panels) return false;
  const listPanel = activeLeaf.value.panels.find((p: any) => p.component === 'GenericList');
  if (!listPanel) return false;
  return listPanel.listConfig?.disableEditModal === true;
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

const activeAdminModel = ref('schools');
const genericItems = ref<any[]>([]);
const genericLoading = ref(false);
const schoolsList = ref<any[]>([]);
const periodTypesList = ref<any[]>([]);
const globalTimeslotDuration = ref(30);
const openApiSpec = ref<any>(null);
provide('openApiSpec', openApiSpec);

// États pour la boîte de dialogue de confirmation d'impact
const showImpactModal = ref(false);
const impactModalTitle = ref('');
const impactedSessionsCount = ref(0);
const impactedSessions = ref<any[]>([]);
const pendingDeleteCallback = ref<(() => Promise<void>) | null>(null);

const modelToResourceType: Record<string, string> = {
  teachers: 'Teacher',
  non_teaching_staffs: 'NonTeachingStaff',
  classrooms: 'Classroom',
  divisions: 'Division',
  schools: 'School',
  resource_constraints: 'ResourceConstraint',
  subject_to_subject_constraints: 'SubjectToSubjectConstraint',
  courses: 'Course',
};

// Notifications
interface Notification {
  id: number;
  type: 'success' | 'error' | 'info';
  message: string;
}
const notifications = ref<Notification[]>([]);
let notificationId = 0;

function removeNotification(id: number) {
  notifications.value = notifications.value.filter(n => n.id !== id);
}

function showNotification(type: 'success' | 'error' | 'info', message: string) {
  const id = ++notificationId;
  notifications.value.push({ id, type, message });
  if (type !== 'error') {
    setTimeout(() => {
      removeNotification(id);
    }, 4500);
  }
}

const scoreData = ref<{ hard_score: number; soft_score: number; summary: string; matches: Record<string, { hard: number; soft: number; count: number }> } | null>(null);

// Chargement initial des données
async function loadData() {
  try {
    const data = await api.fetchTimetable();
    courses.value = data.courses;
    timeslots.value = data.timeslots;
    teachers.value = data.teachers;
    nonTeachingStaffs.value = data.non_teaching_staffs;
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

async function loadOpenApiSpec() {
  try {
    const res = await fetch('/api/openapi.json').then(r => r.json());
    openApiSpec.value = res;
  } catch (err: any) {
    console.error("Échec du chargement de la spécification OpenAPI", err);
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

async function loadPeriods() {
  try {
    const res = await api.fetchGenericList('periods', 0, 1000);
    periodsList.value = res.items;
  } catch (e) {
    console.error("Échec du chargement des périodes", e);
  }
}

async function loadGenericItems() {
  genericLoading.value = true;
  genericItems.value = [];
  try {
    const listPanel = activeLeaf.value?.panels?.find((p: any) => p.component === 'GenericList');
    const filters = listPanel?.listConfig?.filters || {};
    const res = await api.fetchGenericList(activeAdminModel.value, 0, 1000, undefined, filters);
    genericItems.value = res.items;
  } catch (err: any) {
    showNotification('error', err.message || 'Erreur lors du chargement des ressources');
  } finally {
    genericLoading.value = false;
  }
}

const FK_CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes
const fkOptionsCache = ref<Record<string, { items: Array<{ value: any; label: string; rawData?: any }>; loadedAt: number }>>({});

provide('fkOptionsCache', fkOptionsCache);

function invalidateFkCache(resourceName: string) {
  delete fkOptionsCache.value[resourceName];
}

function fkOptions(resourceName: string): Array<{ value: any; label: string }> {
  return fkOptionsCache.value[resourceName]?.items || [];
};

async function loadFkOptionsForModel(model: string) {
  if (!openApiSpec.value) return;
  const schemaName = `${model}_CreatePayload`;
  const schema = openApiSpec.value.components?.schemas?.[schemaName];
  if (!schema || !schema.properties) return;

  const now = Date.now();
  for (const [key, prop] of Object.entries<any>(schema.properties)) {
    let resourceName = prop.resource;
    if (!resourceName && prop.anyOf) {
      const opt = prop.anyOf.find((o: any) => o.resource);
      if (opt) resourceName = opt.resource;
    }

    if (resourceName) {
      const cached = fkOptionsCache.value[resourceName];
      const isStale = !cached || (now - cached.loadedAt > FK_CACHE_TTL_MS);
      if (isStale) {
        try {
          const res = await api.fetchGenericList(resourceName, 0, 1000);
          fkOptionsCache.value[resourceName] = {
            items: (res.items || []).map((item: any) => ({
              value: item.id,
              label: item.display_name || item.name || item.code || String(item.id),
              rawData: item
            })),
            loadedAt: now
          };
        } catch (e) {
          console.error(`Failed to fetch options for resource ${resourceName}`, e);
          fkOptionsCache.value[resourceName] = { items: [], loadedAt: now };
        }
      }
    }
  }
}

watch([activeAdminModel, openApiSpec], () => {
  loadFkOptionsForModel(activeAdminModel.value);
}, { immediate: true });

function updateDefaultSelection() {
  if (selectedDivisionIds.value.length === 0 && selectedTeacherIds.value.length === 0 && selectedClassroomIds.value.length === 0 && selectedNonTeachingStaffIds.value.length === 0) {
    if (divisions.value.length > 0) {
      selectedDivisionIds.value = [divisions.value[0].id];
    }
  }
}

// Watchers
// Removed viewMode watch

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
const isAddingInline = ref(false);

function onAddGeneric() {
  formTitle.value = `Ajouter un élément`;
  // Initialiser le modèle avec les valeurs par défaut issues de l'OpenAPI
  const defaults: Record<string, any> = {};
  formFieldsConfig.value.forEach((field: any) => {
    if (field.default !== undefined) {
      defaults[field.key] = field.default;
    }
  });
  // Appliquer les champs fixes
  const formPanel = activeLeaf.value?.panels?.find((p: any) => p.component === 'GenericForm');
  if (formPanel?.formConfig?.fixedFields) {
    Object.assign(defaults, formPanel.formConfig.fixedFields);
  }
  formModel.value = defaults;
  selectedRelatedRecords.value = [];
  selectedParentIds.value = [];
  isEditing.value = false;
  
  if (isListEditableInline.value) {
    const newId = 'new_' + Date.now();
    const newItem: Record<string, any> = { id: newId };
    // Appliquer les valeurs par défaut issues de l'OpenAPI
    formFieldsConfig.value.forEach((field: any) => {
      if (field.default !== undefined) {
        newItem[field.key] = field.default;
      }
    });
    // Appliquer les champs fixes (ex: resource_type="Subject")
    const formPanel = activeLeaf.value?.panels?.find((p: any) => p.component === 'GenericForm');
    if (formPanel?.formConfig?.fixedFields) {
      Object.assign(newItem, formPanel.formConfig.fixedFields);
    }
    genericItems.value.unshift(newItem);
    return;
  }

  if (!isInlineMode.value) {
    showFormModal.value = true;
  } else {
    isAddingInline.value = true;
  }
}

function onEditGeneric(item: any) {
  formTitle.value = `Modifier l'élément`;
  formModel.value = { ...item };
  selectedRelatedRecords.value = [];
  isEditing.value = true;
  isAddingInline.value = false;
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
  isAddingInline.value = false;
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
      } else if (!isListEditableInline.value && !isEditModalDisabled.value) {
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
      
      // Update local state directly instead of full reload if we modified the main resource
      if (targetResource === activeAdminModel.value) {
        selectedParentIds.value.forEach(id => {
          const idx = genericItems.value.findIndex(x => x.id === id);
          if (idx !== -1) {
            genericItems.value[idx] = { ...genericItems.value[idx], ...value };
          }
        });
      }
      
      await onSelectionChangeGeneric([...selectedParentIds.value]);
    } else if (isEditing.value) {
      await api.updateGenericItem(targetResource, value.id, value);
      showNotification('success', 'Ressource modifiée avec succès !');
      invalidateFkCache(targetResource);;
      
      // Update local state directly instead of full reload if we modified the main resource
      if (targetResource === activeAdminModel.value) {
        const idx = genericItems.value.findIndex(x => x.id === value.id);
        if (idx !== -1) {
          genericItems.value[idx] = { ...genericItems.value[idx], ...value };
        }
      }
      
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
      const created = await api.createGenericItem(targetResource, value);
      showNotification('success', 'Ressource créée avec succès !');
      invalidateFkCache(targetResource);
      
      // Full reload on creation since there might be server-generated fields or ordering changes
      await loadGenericItems();
      
      showFormModal.value = false;
      formModel.value = {};
      isEditing.value = false;
    }
    window.dispatchEvent(new CustomEvent('resource:mutated', { 
      detail: { resource_name: targetResource || activeAdminModel.value } 
    }));
  } catch (err: any) {
    showNotification('error', err.message || 'Impossible d\'enregistrer la ressource.');
  }
}

async function onUpdateGenericInline(item: any) {
  // Optimistic UI update: on applique la modif localement tout de suite
  const idx = genericItems.value.findIndex(x => x.id === item.id);
  let oldItem = null;
  if (idx !== -1) {
    oldItem = { ...genericItems.value[idx] };
    genericItems.value[idx] = item;
  }

  try {
    if (String(item.id).startsWith('new_')) {
      const payload = { ...item };
      delete payload.id;
      const created = await api.createGenericItem(activeAdminModel.value, payload);
      if (idx !== -1) {
        genericItems.value[idx] = created;
      }
      invalidateFkCache(activeAdminModel.value);
      showNotification('success', 'Élément créé directement !');
    } else {
      await api.updateGenericItem(activeAdminModel.value, item.id, item);
      invalidateFkCache(activeAdminModel.value);
      showNotification('success', 'Élément mis à jour directement !');
    }
    
    window.dispatchEvent(new CustomEvent('resource:mutated', { 
      detail: { resource_name: activeAdminModel.value } 
    }));
  } catch (err: any) {
    showNotification('error', err.message || 'Échec de l\'enregistrement en ligne.');
    // En cas d'erreur, on restaure l'ancienne valeur, sauf si c'est une nouvelle ligne (pour ne pas perdre la saisie)
    if (idx !== -1 && oldItem && !String(item.id).startsWith('new_')) {
      genericItems.value[idx] = oldItem;
    }
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
          invalidateFkCache(activeAdminModel.value);
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
      invalidateFkCache(activeAdminModel.value);
      showNotification('success', 'Ressource supprimée avec succès !');
      showFormModal.value = false;
      formModel.value = {};
      loadGenericItems();
      window.dispatchEvent(new CustomEvent('resource:mutated', { 
        detail: { resource_name: activeAdminModel.value } 
      }));
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
  
  // --- GÉNÉRATION DYNAMIQUE VIA OPENAPI (LOW-CODE) ---
  if (openApiSpec.value && openApiSpec.value.components && openApiSpec.value.components.schemas) {
    const schemaName = `${model}_ReadPayload`;

    const schema = openApiSpec.value.components.schemas[schemaName];
    if (schema && schema.properties) {
      const dynamicColumns = [];
      for (const [key, prop] of Object.entries<any>(schema.properties)) {
        if (key === 'id' || key === 'display_name') continue; // On masque l'ID technique et display_name
        
        dynamicColumns.push({
          key: key,
          label: prop.title || key,
          width: prop.list_width || undefined // Si manquant, GenericList fera un width: auto
        });
      }
      return dynamicColumns;
    }
  }
  // ---------------------------------------------------
  return [];
});

// Configurations dynamiques de champs pour GenericForm
function getFormFieldsConfig(resourceKey?: string) {
  const model = resourceKey || activeAdminModel.value;
  const schoolOptions = schoolsList.value.map(s => ({ value: s.id, label: s.name }));
  const periodTypeOptions = periodTypesList.value.map(pt => ({ value: pt.id, label: pt.name || pt.label }));

  // On extrait dynamiquement les heures de début de la vraie grille de l'école !
  const timeSet = new Set<string>();
  timeslots.value.forEach((ts: any) => {
    if ((ts.minutes_from_midnight / 60) !== undefined && (ts.minutes_from_midnight / 60) !== null) {
      // Format start time (e.g. 8.5 -> "08:30")
      const h = Math.floor((ts.minutes_from_midnight / 60));
      const m = Math.round(((ts.minutes_from_midnight / 60) - h) * 60);
      const timeStr = `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
      timeSet.add(timeStr);
      
      // Format approximate end time (+1h par défaut) pour avoir des options de fin de journée cohérentes
      const h2 = Math.floor((ts.minutes_from_midnight / 60) + 1);
      const m2 = Math.round((((ts.minutes_from_midnight / 60) + 1) - h2) * 60);
      const endStr = `${h2.toString().padStart(2, '0')}:${m2.toString().padStart(2, '0')}`;
      timeSet.add(endStr);
    }
  });
  
  let timeOptions = Array.from(timeSet).sort().map(val => ({
    value: val,
    label: val.replace(':', 'h')
  }));

  // Si aucune grille n'est encore générée, on met une option d'avertissement
  if (timeOptions.length === 0) {
    timeOptions.push({ 
      value: '', 
      label: '⚠️ Veuillez d\'abord générer la grille des créneaux (Paramètres > Périodes)' 
    });
  }

  // --- GÉNÉRATION DYNAMIQUE VIA OPENAPI (LOW-CODE) ---
  if (openApiSpec.value && openApiSpec.value.components && openApiSpec.value.components.schemas) {
    const schemaName = `${model}_CreatePayload`;

    const schema = openApiSpec.value.components.schemas[schemaName];
    if (schema && schema.properties) {
      const dynamicFields = [];
      const requiredFields = schema.required || [];
      for (const [key, prop] of Object.entries<any>(schema.properties)) {
        if (key === 'id' || key === 'display_name') continue; // On masque l'ID et display_name dans le formulaire
        
        let baseType = prop.type;
        let resourceName = prop.resource;
        // Gérer les champs optionnels (nullable) de Pydantic qui utilisent anyOf
        if (!baseType && prop.anyOf) {
          const validOption = prop.anyOf.find((o: any) => o.type && o.type !== 'null');
          if (validOption) baseType = validOption.type;
          
          const opt = prop.anyOf.find((o: any) => o.resource);
          if (opt) resourceName = opt.resource;
        }

        let fieldType = prop.ui_type || baseType || 'text';
        if (fieldType === 'string') fieldType = 'text'; // OpenAPI renvoie string, mais le form attend text
        else if (fieldType === 'boolean') fieldType = 'boolean';
        else if (fieldType === 'integer' || fieldType === 'number') fieldType = 'number';
        
        if (fieldType === 'text' && prop.format === 'date') fieldType = 'date';
        
        if (fieldType === 'color' || key === 'color') fieldType = 'color';
        
        let options = prop.options || undefined;
        if (fieldType === 'time') { fieldType = 'select'; options = timeOptions; }
        else if (fieldType === 'array' && resourceName) {
          fieldType = 'multiselect';
          options = fkOptions(resourceName);
        }
        else if (resourceName) {
          fieldType = 'select';
          options = fkOptions(resourceName);
        }
        else if (options) { fieldType = 'select'; }
        
        dynamicFields.push({
          key: key,
          label: prop.title || key,
          type: fieldType,
          required: requiredFields.includes(key),
          requiredExpr: prop.requiredExpr,
          readOnlyExpr: prop.readOnlyExpr,
          invisibleExpr: prop.invisibleExpr,
          placeholder: prop.placeholder || '',
          min: prop.min,
          max: prop.max,
          step: prop.step,
          options: options,
          resource: resourceName,
          default: prop.default,
          help: prop.help,
          widget: prop.widget,
          widgetParams: prop.widgetParams
        });
      }
      return dynamicFields;
    }
  }
  // ---------------------------------------------------

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
             if (ruleName === "Pénaliser les cours non assignés (Overconstrained Planning)") continue;
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
    const response = await api.updateCourse(courseId, timeslotId);
    
    // Mettre à jour tous les cours impactés (le parent + les enfants)
    if (response.courses) {
      response.courses.forEach(updatedCourse => {
        const idx = courses.value.findIndex(c => c.id === updatedCourse.id);
        if (idx !== -1) {
          courses.value[idx] = updatedCourse;
        }
      });
    }
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
    const response = await api.updateCourse(courseId, null);
    
    if (response.courses) {
      response.courses.forEach(updatedCourse => {
        const idx = courses.value.findIndex(c => c.id === updatedCourse.id);
        if (idx !== -1) {
          courses.value[idx] = updatedCourse;
        }
      });
    }
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
    const response = await api.updateCourse(courseId, course.timeslot_id, newPinState);
    
    if (response.courses) {
      response.courses.forEach(updatedCourse => {
        const idx = courses.value.findIndex(c => c.id === updatedCourse.id);
        if (idx !== -1) {
          courses.value[idx] = updatedCourse;
        }
      });
    }
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
      if (!pollingInterval) {
        pollingInterval = window.setInterval(checkStatus, 3000);
      }
    } else {
      if (loading.value) {
        loading.value = false;
        loadData();
      }
      if (pollingInterval) {
        window.clearInterval(pollingInterval);
        pollingInterval = undefined;
      }
    }
  } catch (err) {
    console.error('Erreur lors de la vérification du statut', err);
    if (pollingInterval) {
      window.clearInterval(pollingInterval);
      pollingInterval = undefined;
    }
  }
}

async function onSolve() {
  try {
    const result = await api.solveTimetable();
    showNotification('success', result.message || 'Résolution démarrée en arrière-plan.');
    loading.value = true;
    checkStatus();
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
  await loadOpenApiSpec();
  await loadTimeslotConfig();
  loadData();
  loadSchools();
  loadPeriodTypes();
  loadPeriods();
  checkStatus();

  // Écoute des événements de mutation pour rafraîchir les données globales d'App.vue
  window.addEventListener('resource:mutated', (e: any) => {
    const resource = e.detail?.resource_name;
    if (resource === 'schools') loadSchools();
    if (resource === 'period_types') loadPeriodTypes();
    if (resource === 'periods') loadPeriods();
    if (resource === 'system_settings') loadTimeslotConfig();
    if (['teachers', 'classrooms', 'divisions', 'courses', 'groups'].includes(resource)) loadData();
  });
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
