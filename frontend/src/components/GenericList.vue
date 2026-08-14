<template>
  <div class="generic-list-container">
    <!-- Conteneur de table avec scroll -->
    <div class="table-wrapper" ref="tableWrapperRef" @scroll="onScroll">
      <table class="premium-table" :style="{ minWidth: totalTableWidth + 'px' }">
        <!-- table-layout: fixed résout normalement les largeurs de colonnes à partir des cellules de
             la PREMIÈRE ligne — avec un en-tête à sur-en-têtes (plusieurs <tr>, rowspan/colspan
             mêlés, voir headerRows), cette résolution devient peu fiable : une colonne étroite
             "cachée" dans un colspan de la ligne 0 peut se retrouver bien plus large que sa largeur
             déclarée (constaté : une colonne à width:32px rendue à ~87px). Un <colgroup> est la
             seule source de largeur que l'algorithme "fixed" consulte AVANT toute ligne, quelle que
             soit la structure de l'en-tête — la solution normale pour ce cas, pas un contournement. -->
        <colgroup>
          <col v-if="isMultiSelectAllowed" style="width: 40px;" />
          <col v-for="col in visibleColumns" :key="'colgroup-' + col.key" :style="{ width: (col.width || 150) + 'px' }" />
          <col style="width: 40px;" />
        </colgroup>
        <thead>
          <!-- En-tête(s) : une ligne par profondeur de sur-en-tête (voir listConfig.columnGroups /
               headerRows) — une seule ligne, comportement inchangé, quand aucun groupe n'est déclaré. -->
          <tr
            v-for="(row, rowIdx) in headerRows"
            :key="'header-row-' + rowIdx"
            class="header-tr"
          >
            <template v-for="cell in row" :key="cell.kind === 'group' ? cell.key : cell.kind === 'column' ? 'col-' + cell.column.key : cell.kind">
              <!-- Case à cocher de sélection groupée (toujours ligne 0, étirée sur toute la hauteur de l'en-tête) -->
              <th
                v-if="cell.kind === 'checkbox'"
                class="header-th checkbox-th"
                :class="{ 'column-frozen': frozenColumnCount > 0 }"
                :rowspan="cell.rowspan"
                :style="{ width: '40px', textAlign: 'center', padding: '8px 4px', ...(frozenColumnCount > 0 ? { position: 'sticky', left: '0px' } : {}) }"
              >
                <input
                  type="checkbox"
                  :checked="isAllSelected"
                  :ref="(el) => { selectAllCheckbox = el as HTMLInputElement | null }"
                  @change="toggleSelectAll(($event.target as HTMLInputElement).checked)"
                />
              </th>

              <!-- Cellule de sur-en-tête (regroupement thématique, non interactive) -->
              <th v-else-if="cell.kind === 'group'" class="header-th header-group-th" :colspan="cell.colspan">
                <span class="th-label">{{ cell.label }}</span>
              </th>

              <!-- Cellule de colonne réelle : tri, redimension, glisser-déposer (désactivé si
                   columnGroupsActive), positionnée à la ligne correspondant à la profondeur de son
                   chemin de groupe et étirée jusqu'en bas via rowspan -->
              <th
                v-else-if="cell.kind === 'column'"
                :style="{ width: cell.column.width ? cell.column.width + 'px' : 'auto', ...(frozenLeftStyle(cell.index) || {}) }"
                class="header-th"
                :class="{ 'column-frozen': frozenLeftStyle(cell.index), 'column-frozen-last': isLastFrozenColumn(cell.index) }"
                :rowspan="cell.rowspan"
                :draggable="!columnGroupsActive"
                @dragstart="onDragStart($event, cell.index)"
                @dragover.prevent="onDragOver($event, cell.index)"
                @drop="onDrop($event, cell.index)"
              >
                <!-- En-tête cliquable pour le tri (sauf si isColumnSortable renvoie false — voir
                     FormField.sortable / ColumnConfig.sortable) -->
                <div
                  class="th-content"
                  :class="{ 'th-content-not-sortable': !isColumnSortable(cell.column.key) }"
                  @click="toggleSort(cell.column.key)"
                >
                  <span class="th-label">{{ cell.column.label }}</span>
                  <span v-if="cell.column.help" class="help-tooltip-wrapper" @click.stop>
                    <span class="help-icon">?</span>
                    <span class="help-tooltip tooltip-bottom" v-html="renderMarkdown(cell.column.help)"></span>
                  </span>
                  <!-- Pas de placeholder ↕ tant que la colonne n'est pas triée : inutile de
                       réserver sa place, le libellé profite de l'espace libéré (la largeur de la
                       colonne, elle, reste calculée comme avant — voir App.vue::buildColumnsConfig,
                       qui prévoit déjà une marge pour cet indicateur qu'il soit affiché ou non). -->
                  <span class="sort-indicator" v-if="sortBy === cell.column.key">
                    {{ sortDesc ? '▼' : '▲' }}
                  </span>
                </div>

                <!-- Poignée de redimensionnement manuel -->
                <div
                  class="resize-handle"
                  @mousedown.stop.prevent="startResize($event, cell.column.key)"
                ></div>
              </th>

              <!-- Colonne Actions / sélecteur de colonnes (toujours ligne 0, étirée sur toute la
                   hauteur de l'en-tête) -->
              <th v-else-if="cell.kind === 'actions'" class="header-th actions-th" :rowspan="cell.rowspan">
                <div class="actions-header-wrapper" style="justify-content: center;">

                  <!-- Sélecteur de colonnes (déplacé dans l'en-tête Action) -->
                  <div class="column-selector-wrapper" :ref="(el) => { dropdownRef = el as HTMLElement | null }">
                    <button class="btn-icon-only-flat" @click.stop="toggleDropdown" title="Gérer les colonnes">
                      <svg xmlns="http://www.w3.org/2000/svg" class="icon-columns-settings" fill="none" viewBox="0 0 24 24" stroke="currentColor" width="16" height="16">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                      </svg>
                    </button>

                    <div v-if="showDropdown" class="column-dropdown glass-morphism">
                      <div class="dropdown-header">Affichage des colonnes</div>
                      <div class="dropdown-list">
                        <label v-for="col in internalColumns" :key="col.key" class="dropdown-item">
                          <input
                            type="checkbox"
                            :checked="col.visible"
                            @change="toggleColumnVisibility(col.key)"
                          />
                          <span>{{ col.label }}</span>
                        </label>
                      </div>
                    </div>
                  </div>
                </div>
              </th>
            </template>
          </tr>

          <!-- Ligne de filtrage / recherche spécifique par colonne -->
          <tr class="filter-tr">
            <td
              v-if="isMultiSelectAllowed"
              class="filter-td checkbox-filter-td"
              :class="{ 'column-frozen': frozenColumnCount > 0 }"
              :style="{ width: '40px', borderRight: '1px solid var(--border-color)', padding: '6px 4px', ...(frozenColumnCount > 0 ? { position: 'sticky', left: '0px' } : {}) }"
            ></td>
            <td
              v-for="(col, index) in visibleColumns"
              :key="'filter-' + col.key"
              class="filter-td"
              :class="{ 'column-frozen': frozenLeftStyle(index), 'column-frozen-last': isLastFrozenColumn(index) }"
              :style="frozenLeftStyle(index)"
            >
              <!-- Pas de zone de saisie si isColumnFilterable renvoie false (voir
                   FormField.filterable / ColumnConfig.filterable) — la cellule reste vide, la
                   colonne du dessus garde son alignement. -->
              <template v-if="isColumnFilterable(col.key)">
                <!-- Si c'est un champ couleur, on propose le composant swatch -->
                <color-swatch-picker
                  v-if="getFieldDef(col.key)?.type === 'color'"
                  :model-value="filters[col.key] || ''"
                  @change="filters[col.key] = $event"
                />
                <input
                  v-else
                  type="text"
                  :value="filters[col.key] || ''"
                  @input="debouncedUpdateFilter(col.key, ($event.target as HTMLInputElement).value)"
                  :placeholder="'Filtrer...'"
                  class="filter-input"
                />
              </template>
            </td>
            <td class="filter-td actions-td"></td>
          </tr>
        </thead>
        
        <tbody>
          <!-- Espace virtuel haut -->
          <tr v-if="isVirtualMode && virtualPaddingTop > 0">
            <td :colspan="visibleColumns.length + (isMultiSelectAllowed ? 2 : 1)" :style="{ height: virtualPaddingTop + 'px', padding: 0, border: 'none' }"></td>
          </tr>

          <!-- Ligne virtuelle interactive "+ Ajouter une ligne" -->
          <tr v-if="!listConfig?.disableAdd && (!isVirtualMode || virtualStartIndex === 0)" class="add-row-tr" @click="$emit('add')">
            <td :colspan="visibleColumns.length + (isMultiSelectAllowed ? 2 : 1)" class="add-row-td">
              <div class="add-row-wrapper">
                <svg xmlns="http://www.w3.org/2000/svg" class="icon-add" fill="none" viewBox="0 0 24 24" stroke="currentColor" width="14" height="14">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 4v16m8-8H4" />
                </svg>
                <span>Ajouter une ligne...</span>
              </div>
            </td>
          </tr>

          <tr v-if="!isGrouped && displayedItems.length === 0" class="empty-tr">
            <td :colspan="visibleColumns.length + (isMultiSelectAllowed ? 2 : 1)" class="empty-td">
              Aucune donnée à afficher.
            </td>
          </tr>
          <!-- Corps plat (regroupement inactif) : ligne de donnée extraite dans GenericListRow.vue,
               réutilisée à l'identique par le rendu groupé (voir GenericListGroupHeaderRow.vue) —
               contexte partagé par provide()/inject() (genericListRowContext.ts), jamais dupliqué. -->
          <template v-if="!isGrouped">
            <GenericListRow v-for="item in displayedItems" :key="item.id" :item="item">
              <template v-for="(_, slotName) in $slots" #[slotName]="slotProps" :key="slotName">
                <slot :name="slotName" v-bind="slotProps" />
              </template>
            </GenericListRow>
          </template>

          <!-- Corps groupé (voir listConfig.groupBy) : arbre récursif de lignes de groupe, lignes
               feuilles rendues via GenericListRow (même composant, même comportement que ci-dessus). -->
          <template v-else>
            <GenericListGroupHeaderRow v-for="node in pagedGroupTree" :key="node.path" :node="node">
              <template v-for="(_, slotName) in $slots" #[slotName]="slotProps" :key="slotName">
                <slot :name="slotName" v-bind="slotProps" />
              </template>
            </GenericListGroupHeaderRow>
            <tr v-if="pagedGroupTree.length === 0" class="empty-tr">
              <td :colspan="visibleColumns.length + (isMultiSelectAllowed ? 2 : 1)" class="empty-td">
                Aucune donnée à afficher.
              </td>
            </tr>
          </template>

          <!-- Espace virtuel bas -->
          <tr v-if="isVirtualMode && virtualPaddingBottom > 0">
            <td :colspan="visibleColumns.length + (isMultiSelectAllowed ? 2 : 1)" :style="{ height: virtualPaddingBottom + 'px', padding: 0, border: 'none' }"></td>
          </tr>
        </tbody>

        <!-- Ligne de total en pied de tableau (voir listConfig.showColumnTotals) : somme des
             lignes actuellement AFFICHÉES (displayedItems), pas de l'ensemble filtré — toujours en
             lecture seule, aucun binding d'édition contrairement au corps du tableau. Masqué en
             mode groupé (isGrouped) : les sous-totaux par groupe (voir GenericListGroupHeaderRow)
             le rendent redondant et son calcul (displayedItems) devient sans objet. -->
        <tfoot v-if="listConfig?.showColumnTotals && !isGrouped">
          <tr class="footer-total-tr">
            <td
              v-if="isMultiSelectAllowed"
              class="footer-total-td checkbox-td"
              :class="{ 'column-frozen': frozenColumnCount > 0 }"
              :style="{ width: '40px', borderRight: '1px solid var(--border-color)', ...(frozenColumnCount > 0 ? { position: 'sticky', left: '0px' } : {}) }"
            ></td>
            <td
              v-for="(col, index) in visibleColumns"
              :key="'total-' + col.key"
              class="footer-total-td"
              :class="{ 'column-frozen': frozenLeftStyle(index), 'column-frozen-last': isLastFrozenColumn(index) }"
              :style="frozenLeftStyle(index)"
            >
              {{ formatColumnTotal(col.key) }}
            </td>
            <td class="footer-total-td actions-td"></td>
          </tr>
        </tfoot>
      </table>
    </div>

    <!-- Système de Pagination -->
    <div class="list-pagination">
      <div class="pagination-left">
        <span class="toolbar-badge">{{ filteredItems.length }} éléments</span>
        <span v-if="isMultiSelectAllowed && selectedIds.size > 0" class="toolbar-badge selection-badge">
          {{ selectedIds.size }} sélectionné(s)
        </span>
        <GenericListGroupByPicker
          v-if="listConfig?.showGroupByWidget !== false"
          :modelValue="internalGroupBy"
          :candidateFields="groupableFields"
          @update:modelValue="internalGroupBy = $event"
        />
        <label class="per-page-selector">
          Afficher
          <select v-model="perPage" class="select-custom">
            <option :value="10">10</option>
            <option :value="20">20</option>
            <option :value="30">30</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
            <option :value="10000">Tout</option>
          </select>
          par page
        </label>
      </div>
      <div class="pagination-right" v-if="perPage !== 10000">
        <span class="pagination-info">
          Page {{ currentPage }} sur {{ totalPages }}
        </span>
        <div class="pagination-buttons">
          <BaseButton 
            variant="secondary" iconOnly 
            :disabled="currentPage === 1"
            @click="currentPage = 1"
          >
            <template #icon>«</template>
          </BaseButton>
          <BaseButton 
            variant="secondary" iconOnly 
            :disabled="currentPage === 1"
            @click="currentPage--"
          >
            <template #icon>‹</template>
          </BaseButton>
          <BaseButton 
            variant="secondary" iconOnly 
            :disabled="currentPage === totalPages || totalPages === 0"
            @click="currentPage++"
          >
            <template #icon>›</template>
          </BaseButton>
          <BaseButton 
            variant="secondary" iconOnly 
            :disabled="currentPage === totalPages || totalPages === 0"
            @click="currentPage = totalPages"
          >
            <template #icon>»</template>
          </BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted, provide } from 'vue';
import ColorSwatchPicker from './ColorSwatchPicker.vue';
import DurationInput from './DurationInput.vue';
import SearchableSelect from './SearchableSelect.vue';
import SearchableMultiSelect from './SearchableMultiSelect.vue';
import BaseToggle from './BaseToggle.vue';
import BaseButton from './BaseButton.vue';
import OwnedRelationField from './widgets/OwnedRelationField.vue';
import GenericListRow from './GenericListRow.vue';
import GenericListGroupHeaderRow from './GenericListGroupHeaderRow.vue';
import GenericListGroupByPicker from './GenericListGroupByPicker.vue';
import { GENERIC_LIST_ROW_CONTEXT } from './genericListRowContext';
import { GENERIC_LIST_GROUP_CONTEXT } from './genericListGroupContext';
import { getWidgetForContext } from './widgets/registry';
import { formatDurationMinutes } from '../utils/duration';

interface ColumnDef {
  key: string;
  label: string;
  width?: number;
  visible?: boolean;
  help?: string;
}

interface FormField {
  key: string;
  label: string;
  type: 'text' | 'number' | 'boolean' | 'date' | 'select' | 'color' | 'duration' | 'multiselect' | 'json' | 'binary';
  required?: boolean;
  readOnly?: boolean;
  placeholder?: string;
  min?: number;
  max?: number;
  step?: string;
  options?: Array<{ value: any; label: string }>;
  help?: string;
  resource?: string;
  parentField?: string;
  widget?: string;
  widgetParams?: any;
  // false uniquement si déclaré explicitement côté backend (info={"sortable": False}) — triable
  // par défaut, comme aujourd'hui.
  sortable?: boolean;
  // Même principe que sortable ci-dessus, pour la zone de saisie de la ligne de filtrage (voir
  // isColumnFilterable) — false uniquement si déclaré explicitement (info={"filterable": False}).
  filterable?: boolean;
  // Pour un champ type: "duration" dont 0 minute est une valeur valide ("modalité non utilisée") —
  // voir DurationInput.vue::getDurationOptions.
  durationIncludeZero?: boolean;
}

interface ColumnConfig {
  visibleByDefault?: boolean;
  overrideLabel?: string;
  readOnly?: boolean;
  required?: boolean;
  help?: string;
  // Exclut cette colonne de la ligne de total en pied de tableau (voir ListConfig.showColumnTotals)
  // même si elle est numérique — sans effet si showColumnTotals n'est pas activé.
  hideTotal?: boolean;
  // Surcharge, propre à ce panneau, du sortable déclaré côté backend (FormField.sortable) — un clic
  // sur l'en-tête ne déclenche alors pas de tri (voir isColumnSortable/toggleSort). Sans cette clé,
  // c'est le sortable du champ (par défaut true) qui s'applique.
  sortable?: boolean;
  // Même principe, pour la zone de saisie de la ligne de filtrage (voir isColumnFilterable) —
  // surcharge propre à ce panneau du filterable déclaré côté backend (FormField.filterable).
  filterable?: boolean;
  // Pour une colonne _ids représentant une relation possédée (voir generic.py::parentField) :
  // listConfig complet de la popin CRUD ouverte sur la ressource enfant — même structure que le
  // listConfig d'un panneau GenericList classique (columns, editableInline, disableAdd, ...),
  // simplement imbriquée ici plutôt que déclarée à un nouvel endroit. Voir GenericListModal.vue.
  listConfig?: ListConfig;
}

interface ListConfig {
  editableInline?: boolean;
  allowMultiSelect?: boolean;
  disableAdd?: boolean;
  disableDelete?: boolean;
  disableEditModal?: boolean;
  // Affiche une ligne de total en pied de tableau, sommant chaque colonne numérique affichée (voir
  // ColumnConfig.hideTotal pour exclure une colonne précise) — somme sur les lignes actuellement
  // affichées (displayedItems), pas sur l'ensemble filtré.
  showColumnTotals?: boolean;
  // Sur-en-têtes de colonnes (regroupement thématique, imbriqué sur plusieurs niveaux) : une entrée
  // par colonne concernée, du libellé le plus englobant au plus précis. Incompatible avec le
  // réordonnancement des colonnes par glisser-déposer (désactivé automatiquement si non vide) — le
  // sélecteur d'affichage/masquage des colonnes reste, lui, toujours actif.
  columnGroups?: Record<string, string[]>;
  // Fige les N premières colonnes visibles à gauche (façon "volets figés" d'Excel) : au scroll
  // horizontal, elles restent affichées, les autres colonnes défilent "derrière" elles. Fige par
  // POSITION, pas par identité de champ — si l'utilisateur réordonne les colonnes par
  // glisser-déposer, ce sont les nouvelles N premières qui deviennent figées. 0/absent = aucune
  // colonne figée (comportement actuel, inchangé). Voir frozenColumnLeftOffsets/frozenLeftStyle.
  frozenColumns?: number;
  // Regroupement de lignes façon Odoo (voir GROUP_BY_GRANULARITIES / groupTree) : liste ORDONNÉE de
  // clés de champ ("field" ou "field:granularité" pour un champ date, ex "created_at:month") — le
  // premier niveau de nesting est le premier élément. Un champ many2many, one2many "possédé", json
  // ou binary est silencieusement ignoré s'il apparaît ici (voir isFieldGroupable) — ce n'est qu'une
  // valeur INITIALE, l'utilisateur peut la changer en direct via le widget (voir showGroupByWidget),
  // sans jamais muter cette prop (voir internalGroupBy).
  groupBy?: string[];
  // Profondeur de regroupement dépliée par défaut au chargement (0 = tout replié, défaut). Un
  // niveau déjà basculé manuellement par l'utilisateur (voir manuallyToggledPaths) prévaut ensuite
  // sur cette valeur par défaut, jusqu'au prochain changement de groupBy.
  autoExpandLevel?: number;
  // Affiche le widget de sélection des champs de regroupement (voir GenericListGroupByPicker.vue),
  // dans la barre de pagination, à droite du badge de sélection — true par défaut.
  showGroupByWidget?: boolean;
  columns?: Record<string, ColumnConfig>;
}

// Granularités de troncature disponibles pour regrouper par un champ "date" (suffixe
// "field:granularité" dans ListConfig.groupBy, voir GroupByLevel/parseGroupByLevel) — "day" est la
// maille par défaut si omise sur un champ date.
type DateGroupGranularity = 'day' | 'week' | 'month' | 'quarter' | 'year';

// Un niveau de regroupement résolu (une entrée de `internalGroupBy`, dérivée d'une chaîne
// ListConfig.groupBy) — `granularity` n'a de sens que pour un champ FormField.type === 'date'.
interface GroupByLevel {
  key: string;
  granularity?: DateGroupGranularity;
}

function renderMarkdown(md: string | undefined): string {
  if (!md) return '';
  let html = md;
  html = html.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  
  // Echap HTML pour securite
  html = html
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Inline markdown
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  
  // Listes et retours ligne
  const lines = html.split('\n');
  let inList = false;
  const processedLines: string[] = [];
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      const content = trimmed.substring(2);
      if (!inList) {
        inList = true;
        processedLines.push('<ul><li>' + content + '</li>');
      } else {
        processedLines.push('<li>' + content + '</li>');
      }
    } else {
      if (inList) {
        inList = false;
        processedLines.push('</ul>');
      }
      processedLines.push(trimmed + (i < lines.length - 1 && trimmed ? '<br/>' : ''));
    }
  }
  if (inList) {
    processedLines.push('</ul>');
  }
  
  return processedLines.join('\n');
}

