<template>
  <div class="grid-container">
    <div class="grid-wrapper" :class="{ 'mini-grid': isMini }">
      <div v-if="days.length > 0" class="timetable-grid" :style="{ gridTemplateColumns: computedGridTemplateColumns, gridTemplateRows: computedGridTemplateRows, minWidth: isMini ? '0' : undefined }">
        <!-- Coin supérieur gauche -->
        <div class="grid-header-cell" style="position: sticky; left: 0; z-index: 12;" :style="{ gridRow: layoutMode === 'resource_columns' && activeResources && activeResources.length > 0 ? '1 / span 2' : '1' }">Horaire</div>

        <!-- En-têtes des jours -->
        <div v-for="day in days" :key="'day-'+day.value" class="grid-header-cell" :style="{ gridColumn: `span ${(layoutMode === 'resource_columns' && activeResources && activeResources.length > 0) ? activeResources.length : 1}` }">
          {{ day.label }}
          <div
            class="resize-handle"
            @mousedown.stop.prevent="startResize($event, day.value)"
          ></div>
        </div>

        <!-- En-têtes des ressources (si activé) -->
        <template v-if="layoutMode === 'resource_columns' && activeResources && activeResources.length > 0">
          <template v-for="day in days" :key="'res-row-'+day.value">
            <div v-for="res in activeResources" :key="res.id" class="grid-header-cell resource-header-cell" style="top: 50px; z-index: 11; font-size: 0.85em; font-weight: normal; border-top: none; background-color: var(--bg-surface);">
              {{ res.display_name }}
            </div>
          </template>
        </template>

        <!-- Lignes d'heures (8h à 17h) -->
        <template v-for="(hour, index) in hours" :key="hour">
          <!-- Cellule d'heure à gauche -->
          <div class="grid-time-cell" :ref="(el) => { if (index === 0) gridCellRef = el as HTMLElement | null }">
            {{ hour }}h00 - {{ hour + 1 }}h00
          </div>

          <!-- Cellules de la grille pour chaque colonne -->
          <div
            v-for="col in gridColumns"
            :key="col.id"
            class="grid-cell"
            :style="{ display: 'flex', flexDirection: 'column', alignItems: 'stretch', position: 'relative' }"
          >
            <div
              v-for="idx in subCellCount"
              :key="idx"
              class="sub-cell"
              :class="{ 
                'drag-over': dragOverCells[getCellKey(col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60))],
                'pref-level-off-hashed': !isTimeslotActive(col.dayValue, hour, idx - 1)
              }"
              @dragover.prevent="!shouldSplitCells && $emit('cell-dragover', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
              @dragleave="!shouldSplitCells && $emit('cell-dragleave', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
              @drop="!shouldSplitCells && $emit('cell-drop', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
              @mousedown="$emit('cell-mousedown', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
              @mouseenter="$emit('cell-mouseenter', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
              @mouseleave="$emit('cell-mouseleave', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
              @mousemove="$emit('cell-mousemove', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event)"
            >
              <!-- Layer 1: Background (Preferences/Constraints) -->
              <div class="layer-bg">
                <slot name="cell-background" :day="col.dayValue" :time="hour + (idx - 1) * (currentStandardDuration / 60)" :resource="col.resource"></slot>
              </div>

              <!-- Layer 2: Foreground (Courses) -->
              <div class="layer-fg">
                <slot name="cell-content" :day="col.dayValue" :time="hour + (idx - 1) * (currentStandardDuration / 60)" :resource="col.resource"></slot>
              </div>

              <!-- Layer 3 : zones de dépose scindées Semaine A / Semaine B — uniquement pendant
                   le glisser d'un cours dont la semaine reste à choisir (A/B/Q), en vue "Toutes
                   les semaines" (voir shouldSplitCells, attribution_week_type_auto.md Phase B).
                   Juste un contour (pas de fond ni de lettrage) pour ne pas masquer la coloration
                   de poids/score de la cellule (layer-bg) ; l'ombre portée au survol (.drag-over,
                   voir plus bas) indique où le cours va tomber. N'existent que pendant un drag
                   actif : jamais de conflit avec le clic/la sélection d'un cours déjà placé dans
                   cette cellule. dragover/dragleave/drop de .sub-cell lui-même sont désactivés
                   pendant le split (voir plus haut, !shouldSplitCells) : ces événements REMONTENT
                   (bubbling) depuis .split-half jusqu'à .sub-cell, qui sans cette garde émettrait
                   AUSSI cell-dragover/cell-dragleave sans weekHalf — posant la clé de survol SANS
                   suffixe -A/-B, faisant passer .sub-cell lui-même en .drag-over et teintant donc
                   TOUTE la cellule (les deux moitiés, .sub-cell étant sous .split-half) en plus de
                   la moitié réellement ciblée — d'où l'ombre parasite côté non-ciblé observée. -->
              <template v-if="shouldSplitCells">
                <div
                  class="split-half split-half-a"
                  :class="{ 'drag-over': dragOverCells[getCellKey(col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60)) + '-A'] }"
                  title="Semaine A"
                  @dragover.prevent="$emit('cell-dragover', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event, 'A')"
                  @dragleave="$emit('cell-dragleave', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event, 'A')"
                  @drop="$emit('cell-drop', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event, 'A')"
                ></div>
                <div
                  class="split-half split-half-b"
                  :class="{ 'drag-over': dragOverCells[getCellKey(col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60)) + '-B'] }"
                  title="Semaine B"
                  @dragover.prevent="$emit('cell-dragover', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event, 'B')"
                  @dragleave="$emit('cell-dragleave', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event, 'B')"
                  @drop="$emit('cell-drop', col.dayValue, hour + (idx - 1) * (currentStandardDuration / 60), $event, 'B')"
                ></div>
              </template>
            </div>
          </div>
        </template>

        <!-- Récréations : ligne grise fine en SURIMPRESSION (position absolute, hors flux CSS
             grid) — ne perturbe donc jamais la correspondance minutes -> pixels dont dépend la
             hauteur des cours (voir Sidebar.vue, --grid-cell-height). Activée par défaut, voir
             prop displayBreaks (paramètre du composant, pas un SystemSetting). -->
        <div
          v-if="props.displayBreaks && morningBreakTopPx !== null"
          class="break-line"
          :style="{ top: morningBreakTopPx + 'px' }"
          title="Récréation du matin"
        ></div>
        <div
          v-if="props.displayBreaks && afternoonBreakTopPx !== null"
          class="break-line"
          :style="{ top: afternoonBreakTopPx + 'px' }"
          title="Récréation de l'après-midi"
        ></div>
      </div>

      <div v-else class="no-timeslots-error">
        <div class="error-icon">⚠️</div>
        <div class="error-title">Aucun créneau horaire configuré</div>
        <div class="error-desc">Veuillez configurer les créneaux horaires afin d'afficher la grille.</div>
      </div>

      <!-- Overlay de chargement -->
      <slot name="overlay"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue';
