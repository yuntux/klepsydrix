<template>
  <div class="owned-relation-field">
    <div class="owned-relation-tags">
      <span v-for="tag in tags" :key="tag.key" class="tag-badge" :class="{ 'tag-badge-highlight': tag.highlighted }">
        <span class="tag-label">{{ tag.label }}</span>
      </span>
      <span v-if="tags.length === 0" class="owned-relation-empty">—</span>
    </div>
    <button
      type="button"
      class="btn-edit-related"
      :title="disabled ? 'Consulter' : 'Modifier'"
      @click.stop="showModal = true"
    >{{ disabled ? '👁' : '✏️' }}</button>

    <!-- Imbriqué ici plutôt qu'en racine soeur : une racine UNIQUE pour ce composant (au lieu
         d'un Fragment à deux racines) permet à Vue d'attribuer automatiquement les attributs de
         fallthrough (ex: le `style` de positionnement grille posé par FormLayoutGrid, voir
         GenericForm.vue) sans avertissement "Extraneous non-props attributes". Sans effet visuel :
         GenericListModal -> BaseModal est en position:fixed (.modal-overlay), sa profondeur dans
         l'arbre DOM ne change pas son rendu à l'écran. -->
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
  </div>
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

const props = withDefaults(defineProps<{
  modelValue: any[];
  field?: any;
  widgetParams?: any;
  disabled?: boolean;
  parentRecord?: any;
  liveSync?: boolean;
  // Surlignage générique d'un sous-ensemble de lignes (ex: exigences de salle encore insuffisamment
  // ventilées, voir CoursePopin.vue/Course.underventilated_resource_ids) — teste
  // row[highlightField] contre highlightValues, PAS l'id de la ligne elle-même par défaut (une
  // ligne de groupe non résolue EST la ligne à surligner, voir plan salles §1.5 : sa quantity
  // restante est déjà la quantité manquante, pas besoin de la recalculer).
  highlightField?: string;
  highlightValues?: any[];
}>(), {
  // Le reste du fichier tolérait déjà modelValue=undefined en interne (Array.isArray(...) ? ... :
  // [] aux deux points d'usage, voir plus bas) — mais la prop elle-même restait typée Array sans
  // défaut runtime, d'où l'avertissement Vue "Expected Array, got Undefined" sur un enregistrement
  // tout juste initialisé côté parent (avant que GenericForm.vue::initializeModel() n'ait fini de
  // seeder ses propres défauts, ou pour tout futur appelant qui omettrait ce champ). Un vrai
  // défaut ici couvre le cas à la source, sans dépendre de la synchronisation exacte du parent.
  modelValue: () => [],
});

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

// isHighlighted : teste obj[highlightField] contre highlightValues. En mode liveSync, `obj` est
// l'option (pas la ligne brute, jamais chargée ici) — le champ à tester doit donc être embarqué
// par l'appelant directement dans field.options (ex: {value, label, classroom_id}, voir
// CoursePopin.vue), pas seulement value/label. En mode formulaire, `obj` est la ligne brute
// (draftRows), qui porte déjà tous ses champs.
function isHighlighted(obj: any): boolean {
  if (!props.highlightField || !props.highlightValues?.length || !obj) return false;
  return props.highlightValues.some((v: any) => String(v) === String(obj[props.highlightField!]));
}

const tags = computed(() => {
  const options = props.field?.options || [];
  if (props.liveSync) {
    const ids = Array.isArray(props.modelValue) ? props.modelValue : [];
    return ids.map((id: any) => {
      const opt = options.find((o: any) => String(o.value) === String(id));
      return { key: id, label: opt ? opt.label : String(id), highlighted: isHighlighted(opt) };
    });
  }
  return draftRows.value.map((row: any, idx: number) => {
    if (typeof row.id === 'number') {
      const opt = options.find((o: any) => String(o.value) === String(row.id));
      return { key: row.id, label: opt ? opt.label : String(row.id), highlighted: isHighlighted(row) };
    }
    return { key: `new_${idx}`, label: 'Nouveau', highlighted: false };
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

/* Même habillage que SearchableMultiSelect.vue::.tag-badge-highlight, pour rester cohérent avec
   le surlignage des ressources insuffisamment ventilées ailleurs dans la Fiche T. */
.tag-badge-highlight {
  background-color: rgba(239, 68, 68, 0.15);
  border-color: rgba(239, 68, 68, 0.4);
  color: var(--accent-danger, #dc2626);
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
