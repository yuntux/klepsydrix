<template>
  <div class="pref-grid-container glass-morphism">
    <!-- Barre de configuration (Sélecteurs de ressource et d'outil) -->
    <div class="pref-toolbar">
      <div class="toolbar-section">
        <h3 class="toolbar-title">🎨 Grille de Vœux & Indisponibilités</h3>
      </div>

      <div class="toolbar-section selectors-group">
        <label class="selector-item">
          <span>Type de Ressource :</span>
          <select v-model="resourceType" class="select-custom" @change="onResourceChange">
            <option value="Teacher">👨‍🏫 Enseignant</option>
            <option value="Classroom">🏢 Salle</option>
            <option value="Division">🎒 Classe (Division)</option>
          </select>
        </label>

        <label class="selector-item">
          <span>Ressource :</span>
          <select v-model="resourceId" class="select-custom" @change="loadPreferences">
            <option v-for="item in resourceOptions" :key="item.id" :value="item.id">
              {{ item.name }}
            </option>
            <option v-if="resourceOptions.length === 0" value="">
              Aucune ressource disponible
            </option>
          </select>
        </label>
      </div>

      <!-- Palette de pinceaux (Gomme, Vert, Orange, Rouge) -->
      <div class="toolbar-section brush-palette">
        <span class="palette-label">Outil Vœu :</span>
        <div class="brush-buttons">
          <button 
            class="btn-brush brush-preferred" 
            :class="{ active: activeBrush === 'Preferred' }"
            @click="activeBrush = 'Preferred'"
            title="Préféré (Vert - Bonus)"
          >
            <span class="brush-dot bg-green"></span>
            Préféré
          </button>
          
          <button 
            class="btn-brush brush-undesirable" 
            :class="{ active: activeBrush === 'Undesirable' }"
            @click="activeBrush = 'Undesirable'"
            title="Indésirable (Orange - Pénalité)"
          >
            <span class="brush-dot bg-orange"></span>
            Indésirable
          </button>
          
          <button 
            class="btn-brush brush-unsuited" 
            :class="{ active: activeBrush === 'Unsuited' }"
            @click="activeBrush = 'Unsuited'"
            title="Indisponible / Strict (Rouge - Interdit)"
          >
            <span class="brush-dot bg-red"></span>
            Indisponible
          </button>

          <button 
            class="btn-brush brush-neutral" 
            :class="{ active: activeBrush === 'Neutral' }"
            @click="activeBrush = 'Neutral'"
            title="Gomme (Neutre - Pas de contrainte)"
          >
            <span class="brush-dot bg-neutral"></span>
            Neutre
          </button>
        </div>
      </div>
    </div>

    <!-- Grille interactive des voeux -->
    <div class="grid-wrapper">
      <div class="timetable-grid">
        <!-- Coin supérieur gauche -->
        <div class="grid-header-cell">Horaire</div>

        <!-- En-têtes des jours (Lundi au Samedi) -->
        <div v-for="day in days" :key="day.value" class="grid-header-cell">
          {{ day.label }}
        </div>

        <!-- Lignes d'heures (8h à 17h) -->
        <template v-for="hour in hours" :key="hour">
          <!-- Cellule d'heure à gauche -->
          <div class="grid-time-cell">
            {{ hour }}h00 - {{ hour + 1 }}h00
          </div>

          <!-- Cellules de la grille de voeux -->
          <div
            v-for="day in days"
            :key="day.value"
            class="grid-cell clickable-cell"
            :class="getCellClass(day.value, hour)"
            @click="paintCell(day.value, hour)"
          >
            <div class="cell-label">
              {{ getCellLabel(day.value, hour) }}
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { Teacher, Classroom, Division, Timeslot } from '../types';
import * as api from '../services/api';

const props = defineProps<{
  teachers: Teacher[];
  classrooms: Classroom[];
  divisions: Division[];
  timeslots: Timeslot[];
}>();

const resourceType = ref<'Teacher' | 'Classroom' | 'Division'>('Teacher');
const resourceId = ref<number | ''>('');
const activeBrush = ref<'Preferred' | 'Undesirable' | 'Unsuited' | 'Neutral'>('Unsuited');

// Dictionnaire local des préférences chargées depuis l'API
// Clé: "day-hour", Valeur: PreferenceLevel ('Preferred', 'Undesirable', 'Unsuited')
const preferencesMap = ref<Record<string, string>>({});

const days = [
  { value: 1, label: 'Lundi' },
  { value: 2, label: 'Mardi' },
  { value: 3, label: 'Mercredi' },
  { value: 4, label: 'Jeudi' },
  { value: 5, label: 'Vendredi' },
  { value: 6, label: 'Samedi' },
];

const hours = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17];

