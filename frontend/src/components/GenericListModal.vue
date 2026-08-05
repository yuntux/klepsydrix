<template>
  <BaseModal
    :model-value="true"
    :title="title || resourceKey"
    max-width="1000px"
    no-padding
    @update:model-value="$emit('close')"
  >
    <div class="generic-list-modal-content">
      <div v-if="loading" class="loader-container">
        <div class="spinner"></div>
      </div>
      <GenericList
        v-else
        :title="resourceKey"
        :columns="columns"
        :fields="fields"
        :items="items"
        :listConfig="effectiveListConfig"
        @add="onAdd"
        @update-item="onUpdateItem"
        @delete="onDelete"
      />
    </div>
  </BaseModal>
</template>

<script setup lang="ts">
// Popin CRUD générique pour éditer les enregistrements "possédés" par une ligne d'une autre
// liste (ex: les ServiceRepartition d'un Service) — déclenchée depuis GenericList.vue quand une
// colonne _ids expose un parentField (voir generic.py, make_pydantic_model). Ne réimplémente rien
// de neuf : réutilise BaseModal + GenericList + les fonctions génériques de services/api.ts, avec
// une dérivation de fields/columns à partir du schéma OpenAPI similaire à celle d'App.vue, mais
// volontairement minimale (pas de gestion des colonnes "time", tri, largeur dynamique... ) puisque
// ces popins affichent typiquement une poignée de lignes.
import { ref, computed, inject, onMounted } from 'vue';
import BaseModal from './BaseModal.vue';
import GenericList from './GenericList.vue';
import * as api from '../services/api';

const props = defineProps<{
  resourceKey: string;
  filterField: string;
  filterValue: any;
  title?: string;
  readOnly?: boolean;
  // listConfig complet (même structure que celui d'un panneau GenericList classique — columns,
  // editableInline, disableAdd, ...) déclaré dans ui.json sur la colonne _ids déclenchante et
  // transmis tel quel jusqu'ici — voir GenericList.vue::ColumnConfig.listConfig. Facultatif : sans
  // lui, la popin affiche par défaut tous les champs de la ressource enfant.
  listConfig?: Record<string, any>;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
}>();

const openApiSpec = inject<any>('openApiSpec', ref(null));
const fkOptionsCache = inject<any>('fkOptionsCache', ref({}));

function fkOptions(resourceName: string): Array<{ value: any; label: string }> {
  return fkOptionsCache.value[resourceName]?.items || [];
}

const fields = computed(() => {
  if (!openApiSpec.value) return [];
  const schema = openApiSpec.value.components?.schemas?.[`${props.resourceKey}_CreatePayload`];
  if (!schema?.properties) return [];
  const requiredFields = schema.required || [];
  const result: any[] = [];

  for (const [key, prop] of Object.entries<any>(schema.properties)) {
    if (key === 'id' || key === 'display_name' || key === props.filterField) continue;

    let baseType = prop.type;
    let resourceName = prop.resource;
    if (!baseType && prop.anyOf) {
      const validOption = prop.anyOf.find((o: any) => o.type && o.type !== 'null');
      if (validOption) baseType = validOption.type;
      const opt = prop.anyOf.find((o: any) => o.resource);
      if (opt) resourceName = opt.resource;
    }

    let fieldType = prop.ui_type || baseType || 'text';
    if (fieldType === 'string') fieldType = 'text';
    else if (fieldType === 'boolean') fieldType = 'boolean';
    else if (fieldType === 'integer' || fieldType === 'number') fieldType = 'number';

    let options = prop.options || undefined;
    if ((fieldType === 'array' || fieldType === 'multiselect') && resourceName) {
      fieldType = 'multiselect';
      options = fkOptions(resourceName);
    } else if (resourceName) {
      if (fieldType !== 'multiselect') fieldType = 'select';
      options = fkOptions(resourceName);
    } else if (options) {
      fieldType = 'select';
    }

    result.push({
      key,
      label: prop.title || key,
      type: fieldType,
      required: requiredFields.includes(key),
      readOnly: props.readOnly || prop.readOnly === true,
      min: prop.min,
      max: prop.max,
      step: prop.step,
      options,
      resource: resourceName,
      default: prop.default,
    });
  }
  return result;
});

