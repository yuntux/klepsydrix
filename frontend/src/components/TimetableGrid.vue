<template>
  <div class="timetable-grid-wrapper" style="height: 100%; display: flex; flex-direction: column;">
    <GridContainer
      preferenceMode="readonly"
      :timeslots="timeslots"
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
      :selectedTeacherIds="selectedTeacherIds"
      @update:selectedTeacherIds="$emit('update:selectedTeacherIds', $event)"
      :selectedNonTeachingStaffIds="selectedNonTeachingStaffIds"
      @update:selectedNonTeachingStaffIds="$emit('update:selectedNonTeachingStaffIds', $event)"
      :selectedDivisionIds="selectedDivisionIds"
      @update:selectedDivisionIds="$emit('update:selectedDivisionIds', $event)"
      :selectedClassroomIds="selectedClassroomIds"
      @update:selectedClassroomIds="$emit('update:selectedClassroomIds', $event)"
      :weekType="weekType"
      @update:weekType="$emit('update:weekType', $event)"
      :autoTarget="autoTarget"
      @update:autoTarget="$emit('update:autoTarget', $event)"
      :layoutMode="layoutMode"
      @update:layoutMode="$emit('update:layoutMode', $event)"
      :placementAssistantActive="placementAssistantActive"
      @update:placementAssistantActive="$emit('update:placementAssistantActive', $event)"
      :hideResourceSelectors="false"
      :hideSchoolSelector="false"
      v-model:isDetailedView="isDetailedView"
      :activeResources="activeResources"
      :dragOverCells="activeDragCells"
      :draggedCourseWeekType="draggedCourseWeekType"
      @cell-dragover="onDragOver"
      @cell-dragleave="onDragLeave"
      @cell-drop="onDrop"
    >
      <template #actions>
        <div class="controls-group" style="display: flex; gap: 12px; align-items: center;">
          <div class="score-pill" :class="{ 'score-perfect': scoreData && scoreData.hard_score === 0 && scoreData.soft_score === 0, 'score-warning': scoreData && (scoreData.hard_score < 0 || scoreData.soft_score < 0) }" :title="scoreData ? scoreData.summary : 'En attente...'">
            Score: {{ scoreData ? scoreData.hard_score : '?' }}H / {{ scoreData ? scoreData.soft_score : '?' }}S
          </div>

          <BaseButton variant="secondary" @click="$emit('reset')" :disabled="loading">
            Réinitialiser
          </BaseButton>
          
          <template v-if="!loading">
            <BaseButton variant="primary" @click="$emit('course-placement')">
              <template #icon>
                <svg xmlns="http://www.w3.org/2000/svg" class="icon-btn" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </template>
              Placement automatique
            </BaseButton>

            <BaseButton variant="secondary" @click="$emit('classroom-assignment')">
              <template #icon>
                <svg xmlns="http://www.w3.org/2000/svg" class="icon-btn" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2M5 21H3m16 0h-5m-4 0H5m4 0v-6a2 2 0 012-2v0a2 2 0 012 2v6m-6 0h6" />
                </svg>
              </template>
              Attribuer les salles
            </BaseButton>
          </template>

          <BaseButton v-else variant="danger" @click="$emit('stop-solve')">
            <template #icon>
              <svg xmlns="http://www.w3.org/2000/svg" class="icon-btn" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 10h6v4H9z" />
              </svg>
            </template>
            Arrêter
          </BaseButton>
        </div>
      </template>
      
      <template #sidebar>
        <Sidebar
          :courses="courses"
          :teachers="teachers"
          :divisions="divisions"
          :classrooms="classrooms"
          :subjects="subjects"
          :selectedCourseIds="selectedCourseIds"
          :currentStandardDuration="currentStandardDuration"
          @selectCourse="(id, ev) => $emit('selectCourse', id, ev)"
          @dragstart="onDragStart"
          @dragend="onDragEnd"
        />
      </template>

      <!-- Slot de contenu (Foreground) -->
      <template #cell-content="{ day, time, resource }">
        <CourseCard
          v-for="course in getCoursesAt(day, time, resource)"
          :key="course.id"
          :course="course"
          :isPlaced="true"
          :overlapIndex="getOverlapInfo(course.id).index"
          :overlapCount="getOverlapInfo(course.id).count"
          :isSelected="(selectedCourseIds || []).includes(course.id)"
          :subjects="subjects"
          :height="getCourseHeight(course)"
          :teachersText="(course.teacher_ids ? course.teacher_ids.map(id => getTeacherName(id)).join(', ') : '')"
          :divisionsText="(course.division_ids ? course.division_ids.map(id => getDivisionName(id)).join(', ') : '')"
          :classroomsText="(dataStore.courseClassroomIdsMap[course.id] || []).map(id => getClassroomName(id)).join(', ')"
          @dragstart="onDragStart"
          @dragend="onDragEnd"
          @click="(id, ev) => $emit('selectCourse', id, ev)"
          @togglePin="$emit('togglePin', $event)"
          @unassign="$emit('unassign', $event)"
        />
      </template>

      <!-- Overlay de chargement -->
      <template #overlay>
        <div class="loader-overlay" v-if="loading || isLoadingHeatmap">
          <div class="spinner"></div>
          <div style="color: #black; font-weight: 500; font-size: 16px;">
            {{ isLoadingHeatmap
              ? 'Évaluation de la Heatmap...'
              : (solverIsQueued ? 'En file d\'attente...' : solverStatusLabel) }}
          </div>
          <div v-if="!isLoadingHeatmap && !solverIsQueued && solverPipelineTotalSteps > 1" class="solver-pipeline-step">
            Étape {{ solverPipelineStep }} sur {{ solverPipelineTotalSteps }}
          </div>
          <!-- Progression best-effort (voir solver.py) : le score dur/doux le plus récent connu
               peut manquer par intermittence (limitation du paquet timefold bêta), le temps
               écoulé/limite reste lui toujours fiable. Tant que la résolution est seulement en
               file d'attente (voir solver.py::SolverState, "Concurrence des résolutions"), ni le
               score ni le temps écoulé n'ont de sens (la résolution n'a pas encore démarré) —
               seule la position dans la file est affichée. -->
          <div v-if="!isLoadingHeatmap" class="solver-progress-info">
            <span v-if="solverIsQueued">
              Position {{ solverQueuePosition }} sur {{ solverQueueLength }}
            </span>
            <template v-else>
              <span v-if="solverProgress">Score : {{ solverProgress.hard_score }}H / {{ solverProgress.soft_score }}S</span>
              <span v-if="solverElapsedSeconds != null">
                Temps écoulé : {{ Math.round(solverElapsedSeconds) }}s{{ solverTimeLimitSeconds ? ` / ${solverTimeLimitSeconds}s max` : '' }}
              </span>
            </template>
            <BaseButton variant="danger" size="sm" @click="$emit('stop-solve')">
              Arrêter le calcul
            </BaseButton>
          </div>
        </div>
      </template>

      <!-- Slot de fond (Background) -->
      <template #cell-background="{ day, time }">
        <div v-if="heatmapData[getCellKey(day, time)]" 
             class="heatmap-overlay" 
             :style="getHeatmapStyle(heatmapData[getCellKey(day, time)])"
             :title="getHeatmapTooltip(heatmapData[getCellKey(day, time)])">
        </div>
      </template>
    </GridContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { Course, Timeslot, Teacher, NonTeachingStaff, Division, Classroom } from '../types';
