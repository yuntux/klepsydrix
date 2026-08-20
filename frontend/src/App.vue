<template>
  <div class="app-container">
    <!-- Vue interactive principale orchestrée par NotebooksTree (T032) -->
    <NotebooksTree :initial-path="urlPathIds" @change-leaf="onLeafChange" @trigger-action="onTriggerAction">
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
            :subjects="subjectsList"
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

        <!-- 3bis. Composant Liste Générique "détail" : filtrée par la sélection du panneau maître -->
        <section v-else-if="panel.component === 'GenericList' && panel.role === 'detail'" class="admin-main-content">
          <div v-if="detailListLoading" class="loader-container">
            <div class="spinner"></div>
            <span>Chargement en cours...</span>
          </div>
          <div v-else-if="selectedParentIds.length !== 1" class="pref-placeholder">
            <div class="placeholder-icon">👈</div>
            <div class="placeholder-title">Sélectionnez un élément</div>
            <div class="placeholder-subtitle">
              {{ panel.placeholderText || "Veuillez choisir un élément dans la liste de gauche." }}
            </div>
          </div>
          <GenericList
            v-else
            :title="panel.resourceKey || ''"
            :columns="detailColumnsConfig"
            :fields="getFormFieldsConfig(panel.resourceKey)"
            :items="detailListItems"
            :listConfig="accessAwareListConfig(panel)"
            @add="onAddDetailGeneric"
            @update-item="onUpdateDetailGenericInline"
          />
        </section>

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
            :listConfig="accessAwareListConfig(panel)"
            :initial-selected-ids="urlSelectedIds"
            @add="onAddGeneric"
            @edit="onEditGeneric"
            @delete="onDeleteGeneric"
            @update-item="onUpdateGenericInline"
            @row-click="onRowClickGeneric"
            @selection-change="onSelectionChangeGeneric"
            @initial-selection-applied="urlSelectedIds = []"
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

        <!-- 3ter. Vue Pivot Générique (architecture.md section 15.L) : entièrement pilotée par
             resourceKey + pivotConfig, ne dépend d'aucun état global d'App.vue (mêmes principes
             d'autonomie que GenericListModal). -->
        <section v-else-if="panel.component === 'GenericPivot'" class="admin-main-content">
          <GenericPivot :resourceKey="panel.resourceKey || ''" :pivotConfig="panel.pivotConfig" />
        </section>

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
            :formConfig="accessAwareFormConfig(panel)"
            :selectedRecords="selectedRelatedRecords"
            :resourceKey="panel.resourceKey || activeAdminModel"
            @submit="onSubmitGeneric"
            @delete="onDeleteGeneric"
            @cancel="isAddingInline = false"
          />
        </div>
      </template>
    </NotebooksTree>

    <!-- Couche de progression du solveur (voir SolverProgressOverlay.vue) : montée ici plutôt que
         dans TimetableGrid.vue pour couvrir tout le viewport et rester visible même si
         l'utilisateur navigue vers un autre onglet pendant un calcul déclenché depuis un wizard. -->
    <SolverProgressOverlay
      :loading="loading"
      :solverProgress="solverProgress"
      :solverElapsedSeconds="solverElapsedSeconds"
      :solverTimeLimitSeconds="solverTimeLimitSeconds"
      :solverIsQueued="solverIsQueued"
      :solverQueuePosition="solverQueuePosition"
      :solverQueueLength="solverQueueLength"
      :solverKind="solverKind"
      :solverPipelineStep="solverPipelineStep"
      :solverPipelineTotalSteps="solverPipelineTotalSteps"
      @stop-solve="onStopSolve"
    />

    <!-- Déclenchement direct d'une action de menu (voir NotebooksTree.vue, feuille "action" et
         onTriggerAction ci-dessous) : instance headless de GenericForm, invisible tant que son
         wizard n'est pas ouvert — ne touche à aucun état de la vue affichée derrière. -->
    <GenericForm
      v-if="actionWizardResourceKey"
      :key="actionWizardNonce"
      headless
      title=""
      :fields="[]"
      :modelValue="actionWizardModel"
      :resourceKey="actionWizardResourceKey"
      :formConfig="{ editableForm: false, deletable: false, autoOpenActionId: actionWizardActionId ?? undefined }"
      @wizard-success="onWizardJobStarted"
    />

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
      @wizard-success="onWizardJobStarted"
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

    <!-- Fiche T (T020) -->
    <CoursePopin
      :show="selectedCourseIds.length > 0"
      :courses="courses.filter(c => selectedCourseIds.includes(c.id))"
      :teachers="teachers"
      :nonTeachingStaffs="nonTeachingStaffs"
      :divisions="divisions"
      :classrooms="classrooms"
      :timeslots="timeslots"
      :groups="groupsList"
      :classParts="classPartsList"
      :materials="materialsList"
      :periods="periodsList"
      :subjects="subjectsList"
      @close="selectedCourseIds = []"
      @course-updated="onCoursePopinCourseUpdated"
      @error="(message: string) => showNotification('error', message)"
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
import { ref, onMounted, watch, computed, provide, defineAsyncComponent } from 'vue';
import type { Component, Ref } from 'vue';
import NotebooksTree from './components/NotebooksTree.vue';
import SolverProgressOverlay from './components/SolverProgressOverlay.vue';
import { Course, Timeslot, Teacher, NonTeachingStaff, Division, Classroom } from './types';
import * as api from './services/api';
import { useDataStore } from './stores/data';
import { getTimeslotHour } from './composables/useTimeslotGrid';
import { genericCacheKey } from './composables/useGenericCache';
import { useNotificationStore } from './stores/notifications';
import { getSelectedDatabase } from './services/dbSession';
import { useQueryClient, useQuery } from '@tanstack/vue-query';

const dataStore = useDataStore();
const notificationStore = useNotificationStore();
const queryClient = useQueryClient();

// Chargement asynchrone (Lazy Loading) des gros composants métiers
const TimetableGrid = defineAsyncComponent(() => import('./components/TimetableGrid.vue'));
const GridContainer = defineAsyncComponent(() => import('./components/GridContainer.vue'));
const GenericList = defineAsyncComponent(() => import('./components/GenericList.vue'));
const GenericForm = defineAsyncComponent(() => import('./components/GenericForm.vue'));
const PreferenceGrid = defineAsyncComponent(() => import('./components/PreferenceGrid.vue'));
const PeriodTransitionManager = defineAsyncComponent(() => import('./components/PeriodTransitionManager.vue'));
const GenericPivot = defineAsyncComponent(() => import('./components/GenericPivot.vue'));
const ImpactConfirmDialog = defineAsyncComponent(() => import('./components/ImpactConfirmDialog.vue'));
const CoursePopin = defineAsyncComponent(() => import('./components/CoursePopin.vue'));

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
const groupsList = ref<any[]>([]);
const classPartsList = ref<any[]>([]);
const materialsList = ref<any[]>([]);
const subjectsList = ref<any[]>([]);
const schoolId = ref<number | null>(null);
const loading = ref<boolean>(false);
const solverProgress = ref<{ hard_score: number; soft_score: number } | null>(null);
const solverElapsedSeconds = ref<number | null>(null);
const solverTimeLimitSeconds = ref<number | null>(null);
// QUEUED : une résolution est demandée mais n'a pas encore obtenu d'emplacement (voir
// solver.py::SolverState, "Concurrence des résolutions") — la base reste normalement modifiable
// tant que ce statut dure, seul SOLVING bloque l'écriture (mode exclusif, côté backend).
const solverIsQueued = ref<boolean>(false);
const solverQueuePosition = ref<number | null>(null);
const solverQueueLength = ref<number>(0);
// kind/pipeline_step/pipeline_total_steps (voir plan salles §4) : enrichissent l'overlay de
// TimetableGrid pour distinguer placement/attribution des salles/optimisation, y compris les 2
// phases du pipeline /optimize.
const solverKind = ref<string | null>(null);
const solverPipelineStep = ref<number>(1);
const solverPipelineTotalSteps = ref<number>(1);

import { useGridStore } from './stores/grid';
import { storeToRefs } from 'pinia';
import { parseLocationPath, parseLocationIds, syncUrl } from './services/urlState';
const gridStore = useGridStore();
const { autoTarget, layoutMode, placementAssistantActive, isDetailedView, selectedCourseIds } = storeToRefs(gridStore);

watch(schoolId, () => {
  selectedTeacherIds.value = [];
  selectedNonTeachingStaffIds.value = [];
  selectedDivisionIds.value = [];
  selectedClassroomIds.value = [];
});

