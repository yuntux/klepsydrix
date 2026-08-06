<template>
  <div class="composition-mapping-widget">
    <div class="section-block">
      <h3 class="section-title">Répartition spatiale (Mapping)</h3>
      <table class="mapping-table">
        <thead>
          <tr>
            <th>Professeurs</th>
            <th>Groupes</th>
            <th>Parties de classe</th>
            <th>Classes</th>
            <th>Salles</th>
            <th style="width: 50px;"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in mapping" :key="index">
            <td>
              <SearchableMultiSelect
                v-model="row.teacher_ids"
                :options="teacherOptions"
                :disabled="disabled"
                placeholder="Sélectionner"
                @change="onMappingChanged" />
            </td>
            <td>
              <SearchableMultiSelect
                v-model="row.group_ids"
                :options="groupOptions"
                placeholder="Sélectionner"
                :disabled="disabled || (row.class_part_ids && row.class_part_ids.length > 0) || (row.division_ids && row.division_ids.length > 0)"
                @change="onMappingChanged" />
            </td>
            <td>
              <SearchableMultiSelect
                v-model="row.class_part_ids"
                :options="classPartOptions"
                placeholder="Sélectionner"
                :disabled="disabled || (row.group_ids && row.group_ids.length > 0) || (row.division_ids && row.division_ids.length > 0)"
                @change="onMappingChanged" />
            </td>
            <td>
              <SearchableMultiSelect
                v-model="row.division_ids"
                :options="divisionOptions"
                placeholder="Sélectionner"
                :disabled="disabled || (row.group_ids && row.group_ids.length > 0) || (row.class_part_ids && row.class_part_ids.length > 0)"
                @change="onMappingChanged" />
            </td>
            <td>
              <SearchableMultiSelect
                v-model="row.classroom_ids"
                :options="classroomOptions"
                :disabled="disabled"
                placeholder="Sélectionner"
                @change="onMappingChanged" />
            </td>
            <td>
              <button type="button" class="btn-delete-row" :disabled="disabled" @click="removeMappingRow(index)" title="Supprimer la ligne">×</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div class="mt-2">
        <BaseButton type="button" variant="secondary" :disabled="disabled" @click="addMappingRow">
          + Ajouter une ligne de répartition
        </BaseButton>
      </div>
      <p v-if="!isMappingValid" class="mapping-hint">
        Chaque ligne doit porter au moins un professeur et exactement une cible (groupe, partie de classe ou classe), sans professeur répété entre les lignes.
      </p>
    </div>

    <div class="section-block">
      <h3 class="section-title">Mode de répartition temporelle</h3>
      <div v-if="modesLoading" class="text-sm text-muted">Évaluation des modes...</div>
      <div class="modes-grid">
        <div
          v-for="mode in 9"
          :key="mode"
          class="mode-card"
          :class="{
            'disabled-mode': !availableModes.includes(mode),
            'selected-mode': selectedMode === mode
          }"
          @click="selectMode(mode)"
          :title="!availableModes.includes(mode) ? 'Mode incompatible avec la répartition actuelle' : ''"
        >
          <div class="mode-id">{{ mode }}</div>
          <div class="mode-desc">{{ getModeLabel(mode) }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Widget de champ pour l'étape 1 de l'assistant de décomposition de cours (Course.__actions__,
// steps déclarés côté backend — voir GenericWizard.vue). Regroupe le mapping (profs x
// groupes/parties/classes/salles) ET le choix du mode temporel dans un seul widget, car la
// disponibilité des modes dépend en direct du mapping (appel RPC débounced à chaque changement) —
// deux champs séparés dans un formulaire générique classique ne permettraient pas cette
// dépendance croisée sans machinerie supplémentaire. modelValue est un objet composite
// {mapping, mode} ; voir CourseCompositionPreview.vue pour l'étape suivante.
import { ref, computed, onMounted, watch } from 'vue';
import BaseButton from '../BaseButton.vue';
import SearchableMultiSelect from '../SearchableMultiSelect.vue';
import * as api from '../../services/api';

const props = defineProps<{
  modelValue: { mapping: any[]; mode: number | null };
  field?: any;
  widgetParams?: { recordId: number; resourceKey: string; sourceRecord?: any };
  disabled?: boolean;
  parentRecord?: any;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: { mapping: any[]; mode: number | null }): void;
}>();

const teacherOptions = ref<Array<{ value: number; label: string }>>([]);
const groupOptions = ref<Array<{ value: number; label: string }>>([]);
const classPartOptions = ref<Array<{ value: number; label: string }>>([]);
const divisionOptions = ref<Array<{ value: number; label: string }>>([]);
const classroomOptions = ref<Array<{ value: number; label: string }>>([]);

const mapping = ref<Array<any>>(
  props.modelValue?.mapping?.length
    ? props.modelValue.mapping.map((r: any) => ({ ...r }))
    : [{ teacher_ids: [], group_ids: [], class_part_ids: [], division_ids: [], classroom_ids: [] }]
);
const selectedMode = ref<number | null>(props.modelValue?.mode ?? null);
const availableModes = ref<number[]>([]);
const modesLoading = ref(false);

const isMappingValid = computed(() => {
  if (mapping.value.length === 0) return false;
  const seenTeachers = new Set();
  return mapping.value.every((row: any) => {
    const hasTeacher = row.teacher_ids && row.teacher_ids.length > 0;
    const hasGroup = row.group_ids && row.group_ids.length > 0;
    const hasClassPart = row.class_part_ids && row.class_part_ids.length > 0;
    const hasDivision = row.division_ids && row.division_ids.length > 0;
    if (!hasTeacher) return false;
    if (!hasGroup && !hasClassPart && !hasDivision) return false;
    const targetsCount = [hasGroup, hasClassPart, hasDivision].filter(Boolean).length;
    if (targetsCount !== 1) return false;
    for (const tid of (row.teacher_ids || [])) {
      if (seenTeachers.has(tid)) return false;
      seenTeachers.add(tid);
    }
    return true;
  });
});

function emitUpdate() {
  emit('update:modelValue', { mapping: mapping.value, mode: selectedMode.value });
}

let debounceTimeout: any = null;

onMounted(async () => {
  const source = props.widgetParams?.sourceRecord || {};
  const [teachersRes, groupsRes, classPartsRes, divisionsRes, classroomsRes] = await Promise.all([
    api.fetchGenericList('teachers', 0, 1000),
    api.fetchGenericList('groups', 0, 1000),
    api.fetchGenericList('class_parts', 0, 1000),
    api.fetchGenericList('divisions', 0, 1000),
    api.fetchGenericList('classrooms', 0, 1000),
  ]);

  const filterByIds = (items: any[], ids: number[]) => (ids && ids.length > 0 ? items.filter((i: any) => ids.includes(i.id)) : items);

  teacherOptions.value = filterByIds(teachersRes.items, source.teacher_ids).map((i: any) => ({ value: i.id, label: `${i.first_name} ${i.last_name}` }));
  groupOptions.value = filterByIds(groupsRes.items, source.group_ids).map((i: any) => ({ value: i.id, label: i.name || `Groupe ${i.id}` }));
  classPartOptions.value = filterByIds(classPartsRes.items, source.class_part_ids).map((i: any) => ({ value: i.id, label: i.name || `Partie ${i.id}` }));
  divisionOptions.value = filterByIds(divisionsRes.items, source.division_ids).map((i: any) => ({ value: i.id, label: i.name || `Classe ${i.id}` }));
  classroomOptions.value = filterByIds(classroomsRes.items, source.classroom_ids).map((i: any) => ({ value: i.id, label: i.name || `Salle ${i.id}` }));

  if (!props.modelValue?.mapping?.length && source.teacher_ids?.length > 0) {
    mapping.value = source.teacher_ids.map((teacherId: number) => ({
      teacher_ids: [teacherId], group_ids: [], class_part_ids: [], division_ids: [], classroom_ids: [],
    }));
  }

  await fetchAvailableModes();
});

function getModeLabel(mode: number) {
  const labels: Record<number, string> = {
    1: '1 séance par professeur',
    2: 'Alternance par quinzaine',
    3: 'Barrette (Rotation mi-cours)',
    4: 'Barrette + Alternance quinzaine',
    5: 'Rotation quinzaine croisée',
    6: 'Alternance tri-hebdomadaire',
    7: 'Périodes fixes (1 par période)',
    8: 'Barrette sur périodes multiples',
    9: 'Alternance profs / périodes',
  };
  return labels[mode] || `Mode ${mode}`;
}

function addMappingRow() {
  mapping.value.push({ teacher_ids: [], group_ids: [], class_part_ids: [], division_ids: [], classroom_ids: [] });
  onMappingChanged();
}

function removeMappingRow(index: number) {
  mapping.value.splice(index, 1);
  onMappingChanged();
}

function onMappingChanged() {
  emitUpdate();
  if (selectedMode.value && !availableModes.value.includes(selectedMode.value)) {
    selectedMode.value = null;
  }
  if (debounceTimeout) clearTimeout(debounceTimeout);
  debounceTimeout = setTimeout(fetchAvailableModes, 300);
}

function selectMode(mode: number) {
  if (availableModes.value.includes(mode)) {
    selectedMode.value = mode;
    emitUpdate();
  }
}

async function fetchAvailableModes() {
  if (!isMappingValid.value || !props.widgetParams?.recordId || !props.widgetParams?.resourceKey) {
    availableModes.value = [];
    if (selectedMode.value) { selectedMode.value = null; emitUpdate(); }
    return;
  }
  modesLoading.value = true;
  try {
    const res = await api.callInstanceMethod(props.widgetParams.resourceKey, props.widgetParams.recordId, 'rpc_get_available_modes', {
      kwargs: { mapping: mapping.value },
    });
    availableModes.value = res.available_modes || [];
    if (selectedMode.value && !availableModes.value.includes(selectedMode.value)) {
      selectedMode.value = null;
      emitUpdate();
    }
  } catch (e) {
    availableModes.value = [];
  } finally {
    modesLoading.value = false;
  }
}

watch(() => props.modelValue, (val) => {
  if (val?.mapping && JSON.stringify(val.mapping) !== JSON.stringify(mapping.value)) {
    mapping.value = val.mapping.map((r: any) => ({ ...r }));
  }
});
</script>

<style scoped>
.composition-mapping-widget {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
}
.section-block {
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
}
.section-title {
  margin: 0 0 12px 0;
  font-size: 1rem;
  font-weight: 600;
  color: var(--accent-primary);
}
.mapping-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}
.mapping-table th {
  text-align: left;
  padding: 8px;
  background: var(--bg-body);
  font-weight: 500;
  font-size: 0.85rem;
}
.mapping-table td {
  padding: 8px;
  border-bottom: 1px solid var(--border-color);
  vertical-align: top;
}
.mt-2 { margin-top: 8px; }
.mapping-hint {
  margin-top: 10px;
  font-size: 0.8rem;
  color: var(--text-muted);
}
.text-sm { font-size: 0.85rem; }
.text-muted { color: var(--text-muted); }
.btn-delete-row {
  background: transparent;
  border: none;
  color: var(--accent-danger);
  font-size: 1.2rem;
  cursor: pointer;
  padding: 4px 8px;
}
.btn-delete-row:hover {
  background: rgba(239, 68, 68, 0.1);
  border-radius: 4px;
}
.modes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}
.mode-card {
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 12px;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--bg-body);
}
.mode-card:hover:not(.disabled-mode) {
  border-color: var(--accent-primary);
  box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}
.selected-mode {
  border-color: var(--accent-primary);
  background: rgba(59, 130, 246, 0.1);
}
.disabled-mode {
  opacity: 0.5;
  cursor: not-allowed;
  filter: grayscale(1);
}
.mode-id {
  font-size: 1.2rem;
  font-weight: bold;
  color: var(--accent-primary);
}
.mode-desc {
  font-size: 0.85rem;
  margin-top: 4px;
}
</style>
