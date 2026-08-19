<template>
  <tr class="group-header-tr" @click="groupCtx.toggleNodeExpanded(node)">
    <!-- Comme Odoo : la flèche/le libellé/le compteur démarrent dans la colonne case-à-cocher (si
         présente) et fusionnent (colspan) toutes les colonnes situées avant la première colonne à
         totaliser — jamais une gouttière dédiée, jamais cantonné à une seule colonne. Fonctionne que
         la multisélection soit active ou non (voir mergeEnd). Colonnes figées : la cellule fusionnée
         est scindée en deux si elle déborde de la zone figée, jamais un seul <td> à moitié sticky
         (voir mergeCells). -->
    <td
      v-for="cell in mergeCells"
      :key="'merge-' + cell.colspan"
      class="body-td group-label-td"
      :class="{ 'column-frozen': cell.frozen, 'column-frozen-last': cell.frozen }"
      :colspan="cell.colspan"
      :style="cell.frozen ? { position: 'sticky', left: '0px' } : undefined"
    >
      <span v-if="cell.showLabel" class="group-label-content" :style="{ paddingLeft: (node.level * 20) + 'px' }">
        <span class="group-toggle-arrow">{{ groupCtx.isNodeExpanded(node) ? '▼' : '▶' }}</span>
        <span class="group-label-text">{{ node.label }}</span>
        <span class="group-count">({{ node.directChildCount }})</span>
      </span>
    </td>

    <!-- À partir de la première colonne à totaliser (incluse), chaque colonne visible redevient sa
         propre cellule : sous-total si numérique et non hideTotal, vide sinon — même offsets de
         colonnes figées que les lignes de donnée (frozenLeftStyle ne dépend que des largeurs de
         <col>, pas du nombre de <td> effectivement rendus avant). -->
    <td
      v-for="(col, index) in trailingColumns"
      :key="col.key"
      class="body-td group-subtotal-td"
      :class="{ 'column-frozen': ctx.frozenLeftStyle(index + firstSummableVisibleIndex), 'column-frozen-last': ctx.isLastFrozenColumn(index + firstSummableVisibleIndex) }"
      :style="ctx.frozenLeftStyle(index + firstSummableVisibleIndex)"
    >
      {{ groupCtx.isSummableColumn(col.key) ? groupCtx.formatSubtotal(col.key, node.subtotals[col.key] || 0) : '' }}
    </td>
    <td class="body-td actions-td"></td>
  </tr>

  <template v-if="groupCtx.isNodeExpanded(node)">
    <!-- Pas le dernier niveau : récursion sur les sous-groupes -->
    <template v-if="node.children">
      <GenericListGroupHeaderRow v-for="child in node.children" :key="child.path" :node="child">
        <!-- @vue-expect-error : composant auto-référencé (récursion), le type de slotProps dépend
             de sa propre inférence — limitation connue de vue-tsc sur ce patron précis, sans
             conséquence à l'exécution (voir forwardedSlotNames ci-dessus). -->
        <template v-for="slotName in forwardedSlotNames" #[slotName]="slotProps" :key="slotName">
          <slot :name="slotName" v-bind="slotProps" />
        </template>
      </GenericListGroupHeaderRow>
    </template>
    <!-- Dernier niveau : lignes feuilles, même composant que le mode plat -->
    <template v-else>
      <GenericListRow v-for="row in node.rows" :key="row.id" :item="row">
        <template v-for="slotName in forwardedSlotNames" #[slotName]="slotProps" :key="slotName">
          <slot :name="slotName" v-bind="slotProps" />
        </template>
      </GenericListRow>
    </template>
  </template>
</template>

<script setup lang="ts">
// Ligne de groupe récursive (voir listConfig.groupBy, architecture.md) — auto-référencée via
// defineOptions ci-dessous. Contexte partagé (colonnes visibles, colonnes figées...) injecté via
// GENERIC_LIST_ROW_CONTEXT (même contexte que GenericListRow.vue) + un second contexte propre au
// regroupement, GENERIC_LIST_GROUP_CONTEXT (isNodeExpanded/toggleNodeExpanded/isSummableColumn).
import { computed, inject, useSlots } from 'vue';
import GenericListRow from './GenericListRow.vue';
import { GENERIC_LIST_ROW_CONTEXT } from './genericListRowContext';
import { GENERIC_LIST_GROUP_CONTEXT } from './genericListGroupContext';

defineOptions({ name: 'GenericListGroupHeaderRow' });

const props = defineProps<{ node: any }>();

