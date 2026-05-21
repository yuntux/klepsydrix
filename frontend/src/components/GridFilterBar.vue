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

      <!-- 2. Mode and Resource Selectors (for 'timetable' mode or when selectors are not hidden in 'preference' mode) -->
      <template v-if="mode === 'timetable'">
        <div class="filter-item">
          <label>Mode de vue :</label>
          <select 
            :value="viewMode" 
            @change="$emit('update:viewMode', ($event.target as HTMLSelectElement).value)" 
            class="select-custom"
          >
            <option value="division">Par Classe (Division)</option>
            <option value="teacher">Par Enseignant</option>
            <option value="non_teaching_staff">Par Personnel Non Enseignant</option>
            <option value="classroom">Par Salle</option>
          </select>
        </div>

      </template>

      <template v-if="mode === 'timetable' || (mode === 'preference' && !hideResourceSelectors)">
        <div class="filter-item" v-if="mode === 'preference'">
          <label>Type de Ressource :</label>
          <select 
            :value="viewMode" 
            @change="$emit('update:viewMode', ($event.target as HTMLSelectElement).value)" 
            class="select-custom"
          >
            <option value="Teacher">👨‍🏫 Enseignant</option>
            <option value="NonTeachingStaff">🧑‍💼 Personnel Non Enseignant</option>
            <option value="Classroom">🏢 Salle</option>
            <option value="Division">🎒 Classe (Division)</option>
          </select>
        </div>

        <div class="filter-item resource-multi-select" style="position: relative;">
          <label v-if="mode === 'timetable'">
            <span v-if="viewMode?.toLowerCase() === 'division'">Classe :</span>
            <span v-else-if="viewMode?.toLowerCase() === 'teacher'">Enseignant :</span>
            <span v-else-if="viewMode?.toLowerCase() === 'non_teaching_staff'">Personnel :</span>
            <span v-else-if="viewMode?.toLowerCase() === 'classroom'">Salle :</span>
          </label>
          <label v-else>Ressources :</label>
          
          <button 
            class="select-custom" 
            style="text-align: left; background-color: #fff; cursor: pointer; min-width: 200px; display: flex; justify-content: space-between; align-items: center;"
            @click="openDropdown($event)"
          >
            <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding-right: 8px;">
              {{ selectedIds.length === 0 ? 'Aucune sélection' : (selectedIds.length === 1 ? activeResourceList.find(r => r.id === selectedIds[0])?.name : selectedIds.length + ' sélectionnés') }}
            </span>
            <span style="font-size: 10px;">&#9660;</span>
          </button>

          <!-- Overlay transparent pour fermer au clic exterieur -->
          <div 
            v-if="showResourceDropdown"
            style="position: fixed; inset: 0; z-index: 998;"
            @click="showResourceDropdown = false"
          />

          <!-- Dropdown teleporté dans body pour éviter overflow:hidden -->
          <Teleport to="body">
            <div 
              v-if="showResourceDropdown"
              class="resource-dropdown-panel"
              style="position: fixed; z-index: 999; background: white; border: 1px solid #d1d5db; border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,0.18); max-height: 280px; overflow-y: auto; min-width: 240px;"
              :style="dropdownPos"
              @click.stop
            >
              <div style="padding: 4px 8px; border-bottom: 1px solid #eee; display: flex; gap: 8px;">
                <button class="btn btn-sm" style="flex: 1; padding: 2px; font-size: 11px;" @click="$emit('update:selectedIds', activeResourceList.map(r => r.id))">Tout</button>
                <button class="btn btn-sm" style="flex: 1; padding: 2px; font-size: 11px;" @click="$emit('update:selectedIds', [])">Rien</button>
              </div>
              <label v-for="r in activeResourceList" :key="r.id" style="display: flex; align-items: center; gap: 8px; padding: 6px 12px; margin: 0; cursor: pointer; border-bottom: 1px solid #f3f4f6;">
                <input 
                  type="checkbox" 
                  :value="r.id" 
                  :checked="selectedIds.includes(r.id)"
                  @change="onResourceCheckboxToggle(r.id, $event)"
                />
                <span style="flex: 1; font-size: 13px;">{{ r.name }}</span>
              </label>
              <div v-if="activeResourceList.length === 0" style="padding: 12px; color: #9ca3af; text-align: center; font-size: 13px;">Aucune ressource</div>
            </div>
          </Teleport>
        </div>
      </template>



      <!-- Right actions slot -->
      <div class="filter-actions-right" style="margin-left: auto; display: flex; align-items: center; gap: 16px;">
        <slot name="actions"></slot>
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
  
  viewMode?: string;
  selectedIds?: number[];
  schoolId?: number | null;
  weekType?: 'W' | 'A' | 'B';
  periodTypeId?: number | null;
  periodIds?: number[];
  
  hideResourceSelectors?: boolean;
  hideSchoolSelector?: boolean;
}>(), {
  mode: 'timetable',
  schools: () => [],
  teachers: () => [],
  nonTeachingStaffs: () => [],
  divisions: () => [],
  classrooms: () => [],
  periodTypes: () => [],
  periods: () => [],
  viewMode: 'division',
  selectedIds: () => [],
  schoolId: null,
  weekType: 'W',
  periodTypeId: null,
  periodIds: () => [],
  hideResourceSelectors: false,
  hideSchoolSelector: false
});

const emit = defineEmits<{
  (e: 'update:viewMode', value: string): void;
  (e: 'update:selectedIds', value: number[]): void;
  (e: 'update:schoolId', value: number | null): void;
  (e: 'update:weekType', value: 'W' | 'A' | 'B'): void;
  (e: 'update:periodTypeId', value: number | null): void;
  (e: 'update:periodIds', value: number[]): void;
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

const activeResourceList = computed(() => {
  const m = props.viewMode?.toLowerCase();
  if (m === 'teacher') return filteredTeachers.value;
  if (m === 'non_teaching_staff') return filteredNonTeachingStaffs.value;
  if (m === 'classroom') return filteredClassrooms.value;
  if (m === 'division') return filteredDivisions.value;
  return [];
});

const showResourceDropdown = ref(false);
const dropdownPos = ref<Record<string, string>>({});

function openDropdown(event: MouseEvent) {
  const btn = (event.currentTarget as HTMLElement);
  const rect = btn.getBoundingClientRect();
  dropdownPos.value = {
    top: (rect.bottom + 4) + 'px',
    left: rect.left + 'px',
    width: Math.max(rect.width, 240) + 'px',
  };
  showResourceDropdown.value = true;
}

function onResourceCheckboxToggle(id: number, event: Event) {
  const checked = (event.target as HTMLInputElement).checked;
  let newIds = [...(props.selectedIds || [])];
  if (checked) {
    if (!newIds.includes(id)) newIds.push(id);
  } else {
    newIds = newIds.filter(x => x !== id);
  }
  emit('update:selectedIds', newIds);
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
</style>