function toggleCourseSelection(id: number, event?: MouseEvent) {
  const isMulti = !!(event && (event.ctrlKey || event.metaKey));
  gridStore.toggleCourseSelection(id, isMulti);
  
  // Auto target logic : Si activé, le clic met à jour les filtres
  if (autoTarget.value) {
    if (selectedCourseIds.value.length > 0) {
      const targetId = selectedCourseIds.value[selectedCourseIds.value.length - 1];
      const course = dataStore.courseMap[targetId];
      if (course) {
        selectedTeacherIds.value = [...(course.teacher_ids || [])];
        selectedNonTeachingStaffIds.value = [...(course.non_teaching_staff_ids || [])];
        selectedDivisionIds.value = [...(course.division_ids || [])];
        selectedClassroomIds.value = [...(dataStore.courseClassroomIdsMap[course.id] || [])];
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
    // Si activé, on applique immédiatement les filtres du cours actuellement sélectionné
    const id = selectedCourseIds.value[selectedCourseIds.value.length - 1];
    const course = dataStore.courseMap[id];
    if (course) {
      selectedTeacherIds.value = [...(course.teacher_ids || [])];
      selectedNonTeachingStaffIds.value = [...(course.non_teaching_staff_ids || [])];
      selectedDivisionIds.value = [...(course.division_ids || [])];
      selectedClassroomIds.value = [...(dataStore.courseClassroomIdsMap[course.id] || [])];
    }
  }
});

// Onglet actif et configuration des Notebooks (T032). Valeur initiale dérivée de l'URL (même
// fonction pure que urlPathIds ci-dessous, appelée ici séparément pour ne pas réordonner les
// déclarations) plutôt que systématiquement 'timetable' : sinon, une URL profonde pointant
// directement sur une feuille admin (ex: /settings_root/disciplines_setting, voir "URLs
// profondes") démarre quand même avec activeTab='timetable' le temps qu'onLeafChange corrige la
// valeur — trop tard pour les query() dont le `enabled` dépend de activeTab dès leur création
// synchrone en setup() (voir bindGenericListQuery plus bas) : elles se déclenchaient donc quand
// même, même en arrivant directement sur une page admin, jamais sur la grille EDT.
const activeTab = ref<string>(parseLocationPath()[0] === 'timetable_root' ? 'timetable' : 'admin');
const activeLeaf = ref<any>(null);

// URLs profondes (voir architecture.md, "URLs profondes") : `urlPathIds`/`urlSelectedIds` sont lus
// une fois au chargement (état initial de l'URL), puis remis à jour uniquement sur un retour
// navigateur (popstate, voir onMounted) — NotebooksTree/GenericList les surveillent en continu et
// se resynchronisent dessus. `currentPathIds` reflète au contraire le chemin RÉELLEMENT actif à
// tout instant (mis à jour à chaque changement de feuille, voir onLeafChange) : c'est lui, avec
// `selectedParentIds`, qui pilote l'écriture de l'URL (voir le watch plus bas).
const urlPathIds = ref<string[]>(parseLocationPath());
const urlSelectedIds = ref<Array<string | number>>(parseLocationIds());
const currentPathIds = ref<string[]>([]);
let lastSyncedPathKey: string | null = null;
// Arme une garde d'un tick dans le watcher de synchronisation (voir plus bas) chaque fois qu'une
// restauration de sélection depuis l'URL vient d'être déclenchée (montage initial, ou retour
// navigateur) — évite d'écraser l'URL avec l'état transitoire "sélection vidée" que produit
// systématiquement onLeafChange avant que la restauration asynchrone n'ait eu le temps d'arriver.
let awaitingSelectionRestore = urlSelectedIds.value.length > 0;

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

async function onLeafChange(leaf: any, pathIds: string[] = []) {
  // La Fiche T (CoursePopin) reste affichée tant que selectedCourseIds n'est pas vide, sans
  // rapport avec le panel actif : la vider ici garantit qu'elle disparaît dès qu'on quitte le
  // Visualiseur, plutôt que de rester affichée avec une sélection obsolète derrière un autre menu.
  gridStore.clearCourseSelection();
  activeLeaf.value = leaf;
  currentPathIds.value = pathIds;

  // 'timetable_root' est un noeud GROUPE dans l'arbre (voir ui.json) — jamais lui-même
  // sélectionnable comme feuille : la vraie feuille de la grille EDT s'appelle
  // 'timetable_viewer' (son enfant). Comparer leaf.id === 'timetable_root' ne matchait donc
  // JAMAIS, quelle que soit la feuille affichée — activeTab retombait silencieusement sur
  // 'admin' même quand la grille EDT était bien montrée, empêchant les 6 caches gérés
  // par `enabled: timetableTabActive` (period_types/periods/groups/class_parts/materials/
  // subjects, voir bindGenericListQuery) de jamais se déclencher. Vérifier directement le
  // panneau affiché (comme pour activeAdminModel juste en dessous) est robuste à la profondeur/
  // au nommage de l'arbre, contrairement à une comparaison d'id figée.
  activeTab.value = leaf.panels?.some((p: any) => p.component === 'TimetableGrid') ? 'timetable' : 'admin';

  // Si l'onglet actif est une feuille administrative avec une ressource
  if (leaf.panels) {
    const listPanel = leaf.panels.find((p: any) => p.component === 'GenericList');
    if (listPanel && listPanel.resourceKey) {
      activeAdminModel.value = listPanel.resourceKey;

      // Réinitialiser le formulaire inline et la sélection
      formModel.value = {};
      isEditing.value = false;
      selectedParentIds.value = [];
      return;
    }

    // Feuille "formulaire singleton" : un panel GenericForm SANS GenericList sœur (ex: un
    // wizard TransientModel à enregistrement fixe, voir wizard_course_generations) — charge et
    // sélectionne directement son unique enregistrement, sans passer par une liste préalable.
    const formPanel = leaf.panels.find((p: any) => p.component === 'GenericForm');
    if (formPanel && formPanel.resourceKey) {
      activeAdminModel.value = formPanel.resourceKey;
      isAddingInline.value = false;
      try {
        const res = await api.fetchAllGenericItems(formPanel.resourceKey);
        const record = res.items?.[0];
        formModel.value = record ? { ...record } : {};
        selectedParentIds.value = record ? [record.id] : [];
        isEditing.value = !!record;
      } catch (e) {
        console.error('Échec du chargement de l\'enregistrement singleton', e);
        formModel.value = {};
        selectedParentIds.value = [];
      }
    }
  }
}

// Déclenchement d'une feuille "action" (voir NotebooksTree.vue) : charge l'enregistrement
// singleton de la ressource visée et le confie à une instance headless de GenericForm (voir
// template), qui ouvre aussitôt son wizard — sans toucher à activeLeaf/activeAdminModel/formModel,
// donc sans changer ce qui est déjà affiché derrière la popin.
const actionWizardResourceKey = ref<string | null>(null);
const actionWizardActionId = ref<string | null>(null);
const actionWizardModel = ref<any>(null);
const actionWizardNonce = ref(0);

async function onTriggerAction(action: { resourceKey: string; actionId: string }) {
  try {
    // loadFkOptionsForModel : contrairement aux autres points d'entrée d'un GenericForm (onglet,
    // panneau détail — voir les appels équivalents plus bas dans ce fichier), une action de menu
    // ne passe jamais par activeAdminModel/detailPanel, donc rien ne peuplait jusqu'ici
    // fkOptionsCache pour la ressource du wizard déclenché — resterait invisible tant qu'aucun
    // champ resource éditable n'était utilisé dans une étape (premier cas : ref_grade_id de
    // wizard_specialty_group_generations). En parallèle du chargement de l'enregistrement
    // singleton, pas séquentiel après : indépendants, pas de raison d'attendre l'un pour l'autre.
    const [res] = await Promise.all([
      api.fetchAllGenericItems(action.resourceKey),
      loadFkOptionsForModel(action.resourceKey),
    ]);
    const record = res.items?.[0];
    if (!record) {
      console.error(`Aucun enregistrement pour la ressource singleton ${action.resourceKey}`);
      return;
    }
    actionWizardModel.value = { ...record };
    actionWizardResourceKey.value = action.resourceKey;
    actionWizardActionId.value = action.actionId;
    // Force le remontage de l'instance headless à chaque déclenchement (même resourceKey/actionId
    // possible sur deux clics successifs) : l'auto-ouverture du wizard dans GenericForm.vue ne se
    // déclenche qu'une fois par enregistrement chargé, un nouvel enregistrement { ...record } ne
    // suffit pas à lui seul à le garantir si Vue réutilise l'instance existante.
    actionWizardNonce.value++;
  } catch (e) {
    console.error('Échec du déclenchement de l\'action de menu', e);
  }
}

const activeAdminModel = ref('schools');
const genericItems = ref<any[]>([]);
const genericLoading = ref(false);

// genericItems.value pointe vers le tableau réactif de la query TanStack (voir genericListQuery
// plus bas) : TanStack Query rend ses résultats LECTURE SEULE (Vue readonly()), donc une mutation
// par INDEX (`genericItems.value[idx] = x`) échoue silencieusement (avertissement "Set operation
// ... failed: target is readonly", sans exception) — l'affichage local ne se met alors à jour
// qu'au prochain refetch complet, jamais immédiatement. Remplacer le tableau ENTIER (nouvelle
// référence) plutôt que muter un de ses éléments contourne le problème : c'est une écriture sur
// le ref lui-même, jamais sur le tableau readonly qu'il pointait avant cet appel.
function setGenericItemAt(idx: number, value: any) {
  if (idx === -1) return;
  const next = [...genericItems.value];
  next[idx] = value;
  genericItems.value = next;
}

// Clé de requête réactive du panneau maître générique : recalculée automatiquement dès que
// activeAdminModel ou les filtres du panel actif changent — une vraie useQuery() (ci-dessous)
// redéclenche son fetch nativement dès que sa clé change, sans watch() explicite à maintenir.
// Segment filters omis quand vide (cas de loin le plus courant) : ['genericList', resource] est
// alors EXACTEMENT la même clé que bindGenericListQuery/fkOptionsCache/useGenericCache pour cette
// ressource — ouvrir le panneau Enseignants et référencer teacher_ids comme FK ailleurs partagent
// désormais une seule requête réseau et une seule entrée de cache, plutôt que deux clés distinctes
// pour la même donnée non filtrée (voir architecture.md §15.T, "unification du cache generic").
const genericListQueryKey = computed(() => genericCacheKey(activeAdminModel.value, activeLeaf.value?.panels?.find((p: any) => p.component === 'GenericList')?.listConfig?.filters));

// Source de vérité unique du panneau maître (voir architecture.md §15.T) : UNE SEULE copie en
// cache TanStack Query, partagée par tout consommateur présent ou futur de cette clé — plutôt
// qu'un fetch imperatif isolé (queryClient.fetchQuery() + recopie manuelle) qu'il fallait
// explicitement re-déclencher à chaque site de mutation, au risque d'en oublier un (voir la
// discussion sur schoolsList/fkOptionsCache — des copies indépendantes de la même donnée, qu'il
// fallait garder synchronisées "à la main"). `enabled` : inutile de fetcher tant que l'onglet
// admin n'est pas affiché.
const genericListQuery = useQuery({
  queryKey: genericListQueryKey,
  // genericCacheKey renvoie QueryKey (readonly unknown[], voir useGenericCache.ts) pour satisfaire
  // le typage de useQuery — l'indexation ci-dessous s'appuie sur la forme documentée et garantie
  // par cette fonction (['genericList', resource] ou ['genericList', resource, filters]).
  queryFn: () => api.fetchAllGenericItems(
    genericListQueryKey.value[1] as string,
    undefined,
    genericListQueryKey.value[2] as Record<string, any> | undefined,
  ),
  enabled: computed(() => activeTab.value === 'admin'),
});

// genericItems reste une ref "à plat" mutable : des dizaines de sites existants la lisent/mutent
// directement (ex: patchs optimistes après une sauvegarde, ligne "brouillon" ajoutée localement
// avant sa création serveur) — les conserver tels quels était le but explicite de ce refactor
// (ne pas réécrire GenericList.vue/GenericForm.vue). Elle est maintenant synchronisée depuis le
// résultat réactif de la query ci-dessus : à chaque changement (montage, navigation, invalidation
// déclenchée n'importe où dans l'app — resource:mutated, write-token:stale, invalidateFkCache
// puisqu'ils partagent le même préfixe de clé ['genericList', ressource]), pas seulement quand
// CE composant décide explicitement de recharger.
// flush: 'sync' impératif ici : refreshActiveGenericPanel(IfMatches) attend la fin de
// l'invalidation (await queryClient.invalidateQueries(...)) puis lit immédiatement
// genericItems.value juste après (via loadDetailListItems, qui en dérive) — avec le flush 'pre'
// par défaut de Vue (asynchrone, groupé avant le prochain rendu), rien ne garantit que ce watch
// se soit déjà exécuté à ce moment précis, ce qui ferait lire une valeur encore périmée à
// loadDetailListItems. L'ancien code (avant ce refactor) écrivait genericItems.value de façon
// synchrone dans loadGenericItems() lui-même ; ce watch() doit reproduire exactement cette
// garantie de synchronicité, pas seulement "à peu près en même temps".
watch(() => genericListQuery.data.value, (val) => {
  genericItems.value = val?.items || [];
}, { flush: 'sync' });
// isLoading (pas isFetching) : vrai seulement tant qu'aucune donnée n'est encore en cache pour
// cette clé — un rafraîchissement en arrière-plan (données déjà affichées, requête déjà en cache)
// ne doit pas faire disparaître la liste sous un spinner, seulement le tout premier chargement
// d'une ressource jamais visitée.
watch(() => genericListQuery.isLoading.value, (val) => {
  genericLoading.value = val;
});

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

// Notifications — état déplacé dans stores/notifications.ts (voir plus haut) pour qu'un composant
// hors de l'arbre direct d'App.vue (ex: GenericListModal.vue) puisse aussi déclencher la boîte
// rouge/verte ; ces deux fonctions ne font que déléguer, pour ne pas toucher aux ~30 appels
// showNotification(...)/removeNotification(...) existants plus bas dans ce fichier.
const notifications = computed(() => notificationStore.notifications);
function removeNotification(id: number) {
  notificationStore.removeNotification(id);
}
function showNotification(type: 'success' | 'error' | 'info', message: string) {
  notificationStore.showNotification(type, message);
}

const scoreData = ref<{ hard_score: number; soft_score: number; summary: string; matches: Record<string, { hard: number; soft: number; count: number }> } | null>(null);

// Chargement initial des données de la grille EDT — auparavant un seul round-trip bespoke
// (GET /api/timetable, voir architecture.md §15.U), désormais des appels génériques en
// parallèle, partageant le cache queryClient avec le reste de l'app (queryClient.fetchQuery,
// même clé canonique que useGenericCache — voir GenericPivot.vue pour le même motif). courses/
// timeslots/teachers/etc. restent des refs "à plat" mutables (patchs optimistes après solve,
// drag & drop...), remplies une fois ici plutôt que dérivées d'une useQuery() réactive.
//
// timeslots : filtré ?active=true côté serveur (Timeslot.active, hybrid_property SQL, voir
// timeslot.py) — remplace Timeslot.get_active_timeslots() qui faisait la même chose à la main
// dans l'ancien endpoint dédié.
async function loadData() {
  try {
    // Invalider explicitement avant de (re)fetch : loadData() est appelée dans des contextes où
    // le serveur vient de changer sous nos pieds (fin de résolution détectée via le jeton
    // d'écriture périmé, voir write-token:stale ci-dessous ; resource:mutated d'un wizard).
    // Sans ça, staleTime (60s, voir main.ts) fait servir le cache tel quel par fetchQuery dès
    // qu'une entrée a été peuplée il y a moins d'une minute — ce qui arrive précisément ici si un
    // wizard a déjà dispatché resource:mutated('courses') au LANCEMENT du solve (donc avant la
    // fin réelle) : loadData() rendrait alors silencieusement les données pré-solve, malgré la
    // notification annonçant un rechargement (bug constaté sur "Optimiser l'emploi du temps").
    // Même geste que refreshFkOptionsForResource ci-dessous, généralisé à toutes les clés lues ici.
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: genericCacheKey('teachers') }),
      queryClient.invalidateQueries({ queryKey: genericCacheKey('classrooms') }),
      queryClient.invalidateQueries({ queryKey: genericCacheKey('divisions') }),
      queryClient.invalidateQueries({ queryKey: genericCacheKey('non_teaching_staffs') }),
      queryClient.invalidateQueries({ queryKey: genericCacheKey('courses') }),
      queryClient.invalidateQueries({ queryKey: genericCacheKey('timeslots', { active: true }) }),
      queryClient.invalidateQueries({ queryKey: genericCacheKey('course_classroom_requirements') }),
    ]);

    const [teachersRes, classroomsRes, divisionsRes, nonTeachingRes, coursesRes, timeslotsRes, classroomRequirementsRes] = await Promise.all([
      queryClient.fetchQuery({ queryKey: genericCacheKey('teachers'), queryFn: () => api.fetchAllGenericItems('teachers') }),
      queryClient.fetchQuery({ queryKey: genericCacheKey('classrooms'), queryFn: () => api.fetchAllGenericItems('classrooms') }),
      queryClient.fetchQuery({ queryKey: genericCacheKey('divisions'), queryFn: () => api.fetchAllGenericItems('divisions') }),
      queryClient.fetchQuery({ queryKey: genericCacheKey('non_teaching_staffs'), queryFn: () => api.fetchAllGenericItems('non_teaching_staffs') }),
      queryClient.fetchQuery({ queryKey: genericCacheKey('courses'), queryFn: () => api.fetchAllGenericItems('courses') }),
      queryClient.fetchQuery({ queryKey: genericCacheKey('timeslots', { active: true }), queryFn: () => api.fetchAllGenericItems('timeslots', undefined, { active: true }) }),
      // course_classroom_requirements : chargé aux côtés de courses (même cycle de vie — toute
      // résolution qui réécrit l'un réécrit potentiellement l'autre, voir plan salles §1.4/§4) pour
      // résoudre course.classroom_requirement_ids (ids de ligne) en classroom_id réels côté
      // affichage/filtrage grille (dataStore.courseClassroomIdsMap).
      queryClient.fetchQuery({ queryKey: genericCacheKey('course_classroom_requirements'), queryFn: () => api.fetchAllGenericItems('course_classroom_requirements') }),
    ]);

    // Remplir le store pour accès O(1)
    dataStore.setCourses(coursesRes.items);
    dataStore.setTimeslots(timeslotsRes.items);
    dataStore.setTeachers(teachersRes.items);
    dataStore.setNonTeachingStaffs(nonTeachingRes.items);
    dataStore.setDivisions(divisionsRes.items);
    dataStore.setClassrooms(classroomsRes.items);
    dataStore.setCourseClassroomRequirements(classroomRequirementsRes.items);

    courses.value = coursesRes.items;
    timeslots.value = timeslotsRes.items;
    teachers.value = teachersRes.items;
    nonTeachingStaffs.value = nonTeachingRes.items;
    divisions.value = divisionsRes.items;
    classrooms.value = classroomsRes.items;

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
    const res = await api.apiFetch('/api/openapi.json').then(r => r.json());
    openApiSpec.value = res;
  } catch (err: any) {
    console.error("Échec du chargement de la spécification OpenAPI", err);
  }
}

