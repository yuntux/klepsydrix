<template>
  <div 
    v-if="show && courses.length > 0" 
    class="course-popin-container glass-morphism animate-pop"
    :style="{ top: y + 'px', left: x + 'px' }"
  >
    <!-- En-tête Draggable -->
    <div class="popin-header" @mousedown="startDrag">
      <div class="header-title-group">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="icon-header">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h3.75M9 15h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-.621-.504-1.125-1.125-1.125H9.75M8.25 21h8.25a2.25 2.25 0 002.25-2.25V5.75A2.25 2.25 0 0016.5 3.5h-8.25A2.25 2.25 0 006 5.75v13a2.25 2.25 0 002.25 2.25Z" />
        </svg>
        <span class="header-text">Fiche T Cumulée</span>
        <span class="header-badge">{{ courses.length }} sélectionnés</span>
      </div>
      <button class="btn-close" @click="$emit('close')">×</button>
    </div>

    <!-- Corps de la Fiche T consolidée -->
    <div class="popin-body">
      <!-- Section Matières -->
      <div class="consolidated-section">
        <div class="section-title">📖 Matières</div>
        <div class="chips-container">
          <ConsolidatedChip 
            v-for="chip in consolidatedSubjects" 
            :key="chip.label" 
            v-bind="chip" 
          />
        </div>
      </div>

      <!-- Section Enseignants -->
      <div class="consolidated-section">
        <div class="section-title">👨‍🏫 Enseignants</div>
        <div class="chips-container">
          <ConsolidatedChip 
            v-for="chip in consolidatedTeachers" 
            :key="chip.label" 
            v-bind="chip" 
          />
        </div>
      </div>

      <!-- Section Salles -->
      <div class="consolidated-section">
        <div class="section-title">🏢 Salles</div>
        <div class="chips-container">
          <ConsolidatedChip 
            v-for="chip in consolidatedClassrooms" 
            :key="chip.label" 
            v-bind="chip" 
          />
        </div>
      </div>

      <!-- Section Divisions -->
      <div class="consolidated-section">
        <div class="section-title">🎒 Classes (Divisions)</div>
        <div class="chips-container">
          <ConsolidatedChip 
            v-for="chip in consolidatedDivisions" 
            :key="chip.label" 
            v-bind="chip" 
          />
        </div>
      </div>

      <!-- Section Créneaux -->
      <div class="consolidated-section">
        <div class="section-title">📅 Créneaux Horaires</div>
        <div class="chips-container">
          <ConsolidatedChip 
            v-for="chip in consolidatedTimeslots" 
            :key="chip.label" 
            v-bind="chip" 
          />
        </div>
      </div>

      <!-- Section Alternances -->
      <div class="consolidated-section">
        <div class="section-title">🔄 Semaines Alternées</div>
        <div class="chips-container">
          <ConsolidatedChip 
            v-for="chip in consolidatedWeeks" 
            :key="chip.label" 
            v-bind="chip" 
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import ConsolidatedChip from './ConsolidatedChip.vue';
import { Course, Teacher, Division, Classroom, Timeslot } from '../types';

const props = defineProps<{
  show: boolean;
  courses: Course[];
  teachers: Teacher[];
  divisions: Division[];
  classrooms: Classroom[];
  timeslots: Timeslot[];
}>();

defineEmits<{
  (e: 'close'): void;
}>();

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

// LOGIQUE DE CONSOLIDATION DYNAMIQUE

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

// Consolidations par ressource
const consolidatedSubjects = computed(() => {
  return consolidate(c => c.subject || 'Aucune Matière');
});

const consolidatedTeachers = computed(() => {
  return consolidate(c => {
    const t = props.teachers.find(item => item.id === c.teacher_id);
    return t ? t.name : 'Sans Enseignant';
  });
});

const consolidatedClassrooms = computed(() => {
  return consolidate(c => {
    const rm = props.classrooms.find(item => item.id === c.classroom_id);
    return rm ? rm.name : 'Sans Salle';
  });
});

const consolidatedDivisions = computed(() => {
  return consolidate(c => {
    const d = props.divisions.find(item => item.id === c.division_id);
    return d ? d.name : 'Sans Division';
  });
});

const consolidatedTimeslots = computed(() => {
  return consolidate(c => {
    if (!c.timeslot_id) return 'Non planifié';
    const ts = props.timeslots.find(item => item.id === c.timeslot_id);
    if (!ts) return 'Créneau Inconnu';
    const jours = ['Dimanche', 'Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi'];
    return `${jours[ts.day_of_week]} ${ts.hour}h00`;
  });
});

const consolidatedWeeks = computed(() => {
  return consolidate(c => {
    const sess = c.sessions && c.sessions[0];
    if (!sess) return 'Semaine T (Hebdo)';
    const w = sess.week_type;
    return w === 'A' ? 'Semaine A' : w === 'B' ? 'Semaine B' : 'Semaine T (Hebdo)';
  });
});
</script>

<style scoped>
.course-popin-container {
  position: fixed;
  width: 360px;
  background: rgba(22, 28, 38, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.05);
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
  background-color: rgba(255, 255, 255, 0.03);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  cursor: grab;
}

.popin-header:active {
  cursor: grabbing;
}

.header-title-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.icon-header {
  width: 18px;
  height: 18px;
  color: var(--accent-primary);
}

.header-text {
  font-size: 13.5px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.2px;
}

.header-badge {
  font-size: 10.5px;
  font-weight: 600;
  background-color: rgba(99, 102, 241, 0.18);
  color: #818cf8;
  border: 1px solid rgba(99, 102, 241, 0.25);
  padding: 1px 6px;
  border-radius: 6px;
}

.btn-close {
  background: transparent;
  border: none;
  font-size: 20px;
  color: var(--text-muted);
  cursor: pointer;
  line-height: 1;
  padding: 4px;
  border-radius: 4px;
  transition: all 0.2s;
}

.btn-close:hover {
  color: #fff;
  background-color: rgba(255, 255, 255, 0.06);
}

/* Corps de popin scrollable */
.popin-body {
  padding: 16px;
  max-height: 380px;
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
</style>
