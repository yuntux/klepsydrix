<template>
  <button
    v-if="!disabled || hasRecords"
    class="btn-relation-browser"
    :title="disabled ? 'Consulter' : 'Gérer'"
    @click.stop="showModal = true"
  >
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
      <circle cx="11" cy="11" r="8"></circle>
      <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
    </svg>
  </button>

  <GenericListModal
    v-if="showModal"
    :resourceKey="field?.resource"
    :title="field?.label"
    :readOnly="disabled"
    :listConfig="widgetParams?.listConfig"
    :draftItems="draftRows"
    :manageMembership="!disabled"
    @update:draftItems="onDraftChange"
    @close="showModal = false"
  />
</template>

<script setup lang="ts">
// Widget générique "parcourir/gérer une relation" (one2many ou many2many, JAMAIS many2one) : un
// bouton icône loupe ouvrant une popin listant les enregistrements liés (GenericList générique,
// configurable via widgetParams.listConfig). Se déclare explicitement (widget: "relation_browser"),
// contrairement à OwnedRelationField.vue qui se déclenche automatiquement dès que
// field.resource + field.parentField sont présents (relation "possédée").
//
// Différence de fond avec OwnedRelationField : les enregistrements ciblés existent INDÉPENDAMMENT
// du parent (pas de FK retour vers lui) — le "lien" n'est qu'une valeur de champ sur le parent
// (une liste d'ids), exactement comme n'importe quel autre champ. Donc, contrairement à
// OwnedRelationField (qui a besoin d'un mode liveSync=true en liste, la ligne parente existant déjà,
// pour persister directement), ce widget n'a besoin que d'UN SEUL mode, dans tous les contextes :
// hydrater une copie locale (draftRows) à partir de modelValue, puis ne remonter que via
// update:modelValue — jamais de requête faite par la popin elle-même pour lier/délier (voir
// GenericListModal.vue::manageMembership), afin de fonctionner même si le parent n'est pas encore
// enregistré. Éditer un champ propre d'une ligne déjà liée reste une exception : cet enregistrement
// existe indépendamment du parent, son édition persiste donc immédiatement (voir
// GenericListModal.vue::onUpdateItem).
import { computed, ref, watch } from 'vue';
import GenericListModal from '../GenericListModal.vue';
import * as api from '../../services/api';

const props = defineProps<{
  modelValue: any[];
  field?: any;
  widgetParams?: any;
  disabled?: boolean;
  parentRecord?: any;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: any[]): void;
}>();

const showModal = ref(false);
const draftRows = ref<any[]>([]);

// En lecture seule, un champ vide n'a rien à parcourir : la loupe (qui n'ouvrirait qu'une popin
// vide) ne doit alors pas s'afficher. Basé sur modelValue (synchrone) plutôt que draftRows
// (peuplé de façon asynchrone après le fetch d'hydratation, voir plus bas) pour éviter que le
// bouton clignote brièvement à l'affichage le temps que la requête réponde. Pas de repli : quand le
// champ est éditable, la loupe reste toujours affichée pour permettre de lier un premier élément.
const hasRecords = computed(() => Array.isArray(props.modelValue) && props.modelValue.length > 0);

let lastEmittedJson = '';

function emitIds() {
  const ids = draftRows.value.map((r: any) => r.id);
  const json = JSON.stringify(ids);
  if (json === lastEmittedJson) return;
  lastEmittedJson = json;
  emit('update:modelValue', ids);
}

// Hydrate draftRows depuis modelValue (tableau d'ids "à plat") via UNE requête de lecture — même
// principe que OwnedRelationField.vue : lire pour afficher n'a pas le problème du parent pas
// encore créé (les enregistrements ciblés existent indépendamment de lui), seules les mutations de
// membership doivent l'éviter (voir manageMembership). Le garde anti-écho ignore notre propre
// émission (ex: après un lier/délier dans la popin, modelValue nous revient inchangé).
watch(() => props.modelValue, async (val) => {
  const ids = Array.isArray(val) ? val : [];
  const json = JSON.stringify(ids);
  if (json === lastEmittedJson) return;
  if (!props.field?.resource || ids.length === 0) {
    draftRows.value = [];
    return;
  }
  const res = await api.fetchAllGenericItems(props.field.resource, undefined, { ids: ids.join(',') });
  draftRows.value = res.items || [];
}, { immediate: true });

function onDraftChange(rows: any[]) {
  draftRows.value = rows;
  emitIds();
}
</script>

<style scoped>
.btn-relation-browser {
  /* width: 100% + justify-content: center, pas inline-flex : le bouton doit se centrer dans toute
     la largeur de la cellule (body-td n'a pas de padding propre, voir GenericList.vue), quelle que
     soit la largeur de la colonne — inline-flex se contenterait de la taille intrinsèque du bouton,
     collée à gauche par l'alignement par défaut de la cellule. */
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
}

.btn-relation-browser:hover {
  background-color: var(--bg-secondary, rgba(0, 0, 0, 0.06));
  color: var(--text-primary);
}
</style>