const columns = computed(() =>
  fields.value.map((f: any) => ({ key: f.key, label: f.label, width: 160, visible: true }))
);

// Fusionne le listConfig externe (ui.json) avec les valeurs par défaut de la popin ; l'état
// readOnly calculé par le parent (colonne non éditable) prend toujours le dessus, même si le
// listConfig externe autorisait l'ajout/la suppression.
const effectiveListConfig = computed(() => ({
  allowMultiSelect: false,
  ...(props.listConfig || {}),
  editableInline: props.readOnly ? false : (props.listConfig?.editableInline ?? true),
  disableAdd: props.readOnly ? true : !!props.listConfig?.disableAdd,
  disableDelete: props.readOnly ? true : !!props.listConfig?.disableDelete,
}));

const items = ref<any[]>([]);
const loading = ref(false);

async function loadItems() {
  loading.value = true;
  try {
    const res = await api.fetchGenericList(props.resourceKey, 0, 1000, undefined, { [props.filterField]: props.filterValue });
    items.value = res.items || [];
  } finally {
    loading.value = false;
  }
}

onMounted(loadItems);

function notifyResourceMutated() {
  window.dispatchEvent(new CustomEvent('resource:mutated', { detail: { resource_name: props.resourceKey } }));
}

function onAdd() {
  const defaults: Record<string, any> = { [props.filterField]: props.filterValue };
  fields.value.forEach((f: any) => {
    if (f.default !== undefined) defaults[f.key] = f.default;
  });
  items.value.unshift({ ...defaults, id: 'new_' + Date.now() });
}

async function onUpdateItem(item: any) {
  const idx = items.value.findIndex((x: any) => x.id === item.id);
  const oldItem = idx !== -1 ? { ...items.value[idx] } : null;
  if (idx !== -1) items.value[idx] = item;

  try {
    if (String(item.id).startsWith('new_')) {
      const payload = { ...item };
      delete payload.id;
      const created = await api.createGenericItem(props.resourceKey, payload);
      if (idx !== -1) items.value[idx] = created;
    } else {
      await api.updateGenericItem(props.resourceKey, item.id, item);
    }
    notifyResourceMutated();
  } catch (err) {
    if (idx !== -1 && oldItem && !String(item.id).startsWith('new_')) {
      items.value[idx] = oldItem;
    } else if (idx !== -1) {
      items.value.splice(idx, 1);
    }
  }
}

async function onDelete(item: any) {
  try {
    await api.deleteGenericItem(props.resourceKey, item.id);
    items.value = items.value.filter((x: any) => x.id !== item.id);
    notifyResourceMutated();
  } catch (err) {
    // La ligne reste affichée : rien à faire, l'échec est silencieux côté état local.
  }
}
</script>

<style scoped>
/* Hauteur FIXE (pas min-height) pour qu'une liste avec peu de lignes (ex: 2-3
   ServiceRepartition) laisse quand même assez de place à un dropdown ouvert depuis une
   cellule (SearchableSelect, ~220-240px) ou au sélecteur de colonnes de GenericList — sans
   quoi ces dropdowns, en position:absolute, se retrouvent tronqués par l'overflow de la
   popin. GenericList.vue s'appuie sur .generic-list-container { height: 100% } pour que son
   .table-wrapper (flex: 1) s'étire ; une résolution de pourcentage exige une hauteur *définie*
   sur le parent direct, ce qu'un min-height seul (sur un bloc display:block) ne garantit pas
   de façon fiable — d'où le fait que le min-height précédent n'agrandissait que le wrapper,
   pas la liste elle-même. Une `height` fixe résout ce problème ; les lignes en surnombre
   restent gérées par le scroll interne déjà présent sur .table-wrapper (voir architecture.md
   section 15.K).
   */
.generic-list-modal-content {
  height: 420px;
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
</style>
