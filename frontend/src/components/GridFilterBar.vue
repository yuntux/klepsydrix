<template>
  <div class="filter-bar glass-morphism">
    <!-- Row 1: Primary Filters (Establishment, Mode, Resource) -->
    <div class="filters-row">
      <!-- 1. Établissement (School Selector) -->
      <div class="filter-item" v-if="!hideSchoolSelector && schools && schools.length > 0">
        <label>Établissement :</label>
        <select 
          :value="schoolId" 
          @change="$emit('update:schoolId', $event.target ? Number(($event.target as HTMLSelectElement).value) : null)" 
          class="select-custom"
        >
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
            <option value="classroom">Par Salle</option>
          </select>
        </div>

        <div class="filter-item" v-if="viewMode === 'division'">
          <label>Classe :</label>
          <select 
            :value="selectedId" 
            @change="$emit('update:selectedId', Number(($event.target as HTMLSelectElement).value))" 
            class="select-custom"
          >
            <option v-for="d in filteredDivisions" :key="d.id" :value="d.id">{{ d.name }}</option>
            <option v-if="filteredDivisions.length === 0" value="">Aucune classe</option>
          </select>
        </div>

        <div class="filter-item" v-else-if="viewMode === 'teacher'">
          <label>Enseignant :</label>
          <select 
            :value="selectedId" 
            @change="$emit('update:selectedId', Number(($event.target as HTMLSelectElement).value))" 
            class="select-custom"
          >
            <option v-for="t in filteredTeachers" :key="t.id" :value="t.id">{{ t.name }}</option>
            <option v-if="filteredTeachers.length === 0" value="">Aucun enseignant</option>
          </select>
        </div>

        <div class="filter-item" v-else-if="viewMode === 'classroom'">
          <label>Salle :</label>
          <select 
            :value="selectedId" 
            @change="$emit('update:selectedId', Number(($event.target as HTMLSelectElement).value))" 
            class="select-custom"
          >
            <option v-for="c in filteredClassrooms" :key="c.id" :value="c.id">{{ c.name }} (Cap. {{ c.capacity }})</option>
            <option v-if="filteredClassrooms.length === 0" value="">Aucune salle</option>
          </select>
        </div>
      </template>

      <!-- 3. Resource Selectors for 'preference' mode (optional) -->
      <template v-if="mode === 'preference' && !hideResourceSelectors">
        <div class="filter-item">
          <label>Type de Ressource :</label>
          <select 
            :value="viewMode" 
            @change="$emit('update:viewMode', ($event.target as HTMLSelectElement).value)" 
            class="select-custom"
          >
            <option value="teacher">👨‍🏫 Enseignant</option>
            <option value="classroom">🏢 Salle</option>
            <option value="division">🎒 Classe (Division)</option>
          </select>
        </div>

        <div class="filter-item">
          <label>Ressource :</label>
          <select 
            :value="selectedId" 
            @change="$emit('update:selectedId', Number(($event.target as HTMLSelectElement).value))" 
            class="select-custom"
          >
            <template v-if="viewMode === 'teacher'">
              <option v-for="t in filteredTeachers" :key="t.id" :value="t.id">{{ t.name }}</option>
            </template>
            <template v-else-if="viewMode === 'classroom'">
              <option v-for="c in filteredClassrooms" :key="c.id" :value="c.id">{{ c.name }}</option>
            </template>
            <template v-else-if="viewMode === 'division'">
              <option v-for="d in filteredDivisions" :key="d.id" :value="d.id">{{ d.name }}</option>
            </template>
            <option v-if="activeResourceOptionsCount === 0" value="">Aucune ressource disponible</option>
          </select>
        </div>
      </template>

      <!-- Right actions slot -->
      <div class="filter-actions-right" style="margin-left: auto; display: flex; align-items: center; gap: 16px;">
        <slot name="actions"></slot>
      </div>
    </div>

    <!-- Row 2: Secondary / Constraints Filters (Alternation & Periods) -->
    <div class="filters-row sub-row" v-if="mode === 'preference'">
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
import { computed } from 'vue';

const props = withDefaults(defineProps<{
  mode?: 'timetable' | 'preference';
  schools?: any[];
  teachers?: any[];
  divisions?: any[];
  classrooms?: any[];
  periodTypes?: any[];
  periods?: any[];
  
  viewMode?: string;
  selectedId?: number | null;
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
  divisions: () => [],
  classrooms: () => [],
  periodTypes: () => [],
  periods: () => [],
  viewMode: 'division',
  selectedId: null,
  schoolId: null,
  weekType: 'W',
  periodTypeId: null,
  periodIds: () => [],
  hideResourceSelectors: false,
  hideSchoolSelector: false
});

const emit = defineEmits<{
  (e: 'update:viewMode', value: string): void;
  (e: 'update:selectedId', value: number | null): void;
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

const filteredDivisions = computed(() => {
  if (!props.schoolId) return props.divisions;
  return props.divisions.filter(d => d.school_id === props.schoolId);
});

const filteredClassrooms = computed(() => {
  if (!props.schoolId) return props.classrooms;
  return props.classrooms.filter(c => c.school_id === props.schoolId);
});

const activeResourceOptionsCount = computed(() => {
  if (props.viewMode === 'teacher') return filteredTeachers.value.length;
  if (props.viewMode === 'classroom') return filteredClassrooms.value.length;
  if (props.viewMode === 'division') return filteredDivisions.value.length;
  return 0;
});

// Period types selection logic
const filteredPeriodTypes = computed(() => {
  const activePtIds = Array.from(new Set(props.periods.map(p => p.period_type_id)));
  return props.periodTypes.filter(pt => activePtIds.includes(pt.id));
});

const periodsOfType = computed(() => {
  if (!props.periodTypeId) return [];
  return props.periods.filter(p => p.period_type_id === props.periodTypeId);
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
  margin-bottom: 16px;
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