import BaseGrid from './BaseGrid.vue';
import BaseTooltip from './BaseTooltip.vue';
import BaseButton from './BaseButton.vue';
import GridContainer from './GridContainer.vue';
import Sidebar from './Sidebar.vue';
import CourseCard from './CourseCard.vue';
import { useTimeslotGrid, getTimeslotHour } from '../composables/useTimeslotGrid';
import { apiFetch } from '../services/api';

const props = defineProps<{
  courses: Course[];
  timeslots: Timeslot[];
  teachers: Teacher[];
  nonTeachingStaffs: NonTeachingStaff[];
  divisions: Division[];
  classrooms: Classroom[];
  subjects?: any[];
  selectedTeacherIds: number[];
  selectedNonTeachingStaffIds: number[];
  selectedDivisionIds: number[];
  selectedClassroomIds: number[];
  weekType?: 'W' | 'A' | 'B';
  loading: boolean;
  selectedCourseIds?: number[];
  schools?: any[];
  schoolId?: number | null;
  scoreData?: any;
  solverProgress?: { hard_score: number; soft_score: number } | null;
  solverElapsedSeconds?: number | null;
  solverTimeLimitSeconds?: number | null;
  solverIsQueued?: boolean;
  solverQueuePosition?: number | null;
  solverQueueLength?: number;
  solverKind?: string | null;
  solverPipelineStep?: number;
  solverPipelineTotalSteps?: number;
  periodTypes?: any[];
  periods?: any[];
  periodTypeId?: number | null;
  periodIds?: number[];
  isDetailedView?: boolean;
  autoTarget?: boolean;
  layoutMode?: string;
  placementAssistantActive?: boolean;
}>();

