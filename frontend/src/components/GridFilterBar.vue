<template>
  <div class="filter-bar glass-morphism">
    <!-- Row 1: Primary Filters (Establishment, Mode, Resource) -->
    <div class="filters-row">
      <!-- 1. Établissement (School Selector) -->
      <div class="filter-item" v-if="!hideSchoolSelector && schools && schools.length > 0">
        <label>Établissement :</label>
        <select 
          :value="schoolId === null ? '' : schoolId" 
          @change="$emit('update:schoolId', ($event.target as HTMLSelectElement).value ? Number(($event.target as HTMLSelectElement).value) : null)" 
          class="select-custom"
        >
          <option value="">Tous</option>
          <option v-for="s in schools" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
      </div>

      <!-- 2. Resource Selectors (for 'timetable' mode or when selectors are not hidden in 'preference' mode) -->
      <template v-if="mode === 'timetable' || (mode === 'preference' && !hideResourceSelectors)">
        <div 
          v-for="rt in resourceTypes" 
          :key="rt.key" 
          class="filter-item resource-multi-select" 
          style="position: relative;"
        >
          <label>{{ rt.label }} :</label>
          <button 
            class="select-custom" 
            style="text-align: left; cursor: pointer; min-width: 140px; display: flex; justify-content: space-between; align-items: center;"
            @click="openDropdown(rt.key, $event)"
          >
            <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding-right: 8px;">
              {{ getSelectionLabel(rt) }}
            </span>
            <span style="font-size: 10px;">&#9660;</span>
          </button>
        </div>

        <!-- Overlay transparent pour fermer au clic exterieur -->
        <div 
          v-if="openDropdownType"
          style="position: fixed; inset: 0; z-index: 998;"
          @click="openDropdownType = null"
        />

        <!-- Dropdown teleporté dans body pour éviter overflow:hidden -->
        <Teleport to="body">
          <div 
            v-if="openDropdownType"
            class="resource-dropdown-panel"
            style="position: fixed; z-index: 999; background: white; border: 1px solid #d1d5db; border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,0.18); max-height: 280px; overflow-y: auto; min-width: 240px;"
            :style="dropdownPos"
            @click.stop
          >
            <div style="padding: 4px 8px; border-bottom: 1px solid #eee; display: flex; gap: 8px;">
              <button class="btn btn-sm" style="flex: 1; padding: 2px; font-size: 11px;" @click="selectAll(openDropdownType)">Tout</button>
              <button class="btn btn-sm" style="flex: 1; padding: 2px; font-size: 11px;" @click="selectNone(openDropdownType)">Rien</button>
            </div>
            <label v-for="r in getActiveList(openDropdownType)" :key="r.id" style="display: flex; align-items: center; gap: 8px; padding: 6px 12px; margin: 0; cursor: pointer; border-bottom: 1px solid #f3f4f6;">
              <input 
                type="checkbox" 
                :value="r.id" 
                :checked="isResourceSelected(openDropdownType, r.id)"
                @change="onResourceCheckboxToggle(openDropdownType, r.id, $event)"
              />
              <span style="flex: 1; font-size: 13px;">{{ r.name || (r.first_name + ' ' + r.last_name) }}</span>
            </label>
            <div v-if="getActiveList(openDropdownType).length === 0" style="padding: 12px; color: #9ca3af; text-align: center; font-size: 13px;">Aucune ressource</div>
          </div>
        </Teleport>
      </template>
      
      <!-- Right auto target toggle -->
      <div class="filter-actions-right" style="margin-left: auto; display: flex; align-items: center; gap: 16px;">
        <div class="filter-item" title="Sélectionne automatiquement les ressources (classe, enseignant, etc.) du cours sur lequel vous cliquez pour filtrer la vue.">
          <label>Ciblage auto :</label>
          <div class="toggle-container" @click="$emit('update:autoTarget', !autoTarget)">
            <span :class="{ 'active': !autoTarget }">Désactivé</span>
            <div class="toggle-switch" :class="{ 'on': autoTarget }"></div>
            <span :class="{ 'active': autoTarget }">Activé</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Row 2: Secondary / Constraints Filters (Alternation & Periods) -->
    <div class="filters-row sub-row">
      <!-- Alternation (Week Type) -->
      <div class="filter-item">
        <label>Semaine :</label>
        <select 
          :value="weekType" 
          @change="$emit('update:weekType', ($event.target as HTMLSelectElement).value)" 
          class="select-custom select-small"
        >
          <option value="W">Toutes</option>
          <option value="A">Semaine A</option>
          <option value="B">Semaine B</option>
        </select>
      </div>

      <!-- Periods -->
      <div class="filter-item periods-group">
        <label>Période :</label>
        <select 
          :value="periodTypeId === null ? '' : periodTypeId" 
          @change="onPeriodTypeSelect" 
          class="select-custom select-small"
        >
          <option value="">Annuelle</option>
          <option v-for="pt in filteredPeriodTypes" :key="pt.id" :value="pt.id">
            {{ pt.label || pt.name }}
          </option>
        </select>

        <!-- Checkboxes for periods belonging to the active type -->
        <div class="periods-checkboxes" v-if="periodTypeId && periodsOfType.length > 0">
          <label v-for="p in periodsOfType" :key="p.id" class="checkbox-wrapper">
            <input 
              type="checkbox" 
              :value="p.id" 
              :checked="periodIds.includes(p.id)"
              @change="onPeriodCheckboxToggle(p.id, $event)"
              class="checkbox-custom"
            />
            <span class="checkbox-text">{{ p.name }}</span>
          </label>
        </div>
      </div>

      <!-- Right actions slot -->
      <div class="filter-actions-right" style="margin-left: auto; display: flex; align-items: center; gap: 16px;">
        <div class="filter-item" v-if="mode === 'timetable'" style="margin-right: 16px;" title="Interrupteur permettant d'alterner entre une vue compacte (où l'on voit les cours composés) et une vue détaillée (où l'on voit le détail des composants pour chaque cours composé).">
          <label>Affichage :</label>
          <div class="toggle-container" @click="$emit('update:isDetailedView', !isDetailedView)">
            <span :class="{ 'active': !isDetailedView }">Compact</span>
            <div class="toggle-switch" :class="{ 'on': isDetailedView }"></div>
            <span :class="{ 'active': isDetailedView }">Détaillé</span>
          </div>
        </div>
        <slot name="actions"></slot>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';

