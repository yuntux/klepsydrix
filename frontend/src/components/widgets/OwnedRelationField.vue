<template>
  <div class="owned-relation-field">
    <div class="owned-relation-tags">
      <span v-for="tag in tags" :key="tag.key" class="tag-badge">
        <span class="tag-label">{{ tag.label }}</span>
      </span>
      <span v-if="tags.length === 0" class="owned-relation-empty">—</span>
    </div>
    <button
      class="btn-edit-related"
      :title="disabled ? 'Consulter' : 'Modifier'"
      @click.stop="showModal = true"
    >{{ disabled ? '👁' : '✏️' }}</button>
  </div>

  <GenericListModal
    v-if="showModal"
    :resourceKey="field?.resource"
    :filterField="field?.parentField"
    :filterValue="parentRecord?.id"
    :title="field?.label"
    :readOnly="disabled"
    :listConfig="widgetParams?.listConfig"
    :draftItems="liveSync ? undefined : draftRows"
    @update:draftItems="onDraftChange"
    @close="showModal = false"
  />
</template>

<script setup lang="ts">
// Widget "relation possédée" (voir generic.py::parentField, architecture.md) : un champ _ids dont
// les enregistrements ciblés n'existent pas indépendamment du parent (ex: ServiceRepartition d'un
// Service) ne doit jamais afficher un picker de sélection classique — ce serait choisir parmi TOUS
// les enregistrements de la ressource, tous parents confondus, et tenter d'en rattacher un
// échouerait côté serveur dès que le modèle interdit de réassigner sa FK parent (voir Partition,
// par exemple). Affiche à la place la liste des enregistrements liés sous forme de tags (même
// habillage visuel que SearchableMultiSelect, pour rester cohérent avec l'affichage des autres
// champs multi-valeurs) + un bouton crayon ouvrant GenericListModal, déjà réutilisé tel quel.
//
// Partagé entre GenericList.vue (colonne d'une liste) et GenericForm.vue/FormLayoutGrid (champ
// d'un formulaire) — déclenché automatiquement dès que field.resource ET field.parentField sont
// présents, PAS via une déclaration `widget` explicite (contrairement au registre de
// widgets/registry.ts) : c'est une détection structurelle du schéma, pas un choix de config.
//
// Deux modes, sélectionnés par `liveSync` :
// - Formulaire (liveSync=false, défaut) : écrivain UNIQUE de la collection — aucun appel API
//   direct pour create/update/delete (c'était le rôle de GenericListModal jusqu'ici). Porte l'état
//   brouillon complet (`draftRows`) et le remonte via `update:modelValue` sous forme de
//   "commandes" à la Odoo (un dict par ligne : {id, ...champs} pour garder/modifier, {...champs}
//   sans id pour créer) — voir CRUDMixin._apply_owned_collection_commands (base.py). Rien n'est
//   persisté avant la soumission du formulaire parent : "Annuler" redevient une vraie annulation,
//   et une ligne peut être ajoutée avant même que le parent existe en base.
// - Liste (liveSync=true, GenericList.vue) : une ligne de liste existe déjà indépendamment de ce
//   widget (pas de "soumission" à différer) — comportement historique conservé, la popin persiste
//   chaque create/update/delete immédiatement (GenericListModal en mode direct/serveur), et ce
//   widget se contente de rafraîchir l'affichage des tags après chaque mutation.
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import GenericListModal from '../GenericListModal.vue';
import * as api from '../../services/api';

const props = defineProps<{
  modelValue: any[];
  field?: any;
  widgetParams?: any;
  disabled?: boolean;
  parentRecord?: any;
  liveSync?: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: any[]): void;
}>();

const showModal = ref(false);
const draftRows = ref<any[]>([]);

// --- Mode formulaire (liveSync=false) ---

// Retire du brouillon ce qui ne doit jamais repartir dans une commande vers le serveur : la FK
// parent (calculée côté serveur à partir de l'id du parent, jamais fournie par le client — voir
// _apply_owned_collection_commands) et display_name (propriété calculée en lecture seule ; la
// renvoyer ferait planter <Enfant>.update() sur un setattr sans setter).
function sanitizeRow(row: any) {
  const clean = { ...row };
  delete clean.display_name;
  if (props.field?.parentField) delete clean[props.field.parentField];
  return clean;
}

