<template>
  <div class="period-transition-manager glass-morphism">
    <div class="manager-header">
      <h3>📅 Saisie des Périodes par Transitions</h3>
      <p class="subtitle">Conformément aux contraintes, l'union des périodes doit couvrir l'année scolaire de l'établissement sans trou ni chevauchement.</p>
    </div>

    <div v-if="!periodTypeId" class="placeholder-view">
      <div class="placeholder-icon">👈</div>
      <div class="placeholder-title">Sélectionnez un type de période</div>
      <div class="placeholder-subtitle">Veuillez choisir un type de période dans la liste de gauche pour configurer son calendrier.</div>
    </div>

    <div v-else class="manager-content">
      <!-- Sélecteur d'établissement pour récupérer les dates scolaires -->
      <div class="school-selector-bar">
        <label for="school-select">Établissement de référence :</label>
        <select id="school-select" v-model="selectedSchoolId" class="select-custom">
          <option v-for="school in schools" :key="school.id" :value="school.id">
            {{ school.name }} ({{ school.uai }})
          </option>
        </select>

        <div v-if="activeSchool" class="school-dates-info">
          <span>Rentrée : <strong>{{ formatDateNice(activeSchool.student_start_date) }}</strong></span>
          <span>Sortie : <strong>{{ formatDateNice(activeSchool.student_end_date) }}</strong></span>
        </div>
      </div>

      <div v-if="!hasSchoolDates" class="alert-warning-card">
        ⚠️ L'établissement sélectionné n'a pas de dates de rentrée/sortie configurées. Veuillez les renseigner dans la fiche établissement d'abord.
      </div>

      <div v-else class="periods-timeline-container">
        <!-- Visualisation sous forme de frise chronologique premium -->
        <div class="timeline-visual">
          <div 
            v-for="(p, index) in localPeriods" 
            :key="index"
            class="timeline-segment"
            :style="{ flex: getSegmentWeight(p) }"
          >
            <div class="segment-card">
              <span class="segment-code">{{ p.code || '?' }}</span>
              <span class="segment-dates">{{ formatDateNice(p.start_date) }} - {{ formatDateNice(p.end_date) }}</span>
            </div>
            <div v-if="index < localPeriods.length - 1" class="timeline-connector">
              <span class="connector-arrow">➔</span>
            </div>
          </div>
        </div>

        <!-- Formulaire d'édition de chaque période et de ses transitions -->
        <div class="periods-list-editor">
          <div v-for="(p, index) in localPeriods" :key="index" class="period-editor-row-wrapper">
            
            <!-- Carte d'édition d'une Période -->
            <div class="period-item-card premium-card">
              <div class="card-header-bar">
                <h4>Période {{ index + 1 }}</h4>
                <button 
                  v-if="localPeriods.length > 1" 
                  class="btn-delete-period"
                  @click="deletePeriod(index)"
                  title="Supprimer cette période et fusionner l'espace temporel"
                >
                  Supprimer
                </button>
              </div>
              
              <div class="card-grid">
                <div class="form-field-group">
                  <label>Code</label>
                  <input type="text" v-model="p.code" placeholder="ex: S1" required class="input-custom" />
                </div>
                
                <div class="form-field-group">
                  <label>Nom complet</label>
                  <input type="text" v-model="p.name" placeholder="ex: Semestre 1" required class="input-custom" />
                </div>

                <div class="form-field-group read-only">
                  <label>Date Début</label>
                  <div class="date-badge">{{ formatDateNice(p.start_date) }}</div>
                </div>

                <div class="form-field-group read-only">
                  <label>Date Fin</label>
                  <div class="date-badge">{{ formatDateNice(p.end_date) }}</div>
                </div>
              </div>
            </div>

            <!-- Transition Date Input : affiché uniquement entre la période N et N+1 -->
            <div v-if="index < localPeriods.length - 1" class="transition-editor-card">
              <div class="transition-line"></div>
              <div class="transition-input-wrapper">
                <label>Date de transition {{ index + 1 }} ➔ {{ index + 2 }}</label>
                <input 
                  type="date" 
                  :value="p.end_date"
                  :min="p.start_date"
                  :max="addDays(localPeriods[index + 1].end_date, -1)"
                  @change="handleTransitionChange(index, $event.target.value)"
                  class="input-date-custom"
                />
                <span class="help-text">Décale la fin de la période {{ index + 1 }} et le début de la période {{ index + 2 }}.</span>
              </div>
              <div class="transition-line"></div>
            </div>

          </div>
        </div>

        <!-- Boutons d'actions -->
        <div class="actions-bar">
          <button class="btn btn-secondary" @click="addPeriod">
            ➕ Ajouter une période (scission)
          </button>
          
          <button 
            class="btn btn-primary" 
            :disabled="saving || localPeriods.length === 0" 
            @click="savePeriods"
          >
            {{ saving ? 'Enregistrement...' : '💾 Enregistrer le calendrier' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import * as api from '../services/api';

interface School {
  id: number;
  name: string;
  uai: string;
  student_start_date: string;
  student_end_date: string;
}

interface Period {
  id?: number;
  period_type_id: number;
  code: string;
  name: string;
  start_date: string;
  end_date: string;
  isNew?: boolean;
}

const props = defineProps<{
  periodTypeId: number | null;
  schools: School[];
}>();

const emit = defineEmits<{
  (e: 'change'): void;
}>();

const selectedSchoolId = ref<number | null>(null);
const localPeriods = ref<Period[]>([]);
const deletedPeriodIds = ref<number[]>([]);
const saving = ref(false);

// Sélectionner la première école par défaut
watch(() => props.schools, (newSchools) => {
  if (newSchools && newSchools.length > 0 && selectedSchoolId.value === null) {
    selectedSchoolId.value = newSchools[0].id;
  }
}, { immediate: true });

const activeSchool = computed(() => {
  if (!selectedSchoolId.value) return null;
  return props.schools.find(s => s.id === selectedSchoolId.value) || null;
});

const hasSchoolDates = computed(() => {
  return !!activeSchool.value?.student_start_date && !!activeSchool.value?.student_end_date;
});

// Charger les périodes de ce type
async function loadPeriods() {
  if (!props.periodTypeId) {
    localPeriods.value = [];
    deletedPeriodIds.value = [];
    return;
  }

  try {
    const res = await api.fetchGenericList('periods', 0, 1000);
    // Filtrer par le type de période sélectionné et trier chronologiquement
    const filtered = res.items
      .filter((p: any) => p.period_type_id === props.periodTypeId)
      .sort((a: any, b: any) => a.start_date.localeCompare(b.start_date));

    localPeriods.value = filtered;
    deletedPeriodIds.value = [];

    // Ajuster aux bornes de l'école si nécessaire et si valide
    adjustPeriodsToSchoolDates();
  } catch (e) {
    console.error("Impossible de charger les périodes", e);
  }
}

watch(() => props.periodTypeId, loadPeriods, { immediate: true });
watch(activeSchool, adjustPeriodsToSchoolDates);

// Aligner la première et la dernière période sur les dates de l'établissement
function adjustPeriodsToSchoolDates() {
  if (!hasSchoolDates.value || localPeriods.value.length === 0 || !activeSchool.value) return;

  const start = activeSchool.value.student_start_date;
  const end = activeSchool.value.student_end_date;

  // Si on a des périodes mais que la première ou dernière n'est pas alignée, on réaligne
  if (localPeriods.value[0].start_date !== start) {
    localPeriods.value[0].start_date = start;
  }
  if (localPeriods.value[localPeriods.value.length - 1].end_date !== end) {
    localPeriods.value[localPeriods.value.length - 1].end_date = end;
  }
}

// Fonction de calcul de poids d'un segment pour la frise
function getSegmentWeight(p: Period): number {
  try {
    const s = new Date(p.start_date).getTime();
    const e = new Date(p.end_date).getTime();
    const diff = Math.max(1, e - s);
    return diff;
  } catch {
    return 1;
  }
}

// Date helpers
function formatDateNice(dateStr: string): string {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric' });
  } catch {
    return dateStr;
  }
}

function formatDateISO(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function addDays(dateStr: string, days: number): string {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + days);
  return formatDateISO(d);
}

// Gérer la modification de transition
function handleTransitionChange(index: number, newEndDate: string) {
  if (index < 0 || index >= localPeriods.value.length - 1) return;

  // Mettre à jour la fin de la période index
  localPeriods.value[index].end_date = newEndDate;

  // Mettre à jour automatiquement le début de la période index + 1 au jour suivant
  localPeriods.value[index + 1].start_date = addDays(newEndDate, 1);
}

// Ajouter une période par scission de la dernière
function addPeriod() {
  if (!hasSchoolDates.value || !activeSchool.value || !props.periodTypeId) return;

  const typeId = props.periodTypeId;

  if (localPeriods.value.length === 0) {
    // Si pas encore de périodes, on crée une période couvrant toute l'année scolaire
    localPeriods.value.push({
      period_type_id: typeId,
      code: 'P1',
      name: 'Période 1',
      start_date: activeSchool.value.student_start_date,
      end_date: activeSchool.value.student_end_date,
      isNew: true
    });
    return;
  }

  // Scission de la dernière période en deux
  const lastIndex = localPeriods.value.length - 1;
  const lastPeriod = localPeriods.value[lastIndex];

  const start = new Date(lastPeriod.start_date);
  const end = new Date(lastPeriod.end_date);
  const diffDays = Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24));

  if (diffDays <= 2) {
    alert("La dernière période est trop courte pour être divisée.");
    return;
  }

  const midDays = Math.floor(diffDays / 2);
  const midDateStr = addDays(lastPeriod.start_date, midDays);

  // L'ancienne période se termine à midDateStr
  const oldEndDate = lastPeriod.end_date;
  lastPeriod.end_date = midDateStr;

  // Création de la nouvelle période à la suite
  const nextNum = localPeriods.value.length + 1;
  localPeriods.value.push({
    period_type_id: typeId,
    code: 'P' + nextNum,
    name: 'Période ' + nextNum,
    start_date: addDays(midDateStr, 1),
    end_date: oldEndDate,
    isNew: true
  });
}

