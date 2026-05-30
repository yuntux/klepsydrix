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
            {{ getCellValue(id, col) }}
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
        <option v-for="opt in availableOptions" :key="opt.value" :value="opt.value">
          {{ opt.label }}
        </option>
      </select>
      <button class="add-btn" @click.prevent="addItem" :disabled="!selectedToAdd">Ajouter</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue';

const fkOptionsCache = inject<any>('fkOptionsCache', ref({}));
const openApiSpec = inject<any>('openApiSpec', ref(null));

const props = defineProps<{
  modelValue: any[];
  field: any;
  widgetParams?: any;
  disabled?: boolean;
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

const availableOptions = computed(() => {
  const options = props.field?.options || [];
  return options.filter((o: any) => !localModel.value.includes(o.value));
});

function getCellValue(id: any, col: any): string {
  const options = props.field?.options || [];
  const opt = options.find((o: any) => o.value === id);
  if (!opt) return String(id);
  
  if (col.key === 'label') return opt.label;
  
  const raw = opt.rawData;
  if (!raw) return opt.label;
  
  const val = raw[col.key];
  
  if (val === undefined || val === null) return '';

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

function removeItem(index: number) {
  if (props.disabled) return;
  const newArr = [...localModel.value];
  newArr.splice(index, 1);
  localModel.value = newArr;
  emit('update:modelValue', localModel.value);
}

function addItem() {
  if (props.disabled || !selectedToAdd.value) return;
  const newArr = [...localModel.value, selectedToAdd.value];
  localModel.value = newArr;
  emit('update:modelValue', localModel.value);
  selectedToAdd.value = null;
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