const props = defineProps<{
  title: string;
  columns: ColumnDef[];
  items: any[];
  fields?: FormField[];
  listConfig?: ListConfig;
  // Restauration de sélection depuis l'URL (voir architecture.md, "URLs profondes") — appliquée
  // une seule fois dès que `items` se peuple pour cette ressource (voir watch dédié plus bas),
  // puis la sélection redevient un état purement interactif classique.
  initialSelectedIds?: Array<string | number>;
}>();

const emit = defineEmits<{
  (e: 'add'): void;
  (e: 'edit', item: any): void;
  (e: 'delete', item: any): void;
  (e: 'update-item', item: any): void;
  (e: 'row-click', item: any): void;
  (e: 'selection-change', ids: any[]): void;
  // Accusé de réception de initialSelectedIds — voir architecture.md, "URLs profondes". Sans ça,
  // App.vue n'a aucun moyen de savoir quand une sélection restaurée depuis l'URL a été consommée
  // : la même instance de GenericList (réutilisée pour toute ressource affichée dans ce panneau,
  // voir App.vue) recevrait sinon indéfiniment le même initialSelectedIds périmé à chaque
  // changement de ressource suivant, et l'appliquerait à nouveau à tort (bug réel observé : une
  // sélection restaurée sur les Classes se retrouvait réappliquée en changeant d'onglet vers les
  // Enseignants).
  (e: 'initial-selection-applied'): void;
}>();

