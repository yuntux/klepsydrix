<template>
  <GenericList
    title="Propositions"
    :columns="columns"
    :fields="fields"
    :items="rows"
    :listConfig="listConfig"
    @selection-change="onSelectionChange"
    @update-item="onUpdateItem"
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
// de spécifique à ce widget n'est codé en dur ici. C'est `wizard_teacher_assignment.py` (le champ
// "proposals" de l'étape de review) qui porte la configuration réelle des colonnes et du
// listConfig, pas ce fichier.
//
// Sert l'étape de review du wizard d'affectation des professeurs (voir
// wizard_teacher_assignment.py, specs/002-yearly-timetabling-core/teacher-assignment-
// proposal.md §8) : chaque ligne est une proposition {id, service_id, teacher_ids, ...}. La
// sélection multiple existante de GenericList (cases à cocher) sert ici à choisir quelles
// propositions garder plutôt qu'à déclencher une action groupée classique — le widget ne force
// plus lui-même "tout coché par défaut" : c'est listConfig.selectAllLine (déclaré côté
// wizard_teacher_assignment.py) qui pilote ce comportement, un paramètre générique de
// GenericList, pas une bidouille propre à ce widget. Décocher une ligne la retire de
// modelValue, donc de ce que rpc_apply recevra à la validation de l'étape.
//
// Édition inline (@update-item, voir wizard_grid_settings.py) : symétrique du panneau détail
// (architecture.md §15.E, onUpdateDetailGenericInline) mais sur des lignes TRANSITOIRES — aucun
// appel réseau, l'édition ne fait que remplacer la ligne dans modelValue par son id. C'est ce qui
// permet à un wizard de proposer une GenericList "éditable" (listConfig.editableInline: true) dont
// rien n'est jamais persisté avant sa propre étape de confirmation finale (rpc_apply) : la ressource
// éditée n'est jamais une vraie ressource /api/generic/{resource}, seulement le champ courant.
import { computed } from 'vue';
import GenericList from '../GenericList.vue';

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
const columns = computed(() => props.widgetParams?.columns || []);
// GenericList lit width/label sur `columns` mais widget/type/options/readOnlyExpr sur `fields`
// (deux props distinctes, voir GenericList.vue::getFieldDef) — un list_preview n'a pas de schéma
// OpenAPI dont dériver `fields` séparément (contrairement à un panneau ui.json classique), donc le
// même tableau `widgetParams.columns` sert directement les deux : chaque entrée peut porter à la
// fois les clés de présentation (label, width) ET de comportement (widget, widgetParams,
// readOnlyExpr, options) sans redondance à déclarer côté appelant (ex: wizard_grid_settings.py).
const fields = computed(() => columns.value);

const listConfig = computed(() => ({
  ...(props.widgetParams?.listConfig || {}),
  // Seule exception au passe-plat : le contrat générique `disabled` de tout widget de champ,
  // sans rapport avec la configuration propre à cette ressource — une vue désactivée ne doit
  // jamais autoriser d'interaction, quel que soit ce que widgetParams.listConfig déclare par
  // ailleurs.
  ...(props.disabled ? { allowMultiSelect: false } : {}),
}));

function onSelectionChange(ids: any[]) {
  const kept = new Set(ids);
  emit('update:modelValue', rows.value.filter((r) => kept.has(r.id)));
}

function onUpdateItem(updated: any) {
  emit('update:modelValue', rows.value.map((r) => (r.id === updated.id ? updated : r)));
}
</script>
