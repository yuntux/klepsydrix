<template>
  <div class="generic-pivot-container">
    <div v-if="loading" class="loader-container">
      <div class="spinner"></div>
    </div>
    <div v-else-if="error" class="pivot-error">{{ error }}</div>
    <template v-else>
      <div v-if="selectedServiceIds.length > 0" class="pivot-toolbar">
        <span class="selection-badge">{{ selectedServiceIds.length }} service(s) sélectionné(s)</span>
        <span v-if="actionError" class="pivot-action-error">{{ actionError }}</span>
        <BaseButton
          v-for="action in availableActions"
          :key="action.id"
          variant="primary"
          size="sm"
          :loading="actionLoading"
          @click="runAction(action)"
        >
          {{ action.label }}
        </BaseButton>
      </div>

      <div class="table-wrapper">
        <table class="pivot-table">
          <thead>
            <tr>
              <th v-for="(dim, i) in rowDims" :key="'dim-' + i">{{ dimHeaderLabel(dim) }}</th>
              <th v-for="col in fixedColumns" :key="col.key">{{ col.overrideLabel || fieldLabel(col.field) }}</th>
              <th v-for="colVal in sortedColValues" :key="colVal">{{ colLabel(colVal) }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in pivotRows" :key="row.key">
              <td v-for="(label, i) in row.labels" :key="'label-' + i" class="pivot-label-cell">{{ label }}</td>
              <td v-for="col in fixedColumns" :key="col.key" class="pivot-measure-cell">
                {{ aggregateValue(row.recordIds, col.field, col.agg) }}
              </td>
              <td
                v-for="colVal in sortedColValues"
                :key="colVal"
                class="pivot-cell"
                :class="{ 'is-selected': isCellSelected(row.key, colVal), 'is-hatched': cellColor(row.key, colVal) === 'HATCHED' }"
                :style="cellStyle(row.key, colVal)"
              >
                <div class="pivot-cell-inner">
                  <input
                    v-if="hasCellContent(row.key, colVal)"
                    type="checkbox"
                    class="pivot-cell-checkbox"
                    :checked="isCellSelected(row.key, colVal)"
                    @change="toggleCell(row.key, colVal)"
                  />
                  <template v-if="matrixCell.type === 'aggregate'">
                    <span class="pivot-cell-value">{{ aggregateValue(cellRecordIdsFor(row.key, colVal), matrixCell.field, matrixCell.agg) }}</span>
                  </template>
                  <template v-else>
                    <span class="pivot-cell-value pivot-cell-list-summary">{{ listCellSummary(row.key, colVal).label }}</span>
                    <button
                      v-if="hasCellContent(row.key, colVal)"
                      class="btn-edit-cell"
                      title="Modifier"
                      @click.stop="openCell(row.key, colVal)"
                    >✏️</button>
                  </template>
                </div>
              </td>
            </tr>
            <tr v-if="pivotRows.length === 0">
              <td :colspan="rowDims.length + fixedColumns.length + sortedColValues.length" class="pivot-empty">
                Aucune donnée.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <GenericListModal
      v-if="cellPopin"
      :resourceKey="cellPopin.resourceKey"
      :ids="cellPopin.ids"
      :title="cellPopin.title"
      :readOnly="cellPopin.readOnly"
      :listConfig="cellPopin.listConfig"
      @close="cellPopin = null"
    />
  </div>
</template>

<script setup lang="ts">
// Vue pivot générique (architecture.md section 15.L) : un tableau où les lignes sont les
// enregistrements d'une ressource de base (avec explosion optionnelle sur un champ m2m), les
// colonnes sont les valeurs distinctes d'un champ, et chaque cellule agrège ou résume les
// enregistrements du croisement ligne x colonne. Jamais d'édition directe sur une cellule agrégée
// (voir section 15.L) — l'édition d'une cellule "liste" passe par GenericListModal, réutilisé tel
// quel et filtré par la liste d'IDs déjà résolue ici (voir son prop `ids`), pas par un filtre
// serveur sur les axes ligne/colonne : ce sont souvent des champs dérivés (related_field, ex:
// division_id/mef_id) non filtrables en SQL.
import { ref, computed, inject, onMounted } from 'vue';
import { useQueryClient } from '@tanstack/vue-query';
import * as api from '../services/api';
import BaseButton from './BaseButton.vue';
import GenericListModal from './GenericListModal.vue';
import { genericCacheKey } from '../composables/useGenericCache';

const queryClient = useQueryClient();

interface RowDim {
  field: string;
  explode?: boolean;
  overrideLabel?: string;
}

const props = defineProps<{
  resourceKey: string;
  pivotConfig: {
    row: RowDim | RowDim[];
    columns?: Array<{ key: string; field: string; agg: string; overrideLabel?: string }>;
    matrix: { field: string; cell: { type: 'aggregate' | 'list'; field: string; agg?: string } };
    colorField?: string;
  };
}>();

const openApiSpec = inject<any>('openApiSpec', ref(null));

const loading = ref(true);
const error = ref<string | null>(null);
const actionError = ref<string | null>(null);
const actionLoading = ref(false);
const records = ref<any[]>([]);
const optionMaps = ref<Record<string, Record<number, string>>>({});
const genericActions = ref<any[]>([]);
const selectedCells = ref<Set<string>>(new Set());
const cellPopin = ref<{ resourceKey: string; ids: number[]; title: string; listConfig: any; readOnly: boolean } | null>(null);

const rowDims = computed<RowDim[]>(() => {
  const r = props.pivotConfig?.row;
  return Array.isArray(r) ? r : (r ? [r] : []);
});
const fixedColumns = computed(() => props.pivotConfig?.columns || []);
const matrixField = computed(() => props.pivotConfig?.matrix?.field);
const matrixCell = computed(() => props.pivotConfig?.matrix?.cell || { type: 'aggregate' as const, field: '', agg: 'sum' });
const colorField = computed(() => props.pivotConfig?.colorField);

const baseSchema = computed(() => openApiSpec.value?.components?.schemas?.[`${props.resourceKey}_CreatePayload`]);

function fieldSchemaProp(field: string): any {
  return baseSchema.value?.properties?.[field];
}

function fieldResource(field: string): string | null {
  const prop = fieldSchemaProp(field);
  if (!prop) return null;
  if (prop.resource) return prop.resource;
  if (prop.anyOf) {
    const opt = prop.anyOf.find((o: any) => o.resource);
    if (opt) return opt.resource;
  }
  return null;
}

function fieldLabel(field: string): string {
  return fieldSchemaProp(field)?.title || field;
}

function dimHeaderLabel(dim: RowDim): string {
  return dim.overrideLabel || fieldLabel(dim.field);
}

function dimLabel(dim: RowDim, value: any): string {
  const resource = fieldResource(dim.field);
  if (resource) {
    const map = optionMaps.value[resource] || {};
    return map[Number(value)] ?? String(value);
  }
  return String(value);
}

const matrixResource = computed(() => (matrixField.value ? fieldResource(matrixField.value) : null));

function colLabel(rawVal: string): string {
  if (matrixResource.value) {
    const map = optionMaps.value[matrixResource.value] || {};
    return map[Number(rawVal)] ?? rawVal;
  }
  return rawVal;
}

function cartesian(arrays: any[][]): any[][] {
  return arrays.reduce((acc: any[][], curr: any[]) => acc.flatMap(a => curr.map(c => [...a, c])), [[]] as any[][]);
}

const grouped = computed(() => {
  const rowRecordIds = new Map<string, Set<number>>();
  const rowLabelParts = new Map<string, any[]>();
  const cellRecordIds = new Map<string, Set<number>>();
  const colValuesSet = new Set<string>();

  for (const rec of records.value) {
    const dimValueSets = rowDims.value.map(dim => {
      if (dim.explode) {
        const arr = rec[dim.field] || [];
        return arr;
      }
      const v = rec[dim.field];
      return (v === undefined || v === null) ? [] : [v];
    });
    if (dimValueSets.some((s: any[]) => s.length === 0)) continue;
    const combos = cartesian(dimValueSets);

    const colVal = matrixField.value ? rec[matrixField.value] : null;
    const hasCol = colVal !== null && colVal !== undefined;
    if (hasCol) colValuesSet.add(String(colVal));

    for (const combo of combos) {
      const rowKey = combo.join(' ');
      if (!rowRecordIds.has(rowKey)) {
        rowRecordIds.set(rowKey, new Set());
        rowLabelParts.set(rowKey, combo);
      }
      rowRecordIds.get(rowKey)!.add(rec.id);

      if (hasCol) {
        const cellKey = rowKey + ' ' + colVal;
        if (!cellRecordIds.has(cellKey)) cellRecordIds.set(cellKey, new Set());
        cellRecordIds.get(cellKey)!.add(rec.id);
      }
    }
  }

  return { rowRecordIds, rowLabelParts, cellRecordIds, colValuesSet };
});

const recordsById = computed<Record<number, any>>(() => Object.fromEntries(records.value.map(r => [r.id, r])));

const sortedColValues = computed(() => Array.from(grouped.value.colValuesSet).sort((a, b) => colLabel(a).localeCompare(colLabel(b))));

const pivotRows = computed(() => {
  const { rowRecordIds, rowLabelParts } = grouped.value;
  const rows = Array.from(rowRecordIds.keys()).map(rowKey => {
    const combo = rowLabelParts.get(rowKey)!;
    const labels = combo.map((v, i) => dimLabel(rowDims.value[i], v));
    return { key: rowKey, labels, recordIds: Array.from(rowRecordIds.get(rowKey)!) };
  });
  rows.sort((a, b) => (a.labels[0] || '').localeCompare(b.labels[0] || ''));
  return rows;
});

function cellRecordIdsFor(rowKey: string, colVal: string): number[] {
  return Array.from(grouped.value.cellRecordIds.get(rowKey + ' ' + colVal) || []);
}

function hasCellContent(rowKey: string, colVal: string): boolean {
  return cellRecordIdsFor(rowKey, colVal).length > 0;
}

function aggregateValue(recordIds: number[], field: string, agg?: string): number {
  const vals = recordIds.map(id => Number(recordsById.value[id]?.[field]) || 0);
  if (agg === 'sum' || !agg) return vals.reduce((a, b) => a + b, 0);
  return 0;
}

function listCellSummary(rowKey: string, colVal: string): { label: string; childIds: number[] } {
  const svcIds = cellRecordIdsFor(rowKey, colVal);
  const childField = matrixCell.value.field;
  const childResource = fieldResource(childField);
  const map = childResource ? (optionMaps.value[childResource] || {}) : {};
  const childIds = Array.from(new Set(svcIds.flatMap(id => recordsById.value[id]?.[childField] || [])));
  const labels = childIds.map(cid => map[cid] ?? String(cid));
  const joined = labels.join(', ');
  const label = joined.length > 40 ? `${labels.length} valeur(s)` : (joined || '—');
  return { label, childIds };
}

function cellColor(rowKey: string, colVal: string): string | null {
  if (!colorField.value) return null;
  const svcIds = cellRecordIdsFor(rowKey, colVal);
  if (!svcIds.length) return null;
  const colors = new Set(svcIds.map(id => recordsById.value[id]?.[colorField.value]).filter(Boolean));
  if (colors.size === 0) return null;
  if (colors.size === 1) return Array.from(colors)[0] as string;
  return 'HATCHED';
}

function cellStyle(rowKey: string, colVal: string): Record<string, string> {
  const c = cellColor(rowKey, colVal);
  if (!c || c === 'HATCHED') return {};
  return { backgroundColor: `color-mix(in srgb, ${c} 25%, transparent)` };
}

function toggleCell(rowKey: string, colVal: string) {
  const k = rowKey + ' ' + colVal;
  const next = new Set(selectedCells.value);
  if (next.has(k)) next.delete(k); else next.add(k);
  selectedCells.value = next;
}

function isCellSelected(rowKey: string, colVal: string): boolean {
  return selectedCells.value.has(rowKey + ' ' + colVal);
}

const selectedServiceIds = computed(() => {
  const ids = new Set<number>();
  selectedCells.value.forEach(k => {
    // La clé peut contenir plusieurs ' ' (une par dimension de ligne) : le dernier segment
    // est toujours la valeur de colonne, tout le reste forme la rowKey d'origine.
    const parts = k.split(' ');
    const colVal = parts[parts.length - 1];
    const rowKey = parts.slice(0, -1).join(' ');
    cellRecordIdsFor(rowKey, colVal).forEach(id => ids.add(id));
  });
  return Array.from(ids);
});

const selectedRecords = computed(() => selectedServiceIds.value.map(id => recordsById.value[id]).filter(Boolean));

const availableActions = computed(() => {
  return genericActions.value.filter((a: any) => a.type === 'bulk_api').filter((a: any) => {
    if (!a.condition) return true;
    try {
      const fn = new Function('records', `return ${a.condition}`);
      return !!fn(selectedRecords.value);
    } catch {
      return false;
    }
  });
});

async function runAction(action: any) {
  actionError.value = null;
  actionLoading.value = true;
  try {
    // kwargs (pas args) : make_class_call_endpoint injecte toujours `db` en kwarg quand la
    // signature le porte, un appel positionnel entrerait donc en collision avec lui. `ids` est
    // le nom de paramètre générique attendu par toute action `bulk_api` (voir Service.align_bulk).
    await api.callClassMethod(props.resourceKey, action.id, { kwargs: { ids: selectedServiceIds.value } });
    selectedCells.value = new Set();
    window.dispatchEvent(new CustomEvent('resource:mutated', { detail: { resource_name: props.resourceKey } }));
    window.dispatchEvent(new CustomEvent('resource:mutated', { detail: { resource_name: 'alignments' } }));
    await loadRecords();
  } catch (e: any) {
    actionError.value = e.message || "Échec de l'action.";
  } finally {
    actionLoading.value = false;
  }
}

function openCell(rowKey: string, colVal: string) {
  if (matrixCell.value.type !== 'list') return;
  const svcIds = cellRecordIdsFor(rowKey, colVal);
  cellPopin.value = {
    resourceKey: props.resourceKey,
    ids: svcIds,
    title: fieldLabel(matrixCell.value.field),
    readOnly: false,
    listConfig: {
      disableAdd: true,
      editableInline: true,
      columns: { [matrixCell.value.field]: { visibleByDefault: true } },
    },
  };
}

const neededResources = computed(() => {
  const list = [
    ...rowDims.value.map(d => fieldResource(d.field)),
    matrixField.value ? fieldResource(matrixField.value) : null,
    matrixCell.value.type === 'list' ? fieldResource(matrixCell.value.field) : null,
  ].filter((r): r is string => !!r);
  return Array.from(new Set(list));
});

// resources dynamique (dérivé de la config du pivot) : pas de clé statique possible pour une
// useQuery() dédiée par ressource — queryClient.fetchQuery() partage néanmoins la même entrée de
// cache que le reste de l'app (voir useGenericCache, architecture.md §15.T) sans imposer de
// réactivité complète ici (comportement inchangé : un seul chargement, au montage).
async function loadOptionMaps() {
  const resources = neededResources.value;
  const results = await Promise.all(resources.map(r => queryClient.fetchQuery({ queryKey: genericCacheKey(r), queryFn: () => api.fetchAllGenericItems(r) })));
  const maps: Record<string, Record<number, string>> = {};
  resources.forEach((r, i) => {
    maps[r] = Object.fromEntries((results[i].items || []).map((it: any) => [it.id, it.display_name || it.name || String(it.id)]));
  });
  optionMaps.value = maps;
}

async function loadRecords() {
  const res = await queryClient.fetchQuery({ queryKey: genericCacheKey(props.resourceKey), queryFn: () => api.fetchAllGenericItems(props.resourceKey) });
  records.value = res.items || [];
}

async function loadAll() {
  loading.value = true;
  error.value = null;
  try {
    await Promise.all([loadRecords(), loadOptionMaps()]);
    genericActions.value = await api.fetchGenericActions(props.resourceKey).catch(() => []);
  } catch (e: any) {
    error.value = e.message || 'Erreur lors du chargement du pivot.';
  } finally {
    loading.value = false;
  }
}

onMounted(loadAll);
</script>

<style scoped>
.generic-pivot-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  overflow: hidden;
}

