<template>
  <div class="domain-group" :class="{ 'is-root': depth === 0 }">
    <div class="domain-group-header">
      <div class="domain-connector-toggle">
        <button
          type="button"
          class="domain-connector-btn"
          :class="{ 'is-active': node.connector === '&' }"
          @click="setConnector('&')"
        >ET</button>
        <button
          type="button"
          class="domain-connector-btn"
          :class="{ 'is-active': node.connector === '|' }"
          @click="setConnector('|')"
        >OU</button>
      </div>
      <div class="domain-group-actions">
        <button type="button" class="domain-add-btn" @click="addCondition">+ Condition</button>
        <button type="button" class="domain-add-btn" @click="addGroup">+ Groupe</button>
        <button v-if="depth > 0" type="button" class="domain-remove-group-btn" title="Supprimer ce groupe" @click="$emit('remove')">✕</button>
      </div>
    </div>

    <div v-if="node.children.length === 0" class="domain-empty">Aucune condition — ajoutez-en une.</div>

    <div v-for="(child, index) in node.children" :key="index" class="domain-child-row">
      <GenericListDomainGroupEditor
        v-if="isDomainGroupNode(child)"
        :node="child"
        :fields="fields"
        :depth="depth + 1"
        @update:node="updateChild(index, $event)"
        @remove="removeChild(index)"
      />
      <div v-else class="domain-condition-row">
        <select class="domain-select domain-field-select" :value="child.field" @change="updateConditionField(index, ($event.target as HTMLSelectElement).value)">
          <option v-for="f in fields" :key="f.key" :value="f.key">{{ f.label }}</option>
        </select>
        <select class="domain-select domain-operator-select" :value="child.operator" @change="updateConditionOperator(index, ($event.target as HTMLSelectElement).value as DomainOperator)">
          <option v-for="op in operatorsFor(child.field)" :key="op" :value="op">{{ operatorLabel(op) }}</option>
        </select>
        <select
          v-if="child.operator === 'in' || child.operator === 'not in'"
          class="domain-select domain-value-input"
          multiple
          :size="Math.min(4, Math.max(2, fieldDef(child.field)?.options?.length || 2))"
          @change="updateConditionValueFromEvent(index, $event, child.field, child.operator)"
        >
          <option
            v-for="opt in fieldDef(child.field)?.options || []"
            :key="opt.value"
            :value="opt.value"
            :selected="Array.isArray(child.value) && child.value.includes(opt.value)"
          >{{ opt.label }}</option>
        </select>
        <select
          v-else-if="fieldDef(child.field)?.type === 'boolean'"
          class="domain-select domain-value-input"
          :value="String(child.value)"
          @change="updateConditionValueFromEvent(index, $event, child.field, child.operator)"
        >
          <option value="true">Oui</option>
          <option value="false">Non</option>
        </select>
        <select
          v-else-if="fieldDef(child.field)?.type === 'select'"
          class="domain-select domain-value-input"
          :value="child.value"
          @change="updateConditionValueFromEvent(index, $event, child.field, child.operator)"
        >
          <option v-for="opt in fieldDef(child.field)?.options || []" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <input
          v-else
          class="domain-value-input"
          :type="fieldDef(child.field)?.type === 'date' ? 'date' : (fieldDef(child.field)?.type === 'number' || fieldDef(child.field)?.type === 'duration') ? 'number' : 'text'"
          :value="child.value ?? ''"
          @change="updateConditionValueFromEvent(index, $event, child.field, child.operator)"
        />
        <button type="button" class="domain-remove-condition-btn" title="Supprimer cette condition" @click="removeChild(index)">✕</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Éditeur récursif d'arbre de domaine ET/OU (voir utils/domain.ts, DomainGroupNode) — un groupe =
// connecteur + enfants (condition ou sous-groupe imbriqué), édité en place via v-model (update:node)
// façon composant de formulaire standard. Monté depuis GenericListCustomFilterModal.vue.
import {
  type DomainGroupNode, type DomainConditionNode, type DomainOperator,
  isDomainGroupNode, operatorsForFieldType,
} from '../utils/domain';

interface FilterableField {
  key: string;
  label: string;
  type: string;
  options?: Array<{ value: any; label: string }>;
}

const props = defineProps<{
  node: DomainGroupNode;
  fields: FilterableField[];
  depth: number;
}>();

const emit = defineEmits<{
  (e: 'update:node', value: DomainGroupNode): void;
  (e: 'remove'): void;
}>();

function fieldDef(key: string): FilterableField | undefined {
  return props.fields.find(f => f.key === key);
}

function operatorsFor(fieldKey: string): DomainOperator[] {
  return operatorsForFieldType(fieldDef(fieldKey)?.type || 'text');
}