// Supprimer une période et fusionner son espace temporel
function deletePeriod(index: number) {
  if (localPeriods.value.length <= 1) return;

  const deleted = localPeriods.value[index];
  if (deleted.id && !deleted.isNew) {
    deletedPeriodIds.value.push(deleted.id);
  }

  if (index === 0) {
    // Si premier élément, on étend le début du deuxième à student_start_date
    localPeriods.value[1].start_date = deleted.start_date;
  } else {
    // Sinon, on étend la fin du précédent à la fin du supprimé
    localPeriods.value[index - 1].end_date = deleted.end_date;
  }

  localPeriods.value.splice(index, 1);

  // Renommer les codes si besoin, ou simplement garder l'ordre
  adjustPeriodsToSchoolDates();
}

// Enregistrer les changements
async function savePeriods() {
  saving.value = true;
  try {
    // 1. Supprimer les périodes supprimées
    for (const id of deletedPeriodIds.value) {
      await api.deleteGenericItem('periods', id);
    }

    // 2. Créer ou Mettre à jour les périodes locales
    for (const p of localPeriods.value) {
      const payload = {
        code: p.code,
        name: p.name,
        period_type_id: p.period_type_id,
        start_date: p.start_date,
        end_date: p.end_date
      };

      if (p.isNew) {
        await api.createGenericItem('periods', payload);
      } else if (p.id) {
        await api.updateGenericItem('periods', p.id, payload);
      }
    }

    alert("Calendrier des périodes enregistré avec succès !");
    emit('change');
    await loadPeriods();
  } catch (e: any) {
    alert("Erreur lors de l'enregistrement : " + (e.message || e));
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.period-transition-manager {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 24px;
  box-sizing: border-box;
  overflow-y: auto;
  color: var(--text-primary);
}

.manager-header {
  margin-bottom: 24px;
}

.manager-header h3 {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 6px 0;
  color: var(--text-primary);
}

.manager-header .subtitle {
  font-size: 13.5px;
  color: var(--text-secondary);
  margin: 0;
}

.placeholder-view {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  padding: 40px;
  text-align: center;
}

.placeholder-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.placeholder-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.placeholder-subtitle {
  font-size: 13.5px;
  color: var(--text-secondary);
  max-width: 320px;
}

.school-selector-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  background-color: var(--bg-card);
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid var(--border-color);
  margin-bottom: 20px;
}

.school-selector-bar label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
}

