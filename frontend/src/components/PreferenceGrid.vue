<template>
  <div class="pref-grid-container glass-morphism">
    <!-- Barre de configuration (Sélecteurs de ressource et d'outil) -->
    <div class="pref-toolbar">
      <div class="toolbar-section">
        <h3 class="toolbar-title">Grille de Vœux & Indisponibilités</h3>
      </div>

      <!-- Sélecteurs standards (si non embarqués) -->
      <div v-if="!hideSelectors" class="toolbar-section selectors-group">
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
      <div v-if="resourceIds.length > 0" class="toolbar-section brush-palette">
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

      <!-- Bouton d'aide -->
      <div class="toolbar-section help-section">
        <button class="btn-help" @click="showLegendModal = true" title="Légende de la grille">
          ❓
        </button>
      </div>
    </div>

    <!-- Grille interactive des voeux ou Placeholder -->
    <div class="grid-wrapper">
      <div v-if="resourceIds.length === 0" class="pref-placeholder">
        <div class="placeholder-icon">👈</div>
        <div class="placeholder-title">Sélectionnez un élément</div>
        <div class="placeholder-subtitle">
          Veuillez choisir un ou plusieurs éléments dans la liste de gauche pour configurer leurs vœux et contraintes horaires.
        </div>
      </div>

      <div v-else class="timetable-grid">
        <!-- Coin supérieur gauche -->
        <div class="grid-header-cell corner-header-cell">Horaire</div>

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
            @mousedown="onCellMouseDown(day.value, hour, $event)"
            @mouseenter="onCellMouseEnter(day.value, hour)"
          >
            <div class="cell-label">
              {{ getCellLabel(day.value, hour) }}
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- Modal de Légende -->
    <Teleport to="body">
      <div v-if="showLegendModal" class="legend-modal-overlay" @click.self="showLegendModal = false">
        <div class="legend-modal-card glass-morphism">
          <div class="legend-modal-header">
            <div class="legend-modal-title">
              <span class="legend-modal-title-icon">❓</span> Légende de la grille
            </div>
            <button class="btn-close-legend" @click="showLegendModal = false">&times;</button>
          </div>
          
          <div class="legend-modal-body">
            <div class="legend-tip">
              <strong>Astuce de saisie :</strong><br>
              [Shift + Clic] sur un créneau permet de colorer ce créneau sur tous les jours de la semaine.
            </div>
            
            <div class="legend-items-list">
              <div class="legend-item">
                <div class="legend-color-box pref-level-unsuited-hashed"></div>
                <div class="legend-text">
                  Indisponibilités sur au moins une période et/ou pour au moins une des ressources sélectionnées
                </div>
              </div>

              <div class="legend-item">
                <div class="legend-color-box pref-level-undesirable-hashed"></div>
                <div class="legend-text">
                  Indisponibilités optionnelles sur au moins une période et/ou pour au moins une des ressources sélectionnées
                </div>
              </div>

              <div class="legend-item">
                <div class="legend-color-box pref-level-preferred-hashed"></div>
                <div class="legend-text">
                  Vœux sur au moins une période et/ou pour au moins une des ressources sélectionnées
                </div>
              </div>

              <div class="legend-item">
                <div class="legend-color-box pref-level-mixed-hashed"></div>
                <div class="legend-text">
                  Contraintes différentes selon les périodes et/ou les ressources sélectionnées
                </div>
              </div>

              <div class="legend-item">
                <div class="legend-color-box pref-level-off-hashed"></div>
                <div class="legend-text">
                  Demi-journée non ouvrée
                </div>
              </div>

              <div class="legend-item">
                <div class="legend-color-box cell-with-course">T</div>
                <div class="legend-text">
                  Signale la présence d'un cours sur le créneau<br>
                  <small>Au centre : hebdomadaire, à gauche : semaine A ; à droite : semaine B</small>
                </div>
              </div>

              <div class="legend-item">
                <div class="legend-color-box cell-with-instances">
                  <div class="instance-row"><span>1</span><span>1</span></div>
                  <div class="instance-row"><span>1</span><span>1</span></div>
                </div>
                <div class="legend-text">
                  Pour les groupes de salles, nombre d'occurrences du groupe occupées par un cours.
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { Teacher, Classroom, Division, Timeslot } from '../types';

const props = withDefaults(defineProps<{
  teachers: Teacher[];
  classrooms: Classroom[];
  divisions: Division[];
  timeslots: Timeslot[];
  resourceTypeProp?: 'Teacher' | 'Classroom' | 'Division';
  resourceIdProp?: number | null;
  resourceIdsProp?: number[];
  hideSelectors?: boolean;
}>(), {
  resourceTypeProp: 'Teacher',
  resourceIdsProp: () => [],
  hideSelectors: false
});

const resourceType = ref<'Teacher' | 'Classroom' | 'Division'>('Teacher');
const resourceId = ref<number | ''>('');
const resourceIds = ref<number[]>([]);
const activeBrush = ref<'Preferred' | 'Undesirable' | 'Unsuited' | 'Neutral'>('Unsuited');
const showLegendModal = ref(false);

// Dictionnaire local complet indexe par resource_id
// Clé: resourceId, Valeur: Record<"day-hour", PreferenceLevel>
const allPreferences = ref<Record<number, Record<string, string>>>({});

// Dictionnaire local des préférences consolidées pour affichage réactif
// Clé: "day-hour", Valeur: PreferenceLevel ou motif ('Preferred', 'Undesirable', 'Unsuited', 'Preferred-hashed', 'Undesirable-hashed', 'Unsuited-hashed', 'Mixed-hashed', 'Neutral')
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

const currentResourceName = computed(() => {
  if (resourceIds.value.length > 1) {
    return `${resourceIds.value.length} ressources sélectionnées`;
  }
  if (!resourceId.value) return '';
  const option = resourceOptions.value.find(o => o.id === resourceId.value);
  return option ? option.name : '';
});

// Synchronisation des props vers l'état interne
watch(() => props.resourceTypeProp, (newVal) => {
  if (newVal) {
    resourceType.value = newVal;
  }
}, { immediate: true });

watch(() => props.resourceIdsProp, (newVal) => {
  resourceIds.value = newVal || [];
  if (resourceIds.value.length > 0) {
    resourceId.value = resourceIds.value[0];
    loadPreferences();
  } else {
    if (props.resourceIdProp !== undefined && props.resourceIdProp !== null) {
      resourceId.value = props.resourceIdProp;
      resourceIds.value = [props.resourceIdProp];
      loadPreferences();
    } else {
      resourceId.value = '';
      resourceIds.value = [];
      preferencesMap.value = {};
      allPreferences.value = {};
    }
  }
}, { immediate: true, deep: true });

watch(() => props.resourceIdProp, (newVal) => {
  if (props.resourceIdsProp && props.resourceIdsProp.length > 0) return;
  
  if (newVal !== undefined && newVal !== null) {
    resourceId.value = newVal;
    resourceIds.value = [newVal];
    loadPreferences();
  } else {
    resourceId.value = '';
    resourceIds.value = [];
    preferencesMap.value = {};
    allPreferences.value = {};
  }
}, { immediate: true });

function onResourceChange() {
  if (resourceOptions.value.length > 0) {
    resourceId.value = resourceOptions.value[0].id;
    resourceIds.value = [resourceId.value];
    loadPreferences();
  } else {
    resourceId.value = '';
    resourceIds.value = [];
    preferencesMap.value = {};
    allPreferences.value = {};
  }
}

// Consolider les préférences de toutes les ressources sélectionnées
function updateCombinedPreferences() {
  const ids = resourceIds.value;
  if (ids.length === 0) {
    preferencesMap.value = {};
    return;
  }

  const combined: Record<string, string> = {};
  
  days.forEach(d => {
    hours.forEach(h => {
      const key = `${d.value}-${h}`;
      
      const levels = ids.map(id => (allPreferences.value[id] && allPreferences.value[id][key]) || 'Neutral');
      const activeLevels = levels.filter(lvl => lvl !== 'Neutral');
      const uniqueLevels = Array.from(new Set(levels));
      
      if (uniqueLevels.length === 1) {
        combined[key] = uniqueLevels[0];
      } else {
        const uniqueActive = Array.from(new Set(activeLevels));
        if (uniqueActive.length === 0) {
          combined[key] = 'Neutral';
        } else if (uniqueActive.length === 1) {
          combined[key] = `${uniqueActive[0]}-hashed`;
        } else {
          combined[key] = 'Mixed-hashed';
        }
      }
    });
  });
  
  preferencesMap.value = combined;
}

// Charger les préférences depuis l'API en parallèle
async function loadPreferences() {
  const ids = resourceIds.value;
  if (ids.length === 0) {
    allPreferences.value = {};
    preferencesMap.value = {};
    return;
  }
  
  try {
    const results = await Promise.all(
      ids.map(id =>
        fetch(`/api/generic/resource_preferences?resource_type=${resourceType.value}&resource_id=${id}`)
          .then(res => {
            if (!res.ok) throw new Error();
            return res.json();
          })
          .then(data => ({ id, items: data.items || [] }))
          .catch(() => ({ id, items: [] }))
      )
    );
    
    const newAllPrefs: Record<number, Record<string, string>> = {};
    
    results.forEach(({ id, items }) => {
      const teacherPrefs: Record<string, string> = {};
      items.forEach((pref: any) => {
        const ts = props.timeslots.find(t => t.id === pref.timeslot_id);
        if (ts) {
          teacherPrefs[`${ts.day_of_week}-${ts.hour}`] = pref.preference_level;
        }
      });
      newAllPrefs[id] = teacherPrefs;
    });
    
    allPreferences.value = newAllPrefs;
    updateCombinedPreferences();
  } catch (err) {
    console.error("Erreur de chargement des préférences", err);
  }
}

// Peindre la cellule avec le pinceau actif pour toutes les ressources sélectionnées
async function paintCell(day: number, hour: number) {
  const ids = resourceIds.value;
  if (ids.length === 0) return;

  const ts = props.timeslots.find(t => t.day_of_week === day && t.hour === hour);
  if (!ts) return;

  const key = `${day}-${hour}`;
  const newLevel = activeBrush.value;

  // Sauvegarder les valeurs precedentes en cas d'erreur (rollback)
  const previousLevels: Record<number, string> = {};
  ids.forEach(id => {
    previousLevels[id] = (allPreferences.value[id] && allPreferences.value[id][key]) || 'Neutral';
  });

  // Optimistic UI update
  ids.forEach(id => {
    if (!allPreferences.value[id]) {
      allPreferences.value[id] = {};
    }
    if (newLevel === 'Neutral') {
      delete allPreferences.value[id][key];
    } else {
      allPreferences.value[id][key] = newLevel;
    }
  });

  updateCombinedPreferences();

  try {
    await Promise.all(
      ids.map(id =>
        fetch('/api/generic/resource_preferences', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            resource_type: resourceType.value,
            resource_id: id,
            timeslot_id: ts.id,
            preference_level: newLevel,
          }),
        }).then(res => {
          if (!res.ok) throw new Error();
        })
      )
    );
  } catch (err) {
    // Rollback en cas d'erreur
    ids.forEach(id => {
      if (previousLevels[id] === 'Neutral') {
        if (allPreferences.value[id]) {
          delete allPreferences.value[id][key];
        }
      } else {
        if (!allPreferences.value[id]) {
          allPreferences.value[id] = {};
        }
        allPreferences.value[id][key] = previousLevels[id];
      }
    });
    updateCombinedPreferences();
    alert("Impossible d'enregistrer le vœu pour toutes les ressources sélectionnées. Veuillez réessayer.");
  }
}

