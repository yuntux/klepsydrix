<template>
  <div class="m2m-ordered-list-container">
    <table class="m2m-table">
      <thead>
        <tr>
          <th class="order-col"></th>
          <th v-for="col in columns" :key="col.key">{{ col.label }}</th>
          <th class="actions-col"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(id, index) in localModel" :key="id + '-' + index">
          <td class="order-col">
            <button class="order-btn" @click.prevent="moveUp(index)" :disabled="index === 0" title="Monter">▲</button>
            <button class="order-btn" @click.prevent="moveDown(index)" :disabled="index === localModel.length - 1" title="Descendre">▼</button>
          </td>
          <td v-for="col in columns" :key="col.key">
            <input
              v-if="col.editable && isAssociationMode"
              type="number"
              class="form-input cell-input"
              :disabled="disabled"
              :value="getCellValue(id, col)"
              @change="onCellEdit(id, col, $event)"
            />
            <template v-else>{{ getCellValue(id, col) }}</template>
          </td>
          <td class="actions-col">
            <button class="delete-btn" @click.prevent="removeItem(index)" title="Retirer">✕</button>
          </td>
        </tr>
        <tr v-if="localModel.length === 0">
          <td :colspan="columns.length + 2" class="empty-state">Aucun élément sélectionné.</td>
        </tr>
      </tbody>
    </table>

    <div class="add-container" v-if="!disabled">
      <select v-model="selectedToAdd" class="add-select form-select">
        <option :value="null" disabled>-- Ajouter un élément --</option>
        <option v-for="opt in (isAssociationMode ? availablePickOptions : availableOptions)" :key="opt.value" :value="opt.value">
          {{ opt.label }}
        </option>
      </select>
      <button class="add-btn" @click.prevent="addItem" :disabled="!selectedToAdd">Ajouter</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue';
import { fetchGenericList, createGenericItem, updateGenericItem, deleteGenericItem } from '../../services/api';

const fkOptionsCache = inject<any>('fkOptionsCache', ref({}));
const openApiSpec = inject<any>('openApiSpec', ref(null));

const props = defineProps<{
  modelValue: any[];
  field: any;
  widgetParams?: any;
  disabled?: boolean;
  parentRecord?: any;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: any[]): void;
}>();

const localModel = ref<any[]>(Array.isArray(props.modelValue) ? [...props.modelValue] : []);

watch(() => props.modelValue, (newVal) => {
  if (Array.isArray(newVal)) {
    localModel.value = [...newVal];
  } else {
    localModel.value = [];
  }
}, { deep: true });

const selectedToAdd = ref<any>(null);

const columns = computed(() => {
  return props.widgetParams?.columns || [{ key: 'label', label: 'Élément' }];
});

// --- Mode association : la relation pointe vers un objet de liaison "possédé" (ex: MefDivision)
// qu'il faut créer/supprimer directement, plutôt que rattacher/détacher une ligne déjà existante.
const isAssociationMode = computed(() => !!props.widgetParams?.pickResource);

// Options du sélecteur "pick" (ex: la liste des Mef) — chargées séparément de field.options
// (qui référence les lignes de la relation elle-même, ex: mef_divisions, pas les Mef).
const pickOptions = ref<any[]>([]);

// Données fraîchement créées/éditées, en attendant que le cache global (fkOptionsCache /
// field.options, peuplé une seule fois au montage du formulaire) soit rechargé.
const localRowData = ref<Record<number, any>>({});

async function loadPickOptions() {
  if (!isAssociationMode.value) return;
  const resourceName = props.widgetParams.pickResource;
  const schoolId = props.parentRecord?.school_id;
  const res = await fetchGenericList(resourceName, 0, 1000, schoolId);
  pickOptions.value = res.items;
}

watch(() => [props.widgetParams?.pickResource, props.parentRecord?.school_id], loadPickOptions, { immediate: true });

function getRowData(id: any): any {
  if (localRowData.value[id]) return localRowData.value[id];
  const options = props.field?.options || [];
  const opt = options.find((o: any) => o.value === id);
  return opt?.rawData || {};
}

const availableOptions = computed(() => {
  const options = props.field?.options || [];
  return options.filter((o: any) => !localModel.value.includes(o.value));
});

const availablePickOptions = computed(() => {
  if (!isAssociationMode.value) return [];
  const pickField = props.widgetParams.pickField || 'id';
  const usedValues = new Set(localModel.value.map(id => getRowData(id)[pickField]));
  return pickOptions.value
    .filter((o: any) => !usedValues.has(o.id))
    .map((o: any) => ({ value: o.id, label: o.display_name || o.name || `#${o.id}` }));
});

