<template>
  <div
    v-if="show && courses.length > 0"
    ref="containerRef"
    class="course-popin-container glass-morphism animate-pop"
    :style="{ top: y + 'px', left: x + 'px' }"
  >
    <!-- En-tête Draggable -->
    <div class="popin-header" @mousedown="startDrag">
      <div class="header-title-group">
        <span v-if="courses.length > 1" class="header-badge">{{ courses.length }} sélectionnés</span>
        <span class="header-badge duration-badge" style="background-color: rgba(16, 185, 129, 0.08); color: #059669; border-color: rgba(16, 185, 129, 0.2);">⏱️ {{ totalDurationHours }}</span>
        <span v-if="headerWeekTypeLabel" class="header-badge week-badge">🔄 {{ headerWeekTypeLabel }}</span>
        <span v-if="headerPeriodCodes" class="header-badge period-badge">📅 {{ headerPeriodCodes }}</span>
      </div>
      <button class="btn-close" @click="$emit('close')">×</button>
    </div>

    <!-- Corps de la Fiche T -->
    <div class="popin-body">
      <!-- Section Matière (singulier : un cours n'a qu'un seul subject_id, contrairement aux
           autres sections ci-dessous qui sont toutes des relations N-N) -->
      <div class="consolidated-section">
        <div class="section-title">{{ subjectCount }} 📖 Matière</div>
        <div v-if="isSingle" class="editable-field" :style="subjectFieldStyle">
          <SearchableSelect
            :modelValue="singleCourse.subject_id ?? null"
            :options="subjectOptions"
            placeholder="-- Aucune matière --"
            @update:modelValue="(val: any) => updateCourseField('subject_id', val)"
          />
        </div>
        <div v-else class="chips-container">
          <ConsolidatedChip v-for="chip in consolidatedSubjects" :key="chip.label" v-bind="chip" />
        </div>
      </div>

      <!-- Sections des ressources N-N, dans l'ordre demandé — un seul bloc piloté par
           RESOURCE_TYPES plutôt que 7 blocs quasi-identiques copiés-collés. -->
      <div v-for="rt in RESOURCE_TYPES" :key="rt.key" class="consolidated-section">
        <div class="section-title">{{ distinctCount(rt.key) }} {{ rt.icon }} {{ rt.label }}</div>
        <SearchableMultiSelect
          v-if="isSingle"
          :modelValue="(singleCourse as any)[rt.key]"
          :options="rt.options.value"
          :highlightValues="highlightFor(rt.key)"
          @update:modelValue="(ids: number[]) => updateCourseField(rt.key, ids)"
        />
        <div v-else class="chips-container">
          <ConsolidatedChip v-for="chip in consolidateResource(rt.key, rt.nameFn)" :key="chip.label" v-bind="chip" />
        </div>
      </div>

      <!-- Salles : section séparée, voir commentaire de RESOURCE_TYPES ci-dessus. -->
      <div class="consolidated-section">
        <div class="section-title">{{ classroomRequirementCount }} 🏢 Salles</div>
        <div v-if="isSingle" class="editable-field">
          <OwnedRelationField
            :modelValue="classroomRequirementIds"
            :field="classroomRequirementField"
            :parentRecord="singleCourse"
            liveSync
            highlightField="classroom_id"
            :highlightValues="underventilatedClassroomIds"
            @update:modelValue="onClassroomRequirementIdsUpdated"
          />
        </div>
        <div v-else class="chips-container">
          <ConsolidatedChip v-for="chip in consolidatedClassroomRequirements" :key="chip.label" v-bind="chip" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Fiche T : détail d'un cours sélectionné (édition directe des ressources) ou vue consolidée en
// lecture seule de plusieurs cours sélectionnés à la fois. Le mode édition (multiselect générique
// + surlignage des ressources insuffisamment ventilées) n'est actif qu'à 1 seul cours sélectionné
// — au-delà, l'ambiguïté d'une édition en masse (quel cours modifier ? quel enfant surligner ?)
// n'a pas de réponse évidente, donc on garde l'affichage consolidé existant.
import { ref, computed, onMounted, inject, watch } from 'vue';
import ConsolidatedChip from './ConsolidatedChip.vue';
import SearchableSelect from './SearchableSelect.vue';
import SearchableMultiSelect from './SearchableMultiSelect.vue';
import OwnedRelationField from './widgets/OwnedRelationField.vue';
import { Course, Teacher, NonTeachingStaff, Division, Classroom, Timeslot, Group, ClassPart, Material, Period } from '../types';
import { getTeacherName, getDivisionName, getClassroomName, getNonTeachingStaffName } from '../utils/resourceFormatters';
import { useDataStore } from '../stores/data';
import * as api from '../services/api';

