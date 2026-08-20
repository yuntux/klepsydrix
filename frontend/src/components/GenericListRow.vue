<template>
  <tr
    class="body-tr"
    :class="{ 'selected-row': ctx.isRowSelected(item.id) }"
    @click="ctx.onRowClick(item, $event)"
    @focusout="ctx.onRowFocusOut(item, $event)"
  >
    <td
      v-if="ctx.isMultiSelectAllowed()"
      class="body-td checkbox-td"
      :class="{ 'column-frozen': ctx.frozenColumnCount() > 0 }"
      :style="{ textAlign: 'center', width: '40px', borderRight: '1px solid var(--border-color)', padding: '0 4px', ...(ctx.frozenColumnCount() > 0 ? { position: 'sticky', left: '0px' } : {}) }"
    >
      <input
        type="checkbox"
        :checked="ctx.isRowSelected(item.id)"
        style="pointer-events: none;"
      />
    </td>
    <td
      v-for="(col, index) in ctx.visibleColumns()"
      :key="col.key"
      class="body-td"
      :class="{
        'has-select': ctx.getFieldDef(col.key)?.type === 'select' || ctx.getFieldDef(col.key)?.type === 'multiselect',
        'column-frozen': ctx.frozenLeftStyle(index),
        'column-frozen-last': ctx.isLastFrozenColumn(index)
      }"
      :style="ctx.frozenLeftStyle(index)"
    >
      <!-- Formatage personnalisé des valeurs (Édition en ligne Airtable) -->
      <slot :name="'col-' + col.key" :item="item">
        <!-- ID est immuable -->
        <span v-if="col.key === 'id'" class="immutable-id">
          {{ item[col.key] }}
        </span>

        <!-- Widget explicite (registre partagé avec GenericForm.vue, voir widgets/registry.ts)
             — toujours prioritaire sur le rendu par type, comme côté formulaire. -->
        <component
          v-else-if="ctx.getWidgetComponent(col.key)"
          :is="ctx.getWidgetComponent(col.key)"
          :modelValue="ctx.rowSource(item)[col.key]"
          :field="ctx.getFieldDef(col.key)"
          :widgetParams="ctx.getFieldDef(col.key)?.widgetParams"
          :disabled="ctx.isColumnReadOnly(col.key, ctx.rowSource(item))"
          :parentRecord="item"
          @update:modelValue="ctx.updateInline(item, col.key, $event)"
        />

        <!-- Booléen (Switch / Checkbox en ligne) -->
        <div v-else-if="ctx.getFieldDef(col.key)?.type === 'boolean' || typeof item[col.key] === 'boolean'" class="inline-checkbox-wrapper">
          <BaseToggle
            :model-value="!!ctx.rowSource(item)[col.key]"
            :disabled="ctx.isColumnReadOnly(col.key, ctx.rowSource(item))"
            @update:model-value="ctx.updateInline(item, col.key, $event)"
          />
        </div>

        <!-- Couleur (Sélecteur premium en ligne avec palette finie et input hex) -->
        <!-- Couleur : composant standard vue3-swatches -->
        <div v-else-if="ctx.getFieldDef(col.key)?.type === 'color'" class="inline-color-swatch-wrapper" :class="{ 'readonly-swatch': ctx.isColumnReadOnly(col.key, ctx.rowSource(item)) }">
          <color-swatch-picker
            :model-value="ctx.rowSource(item)[col.key] || '#3B82F6'"
            @change="ctx.updateInline(item, col.key, $event)"
          />
        </div>

        <SearchableSelect
          v-else-if="ctx.getFieldDef(col.key)?.type === 'select'"
          :model-value="ctx.rowSource(item)[col.key]"
          :options="ctx.getFieldDef(col.key)?.options || []"
          :disabled="ctx.isColumnReadOnly(col.key, ctx.rowSource(item))"
          :required="ctx.isColumnRequired(col.key)"
          :nullable="ctx.getFieldDef(col.key)?.nullable"
          :inline="true"
          @update:model-value="ctx.updateInline(item, col.key, $event)"
        />

        <!-- Relation 1-à-N "possédée" (ex: repartition_ids) : jamais un simple picker
             multiselect (les enregistrements ciblés n'existent pas indépendamment du
             parent) — tags + bouton crayon ouvrant une popin CRUD générique. Widget
             partagé avec GenericForm.vue (widgets/OwnedRelationField.vue), voir
             architecture.md. Persiste lui-même (liveSync) : passe par updateInline
             uniquement pour que le brouillon local (voir rowSource) reste cohérent avec le
             reste de la ligne, pas parce que ce champ a besoin d'être flushé au blur. -->
        <OwnedRelationField
          v-else-if="ctx.getFieldDef(col.key)?.resource && ctx.getFieldDef(col.key)?.parentField"
          :modelValue="ctx.rowSource(item)[col.key]"
          :field="ctx.getFieldDef(col.key)"
          :widgetParams="{ listConfig: ctx.columnListConfig(col.key) }"
          :disabled="ctx.isColumnReadOnly(col.key, ctx.rowSource(item))"
          :parentRecord="item"
          liveSync
          @update:modelValue="ctx.updateInline(item, col.key, $event)"
        />

        <SearchableMultiSelect
          v-else-if="ctx.getFieldDef(col.key)?.type === 'multiselect'"
          :model-value="ctx.rowSource(item)[col.key]"
          :options="ctx.getFieldDef(col.key)?.options || []"
          :itemModeOptions="ctx.getFieldDef(col.key)?.itemModeOptions"
          :disabled="ctx.isColumnReadOnly(col.key, ctx.rowSource(item))"
          :required="ctx.isColumnRequired(col.key)"
          :inline="true"
          @update:model-value="ctx.updateInline(item, col.key, $event)"
        />

        <!-- Durée (minutes en base, affichage/saisie Xh/XhYY — voir DurationInput.vue).
             Avant la branche "Nombre" ci-dessous : sa valeur est aussi un number JS brut,
             le repli typeof de cette dernière l'intercepterait sinon en premier. -->
        <DurationInput
          v-else-if="ctx.getFieldDef(col.key)?.type === 'duration'"
          :modelValue="ctx.rowSource(item)[col.key]"
          :disabled="ctx.isColumnReadOnly(col.key, ctx.rowSource(item))"
          :includeZero="ctx.getFieldDef(col.key)?.durationIncludeZero"
          @update:modelValue="ctx.updateInline(item, col.key, $event)"
        />

        <!-- Nombre -->
        <input
          v-else-if="ctx.getFieldDef(col.key)?.type === 'number' || typeof item[col.key] === 'number'"
          type="number"
          :value="ctx.rowSource(item)[col.key]"
          :min="ctx.getFieldDef(col.key)?.min"
          :max="ctx.getFieldDef(col.key)?.max"
          :step="ctx.getFieldDef(col.key)?.step || '1'"
          :disabled="ctx.isColumnReadOnly(col.key, ctx.rowSource(item))"
          :required="ctx.isColumnRequired(col.key)"
          @change="ctx.updateInline(item, col.key, ($event.target as HTMLInputElement).value !== '' ? Number(($event.target as HTMLInputElement).value) : null)"
          class="inline-input inline-number"
        />

        <!-- Date : même widget que GenericForm.vue (input natif type=date), pour ne pas
             éditer une date en texte libre ici alors que le formulaire propose un vrai
             sélecteur de date. -->
        <input
          v-else-if="ctx.getFieldDef(col.key)?.type === 'date'"
          type="date"
          :value="ctx.rowSource(item)[col.key] || ''"
          :disabled="ctx.isColumnReadOnly(col.key, ctx.rowSource(item))"
          :required="ctx.isColumnRequired(col.key)"
          @change="ctx.updateInline(item, col.key, ($event.target as HTMLInputElement).value)"
          class="inline-input"
        />

        <!-- Champ objet calculé côté serveur (ex: Course.underventilated_resource_ids) :
             jamais un input texte brut sur un objet JS — un résumé compact en lecture
             seule, détail en tooltip. Toujours read-only, aucun widget d'édition générique
             sensé pour un JSON arbitraire. -->
        <div
          v-else-if="ctx.getFieldDef(col.key)?.type === 'json'"
          class="inline-json-summary"
          :title="item[col.key] && Object.keys(item[col.key]).length ? JSON.stringify(item[col.key], null, 2) : ''"
        >{{ item[col.key] && Object.keys(item[col.key]).length ? `${Object.keys(item[col.key]).length} type(s)` : '—' }}</div>

        <!-- Champ binaire (n'importe quel fichier, avec ou sans widget="image") : jamais le
             contenu du fichier dans une cellule de liste — juste un badge de présence, le
             détail/l'édition se fait dans le formulaire (BinaryFileField/ImageField). -->
        <span
          v-else-if="ctx.getFieldDef(col.key)?.type === 'binary'"
          class="inline-binary-badge"
          :title="item[col.key]?.filename || ''"
        >{{ item[col.key]?.data_base64 ? '📎 Fichier' : '—' }}</span>

        <!-- Texte standard (ex: nom, code) -->
        <input
          v-else
          type="text"
          :value="ctx.rowSource(item)[col.key] || ''"
          :disabled="ctx.isColumnReadOnly(col.key, ctx.rowSource(item))"
          :required="ctx.isColumnRequired(col.key)"
          @change="ctx.updateInline(item, col.key, ($event.target as HTMLInputElement).value)"
          class="inline-input"
        />
      </slot>
    </td>
    <td class="body-td actions-td">
      <div class="actions-group">
        <button v-if="!ctx.disableDelete()" class="btn-action btn-delete" @click.stop="ctx.onDeleteItem(item)" title="Supprimer">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
        </button>
      </div>
    </td>
  </tr>
</template>

<script setup lang="ts">
// Ligne de donnée du tableau générique — extraite de GenericList.vue pour être partagée à
// l'identique entre le corps plat existant et le rendu des lignes feuilles en mode regroupé (voir
// GenericListGroupHeaderRow.vue / architecture.md), sans dupliquer la longue chaîne de rendu par
// type de colonne. Tout l'état/les fonctions partagées viennent du contexte injecté depuis
// GenericList.vue (voir genericListRowContext.ts) — jamais dupliqués ici, pour garantir un
// comportement pixel-identique entre ligne groupée et ligne plate (y compris les brouillons
// d'édition en ligne, centralisés dans le parent).
import { inject } from 'vue';
import ColorSwatchPicker from './ColorSwatchPicker.vue';
import DurationInput from './DurationInput.vue';
import SearchableSelect from './SearchableSelect.vue';
import SearchableMultiSelect from './SearchableMultiSelect.vue';
import BaseToggle from './BaseToggle.vue';
import OwnedRelationField from './widgets/OwnedRelationField.vue';
import { GENERIC_LIST_ROW_CONTEXT } from './genericListRowContext';

defineProps<{ item: any }>();

const ctx = inject(GENERIC_LIST_ROW_CONTEXT)!;
</script>

<style scoped>
/* Repris tel quel de GenericList.vue (voir ses commentaires "déplacée dans GenericListRow.vue") —
   ce composant rendait auparavant ces éléments directement dans GenericList.vue ; un style scoped
   Vue ne s'applique qu'aux éléments du template du composant qui le déclare, jamais à ceux rendus
   par un composant enfant (frontière de scope) — d'où le déplacement, pas une simple copie. */
.inline-input:invalid, .inline-select:invalid, .inline-number:invalid {
  border-color: var(--accent-danger) !important;
  background-color: #fef2f2 !important;
  outline: 2px solid #fca5a5 !important;
}

.body-tr {
  border-bottom: 1px solid var(--border-color);
  transition: background-color var(--transition-fast);
  background-color: var(--bg-card);
}

.body-tr:hover {
  background-color: var(--bg-secondary);
}

.body-tr.selected-row {
  background-color: rgba(99, 102, 241, 0.12) !important;
}

.body-tr.selected-row:hover {
  background-color: rgba(99, 102, 241, 0.18) !important;
}

.body-td {
  padding: 0;
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  border-right: 1px solid var(--border-color);
}

.body-td.has-select {
  overflow: visible !important;
}

/* .actions-td dupliquée depuis GenericList.vue (qui la garde pour ses propres combos
   filter-td/footer-total-td) — règle purement visuelle, duplication à faible risque. */
.actions-td {
  width: 40px !important;
  min-width: 40px !important;
  max-width: 40px !important;
  padding: 0 4px !important;
  text-align: center;
  position: sticky;
  right: 0;
  background-color: var(--bg-card);
  backdrop-filter: blur(8px);
  z-index: 9;
  border-left: 1px solid var(--border-color);
}

.actions-group {
  display: flex;
  justify-content: center;
  gap: 8px;
}

.btn-action {
  background: transparent;
  border: none;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  transition: all var(--transition-fast);
}

.btn-action svg {
  width: 16px;
  height: 16px;
}

.btn-delete:hover {
  background-color: rgba(239, 68, 68, 0.15);
  color: var(--accent-danger);
}

.body-td.column-frozen {
  z-index: 9;
  background-color: var(--bg-card);
}

.body-tr:hover .body-td.column-frozen {
  background-color: var(--bg-secondary);
}

.body-tr.selected-row .body-td.column-frozen {
  background-color: rgba(99, 102, 241, 0.12) !important;
}

.body-td.column-frozen-last {
  box-shadow: 2px 0 4px -2px rgba(0, 0, 0, 0.25);
}

.immutable-id {
  color: var(--text-muted);
  font-family: monospace;
  font-weight: 600;
  padding: 6px 10px;
  display: block;
}

.inline-input, .inline-select {
  width: 100%;
  background-color: transparent;
  border: 1px solid transparent;
  color: var(--text-primary);
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  outline: none;
  font-family: var(--font-sans);
  font-size: 13px;
  transition: all var(--transition-fast);
}

.inline-json-summary {
  width: 100%;
  padding: 6px 10px;
  box-sizing: border-box;
  color: var(--text-muted);
  font-style: italic;
  font-size: 13px;
  cursor: help;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.inline-binary-badge {
  display: inline-block;
  width: 100%;
  padding: 6px 10px;
  box-sizing: border-box;
  color: var(--text-muted);
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.inline-input:hover, .inline-select:hover {
  background-color: var(--bg-secondary);
  border-color: var(--border-color);
}

.inline-input:focus, .inline-select:focus {
  background-color: var(--bg-card);
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.15);
}

.inline-input:disabled, .inline-select:disabled {
  background-color: transparent !important;
  border-color: transparent !important;
  color: var(--text-primary) !important;
  cursor: default;
  pointer-events: none;
}

/* Convention comptable : les valeurs numériques calées à droite de leur colonne. */
.inline-number {
  text-align: right;
}

/* Les flèches +/- natives n'ont de sens que pour une valeur éditable — en lecture seule, elles ne
   font qu'ajouter du bruit visuel à côté d'une valeur qu'on ne peut de toute façon pas modifier. */
.inline-number:disabled {
  -moz-appearance: textfield;
}

.inline-number:disabled::-webkit-inner-spin-button,
.inline-number:disabled::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.inline-checkbox-wrapper {
  display: flex;
  align-items: center;
  height: 28px;
  padding: 0 10px;
}

.inline-color-swatch-wrapper {
  padding: 4px 10px;
  display: flex;
  align-items: center;
}

.readonly-swatch {
  pointer-events: none;
  opacity: 0.6;
}
</style>