const isDetailedView = ref(false);

const emit = defineEmits<{
  (e: 'move', courseId: number, timeslotId: number, weekType?: 'A' | 'B'): void;
  (e: 'unassign', courseId: number): void;
  (e: 'togglePin', courseId: number): void;
  (e: 'selectCourse', courseId: number, event: MouseEvent): void;
  (e: 'update:selectedTeacherIds', value: number[]): void;
  (e: 'update:selectedNonTeachingStaffIds', value: number[]): void;
  (e: 'update:selectedDivisionIds', value: number[]): void;
  (e: 'update:selectedClassroomIds', value: number[]): void;
  (e: 'update:weekType', value: 'W' | 'A' | 'B'): void;
  (e: 'reset'): void;
  (e: 'course-placement'): void;
  (e: 'classroom-assignment'): void;
  (e: 'stop-solve'): void;
  (e: 'update:periodTypeId', value: number | null): void;
  (e: 'update:periodIds', value: number[]): void;
  (e: 'update:schoolId', value: number | null): void;
  (e: 'update:isDetailedView', value: boolean): void;
  (e: 'update:autoTarget', value: boolean): void;
  (e: 'update:layoutMode', value: string): void;
  (e: 'update:placementAssistantActive', value: boolean): void;
}>();

const { currentStandardDuration, getCellKey } = useTimeslotGrid();

// Libellé de l'overlay de chargement, selon le type de résolution en cours (voir plan salles §4,
// SolverState.kind côté backend) — null/undefined (legacy /solve, ou pas encore reçu un premier
// /status) retombe sur le libellé générique historique.
const SOLVER_KIND_LABELS: Record<string, string> = {
  COURSE_PLACEMENT: 'Placement automatique en cours...',
  CLASSROOM_ASSIGNMENT: 'Attribution des salles en cours...',
  OPTIMIZE_COURSE_PLACEMENT: 'Optimisation — placement des cours...',
  OPTIMIZE_CLASSROOM_ASSIGNMENT: 'Optimisation — attribution des salles...',
};
const solverStatusLabel = computed(() => {
  return (props.solverKind && SOLVER_KIND_LABELS[props.solverKind]) || 'Calcul de l\'emploi du temps optimal...';
});
const solverPipelineStep = computed(() => props.solverPipelineStep || 1);
const solverPipelineTotalSteps = computed(() => props.solverPipelineTotalSteps || 1);