import { useTimeslotGrid } from '../composables/useTimeslotGrid';

const props = withDefaults(defineProps<{
  timeslots: any[];
  dragOverCells?: Record<string, boolean>;
  layoutMode?: string;
  activeResources?: any[];
  isMini?: boolean;
  // Filtre de semaine actif ("Toutes" = 'W') et week_type du cours en cours de glisser-déposer
  // (voir TimetableGrid.vue) : pilotent le split de colonnes A/B (voir attribution_week_type_auto.md,
  // Phase B). Un cours W n'est jamais scindable (il occupe intrinsèquement les deux semaines) ;
  // le split n'a de sens que si on visualise déjà "Toutes les semaines" (sinon une seule semaine
  // est affichée, aucune ambiguïté à résoudre).
  weekType?: 'W' | 'A' | 'B';
  draggedCourseWeekType?: string | null;
  // Affichage des lignes de récréation (voir break-line ci-dessous) : un paramètre du composant
  // graphique, PAS un réglage système — HOUR_MORNING/AFTERNOON_BREAK_START restent des
  // SystemSetting (donnée métier), mais le fait de les DESSINER sur cette grille précise est une
  // simple préférence d'affichage locale, activée par défaut.
  displayBreaks?: boolean;
}>(), {
  dragOverCells: () => ({}),
  layoutMode: 'merged',
  activeResources: () => [],
  isMini: false,
  weekType: 'W',
  draggedCourseWeekType: null,
  displayBreaks: true,
});

const shouldSplitCells = computed(() => {
  return props.weekType === 'W' && !!props.draggedCourseWeekType && props.draggedCourseWeekType !== 'W';
});