function getCellClass(day: number, hour: number): string {
  const key = `${day}-${hour}`;
  const level = preferencesMap.value[key];
  if (!level) return 'pref-level-neutral';
  
  if (level.endsWith('-hashed')) {
    return `pref-level-${level.toLowerCase()}`;
  }
  
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
  if (level === 'Preferred-hashed') return 'Préféré (Partiel)';
  if (level === 'Undesirable-hashed') return 'Indésirable (Partiel)';
  if (level === 'Unsuited-hashed') return 'Indisponible (Partiel)';
  if (level === 'Mixed-hashed') return 'Contraintes différentes';
  return 'Neutre';
}

const isMouseDown = ref(false);

function onCellMouseDown(day: number, hour: number, event: MouseEvent) {
  if (event.button !== 0) return; // Seul le clic gauche dessine
  event.preventDefault();
  isMouseDown.value = true;
  paintCell(day, hour);
}

function onCellMouseEnter(day: number, hour: number) {
  if (isMouseDown.value) {
    paintCell(day, hour);
  }
}

const handleGlobalMouseUp = () => {
  isMouseDown.value = false;
};

onMounted(() => {
  if (!props.hideSelectors) {
    onResourceChange();
  }
  window.addEventListener('mouseup', handleGlobalMouseUp);
});