// Noms des slots à retransmettre tels quels lors de la récursion (voir template ci-dessous) —
// capturés en string[] plutôt qu'itérés directement sur $slots dans le template : ce composant se
// référençant lui-même récursivement, le type de $slots dépend de sa propre utilisation dans son
// propre template, ce que vue-tsc ne peut pas résoudre (slotProps se retrouve dans son propre
// initializer). Un string[] simple casse ce cycle sans changer le comportement à l'exécution.
// useSlots() appelé une seule fois, de façon synchrone, à l'exécution de setup() — comme requis.
const injectedSlots = useSlots();
const forwardedSlotNames = computed<string[]>(() => Object.keys(injectedSlots));

const ctx = inject(GENERIC_LIST_ROW_CONTEXT)!;
const groupCtx = inject(GENERIC_LIST_GROUP_CONTEXT)!;

// Index (dans visibleColumns) de la première colonne à totaliser — visibleColumns.length si aucune.
const firstSummableVisibleIndex = computed(() => {
  const cols = ctx.visibleColumns();
  const idx = cols.findIndex(col => groupCtx.isSummableColumn(col.key));
  return idx === -1 ? cols.length : idx;
});

const trailingColumns = computed(() => ctx.visibleColumns().slice(firstSummableVisibleIndex.value));

// Borne (en "cellules de ligne", case à cocher comprise si présente) de la zone à fusionner pour la
// flèche/le libellé/le compteur — plancher à 1 colonne minimum (cas limite : la toute première
// colonne visible est elle-même à totaliser, rien à fusionner avant elle hors case à cocher).
const mergeEnd = computed(() => {
  const cellsBeforeData = ctx.isMultiSelectAllowed() ? 1 : 0;
  return Math.max(1, cellsBeforeData + firstSummableVisibleIndex.value);
});

// Borne des cellules figées sur cette ligne — la case à cocher n'est elle-même figée que si
// frozenColumnCount > 0, même convention que le reste du tableau.
const frozenEnd = computed(() => {
  const count = ctx.frozenColumnCount();
  if (count <= 0) return 0;
  const cellsBeforeData = ctx.isMultiSelectAllowed() ? 1 : 0;
  return cellsBeforeData + count;
});

// Une ou deux cellules selon que la zone fusionnée déborde ou non de la partie figée (voir
// architecture.md) — jamais un seul <td colspan> qui chevaucherait la frontière figé/non-figé (un
// <td> ne peut pas être à moitié position:sticky). Le contenu (flèche/libellé/compteur) va toujours
// dans le premier segment (figé s'il y en a un).
const mergeCells = computed(() => {
  const end = mergeEnd.value;
  const frozen = frozenEnd.value;
  if (end <= frozen || frozen === 0) {
    return [{ colspan: end, frozen: frozen > 0, showLabel: true }];
  }
  return [
    { colspan: frozen, frozen: true, showLabel: true },
    { colspan: end - frozen, frozen: false, showLabel: false },
  ];
});
</script>

<style scoped>
/* Base .body-td/.actions-td/.column-frozen* reprise de GenericList.vue (voir ses commentaires
   "déplacée dans GenericListRow.vue / GenericListGroupHeaderRow.vue") — un style scoped Vue ne
   s'applique qu'aux éléments du template du composant qui le déclare ; ce composant rendant
   désormais lui-même ses propres <td class="body-td">/<td class="actions-td">, il a besoin de sa
   propre copie (règles purement visuelles, duplication à faible risque avec GenericListRow.vue). */
.body-td {
  padding: 0;
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  border-right: 1px solid var(--border-color);
}

.body-td.column-frozen {
  z-index: 9;
  background-color: var(--bg-card);
}

.body-td.column-frozen-last {
  box-shadow: 2px 0 4px -2px rgba(0, 0, 0, 0.25);
}

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

.group-header-tr {
  cursor: pointer;
  background-color: var(--bg-surface);
}
.group-header-tr:hover {
  background-color: var(--bg-secondary, rgba(0, 0, 0, 0.04));
}
/* Même padding vertical que .footer-total-td (GenericList.vue) : .body-td repris ci-dessus part
   d'un padding:0 (la hauteur d'une ligne de donnée vient du widget interne — .inline-input,
   .inline-checkbox-wrapper, etc., voir GenericListRow.vue), une ligne de groupe n'a pas ce
   widget interne et retombait donc sur la seule hauteur de ligne du texte, plus basse qu'une
   ligne normale ou que le pied de page — corrigé en portant le padding directement sur la
   cellule, comme le pied de page. */
.group-label-td, .group-subtotal-td {
  padding: 8px 16px;
}
.group-label-content {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--text-primary);
}
.group-toggle-arrow {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--text-secondary);
  width: 12px;
  display: inline-block;
}
.group-count {
  font-weight: 400;
  color: var(--text-secondary);
}
.group-subtotal-td {
  text-align: right;
  font-weight: 600;
  color: var(--text-primary);
}
</style>