const isMultiSelectAllowed = computed(() => {
  return props.listConfig?.allowMultiSelect !== false;
});

const isEditableInline = computed(() => {
  return props.listConfig?.editableInline !== false;
});

const totalTableWidth = computed(() => {
  const colsWidth = visibleColumns.value.reduce((acc, col) => acc + (col.width || 150), 0);
  const checkboxWidth = isMultiSelectAllowed.value ? 40 : 0;
  const actionsWidth = 40;
  return colsWidth + checkboxWidth + actionsWidth;
});

// Voir listConfig.frozenColumns.
const frozenColumnCount = computed(() => Math.max(0, props.listConfig?.frozenColumns || 0));

// Offset gauche cumulé (px) de chaque colonne visible qui EST effectivement figée (les
// frozenColumnCount premières) — undefined pour une colonne non figée. Inclut la largeur de la
// case à cocher (si présente) comme point de départ : dès qu'au moins une colonne est figée, la
// case à cocher doit elle aussi rester visible, sans quoi les colonnes figées se retrouveraient
// détachées à droite d'une case à cocher qui a défilé.
const frozenColumnLeftOffsets = computed<(number | undefined)[]>(() => {
  const count = frozenColumnCount.value;
  const offsets: (number | undefined)[] = [];
  let acc = count > 0 && isMultiSelectAllowed.value ? 40 : 0;
  visibleColumns.value.forEach((col, idx) => {
    if (idx < count) {
      offsets.push(acc);
      acc += (col.width || 150);
    } else {
      offsets.push(undefined);
    }
  });
  return offsets;
});

// Style à appliquer à la cellule (th/td) d'index `index` dans visibleColumns si elle est figée,
// undefined sinon — même mécanisme sticky que la colonne Actions, déjà figée à droite (voir
// .actions-th/.actions-td), mais côté gauche et sur un nombre de colonnes variable.
function frozenLeftStyle(index: number): { position: 'sticky'; left: string } | undefined {
  const left = frozenColumnLeftOffsets.value[index];
  return left === undefined ? undefined : { position: 'sticky', left: left + 'px' };
}

function isLastFrozenColumn(index: number): boolean {
  return frozenColumnCount.value > 0 && index === frozenColumnCount.value - 1;
}

function isColumnReadOnly(key: string, item?: any): boolean {
  if (!isEditableInline.value) return true;
  const colConf = props.listConfig?.columns?.[key];
  if (colConf?.readOnly === true) return true;
  if (typeof colConf?.readOnly === 'string' && item) {
    try {
      const fn = new Function('model', `return ${colConf.readOnly}`);
      return !!fn(item);
    } catch (e) {
      console.error("Error evaluating readOnly expression in list", e);
    }
  }
  // Repli sur le readOnly déclaré côté backend (ex: related_field readOnly=True)
  if (getFieldDef(key)?.readOnly === true) return true;
  return false;
}

// Triable par défaut ; false uniquement si explicitement déclaré, soit dans ce panneau
// (listConfig.columns[key].sortable — prioritaire), soit côté backend (info={"sortable": False}).
function isColumnSortable(key: string): boolean {
  const colConf = props.listConfig?.columns?.[key];
  if (colConf?.sortable === false) return false;
  if (colConf?.sortable === true) return true;
  return getFieldDef(key)?.sortable !== false;
}

// Filtrable par défaut ; false uniquement si explicitement déclaré, soit dans ce panneau
// (listConfig.columns[key].filterable — prioritaire), soit côté backend (info={"filterable": False}).
function isColumnFilterable(key: string): boolean {
  const colConf = props.listConfig?.columns?.[key];
  if (colConf?.filterable === false) return false;
  if (colConf?.filterable === true) return true;
  return getFieldDef(key)?.filterable !== false;
}

function isColumnRequired(key: string): boolean {
  const colConf = props.listConfig?.columns?.[key];
  return colConf?.required === true;
}

function onRowClick(item: any, event: MouseEvent) {
  const target = event.target as HTMLElement;

  // Si c'est un clic d'action (boutons, swatches), on ignore pour l'action spécifique
  if (
    target.closest('button') || 
    target.closest('.inline-color-swatch-wrapper') || 
    target.closest('.btn-action')
  ) {
    return;
  }

  const isCheckboxClick = !!target.closest('.checkbox-td');
  const isSelectionShortcut = event.ctrlKey || event.metaKey || event.shiftKey;

  // Si c'est un clic normal sur un input ou un select (hors checkbox-td), on ignore pour laisser l'édition en ligne
  if (!isCheckboxClick && (target.closest('input') || target.closest('select'))) {
    const inputEl = (target.closest('input') || target.closest('select')) as HTMLInputElement | HTMLSelectElement;
    if (inputEl && !inputEl.disabled && !inputEl.readOnly) {
      if (!isSelectionShortcut) {
        return;
      }
    }
  }

  if (!isMultiSelectAllowed.value) {
    selectedIds.value.clear();
    selectedIds.value.add(item.id);
    lastClickedItem.value = item;
    emit('row-click', item);
    return;
  }

  // Si clic sur la checkbox ou sa cellule : 
  // - Clic normal ou Ctrl+Clic : coche/décoche la ligne, mais n'ouvre pas le formulaire d'édition
  // - Shift+Clic : sélectionne la plage de lignes correspondante
  if (isCheckboxClick && isMultiSelectAllowed.value) {
    event.preventDefault();
    if (event.shiftKey) {
      if (lastClickedItem.value) {
        const rangeItems = rangeSelectableItems();
        const idx1 = rangeItems.findIndex(x => x.id === lastClickedItem.value.id);
        const idx2 = rangeItems.findIndex(x => x.id === item.id);
        if (idx1 !== -1 && idx2 !== -1) {
          const start = Math.min(idx1, idx2);
          const end = Math.max(idx1, idx2);
          for (let i = start; i <= end; i++) {
            selectedIds.value.add(rangeItems[i].id);
          }
        } else {
          selectedIds.value.add(item.id);
        }
      } else {
        selectedIds.value.add(item.id);
      }
      lastClickedItem.value = item;
    } else {
      if (selectedIds.value.has(item.id)) {
        selectedIds.value.delete(item.id);
      } else {
        selectedIds.value.add(item.id);
      }
      lastClickedItem.value = item;
    }
    return;
  }

  // EDT Raccourcis page 41 pour le clic hors checkbox
  if ((event.ctrlKey || event.metaKey) && isMultiSelectAllowed.value) {
    event.preventDefault();
    if (selectedIds.value.has(item.id)) {
      selectedIds.value.delete(item.id);
    } else {
      selectedIds.value.add(item.id);
    }
    lastClickedItem.value = item;
    return;
  }

  if (event.shiftKey && isMultiSelectAllowed.value) {
    event.preventDefault();
    if (lastClickedItem.value) {
      const rangeItems = rangeSelectableItems();
      const idx1 = rangeItems.findIndex(x => x.id === lastClickedItem.value.id);
      const idx2 = rangeItems.findIndex(x => x.id === item.id);
      if (idx1 !== -1 && idx2 !== -1) {
        const start = Math.min(idx1, idx2);
        const end = Math.max(idx1, idx2);
        for (let i = start; i <= end; i++) {
          selectedIds.value.add(rangeItems[i].id);
        }
      } else {
        selectedIds.value.add(item.id);
      }
    } else {
      selectedIds.value.add(item.id);
    }
    lastClickedItem.value = item;
    return;
  }

  // Clic normal sur le reste de la ligne -> sélectionne uniquement cette ligne et ouvre le formulaire d'édition
  selectedIds.value.clear();
  selectedIds.value.add(item.id);
  lastClickedItem.value = item;
  emit('row-click', item);
}

function getFieldDef(key: string): FormField | undefined {
  return props.fields?.find(f => f.key === key);
}

function getWidgetComponent(key: string): any {
  return getWidgetForContext(getFieldDef(key)?.widget, 'list');
}

function getDisplayValue(item: any, key: string): string {
  const val = item[key];
  if (val === undefined || val === null) return '';
  const fieldDef = getFieldDef(key);
  if (fieldDef && fieldDef.options) {
    if (Array.isArray(val)) {
      return val
        .map(v => {
          const opt = fieldDef.options?.find(o => String(o.value) === String(v));
          return opt ? opt.label : String(v);
        })
        .join(', ');
    }
    const option = fieldDef.options.find(o => String(o.value) === String(val));
    if (option) return option.label;
  }
  return String(val);
}