const dataStore = useDataStore();

const props = defineProps<{
  show: boolean;
  courses: Course[];
  teachers: Teacher[];
  nonTeachingStaffs: NonTeachingStaff[];
  divisions: Division[];
  classrooms: Classroom[];
  timeslots: Timeslot[];
  groups: Group[];
  classParts: ClassPart[];
  materials: Material[];
  periods: Period[];
  subjects: any[];
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'course-updated', course: Course): void;
  (e: 'error', message: string): void;
}>();

const isSingle = computed(() => props.courses.length === 1);
const singleCourse = computed(() => props.courses[0]);

const totalDurationHours = computed(() => {
  const sumMinutes = props.courses.reduce((acc, c) => acc + (c.duration_minutes || 0), 0);
  const h = Math.floor(sumMinutes / 60);
  const m = sumMinutes % 60;
  const mStr = String(m).padStart(2, '0');
  return `${h}h${mStr}`;
});

// LIBELLÉ DE SEMAINE (EN-TÊTE) — résolu via le schéma OpenAPI déjà injecté par App.vue (même
// mécanisme que GenericListModal.vue), à partir des options attachées à week_type dans son info
// dict (backend/app/models/course.py) plutôt qu'un mapping dupliqué en dur ici.
const openApiSpec = inject<any>('openApiSpec', ref(null));

const weekTypeOptions = computed(() => {
  const schema = openApiSpec.value?.components?.schemas?.['courses_CreatePayload'];
  return schema?.properties?.week_type?.options || [];
});

function weekTypeLabelFor(weekType: string): string {
  const opt = weekTypeOptions.value.find((o: any) => o.value === weekType);
  return opt?.label || weekType;
}

const headerWeekTypeLabel = computed(() => {
  const distinct = new Set(props.courses.map(c => c.week_type));
  if (distinct.size === 0) return '';
  if (distinct.size > 1) return 'Semaines multiples';
  return weekTypeLabelFor(props.courses[0].week_type);
});

const headerPeriodCodes = computed(() => {
  const hasNonAnnual = props.courses.some(c => !!c.period_type_id);
  if (!hasNonAnnual) return '';
  const codes = new Set<string>();
  props.courses.forEach(c => {
    (c.period_ids || []).forEach(pid => {
      const period = props.periods.find(p => p.id === pid);
      if (period) codes.add(period.code);
    });
  });
  return Array.from(codes).join(', ');
});

// COMPTEURS — nombre d'IDs distincts de ce type sur le(s) cours sélectionné(s), affiché à gauche
// du libellé de section, remplace les étiquettes "Sans <type>" supprimées.
function distinctCount(field: string): number {
  const set = new Set<number>();
  props.courses.forEach(c => ((c as any)[field] || []).forEach((id: number) => set.add(id)));
  return set.size;
}

const subjectCount = computed(() => new Set(props.courses.map(c => c.subject_id).filter((id): id is number => id != null)).size);

// OPTIONS DES MULTISELECT (mode 1 cours) — construites directement depuis les listes reçues en
// props, sous la forme {value, label} attendue par SearchableMultiSelect/SearchableSelect.
const subjectOptions = computed(() => props.subjects.map((s: any) => ({ value: s.id, label: s.name || s.display_name })));
const teacherOptions = computed(() => props.teachers.map((t: any) => ({ value: t.id, label: t.display_name })));
const divisionOptions = computed(() => props.divisions.map((d: any) => ({ value: d.id, label: d.display_name })));
const groupOptions = computed(() => props.groups.map((g: any) => ({ value: g.id, label: g.display_name })));
const classPartOptions = computed(() => props.classParts.map((cp: any) => ({ value: cp.id, label: cp.display_name })));
const nonTeachingStaffOptions = computed(() => props.nonTeachingStaffs.map((s: any) => ({ value: s.id, label: s.display_name })));
const materialOptions = computed(() => props.materials.map((m: any) => ({ value: m.id, label: m.display_name || m.name })));