// Même traitement que genericItems (voir plus haut) pour les caches "globaux" à clé statique
// (pas de filtre, pas de dépendance à la navigation) — schools, period_types, periods, groups,
// class_parts, materials, subjects. Ces refs partageaient déjà la même clé de cache TanStack
// Query que fkOptionsCache (['genericList', resourceName]) sans pour autant en profiter : chaque
// mutation devait explicitement rappeler loadSchools()/loadPeriodTypes()/etc pour rester à jour
// (voir la discussion sur les copies indépendantes d'une même table en mémoire navigateur,
// architecture.md §15.T). Devenues de vrais abonnés réactifs : invalider cette clé n'importe où
// (ex: invalidateFkCache) les rafraîchit désormais automatiquement.
//
// `enabled` (optionnel) : ces 7 caches n'existent que pour alimenter la grille EDT et ses
// dépendances (TimetableGrid, CoursePopin) — sauf schools, dont PreferenceGrid et
// PeriodTransitionManager ont AUSSI besoin (des panneaux de l'onglet admin, pas seulement
// timetable). Les charger inconditionnellement au montage de l'appli couplait leur déclenchement
// à la page d'accueil ACTUELLE (qui affiche la grille EDT par défaut) plutôt qu'au véritable
// besoin — un couplage accidentel, pas voulu : si la page d'accueil change un jour, ces 6-là se
// chargeraient quand même, pour rien, avant même que la grille EDT soit affichée une seule fois.
function bindGenericListQuery(resourceName: string, target: Ref<any[]>, enabled?: Ref<boolean> | (() => boolean)) {
  const query = useQuery({
    queryKey: genericCacheKey(resourceName),
    queryFn: () => api.fetchAllGenericItems(resourceName),
    ...(enabled !== undefined ? { enabled } : {}),
  });
  watch(() => query.data.value, (val) => {
    target.value = val?.items || [];
  });
  return query;
}