// Un champ est regroupable (listConfig.groupBy / GenericListGroupByPicker.vue) sauf s'il est
// many2many (type === 'multiselect'), one2many "possédé" (resource + parentField tous deux
// présents — même détection que la branche OwnedRelationField du template), ou json/binary (aucune
// clé de regroupement stable pour un blob/fichier arbitraire). Tout le reste (text, number,
// boolean, date, color, duration, select simple ou many2one) est regroupable.
function isFieldGroupable(field: FormField): boolean {
  if (field.type === 'multiselect') return false;
  if (field.resource && field.parentField) return false;
  if (field.type === 'json' || field.type === 'binary') return false;
  return true;
}

const GROUP_BY_GRANULARITIES: DateGroupGranularity[] = ['day', 'week', 'month', 'quarter', 'year'];

// Parse une entrée ListConfig.groupBy ("field" ou "field:granularité") en GroupByLevel, en
// ignorant silencieusement une clé de champ inconnue ou non regroupable (voir isFieldGroupable) —
// listConfig.groupBy n'est qu'une valeur initiale, jamais revalidée à la main par l'appelant.
function parseGroupByEntry(entry: string): GroupByLevel | null {
  const [key, granRaw] = entry.split(':');
  const field = getFieldDef(key);
  if (!field || !isFieldGroupable(field)) return null;
  if (field.type !== 'date') return { key };
  const granularity = GROUP_BY_GRANULARITIES.includes(granRaw as DateGroupGranularity)
    ? (granRaw as DateGroupGranularity)
    : 'day';
  return { key, granularity };
}

// reactive() (pas un Map brut) : les lectures via rowSource() dans le template doivent redéclencher
// un rendu quand une édition est mise en brouillon (voir updateInline ci-dessous).
const pendingUpdates = reactive(new Map<string, any>());

// Source de lecture d'une cellule éditable : le brouillon en attente s'il existe, sinon l'item
// lui-même. Nécessaire car `item` peut être un proxy Vue en LECTURE SEULE (ex: items sourcés depuis
// useQuery() côté App.vue, voir son commentaire sur genericListQuery) — le muter en place échoue
// silencieusement (avertissement "Set operation ... failed: target is readonly", sans exception),
// ce qui envoyait jusqu'ici la valeur D'AVANT l'édition au serveur (l'ancien mécanisme mutait
// `item` puis recopiait aussitôt cet `item` non modifié dans pendingUpdates).
function rowSource(item: any): any {
  return pendingUpdates.get(item.id) || item;
}

function updateInline(item: any, key: string, value: any) {
  const current = rowSource(item);
  if (current[key] === value) return;
  pendingUpdates.set(item.id, { ...current, [key]: value });
}

function onRowFocusOut(item: any, event: FocusEvent) {
  const tr = event.currentTarget as HTMLElement;
  if (event.relatedTarget && tr.contains(event.relatedTarget as Node)) {
    return; // Focus is still inside the same row
  }

  if (pendingUpdates.has(item.id)) {
    emit('update-item', pendingUpdates.get(item.id));
    pendingUpdates.delete(item.id);
  }
}

// Palette unifiée de 30 couleurs premium
const colorPalette = [
  '#F87171', '#F97316', '#F59E0B', '#EAB308', '#84CC16', '#22C55E', '#10B981', '#14B8A6', '#06B6D4', '#0EA5E9',
  '#3B82F6', '#6366F1', '#8B5CF6', '#A855F7', '#D946EF', '#EC4899', '#F43F5E', '#6B7280', '#4F46E5', '#059669',
  '#DC2626', '#D97706', '#0891B2', '#2563EB', '#7C3AED', '#DB2777', '#0284C7', '#4B5563', '#9CA3AF', '#374151'
];

function getContrastYIQ(hexcolor: string) {
  if (!hexcolor || hexcolor.length < 6) return '#ffffff';
  const hex = hexcolor.replace('#', '');
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  const yiq = ((r * 299) + (g * 587) + (b * 114)) / 1000;
  return (yiq >= 128) ? '#000000' : '#ffffff';
}

// Largeur par défaut pour un type de colonne intrinsèquement étroit (voir totalTableWidth/
// startResize : sans width explicite, une colonne retombe sur un partage ~150px, beaucoup trop
// large pour un simple nombre ou un bouton d'icône) — seulement un repli, une largeur explicite
// (ui.json ColumnConfig.width, ou déjà posée sur la colonne d'origine) garde toujours priorité.
function defaultColumnWidth(key: string): number | undefined {
  const fieldDef = getFieldDef(key);
  if (!fieldDef) return undefined;
  if (fieldDef.widget === 'relation_browser') return 70;
  if (fieldDef.type === 'number') return 100;
  return undefined;
}

// Gestion des colonnes internes (pour réordonner/redimensionner localement)
const internalColumns = ref<ColumnDef[]>([]);

watch([() => props.columns, () => props.listConfig, () => props.fields], () => {
  if (props.listConfig?.columns) {
    // Si la config spécifie des colonnes précises, on filtre et on réordonne selon la config
    const configKeys = Object.keys(props.listConfig.columns);
    const mapped: ColumnDef[] = [];

    configKeys.forEach(key => {
      const originalCol = props.columns.find(c => c.key === key);
      if (originalCol) {
        const colConf = props.listConfig.columns[key];
        const isVisible = colConf.visibleByDefault !== undefined
          ? colConf.visibleByDefault
          : true;

        const overrideLabel = colConf.overrideLabel || originalCol.label;

        mapped.push({
          ...originalCol,
          label: overrideLabel,
          width: colConf.width || originalCol.width || defaultColumnWidth(key) || undefined,
          visible: isVisible,
          help: colConf.help || originalCol.help
        });
      }
    });

    internalColumns.value = mapped;
  } else {
    // Comportement par défaut (conserver toutes les colonnes d'origine)
    internalColumns.value = props.columns.map(c => {
      return {
        ...c,
        width: c.width || defaultColumnWidth(c.key) || undefined,
        visible: c.visible !== false,
        help: c.help
      };
    });
  }
}, { immediate: true, deep: true });

const visibleColumns = computed(() => {
  return internalColumns.value.filter(c => c.visible);
});

// Candidats du sélecteur de regroupement (GenericListGroupByPicker.vue) : TOUS les champs
// regroupables, y compris ceux dont la colonne n'est pas affichée (candidats = props.fields en
// entier, jamais visibleColumns — demandé explicitement).
const groupableFields = computed(() => (props.fields || []).filter(isFieldGroupable));

// Copie locale mutable de listConfig.groupBy (même patron que internalColumns ci-dessus) : la prop
// n'est qu'une valeur INITIALE, l'utilisateur la change en direct via GenericListGroupByPicker.vue
// sans jamais la muter. Une entrée invalide/non regroupable est silencieusement filtrée (voir
// parseGroupByEntry).
const internalGroupBy = ref<GroupByLevel[]>([]);

watch([() => props.listConfig?.groupBy, () => props.fields], () => {
  internalGroupBy.value = (props.listConfig?.groupBy || [])
    .map(parseGroupByEntry)
    .filter((l): l is GroupByLevel => l !== null);
}, { immediate: true, deep: true });

const isGrouped = computed(() => internalGroupBy.value.length > 0);

// Dropdown colonnes
const showDropdown = ref(false);
const dropdownRef = ref<HTMLElement | null>(null);

function toggleDropdown() {
  showDropdown.value = !showDropdown.value;
}

function toggleColumnVisibility(key: string) {
  const col = internalColumns.value.find(c => c.key === key);
  if (col) {
    col.visible = !col.visible;
  }
}

// Click outside pour fermer le dropdown
function handleClickOutside(event: MouseEvent) {
  if (dropdownRef.value && !dropdownRef.value.contains(event.target as Node)) {
    showDropdown.value = false;
  }
}

// Multisélection (Actions groupées & Raccourcis EDT p.41)
const selectedIds = ref<Set<number | string>>(new Set());
const lastClickedItem = ref<any>(null);
const selectAllCheckbox = ref<HTMLInputElement | null>(null);

watch(selectedIds, (newVal) => {
  emit('selection-change', Array.from(newVal));
}, { deep: true });

// Restauration de sélection depuis l'URL — une seule fois par chargement de ressource (voir
// hasAppliedInitialSelection, réarmé plus bas au changement de `title`). Le `watch(selectedIds)`
// ci-dessus émet ensuite `selection-change` normalement : toute la chaîne en aval (App.vue,
// panneau détail maître/détail, PreferenceGrid, formulaire) réagit exactement comme pour un clic
// utilisateur, sans code spécifique à écrire pour ces cas.
const hasAppliedInitialSelection = ref(false);
watch(() => props.items, (newItems) => {
  if (hasAppliedInitialSelection.value) return;
  if (!props.initialSelectedIds || props.initialSelectedIds.length === 0) return;
  if (!newItems || newItems.length === 0) return;
  const validIds = newItems
    .map(item => item.id)
    .filter(id => props.initialSelectedIds!.some(rid => String(rid) === String(id)));
  hasAppliedInitialSelection.value = true;
  emit('initial-selection-applied');
  if (validIds.length === 0) return;
  // Une vue non multi-sélectionnable ne garde jamais que la première valeur valide, comme pour
  // un simple clic (voir onRowClick) — sans quoi une URL fournissant plusieurs ids sur une liste
  // à sélection unique laisserait un Set incohérent avec ce que l'UI peut normalement produire.
  selectedIds.value = new Set(isMultiSelectAllowed.value ? validIds : validIds.slice(0, 1));
}, { immediate: true });

// Pagination
const currentPage = ref(1);
const perPage = ref(30);

// Filtres
const filters = ref<Record<string, string>>({});
let filterTimeout: any = null;
function debouncedUpdateFilter(key: string, value: string) {
  if (filterTimeout) clearTimeout(filterTimeout);
  filterTimeout = setTimeout(() => {
    filters.value[key] = value;
  }, 300);
}

watch(() => props.columns, () => {
  filters.value = {};
  props.columns.forEach(c => {
    filters.value[c.key] = '';
  });
}, { immediate: true });

// Tri
const sortBy = ref<string | null>(null);
const sortDesc = ref(false);

function toggleSort(key: string) {
  if (!isColumnSortable(key)) return;
  if (sortBy.value === key) {
    if (!sortDesc.value) {
      sortDesc.value = true;
    } else {
      sortBy.value = null;
      sortDesc.value = false;
    }
  } else {
    sortBy.value = key;
    sortDesc.value = false;
  }
}