onUnmounted(() => {
  window.removeEventListener('mouseup', handleGlobalMouseUp);
});

// Re-charger si les listes changent
watch(resourceOptions, () => {
  if (!props.hideSelectors && !resourceId.value && resourceOptions.value.length > 0) {
    resourceId.value = resourceOptions.value[0].id;
    resourceIds.value = [resourceId.value];
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
  border-radius: 0;
  overflow: hidden;
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(12px);
  padding: 0;
  gap: 0;
}

.pref-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  background-color: var(--bg-surface);
  border: none;
  border-bottom: 1px solid var(--border-color);
  padding: 12px 20px;
  border-radius: 0;
}

.toolbar-title {
  font-size: 15px;
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
  font-size: 13px;
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

.active-resource-info {
  display: flex;
  align-items: center;
  gap: 8px;
  background-color: rgba(99, 102, 241, 0.1);
  padding: 6px 14px;
  border-radius: 20px;
  border: 1px solid rgba(99, 102, 241, 0.2);
}

.active-resource-label {
  font-size: 12.5px;
  color: var(--text-secondary);
}

.active-resource-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--accent-primary);
}

.brush-palette {
  display: flex;
  align-items: center;
  gap: 12px;
}

.palette-label {
  font-size: 13px;
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
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 12px;
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
  border: none;
  border-radius: 0;
  background-color: var(--bg-secondary);
  box-shadow: none;
}