// Pas de wrapper loadX()/appel explicite au montage pour ces 7 : useQuery ci-dessus fait déjà son
// propre fetch automatique dès sa création (pas de enabled:false), donc au chargement initial.
// Un appel explicite supplémentaire ici (refetch() ou même invalidateQueries()) entrait en course
// avec ce fetch automatique ET avec loadFkOptionsForModel() (watch immediate sur activeAdminModel,
// qui interroge potentiellement la même clé de cache au même instant) : TanStack Query annule
// purement et simplement tout fetch déjà en vol dès qu'un second est déclenché pour la MÊME clé,
// quel que soit le mécanisme utilisé pour le déclencher — observé en conditions réelles
// (CancelledError répétées au montage). Pas de perte fonctionnelle : une mutation externe de l'une
// de ces 7 ressources reste rafraîchie normalement via resource:mutated -> invalidateFkCache (même
// clé exacte, voir plus bas) ; et un jeton d'écriture périmé (fin de résolution) ne les concerne de
// toute façon jamais — un solve ne touche jamais schools/period_types/periods/groups/class_parts/
// materials/subjects, seulement courses/timeslots.
const timetableTabActive = computed(() => activeTab.value === 'timetable');
bindGenericListQuery('schools', schoolsList); // pas de enabled : aussi requis par PreferenceGrid/PeriodTransitionManager (onglet admin)
bindGenericListQuery('period_types', periodTypesList, timetableTabActive);
bindGenericListQuery('periods', periodsList, timetableTabActive);
bindGenericListQuery('groups', groupsList, timetableTabActive);
bindGenericListQuery('class_parts', classPartsList, timetableTabActive);
bindGenericListQuery('materials', materialsList, timetableTabActive);
bindGenericListQuery('subjects', subjectsList, timetableTabActive);

// Conservée telle quelle (même nom, même contrat "appelable sans argument") pour tous les sites
// d'appel existants (navigation, après création, après suppression...) — ne fait plus qu'un
// refetch forcé de la query réactive ci-dessus ; genericItems/genericLoading se resynchronisent
// automatiquement via les watch() qui l'accompagnent, plus besoin de le faire ici à la main.
async function loadGenericItems() {
  try {
    await genericListQuery.refetch();
  } catch (err: any) {
    showNotification('error', err.message || 'Erreur lors du chargement des ressources');
  }
}

const fkOptionsCache = ref<Record<string, { items: Array<{ value: any; label: string; rawData?: any }> }>>({});

provide('fkOptionsCache', fkOptionsCache);

function toFkOptions(items: any[]) {
  return (items || []).map((item: any) => ({
    value: item.id,
    label: item.display_name || item.name || item.code || String(item.id),
    rawData: item,
  }));
}

// fkOptionsCache est un miroir réactif PASSIF du cache queryClient (voir architecture.md §15.T,
// "unification du cache generic") : toute query dont la clé est ['genericList', resource] SANS
// filtre (voir genericCacheKey) alimente automatiquement cette entrée, quelle que soit son
// origine — un des 7 caches globaux (bindGenericListQuery), le panneau admin actif sans filtre
// (genericListQuery), ou n'importe quel composant utilisant useGenericCache(resource) ailleurs
// dans l'app (ListPreviewField, GenericPivot...). Remplace l'ancienne écriture manuelle
// propre à refreshFkOptionsForResource seul : désormais N'IMPORTE QUEL déclencheur du même fetch
// (ex: une mutation invalidant la query via resource:mutated ailleurs) tient fkOptionsCache à
// jour, pas seulement un appel explicite à cette fonction précise — la duplication qu'on cherchait
// à éliminer n'était pas seulement réseau, mais aussi structurelle (deux ownership distincts pour
// une même collection).
queryClient.getQueryCache().subscribe((event: any) => {
  const key = event.query?.queryKey;
  if (!Array.isArray(key) || key[0] !== 'genericList' || key.length !== 2) return;
  const data = event.query.state.data;
  if (!data) return;
  fkOptionsCache.value[key[1]] = { items: toFkOptions(data.items) };
});

// S'assure que fkOptionsCache[resourceName] est frais, sans jamais le vider entre-temps (voir
// invalidateFkCache) — le fetch alimente le miroir ci-dessus, cette fonction ne fait qu'en garantir
// le déclenchement.
//
// Invalide TOUJOURS la query avant de la refetch : le QueryClient a un staleTime global de 1
// minute (main.ts), donc un simple fetchQuery() sur une queryKey déjà en cache (ex: chargée au
// montage de l'onglet) renvoie les données EN CACHE sans requête réseau, même juste après une
// mutation côté serveur — bug réel observé (le libellé d'un ServiceRepartition nouvellement
// recréé restait affiché sous forme d'ID brut malgré l'appel à ce refresh).
async function refreshFkOptionsForResource(resourceName: string) {
  try {
    await queryClient.invalidateQueries({ queryKey: genericCacheKey(resourceName) });
    await queryClient.fetchQuery({
      queryKey: genericCacheKey(resourceName),
      queryFn: () => api.fetchAllGenericItems(resourceName)
    });
  } catch (e) {
    console.error(`Failed to fetch options for resource ${resourceName}`, e);
  }
}

// Invalide ET rafraîchit immédiatement fkOptionsCache[resourceName] — ne JAMAIS se contenter de
// supprimer l'entrée : un widget affichant déjà cette ressource (ex: Many2ManyOrderedList, qui
// retombe sur field.options pour toute ligne pas encore éditée dans la session) se retrouverait
// avec des données vides pendant la fenêtre entre la suppression et le prochain rechargement —
// bug réel observé (ajouter une ligne "vidait" l'affichage des lignes existantes).
async function invalidateFkCache(resourceName: string) {
  await refreshFkOptionsForResource(resourceName);
}

function fkOptions(resourceName: string): Array<{ value: any; label: string }> {
  return fkOptionsCache.value[resourceName]?.items || [];
};

async function loadFkOptionsForModel(model: string) {
  if (!openApiSpec.value) return;
  const schemaName = `${model}_CreatePayload`;
  const schema = openApiSpec.value.components?.schemas?.[schemaName];
  if (!schema || !schema.properties) return;

  const resourcesToFetch = new Set<string>();

  for (const [key, prop] of Object.entries<any>(schema.properties)) {
    let resourceName = prop.resource;
    if (!resourceName && prop.anyOf) {
      const opt = prop.anyOf.find((o: any) => o.resource);
      if (opt) resourceName = opt.resource;
    }

    if (resourceName) {
      resourcesToFetch.add(resourceName);
    }
  }

  if (resourcesToFetch.size > 0) {
    await Promise.all(Array.from(resourcesToFetch).map(refreshFkOptionsForResource));
  }
}