const OPERATOR_LABELS: Record<DomainOperator, string> = {
  '=': 'est égal à', '!=': 'est différent de', '>': '>', '<': '<', '>=': '≥', '<=': '≤',
  in: 'fait partie de', 'not in': 'ne fait pas partie de', like: 'contient', ilike: 'contient (insensible à la casse)',
};
function operatorLabel(op: DomainOperator): string {
  return OPERATOR_LABELS[op] || op;
}

function defaultValueFor(field: FilterableField | undefined, operator: DomainOperator): any {
  if (!field) return '';
  if (operator === 'in' || operator === 'not in') return [];
  if (field.type === 'boolean') return true;
  if (field.type === 'select') return field.options?.[0]?.value ?? '';
  if (field.type === 'number' || field.type === 'duration') return 0;
  return '';
}

function defaultCondition(): DomainConditionNode {
  const field = props.fields[0];
  const operator = operatorsForFieldType(field?.type || 'text')[0];
  return { field: field?.key || '', operator, value: defaultValueFor(field, operator) };
}

function setConnector(connector: '&' | '|') {
  emit('update:node', { ...props.node, connector });
}

function addCondition() {
  emit('update:node', { ...props.node, children: [...props.node.children, defaultCondition()] });
}

function addGroup() {
  const group: DomainGroupNode = { connector: '&', children: [defaultCondition()] };
  emit('update:node', { ...props.node, children: [...props.node.children, group] });
}

function updateChild(index: number, child: DomainGroupNode) {
  const children = [...props.node.children];
  children[index] = child;
  emit('update:node', { ...props.node, children });
}

function removeChild(index: number) {
  const children = [...props.node.children];
  children.splice(index, 1);
  emit('update:node', { ...props.node, children });
}

function updateConditionField(index: number, fieldKey: string) {
  const operator = operatorsFor(fieldKey)[0];
  const children = [...props.node.children];
  children[index] = { field: fieldKey, operator, value: defaultValueFor(fieldDef(fieldKey), operator) };
  emit('update:node', { ...props.node, children });
}

function updateConditionOperator(index: number, operator: DomainOperator) {
  const child = props.node.children[index] as DomainConditionNode;
  const children = [...props.node.children];
  const wasMulti = child.operator === 'in' || child.operator === 'not in';
  const isMulti = operator === 'in' || operator === 'not in';
  const value = wasMulti === isMulti ? child.value : defaultValueFor(fieldDef(child.field), operator);
  children[index] = { ...child, operator, value };
  emit('update:node', { ...props.node, children });
}

function updateConditionValue(index: number, value: any) {
  const child = props.node.children[index] as DomainConditionNode;
  const children = [...props.node.children];
  children[index] = { ...child, value };
  emit('update:node', { ...props.node, children });
}

function updateConditionValueFromEvent(index: number, event: Event, fieldKey: string, operator: DomainOperator) {
  const target = event.target as HTMLInputElement | HTMLSelectElement;
  const field = fieldDef(fieldKey);
  if (operator === 'in' || operator === 'not in') {
    const selected = Array.from((target as HTMLSelectElement).selectedOptions).map(o => o.value);
    updateConditionValue(index, field?.type === 'number' ? selected.map(Number) : selected);
    return;
  }
  if (field?.type === 'boolean') {
    updateConditionValue(index, target.value === 'true');
    return;
  }
  if (field?.type === 'number' || field?.type === 'duration') {
    updateConditionValue(index, target.value === '' ? null : Number(target.value));
    return;
  }
  updateConditionValue(index, target.value);
}
</script>

<style scoped>
.domain-group {
  border: 1px dashed var(--border-color);
  border-radius: var(--radius-sm);
  padding: 8px;
  margin: 4px 0;
}
.domain-group.is-root {
  border: none;
  padding: 0;
  margin: 0;
}
.domain-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.domain-connector-toggle {
  display: flex;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.domain-connector-btn {
  padding: 2px 10px;
  font-size: 11px;
  font-weight: 700;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
}
.domain-connector-btn.is-active {
  background-color: var(--accent-primary);
  color: white;
}
.domain-group-actions {
  display: flex;
  gap: 4px;
}
.domain-add-btn {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}
.domain-add-btn:hover {
  background-color: var(--bg-secondary);
}
.domain-remove-group-btn, .domain-remove-condition-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--accent-danger, #e74c3c);
  font-size: 12px;
  padding: 2px 6px;
}
.domain-empty {
  font-size: 12px;
  color: var(--text-muted);
  font-style: italic;
  padding: 4px 0;
}
.domain-child-row {
  margin: 4px 0;
}
.domain-condition-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.domain-select, .domain-value-input {
  font-size: 12px;
  padding: 3px 6px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background-color: var(--bg-card);
  color: var(--text-primary);
}
.domain-field-select {
  flex: 1.2;
  min-width: 0;
}
.domain-operator-select {
  flex: 1;
  min-width: 0;
}
.domain-value-input {
  flex: 1.2;
  min-width: 0;
}
</style>