let lastEmittedJson = '';

function emitDraft() {
  lastEmittedJson = JSON.stringify(draftRows.value);
  emit('update:modelValue', draftRows.value);
}

// Source de vérité : props.modelValue. Deux formes possibles en entrée :
// - un tableau d'ids "à plat" (lecture serveur initiale, voir generic.py) : les lignes n'ont pas
//   encore leurs champs, il faut les récupérer une fois pour permettre l'édition en popin.
// - un tableau de dicts déjà "riches" : soit notre propre écho (ignoré via lastEmittedJson, pour
//   ne pas re-déclencher un cycle), soit une valeur remise par le formulaire parent (ex: Annuler,
//   qui restaure localModel depuis son instantané initial) — dans ce cas on resynchronise
//   directement le brouillon dessus, sans nouvel appel serveur.
watch(() => props.modelValue, async (val) => {
  if (props.liveSync) return;
  const json = JSON.stringify(val || []);
  if (json === lastEmittedJson) return;
  const arr = Array.isArray(val) ? val : [];
  if (arr.length > 0 && arr.every((x: any) => typeof x === 'number')) {
    if (!props.field?.resource || !props.field?.parentField || !props.parentRecord?.id) {
      draftRows.value = [];
    } else {
      const res = await api.fetchAllGenericItems(props.field.resource, undefined, {
        [props.field.parentField]: props.parentRecord.id,
      });
      draftRows.value = (res.items || []).map(sanitizeRow);
    }
  } else {
    draftRows.value = arr.map(sanitizeRow);
  }
  emitDraft();
}, { immediate: true });

function onDraftChange(rows: any[]) {
  if (props.liveSync) return;
  draftRows.value = rows.map(sanitizeRow);
  emitDraft();
}

// --- Mode liste (liveSync=true) ---

// La popin (GenericListModal, mode direct) persiste ses créations/modifications/suppressions
// immédiatement, sans jamais repasser par ce widget — ce listener est le seul moyen de garder les
// tags affichés ici à jour pendant que le formulaire reste ouvert.
async function onResourceMutated(e: Event) {
  if (!props.liveSync) return;
  const detail = (e as CustomEvent).detail;
  if (!detail || detail.resource_name !== props.field?.resource) return;
  if (!props.parentRecord?.id || !props.field?.parentField) return;
  const res = await api.fetchAllGenericItems(props.field.resource, undefined, {
    [props.field.parentField]: props.parentRecord.id,
  });
  emit('update:modelValue', (res.items || []).map((item: any) => item.id));
}

onMounted(() => { if (props.liveSync) window.addEventListener('resource:mutated', onResourceMutated); });
onUnmounted(() => window.removeEventListener('resource:mutated', onResourceMutated));

// --- Affichage (tags), commun aux deux modes ---

const tags = computed(() => {
  const options = props.field?.options || [];
  if (props.liveSync) {
    const ids = Array.isArray(props.modelValue) ? props.modelValue : [];
    return ids.map((id: any) => {
      const opt = options.find((o: any) => String(o.value) === String(id));
      return { key: id, label: opt ? opt.label : String(id) };
    });
  }
  return draftRows.value.map((row: any, idx: number) => {
    if (typeof row.id === 'number') {
      const opt = options.find((o: any) => String(o.value) === String(row.id));
      return { key: row.id, label: opt ? opt.label : String(row.id) };
    }
    return { key: `new_${idx}`, label: 'Nouveau' };
  });
});
</script>

<style scoped>
.owned-relation-field {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  width: 100%;
}

.owned-relation-tags {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.tag-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background-color: rgba(99, 102, 241, 0.12);
  border: 1px solid rgba(99, 102, 241, 0.2);
  color: var(--accent-primary);
  padding: 2px 8px;
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 500;
  user-select: none;
}

.owned-relation-empty {
  color: var(--text-muted);
  font-style: italic;
  font-size: 13px;
}

.btn-edit-related {
  flex-shrink: 0;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 13px;
  padding: 2px 4px;
  border-radius: var(--radius-md);
  line-height: 1;
}

.btn-edit-related:hover {
  background-color: var(--bg-secondary, rgba(0, 0, 0, 0.06));
}
</style>