const activeResources = computed(() => {
  if (props.layoutMode !== 'resource_columns' && props.layoutMode !== 'resource_grids') return [];
  
  const res: { type: string, id: number, display_name: string }[] = [];
  props.selectedTeacherIds.forEach(id => {
    res.push({ type: 'teacher', id, display_name: _getTeacherName(props.teachers, id) });
  });
  props.selectedDivisionIds.forEach(id => {
    res.push({ type: 'division', id, display_name: _getDivisionName(props.divisions, id) });
  });
  props.selectedClassroomIds.forEach(id => {
    res.push({ type: 'classroom', id, display_name: _getClassroomName(props.classrooms, id) });
  });
  props.selectedNonTeachingStaffIds.forEach(id => {
    res.push({ type: 'non_teaching_staff', id, display_name: _getNonTeachingStaffName(props.nonTeachingStaffs, id) });
  });
  return res;
});

function getCourseHeight(course: Course) {
  const duration = course.duration_minutes || 30;
  const span = duration / currentStandardDuration.value;
  return `calc(${span} * 100% - 8px + ${span - 1}px)`;
}
const activeDragCells = ref<Record<string, boolean>>({});

// Cours en cours de glisser-déposer (défini au dragstart, effacé au dragend) — sa semaine pilote
// le split de colonnes A/B de BaseGrid.vue (voir attribution_week_type_auto.md, Phase B), sa
// durée pilote l'étendue de l'ombre portée (voir onDragOver/onDragLeave ci-dessous). Ne peut pas
// être lu depuis dataTransfer pendant le survol (dragover) pour des raisons de sécurité
// navigateur (getData n'est disponible qu'au drop) — d'où cet état local dédié.
const draggedCourse = ref<Course | null>(null);
const draggedCourseWeekType = computed(() => draggedCourse.value?.week_type || null);

const heatmapData = ref<Record<string, any>>({});
const isLoadingHeatmap = ref<boolean>(false);
// Depuis la mise en cache du SolverFactory (voir backend/experimental_java_heatmap/README.md
// § 5.1), la Heatmap répond typiquement en 100-500ms — trop court pour afficher un sablier sans
// qu'il ne "clignote" (apparaît et disparaît quasi instantanément, plus perturbant qu'utile).
// On ne montre donc le spinner que si la requête dépasse ce délai ; en dessous, la mise à jour
// de la grille paraît instantanée. Pattern standard (GitHub, Gmail...) pour ce cas précis.
const HEATMAP_SPINNER_DELAY_MS = 300;
let heatmapSpinnerTimer: ReturnType<typeof setTimeout> | null = null;

import { watch } from 'vue';
import { useDataStore } from '../stores/data';
const dataStore = useDataStore();
// Watcher pour le heatmap
watch(() => [props.placementAssistantActive, props.selectedCourseIds], async ([isActive, courseIds]) => {
  if (heatmapSpinnerTimer) {
    clearTimeout(heatmapSpinnerTimer);
    heatmapSpinnerTimer = null;
  }
  if (isActive && courseIds && (courseIds as number[]).length === 1) {
    const courseId = (courseIds as number[])[0];
    heatmapSpinnerTimer = setTimeout(() => {
      isLoadingHeatmap.value = true;
    }, HEATMAP_SPINNER_DELAY_MS);
    try {
      const response = await apiFetch(`/api/timetable/courses/${courseId}/heatmap`);
      if (response.ok) {
        const data = await response.json();
        const mappedData: Record<string, any> = {};
        for (const [tsIdStr, scoreInfo] of Object.entries(data)) {
          const tsId = parseInt(tsIdStr);
          const ts = dataStore.timeslotMap[tsId];
          if (ts) {
            mappedData[getCellKey(ts.day_of_week, getTimeslotHour(ts))] = scoreInfo;
          }
        }
        heatmapData.value = mappedData;
      }
    } catch (e) {
      console.error("Erreur Heatmap", e);
    } finally {
      if (heatmapSpinnerTimer) {
        clearTimeout(heatmapSpinnerTimer);
        heatmapSpinnerTimer = null;
      }
      isLoadingHeatmap.value = false;
    }
  } else {
    heatmapData.value = {};
  }
}, { deep: true });

