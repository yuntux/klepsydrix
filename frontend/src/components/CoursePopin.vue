<template>
  <div
    v-if="show && courses.length > 0"
    class="course-popin-container glass-morphism animate-pop"
    :style="{ top: y + 'px', left: x + 'px' }"
  >
    <!-- En-tête Draggable -->
    <div class="popin-header" @mousedown="startDrag">
      <div class="header-title-group">
        <span class="header-badge">{{ courses.length }} sélectionné{{ courses.length > 1 ? 's' : '' }}</span>
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
    </div>
  </div>
</template>

<script setup lang="ts">
// Fiche T : détail d'un cours sélectionné (édition directe des ressources) ou vue consolidée en
// lecture seule de plusieurs cours sélectionnés à la fois. Le mode édition (multiselect générique
// + surlignage des ressources insuffisamment ventilées) n'est actif qu'à 1 seul cours sélectionné
// — au-delà, l'ambiguïté d'une édition en masse (quel cours modifier ? quel enfant surligner ?)
// n'a pas de réponse évidente, donc on garde l'affichage consolidé existant.
import { ref, computed, onMounted, inject } from 'vue';
import ConsolidatedChip from './ConsolidatedChip.vue';
import SearchableSelect from './SearchableSelect.vue';
import SearchableMultiSelect from './SearchableMultiSelect.vue';
import { Course, Teacher, NonTeachingStaff, Division, Classroom, Timeslot, Group, ClassPart, Material, Period } from '../types';
import { getTeacherName, getDivisionName, getClassroomName, getNonTeachingStaffName } from '../utils/resourceFormatters';
import * as api from '../services/api';

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
const classroomOptions = computed(() => props.classrooms.map((cr: any) => ({ value: cr.id, label: cr.display_name })));
const nonTeachingStaffOptions = computed(() => props.nonTeachingStaffs.map((s: any) => ({ value: s.id, label: s.display_name })));
const materialOptions = computed(() => props.materials.map((m: any) => ({ value: m.id, label: m.display_name || m.name })));

// Pilote les 7 sections de ressources N-N (ordre demandé : Enseignants, Divisions, Groupes,
// Parties de classe, Salles, Personnel, Matériels) — un seul bloc de template les parcourt tous
// plutôt que 7 blocs copiés-collés. `nameFn` sert uniquement au mode consolidé (2+ cours).
const RESOURCE_TYPES = [
  { key: 'teacher_ids', label: 'Enseignants', icon: '👨‍🏫', options: teacherOptions, nameFn: (id: number) => getTeacherName(props.teachers, id) },
  { key: 'division_ids', label: 'Divisions', icon: '🎒', options: divisionOptions, nameFn: (id: number) => getDivisionName(props.divisions, id) },
  { key: 'group_ids', label: 'Groupes', icon: '👥', options: groupOptions, nameFn: (id: number) => props.groups.find((g: any) => g.id === id)?.display_name || 'Inconnu' },
  { key: 'class_part_ids', label: 'Parties de classe', icon: '🧩', options: classPartOptions, nameFn: (id: number) => props.classParts.find((cp: any) => cp.id === id)?.display_name || 'Inconnu' },
  { key: 'classroom_ids', label: 'Salles', icon: '🏢', options: classroomOptions, nameFn: (id: number) => getClassroomName(props.classrooms, id) },
  { key: 'non_teaching_staff_ids', label: 'Personnel', icon: '🧑‍💼', options: nonTeachingStaffOptions, nameFn: (id: number) => getNonTeachingStaffName(props.nonTeachingStaffs, id) },
  { key: 'material_ids', label: 'Matériels', icon: '📦', options: materialOptions, nameFn: (id: number) => props.materials.find((m: any) => m.id === id)?.display_name || 'Inconnu' },
];

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

onMounted(() => {
  // Positionnement par défaut en haut à droite
  x.value = window.innerWidth - 420;
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

  // Calculer la nouvelle position avec limites d'écran basiques
  x.value = Math.max(10, Math.min(window.innerWidth - 380, dragOffsetX + diffX));
  y.value = Math.max(10, Math.min(window.innerHeight - 300, dragOffsetY + diffY));
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
  return consolidate(c => c.subject || 'Aucune Matière');
});
</script>

<style scoped>
.course-popin-container {
  position: fixed;
  width: 360px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--border-color);
  border-radius: 14px;
  box-shadow: var(--shadow-lg), 0 10px 30px rgba(15, 23, 42, 0.15);
  z-index: 5000;
  overflow: hidden;
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
  padding: 12px 16px;
  background-color: rgba(0, 0, 0, 0.02);
  border-bottom: 1px solid var(--border-color);
  cursor: grab;
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
  font-size: 10.5px;
  font-weight: 600;
  background-color: rgba(99, 102, 241, 0.08);
  color: var(--accent-primary);
  border: 1px solid rgba(99, 102, 241, 0.2);
  padding: 1px 6px;
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
  padding: 16px;
  max-height: 420px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.consolidated-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-title {
  font-size: 11.5px;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--text-muted);
  letter-spacing: 0.5px;
}

.chips-container {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.editable-field {
  border-radius: var(--radius-md);
  transition: background-color 0.2s, border-color 0.2s;
}
</style>