.loader-container {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}
.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-color);
  border-top-color: var(--accent-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

.pivot-error {
  padding: 24px;
  color: var(--accent-danger, #e74c3c);
}

.pivot-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-color);
  background-color: var(--bg-surface);
}
.selection-badge {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}
.pivot-action-error {
  font-size: 13px;
  color: var(--accent-danger, #e74c3c);
}

.table-wrapper {
  flex: 1;
  overflow: auto;
}

.pivot-table {
  border-collapse: collapse;
  width: 100%;
  font-size: 13px;
}

.pivot-table th, .pivot-table td {
  border: 1px solid var(--border-color);
  padding: 8px 12px;
  text-align: left;
  white-space: nowrap;
}

.pivot-table th {
  position: sticky;
  top: 0;
  background-color: var(--bg-surface);
  color: var(--text-secondary);
  font-weight: 600;
  z-index: 1;
}

.pivot-label-cell {
  font-weight: 500;
  color: var(--text-primary);
}

.pivot-measure-cell {
  color: var(--text-secondary);
  text-align: right;
}

.pivot-cell {
  min-width: 90px;
}

.pivot-cell.is-selected {
  outline: 2px solid var(--accent-primary);
  outline-offset: -2px;
}

.pivot-cell.is-hatched {
  background-image: repeating-linear-gradient(45deg, #cccccc55, #cccccc55 6px, #ffffff55 6px, #ffffff55 12px);
}

.pivot-cell-inner {
  display: flex;
  align-items: center;
  gap: 6px;
}

.pivot-cell-checkbox {
  flex-shrink: 0;
  cursor: pointer;
}

.pivot-cell-value {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pivot-cell-list-summary {
  color: var(--text-secondary);
  font-size: 12px;
}

.btn-edit-cell {
  flex-shrink: 0;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 12px;
  padding: 2px 4px;
  border-radius: var(--radius-md);
  line-height: 1;
}
.btn-edit-cell:hover {
  background-color: var(--bg-secondary, rgba(0,0,0,0.06));
}

.pivot-empty {
  text-align: center;
  color: var(--text-muted);
  padding: 24px;
}
</style>
