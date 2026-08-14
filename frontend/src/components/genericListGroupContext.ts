import type { InjectionKey } from 'vue';

// Contexte spécifique au regroupement (voir GenericListGroupHeaderRow.vue), fourni séparément de
// GENERIC_LIST_ROW_CONTEXT (genericListRowContext.ts) — ces fonctions n'ont de sens que pour une
// ligne de GROUPE, jamais pour une ligne de donnée (GenericListRow.vue n'en a pas besoin).
export interface GenericListGroupContext {
  isNodeExpanded: (node: any) => boolean;
  toggleNodeExpanded: (node: any) => void;
  // Même prédicat "colonne à totaliser" que columnTotals (voir isSummableColumn dans
  // GenericList.vue) — détermine à la fois quelles colonnes affichent un sous-total ET où s'arrête
  // la cellule fusionnée flèche/libellé/compteur (voir architecture.md).
  isSummableColumn: (key: string) => boolean;
  formatSubtotal: (key: string, value: number) => string | number;
}

export const GENERIC_LIST_GROUP_CONTEXT: InjectionKey<GenericListGroupContext> = Symbol('GenericListGroupContext');