// Filtrage et Tri
const filteredItems = computed(() => {
  let result = [...props.items];

  // 1. Filtrage
  Object.keys(filters.value).forEach(key => {
    const val = filters.value[key];
    if (val) {
      const lowerVal = val.toLowerCase();
      result = result.filter(item => {
        const displayVal = getDisplayValue(item, key);
        return displayVal.toLowerCase().includes(lowerVal);
      });
    }
  });

  // 2. Tri
  if (sortBy.value) {
    const key = sortBy.value;
    const fieldDef = getFieldDef(key);
    const isSelect = fieldDef && fieldDef.type === 'select';

    result.sort((a, b) => {
      let valA = a[key];
      let valB = b[key];

      if (valA === undefined || valA === null) return 1;
      if (valB === undefined || valB === null) return -1;

      if (isSelect) {
        const displayA = getDisplayValue(a, key);
        const displayB = getDisplayValue(b, key);
        return sortDesc.value 
          ? displayB.localeCompare(displayA)
          : displayA.localeCompare(displayB);
      }

      if (typeof valA === 'string') {
        return sortDesc.value 
          ? valB.localeCompare(valA)
          : valA.localeCompare(valB);
      } else {
        return sortDesc.value 
          ? (valB - valA)
          : (valA - valB);
      }
    });
  }

  return result;
});

// --- Regroupement de lignes (voir listConfig.groupBy / architecture.md) ---

interface GroupNode {
  level: number;
  fieldKey: string;
  rawValue: any;
  label: string;
  // Clé stable identifiant ce nœud à travers les reconstructions de l'arbre (computed re-exécuté à
  // chaque changement de filteredItems, y compris une simple édition en ligne sans rapport avec le
  // regroupement) — JSON.stringify de la liste ordonnée des valeurs BRUTES des ancêtres + celle-ci,
  // jamais des libellés résolus (résolus en asynchrone après montage, voir loadFkOptionsForModel
  // côté App.vue) ni une simple concaténation (collisions possibles entre chaînes différentes).
  path: string;
  // Nombre d'éléments du niveau IMMÉDIATEMENT inférieur — sous-groupes si ce n'est pas le dernier
  // niveau, lignes du bucket sinon. Jamais un total récursif de lignes descendantes.
  directChildCount: number;
  children: GroupNode[] | null; // non-null sauf au dernier niveau de regroupement
  rows: any[] | null;           // non-null seulement au dernier niveau de regroupement
  subtotals: Record<string, number>;
}

const NULL_GROUP_BUCKET_KEY = ' __null__';

function truncateDateForGrouping(iso: string, granularity: DateGroupGranularity): string {
  const d = new Date(iso + 'T00:00:00');
  if (isNaN(d.getTime())) return iso;
  switch (granularity) {
    case 'day':
      return iso;
    case 'week': {
      const dayOffset = (d.getDay() + 6) % 7; // 0 = lundi (semaine ISO)
      const monday = new Date(d);
      monday.setDate(d.getDate() - dayOffset);
      return monday.toISOString().slice(0, 10);
    }
    case 'month':
      return iso.slice(0, 7);
    case 'quarter':
      return `${d.getFullYear()}-T${Math.floor(d.getMonth() / 3) + 1}`;
    case 'year':
      return String(d.getFullYear());
  }
}

const MONTH_LABELS = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];

function formatDateGroupLabel(truncated: string, granularity: DateGroupGranularity): string {
  switch (granularity) {
    case 'day':
      return truncated;
    case 'week':
      return `Semaine du ${truncated}`;
    case 'month': {
      const [y, m] = truncated.split('-');
      return `${MONTH_LABELS[Number(m) - 1] || m} ${y}`;
    }
    case 'quarter':
      return truncated.replace('-T', ' - T');
    case 'year':
      return truncated;
  }
}

// Résout la clé de bucket (regroupe deux valeurs équivalentes ensemble), le libellé affiché et la
// valeur "brute" normalisée (tronquée pour un champ date+granularité, telle quelle sinon) à partir
// de la valeur brute stockée sur la ligne — null/undefined devient toujours un bucket dédié
// "Aucune valeur", dépliable comme n'importe quel autre (jamais exclu du regroupement).
function resolveGroupBucket(level: GroupByLevel, rawValue: any): { bucketKey: string; label: string; value: any } {
  if (rawValue === null || rawValue === undefined) {
    return { bucketKey: NULL_GROUP_BUCKET_KEY, label: 'Aucune valeur', value: null };
  }
  const field = getFieldDef(level.key);
  if (field?.type === 'date' && level.granularity) {
    const truncated = truncateDateForGrouping(String(rawValue), level.granularity);
    return { bucketKey: truncated, label: formatDateGroupLabel(truncated, level.granularity), value: truncated };
  }
  const label = getDisplayValue({ [level.key]: rawValue }, level.key) || String(rawValue);
  return { bucketKey: String(rawValue), label, value: rawValue };
}

interface GroupBucket { value: any; label: string; rows: any[]; }

// Regroupe `rows` par la valeur résolue de `level`, en préservant l'ordre de première apparition
// (cohérent avec le tri global actif, voir filteredItems) puis en plaçant le bucket "Aucune valeur"
// toujours en dernier — les autres, par libellé (cohérent avec un regroupement humainement lisible,
// ex: noms d'établissement, plutôt que par id brut).
function bucketRows(rows: any[], level: GroupByLevel): GroupBucket[] {
  const buckets = new Map<string, GroupBucket>();
  for (const row of rows) {
    const { bucketKey, label, value } = resolveGroupBucket(level, row[level.key]);
    let bucket = buckets.get(bucketKey);
    if (!bucket) {
      bucket = { value, label, rows: [] };
      buckets.set(bucketKey, bucket);
    }
    bucket.rows.push(row);
  }
  return Array.from(buckets.values()).sort((a, b) => {
    if (a.value === null && b.value === null) return 0;
    if (a.value === null) return 1;
    if (b.value === null) return -1;
    return a.label.localeCompare(b.label, undefined, { numeric: true, sensitivity: 'base' });
  });
}

function buildGroupNode(level: number, bucket: GroupBucket, ancestorValues: any[], levels: GroupByLevel[]): GroupNode {
  const currentLevel = levels[level];
  const thisPath = [...ancestorValues, bucket.value];
  const path = JSON.stringify(thisPath);
  const isLastLevel = level === levels.length - 1;
  const subtotals: Record<string, number> = {};
  let children: GroupNode[] | null = null;
  let leafRows: any[] | null = null;
  let directChildCount: number;

  if (isLastLevel) {
    leafRows = bucket.rows;
    directChildCount = bucket.rows.length;
    for (const col of visibleColumns.value) {
      if (!isSummableColumn(col.key)) continue;
      subtotals[col.key] = bucket.rows.reduce((acc, r) => acc + (typeof r[col.key] === 'number' ? r[col.key] : 0), 0);
    }
  } else {
    const childBuckets = bucketRows(bucket.rows, levels[level + 1]);
    children = childBuckets.map(b => buildGroupNode(level + 1, b, thisPath, levels));
    directChildCount = children.length;
    // Bas en haut, un seul passage : somme des subtotals déjà calculés des enfants, jamais un
    // nouveau parcours du sous-arbre complet à ce niveau.
    for (const col of visibleColumns.value) {
      if (!isSummableColumn(col.key)) continue;
      subtotals[col.key] = children.reduce((acc, c) => acc + (c.subtotals[col.key] || 0), 0);
    }
  }

  return {
    level, fieldKey: currentLevel.key, rawValue: bucket.value, label: bucket.label,
    path, directChildCount, children, rows: leafRows, subtotals,
  };
}

// Arbre de regroupement — construit sur filteredItems (après filtres texte + tri existants, sur
// l'INTÉGRALITÉ du jeu de données déjà chargé, pas seulement la page affichée : voir le contexte du
// plan, props.items contient déjà toute la ressource). Racine = tableau de nœuds de premier niveau,
// paginé séparément (voir pagedGroupTree) — la pagination porte sur le NOMBRE DE GROUPES de premier
// niveau, pas sur les lignes, quand le regroupement est actif.
const groupTree = computed<GroupNode[]>(() => {
  if (!isGrouped.value) return [];
  const levels = internalGroupBy.value;
  return bucketRows(filteredItems.value, levels[0]).map(b => buildGroupNode(0, b, [], levels));
});

// État de dépli/repli — volontairement PAS une propriété sur les nœuds de groupTree : ce dernier
// est un computed(), reconstruit (nouvelles instances d'objets) à chaque changement de
// filteredItems, y compris une simple édition en ligne sans rapport avec le regroupement. Si l'état
// déplié vivait sur les nœuds, toute édition en ligne replierait tous les groupes. À la place, un
// Set des chemins (node.path) manuellement basculés par l'utilisateur — toujours réassigné (jamais
// muté en place), même patron que selectedCells dans GenericPivot.vue.
const manuallyToggledPaths = ref<Set<string>>(new Set());

// listConfig.autoExpandLevel : profondeur dépliée par défaut (0 = tout replié). Un clic utilisateur
// inverse cet état par défaut pour le chemin concerné — la clé stable (path, basée sur les valeurs
// BRUTES des ancêtres) fait survivre ce choix aux reconstructions de l'arbre tant que les mêmes
// buckets existent toujours après une édition.
const autoExpandLevel = computed(() => props.listConfig?.autoExpandLevel ?? 0);

function isNodeExpanded(node: GroupNode): boolean {
  const manuallyToggled = manuallyToggledPaths.value.has(node.path);
  const defaultExpanded = node.level < autoExpandLevel.value;
  return manuallyToggled ? !defaultExpanded : defaultExpanded;
}

function toggleNodeExpanded(node: GroupNode) {
  const next = new Set(manuallyToggledPaths.value);
  if (next.has(node.path)) {
    next.delete(node.path);
  } else {
    next.add(node.path);
  }
  manuallyToggledPaths.value = next;
}

// Changer les champs de regroupement (réordonner, ajouter, retirer un niveau) change ce qu'un path
// représente conceptuellement — les anciennes entrées n'ont plus de sens et doivent être purgées,
// sans quoi elles s'accumulent indéfiniment sur une session longue.
watch(internalGroupBy, () => {
  manuallyToggledPaths.value = new Set();
});

// Pagination et Virtualisation
const tableWrapperRef = ref<HTMLElement | null>(null);

// En mode groupé, la pagination porte sur le nombre de groupes de premier niveau (typiquement bien
// plus petit que le nombre de lignes brutes) — le fenêtrage virtuel, conçu pour une liste PLATE de
// nombreuses lignes, ne s'applique donc jamais en mode groupé (voir pagedGroupTree). Limitation v1
// assumée : aucune virtualisation À L'INTÉRIEUR d'un groupe déplié, même très grand.
const isVirtualMode = computed(() => perPage.value === 10000 && !isGrouped.value);
const rowHeight = 44; // Hauteur estimée d'une ligne
const overscan = 10; // Nombre de lignes pré-rendues hors écran