// Pilote les 6 sections de ressources N-N à plat (ordre demandé : Enseignants, Divisions,
// Groupes, Parties de classe, Personnel, Matériels) — un seul bloc de template les parcourt tous
// plutôt que 6 blocs copiés-collés. `nameFn` sert uniquement au mode consolidé (2+ cours).
// Salles : section séparée ci-dessous (classroom_requirement_ids n'est plus une simple liste
// d'ids de Classroom mais une collection possédée de CourseClassroomRequirement avec quantity —
// voir plan salles §1.4/§1.5/§1.7 — rendue par OwnedRelationField, pas SearchableMultiSelect).
const RESOURCE_TYPES = [
  { key: 'teacher_ids', label: 'Enseignants', icon: '👨‍🏫', options: teacherOptions, nameFn: (id: number) => getTeacherName(props.teachers, id) },
  { key: 'division_ids', label: 'Divisions', icon: '🎒', options: divisionOptions, nameFn: (id: number) => getDivisionName(props.divisions, id) },
  { key: 'group_ids', label: 'Groupes', icon: '👥', options: groupOptions, nameFn: (id: number) => props.groups.find((g: any) => g.id === id)?.display_name || 'Inconnu' },
  { key: 'class_part_ids', label: 'Parties de classe', icon: '🧩', options: classPartOptions, nameFn: (id: number) => props.classParts.find((cp: any) => cp.id === id)?.display_name || 'Inconnu' },
  { key: 'non_teaching_staff_ids', label: 'Personnel', icon: '🧑‍💼', options: nonTeachingStaffOptions, nameFn: (id: number) => getNonTeachingStaffName(props.nonTeachingStaffs, id) },
  { key: 'material_ids', label: 'Matériels', icon: '📦', options: materialOptions, nameFn: (id: number) => props.materials.find((m: any) => m.id === id)?.display_name || 'Inconnu' },
];

// SECTION SALLES — voir commentaire ci-dessus. `field.options` embarque classroom_id (en plus de
// value/label) : nécessaire en mode liveSync d'OwnedRelationField, qui ne charge jamais les lignes
// complètes lui-même (voir son commentaire de tête) — c'est ce qui permet au surlignage
// (highlightField="classroom_id") de fonctionner sans aller-retour serveur supplémentaire ici.
function classroomRequirementLabel(classroomId: number, quantity: number): string {
  const name = getClassroomName(props.classrooms, classroomId);
  return quantity > 1 ? `${name} ×${quantity}` : name;
}

const classroomRequirementField = computed(() => ({
  resource: 'course_classroom_requirements',
  parentField: 'course_id',
  label: 'Salles',
  options: dataStore.courseClassroomRequirements.map(r => ({
    value: r.id,
    label: classroomRequirementLabel(r.classroom_id, r.quantity),
    classroom_id: r.classroom_id,
  })),
}));


const classroomRequirementCount = computed(() => {
  const set = new Set<number>();
  props.courses.forEach(c => (dataStore.courseClassroomIdsMap[c.id] || []).forEach(id => set.add(id)));
  return set.size;
});

// Écart de quantité non ventilé, {classroom_id: quantité manquante} — voir plan salles §1.5,
// contrairement aux 6 autres relations (simple liste d'ids manquants).
const underventilatedClassroomIds = computed<number[]>(() => {
  if (!showUnderventilatedHighlight.value) return [];
  const dict = singleCourse.value.underventilated_resource_ids?.classroom_requirement_ids;
  return dict ? Object.keys(dict).map(Number) : [];
});

// OwnedRelationField (mode liveSync) persiste lui-même via GenericListModal, mais ne connaît pas
// la ligne complète — il émet update:modelValue avec les ids frais après chaque mutation (voir
// GenericListRow.vue pour le même pattern) : sans relayer cet évènement vers un état local, ses
// tags resteraient figés sur l'instantané initial de classroom_requirement_ids après un
// ajout/retrait de salle depuis la popin d'édition.
const classroomRequirementIds = ref<number[]>([]);
watch(() => singleCourse.value?.classroom_requirement_ids, (val) => {
  classroomRequirementIds.value = val || [];
}, { immediate: true });

function onClassroomRequirementIdsUpdated(ids: number[]) {
  classroomRequirementIds.value = ids;
}

const consolidatedClassroomRequirements = computed(() => {
  const counts: Record<string, number> = {};
  props.courses.forEach(c => {
    const ids = dataStore.courseClassroomIdsMap[c.id] || [];
    if (ids.length === 0) return;
    const label = ids.map(id => getClassroomName(props.classrooms, id)).join(', ');
    counts[label] = (counts[label] || 0) + 1;
  });
  const total = props.courses.length;
  return Object.entries(counts).map(([label, count]) => ({
    label, count, total, isDivergent: count < total,
  })).sort((a, b) => b.count - a.count);
});