const props = withDefaults(defineProps<{
  mode?: 'timetable' | 'preference';
  schools?: any[];
  teachers?: any[];
  nonTeachingStaffs?: any[];
  divisions?: any[];
  classrooms?: any[];
  periodTypes?: any[];
  periods?: any[];
  
  selectedTeacherIds?: number[];
  selectedNonTeachingStaffIds?: number[];
  selectedDivisionIds?: number[];
  selectedClassroomIds?: number[];
  
  schoolId?: number | null;
  weekType?: 'W' | 'A' | 'B';
  periodTypeId?: number | null;
  periodIds?: number[];
  
  hideResourceSelectors?: boolean;
  hideSchoolSelector?: boolean;
  isDetailedView?: boolean;
  autoTarget?: boolean;
}>(), {
  mode: 'timetable',
  schools: () => [],
  teachers: () => [],
  nonTeachingStaffs: () => [],
  divisions: () => [],
  classrooms: () => [],
  periodTypes: () => [],
  periods: () => [],
  selectedTeacherIds: () => [],
  selectedNonTeachingStaffIds: () => [],
  selectedDivisionIds: () => [],
  selectedClassroomIds: () => [],
  schoolId: null,
  weekType: 'W',
  periodTypeId: null,
  periodIds: () => [],
  hideResourceSelectors: false,
  hideSchoolSelector: false,
  isDetailedView: false,
  autoTarget: false
});

