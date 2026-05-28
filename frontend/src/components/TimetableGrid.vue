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
      @cell-dragover="onDragOver"
      @cell-dragleave="onDragLeave"
      @cell-drop="onDrop"
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
          @selectCourse="(id, ev) => $emit('selectCourse', id, ev)"
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
          :backgroundColor="course.color || '#cbd5e1'"
          :height="getCourseHeight(course)"
          :teachersText="(course.teacher_ids ? course.teacher_ids.map(id => getTeacherName(id)).join(', ') : '')"
          :divisionsText="(course.division_ids ? course.division_ids.map(id => getDivisionName(id)).join(', ') : '')"
          :classroomsText="(course.classroom_ids ? course.classroom_ids.map(id => getClassroomName(id)).join(', ') : '')"
          @dragstart="onDragStart"
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
            {{ isLoadingHeatmap ? 'Évaluation de la Heatmap...' : 'Calcul de l\'emploi du temps optimal...' }}
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
  (e: 'move', courseId: number, timeslotId: number): void;
  (e: 'unassign', courseId: number): void;
  (e: 'togglePin', courseId: number): void;
  (e: 'selectCourse', courseId: number, event: MouseEvent): void;
  (e: 'update:selectedTeacherIds', value: number[]): void;
  (e: 'update:selectedNonTeachingStaffIds', value: number[]): void;
  (e: 'update:selectedDivisionIds', value: number[]): void;
  (e: 'update:selectedClassroomIds', value: number[]): void;
  (e: 'update:weekType', value: 'W' | 'A' | 'B'): void;
  (e: 'reset'): void;
  (e: 'solve'): void;
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

const activeResources = computed(() => {
  if (props.layoutMode !== 'resource_columns' && props.layoutMode !== 'resource_grids') return [];
  
  const res: { type: string, id: number, name: string }[] = [];
  props.selectedTeacherIds.forEach(id => {
    const t = props.teachers.find(x => x.id === id);
    if (t) res.push({ type: 'teacher', id, name: t.name || 'Prof' });
  });
  props.selectedDivisionIds.forEach(id => {
    const d = props.divisions.find(x => x.id === id);
    if (d) res.push({ type: 'division', id, name: d.name || 'Classe' });
  });
  props.selectedClassroomIds.forEach(id => {
    const c = props.classrooms?.find(x => x.id === id);
    if (c) res.push({ type: 'classroom', id, name: c.name || 'Salle' });
  });
  props.selectedNonTeachingStaffIds.forEach(id => {
    const s = props.nonTeachingStaffs?.find(x => x.id === id);
    if (s) res.push({ type: 'non_teaching_staff', id, name: (s.first_name + ' ' + s.last_name).trim() || 'Personnel' });
  });
  return res;
});

function getCourseHeight(course: Course) {
  const duration = course.duration_minutes || 30;
  const span = duration / currentStandardDuration.value;
  return `calc(${span} * 100% - 8px + ${span - 1}px)`;
}
const activeDragCells = ref<Record<string, boolean>>({});

const heatmapData = ref<Record<string, any>>({});
const isLoadingHeatmap = ref<boolean>(false);

import { watch } from 'vue';

// Watcher pour le heatmap
watch(() => [props.placementAssistantActive, props.selectedCourseIds], async ([isActive, courseIds]) => {
  if (isActive && courseIds && (courseIds as number[]).length === 1) {
    const courseId = (courseIds as number[])[0];
    isLoadingHeatmap.value = true;
    try {
      const response = await fetch(`/api/timetable/courses/${courseId}/heatmap`);
      if (response.ok) {
        const data = await response.json();
        const mappedData: Record<string, any> = {};
        for (const [tsIdStr, scoreInfo] of Object.entries(data)) {
          const tsId = parseInt(tsIdStr);
          const ts = props.timeslots.find(t => t.id === tsId);
          if (ts) {
            mappedData[getCellKey(ts.day_of_week, ts.hour)] = scoreInfo;
          }
        }
        heatmapData.value = mappedData;
      }
    } catch (e) {
      console.error("Erreur Heatmap", e);
    } finally {
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
    const isClassroomMatch = props.selectedClassroomIds.length > 0 && course.classroom_ids && course.classroom_ids.some(id => props.selectedClassroomIds.includes(id));
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
      if (!coursesByDay.has(ts.day_of_week)) coursesByDay.set(ts.day_of_week, []);
      coursesByDay.get(ts.day_of_week)!.push({
        course: c,
        start: ts.hour,
        end: ts.hour + (c.duration_minutes || 0) / 60
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
        if (res.type === 'classroom') return c.classroom_ids && c.classroom_ids.includes(res.id);
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
    if (resource.type === 'classroom') result = result.filter(c => c.classroom_ids && c.classroom_ids.includes(resource.id));
    if (resource.type === 'non_teaching_staff') result = result.filter(c => c.non_teaching_staff_ids && c.non_teaching_staff_ids.includes(resource.id));
  }
  
  return result;
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

// Les couleurs des cours proviennent maintenant directement de la base de données (champ subject.color)
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