const scrollTop = ref(0);

function onScroll(e: Event) {
  if (isVirtualMode.value) {
    scrollTop.value = (e.target as HTMLElement).scrollTop;
  }
}

const virtualStartIndex = computed(() => {
  if (!isVirtualMode.value) return 0;
  return Math.max(0, Math.floor(scrollTop.value / rowHeight) - overscan);
});

const virtualVisibleCount = computed(() => {
  if (!isVirtualMode.value) return filteredItems.value.length;
  // Suppose container height ~800px if not perfectly measured
  const containerHeight = tableWrapperRef.value ? tableWrapperRef.value.clientHeight : 800;
  return Math.ceil(containerHeight / rowHeight) + (overscan * 2);
});

const virtualEndIndex = computed(() => {
  if (!isVirtualMode.value) return filteredItems.value.length;
  return Math.min(filteredItems.value.length, virtualStartIndex.value + virtualVisibleCount.value);
});

const virtualPaddingTop = computed(() => {
  return virtualStartIndex.value * rowHeight;
});

const virtualPaddingBottom = computed(() => {
  return (filteredItems.value.length - virtualEndIndex.value) * rowHeight;
});

const totalPages = computed(() => {
  if (isGrouped.value) {
    if (perPage.value === 10000) return 1;
    return Math.ceil(groupTree.value.length / perPage.value) || 1;
  }
  if (isVirtualMode.value) return 1;
  return Math.ceil(filteredItems.value.length / perPage.value);
});

const paginatedItems = computed(() => {
  if (isVirtualMode.value) {
    return filteredItems.value.slice(virtualStartIndex.value, virtualEndIndex.value);
  }
  const start = (currentPage.value - 1) * perPage.value;
  return filteredItems.value.slice(start, start + perPage.value);
});

const displayedItems = computed(() => paginatedItems.value);

// Pagination en mode groupé : porte sur le NOMBRE DE GROUPES DE PREMIER NIVEAU, pas sur le nombre
// de lignes (demandé explicitement) — même calcul de tranche que le mode plat (paginatedItems),
// appliqué à groupTree plutôt qu'à filteredItems. perPage === 10000 ("Tout") : tous les groupes de
// premier niveau sur une page unique (voir isVirtualMode ci-dessus, jamais actif en mode groupé).
const pagedGroupTree = computed<GroupNode[]>(() => {
  if (perPage.value === 10000) return groupTree.value;
  const start = (currentPage.value - 1) * perPage.value;
  return groupTree.value.slice(start, start + perPage.value);
});

function flattenVisibleLeafRows(nodes: GroupNode[]): any[] {
  const result: any[] = [];
  for (const node of nodes) {
    if (!isNodeExpanded(node)) continue;
    if (node.children) {
      result.push(...flattenVisibleLeafRows(node.children));
    } else if (node.rows) {
      result.push(...node.rows);
    }
  }
  return result;
}

// Ordre RÉEL d'affichage des lignes feuilles actuellement visibles (page de groupes courante,
// groupes dépliés uniquement) — nécessaire pour le shift-clic (voir onRowClick) : en mode groupé,
// deux lignes visuellement adjacentes ne sont PLUS adjacentes dans filteredItems (le regroupement
// les réordonne/éclate en buckets), un shift-clic basé sur filteredItems sélectionnerait donc une
// plage arbitraire et fausse.
const visibleLeafRowsFlat = computed<any[]>(() => {
  if (!isGrouped.value) return [];
  return flattenVisibleLeafRows(pagedGroupTree.value);
});

// Ensemble sur lequel calculer une plage de shift-clic (voir onRowClick) — les lignes feuilles
// visibles aplaties en mode groupé, filteredItems sinon (comportement inchangé).
function rangeSelectableItems(): any[] {
  return isGrouped.value ? visibleLeafRowsFlat.value : filteredItems.value;
}

// Prédicat partagé : une colonne est "à totaliser" si son type déclaré est 'number', OU par repli
// sur le type JS réel d'au moins une valeur de l'ensemble FILTRÉ (filteredItems, pas seulement la
// page affichée — une colonne reste numérique même si la page courante n'en montre aucune valeur,
// ce qui compte désormais aussi pour les sous-totaux de groupe ci-dessous) — SAUF 'select'/
// 'multiselect' (clé étrangère), jamais sommés même si leurs valeurs sont des ids numériques : ce
// sont les deux seuls types où une déclaration de champ fait autorité contre le typeof runtime (une
// relation sans "type" explicite, ex: related_field non typé, retombe sur 'text' par défaut côté
// App.vue — un défaut de rendu de formulaire, pas une vraie déclaration — donc le repli typeof doit
// rester actif pour ne pas cesser de sommer un champ related réellement numérique).
// ColumnConfig.hideTotal exclut une colonne précise même si elle est numérique. Réutilisé par
// columnTotals (pied de page, somme sur displayedItems) ET par les sous-totaux de groupe (somme sur
// le sous-arbre complet, voir groupTree) — même règle "colonne numérique", ensembles de lignes
// différents.
function isSummableColumn(key: string): boolean {
  if (props.listConfig?.columns?.[key]?.hideTotal) return false;
  const declaredType = getFieldDef(key)?.type;
  if (declaredType === 'select' || declaredType === 'multiselect') return false;
  if (declaredType === 'number') return true;
  return filteredItems.value.some(item => typeof item[key] === 'number');
}

// Somme de chaque colonne numérique visible, sur les lignes actuellement affichées (displayedItems
// — voir listConfig.showColumnTotals). Masqué (voir <tfoot> dans le template) dès que le
// regroupement est actif : les sous-totaux par groupe le rendent redondant.
const columnTotals = computed<Record<string, number>>(() => {
  const totals: Record<string, number> = {};
  if (!props.listConfig?.showColumnTotals) return totals;
  for (const col of visibleColumns.value) {
    if (!isSummableColumn(col.key)) continue;
    totals[col.key] = displayedItems.value.reduce(
      (acc, item) => acc + (typeof item[col.key] === 'number' ? item[col.key] : 0),
      0
    );
  }
  return totals;
});

// Une colonne "duration" reste sommée comme n'importe quel nombre (columnTotals ci-dessus, minutes
// additives) — seul l'AFFICHAGE du total suit le format Xh/XhYY de la colonne, cohérent avec ses
// propres cellules (sinon un total de minutes brutes apparaîtrait à côté de valeurs déjà formatées).
function formatColumnTotal(key: string): string | number {
  const total = columnTotals.value[key];
  if (total === undefined) return '';
  return getFieldDef(key)?.type === 'duration' ? formatDurationMinutes(total) : total;
}

// Sur-en-têtes de colonnes (voir listConfig.columnGroups) : true dès qu'au moins une entrée est
// déclarée, indépendamment des colonnes visibles — pilote la désactivation du glisser-déposer.
const columnGroupsActive = computed(() => {
  return !!(props.listConfig?.columnGroups && Object.keys(props.listConfig.columnGroups).length);
});

// Profondeur max des chemins de groupe parmi les colonnes VISIBLES (0 si columnGroupsActive est
// faux, ou si aucune colonne visible n'a de chemin déclaré) — nombre de lignes de sur-en-tête
// au-dessus de la ligne d'en-tête profonde.
const maxGroupDepth = computed(() => {
  if (!columnGroupsActive.value) return 0;
  let max = 0;
  for (const col of visibleColumns.value) {
    const path = props.listConfig?.columnGroups?.[col.key] || [];
    if (path.length > max) max = path.length;
  }
  return max;
});

interface HeaderGroupCell { kind: 'group'; key: string; label: string; colspan: number; }
interface HeaderColumnCell { kind: 'column'; column: ColumnDef; index: number; rowspan: number; }
interface HeaderCheckboxCell { kind: 'checkbox'; rowspan: number; }
interface HeaderActionsCell { kind: 'actions'; rowspan: number; }
type HeaderCell = HeaderGroupCell | HeaderColumnCell | HeaderCheckboxCell | HeaderActionsCell;

// Matrice des lignes d'en-tête (une ligne par profondeur 0..maxGroupDepth). Un cellule HTML avec
// rowspan doit démarrer sur la PREMIÈRE ligne qu'elle occupe (un rowspan ne s'étend que vers le
// bas) : une colonne dont le chemin de groupe est plus court que maxGroupDepth (ou absent) place
// donc sa cellule interactive réelle (tri, redimension, glisser-déposer) à la ligne correspondant
// à la profondeur de son chemin, étirée jusqu'en bas via rowspan — pas systématiquement sur la
// dernière ligne. Les cellules 'group' regroupent les colonnes visibles consécutives partageant le
// même préfixe de chemin à ce niveau ; leur colspan se recalcule automatiquement au masquage d'une
// colonne (réactif via visibleColumns).
const headerRows = computed<HeaderCell[][]>(() => {
  const depth = maxGroupDepth.value;
  const rows: HeaderCell[][] = Array.from({ length: depth + 1 }, () => []);

  function processSegment(seg: { col: ColumnDef; index: number }[], level: number) {
    let i = 0;
    while (i < seg.length) {
      const path = props.listConfig?.columnGroups?.[seg[i].col.key] || [];
      if (level < path.length) {
        const label = path[level];
        const members: typeof seg = [];
        let j = i;
        while (j < seg.length) {
          const p2 = props.listConfig?.columnGroups?.[seg[j].col.key] || [];
          if (level < p2.length && p2[level] === label) {
            members.push(seg[j]);
            j++;
          } else {
            break;
          }
        }
        rows[level].push({ kind: 'group', key: `g-${level}-${members[0].index}`, label, colspan: members.length });
        processSegment(members, level + 1);
        i = j;
      } else {
        rows[level].push({ kind: 'column', column: seg[i].col, index: seg[i].index, rowspan: depth - level + 1 });
        i++;
      }
    }
  }

  processSegment(visibleColumns.value.map((col, index) => ({ col, index })), 0);

  if (isMultiSelectAllowed.value) {
    rows[0].unshift({ kind: 'checkbox', rowspan: depth + 1 });
  }
  rows[0].push({ kind: 'actions', rowspan: depth + 1 });

  return rows;
});

// Multisélection (Actions groupées & Raccourcis EDT p.41) dépendantes de filteredItems
const isAllSelected = computed(() => {
  if (filteredItems.value.length === 0) return false;
  return filteredItems.value.every(item => selectedIds.value.has(item.id));
});

