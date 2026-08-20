<template>
  <GenericList
    title=""
    :columns="columns"
    :fields="fields"
    :items="rows"
    :listConfig="listConfig"
    @selection-change="onSelectionChange"
    @update-item="onUpdateItem"
    @add="onAdd"
    @delete="onDelete"
  />
</template>

<script setup lang="ts">
// Widget "aperçu de liste transitoire" (widget: "list_preview") : affiche un tableau de lignes
// déjà en mémoire (modelValue), jamais récupérées depuis /api/generic/{resource} — contrairement
// à tout le reste de GenericList.vue, qui ne fait déjà QUE rendre le tableau `items` qu'on lui
// donne (aucune logique de fetch ne vit dans GenericList.vue lui-même, c'est toujours l'appelant
// qui la porte). Aucun changement structurel n'a donc été nécessaire dans GenericList.vue au-delà
// d'un paramètre générique (listConfig.selectAllLine, voir plus bas) : ce widget est un pur
// enrobage qui adapte modelValue à la prop `items`, et fait passe-plat de `widgetParams.columns`/
// `widgetParams.listConfig` vers les props `columns`/`listConfig` de GenericList — exactement le
// même dictionnaire de config qu'un panneau GenericList classique déclarerait dans ui.json, rien
// de spécifique à un wizard précis n'est codé en dur ici. C'est chaque `__actions__`/wizard_*.py
// appelant (ex: wizard_teacher_assignment.py::proposals, Course.__actions__::compose_course) qui
// porte la configuration réelle des colonnes et du listConfig.
//
// `title=""` (jamais un libellé cosmétique) : GenericList.vue réutilise sa prop `title` comme clé
// de ressource pour chercher les actions de portée liste (`GET /api/generic/{title}/actions`,
// voir son commentaire "props.title EST la clé de ressource") — un list_preview n'a par
// définition AUCUNE ressource propre, donc aucune action de ce genre n'a de sens ici. Une chaîne
// vide laisse ce watch se taire (`if (!resourceKey) return`) au lieu de déclencher un 404 silencieux
// à chaque rendu vers une fausse ressource ("Propositions", valeur historique codée en dur ici).
//
// Sélection multiple (cases à cocher, voir wizard_teacher_assignment.py::proposals) : sert à
// choisir quelles lignes garder plutôt qu'à déclencher une action groupée classique — le widget ne
// force plus lui-même "tout coché par défaut" : c'est listConfig.selectAllLine (déclaré côté
// appelant) qui pilote ce comportement, un paramètre générique de GenericList, pas une bidouille
// propre à ce widget. Décocher une ligne la retire de modelValue, donc de ce que l'étape suivante
// du wizard recevra à sa soumission.
//
// Édition inline (@update-item, voir wizard_grid_settings.py) : symétrique du panneau détail
// (architecture.md §15.E, onUpdateDetailGenericInline) mais sur des lignes TRANSITOIRES — aucun
// appel réseau, l'édition ne fait que remplacer la ligne dans modelValue par son id. C'est ce qui
// permet à un wizard de proposer une GenericList "éditable" (listConfig.editableInline: true) dont
// rien n'est jamais persisté avant sa propre étape de confirmation finale (rpc_apply) : la ressource
// éditée n'est jamais une vraie ressource /api/generic/{resource}, seulement le champ courant.
import { computed } from 'vue';
import GenericList from '../GenericList.vue';
import { useGenericCache } from '../../composables/useGenericCache';

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

const rows = computed(() => props.modelValue || []);
const rawColumns = computed(() => props.widgetParams?.columns || []);

// Résolution générique des options FK d'une colonne qui déclare `resource` sans `options` statique
// (ex: teacher_ids -> resource: "teachers") : GenericList/GenericListRow ne résolvent jamais un
// `resource` dynamiquement elles-mêmes (voir GenericListRow.vue::getFieldDef, toujours des
// `options` déjà résolues en amont) — pour un panneau de ressource classique, c'est App.vue qui le
// fait via fkOptionsCache avant de construire `fields` ; un list_preview n'a pas cette étape (pas de
// ressource propre), donc ce widget générique s'en charge lui-même. Un seul useGenericCache() par
// ressource DISTINCTE référencée, appelé une seule fois à l'initialisation du composant (le tableau
// de colonnes d'un wizard step est fixe pour la durée de vie de ce champ) — respecte les règles
// d'appel des composables de Vue tout en restant piloté par la config plutôt que codé en dur.
const resourcesToResolve: string[] = Array.from(new Set(
  (props.widgetParams?.columns || [])
    .filter((c: any) => c.resource && !c.options)
    .map((c: any) => c.resource as string)
));
const resourceItemsByName: Record<string, ReturnType<typeof useGenericCache>['items']> = {};
for (const resource of resourcesToResolve) {
  resourceItemsByName[resource] = useGenericCache(resource).items;
}

