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
      <template v-else>
        <!-- Bandeau "lier un élément existant" (voir manageMembership) : uniquement une lecture du
             cache fkOptions déjà chargé (aucune requête), jamais affiché si l'ajout est désactivé ou
             la popin en lecture seule. -->
        <div v-if="showAttachToolbar" class="attach-toolbar">
          <SearchableSelect
            :modelValue="null"
            :options="attachCandidates"
            placeholder="Lier un élément existant..."
            :nullable="false"
            @update:modelValue="onAttachExisting"
          />
        </div>
        <div class="generic-list-modal-list-wrapper">
          <GenericList
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
      </template>
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
import { ref, computed, inject, onMounted, watch } from 'vue';
import BaseModal from './BaseModal.vue';
import GenericList from './GenericList.vue';
import SearchableSelect from './SearchableSelect.vue';
import * as api from '../services/api';
import { useNotificationStore } from '../stores/notifications';

const notificationStore = useNotificationStore();

const props = defineProps<{
  resourceKey: string;
  // Deux modes de filtrage mutuellement exclusifs :
  // - filterField/filterValue : popin "enfant possédé" (ex: repartition_ids) — sert uniquement à
  //   exclure la colonne FK parent de l'édition (voir `fields` ci-dessous) et de préremplissage
  //   pour `onAdd` ; le chargement lui-même passe par `draftItems` (voir plus bas), pas par un
  //   fetch serveur filtré, DÈS QUE `draftItems` est fourni.
  // - ids : liste d'IDs explicite, déjà résolue côté appelant (ex: GenericPivot — une cellule de
  //   pivot peut regrouper plusieurs Service, et ses axes ligne/colonne peuvent être des champs
  //   dérivés non filtrables en SQL comme division_id/mef_id, voir generic.py::related_field) —
  //   voir GenericPivot.vue et le paramètre `ids` de l'endpoint liste générique. Toujours en mode
  //   direct/serveur (jamais de draftItems pour ce mode).
  filterField?: string;
  filterValue?: any;
  ids?: number[];
  // Présence (même à []) => mode "brouillon" : aucun appel API (create/update/delete) n'est fait
  // ici, les lignes sont purement en mémoire, portées par l'appelant (OwnedRelationField.vue) et
  // remontées via `update:draftItems` à chaque ajout/modification/suppression. Utilisé par le
  // widget "relation possédée" d'un formulaire — voir architecture.md section 15.J : un seul
  // écrivain (le formulaire parent, à sa soumission), jamais cette popin en direct.
  draftItems?: any[];
  title?: string;
  readOnly?: boolean;
  // listConfig complet (même structure que celui d'un panneau GenericList classique — columns,
  // editableInline, disableAdd, ...) déclaré dans ui.json sur la colonne _ids déclenchante et
  // transmis tel quel jusqu'ici — voir GenericList.vue::ColumnConfig.listConfig. Facultatif : sans
  // lui, la popin affiche par défaut tous les champs de la ressource enfant.
  listConfig?: Record<string, any>;
  // Widget "relation_browser" (voir widgets/RelationBrowserField.vue, architecture.md section
  // 15.X) : la popin gère elle-même l'appartenance à la relation (lier un enregistrement existant
  // / délier) plutôt que la création/suppression de l'enregistrement cible — n'a de sens qu'avec
  // draftItems (jamais avec ids/filterField en mode direct/serveur). "Supprimer" une ligne devient
  // un simple détachement local (comportement déjà celui de onDelete en mode draftItems, inchangé)
  // ; en revanche éditer un champ propre d'une ligne déjà liée persiste immédiatement (voir
  // onUpdateItem) puisque cet enregistrement existe indépendamment du parent.
  manageMembership?: boolean;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'update:draftItems', value: any[]): void;
}>();

const isDraftMode = computed(() => props.draftItems !== undefined);

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
      durationIncludeZero: prop.durationIncludeZero === true,
    });
  }
  return result;
});

const columns = computed(() =>
  fields.value.map((f: any) => ({
    key: f.key,
    label: f.label,
    width: (f.type === 'number' || f.type === 'duration') ? 100 : 160,
    visible: true
  }))
);

// Valeur "brute" de disableAdd (avant la surcharge manageMembership ci-dessous) : sert à piloter
// l'affichage du bandeau "lier un élément existant" (showAttachToolbar) — le "+" natif de
// GenericList, lui, reste toujours masqué en mode manageMembership (remplacé par ce bandeau).
const rawDisableAdd = computed(() => props.readOnly ? true : !!props.listConfig?.disableAdd);

