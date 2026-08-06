<template>
  <div class="composition-preview-widget">
    <p class="preview-hint">Vous pouvez ajuster manuellement la durée ou la quinzaine de chaque enfant avant d'enregistrer.</p>
    <table class="preview-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Semaine</th>
          <th>Durée (min)</th>
          <th>Offset</th>
          <th>Périodes</th>
          <th>Professeurs (IDs)</th>
          <th>Groupes (IDs)</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(child, idx) in children" :key="idx">
          <td>Enfant {{ idx + 1 }}</td>
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
          <td class="text-xs">{{ (child.teacher_ids || []).join(', ') }}</td>
          <td class="text-xs">{{ (child.group_ids || []).join(', ') }}</td>
        </tr>
        <tr v-if="children.length === 0">
          <td colspan="7" class="empty-state">Aucun cours enfant à prévisualiser.</td>
        </tr>
      </tbody>
    </table>
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

watch(() => props.modelValue, (val) => {
  if (Array.isArray(val) && JSON.stringify(val) !== JSON.stringify(children.value)) {
    children.value = val.map((c: any) => ({ ...c }));
  }
});

function emitUpdate() {
  emit('update:modelValue', children.value);
}

onMounted(async () => {
  const source = props.widgetParams?.sourceRecord || {};
  const res = await api.fetchGenericList('periods', 0, 1000);
  const items = source.period_ids?.length ? res.items.filter((i: any) => source.period_ids.includes(i.id)) : res.items;
  periodOptions.value = items.map((i: any) => ({ value: i.id, label: i.name || `Période ${i.id}` }));
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
.preview-table {
  width: 100%;
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