.pref-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 40px;
  text-align: center;
  color: var(--text-secondary);
  background-color: var(--bg-card);
}

.placeholder-icon {
  font-size: 48px;
  margin-bottom: 16px;
  animation: float 2s ease-in-out infinite;
}

.placeholder-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.placeholder-subtitle {
  font-size: 13.5px;
  max-width: 320px;
}

@keyframes float {
  0%, 100% { transform: translateX(0); }
  50% { transform: translateX(-8px); }
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
  font-size: 13px;
  color: var(--text-primary);
  position: sticky;
  top: 0;
  z-index: 3;
}

.grid-time-cell {
  background-color: var(--bg-surface);
  border-right: 2px solid var(--border-color);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  position: sticky;
  left: 0;
  z-index: 2;
}

.corner-header-cell {
  position: sticky;
  top: 0;
  left: 0;
  z-index: 4;
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
  cursor: url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='32' height='32' style='font-size: 24px;'%3E%3Ctext y='24'%3E🖌️%3C/text%3E%3C/svg%3E") 4 28, pointer;
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

/* Classes Hachurées */
.pref-level-preferred-hashed {
  background: repeating-linear-gradient(45deg, rgba(16, 185, 129, 0.05) 0px, rgba(16, 185, 129, 0.05) 6px, rgba(16, 185, 129, 0.25) 6px, rgba(16, 185, 129, 0.25) 12px) !important;
  border: 1.5px dashed rgba(16, 185, 129, 0.5) !important;
  color: #10b981;
}

.pref-level-undesirable-hashed {
  background: repeating-linear-gradient(45deg, rgba(245, 158, 11, 0.05) 0px, rgba(245, 158, 11, 0.05) 6px, rgba(245, 158, 11, 0.25) 6px, rgba(245, 158, 11, 0.25) 12px) !important;
  border: 1.5px dashed rgba(245, 158, 11, 0.5) !important;
  color: #f59e0b;
}

.pref-level-unsuited-hashed {
  background: repeating-linear-gradient(45deg, rgba(239, 68, 68, 0.05) 0px, rgba(239, 68, 68, 0.05) 6px, rgba(239, 68, 68, 0.25) 6px, rgba(239, 68, 68, 0.25) 12px) !important;
  border: 1.5px dashed rgba(239, 68, 68, 0.5) !important;
  color: #ef4444;
}

.pref-level-mixed-hashed {
  background: repeating-linear-gradient(45deg, rgba(59, 130, 246, 0.05) 0px, rgba(59, 130, 246, 0.05) 6px, rgba(59, 130, 246, 0.25) 6px, rgba(59, 130, 246, 0.25) 12px) !important;
  border: 1.5px dashed rgba(59, 130, 246, 0.5) !important;
  color: #3b82f6;
}

.pref-level-off-hashed {
  background: repeating-linear-gradient(45deg, rgba(156, 163, 175, 0.05) 0px, rgba(156, 163, 175, 0.05) 6px, rgba(156, 163, 175, 0.2) 6px, rgba(156, 163, 175, 0.2) 12px) !important;
  border: 1px solid rgba(156, 163, 175, 0.3) !important;
  color: #9ca3af;
}

.cell-label {
  font-size: 11px;
  font-weight: 600;
}

/* Modal de Legende */
.legend-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.legend-modal-card {
  width: 550px;
  max-width: 90%;
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  box-shadow: var(--shadow-lg);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.legend-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background-color: var(--accent-primary);
  color: white;
}

.legend-modal-title {
  font-size: 16px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-close-legend {
  background: none;
  border: none;
  color: white;
  font-size: 24px;
  cursor: pointer;
  line-height: 1;
}

.legend-modal-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-height: 60vh;
  overflow-y: auto;
}

.legend-tip {
  background-color: var(--bg-secondary);
  border-left: 4px solid var(--accent-primary);
  padding: 12px;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.4;
  color: var(--text-primary);
}

.legend-items-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 16px;
}

.legend-color-box {
  width: 60px;
  height: 35px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  flex-shrink: 0;
  background-color: var(--bg-card);
}

.legend-text {
  font-size: 12.5px;
  color: var(--text-primary);
  line-height: 1.4;
  text-align: left;
}

.legend-modal-footer {
  padding: 12px 20px;
  background-color: var(--bg-surface);
  border-top: 1px solid var(--border-color);
  display: flex;
  justify-content: flex-end;
}

.btn-modal-close {
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-modal-close:hover {
  background-color: var(--border-color);
}

.btn-help {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  font-size: 16px;
  cursor: pointer;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  color: var(--text-primary);
}

.btn-help:hover {
  background-color: var(--border-color);
  transform: scale(1.05);
}

/* Styles pour les boîtes de cours dans la légende */
.cell-with-course {
  border: 1.5px solid var(--text-primary);
  font-weight: 800;
  color: var(--text-primary);
}

.cell-with-instances {
  display: flex;
  flex-direction: column;
  padding: 2px;
  background-color: #e5e7eb;
}

.instance-row {
  display: flex;
  justify-content: space-between;
  width: 100%;
  font-size: 9px;
  font-weight: 500;
  color: #6b7280;
  padding: 0 4px;
}
</style>