const resourceOptions = computed(() => {
  if (resourceType.value === 'Teacher') {
    return props.teachers.map(t => ({ id: t.id, name: t.name }));
  } else if (resourceType.value === 'Classroom') {
    return props.classrooms.map(c => ({ id: c.id, name: c.name }));
  } else {
    return props.divisions.map(d => ({ id: d.id, name: d.name }));
  }
});

function onResourceChange() {
  if (resourceOptions.value.length > 0) {
    resourceId.value = resourceOptions.value[0].id;
    loadPreferences();
  } else {
    resourceId.value = '';
    preferencesMap.value = {};
  }
}

// Charger les préférences depuis l'API
async function loadPreferences() {
  if (!resourceId.value) return;
  try {
    const list = await fetch(`/api/generic/resource_preferences?resource_type=${resourceType.value}&resource_id=${resourceId.value}`)
      .then(res => res.json())
      .then(data => data.items || []);
    
    const newMap: Record<string, string> = {};
    list.forEach((pref: any) => {
      const ts = props.timeslots.find(t => t.id === pref.timeslot_id);
      if (ts) {
        newMap[`${ts.day_of_week}-${ts.hour}`] = pref.preference_level;
      }
    });
    preferencesMap.value = newMap;
  } catch (err) {
    console.error("Erreur de chargement des préférences", err);
  }
}

// Peindre la cellule avec le pinceau actif
async function paintCell(day: number, hour: number) {
  if (!resourceId.value) return;

  const ts = props.timeslots.find(t => t.day_of_week === day && t.hour === hour);
  if (!ts) return;

  const key = `${day}-${hour}`;
  const originalLevel = preferencesMap.value[key] || 'Neutral';
  const newLevel = activeBrush.value;

  if (originalLevel === newLevel) return;

  // Optimistic UI update
  if (newLevel === 'Neutral') {
    delete preferencesMap.value[key];
  } else {
    preferencesMap.value[key] = newLevel;
  }

  try {
    const response = await fetch('/api/generic/resource_preferences', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        resource_type: resourceType.value,
        resource_id: resourceId.value,
        timeslot_id: ts.id,
        preference_level: newLevel,
      }),
    });
    if (!response.ok) {
      throw new Error("Erreur de sauvegarde");
    }
  } catch (err) {
    // Revert on error
    if (originalLevel === 'Neutral') {
      delete preferencesMap.value[key];
    } else {
      preferencesMap.value[key] = originalLevel;
    }
    alert("Impossible d'enregistrer le vœu. Veuillez réessayer.");
  }
}

function getCellClass(day: number, hour: number): string {
  const key = `${day}-${hour}`;
  const level = preferencesMap.value[key];
  if (level === 'Preferred') return 'pref-level-preferred';
  if (level === 'Undesirable') return 'pref-level-undesirable';
  if (level === 'Unsuited') return 'pref-level-unsuited';
  return 'pref-level-neutral';
}

function getCellLabel(day: number, hour: number): string {
  const key = `${day}-${hour}`;
  const level = preferencesMap.value[key];
  if (level === 'Preferred') return 'Vert / Préféré';
  if (level === 'Undesirable') return 'Orange / Indésirable';
  if (level === 'Unsuited') return 'Rouge / Indisponible';
  return 'Neutre';
}

onMounted(() => {
  onResourceChange();
});

// Re-charger si les listes changent
watch(resourceOptions, () => {
  if (!resourceId.value && resourceOptions.value.length > 0) {
    resourceId.value = resourceOptions.value[0].id;
    loadPreferences();
  }
});
</script>