// Fusionne le listConfig externe (ui.json) avec les valeurs par défaut de la popin ; l'état
// readOnly calculé par le parent (colonne non éditable) prend toujours le dessus, même si le
// listConfig externe autorisait l'ajout/la suppression.
const effectiveListConfig = computed(() => ({
  allowMultiSelect: false,
  ...(props.listConfig || {}),
  editableInline: props.readOnly ? false : (props.listConfig?.editableInline ?? true),
  disableAdd: props.manageMembership ? true : rawDisableAdd.value,
  disableDelete: props.readOnly ? true : !!props.listConfig?.disableDelete,
}));

const showAttachToolbar = computed(() => !!props.manageMembership && !rawDisableAdd.value);

// Options non encore liées, pour le picker "lier un élément existant" — lecture pure du cache déjà
// chargé (voir App.vue::loadFkOptionsForModel), aucune requête déclenchée ici.
const attachCandidates = computed(() => {
  if (!props.manageMembership) return [];
  const linkedIds = new Set(items.value.map((x: any) => x.id));
  return fkOptions(props.resourceKey).filter((o: any) => !linkedIds.has(o.value));
});

const items = ref<any[]>([]);
const loading = ref(false);

// En mode brouillon, `items` n'est qu'un miroir local de `props.draftItems` (source de vérité
// détenue par OwnedRelationField.vue) — jamais rechargé depuis le serveur.
watch(() => props.draftItems, (val) => {
  if (isDraftMode.value) items.value = val || [];
}, { immediate: true });

async function loadItems() {
  if (isDraftMode.value) return;
  loading.value = true;
  try {
    const filters = props.ids ? { ids: props.ids.join(',') } : { [props.filterField as string]: props.filterValue };
    const res = await api.fetchAllGenericItems(props.resourceKey, undefined, filters);
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
  const defaults: Record<string, any> = props.filterField ? { [props.filterField]: props.filterValue } : {};
  fields.value.forEach((f: any) => {
    if (f.default !== undefined) defaults[f.key] = f.default;
  });
  items.value.unshift({ ...defaults, id: 'new_' + Date.now() });
  if (isDraftMode.value) emit('update:draftItems', items.value);
}

// Lier un enregistrement EXISTANT (voir manageMembership) — distinct de onAdd (qui crée une ligne
// vierge, pour les enfants "possédés"). Ne pousse qu'une ligne minimale (id + label déjà connu via
// fkOptions, aucune requête) : les autres champs resteront vides jusqu'à la prochaine ouverture de
// la popin (nouvelle hydratation complète côté RelationBrowserField.vue).
function onAttachExisting(id: any) {
  if (id === null || id === undefined) return;
  if (items.value.some((x: any) => x.id === id)) return;
  const opt = attachCandidates.value.find((o: any) => o.value === id);
  items.value = [{ id, display_name: opt?.label ?? String(id) }, ...items.value];
  emit('update:draftItems', items.value);
}

async function onUpdateItem(item: any) {
  const idx = items.value.findIndex((x: any) => x.id === item.id);

  if (isDraftMode.value && !props.manageMembership) {
    if (idx !== -1) items.value[idx] = item;
    emit('update:draftItems', items.value);
    return;
  }

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
    // manageMembership : le composant appelant (RelationBrowserField.vue) tient sa propre copie
    // hydratée (draftRows) — sans ce report, une édition de champ propre resterait visible
    // uniquement le temps que cette popin reste ouverte, perdue à la fermeture/réouverture.
    if (props.manageMembership) emit('update:draftItems', items.value);
  } catch (err: any) {
    if (idx !== -1 && oldItem && !String(item.id).startsWith('new_')) {
      items.value[idx] = oldItem;
    } else if (idx !== -1) {
      items.value.splice(idx, 1);
    }
    notificationStore.showNotification('error', err.message || 'Échec de l\'enregistrement.');
  }
}

async function onDelete(item: any) {
  if (isDraftMode.value) {
    items.value = items.value.filter((x: any) => x.id !== item.id);
    emit('update:draftItems', items.value);
    return;
  }

  try {
    await api.deleteGenericItem(props.resourceKey, item.id);
    items.value = items.value.filter((x: any) => x.id !== item.id);
    notifyResourceMutated();
  } catch (err: any) {
    // La ligne reste affichée : rien à faire côté état local, l'échec est déjà silencieux là —
    // mais l'utilisateur doit être prévenu (voir onUpdateItem, même correctif).
    notificationStore.showNotification('error', err.message || 'Échec de la suppression.');
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
  display: flex;
  flex-direction: column;
}

.attach-toolbar {
  flex-shrink: 0;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-color);
}

/* GenericList.vue s'appuie sur .generic-list-container { height: 100% } (voir commentaire ci-dessus)
   — nécessite un parent direct à hauteur définie. Sans le bandeau "lier" (showAttachToolbar), ce
   wrapper reste le seul enfant et se comporte comme avant (100% de .generic-list-modal-content) ;
   avec le bandeau, flex:1 lui donne la hauteur restante une fois le bandeau soustrait. */
.generic-list-modal-list-wrapper {
  flex: 1;
  min-height: 0;
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