// SURLIGNAGE DES RESSOURCES INSUFFISAMMENT VENTILÉES — n'a de sens que pour un cours composé avec
// des enfants pas encore FULLY_VENTILATED (voir Course.underventilated_resource_ids, recalculé
// côté backend au même endroit que decomposition_status).
const showUnderventilatedHighlight = computed(() => {
  if (!isSingle.value) return false;
  const c = singleCourse.value;
  return !!c.is_composed && (c.children_ids?.length || 0) > 0 && c.decomposition_status !== 'FULLY_VENTILATED';
});

function highlightFor(field: string): number[] {
  if (!showUnderventilatedHighlight.value) return [];
  return singleCourse.value.underventilated_resource_ids?.[field] || [];
}

// Couleur de fond de la Matière = subject.color (mêmes teintes que CourseCard/TimetableGrid).
function hexToRgba(hex: string, alpha: number): string {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m) return hex;
  const num = parseInt(m[1], 16);
  return `rgba(${(num >> 16) & 255}, ${(num >> 8) & 255}, ${num & 255}, ${alpha})`;
}

const subjectFieldStyle = computed(() => {
  if (!isSingle.value) return {};
  const subj = props.subjects.find((s: any) => s.id === singleCourse.value.subject_id);
  if (!subj?.color) return {};
  return { backgroundColor: hexToRgba(subj.color, 0.15), borderColor: hexToRgba(subj.color, 0.5) };
});

// PERSISTANCE — appelle directement l'API générique (déjà validée côté serveur : conflits de
// ressources, cascade Group<->ClassPart...) puis remonte l'objet cours COMPLET renvoyé par le
// serveur (pas seulement le champ modifié localement) : App.vue le réinjecte dans son ref
// `courses`, ce qui propage par réactivité tout effet de bord (cascade, recalcul de
// decomposition_status/underventilated_resource_ids) à cette Fiche T et au reste de l'IHM.
async function updateCourseField(field: string, value: any) {
  const course = singleCourse.value;
  try {
    const updated = await api.updateGenericItem('courses', course.id, { [field]: value });
    emit('course-updated', updated);
  } catch (e: any) {
    emit('error', e.message || "Erreur lors de la mise à jour du cours.");
  }
}

// Coordonnées absolues du Popin
const x = ref(100);
const y = ref(100);

const containerRef = ref<HTMLElement | null>(null);

onMounted(() => {
  // Positionnement par défaut en haut à droite
  x.value = window.innerWidth - 400;
  y.value = 140;
});

// Drag and drop natif
let startX = 0;
let startY = 0;
let dragOffsetX = 0;
let dragOffsetY = 0;

function startDrag(event: MouseEvent) {
  // Empêcher le drag si on clique sur le bouton fermer
  if ((event.target as HTMLElement).classList.contains('btn-close')) return;

  startX = event.clientX;
  startY = event.clientY;
  dragOffsetX = x.value;
  dragOffsetY = y.value;

  document.addEventListener('mousemove', onDrag);
  document.addEventListener('mouseup', stopDrag);
  document.body.style.userSelect = 'none';
}

function onDrag(event: MouseEvent) {
  const diffX = event.clientX - startX;
  const diffY = event.clientY - startY;

  // Limites d'écran basées sur la taille RÉELLE du popin (containerRef) plutôt qu'une largeur/
  // hauteur figée : la popin étant désormais redimensionnable (resize: both), une valeur figée
  // laisserait un popin agrandi dépasser de l'écran une fois glissé.
  const width = containerRef.value?.offsetWidth || 380;
  const height = containerRef.value?.offsetHeight || 480;
  x.value = Math.max(10, Math.min(window.innerWidth - width - 10, dragOffsetX + diffX));
  y.value = Math.max(10, Math.min(window.innerHeight - height - 10, dragOffsetY + diffY));
}

function stopDrag() {
  document.removeEventListener('mousemove', onDrag);
  document.removeEventListener('mouseup', stopDrag);
  document.body.style.userSelect = '';
}

// LOGIQUE DE CONSOLIDATION (mode 2+ cours sélectionnés, lecture seule)

function consolidate(attrGetter: (c: Course) => string) {
  const counts: Record<string, number> = {};
  props.courses.forEach(c => {
    const val = attrGetter(c) || 'Non défini';
    counts[val] = (counts[val] || 0) + 1;
  });

  const total = props.courses.length;
  return Object.entries(counts).map(([label, count]) => ({
    label,
    count,
    total,
    isDivergent: count < total
  })).sort((a, b) => b.count - a.count);
}