function getHeatmapStyle(scoreInfo: any) {
  if (scoreInfo.hard < 0) {
    return { backgroundColor: 'rgba(239, 68, 68, 0.15)' }; // Red
  } else if (scoreInfo.soft < 0) {
    return { backgroundColor: 'rgba(245, 158, 11, 0.15)' }; // Orange
  } else {
    return { backgroundColor: 'rgba(16, 185, 129, 0.15)' }; // Green
  }
}

function getHeatmapTooltip(scoreInfo: any) {
  let tooltip = `Score: Hard ${scoreInfo.hard}, Soft ${scoreInfo.soft}\n`;
  if (scoreInfo.reasons && scoreInfo.reasons.length > 0) {
    tooltip += "Explications :\n";
    scoreInfo.reasons.forEach((r: any) => {
      tooltip += `- ${r.name} (H: ${r.impact_hard}, S: ${r.impact_soft})\n`;
    });
  } else {
    tooltip += "Aucune contrainte déclenchée.";
  }
  return tooltip;
}

// Cases occupées par le cours glissé s'il était déposé en partant de (day, hour) — de son début
// à sa fin, pas seulement le créneau survolé — pour que l'ombre portée prévisualise fidèlement
// tout l'emplacement final, pas juste son point de départ.
function occupiedCellSuffixes(day: number, hour: number, weekHalf?: 'A' | 'B'): string[] {
  const stepHours = currentStandardDuration.value / 60;
  const duration = draggedCourse.value?.duration_minutes || currentStandardDuration.value;
  const steps = Math.max(1, Math.round(duration / currentStandardDuration.value));
  const suffix = weekHalf ? `-${weekHalf}` : '';
  const keys: string[] = [];
  for (let i = 0; i < steps; i++) {
    keys.push(getCellKey(day, hour + i * stepHours) + suffix);
  }
  return keys;
}

function onDragOver(day: number, hour: number, event: DragEvent, weekHalf?: 'A' | 'B') {
  occupiedCellSuffixes(day, hour, weekHalf).forEach(key => { activeDragCells.value[key] = true; });
}

function onDragLeave(day: number, hour: number, event: DragEvent, weekHalf?: 'A' | 'B') {
  occupiedCellSuffixes(day, hour, weekHalf).forEach(key => { activeDragCells.value[key] = false; });
}

function getTimeslot(day: number, hour: number): Timeslot | undefined {
  return dataStore.getTimeslot(day, hour);
}

const parentIdsSet = computed(() => {
  return new Set(props.courses.map(c => c.parent_id).filter(id => id != null));
});

const displayedCourses = computed(() => {
  const selectedWeek = props.weekType || 'W';
  return props.courses.filter(course => {
    if (!course.timeslot_id) return false;

    // Filtre de granularité
    if (isDetailedView.value) {
      if (parentIdsSet.value.has(course.id)) return false; // detailed: exclut les parents
    } else {
      if (course.parent_id !== null) return false; // compact: exclut les enfants
    }

    // Filtre par semaine
    if (selectedWeek !== 'W') {
      const courseWeek = course.week_type || 'W';
      if (courseWeek !== 'W' && courseWeek !== selectedWeek) return false;
    }

    const noSelection = props.selectedTeacherIds.length === 0 && props.selectedDivisionIds.length === 0 && props.selectedClassroomIds.length === 0 && props.selectedNonTeachingStaffIds.length === 0;

    const isTeacherMatch = props.selectedTeacherIds.length > 0 && course.teacher_ids && course.teacher_ids.some(id => props.selectedTeacherIds.includes(id));
    const isDivisionMatch = props.selectedDivisionIds.length > 0 && course.division_ids && course.division_ids.some(id => props.selectedDivisionIds.includes(id));
    const courseClassroomIds = dataStore.courseClassroomIdsMap[course.id] || [];
    const isClassroomMatch = props.selectedClassroomIds.length > 0 && courseClassroomIds.some(id => props.selectedClassroomIds.includes(id));
    const isNonTeachingMatch = props.selectedNonTeachingStaffIds.length > 0 && course.non_teaching_staff_ids && course.non_teaching_staff_ids.some(id => props.selectedNonTeachingStaffIds.includes(id));

    return noSelection || isTeacherMatch || isDivisionMatch || isClassroomMatch || isNonTeachingMatch;
  });
});

