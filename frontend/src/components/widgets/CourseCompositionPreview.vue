<template>
  <div class="composition-preview-widget">
    <p class="preview-hint">Vous pouvez ajuster manuellement la durée, la quinzaine, le décalage ou les périodes de chaque enfant avant de valider.</p>
    <div class="preview-table-wrapper">
      <table class="preview-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Matière</th>
            <th>Semaine</th>
            <th>Durée (min)</th>
            <th>Offset</th>
            <th>Périodes</th>
            <th>Professeurs</th>
            <th>Co-enseignement</th>
            <th>Salles</th>
            <th>Classes</th>
            <th>Parties de classe</th>
            <th>Groupes</th>
            <th>Matériel</th>
            <th>Personnel non enseignant</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(child, idx) in children" :key="idx">
            <td>Enfant {{ idx + 1 }}</td>
            <td class="text-xs">{{ namesFor(child.subject_id != null ? [child.subject_id] : [], subjectMap) }}</td>
            <td>
              <select v-model="child.week_type" class="form-select" :disabled="disabled" @change="emitUpdate">
                <option value="W">Semaine Entière (W)</option>
                <option value="A">Quinzaine A</option>
                <option value="B">Quinzaine B</option>
              </select>
            </td>
            <td>
              <input type="number" v-model.number="child.duration_minutes" class="form-input" min="15" step="5" :disabled="disabled" @change="emitUpdate" />
            </td>
            <td>
              <input type="number" v-model.number="child.parent_timeslot_offset" class="form-input" min="0" :disabled="disabled" @change="emitUpdate" />
            </td>
            <td>
              <SearchableMultiSelect v-model="child.period_ids" :options="periodOptions" :disabled="disabled" placeholder="Héritées du parent" @change="emitUpdate" />
            </td>
            <td class="text-xs">{{ namesFor(child.teacher_ids, teacherMap) }}</td>
            <td class="text-xs">{{ child.is_co_teaching ? 'Oui' : 'Non' }}</td>
            <td class="text-xs">{{ namesFor(child.classroom_ids, classroomMap) }}</td>
            <td class="text-xs">{{ namesFor(child.division_ids, divisionMap) }}</td>
            <td class="text-xs">{{ namesFor(child.class_part_ids, classPartMap) }}</td>
            <td class="text-xs">{{ namesFor(child.group_ids, groupMap) }}</td>
            <td class="text-xs">{{ namesFor(child.material_ids, materialMap) }}</td>
            <td class="text-xs">{{ namesFor(child.non_teaching_staff_ids, nonTeachingStaffMap) }}</td>
          </tr>
          <tr v-if="children.length === 0">
            <td colspan="14" class="empty-state">Aucun cours enfant à prévisualiser.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
// Widget de champ pour l'étape 2 (aperçu) de l'assistant de décomposition de cours — voir
// CourseCompositionMapping.vue pour l'étape 1 et GenericWizard.vue pour l'orchestration.
// modelValue est la liste des cours enfants en brouillon (déjà calculée par rpc_preview_composition
// à l'étape précédente), éditable avant l'enregistrement définitif (rpc_save_composition).
import { ref, onMounted, watch } from 'vue';
import SearchableMultiSelect from '../SearchableMultiSelect.vue';
import * as api from '../../services/api';
import { useDataStore } from '../../stores/data';

const props = defineProps<{
  modelValue: any[];
  field?: any;
  widgetParams?: { recordId: number; resourceKey: string; sourceRecord?: any };
  disabled?: boolean;
  parentRecord?: any;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: any[]): void;
}>();

const children = ref<any[]>(Array.isArray(props.modelValue) ? props.modelValue.map((c: any) => ({ ...c })) : []);
const periodOptions = ref<Array<{ value: number; label: string }>>([]);

// Réutilise le store partagé (déjà peuplé pour la grille de l'emploi du temps) pour les
// ressources qui y figurent déjà — évite un refetch redondant.
const dataStore = useDataStore();
const teacherMap = dataStore.teacherMap;
const classroomMap = dataStore.classroomMap;
const divisionMap = dataStore.divisionMap;
const nonTeachingStaffMap = dataStore.nonTeachingStaffMap;

// Absentes du store partagé (propre à ce widget) : chargées localement, comme periodOptions.
const subjectMap = ref<Record<number, any>>({});
const classPartMap = ref<Record<number, any>>({});
const groupMap = ref<Record<number, any>>({});
const materialMap = ref<Record<number, any>>({});

function namesFor(ids: number[] | undefined, map: Record<number, any>): string {
  return (ids || []).map(id => map[id]?.display_name || map[id]?.name || `#${id}`).join(', ') || '—';
}

watch(() => props.modelValue, (val) => {
  if (Array.isArray(val) && JSON.stringify(val) !== JSON.stringify(children.value)) {
    children.value = val.map((c: any) => ({ ...c }));
  }
});

function emitUpdate() {
  emit('update:modelValue', children.value);
}

function toMap(items: any[]): Record<number, any> {
  return items.reduce((map: Record<number, any>, item: any) => { map[item.id] = item; return map; }, {});
}

onMounted(async () => {
  const source = props.widgetParams?.sourceRecord || {};
  const [periodsRes, subjectsRes, classPartsRes, groupsRes, materialsRes] = await Promise.all([
    api.fetchAllGenericItems('periods'),
    api.fetchAllGenericItems('subjects'),
    api.fetchAllGenericItems('class_parts'),
    api.fetchAllGenericItems('groups'),
    api.fetchAllGenericItems('materials'),
  ]);
  const items = source.period_ids?.length ? periodsRes.items.filter((i: any) => source.period_ids.includes(i.id)) : periodsRes.items;
  periodOptions.value = items.map((i: any) => ({ value: i.id, label: i.name || `Période ${i.id}` }));
  subjectMap.value = toMap(subjectsRes.items);
  classPartMap.value = toMap(classPartsRes.items);
  groupMap.value = toMap(groupsRes.items);
  materialMap.value = toMap(materialsRes.items);
});
</script>

<style scoped>
.composition-preview-widget {
  width: 100%;
}
.preview-hint {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin: 0 0 8px 0;
}
.preview-table-wrapper {
  overflow-x: auto;
}
.preview-table {
  width: 100%;
  min-width: 1400px;
  border-collapse: collapse;
  table-layout: fixed;
}
.preview-table th {
  text-align: left;
  padding: 8px;
  background: var(--bg-body);
  font-weight: 500;
  font-size: 0.85rem;
}
.preview-table td {
  padding: 8px;
  border-bottom: 1px solid var(--border-color);
  vertical-align: top;
}
.text-xs { font-size: 0.75rem; }
.empty-state {
  text-align: center;
  color: var(--text-muted);
  padding: 16px;
}
</style>