<style scoped>
.pref-grid-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(12px);
  padding: 20px;
  gap: 20px;
}

.pref-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  background-color: var(--bg-surface);
  border: 1px solid var(--border-color);
  padding: 16px 20px;
  border-radius: 10px;
}

.toolbar-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.selectors-group {
  display: flex;
  align-items: center;
  gap: 16px;
}

.selector-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  color: var(--text-secondary);
}

.select-custom {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 6px 12px;
  border-radius: 6px;
  outline: none;
  cursor: pointer;
  font-family: inherit;
  font-size: 13px;
  min-width: 180px;
}

.select-custom:focus {
  border-color: var(--accent-primary);
}

.brush-palette {
  display: flex;
  align-items: center;
  gap: 12px;
}

.palette-label {
  font-size: 13.5px;
  color: var(--text-secondary);
  font-weight: 600;
}

.brush-buttons {
  display: flex;
  gap: 8px;
}

.btn-brush {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  padding: 6px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-brush:hover {
  background-color: var(--bg-surface);
  color: var(--text-primary);
  border-color: var(--text-secondary);
}

.btn-brush.active {
  color: var(--text-primary);
}

.btn-brush.brush-preferred.active {
  background-color: rgba(16, 185, 129, 0.15);
  border-color: #10b981;
  box-shadow: 0 0 10px rgba(16, 185, 129, 0.25);
  color: #10b981;
}

.btn-brush.brush-undesirable.active {
  background-color: rgba(245, 158, 11, 0.15);
  border-color: #f59e0b;
  box-shadow: 0 0 10px rgba(245, 158, 11, 0.25);
  color: #f59e0b;
}

.btn-brush.brush-unsuited.active {
  background-color: rgba(239, 68, 68, 0.15);
  border-color: #ef4444;
  box-shadow: 0 0 10px rgba(239, 68, 68, 0.25);
  color: #ef4444;
}

.btn-brush.brush-neutral.active {
  background-color: var(--bg-surface);
  border-color: #9ca3af;
  color: var(--text-primary);
}

.brush-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.bg-green { background-color: #10b981; }
.bg-orange { background-color: #f59e0b; }
.bg-red { background-color: #ef4444; }
.bg-neutral { background-color: #6b7280; }

/* Grille */
.grid-wrapper {
  flex: 1;
  overflow: auto;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background-color: var(--bg-secondary);
  box-shadow: var(--shadow-lg);
}

.timetable-grid {
  display: grid;
  grid-template-columns: 80px repeat(6, minmax(130px, 1fr));
  grid-template-rows: 50px repeat(10, minmax(65px, 1fr));
  min-width: 900px;
  height: 100%;
}

.grid-header-cell {
  background-color: var(--bg-surface);
  border-bottom: 2px solid var(--border-color);
  border-right: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 13.5px;
  color: var(--text-primary);
  position: sticky;
  top: 0;
  z-index: 2;
}

.grid-time-cell {
  background-color: var(--bg-surface);
  border-right: 2px solid var(--border-color);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-secondary);
  position: sticky;
  left: 0;
  z-index: 2;
}

.grid-cell {
  border-right: 1px solid var(--border-color);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  position: relative;
  background-color: var(--bg-card);
}

.clickable-cell {
  cursor: pointer;
  user-select: none;
}

.clickable-cell:hover {
  filter: brightness(1.15);
  transform: scale(1.01);
  z-index: 1;
}

/* Couleurs des voeux */
.pref-level-preferred {
  background-color: rgba(16, 185, 129, 0.12) !important;
  border: 1px solid rgba(16, 185, 129, 0.35);
  color: #10b981;
}

.pref-level-undesirable {
  background-color: rgba(245, 158, 11, 0.12) !important;
  border: 1px solid rgba(245, 158, 11, 0.35);
  color: #f59e0b;
}

.pref-level-unsuited {
  background-color: rgba(239, 68, 68, 0.12) !important;
  border: 1px solid rgba(239, 68, 68, 0.35);
  color: #ef4444;
}

.pref-level-neutral {
  background-color: var(--bg-card) !important;
  color: var(--text-muted);
}

.cell-label {
  font-size: 11.5px;
  font-weight: 600;
}
</style>