const isSomeSelected = computed(() => {
  if (filteredItems.value.length === 0) return false;
  const numSelected = filteredItems.value.filter(item => selectedIds.value.has(item.id)).length;
  return numSelected > 0 && numSelected < filteredItems.value.length;
});

function toggleSelectAll(checked: boolean) {
  if (checked) {
    filteredItems.value.forEach(item => {
      selectedIds.value.add(item.id);
    });
  } else {
    filteredItems.value.forEach(item => {
      selectedIds.value.delete(item.id);
    });
  }
}

function toggleSelectRow(item: any, checked: boolean) {
  if (checked) {
    selectedIds.value.add(item.id);
  } else {
    selectedIds.value.delete(item.id);
  }
  lastClickedItem.value = item;
}

function handleGlobalKeyDown(event: KeyboardEvent) {
  const target = event.target as HTMLElement;
  if (
    target.tagName === 'INPUT' ||
    target.tagName === 'TEXTAREA' ||
    target.tagName === 'SELECT' ||
    target.isContentEditable
  ) {
    return;
  }

  // Ctrl+A ou Cmd+A
  if ((event.ctrlKey || event.metaKey) && (event.key === 'a' || event.key === 'A') && isMultiSelectAllowed.value) {
    event.preventDefault();
    filteredItems.value.forEach(item => {
      selectedIds.value.add(item.id);
    });
  }
}

watch(isSomeSelected, (val) => {
  if (selectAllCheckbox.value) {
    selectAllCheckbox.value.indeterminate = val;
  }
});

watch(() => props.title, () => {
  selectedIds.value.clear();
  lastClickedItem.value = null;
  // Réarme la restauration depuis l'URL : si l'utilisateur navigue vers une autre ressource puis
  // revient (bouton Précédent) sur celle-ci avec initialSelectedIds à nouveau pertinent, il faut
  // pouvoir la réappliquer plutôt que la considérer comme déjà consommée.
  hasAppliedInitialSelection.value = false;
});

watch(() => props.items, (newItems) => {
  const validIds = new Set(newItems.map(item => item.id));
  const toDelete: any[] = [];
  selectedIds.value.forEach(id => {
    if (!validIds.has(id)) {
      toDelete.push(id);
    }
  });
  toDelete.forEach(id => selectedIds.value.delete(id));
  if (lastClickedItem.value && !validIds.has(lastClickedItem.value.id)) {
    lastClickedItem.value = null;
  }
}, { deep: true });

onMounted(() => {
  document.addEventListener('mousedown', handleClickOutside);
  window.addEventListener('keydown', handleGlobalKeyDown);
});

onUnmounted(() => {
  document.removeEventListener('mousedown', handleClickOutside);
  window.removeEventListener('keydown', handleGlobalKeyDown);
});

// Reset page on filter/limit/grouping changes — activer/désactiver/modifier le regroupement change
// radicalement le dénominateur de pagination (pages de groupes vs pages de lignes), sans quoi
// l'utilisateur peut atterrir sur une page vide hors bornes.
watch([filters, perPage, internalGroupBy], () => {
  currentPage.value = 1;
}, { deep: true });

// Redimensionnement de colonnes
let startX = 0;
let startWidth = 0;
let resizingKey: string | null = null;

function startResize(event: MouseEvent, key: string) {
  startX = event.clientX;
  resizingKey = key;
  const col = internalColumns.value.find(c => c.key === key);
  if (col) {
    startWidth = col.width || 150;
  }
  document.addEventListener('mousemove', onResize);
  document.addEventListener('mouseup', stopResize);
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
}

function onResize(event: MouseEvent) {
  if (!resizingKey) return;
  const diff = event.clientX - startX;
  const col = internalColumns.value.find(c => c.key === resizingKey);
  if (col) {
    col.width = Math.max(50, startWidth + diff);
  }
}

function stopResize() {
  document.removeEventListener('mousemove', onResize);
  document.removeEventListener('mouseup', stopResize);
  resizingKey = null;
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
}

// Drag & Drop de colonnes (Réordonnancement)
let draggedIdx: number | null = null;

function onDragStart(event: DragEvent, index: number) {
  if (columnGroupsActive.value) return;
  draggedIdx = index;
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move';
  }
}

function onDragOver(event: DragEvent, index: number) {
  if (columnGroupsActive.value) return;
  event.preventDefault();
}

function onDrop(event: DragEvent, index: number) {
  if (columnGroupsActive.value) return;
  if (draggedIdx === null || draggedIdx === index) return;
  
  // Retrouver les colonnes réelles correspondantes
  const visibleCols = [...visibleColumns.value];
  const targetCol = visibleCols[index];
  const sourceCol = visibleCols[draggedIdx];
  
  // Repositionner dans le tableau internalColumns
  const sourceIdx = internalColumns.value.findIndex(c => c.key === sourceCol.key);
  const targetIdx = internalColumns.value.findIndex(c => c.key === targetCol.key);
  
  if (sourceIdx !== -1 && targetIdx !== -1) {
    const col = internalColumns.value.splice(sourceIdx, 1)[0];
    internalColumns.value.splice(targetIdx, 0, col);
  }

  draggedIdx = null;
}

// --- Contexte partagé avec GenericListRow.vue / GenericListGroupHeaderRow.vue (voir
// genericListRowContext.ts) : provide() une seule fois, en fin de configuration, une fois toutes
// les fonctions/computed référencées définies plus haut dans ce fichier. ---

function isRowSelected(id: number | string): boolean {
  return selectedIds.value.has(id);
}

function onDeleteItem(item: any) {
  emit('delete', item);
}

function columnListConfig(key: string): any {
  return props.listConfig?.columns?.[key]?.listConfig;
}

provide(GENERIC_LIST_ROW_CONTEXT, {
  visibleColumns: () => visibleColumns.value,
  isMultiSelectAllowed: () => isMultiSelectAllowed.value,
  isRowSelected,
  disableDelete: () => !!props.listConfig?.disableDelete,
  getFieldDef,
  getWidgetComponent,
  isColumnReadOnly,
  isColumnRequired,
  columnListConfig,
  rowSource,
  updateInline,
  onRowFocusOut,
  onRowClick,
  onDeleteItem,
  frozenLeftStyle,
  isLastFrozenColumn,
  frozenColumnCount: () => frozenColumnCount.value,
});

function formatSubtotal(key: string, value: number): string | number {
  return getFieldDef(key)?.type === 'duration' ? formatDurationMinutes(value) : value;
}

provide(GENERIC_LIST_GROUP_CONTEXT, {
  isNodeExpanded,
  toggleNodeExpanded,
  isSummableColumn,
  formatSubtotal,
});
</script>

<style scoped>
.generic-list-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(12px);
}

.list-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
  background-color: var(--bg-surface);
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}

.toolbar-badge {
  background-color: rgba(99, 102, 241, 0.15);
  color: var(--accent-primary);
  border: 1px solid rgba(99, 102, 241, 0.25);
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 600;
}

.selection-badge {
  background-color: rgba(99, 102, 241, 0.25) !important;
  color: var(--accent-primary) !important;
  border: 1px solid var(--accent-primary) !important;
  font-weight: bold;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.icon-selector, .icon-add {
  width: 16px;
  height: 16px;
}

/* Dropdown Colonnes */
.column-selector-wrapper {
  position: relative;
}

.column-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 220px;
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  z-index: 100;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  animation: fadeIn var(--transition-fast);
}

.dropdown-header {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--text-muted);
  letter-spacing: 0.5px;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 6px;
}

.dropdown-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 200px;
  overflow-y: auto;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-primary);
  cursor: pointer;
  padding: 4px;
  border-radius: var(--radius-md);
  transition: background-color var(--transition-fast);
}

.dropdown-item:hover {
  background-color: var(--bg-secondary);
}

.dropdown-item input[type="checkbox"] {
  accent-color: var(--accent-primary);
  width: 15px;
  height: 15px;
}

/* Table */
.table-wrapper {
  flex: 1;
  position: relative;
  overflow: auto;
}

.premium-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  table-layout: fixed;
}

.header-tr {
  background-color: var(--bg-surface);
}

.header-th {
  position: sticky;
  top: 0;
  background-color: var(--bg-surface);
  backdrop-filter: blur(8px);
  z-index: 10;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
  padding: 8px 5px;
  position: relative;
  user-select: none;
  /* box-shadow inset plutôt que border-right/border-bottom : sous border-collapse, une cellule à
     rowspan (colonne sans groupe, étirée sur toute la hauteur de l'en-tête) et une cellule à
     colspan (sur-en-tête) voisines ne partagent pas le même "segment" de bordure au sens de
     l'algorithme de fusion des bordures — deux cellules déclarant pourtant la MÊME couleur peuvent
     alors se peindre avec un gris légèrement différent selon la cellule "gagnante" du conflit à
     chaque jonction (bug constaté, pas une différence de configuration : voir git blame). Un
     box-shadow inset est peint par chaque cellule indépendamment, sans fusion ni conflit avec ses
     voisines — un même --border-color-strong partout, garanti pixel pour pixel. Bénéfice
     secondaire : plus besoin de distinguer "dernière ligne d'en-tête" (ex-.header-tr-last) pour la
     séparation avec le corps du tableau — une cellule à rowspan porte déjà son propre bord bas
     exactement là où elle se termine, qu'elle couvre une ou plusieurs lignes d'en-tête. */
  box-shadow: inset -1px -1px 0 0 var(--border-color-strong);
}

.header-th:hover {
  z-index: 100;
}

/* Cellule de sur-en-tête (voir listConfig.columnGroups) : non interactive, pas de hover/cursor.
   Bordures héritées de .header-th (--border-color-strong), pas de traitement visuel distinct —
   un fond plus soutenu a été essayé puis abandonné (n'aidait pas à distinguer les groupes). */
.header-group-th {
  text-align: center;
  cursor: default;
  user-select: none;
}

.th-content {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
  transition: color var(--transition-fast);
}

.th-content:hover {
  color: var(--text-primary);
}

/* Colonne non triable (voir isColumnSortable) : le clic ne fait rien, l'en-tête ne doit donc pas se
   présenter comme cliquable. */
.th-content-not-sortable {
  cursor: default;
}

.th-content-not-sortable:hover {
  color: inherit;
}

.th-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sort-indicator {
  color: var(--accent-primary);
  font-size: 10px;
}

.resize-handle {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 5px;
  cursor: col-resize;
  background-color: transparent;
  transition: background-color var(--transition-fast);
}

.resize-handle:hover {
  background-color: rgba(99, 102, 241, 0.5);
}