const { days, hours, currentStandardDuration, subCellCount, getCellKey, isTimeslotActive, morningBreakStart, afternoonBreakStart } = useTimeslotGrid(computed(() => props.timeslots));

const gridColumns = computed(() => {
  if (props.layoutMode === 'resource_columns' && props.activeResources && props.activeResources.length > 0) {
    const cols: any[] = [];
    days.value.forEach(day => {
      props.activeResources!.forEach(res => {
        cols.push({ id: `${day.value}-${res.type}-${res.id}`, dayValue: day.value, resource: res });
      });
    });
    return cols;
  }
  return days.value.map(day => ({ id: `${day.value}`, dayValue: day.value, resource: null }));
});

// === Redimensionnement des colonnes (jours) ===
const columnWidths = ref<Record<number, number>>({});

function getColWidth(dayVal: number) {
  return columnWidths.value[dayVal] || 0;
}

const computedGridTemplateColumns = computed(() => {
  const timeCol = '60px'; // Slightly smaller time col to fit more content
  const dayCols = gridColumns.value.map(col => {
    if (columnWidths.value[col.dayValue]) {
      if (props.layoutMode === 'resource_columns' && props.activeResources && props.activeResources.length > 0) {
        return `${columnWidths.value[col.dayValue] / props.activeResources.length}px`;
      }
      return `${columnWidths.value[col.dayValue]}px`;
    }
    return `minmax(0, 1fr)`;
  }).join(' ');
  return `${timeCol} ${dayCols}`;
});

const computedGridTemplateRows = computed(() => {
  const hasResourceHeader = props.layoutMode === 'resource_columns' && props.activeResources && props.activeResources.length > 0;
  const numHours = hours.value.length;
  return hasResourceHeader ? `40px 30px repeat(${numHours}, minmax(0, 1fr))` : `40px repeat(${numHours}, minmax(0, 1fr))`;
});

let startX = 0;
let startWidth = 0;
let resizingDay: number | null = null;

function startResize(event: MouseEvent, dayVal: number) {
  startX = event.clientX;
  resizingDay = dayVal;
  startWidth = getColWidth(dayVal);
  
  document.addEventListener('mousemove', onResize);
  document.addEventListener('mouseup', stopResize);
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
}

function onResize(event: MouseEvent) {
  if (resizingDay === null) return;
  const diff = event.clientX - startX;
  let newWidth = startWidth + diff;
  if (newWidth < 100) newWidth = 100; // largeur minimale
  columnWidths.value[resizingDay] = newWidth;
}

function stopResize() {
  document.removeEventListener('mousemove', onResize);
  document.removeEventListener('mouseup', stopResize);
  resizingDay = null;
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
}
// ===============================================



defineEmits<{
  (e: 'cell-dragover', day: number, time: number, event: DragEvent, weekHalf?: 'A' | 'B'): void;
  (e: 'cell-dragleave', day: number, time: number, event: DragEvent, weekHalf?: 'A' | 'B'): void;
  (e: 'cell-drop', day: number, time: number, event: DragEvent, weekHalf?: 'A' | 'B'): void;
  (e: 'cell-mousedown', day: number, time: number, event: MouseEvent): void;
  (e: 'cell-mouseenter', day: number, time: number, event: MouseEvent): void;
  (e: 'cell-mouseleave', day: number, time: number, event: MouseEvent): void;
  (e: 'cell-mousemove', day: number, time: number, event: MouseEvent): void;
}>();

const gridCellRef = ref<HTMLElement | null>(null);
let resizeObserver: ResizeObserver | null = null;

// Miroir réactif de --grid-cell-height (CSS var, voir Sidebar.vue) : nécessaire ici en JS pur
// pour calculer la position en pixels des lignes de récréation (voir break-line ci-dessous), la
// CSS var elle-même n'étant pas lisible de façon réactive depuis un computed().
const gridCellHeightPx = ref(75);

onMounted(() => {
  if (gridCellRef.value) {
    resizeObserver = new ResizeObserver(entries => {
      for (const entry of entries) {
        // Obtenir la hauteur réelle (y compris les bordures/padding)
        const height = entry.borderBoxSize?.[0]?.blockSize || entry.contentRect.height;
        document.documentElement.style.setProperty('--grid-cell-height', `${height}px`);
        gridCellHeightPx.value = height;
      }
    });
    resizeObserver.observe(gridCellRef.value);
  }
});

