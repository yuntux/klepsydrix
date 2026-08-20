import type { InjectionKey } from 'vue';

// Contexte partagé entre GenericList.vue (racine, propriétaire de tout l'état) et les composants de
// ligne qu'il instancie — GenericListRow.vue (ligne de donnée) et GenericListGroupHeaderRow.vue
// (ligne de groupe récursive, voir architecture.md). Fourni via provide()/inject() plutôt que des
// props transmises à la main à travers chaque niveau de récursion : un futur ajout à cette surface
// commune ne nécessite qu'un seul point de mise à jour (GenericList.vue), jamais chaque composant
// intermédiaire de la récursion — l'endroit le moins testé, sinon le plus facile à oublier.
export interface GenericListRowContext {
  visibleColumns: () => Array<{ key: string; label: string; width?: number }>;
  isMultiSelectAllowed: () => boolean;
  isRowSelected: (id: number | string) => boolean;
  disableDelete: () => boolean;
  getFieldDef: (key: string) => any;
  getWidgetComponent: (key: string) => any;
  isColumnReadOnly: (key: string, item?: any) => boolean;
  isColumnRequired: (key: string) => boolean;
  columnListConfig: (key: string) => any;
  rowSource: (item: any) => any;
  updateInline: (item: any, key: string, value: any) => void;
  onRowFocusOut: (item: any, event: FocusEvent) => void;
  onRowClick: (item: any, event: MouseEvent) => void;
  onDeleteItem: (item: any) => void;
  frozenLeftStyle: (index: number) => { position: 'sticky'; left: string } | undefined;
  isLastFrozenColumn: (index: number) => boolean;
  frozenColumnCount: () => number;
  // Vue arbre parent/enfant (voir ListConfig.treeBy, GenericList.vue) — isTreeMode gate le rendu
  // de la colonne dépli/repli ; treeMetaFor(id) est null pour toute ligne hors mode arbre.
  isTreeMode: () => boolean;
  treeMetaFor: (id: number | string) => { level: number; hasChildren: boolean; expanded: boolean } | null;
  toggleTreeNode: (id: number | string) => void;
}

export const GENERIC_LIST_ROW_CONTEXT: InjectionKey<GenericListRowContext> = Symbol('GenericListRowContext');