.select-custom {
  background-color: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13.5px;
  min-width: 250px;
}

.school-dates-info {
  display: flex;
  gap: 20px;
  font-size: 13.5px;
  color: var(--text-secondary);
  margin-left: auto;
  border-left: 1px solid var(--border-color);
  padding-left: 20px;
}

.alert-warning-card {
  background-color: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.3);
  color: #F59E0B;
  padding: 16px;
  border-radius: 8px;
  font-size: 14px;
  margin-bottom: 20px;
}

.periods-timeline-container {
  display: flex;
  flex-direction: column;
  gap: 24px;
  flex: 1;
}

/* Frise chronologique visuelle */
.timeline-visual {
  display: flex;
  align-items: center;
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
  min-height: 80px;
  overflow-x: auto;
}

.timeline-segment {
  display: flex;
  align-items: center;
}

.segment-card {
  background: linear-gradient(135deg, var(--accent-color, #8B5CF6) 0%, rgba(139, 92, 246, 0.8) 100%);
  color: white;
  padding: 12px 16px;
  border-radius: 6px;
  text-align: center;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  min-width: 120px;
  flex: 1;
}

.segment-code {
  display: block;
  font-weight: 700;
  font-size: 15px;
  margin-bottom: 2px;
}

.segment-dates {
  font-size: 11.5px;
  opacity: 0.9;
}

.timeline-connector {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  color: var(--text-secondary);
}

.connector-arrow {
  font-size: 18px;
}

/* Editeur vertical */
.periods-list-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.period-editor-row-wrapper {
  display: flex;
  flex-direction: column;
}

.period-item-card {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
}

.card-header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 8px;
}

.card-header-bar h4 {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
  color: var(--accent-color, #8B5CF6);
}

.btn-delete-period {
  background-color: rgba(239, 68, 68, 0.1);
  color: #EF4444;
  border: 1px solid rgba(239, 68, 68, 0.3);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-delete-period:hover {
  background-color: #EF4444;
  color: white;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.form-field-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-field-group label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.input-custom {
  background-color: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13.5px;
}

.form-field-group.read-only .date-badge {
  background-color: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13.5px;
  font-family: monospace;
}

/* Connecteur de transition graphique */
.transition-editor-card {
  display: flex;
  align-items: center;
  margin: 12px 0;
}

.transition-line {
  flex: 1;
  height: 2px;
  background: repeating-linear-gradient(to right, var(--border-color) 0px, var(--border-color) 4px, transparent 4px, transparent 8px);
}

.transition-input-wrapper {
  background-color: var(--bg-card);
  border: 1.5px dashed var(--accent-color, #8B5CF6);
  border-radius: 8px;
  padding: 12px 20px;
  text-align: center;
  min-width: 320px;
  margin: 0 16px;
}

.transition-input-wrapper label {
  display: block;
  font-size: 11.5px;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--accent-color, #8B5CF6);
  margin-bottom: 6px;
}

.input-date-custom {
  background-color: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 6px 12px;
  border-radius: 4px;
  font-size: 13px;
  width: 150px;
  text-align: center;
}

.transition-input-wrapper .help-text {
  display: block;
  font-size: 10.5px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.actions-bar {
  display: flex;
  justify-content: space-between;
  margin-top: 16px;
  border-top: 1px solid var(--border-color);
  padding-top: 20px;
}

.btn {
  padding: 10px 20px;
  border-radius: 6px;
  font-weight: 600;
  font-size: 13.5px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
}

.btn-secondary:hover {
  background-color: var(--border-color);
}

.btn-primary {
  background-color: var(--accent-color, #8B5CF6);
  border: 1px solid var(--accent-color, #8B5CF6);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