// Même convention de libellé que SearchableSelect.vue/App.vue (fkOptionsCache) : display_name en
// priorité, avec les mêmes replis — cohérent partout où une option FK est affichée dans l'appli.
function optionsForResource(resource: string) {
  return (resourceItemsByName[resource]?.value || []).map((item: any) => ({
    value: item.id,
    label: item.display_name || item.name || item.code || String(item.id),
  }));
}

const columns = computed(() => rawColumns.value.map((c: any) => (
  c.resource && !c.options ? { ...c, options: optionsForResource(c.resource) } : c
)));
// GenericList lit width/label sur `columns` mais widget/type/options/readOnlyExpr sur `fields`
// (deux props distinctes, voir GenericList.vue::getFieldDef) — un list_preview n'a pas de schéma
// OpenAPI dont dériver `fields` séparément (contrairement à un panneau ui.json classique), donc le
// même tableau `widgetParams.columns` (options désormais résolues ci-dessus) sert directement les
// deux : chaque entrée peut porter à la fois les clés de présentation (label, width) ET de
// comportement (widget, widgetParams, readOnlyExpr, options) sans redondance à déclarer côté
// appelant (ex: wizard_grid_settings.py).
const fields = computed(() => columns.value);

const listConfig = computed(() => ({
  ...(props.widgetParams?.listConfig || {}),
  // Ces lignes ne sont jamais un vrai PATCH réseau (voir le commentaire d'en-tête, "aucun appel
  // réseau") : rien ne justifie ici le blur-jusqu'à-la-ligne de GenericList.vue (pensé pour batcher
  // plusieurs cellules en UN SEUL PATCH sur une vraie ressource) — au contraire, il retarde
  // silencieusement applyCrossRowRules ci-dessous jusqu'à ce que l'utilisateur clique en dehors de
  // la ligne éditée. Toujours forcé à true, jamais un passe-plat de widgetParams.listConfig (aucune
  // raison de le désactiver pour CE widget).
  immediateInlineUpdate: true,
  // Seule autre exception au passe-plat : le contrat générique `disabled` de tout widget de champ,
  // sans rapport avec la configuration propre à cette ressource — une vue désactivée ne doit
  // jamais autoriser d'interaction, quel que soit ce que widgetParams.listConfig déclare par
  // ailleurs.
  ...(props.disabled ? { allowMultiSelect: false } : {}),
}));

function onSelectionChange(ids: any[]) {
  const kept = new Set(ids);
  emit('update:modelValue', rows.value.filter((r) => kept.has(r.id)));
}

// GenericList.vue suit chaque ligne éditable par `item.id` (Map d'édition en attente
// `pendingUpdates`, `:key` de la boucle de rendu) — sans id unique par ligne, TOUTES les lignes
// partagent la même clé `undefined` : éditer une ligne recopiait alors son contenu complet sur
// toutes les autres (bug constaté : choisir une matière/un professeur sur la 1re ligne se
// répercutait sur toutes). Les lignes issues d'un champ calculé côté backend (ex:
// Course.composition_mapping) portent déjà un id ; toute ligne ajoutée ici doit continuer la même
// numérotation, jamais en revenir à `undefined`.
function nextRowId(): number {
  const maxId = rows.value.reduce((max: number, r: any) => (typeof r.id === 'number' && r.id > max ? r.id : max), 0);
  return maxId + 1;
}

function onAdd() {
  const blank: Record<string, any> = { id: nextRowId() };
  for (const col of rawColumns.value) {
    blank[col.key] = col.type === 'multiselect' ? [] : null;
  }
  emit('update:modelValue', [...rows.value, blank]);
}

function onDelete(item: any) {
  emit('update:modelValue', rows.value.filter((r) => r.id !== item.id));
}