onUnmounted(() => {
  if (resizeObserver) {
    resizeObserver.disconnect();
  }
});

// Hauteur de l'en-tête (voir computedGridTemplateRows : 40px, +30px pour la sous-ligne de
// ressources en layoutMode="resource_columns") — offset de départ pour tout calcul minutes -> px.
const headerHeightPx = computed(() => {
  const hasResourceHeader = props.layoutMode === 'resource_columns' && props.activeResources && props.activeResources.length > 0;
  return hasResourceHeader ? 70 : 40;
});

// Position verticale (px, depuis le haut de .timetable-grid) d'un horaire donné — null s'il tombe
// hors de la plage d'heures actuellement affichée (hours, voir useTimeslotGrid).
function breakOffsetPx(minutesFromMidnight: number | null): number | null {
  if (minutesFromMidnight === null || hours.value.length === 0) return null;
  const firstHourMinutes = hours.value[0] * 60;
  const lastHourEndMinutes = (hours.value[hours.value.length - 1] + 1) * 60;
  if (minutesFromMidnight < firstHourMinutes || minutesFromMidnight >= lastHourEndMinutes) return null;
  return headerHeightPx.value + ((minutesFromMidnight - firstHourMinutes) / 60) * gridCellHeightPx.value;
}

const morningBreakTopPx = computed(() => breakOffsetPx(morningBreakStart.value));
const afternoonBreakTopPx = computed(() => breakOffsetPx(afternoonBreakStart.value));
</script>

<style scoped>
.sub-cell {
  flex: 1;
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-areas: "stack";
  position: relative;
  transition: all 0.2s;
  padding: 0;
}

.sub-cell:not(:last-child) {
  border-bottom: 1px dotted var(--border-color);
}

/* Zones de dépose scindées Semaine A / Semaine B (voir shouldSplitCells) — juste un contour,
   aucun fond : la coloration de poids/score de la cellule (layer-bg) doit rester entièrement
   visible, seule l'ombre .drag-over (au survol pendant le glisser) donne un retour visuel. */
.split-half {
  grid-area: stack;
  position: relative;
  height: 100%;
  width: 50%;
  z-index: 3;
  pointer-events: auto;
  transition: background-color 0.15s;
}

.split-half-a {
  justify-self: start;
  border-right: 1px dashed var(--border-color);
}

.split-half-b {
  justify-self: end;
}

/* Ombre portée au survol pendant un glisser — indique où le cours va tomber au relâchement.
   Grisé neutre et transparent (pas de teinte colorée) pour ne pas masquer la coloration de
   poids/score déjà affichée par layer-bg en dessous. S'applique à .sub-cell (cours W, cellule
   entière, non scindée) et à .split-half (cours A/B/Q, une moitié de cellule) de façon identique. */
.sub-cell.drag-over,
.split-half.drag-over {
  background-color: rgba(100, 116, 139, 0.25);
  outline: 1px dashed rgba(100, 116, 139, 0.6);
  outline-offset: -2px;
}

.pref-level-off-hashed {
  background: repeating-linear-gradient(45deg, rgba(156, 163, 175, 0.05) 0px, rgba(156, 163, 175, 0.05) 6px, rgba(156, 163, 175, 0.2) 6px, rgba(156, 163, 175, 0.2) 12px) !important;
  border: 1px solid rgba(156, 163, 175, 0.3) !important;
  color: var(--text-muted);
}

.layer-bg, .layer-fg {
  grid-area: stack;
  width: 100%;
  height: 100%;
  position: relative;
}

.layer-fg {
  z-index: 2;
  pointer-events: none;
}

.layer-fg :deep(*) {
  pointer-events: auto;
}

.layer-bg {
  z-index: 1;
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
  z-index: 10;
}

.resize-handle:hover {
  background-color: rgba(99, 102, 241, 0.5);
}

.no-timeslots-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  text-align: center;
  padding: 32px;
}
.no-timeslots-error .error-icon {
  font-size: 48px;
  margin-bottom: 16px;
}
.no-timeslots-error .error-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}
.mini-grid .grid-header-cell,
.mini-grid .grid-time-cell {
  font-size: 0.7em;
  padding: 4px;
}
</style>