const timeslotMap = computed(() => {
  const map = new Map<number, Timeslot>();
  props.timeslots.forEach(ts => map.set(ts.id, ts));
  return map;
});

const overlapInfoMap = computed(() => {
  const info = new Map<string, { index: number, count: number }>();
  
  const computeClusterInfo = (coursesSubset: any[], prefixKey: string) => {
    const coursesByDay = new Map<number, any[]>();
    coursesSubset.forEach(c => {
      const ts = timeslotMap.value.get(c.timeslot_id!);
      if (!ts) return;
      const start = getTimeslotHour(ts);
      if (!coursesByDay.has(ts.day_of_week)) coursesByDay.set(ts.day_of_week, []);
      coursesByDay.get(ts.day_of_week)!.push({
        course: c,
        start,
        end: start + (c.duration_minutes || 0) / 60
      });
    });

    for (const dayCourses of coursesByDay.values()) {
      dayCourses.sort((a, b) => a.start - b.start || b.end - a.end);
      let currentCluster: any[] = [];
      let clusterEnd = 0;
      
      const processCluster = (cluster: any[]) => {
        if (cluster.length === 0) return;
        const columns: any[][] = [];
        for (const item of cluster) {
          let placed = false;
          for (let i = 0; i < columns.length; i++) {
            const col = columns[i];
            const lastItemInCol = col[col.length - 1];
            if (lastItemInCol.end <= item.start + 0.001) {
              col.push(item);
              placed = true;
              break;
            }
          }
          if (!placed) columns.push([item]);
        }
        const count = columns.length;
        for (let i = 0; i < columns.length; i++) {
          for (const item of columns[i]) {
            info.set(`${prefixKey}_${item.course.id}`, { index: i, count: count });
          }
        }
      };
      
      for (const item of dayCourses) {
        if (currentCluster.length === 0) {
          currentCluster.push(item);
          clusterEnd = item.end;
        } else {
          if (item.start < clusterEnd - 0.001) {
            currentCluster.push(item);
            clusterEnd = Math.max(clusterEnd, item.end);
          } else {
            processCluster(currentCluster);
            currentCluster = [item];
            clusterEnd = item.end;
          }
        }
      }
      processCluster(currentCluster);
    }
  };

  if (props.layoutMode === 'merged' || activeResources.value.length === 0) {
    computeClusterInfo(displayedCourses.value, 'merged');
  } else {
    // Mode dégroupé (ressource_grids ou ressource_columns) : on calcule les chevauchements colonne par colonne
    for (const res of activeResources.value) {
      const subset = displayedCourses.value.filter(c => {
        if (res.type === 'teacher') return c.teacher_ids && c.teacher_ids.includes(res.id);
        if (res.type === 'division') return c.division_ids && c.division_ids.includes(res.id);
        if (res.type === 'classroom') return (dataStore.courseClassroomIdsMap[c.id] || []).includes(res.id);
        if (res.type === 'non_teaching_staff') return c.non_teaching_staff_ids && c.non_teaching_staff_ids.includes(res.id);
        return false;
      });
      computeClusterInfo(subset, `${res.type}_${res.id}`);
    }
  }
  
  return info;
});

function getOverlapInfo(courseId: number, resource?: { type: string, id: number }) {
  const prefix = (props.layoutMode === 'merged' || !resource) ? 'merged' : `${resource.type}_${resource.id}`;
  return overlapInfoMap.value.get(`${prefix}_${courseId}`) || { index: 0, count: 1 };
}