// Capacité générique symétrique du pré-remplissage déjà fait une fois côté backend à l'ouverture
// du wizard (ex: Course.composition_mapping) : une colonne peut déclarer `prefillFromField` pour
// se faire remplir automatiquement depuis un champ FK frère de LA MÊME ligne dès que celui-ci
// change — ex: la matière depuis la matière préférée du professeur qu'on vient de choisir.
// `onlyIfEmpty` (recommandé) ne remplace jamais une valeur déjà choisie, manuellement ou par un
// pré-remplissage précédent.
function applyPrefills(previous: any, updated: any): any {
  let result = updated;
  for (const col of rawColumns.value) {
    const prefill = col.prefillFromField;
    if (!prefill) continue;
    const newSource = updated[prefill.sourceField];
    if (JSON.stringify(previous?.[prefill.sourceField]) === JSON.stringify(newSource)) continue;
    if (prefill.onlyIfEmpty && result[col.key] !== null && result[col.key] !== undefined) continue;
    const sourceResource = rawColumns.value.find((c: any) => c.key === prefill.sourceField)?.resource;
    const firstId = Array.isArray(newSource) ? newSource[0] : newSource;
    if (firstId == null || !sourceResource) continue;
    const rawItem = (resourceItemsByName[sourceResource]?.value || []).find((i: any) => i.id === firstId);
    const prefillValue = rawItem?.[prefill.sourceItemField];
    if (prefillValue !== null && prefillValue !== undefined) {
      result = { ...result, [col.key]: prefillValue };
    }
  }
  return result;
}

// Correction croisée entre lignes (voir course.py::widgetParams.crossRowExclusiveColumn, ex.
// composition_mapping::division_targets) — seul mécanisme de ce genre dans tout GenericList/
// GenericListRow (architecture volontairement mono-ligne ailleurs, voir readOnlyExpr/parentRecord
// scopés à UNE ligne) : `onUpdateItem` est le seul point qui a déjà `rows.value` complet en main
// juste avant son unique émission. Reste générique (pas de nom de mode/domaine codé en dur) :
// - un même `id` dans la colonne désignée ne peut porter qu'UN SEUL mode à travers tout le
//   tableau — la ligne qu'on vient d'éditer fait foi, ses entrées remplacent silencieusement toute
//   entrée contradictoire (mode différent) du même id sur les autres lignes ;
// - `crossRowMaxRowsByMode` plafonne en plus le nombre de lignes portant un `id` donné pour les
//   modes qui y figurent (au-delà, les lignes les plus anciennes perdent cette entrée) — la ligne
//   éditée n'est jamais celle qu'on retire.
function applyCrossRowRules(enriched: any, allRows: any[]): any[] {
  const columnKey = props.widgetParams?.crossRowExclusiveColumn;
  let rows2 = allRows.map((r) => (r.id === enriched.id ? enriched : r));
  if (!columnKey) return rows2;

  const maxRowsByMode: Record<string, number> = props.widgetParams?.crossRowMaxRowsByMode || {};
  const entries: { id: any; mode: string }[] = enriched[columnKey] || [];

  for (const entry of entries) {
    // Un seul mode par id à travers tout le tableau : retire toute entrée contradictoire ailleurs.
    rows2 = rows2.map((r) => {
      if (r.id === enriched.id) return r;
      const col = r[columnKey];
      if (!Array.isArray(col)) return r;
      const filtered = col.filter((e: any) => !(String(e.id) === String(entry.id) && e.mode !== entry.mode));
      return filtered.length === col.length ? r : { ...r, [columnKey]: filtered };
    });

    // Plafond de lignes pour ce mode (dédoublement : 2 max) — la ligne éditée n'est jamais retirée,
    // les lignes en trop les plus anciennes (ordre du tableau) perdent l'entrée.
    const maxRows = maxRowsByMode[entry.mode];
    if (!maxRows) continue;
    const rowsWithEntry = rows2.filter((r) => (r[columnKey] || []).some((e: any) => String(e.id) === String(entry.id) && e.mode === entry.mode));
    const overflow = rowsWithEntry.filter((r) => r.id !== enriched.id).slice(maxRows - 1);
    if (!overflow.length) continue;
    const overflowIds = new Set(overflow.map((r) => r.id));
    rows2 = rows2.map((r) => (overflowIds.has(r.id)
      ? { ...r, [columnKey]: (r[columnKey] || []).filter((e: any) => !(String(e.id) === String(entry.id) && e.mode === entry.mode)) }
      : r));
  }
  return rows2;
}

function onUpdateItem(updated: any) {
  const previous = rows.value.find((r) => r.id === updated.id);
  const enriched = applyPrefills(previous, updated);
  emit('update:modelValue', applyCrossRowRules(enriched, rows.value));
}
</script>