/* Filtres */
.filter-tr {
  background-color: var(--bg-surface);
}

.filter-td {
  padding: 3px 6px;
  border-bottom: 1px solid var(--border-color);
  border-right: 1px solid var(--border-color);
}

.filter-input {
  width: 100%;
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 5px 10px;
  color: var(--text-primary);
  font-size: 12px;
  outline: none;
  font-family: var(--font-sans);
  transition: border-color var(--transition-fast);
}

.filter-input:focus {
  border-color: var(--accent-primary);
}

/* .body-tr/.body-td (base + hover/selected/has-select) : déplacées dans GenericListRow.vue /
   GenericListGroupHeaderRow.vue — plus rendues par ce composant depuis l'extraction du volet
   regroupement (voir architecture.md, section Z) ; le CSS scoped de CE fichier ne les ciblerait
   plus (frontière de scope Vue : un style scoped ne s'applique qu'aux éléments du template DE CE
   composant, jamais à ceux rendus par un composant enfant). */

.footer-total-tr {
  background-color: var(--bg-surface);
  border-top: 2px solid var(--border-color);
}

.footer-total-td {
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  border-right: 1px solid var(--border-color);
  /* Convention comptable, même choix que .inline-number : les colonnes non numériques restent
     vides sur cette ligne (voir columnTotals), l'alignement n'y change donc rien de visible. */
  text-align: right;
}

.empty-td {
  text-align: center;
  padding: 40px;
  color: var(--text-muted);
  font-size: 14px;
}

.actions-th {
  width: 40px !important;
  min-width: 40px !important;
  max-width: 40px !important;
  padding: 8px 4px !important;
  text-align: center;
  position: sticky;
  right: 0;
  background-color: var(--bg-surface);
  z-index: 11;
  border-left: 1px solid var(--border-color);
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

/* .actions-group/.btn-action et les variantes .body-td.column-frozen (base + hover/selected) sont
   déplacées dans GenericListRow.vue / GenericListGroupHeaderRow.vue, comme .body-tr/.body-td plus
   haut — .actions-td lui-même RESTE ici (encore utilisé par les combos filter-td/footer-total-td
   ci-dessous, propres au template de CE composant), en plus d'être dupliqué (règle purement
   visuelle, sans risque) dans les deux composants enfants pour leur propre cellule actions. */

/* Colonnes figées à gauche (voir listConfig.frozenColumns) — même mécanisme sticky que la colonne
   Actions ci-dessus (déjà figée à droite), mais côté gauche et sur un nombre de colonnes variable ;
   mêmes conventions de z-index/fond reprises à l'identique (au-dessus des cellules non figées de
   la même ligne, opaque pour masquer ce qui défile en dessous). Le positionnement (left) est posé
   en inline via frozenLeftStyle, ces règles ne portent que ce que CSS seul ne peut pas exprimer
   (z-index, fond, conditionné par ligne/état). */
.header-th.column-frozen {
  z-index: 11;
}

.filter-td.column-frozen {
  z-index: 9;
  background-color: var(--bg-surface);
}

.footer-total-td.column-frozen {
  z-index: 9;
  background-color: var(--bg-surface);
}

/* Ligne de démarcation sur la dernière colonne figée (comme le "mur" entre volets figés/non figés
   sous Excel ou Google Sheets), pour bien marquer où s'arrête la zone figée. Écrit à part pour
   .header-th (sélecteur à deux classes, plus spécifique que .header-th seul) car .header-th porte
   déjà sa bordure via box-shadow (voir plus haut) — un box-shadow déclaré ici écraserait l'autre au
   lieu de s'y ajouter si on ne les combinait pas dans une seule et même déclaration. */
.header-th.column-frozen-last {
  box-shadow: inset -1px -1px 0 0 var(--border-color-strong), 2px 0 4px -2px rgba(0, 0, 0, 0.25);
}

.filter-td.column-frozen-last,
.footer-total-td.column-frozen-last {
  box-shadow: 2px 0 4px -2px rgba(0, 0, 0, 0.25);
}

/* Badges */
.badge-boolean {
  padding: 2px 6px;
  border-radius: var(--radius-md);
  font-size: 11px;
  font-weight: 700;
}

.badge-true {
  background-color: rgba(16, 185, 129, 0.15);
  color: var(--accent-success);
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.badge-false {
  background-color: rgba(239, 68, 68, 0.15);
  color: var(--accent-danger);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

/* Pagination */
.list-pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 12px;
  border-top: 1px solid var(--border-color);
  background-color: var(--bg-surface);
  font-size: 12px;
  color: var(--text-secondary);
}

.per-page-selector {
  display: flex;
  align-items: center;
  gap: 8px;
}

.select-custom {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  outline: none;
  cursor: pointer;
  height: 22px;
  font-size: 11px;
}

.pagination-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.pagination-buttons {
  display: flex;
  gap: 4px;
}

.btn-icon-only {
  width: 22px;
  height: 22px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: bold;
  background-color: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-icon-only:hover:not(:disabled) {
  background-color: rgba(99, 102, 241, 0.15);
  color: var(--accent-primary);
  border-color: var(--accent-primary);
}

.btn-icon-only:disabled {
  opacity: 0.25;
  cursor: not-allowed;
  border-color: var(--border-color);
  color: var(--text-muted);
}

.glass-morphism {
  background: var(--bg-card);
  backdrop-filter: blur(12px);
}

/* .immutable-id/.inline-input/.inline-json-summary/.inline-binary-badge/.inline-number/
   .inline-checkbox-wrapper/.inline-color-swatch-wrapper/.readonly-swatch (styles Airtable-style
   pour l'édition en ligne) sont déplacées dans GenericListRow.vue, comme .body-tr/.body-td plus
   haut — même raison (frontière de scope Vue). */

/* Sélecteur de couleur unifié standard */
.inline-color-select-wrapper {
  width: 100%;
  display: flex;
  align-items: center;
}

.inline-color-select {
  width: 100%;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 4px 8px;
  font-family: monospace;
  font-size: 12px;
  font-weight: bold;
  cursor: pointer;
  outline: none;
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-fast);
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
  appearance: none;
  -webkit-appearance: none;
  -moz-appearance: none;
  text-align: center;
}

.inline-color-select:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
  border-color: var(--accent-primary);
}

.inline-color-select:focus {
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 2px var(--accent-primary);
}

/* Filtre de couleur spécial */
.filter-color-select {
  cursor: pointer;
  font-weight: 600;
  font-size: 12px;
  padding: 4px 6px;
}

.inline-switch {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 18px;
}

.inline-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.inline-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-color);
  transition: .3s;
}

.inline-slider:before {
  position: absolute;
  content: "";
  height: 12px;
  width: 12px;
  left: 2px;
  bottom: 2px;
  background-color: var(--text-secondary);
  transition: .3s;
}

input:checked + .inline-slider {
  background-color: rgba(99, 102, 241, 0.2);
  border-color: var(--accent-primary);
}

input:checked + .inline-slider:before {
  transform: translateX(18px);
  background-color: var(--accent-primary);
}

.inline-slider.inline-round {
  border-radius: 18px;
}

.inline-slider.inline-round:before {
  border-radius: 50%;
}

/* Nouveaux styles IHM optimisés */
.actions-header-wrapper {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
}

.btn-icon-only-flat {
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--text-muted);
  padding: 4px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
}

.btn-icon-only-flat:hover {
  background-color: rgba(99, 102, 241, 0.15);
  color: var(--accent-primary);
}

.pagination-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.add-row-tr {
  background-color: rgba(99, 102, 241, 0.03);
  cursor: pointer;
  transition: all var(--transition-fast);
  border-bottom: 1px solid var(--border-color);
}

.add-row-tr:hover {
  background-color: rgba(99, 102, 241, 0.08);
}

.add-row-td {
  padding: 8px 16px;
}

.add-row-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--accent-primary);
  font-size: 13px;
  font-weight: 600;
}

/* Disabled and ReadOnly styles */
.disabled-switch {
  cursor: not-allowed !important;
  opacity: 0.6;
  pointer-events: none;
}

/* .readonly-swatch déplacée dans GenericListRow.vue (voir le commentaire plus haut sur .body-tr). */

/* Bulle d'aide (tooltip help) */
.help-tooltip-wrapper {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-left: 4px;
  cursor: help;
}

.help-icon {
  color: rgba(1, 128, 165, 1);
  background: rgba(1, 128, 165, 0.1);
  border-radius: 50%;
  width: 14px;
  height: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-style: normal;
  font-size: 10px;
  font-weight: bold;
  transition: all var(--transition-fast);
}

.help-icon:hover {
  background: rgba(1, 128, 165, 0.2);
  transform: scale(1.1);
}

.help-tooltip {
  visibility: hidden;
  opacity: 0;
  width: 250px;
  background-color: var(--bg-secondary);
  color: var(--text-primary);
  text-align: left;
  border-radius: var(--radius-lg);
  padding: 10px 12px;
  position: absolute;
  z-index: 1000;
  bottom: 125%; /* Position the tooltip above the text */
  left: 50%;
  transform: translateX(-50%);
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06), 0 10px 15px -3px rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.1);
  font-size: 12px;
  font-weight: normal;
  line-height: 1.5;
  pointer-events: none;
  transition: opacity 0.2s ease, visibility 0.2s ease;
  white-space: normal;
}

/* Tooltip arrow */
.help-tooltip::after {
  content: "";
  position: absolute;
  top: 100%; /* At the bottom of the tooltip */
  left: 50%;
  margin-left: -5px;
  border-width: 5px;
  border-style: solid;
  border-color: var(--bg-secondary) transparent transparent transparent;
}

.help-tooltip-wrapper:hover .help-tooltip {
  visibility: visible;
  opacity: 1;
}

/* Basic styling inside the parsed markdown tooltip */
.help-tooltip strong {
  font-weight: bold;
  color: var(--text-primary);
}

.help-tooltip em {
  font-style: italic;
}

.help-tooltip code {
  background-color: rgba(255, 255, 255, 0.15);
  padding: 2px 4px;
  border-radius: var(--radius-md);
  font-family: monospace;
  font-size: 11px;
}

.help-tooltip ul {
  margin: 6px 0 0 0;
  padding-left: 16px;
  list-style-type: disc;
}

.help-tooltip li {
  margin-bottom: 4px;
}

/* Positionnement vers le bas pour eviter la troncature par le bord superieur du conteneur */
.help-tooltip.tooltip-bottom {
  bottom: auto;
  top: 125%;
}

.help-tooltip.tooltip-bottom::after {
  bottom: 100%;
  top: auto;
  border-color: transparent transparent var(--bg-secondary) transparent;
}
</style>