// activeLeaf ajouté aux sources : activeAdminModel vaut 'schools' par défaut avant toute
// résolution de feuille (voir plus bas), donc sans ce garde-fou ce watch peut se déclencher sur
// cette valeur par défaut erronée dès que openApiSpec charge, avant que NotebooksTree n'ait
// restauré la vraie feuille depuis l'URL (onLeafChange) — provoquant des GET FK parasites
// (ex: teachers/divisions/classrooms/courses/periods, référencés par schools_CreatePayload).
//
// activeTab !== 'admin' ajouté séparément : onLeafChange ne remet jamais activeAdminModel à zéro
// pour une feuille sans panneau GenericForm (ex: la grille EDT elle-même) — sans ce garde,
// naviguer d'un panneau admin QUELCONQUE vers la grille redéclenche loadFkOptionsForModel() avec
// le modèle du DERNIER panneau admin visité, dont les dépendances FK n'ont aucune raison de
// recouper les besoins de la grille (ex: Disciplines -> disciplines/trmd_budgets, inutiles ici) —
// contrairement au cas "premier chargement" ci-dessus (activeAdminModel === 'schools' par défaut,
// dont les dépendances FK recoupent par coïncidence celles de loadData()). Même garde que
// refreshActiveGenericPanel un peu plus bas.
watch([activeAdminModel, openApiSpec, activeLeaf], () => {
  if (!activeLeaf.value || activeTab.value !== 'admin') return;
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

// Le rechargement du panneau maître sur navigation (changement d'onglet admin ou de ressource)
// est désormais géré nativement par genericListQuery (clé réactive + `enabled` sur activeTab,
// voir sa déclaration plus haut) — plus besoin de le redéclencher ici à la main. Seul le
// rechargement de la grille EDT au retour sur l'onglet Emploi du temps reste explicite.
watch([activeTab, activeAdminModel], ([newTab], [oldTab]) => {
  if (newTab !== 'admin' && newTab !== oldTab) {
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

// Point unique de synchronisation de l'URL (voir architecture.md, "URLs profondes") — centralise
// toute la logique push/replace pour éviter toute incohérence entre plusieurs endroits qui
// écriraient l'URL indépendamment. `push` (nouvelle entrée d'historique) uniquement quand le
// CHEMIN change (vraie navigation "page") ; `replace` (pas de nouvelle entrée) quand seule la
// sélection change (coche une ligne) — le bouton Précédent du navigateur navigue ainsi entre
// feuilles visitées, pas entre chaque clic de ligne individuel.
//
// awaitingSelectionRestore gère un piège d'ordonnancement : la restauration d'une sélection
// depuis l'URL est asynchrone (GenericList l'applique une fois `items` chargé, voir son watch
// dédié), alors que onLeafChange remet toujours selectedParentIds à [] de façon synchrone en
// premier — sans garde, le déclenchement immédiat de ce watcher écrirait une URL sans ids et
// effacerait ceux collés par l'utilisateur (ou restaurés au clic Précédent) avant même qu'ils
// aient eu la chance d'être appliqués. On ignore donc UN SEUL déclenchement par restauration
// armée (au montage, ou après un popstate, voir onMounted) ; s'il ne s'agit que d'un état
// transitoire, le déclenchement suivant (sélection réellement restaurée) écrit l'URL définitive
// avec push:false (le chemin, lui, n'a pas changé entre les deux) ; si la restauration échoue
// (ids invalides), l'URL est nettoyée au déclenchement suivant plutôt que de rester bloquée.
watch([currentPathIds, selectedParentIds], ([pathIds, ids]) => {
  if (!pathIds || pathIds.length === 0) return;
  const pathKey = pathIds.join('/');
  if (awaitingSelectionRestore) {
    awaitingSelectionRestore = false;
    lastSyncedPathKey = pathKey;
    if (ids.length === 0) return;
  }
  const push = pathKey !== lastSyncedPathKey;
  lastSyncedPathKey = pathKey;
  syncUrl(pathIds, ids, { push });
}, { deep: true });

async function onAddGeneric() {
  formTitle.value = `Ajouter un élément`;

  // Valeurs par défaut : OpenAPI (statiques) puis serveur (dynamiques, voir CRUDMixin.default_get,
  // pendant Odoo default_get()) puis champs fixes ui.json (prioritaires, override explicite).
  const defaults: Record<string, any> = {};
  formFieldsConfig.value.forEach((field: any) => {
    if (field.default !== undefined) {
      defaults[field.key] = field.default;
    }
  });
  const serverDefaults = await api.fetchDefaults(activeAdminModel.value, {});
  Object.assign(defaults, serverDefaults);
  const formPanel = activeLeaf.value?.panels?.find((p: any) => p.component === 'GenericForm');
  if (formPanel?.formConfig?.fixedFields) {
    Object.assign(defaults, formPanel.formConfig.fixedFields);
  }
  formModel.value = defaults;
  selectedRelatedRecords.value = [];
  selectedParentIds.value = [];
  isEditing.value = false;

  if (isListEditableInline.value) {
    genericItems.value = [{ ...defaults, id: 'new_' + Date.now() }, ...genericItems.value];
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
      } else if (!isEditModalDisabled.value) {
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
      // Capture les réponses serveur (pas le payload envoyé) pour chaque ligne : même raison que
      // pour l'édition simple plus bas dans cette fonction — un champ peut être recalculé côté
      // backend en effet de bord (ex: Service.weekly_duration_split_minutes régénère ses
      // ServiceRepartition liées), et s'y fier laissait l'affichage local périmé jusqu'à un F5.
      // Reste vide pour la branche relationName ci-dessous : elle édite une ressource différente
      // de activeAdminModel.value, donc le merge local qui suit est de toute façon ignoré.
      let updatedItems: any[] = [];
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
        updatedItems = await Promise.all(
          selectedParentIds.value.map(id => api.updateGenericItem(targetResource, id, value))
        );
      }
      showNotification('success', 'Ressources modifiées en masse avec succès !');
      loadFkOptionsForModel(targetResource);

      // Update local state directly instead of full reload if we modified the main resource
      if (targetResource === activeAdminModel.value) {
        selectedParentIds.value.forEach((id, index) => {
          const idx = genericItems.value.findIndex(x => x.id === id);
          if (idx !== -1) {
            setGenericItemAt(idx, { ...genericItems.value[idx], ...(updatedItems[index] || value) });
          }
        });
      }

      await onSelectionChangeGeneric([...selectedParentIds.value]);
    } else if (isEditing.value) {
      // Capture et réutilise la réponse serveur (pas le payload envoyé) : une mise à jour peut
      // déclencher des effets de bord côté backend sur d'AUTRES champs que ceux soumis (ex:
      // Service.weekly_duration_split_minutes régénère ses ServiceRepartition liées) — se fier au
      // payload soumis pour rafraîchir l'affichage local laissait ces champs dérivés périmés à
      // l'écran jusqu'à un F5.
      const updated = await api.updateGenericItem(targetResource, value.id, value);
      showNotification('success', 'Ressource modifiée avec succès !');
      // Pas d'invalidateFkCache(targetResource) direct ici : le dispatch resource:mutated
      // juste en dessous s'en charge déjà (son handler l'appelle inconditionnellement pour la
      // ressource mutée) — l'appeler aussi ici doublait le nombre de requêtes réseau déclenchées
      // par cette sauvegarde sans le moindre bénéfice (voir architecture.md §15.T).
      // Rafraîchit aussi le cache des ressources référencées par les champs relation de
      // targetResource lui-même (ex: repartition_ids -> service_repartitions) — sans quoi
      // l'étiquette affiche l'ID brut au lieu du nom pour toute ligne enfant régénérée côté
      // backend (voir loadFkOptionsForModel, déjà utilisé au changement d'onglet admin).
      loadFkOptionsForModel(targetResource);

      // Update local state directly instead of full reload if we modified the main resource
      if (targetResource === activeAdminModel.value) {
        const idx = genericItems.value.findIndex(x => x.id === value.id);
        if (idx !== -1) {
          setGenericItemAt(idx, { ...genericItems.value[idx], ...updated });
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
          formModel.value = { ...updated };
          isEditing.value = true;
        }
      } else {
        showFormModal.value = false;
        formModel.value = {};
        isEditing.value = false;
      }
    } else {
      const created = await api.createGenericItem(targetResource, value);
      showNotification('success', 'Ressource créée avec succès !');
      // Pas d'invalidateFkCache(targetResource) direct ici : le dispatch resource:mutated
      // juste en dessous s'en charge déjà (voir la même remarque plus haut dans cette fonction).
      loadFkOptionsForModel(targetResource);

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
    setGenericItemAt(idx, item);
  }

  try {
    if (String(item.id).startsWith('new_')) {
      const payload = { ...item };
      delete payload.id;
      const created = await api.createGenericItem(activeAdminModel.value, payload);
      if (idx !== -1) {
        setGenericItemAt(idx, created);
      }
      // Pas d'invalidateFkCache direct ici : le dispatch resource:mutated en fin de fonction
      // s'en charge déjà (voir la même remarque dans onSubmitGeneric plus haut).
      loadFkOptionsForModel(activeAdminModel.value);
      showNotification('success', 'Élément créé directement !');
    } else {
      // Capture et réutilise la réponse serveur (pas le payload envoyé) : une mise à jour peut
      // déclencher des effets de bord côté backend sur d'AUTRES champs que ceux soumis (ex:
      // Service.weekly_duration_split_minutes régénère ses ServiceRepartition liées, dont les IDs
      // changent) — s'en tenir au payload soumis laissait genericItems[idx] à jamais périmé.
      const updated = await api.updateGenericItem(activeAdminModel.value, item.id, item);
      if (idx !== -1) {
        setGenericItemAt(idx, updated);
      }
      // Pas d'invalidateFkCache direct ici non plus (voir juste au-dessus dans cette même
      // fonction) : le dispatch resource:mutated en fin de fonction s'en charge déjà.
      // invalidateFkCache ne rafraîchit que le cache de activeAdminModel.value lui-même — pas
      // celui des ressources référencées par SES propres champs relation (ex: repartition_ids ->
      // service_repartitions), d'où l'ID brut affiché dans l'étiquette au lieu du nom tant que ce
      // cache-là n'est pas explicitement rafraîchi (voir loadFkOptionsForModel, déjà utilisé au
      // changement d'onglet admin).
      loadFkOptionsForModel(activeAdminModel.value);
      showNotification('success', 'Élément mis à jour directement !');
    }

    window.dispatchEvent(new CustomEvent('resource:mutated', {
      detail: { resource_name: activeAdminModel.value }
    }));
  } catch (err: any) {
    showNotification('error', err.message || 'Échec de l\'enregistrement en ligne.');
    // En cas d'erreur, on restaure l'ancienne valeur, sauf si c'est une nouvelle ligne (pour ne pas perdre la saisie)
    if (idx !== -1 && oldItem && !String(item.id).startsWith('new_')) {
      setGenericItemAt(idx, oldItem);
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
          // Séquentiel, pas fire-and-forget : invalidateFkCache(activeAdminModel.value) et
          // loadData() peuvent cibler la MÊME clé de cache (ex: activeAdminModel === 'teachers',
          // aussi l'une des 6 ressources rechargées par loadData) — lancés en parallèle, TanStack
          // Query annule l'un des deux fetchQuery en vol (CancelledError visible à l'utilisateur,
          // découvert en testant ce chemin — voir architecture.md §15.T sur cette même classe de
          // course au montage).
          await invalidateFkCache(activeAdminModel.value);
          showNotification('success', 'Ressource supprimée et séances dépositionnées avec succès !');
          showFormModal.value = false;
          formModel.value = {};
          await loadGenericItems();
          await loadData();
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
      // Pas d'invalidateFkCache direct ici : le dispatch resource:mutated juste en dessous s'en
      // charge déjà (voir la même remarque dans onSubmitGeneric plus haut).
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

// Mesure réelle (canvas) de la largeur d'un texte, plutôt qu'une estimation par nombre de
// caractères (ex: longueur * 8.5px) — beaucoup trop imprécise pour une police proportionnelle
// (largeur très variable d'un caractère à l'autre, accents français compris) : produisait des
// colonnes visiblement plus larges que nécessaire (ex: colonne Discipline). Même police que le
// texte réellement affiché en cellule (voir .body-td, 13px, --font-sans).
let columnWidthMeasureCtx: CanvasRenderingContext2D | null = null;
function measureTextWidth(text: string): number {
  if (!columnWidthMeasureCtx) {
    columnWidthMeasureCtx = document.createElement('canvas').getContext('2d');
  }
  if (!columnWidthMeasureCtx) return text.length * 7; // repli si canvas indisponible
  columnWidthMeasureCtx.font = "13px 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
  return columnWidthMeasureCtx.measureText(text).width;
}

// Configurations dynamiques de colonnes pour GenericList
function buildColumnsConfig(model: string, items: any[]) {
  // --- GÉNÉRATION DYNAMIQUE VIA OPENAPI (LOW-CODE) ---
  if (openApiSpec.value && openApiSpec.value.components && openApiSpec.value.components.schemas) {
    const schemaName = `${model}_ReadPayload`;

    const schema = openApiSpec.value.components.schemas[schemaName];
    if (schema && schema.properties) {
      const dynamicColumns = [];
      for (const [key, prop] of Object.entries<any>(schema.properties)) {
        if (key === 'id' || key === 'display_name' || prop.hidden === true) continue; // On masque l'ID technique, display_name et les champs de support (info={"hidden": True})

        let colWidth = prop.list_width;
        if (!colWidth && prop.widget === 'relation_browser') {
          // Juste un bouton icône (voir RelationBrowserField.vue) : jamais de calcul par contenu,
          // qui se baserait sur la liste des libellés liés (potentiellement très longue) alors que
          // la cellule n'affiche qu'un bouton. 32px = tout juste la taille du bouton (icône 14px +
          // padding 4px/6px), la colonne ne doit pas être plus large que la loupe elle-même.
          colWidth = 32;
        }
        if (!colWidth) {
          let baseType = prop.type;
          let baseFormat = prop.format;
          if (!baseType && prop.anyOf) {
            const validOption = prop.anyOf.find((o: any) => o.type && o.type !== 'null');
            if (validOption) {
              baseType = validOption.type;
              if (!baseFormat) baseFormat = validOption.format;
            }
          }

          if (baseType === 'boolean') colWidth = 100;
          // prop.ui_type, jamais key === 'color' : un champ nommé "color" sans "type": "color"
          // explicite côté backend doit rester un champ texte brut, pas se voir imposer un widget
          // par magie de nommage (voir architecture.md).
          else if (prop.ui_type === 'color') colWidth = 80;
          else if (prop.ui_type === 'duration') colWidth = 100;
          // prop.ui_type en repli : un TransientModel (ex: TrmdLine) n'a pas de "type" JSON-Schema
          // réel (Optional[Any], voir generic.py::make_pydantic_model) — seul ui_type porte
          // l'information "nombre" pour ces champs, sans quoi ils retombaient dans le calcul par
          // longueur de contenu ci-dessous (beaucoup trop large pour une simple valeur numérique).
          else if (baseType === 'integer' || baseType === 'number' || prop.ui_type === 'number') colWidth = 100;
          else if (baseFormat === 'date-time' || baseFormat === 'date') colWidth = 160;
          else {
            // Calcul dynamique basé sur le contenu réel des données — largeur de texte mesurée
            // (measureTextWidth), pas une estimation par nombre de caractères.
            let maxTextWidth = measureTextWidth(prop.title || key);

            for (const item of (items || []).slice(0, 100)) {
              const val = item[key];
              if (val !== undefined && val !== null) {
                let strVal = '';

                // Si c'est une clé étrangère, tenter de trouver le label
                const resourceName = prop.resource || (prop.anyOf && prop.anyOf.find((o: any) => o.resource)?.resource);
                if (resourceName && fkOptionsCache.value[resourceName]) {
                  const options = fkOptionsCache.value[resourceName].items;
                  if (Array.isArray(val)) {
                    strVal = val.map(v => {
                      const opt = options.find((o: any) => String(o.value) === String(v));
                      return opt ? opt.label : String(v);
                    }).join(', ');
                  } else {
                    const opt = options.find((o: any) => String(o.value) === String(val));
                    strVal = opt ? opt.label : String(val);
                  }
                } else {
                  strVal = Array.isArray(val) ? val.join(', ') : String(val);
                }

                const textWidth = measureTextWidth(strVal);
                if (textWidth > maxTextWidth) {
                  maxTextWidth = textWidth;
                }
              }
            }
            // + 60px pour marges/icônes de l'en-tête (padding, indicateur de tri) — voir .header-th
            // (min 150px, max 500px)
            colWidth = Math.min(Math.max(Math.ceil(maxTextWidth) + 60, 150), 500);
          }
        }

        dynamicColumns.push({
          key: key,
          label: prop.title || key,
          width: colWidth || undefined // Si manquant, GenericList fera un width: auto
        });
      }
      return dynamicColumns;
    }
  }
  // ---------------------------------------------------
  return [];
}

const columnsConfig = computed(() => buildColumnsConfig(activeAdminModel.value, genericItems.value));

// --- Panneau "détail" : une seconde GenericList indépendante dans le même onglet, filtrée par
// la sélection courante du panneau "maître" (ex: Services par classe -> Divisions | Services).
const detailListItems = ref<any[]>([]);
const detailListLoading = ref(false);

function getDetailPanel() {
  return activeLeaf.value?.panels?.find((p: any) => p.component === 'GenericList' && p.role === 'detail');
}

const detailColumnsConfig = computed(() => {
  const detailPanel = getDetailPanel();
  if (!detailPanel) return [];
  return buildColumnsConfig(detailPanel.resourceKey, detailListItems.value);
});

async function loadDetailListItems() {
  const detailPanel = getDetailPanel();
  if (!detailPanel) {
    detailListItems.value = [];
    return;
  }
  if (selectedParentIds.value.length !== 1) {
    detailListItems.value = [];
    return;
  }
  const masterItem = genericItems.value.find(x => x.id === selectedParentIds.value[0]);
  const masterField = detailPanel.listConfig?.filterFromMasterField;
  const filterField = detailPanel.listConfig?.filterByField;
  if (!masterItem || !masterField || !filterField) {
    detailListItems.value = [];
    return;
  }
  const masterVal = masterItem[masterField];
  const filterValues = Array.isArray(masterVal) ? masterVal : (masterVal !== undefined && masterVal !== null ? [masterVal] : []);
  if (filterValues.length === 0) {
    detailListItems.value = [];
    return;
  }

  detailListLoading.value = true;
  try {
    // Filtrage côté client sur l'ensemble des valeurs du champ maître (ex: tous les service_ids
    // d'une classe, pas seulement le premier) : le endpoint générique ne filtre que sur une valeur
    // scalaire, donc on récupère la liste complète puis on garde les lignes dont filterField
    // correspond à l'une des valeurs du maître.
    const res = await api.fetchAllGenericItems(detailPanel.resourceKey);
    const filterSet = new Set(filterValues);
    detailListItems.value = res.items.filter((item: any) => filterSet.has(item[filterField]));
  } catch (err: any) {
    showNotification('error', err.message || 'Erreur lors du chargement de la liste détaillée');
    detailListItems.value = [];
  } finally {
    detailListLoading.value = false;
  }
}

watch([selectedParentIds, genericItems, activeLeaf], loadDetailListItems);

watch(activeLeaf, () => {
  const detailPanel = getDetailPanel();
  if (detailPanel) {
    loadFkOptionsForModel(detailPanel.resourceKey);
  }
}, { immediate: true });

// Ajout d'une ligne dans le panneau détail : crée un brouillon local (id "new_...", non
// persisté), pré-rempli avec les valeurs par défaut OpenAPI puis serveur (voir CRUDMixin.default_get,
// backend/app/models/base.py — pendant de default_get() côté Odoo). Le contexte transmis (ressource
// + id de la sélection maître) est un contrat libre entre le frontend et default_get() côté modèle,
// pas une config déclarée dans ui.json. La ligne n'est réellement créée côté serveur qu'à la
// première édition inline (voir onUpdateDetailGenericInline).
async function onAddDetailGeneric() {
  const detailPanel = getDetailPanel();
  if (!detailPanel || selectedParentIds.value.length !== 1) return;

  const masterPanel = activeLeaf.value?.panels?.find((p: any) => p.component === 'GenericList' && p.role !== 'detail');
  const masterItem = genericItems.value.find(x => x.id === selectedParentIds.value[0]);

  // Valeurs par défaut : OpenAPI (statiques) puis serveur (dynamiques, voir default_get).
  const newItem: Record<string, any> = {};
  getFormFieldsConfig(detailPanel.resourceKey).forEach((field: any) => {
    if (field.default !== undefined) {
      newItem[field.key] = field.default;
    }
  });
  const context = masterPanel && masterItem ? { resource: masterPanel.resourceKey, id: masterItem.id } : {};
  const serverDefaults = await api.fetchDefaults(detailPanel.resourceKey, context);
  Object.assign(newItem, serverDefaults);

  detailListItems.value.unshift({ ...newItem, id: 'new_' + Date.now() });
}

async function onUpdateDetailGenericInline(item: any) {
  const detailPanel = getDetailPanel();
  if (!detailPanel) return;

  // Optimistic UI update: on applique la modif localement tout de suite
  const idx = detailListItems.value.findIndex(x => x.id === item.id);
  let oldItem = null;
  if (idx !== -1) {
    oldItem = { ...detailListItems.value[idx] };
    detailListItems.value[idx] = item;
  }

  try {
    if (String(item.id).startsWith('new_')) {
      const payload = { ...item };
      delete payload.id;
      const created = await api.createGenericItem(detailPanel.resourceKey, payload);
      if (idx !== -1) {
        detailListItems.value[idx] = created;
      }
      invalidateFkCache(detailPanel.resourceKey);
      loadFkOptionsForModel(detailPanel.resourceKey);
      showNotification('success', 'Élément créé directement !');
    } else {
      // Capture et réutilise la réponse serveur (pas le payload envoyé) — voir même correctif dans
      // onUpdateGenericInline juste au-dessus.
      const updated = await api.updateGenericItem(detailPanel.resourceKey, item.id, item);
      if (idx !== -1) {
        detailListItems.value[idx] = updated;
      }
      invalidateFkCache(detailPanel.resourceKey);
      // Rafraîchit aussi le cache des ressources référencées par les champs relation de
      // detailPanel.resourceKey lui-même (voir commentaire équivalent dans onUpdateGenericInline).
      loadFkOptionsForModel(detailPanel.resourceKey);
      showNotification('success', 'Élément mis à jour directement !');
    }
    window.dispatchEvent(new CustomEvent('resource:mutated', {
      detail: { resource_name: detailPanel.resourceKey }
    }));
  } catch (err: any) {
    showNotification('error', err.message || 'Échec de l\'enregistrement en ligne.');
    if (idx !== -1 && oldItem && !String(item.id).startsWith('new_')) {
      detailListItems.value[idx] = oldItem;
    }
  }
}

// Lecture seule automatique pilotée par les droits (voir architecture.md, moteur de droits) :
// /api/ui/menus calcule panel.access.readOnly par panel (pas de droit d'écriture sur la ressource
// visée) — fusionné ici dans les flags listConfig/formConfig déjà existants (architecture.md
// §15.E/W), jamais un nouveau mécanisme : GenericList.vue/GenericForm.vue n'ont besoin d'aucune
// modification, ils honorent déjà ces flags depuis leur configuration ui.json statique.
function accessAwareListConfig(panel: any) {
  if (!panel?.access?.readOnly) return panel?.listConfig;
  return { ...panel.listConfig, editableInline: false, disableAdd: true, disableDelete: true };
}
function accessAwareFormConfig(panel: any) {
  if (!panel?.access?.readOnly) return panel?.formConfig;
  return { ...panel.formConfig, editableForm: false, deletable: false };
}

// Configurations dynamiques de champs pour GenericForm
function getFormFieldsConfig(resourceKey?: string) {
  const model = resourceKey || activeAdminModel.value;
  const schoolOptions = schoolsList.value.map(s => ({ value: s.id, label: s.name }));
  const periodTypeOptions = periodTypesList.value.map(pt => ({ value: pt.id, label: pt.name || pt.label }));

  // On extrait dynamiquement les heures de début de la vraie grille de l'école !
  const timeSet = new Set<string>();
  timeslots.value.forEach((ts: any) => {
    const hour = getTimeslotHour(ts);
    if (hour !== undefined && hour !== null) {
      // Format start time (e.g. 8.5 -> "08:30")
      const h = Math.floor(hour);
      const m = Math.round((hour - h) * 60);
      const timeStr = `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
      timeSet.add(timeStr);

      // Format approximate end time (+1h par défaut) pour avoir des options de fin de journée cohérentes
      const h2 = Math.floor(hour + 1);
      const m2 = Math.round(((hour + 1) - h2) * 60);
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
        if (key === 'id' || key === 'display_name' || prop.hidden === true) continue; // On masque l'ID, display_name et les champs de support (info={"hidden": True}) dans le formulaire

        let baseType = prop.type;
        let resourceName = prop.resource;
        let baseFormat = prop.format;
        // Gérer les champs optionnels (nullable) de Pydantic qui utilisent anyOf — format doit
        // être déballé au même titre que type/resource, sans quoi un champ Date nullable (ex:
        // Optional[date]) perd son format 'date' (porté par la branche anyOf, jamais au niveau
        // racine du schéma) et retombe en simple texte au lieu du widget <input type="date">.
        if (!baseType && prop.anyOf) {
          const validOption = prop.anyOf.find((o: any) => o.type && o.type !== 'null');
          if (validOption) {
            baseType = validOption.type;
            if (!baseFormat) baseFormat = validOption.format;
          }

          const opt = prop.anyOf.find((o: any) => o.resource);
          if (opt) resourceName = opt.resource;
        }

        let fieldType = prop.ui_type || baseType || 'text';
        if (fieldType === 'string') fieldType = 'text'; // OpenAPI renvoie string, mais le form attend text
        else if (fieldType === 'boolean') fieldType = 'boolean';
        else if (fieldType === 'integer' || fieldType === 'number') fieldType = 'number';

        if (fieldType === 'text' && baseFormat === 'date') fieldType = 'date';

        let options = prop.options || undefined;
        if (fieldType === 'time') { fieldType = 'select'; options = timeOptions; }
        else if ((fieldType === 'array' || fieldType === 'multiselect') && resourceName) {
          fieldType = 'multiselect';
          options = fkOptions(resourceName);
        }
        else if (resourceName) {
          // Si on a explicitement forcé ui_type = 'multiselect', on ne l'écrase pas en 'select'
          if (fieldType !== 'multiselect') {
            fieldType = 'select';
          }
          options = fkOptions(resourceName);
        }
        else if (options) { fieldType = 'select'; }
        
        dynamicFields.push({
          key: key,
          label: prop.title || key,
          type: fieldType,
          // required_field (voir teacher.py::discipline_lines) fusionné directement ici : clé
          // backend dédiée (info={}) distincte du `required` JSON-Schema réservé (présence de la
          // clé dans le payload, schema.required ci-dessus) pour éviter de faire planter la
          // génération OpenAPI — mais côté frontend, un seul et même `required`, générique à
          // n'importe quel type de champ (scalaire, relation, collection...), pas seulement les
          // relations possédées.
          required: requiredFields.includes(key) || prop.required_field === true,
          requiredExpr: prop.requiredExpr,
          readOnly: prop.readOnly,
          readOnlyExpr: prop.readOnlyExpr,
          invisibleExpr: prop.invisibleExpr,
          placeholder: prop.placeholder || '',
          min: prop.min,
          max: prop.max,
          step: prop.step,
          options: options,
          resource: resourceName,
          parentField: prop.parentField,
          // false uniquement si le backend l'affirme explicitement (colonne SQL nullable=False,
          // voir generic.py::make_pydantic_model) — absent pour les champs virtuels/relations,
          // qu'on continue de considérer effaçables comme avant cet ajout.
          nullable: prop.nullable !== false,
          default: prop.default,
          help: prop.help,
          widget: prop.widget,
          widgetParams: prop.widgetParams,
          // false uniquement si déclaré explicitement (info={"sortable": False} côté backend) —
          // même convention que nullable ci-dessus, triable par défaut.
          sortable: prop.sortable !== false,
          // Même principe pour la zone de saisie de la ligne de filtrage (info={"filterable": False}).
          filterable: prop.filterable !== false,
          // Pour un champ "type": "duration" dont 0 minute est une valeur valide ("modalité non
          // utilisée", voir Service/MefService.weekly_duration_*_minutes) — insère l'option
          // "Aucune" dans la liste déroulante (voir DurationInput.vue::getDurationOptions).
          durationIncludeZero: prop.durationIncludeZero === true
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
async function onMoveCourse(courseId: number, timeslotId: number, weekType?: 'A' | 'B') {
  const previousCoursesState = JSON.parse(JSON.stringify(courses.value));
  const oldScore = scoreData.value ? { ...scoreData.value } : null;

  const courseIndex = courses.value.findIndex(c => c.id === courseId);
  const courseObj = courseIndex !== -1 ? courses.value[courseIndex] : null;

  if (courseIndex !== -1) {
    courses.value[courseIndex].timeslot_id = timeslotId;
    if (weekType) {
      courses.value[courseIndex].week_type = weekType;
    }
  }

  try {
    const response = await api.updateCourse(courseId, timeslotId, undefined, weekType);
    
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
        // fetchAllGenericItems plutôt qu'un limit=1000 codé en dur : au-delà du seuil, les
        // préférences excédentaires étaient perdues sans erreur — donc une préférence « Rouge »
        // pouvait ne jamais déclencher l'alerte ci-dessous, silencieusement. La fonction pagine
        // jusqu'à tout avoir (voir services/api.ts).
        const prefResData = await api.fetchAllGenericItems('resource_preferences', undefined, { timeslot_id: timeslotId });
        const prefRes = prefResData.items || [];
        const unsuitedPref = prefRes.find((p: any) => 
          p.preference_level === 'Unsuited' && (
            (p.resource_type === 'Teacher' && courseObj.teacher_ids && courseObj.teacher_ids.includes(p.resource_id)) ||
            (p.resource_type === 'Classroom' && (dataStore.courseClassroomIdsMap[courseObj.id] || []).includes(p.resource_id)) ||
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

// La Fiche T (CoursePopin) appelle elle-même l'API générique pour éditer une ressource d'un cours
// et attend en retour l'objet cours complet renvoyé par le serveur (pas seulement le champ
// modifié) : une modification peut en cascader d'autres (ex: cascade Group<->ClassPart,
// recalcul de decomposition_status/underventilated_resource_ids). Remplacer l'entrée dans
// `courses` ici propage la mise à jour par réactivité à la grille, la Sidebar et la Fiche T
// elle-même, sans rechargement complet (même principe que onUnassignCourse/onTogglePinCourse).
function onCoursePopinCourseUpdated(updatedCourse: Course) {
  const idx = courses.value.findIndex(c => c.id === updatedCourse.id);
  if (idx !== -1) {
    courses.value[idx] = updatedCourse;
  }
  invalidateFkCache('courses');
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
    if (res.status === 'SOLVING' || res.status === 'QUEUED') {
      loading.value = true;
      solverIsQueued.value = res.status === 'QUEUED';
      solverProgress.value = res.progress;
      solverElapsedSeconds.value = res.elapsed_seconds;
      solverTimeLimitSeconds.value = res.time_limit_seconds;
      solverQueuePosition.value = res.queue_position;
      solverQueueLength.value = res.queue_length;
      solverKind.value = res.kind;
      solverPipelineStep.value = res.pipeline_step;
      solverPipelineTotalSteps.value = res.pipeline_total_steps;
      if (!pollingInterval) {
        pollingInterval = window.setInterval(checkStatus, 3000);
      }
    } else {
      if (loading.value) {
        loading.value = false;
        loadData();
      }
      solverIsQueued.value = false;
      solverProgress.value = null;
      solverElapsedSeconds.value = null;
      solverTimeLimitSeconds.value = null;
      solverQueuePosition.value = null;
      solverQueueLength.value = 0;
      solverKind.value = null;
      solverPipelineStep.value = 1;
      solverPipelineTotalSteps.value = 1;
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

// Déclenché par GenericForm.vue (voir wizard-success) quand le wizard soumis vient de lancer une
// résolution asynchrone en arrière-plan (placement, attribution des salles, optimisation — voir
// startsBackgroundJob dans GenericWizard.vue) — même effet que l'ancien onCoursePlacement/
// onClassroomAssignment directs, mais générique : App.vue n'a pas besoin de connaître la liste des
// wizards concernés, seulement de réagir à ce flag déclaré côté backend.
function onWizardJobStarted(payload: { startsBackgroundJob: boolean }) {
  if (payload?.startsBackgroundJob) {
    loading.value = true;
    checkStatus();
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
      // Pas de c.classroom_requirement_ids = [] ici : POST /reset (endpoints.py) ne touche que
      // timeslot_id/is_pinned, jamais les exigences de salle (voir plan salles §4) — les 2
      // domaines sont indépendants depuis la séparation COURSE_PLACEMENT/CLASSROOM_ASSIGNMENT.
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
    const res = await api.apiFetch('/api/generic/system_settings').then(r => r.json());
    const items = res.items || [];
    const durationSetting = items.find((item: any) => item.key === 'STANDARD_TIMESLOT_DURATION');
    globalTimeslotDuration.value = durationSetting ? Number(durationSetting.value) : 30;
  } catch (e) {
    console.error("Failed to load standard timeslot duration config", e);
  }
}

// Rechargement global des données en cache (mêmes appels qu'au montage) — factorisé pour être
// aussi réutilisable par le mécanisme de jeton d'écriture périmé (voir onMounted ci-dessous et
// architecture.md, "mode exclusif") : nos données locales doivent être rafraîchies exactement de
// la même façon qu'à l'ouverture de l'application, que ce soit au premier chargement ou après
// avoir détecté qu'elles ont divergé (ex: une résolution automatique vient de se terminer).
function reloadAllData() {
  loadData();
  // schools/period_types/periods/groups/class_parts/materials/subjects : pas rechargés ici
  // (voir bindGenericListQuery plus haut) — un solve ne touche jamais ces ressources, et une
  // mutation externe les rafraîchit déjà via resource:mutated -> invalidateFkCache.
  refreshActiveGenericPanel();
}

// Rafraîchit génériquement le panneau maître (genericItems) et, s'il dépend du même
// enregistrement sélectionné, le panneau détail (detailListItems) — quelle que soit la ressource
// affichée. Remplace le besoin d'étendre au cas par cas une liste codée en dur à chaque nouvelle
// ressource : fonctionne pour les ~60 ressources exposées par l'API générique, pas seulement
// celles qui ont un cache global dédié (schools, period_types... juste au-dessus, qui restent
// nécessaires pour d'autres usages indépendants du panneau actif, ex: le sélecteur
// d'établissement).
//
// invalidateQueries (pas loadGenericItems/refetch) : un refetch forcé déclenche TOUJOURS une
// nouvelle requête réseau, même si une invalidation identique vient déjà d'en déclencher une
// (ex: invalidateFkCache, appelée juste avant dans le handler resource:mutated, invalide déjà
// exactement le même préfixe de clé) — deux requêtes réseau redondantes pour la même donnée.
// invalidateQueries se contente de marquer périmé et laisse l'abonné actif (genericListQuery)
// se recharger une seule fois, quel que soit le nombre d'appels à invalidateQueries pour la même
// clé dans le même tick (voir architecture.md §15.T).
async function refreshActiveGenericPanel() {
  if (activeTab.value !== 'admin') return;
  await queryClient.invalidateQueries({ queryKey: ['genericList', activeAdminModel.value] });
  await loadDetailListItems();
}

// Variante ciblée pour resource:mutated (voir plus bas) : on connaît la ressource mutée, donc on
// ne rafraîchit que si elle correspond effectivement à ce qui est affiché (maître ou détail) —
// contrairement à refreshActiveGenericPanel, toujours inconditionnel, adapté au signal plus flou
// "le jeton d'écriture a changé, on ne sait pas précisément quoi a bougé".
async function refreshActiveGenericPanelIfMatches(resource: string) {
  if (activeTab.value !== 'admin') return;
  if (resource === activeAdminModel.value) {
    await queryClient.invalidateQueries({ queryKey: ['genericList', resource] });
    // Le formulaire ouvert (formModel) est un INSTANTANÉ pris à la sélection (onSelectionChangeGeneric/
    // onEditGeneric), jamais lui-même relié à la query — une mutation hors du cycle submit/update
    // habituel (ex: le wizard "Décomposer le cours", dont chaque étape écrit directement en base via
    // RPC, voir GenericWizard.vue) ne le rafraîchit donc pas tout seul : sans ça, le champ "Cours
    // enfants" et le mapping pré-rempli à la réouverture du wizard resteraient périmés jusqu'au
    // prochain changement de sélection. genericItems.value est déjà à jour à cet instant (watch
    // flush:'sync' sur genericListQuery.data, voir plus haut) : on y relit la copie fraîche plutôt que
    // de refaire un appel réseau dédié.
    if (formModel.value?.id != null) {
      const fresh = genericItems.value.find((x: any) => x.id === formModel.value.id);
      if (fresh) formModel.value = { ...fresh };
    }
    await loadDetailListItems();
    return;
  }
  const detailPanel = getDetailPanel();
  if (detailPanel && resource === detailPanel.resourceKey) {
    await loadDetailListItems();
  }
}

onMounted(async () => {
  // Aucune base sélectionnée (premier accès, cookie expiré/effacé) : redirection vers le
  // sélecteur avant toute autre chose — sans ça, tous les appels API qui suivent échoueraient en
  // boucle (428, voir services/api.ts::apiFetch) sans que l'utilisateur comprenne pourquoi.
  if (!getSelectedDatabase()) {
    const next = window.location.pathname + window.location.search;
    window.location.href = `/select-database?next=${encodeURIComponent(next)}`;
    return;
  }

  await loadOpenApiSpec();
  await loadTimeslotConfig();
  reloadAllData();
  checkStatus();

  // Jeton d'écriture périmé (voir services/api.ts::apiFetch, architecture.md "mode exclusif") :
  // le backend annonce un jeton différent de celui qu'on connaissait, sur n'importe quelle
  // réponse. Deux cas, distingués par wasWriteAttempt :
  // - Simple lecture devenue périmée (ex: on vient d'apprendre qu'une résolution automatique
  //   s'est terminée en arrière-plan) : rechargement silencieux, sans interrompre l'utilisateur.
  // - Une ÉCRITURE vient d'être activement rejetée (409, voir write_token_middleware.py) parce que
  //   son jeton ne correspondait plus : l'utilisateur doit comprendre pourquoi son action n'a pas
  //   été appliquée, pas juste voir ses données changer sous ses yeux sans explication.
  window.addEventListener('write-token:stale', (e: any) => {
    if (e.detail?.wasWriteAttempt) {
      showNotification('error', 'Les données ont été modifiées entre-temps (ex: une résolution automatique vient de se terminer). Votre action n\'a pas été appliquée — les données à jour ont été rechargées, merci de réessayer.');
    } else {
      showNotification('info', 'Les données ont été mises à jour en arrière-plan (ex: une résolution automatique vient de se terminer) et ont été rechargées.');
    }
    reloadAllData();
  });

  // Écoute des événements de mutation pour rafraîchir les données globales d'App.vue
  window.addEventListener('resource:mutated', (e: any) => {
    const resource = e.detail?.resource_name;
    if (!resource) return;
    // Toute ressource mutée doit voir son cache d'options FK (fkOptionsCache / TanStack Query)
    // invalidé, sans quoi un widget qui édite une ressource "en aparté" (ex: Many2ManyOrderedList
    // en mode association) laisse les autres consommateurs de cette ressource (y compris son propre
    // repli field.options) afficher des données périmées jusqu'au prochain changement de menu actif.
    // Bénéfice supplémentaire (voir architecture.md §15.T) : schools/period_types/periods/groups/
    // class_parts/materials/subjects partagent EXACTEMENT la même clé de cache TanStack Query
    // (['genericList', resourceName], sans segment filtres) que leur ref associée (schoolsList,
    // etc., voir bindGenericListQuery) — invalider ici les rafraîchit donc déjà automatiquement,
    // plus besoin des 7 lignes "if (resource === 'x') loadX()" qui existaient avant (chacune
    // déclenchait un second fetch réseau redondant avec celui-ci).
    invalidateFkCache(resource);
    if (resource === 'system_settings') loadTimeslotConfig();
    if (['teachers', 'classrooms', 'divisions', 'courses', 'groups'].includes(resource)) loadData();
    refreshActiveGenericPanelIfMatches(resource);
  });

  // Retour/avancée navigateur (voir architecture.md, "URLs profondes") : ré-écrire urlPathIds/
  // urlSelectedIds suffit à rejouer la restauration — NotebooksTree (watch sur initialPath) et
  // GenericList (watch sur items + hasAppliedInitialSelection réarmé au changement de title)
  // surveillent déjà ces refs en continu, aucun code de re-déclenchement supplémentaire ici.
  window.addEventListener('popstate', () => {
    urlPathIds.value = parseLocationPath();
    urlSelectedIds.value = parseLocationIds();
    awaitingSelectionRestore = urlSelectedIds.value.length > 0;
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
  border-radius: var(--radius-sm);
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
  border-radius: var(--radius-lg);
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