function getCoursesAt(day: number, hour: number, resource?: { type: string, id: number }): Course[] {
  const ts = getTimeslot(day, hour);
  if (!ts) return [];
  
  let result = displayedCourses.value.filter(c => c.timeslot_id === ts.id);
  
  if (resource) {
    if (resource.type === 'teacher') result = result.filter(c => c.teacher_ids && c.teacher_ids.includes(resource.id));
    if (resource.type === 'division') result = result.filter(c => c.division_ids && c.division_ids.includes(resource.id));
    if (resource.type === 'classroom') result = result.filter(c => (dataStore.courseClassroomIdsMap[c.id] || []).includes(resource.id));
    if (resource.type === 'non_teaching_staff') result = result.filter(c => c.non_teaching_staff_ids && c.non_teaching_staff_ids.includes(resource.id));
  }
  
  return result;
}

import { getTeacherName as _getTeacherName, getDivisionName as _getDivisionName, getClassroomName as _getClassroomName, getNonTeachingStaffName as _getNonTeachingStaffName, onCourseDragStart } from '../utils/resourceFormatters';

function getTeacherName(id: number) {
  return _getTeacherName(props.teachers, id);
}

function getDivisionName(id: number) {
  return _getDivisionName(props.divisions, id);
}

function getClassroomName(id: number | null) {
  return _getClassroomName(props.classrooms, id);
}

function onDragStart(event: DragEvent, courseId: number) {
  onCourseDragStart(event, courseId);
  draggedCourse.value = props.courses.find(c => c.id === courseId) || null;
}

function onDragEnd() {
  draggedCourse.value = null;
  // Filet de sécurité : drop() ne déclenche jamais dragleave sur sa propre cible (l'un ou
  // l'autre se produit, jamais les deux — voir la spec HTML5 Drag and Drop), donc la case sur
  // laquelle le cours atterrit restait grisée indéfiniment sans ce nettoyage global. dragend se
  // déclenche systématiquement en tout dernier, quelle que soit l'issue du glisser (drop réussi,
  // annulé, relâché hors zone valide) — un seul point de nettoyage suffit, pas besoin de traquer
  // précisément quelles cases éteindre au cas par cas.
  activeDragCells.value = {};
}

function onDrop(day: number, hour: number, event: DragEvent, weekHalf?: 'A' | 'B') {
  // Nettoyage synchrone ICI plutôt que de compter uniquement sur onDragEnd (dragend) : déplacer
  // un cours déjà placé fait changer sa cellule de rendu (retiré de l'ancienne case, ajouté à la
  // nouvelle — des blocs v-for différents, pas un simple réordonnancement), donc le nœud DOM
  // source peut être détruit par la réactivité Vue avant que le navigateur n'ait dispatché
  // dragend dessus — auquel cas dragend ne se déclenche jamais et le nettoyage n'arrivait pas.
  // onDragEnd reste nécessaire pour le cas d'un glisser annulé (aucun drop, Échap, hors zone).
  activeDragCells.value = {};

  const ts = getTimeslot(day, hour);
  if (!ts) return;

  const courseIdStr = event.dataTransfer?.getData('text/plain');
  if (!courseIdStr) return;

  const courseId = Number(courseIdStr);

  // weekHalf n'est fourni que si le cours glissé n'est pas W (zones de dépose scindées, voir
  // BaseGrid.vue) — un cours W n'envoie jamais de week_type, il garde sa valeur (voir aussi la
  // garde backend Course.update() qui refuse toute bascule W->A/B "lors du placement").
  emit('move', courseId, ts.id, weekHalf);
}

// Les couleurs des cours proviennent maintenant directement de la base de données (champ subject.color)
</script>

<style scoped>
.solver-progress-info .btn {
  margin-top: 8px;
}
.solver-pipeline-step {
  font-size: 13px;
  color: var(--text-muted);
  font-weight: 500;
}
.unassign-btn {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 2px;
  border-radius: var(--radius-md);
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
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
  opacity: 0.6;
}
.pin-btn:hover, .pin-btn.is-pinned {
  color: var(--accent-warning, var(--accent-warning));
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
  border-left: 3px solid var(--accent-warning, var(--accent-warning)) !important;
}

.heatmap-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: auto;
  z-index: 1;
  transition: background-color 0.2s ease;
}
</style>
