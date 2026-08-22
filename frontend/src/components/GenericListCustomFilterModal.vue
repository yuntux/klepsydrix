<template>
  <BaseModal :model-value="modelValue" title="Filtre personnalisé" max-width="640px" @update:model-value="$emit('update:modelValue', $event)">
    <div class="custom-filter-modal-body">
      <GenericListDomainGroupEditor :node="tree" :fields="filterableFields" :depth="0" @update:node="tree = $event" />

      <div class="save-block">
        <label class="save-toggle">
          <input type="checkbox" v-model="wantsToSave" />
          Enregistrer ce filtre
        </label>
        <div v-if="wantsToSave" class="save-fields">
          <input
            type="text"
            class="save-name-input"
            placeholder="Nom du filtre"
            v-model="filterName"
          />
          <label class="save-checkbox">
            <input type="checkbox" v-model="isShared" />
            Partagé
          </label>
          <label class="save-checkbox">
            <input type="checkbox" v-model="isAutoApply" />
            Application automatique
          </label>
        </div>
      </div>

      <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
    </div>

    <template #footer>
      <BaseButton variant="secondary" @click="$emit('update:modelValue', false)">Annuler</BaseButton>
      <BaseButton variant="primary" :disabled="tree.children.length === 0 || saving" @click="apply">
        {{ saving ? 'Application...' : 'Appliquer' }}
      </BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
// Popin de construction d'un filtre personnalisé (arbre ET/OU) — voir GenericListFilterPicker.vue
// (bouton "Filtre personnalisé" qui l'ouvre) et utils/domain.ts (format du domaine). "Appliquer"
// applique immédiatement le domaine construit (sans le persister) ; la case "Enregistrer ce filtre"
// persiste en plus un CustomFilter via le CRUD générique (voir models/custom_filter.py côté
// backend, aucune route dédiée nécessaire).
import { ref, computed, watch } from 'vue';
import BaseModal from './BaseModal.vue';
import BaseButton from './BaseButton.vue';
import GenericListDomainGroupEditor from './GenericListDomainGroupEditor.vue';
import * as api from '../services/api';
import { domainTreeToPrefix, prefixToDomainTree, isFieldFilterableInDomain, type DomainGroupNode, type DomainNode } from '../utils/domain';

interface FilterableField {
  key: string;
  label: string;
  type: string;
  options?: Array<{ value: any; label: string }>;
  resource?: string;
  parentField?: string;
}

const props = defineProps<{
  modelValue: boolean;
  resource: string;
  fields: FilterableField[];
  // Domaine de départ (édition d'un filtre déjà appliqué) — vide pour un nouveau filtre.
  initialDomain?: DomainNode;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
  (e: 'apply', domain: DomainNode): void;
  (e: 'saved', record: any): void;
}>();

const filterableFields = computed(() => props.fields.filter(isFieldFilterableInDomain));

const tree = ref<DomainGroupNode>({ connector: '&', children: [] });
const wantsToSave = ref(false);
const filterName = ref('');
const isShared = ref(false);
const isAutoApply = ref(false);
const saving = ref(false);
const errorMessage = ref('');

watch(() => props.modelValue, (open) => {
  if (!open) return;
  try {
    tree.value = prefixToDomainTree(props.initialDomain);
  } catch {
    tree.value = { connector: '&', children: [] };
  }
  if (tree.value.children.length === 0) {
    tree.value = { connector: '&', children: [{ field: filterableFields.value[0]?.key || '', operator: '=', value: '' }] };
  }
  wantsToSave.value = false;
  filterName.value = '';
  isShared.value = false;
  isAutoApply.value = false;
  errorMessage.value = '';
});

async function apply() {
  const domain = domainTreeToPrefix(tree.value);
  errorMessage.value = '';

  if (wantsToSave.value) {
    if (!filterName.value.trim()) {
      errorMessage.value = 'Le nom du filtre est requis pour l\'enregistrer.';
      return;
    }
    saving.value = true;
    try {
      const record = await api.createGenericItem('custom_filters', {
        name: filterName.value.trim(),
        resource: props.resource,
        domain: JSON.stringify(domain),
        is_shared: isShared.value,
        is_auto_apply: isAutoApply.value,
      });
      // Le parent (GenericList.vue::onCustomFilterSaved) coche déjà ce nouveau filtre nommé pour
      // représenter EXACTEMENT ce même domaine — émettre 'apply' en plus dupliquerait l'état en un
      // second indicateur redondant ("filtre personnalisé actif (non enregistré)") à côté du
      // premier, pour un seul et même domaine.
      emit('saved', record);
      saving.value = false;
      emit('update:modelValue', false);
      return;
    } catch (e: any) {
      errorMessage.value = e?.message || 'Échec de l\'enregistrement du filtre.';
      saving.value = false;
      return;
    }
  }

  emit('apply', domain);
  emit('update:modelValue', false);
}
</script>

<style scoped>
.custom-filter-modal-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 120px;
}
.save-block {
  border-top: 1px solid var(--border-color);
  padding-top: 12px;
}
.save-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  cursor: pointer;
}
.save-fields {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
  flex-wrap: wrap;
}
.save-name-input {
  flex: 1;
  min-width: 160px;
  font-size: 13px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background-color: var(--bg-card);
  color: var(--text-primary);
}
.save-checkbox {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
}
.error-message {
  color: var(--accent-danger, #e74c3c);
  font-size: 12px;
  margin: 0;
}
</style>