const emit = defineEmits<{
  (e: 'update:selectedTeacherIds', value: number[]): void;
  (e: 'update:selectedNonTeachingStaffIds', value: number[]): void;
  (e: 'update:selectedDivisionIds', value: number[]): void;
  (e: 'update:selectedClassroomIds', value: number[]): void;
  (e: 'update:schoolId', value: number | null): void;
  (e: 'update:weekType', value: 'W' | 'A' | 'B'): void;
  (e: 'update:periodTypeId', value: number | null): void;
  (e: 'update:periodIds', value: number[]): void;
  (e: 'update:isDetailedView', value: boolean): void;
  (e: 'update:autoTarget', value: boolean): void;
}>();

// Filter resources by schoolId if set
const filteredTeachers = computed(() => {
  if (!props.schoolId) return props.teachers;
  return props.teachers.filter(t => t.school_id === props.schoolId);
});

const filteredNonTeachingStaffs = computed(() => {
  if (!props.schoolId) return props.nonTeachingStaffs;
  return props.nonTeachingStaffs.filter(s => s.school_id === props.schoolId).map((s: any) => ({...s, name: s.first_name + ' ' + s.last_name}));
});

const filteredDivisions = computed(() => {
  if (!props.schoolId) return props.divisions;
  return props.divisions.filter(d => d.school_id === props.schoolId);
});

const filteredClassrooms = computed(() => {
  if (!props.schoolId) return props.classrooms;
  return props.classrooms.filter(c => c.school_id === props.schoolId);
});

const resourceTypes = computed(() => [
  { key: 'teacher', label: '👨‍🏫 Ens.', list: filteredTeachers.value, selected: props.selectedTeacherIds },
  { key: 'non_teaching_staff', label: '🧑‍💼 Pers.', list: filteredNonTeachingStaffs.value, selected: props.selectedNonTeachingStaffIds },
  { key: 'division', label: '🎒 Classe', list: filteredDivisions.value, selected: props.selectedDivisionIds },
  { key: 'classroom', label: '🏢 Salle', list: filteredClassrooms.value, selected: props.selectedClassroomIds }
]);

const openDropdownType = ref<string | null>(null);
const dropdownPos = ref<Record<string, string>>({});

function openDropdown(type: string, event: MouseEvent) {
  if (openDropdownType.value === type) {
    openDropdownType.value = null;
    return;
  }
  const btn = (event.currentTarget as HTMLElement);
  const rect = btn.getBoundingClientRect();
  dropdownPos.value = {
    top: (rect.bottom + 4) + 'px',
    left: rect.left + 'px',
    width: Math.max(rect.width, 240) + 'px',
  };
  openDropdownType.value = type;
}

function getActiveList(type: string) {
  const rt = resourceTypes.value.find(rt => rt.key === type);
  return rt ? rt.list : [];
}

function isResourceSelected(type: string, id: number) {
  const rt = resourceTypes.value.find(rt => rt.key === type);
  return rt ? rt.selected.includes(id) : false;
}

function getSelectionLabel(rt: any) {
  if (rt.selected.length === 0) return 'Tous';
  if (rt.selected.length === 1) {
    const item = rt.list.find((r: any) => r.id === rt.selected[0]);
    return item ? (item.name || (item.first_name + ' ' + item.last_name)) : '1 sélectionné';
  }
  return rt.selected.length + ' sélectionnés';
}

function onResourceCheckboxToggle(type: string, id: number, event: Event) {
  const checked = (event.target as HTMLInputElement).checked;
  const rt = resourceTypes.value.find(rt => rt.key === type);
  if (!rt) return;
  
  let newIds = [...rt.selected];
  if (checked) {
    if (!newIds.includes(id)) newIds.push(id);
  } else {
    newIds = newIds.filter(x => x !== id);
  }
  
  emitUpdateForType(type, newIds);
}