function getCellValue(id: any, col: any): string {
  const raw = getRowData(id);

  if (col.key === 'label') {
    const options = props.field?.options || [];
    const opt = options.find((o: any) => o.value === id);
    return opt?.label || String(id);
  }

  const val = raw[col.key];
  if (val === undefined || val === null) return '';

  // En mode association, le champ "pick" (ex: mef_id) se résout via les pickOptions déjà chargées.
  if (isAssociationMode.value && col.key === props.widgetParams.pickField) {
    const found = pickOptions.value.find((o: any) => o.id === val);
    return found ? (found.display_name || found.name || String(val)) : String(val);
  }

  let resourceName = col.resource;

  if (!resourceName && props.field?.resource && openApiSpec.value?.components?.schemas) {
    const targetSchemaName = `${props.field.resource}_CreatePayload`;
    const targetSchema = openApiSpec.value.components.schemas[targetSchemaName];
    if (targetSchema && targetSchema.properties && targetSchema.properties[col.key]) {
      const propConfig = targetSchema.properties[col.key];
      resourceName = propConfig.resource;

      if (!resourceName && propConfig.anyOf) {
        const opt = propConfig.anyOf.find((o: any) => o.resource);
        if (opt) resourceName = opt.resource;
      }
    }
  }

  if (resourceName) {
    const cache = fkOptionsCache.value[resourceName];
    if (cache && cache.items) {
      if (Array.isArray(val)) {
        return val.map((vId: any) => {
          const found = cache.items.find((item: any) => item.value === vId);
          return found ? found.label : String(vId);
        }).join(', ');
      } else {
        const found = cache.items.find((item: any) => item.value === val);
        return found ? found.label : String(val);
      }
    }
  }

  if (Array.isArray(val)) {
    return val.join(', ');
  }

  return String(val);
}

function moveUp(index: number) {
  if (props.disabled || index <= 0) return;
  const newArr = [...localModel.value];
  const temp = newArr[index];
  newArr[index] = newArr[index - 1];
  newArr[index - 1] = temp;
  localModel.value = newArr;
  emit('update:modelValue', localModel.value);
}

function moveDown(index: number) {
  if (props.disabled || index >= localModel.value.length - 1) return;
  const newArr = [...localModel.value];
  const temp = newArr[index];
  newArr[index] = newArr[index + 1];
  newArr[index + 1] = temp;
  localModel.value = newArr;
  emit('update:modelValue', localModel.value);
}

async function removeItem(index: number) {
  if (props.disabled) return;
  const id = localModel.value[index];

  if (isAssociationMode.value) {
    await deleteGenericItem(props.field.resource, id);
  }

  const newArr = [...localModel.value];
  newArr.splice(index, 1);
  localModel.value = newArr;
  emit('update:modelValue', localModel.value);
}

async function addItem() {
  if (props.disabled || !selectedToAdd.value) return;

  if (isAssociationMode.value) {
    if (!props.parentRecord?.id) return;
    const parentField = props.widgetParams.parentField;
    const pickField = props.widgetParams.pickField;
    const created = await createGenericItem(props.field.resource, {
      [parentField]: props.parentRecord.id,
      [pickField]: selectedToAdd.value
    });
    localRowData.value = { ...localRowData.value, [created.id]: created };
    localModel.value = [...localModel.value, created.id];
    emit('update:modelValue', localModel.value);
    selectedToAdd.value = null;
    return;
  }

  const newArr = [...localModel.value, selectedToAdd.value];
  localModel.value = newArr;
  emit('update:modelValue', localModel.value);
  selectedToAdd.value = null;
}

async function onCellEdit(id: number, col: any, event: Event) {
  const value = Number((event.target as HTMLInputElement).value) || 0;
  const updated = await updateGenericItem(props.field.resource, id, { [col.key]: value });
  localRowData.value = { ...localRowData.value, [id]: updated };
}
</script>

<style scoped>
.m2m-ordered-list-container {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 12px;
}

.m2m-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.m2m-table th {
  text-align: left;
  padding: 8px;
  border-bottom: 2px solid var(--border-color);
  color: var(--text-secondary);
  font-weight: 600;
}

.m2m-table td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border-color);
  vertical-align: middle;
}

.m2m-table tr:last-child td {
  border-bottom: none;
}

.order-col {
  width: 50px;
  text-align: center;
}

.actions-col {
  width: 40px;
  text-align: right;
}

.cell-input {
  width: 90px;
  padding: 2px 6px;
  font-size: 13px;
}

.order-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 2px 4px;
  font-size: 12px;
}

.order-btn:hover:not(:disabled) {
  color: var(--accent-primary);
}

.order-btn:disabled {
  opacity: 0.2;
  cursor: default;
}

.delete-btn {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: var(--accent-danger);
  border-radius: var(--radius-md);
  cursor: pointer;
  padding: 2px 6px;
  font-size: 12px;
  font-weight: bold;
}

.delete-btn:hover {
  background: #fee2e2;
}

.empty-state {
  text-align: center;
  color: var(--text-muted);
  font-style: italic;
  padding: 16px !important;
}

.add-container {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.add-select {
  flex: 1;
}

.add-btn {
  padding: 0 16px;
  background-color: var(--accent-primary);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-weight: 500;
  font-size: 13px;
}

.add-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