// Variante pour les ressources N-N (hors Matière) : un cours sans aucune ressource de ce type ne
// produit plus de chip "Sans X" — il est simplement absent du regroupement (le compteur de
// section indique déjà le total de ressources distinctes).
function consolidateResource(field: string, nameFn: (id: number) => string) {
  const counts: Record<string, number> = {};
  props.courses.forEach(c => {
    const ids: number[] = (c as any)[field] || [];
    if (ids.length === 0) return;
    const label = ids.map(nameFn).join(', ');
    counts[label] = (counts[label] || 0) + 1;
  });
  const total = props.courses.length;
  return Object.entries(counts).map(([label, count]) => ({
    label,
    count,
    total,
    isDivergent: count < total
  })).sort((a, b) => b.count - a.count);
}

const consolidatedSubjects = computed(() => {
  return consolidate(c => props.subjects.find((s: any) => s.id === c.subject_id)?.short_name || 'Aucune Matière');
});
</script>

<style scoped>
.course-popin-container {
  position: fixed;
  width: 380px;
  height: 480px;
  min-width: 320px;
  min-height: 220px;
  max-width: 90vw;
  max-height: 90vh;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--border-color);
  border-radius: 14px;
  box-shadow: var(--shadow-lg), 0 10px 30px rgba(15, 23, 42, 0.15);
  z-index: 5000;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  /* Poignée de redimensionnement native (coin bas-droit) — largeur ET hauteur, aucun JS custom
     nécessaire. Fonctionne avec overflow:hidden (préserve les coins arrondis du popin). */
  resize: both;
}

.glass-morphism {
  backdrop-filter: blur(25px);
}

.animate-pop {
  animation: popIn 0.22s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes popIn {
  from {
    opacity: 0;
    transform: scale(0.95) translateY(5px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

/* En-tête Draggable */
.popin-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 8px;
  background-color: rgba(0, 0, 0, 0.02);
  border-bottom: 1px solid var(--border-color);
  cursor: grab;
  flex-shrink: 0;
}

.popin-header:active {
  cursor: grabbing;
}

.header-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.header-badge {
  font-size: 14px;
  font-weight: 600;
  background-color: rgba(99, 102, 241, 0.08);
  color: var(--accent-primary);
  border: 1px solid rgba(99, 102, 241, 0.2);
  padding: 3px 8px;
  border-radius: var(--radius-lg);
}

.week-badge {
  background-color: rgba(14, 165, 233, 0.08);
  color: rgb(2, 132, 199);
  border-color: rgba(14, 165, 233, 0.2);
}

.period-badge {
  background-color: rgba(168, 85, 247, 0.08);
  color: rgb(147, 51, 234);
  border-color: rgba(168, 85, 247, 0.2);
}

.btn-close {
  background: transparent;
  border: none;
  font-size: 20px;
  color: var(--text-muted);
  cursor: pointer;
  line-height: 1;
  padding: 4px;
  border-radius: var(--radius-md);
  transition: all 0.2s;
}

.btn-close:hover {
  color: var(--text-primary);
  background-color: rgba(0, 0, 0, 0.05);
}

/* Corps de popin scrollable */
.popin-body {
  padding: 12px 16px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* Étiquette de section à gauche + widget à droite sur une seule ligne (plutôt qu'empilés) : la
   Fiche T listant 8 types de ressources, ce gain de hauteur par section évite un ascenseur
   systématique sans avoir à agrandir la popin. */
.consolidated-section {
  display: grid;
  grid-template-columns: 116px 1fr;
  align-items: start;
  gap: 8px;
  min-height: 38px;
}

/* Une cellule de grille garde par défaut min-width: auto (jamais plus étroite que son contenu) :
   sans ce reset, le widget de droite (tags, texte non coupé) pousse au-delà de la colonne 1fr et
   provoque un débordement horizontal du popin plutôt que de s'y adapter. */
.consolidated-section > *:last-child {
  min-width: 0;
}

.section-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--text-muted);
  letter-spacing: 0.3px;
  line-height: 1.3;
  padding-top: 11px;
}

.chips-container {
  display: flex;
  flex-wrap: wrap;
  align-content: flex-start;
  align-items: center;
  gap: 6px;
  min-height: 38px;
}

.editable-field {
  border-radius: var(--radius-md);
  transition: background-color 0.2s, border-color 0.2s;
}
</style>
