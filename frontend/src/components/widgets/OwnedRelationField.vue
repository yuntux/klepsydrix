<template>
  <div class="owned-relation-field">
    <div class="owned-relation-tags">
      <span v-for="tag in tags" :key="tag.value" class="tag-badge">
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
import { ref, computed } from 'vue';
import GenericListModal from '../GenericListModal.vue';

const props = defineProps<{
  modelValue: any[];
  field?: any;
  widgetParams?: any;
  disabled?: boolean;
  parentRecord?: any;
}>();

const showModal = ref(false);

const tags = computed(() => {
  const ids = Array.isArray(props.modelValue) ? props.modelValue : [];
  const options = props.field?.options || [];
  return ids.map((id: any) => {
    const opt = options.find((o: any) => String(o.value) === String(id));
    return { value: id, label: opt ? opt.label : String(id) };
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