function selectAll(type: string) {
  const rt = resourceTypes.value.find(rt => rt.key === type);
  if (!rt) return;
  emitUpdateForType(type, rt.list.map((r: any) => r.id));
}

function selectNone(type: string) {
  emitUpdateForType(type, []);
}

function emitUpdateForType(type: string, ids: number[]) {
  if (type === 'teacher') emit('update:selectedTeacherIds', ids);
  if (type === 'non_teaching_staff') emit('update:selectedNonTeachingStaffIds', ids);
  if (type === 'division') emit('update:selectedDivisionIds', ids);
  if (type === 'classroom') emit('update:selectedClassroomIds', ids);
}

// Period types selection logic
const filteredPeriodTypes = computed(() => {
  let relevantPeriods = props.periods;
  if (props.schoolId) {
    relevantPeriods = relevantPeriods.filter(p => p.school_id === props.schoolId);
  }
  const activePtIds = Array.from(new Set(relevantPeriods.map(p => p.period_type_id)));
  return props.periodTypes.filter(pt => activePtIds.includes(pt.id));
});

const periodsOfType = computed(() => {
  if (!props.periodTypeId) return [];
  let relevantPeriods = props.periods;
  if (props.schoolId) {
    relevantPeriods = relevantPeriods.filter(p => p.school_id === props.schoolId);
  }
  return relevantPeriods.filter(p => p.period_type_id === props.periodTypeId);
});

function onPeriodTypeSelect(event: Event) {
  const val = (event.target as HTMLSelectElement).value;
  const pTypeId = val ? Number(val) : null;
  emit('update:periodTypeId', pTypeId);
  
  if (pTypeId) {
    // Select all periods of this type by default
    const associatedPeriods = props.periods.filter(p => p.period_type_id === pTypeId);
    emit('update:periodIds', associatedPeriods.map(p => p.id));
  } else {
    emit('update:periodIds', []);
  }
}

function onPeriodCheckboxToggle(pId: number, event: Event) {
  const isChecked = (event.target as HTMLInputElement).checked;
  let newIds = [...props.periodIds];
  
  if (isChecked) {
    if (!newIds.includes(pId)) {
      newIds.push(pId);
    }
  } else {
    // Constraint: must keep at least one checked period
    if (newIds.length > 1) {
      newIds = newIds.filter(id => id !== pId);
    } else {
      // Force keep the checkbox checked in DOM by toggling checked state back
      (event.target as HTMLInputElement).checked = true;
    }
  }
  emit('update:periodIds', newIds);
}
</script>

<style scoped>
.filter-bar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px 16px;
  background-color: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.filters-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 20px;
}

.sub-row {
  border-top: 1px solid var(--border-color);
  padding-top: 12px;
}

.filter-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-item > label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.periods-group {
  flex-grow: 1;
}

.periods-checkboxes {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-left: 12px;
  padding-left: 12px;
  border-left: 1px solid var(--border-color);
}

.checkbox-wrapper {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary);
}

.checkbox-custom {
  cursor: pointer;
  accent-color: var(--accent-primary);
}

.checkbox-text {
  user-select: none;
}

/* Toggle Switch Styles */
.toggle-container {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(255, 255, 255, 0.4);
  padding: 4px 8px;
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.5);
  cursor: pointer;
  user-select: none;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
}

.toggle-container span {
  transition: color 0.3s;
}

.toggle-container span.active {
  color: var(--accent-primary);
}

.toggle-switch {
  width: 32px;
  height: 18px;
  background: rgba(0, 0, 0, 0.15);
  border-radius: 10px;
  position: relative;
  transition: background 0.3s;
}

.toggle-switch::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 14px;
  height: 14px;
  background: white;
  border-radius: 50%;
  transition: transform 0.3s cubic-bezier(0.4, 0.0, 0.2, 1);
  box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}

.toggle-switch.on {
  background: var(--accent-primary);
}

.toggle-switch.on::after {
  transform: translateX(14px);
}
</style>
