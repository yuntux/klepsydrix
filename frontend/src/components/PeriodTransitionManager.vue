<template>
  <div class="period-transition-manager glass-morphism">
    <div class="manager-header">
      <h3 class="title">📅 Calendrier des Périodes</h3>
      
      <div class="school-selector-container">
        <label for="school-select" class="selector-label">Établissement :</label>
        <select id="school-select" v-model="selectedSchoolId" class="select-custom">
          <option v-for="school in schools" :key="school.id" :value="school.id">
            {{ school.name }}
          </option>
        </select>
      </div>

      <div v-if="activeSchool && hasSchoolDates" class="school-year-badge">
        Année scolaire : <strong>{{ formatDateNice(activeSchool.student_start_date) }}</strong> au <strong>{{ formatDateNice(activeSchool.student_end_date) }}</strong>
      </div>
    </div>

    <div v-if="!periodTypeId" class="placeholder-view">
      <div class="placeholder-icon">👈</div>
      <p class="placeholder-text">Sélectionnez un type de période à gauche pour configurer son calendrier.</p>
    </div>

    <div v-else class="manager-content">
      <div v-if="!hasSchoolDates" class="alert-warning">
        ⚠️ Renseignez d'abord les dates de rentrée et de sortie dans la fiche établissement.
      </div>

      <div v-else class="table-wrapper">
        <table class="premium-table">
          <thead>
            <tr class="header-tr">
              <th style="width: 15%;" class="header-th">Code</th>
              <th style="width: 40%;" class="header-th">Nom de la période</th>
              <th style="width: 20%;" class="header-th">Date Début</th>
              <th style="width: 20%;" class="header-th">Date Fin (Transition)</th>
              <th style="width: 5%;" class="header-th actions-th"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(p, index) in localPeriods" :key="index" class="body-tr">
              <td class="body-td">
                <input type="text" v-model="p.code" class="inline-input" placeholder="ex: S1" required />
              </td>
              <td class="body-td">
                <input type="text" v-model="p.name" class="inline-input" placeholder="ex: Semestre 1" required />
              </td>
              <td class="body-td">
                <span v-if="index === 0" class="date-text locked">
                  {{ formatDateNice(p.start_date) }} (Rentrée - Verrouillée)
                </span>
                <span v-else class="date-text">
                  {{ formatDateNice(p.start_date) }}
                </span>
              </td>
              <td class="body-td">
                <span v-if="index === localPeriods.length - 1" class="date-text locked">
                  {{ formatDateNice(p.end_date) }} (Sortie - Verrouillée)
                </span>
                <input 
                  v-else 
                  type="date" 
                  :value="p.end_date"
                  :min="p.start_date"
                  :max="addDays(localPeriods[index + 1].end_date, -1)"
                  @change="handleTransitionChange(index, $event.target.value)"
                  class="input-date-inline"
                />
              </td>
              <td class="body-td actions-td">
                <div class="actions-group">
                  <button 
                    v-if="localPeriods.length > 1" 
                    class="btn-action btn-delete" 
                    @click.stop="deletePeriod(index)"
                    title="Supprimer (fusionne l'intervalle)"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="localPeriods.length === 0">
              <td colspan="5" class="empty-row text-center" style="padding: 20px;">
                Aucune période définie. Cliquez sur "Ajouter une période" pour commencer.
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="actions-footer">
        <button class="btn btn-secondary btn-sm" @click="addPeriod">
          ➕ Ajouter une période
        </button>
        <button 
          class="btn btn-primary btn-sm" 
          :disabled="saving" 
          @click="savePeriods"
        >
          {{ saving ? 'Enregistrement...' : '💾 Enregistrer' }}
        </button>
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
  school_id?: number;
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

const localPeriods = ref<Period[]>([]);
const deletedPeriodIds = ref<number[]>([]);
const saving = ref(false);
const selectedSchoolId = ref<number | null>(null);

watch(() => props.schools, (newSchools) => {
  if (newSchools && newSchools.length > 0) {
    if (selectedSchoolId.value === null || !newSchools.some(s => s.id === selectedSchoolId.value)) {
      selectedSchoolId.value = newSchools[0].id;
    }
  }
}, { immediate: true });

const activeSchool = computed(() => {
  if (!props.schools || !selectedSchoolId.value) return null;
  return props.schools.find(s => s.id === selectedSchoolId.value) || null;
});

const hasSchoolDates = computed(() => {
  return !!activeSchool.value?.student_start_date && !!activeSchool.value?.student_end_date;
});

async function loadPeriods() {
  console.log("[PeriodTransitionManager] loadPeriods - props.periodTypeId:", props.periodTypeId, "selectedSchoolId:", selectedSchoolId.value);
  if (!props.periodTypeId || !selectedSchoolId.value) {
    localPeriods.value = [];
    deletedPeriodIds.value = [];
    return;
  }
  try {
    const res = await api.fetchGenericList('periods', 0, 1000, selectedSchoolId.value);
    console.log("[PeriodTransitionManager] fetched periods list:", res.items);
    localPeriods.value = res.items
      .filter((p: any) => Number(p.period_type_id) === Number(props.periodTypeId))
      .sort((a: any, b: any) => a.start_date.localeCompare(b.start_date));
    console.log("[PeriodTransitionManager] filtered periods:", localPeriods.value);
    deletedPeriodIds.value = [];
    adjustPeriodsToSchoolDates();
  } catch (e) {
    console.error("Erreur de chargement des périodes", e);
  }
}

watch([() => props.periodTypeId, selectedSchoolId], loadPeriods, { immediate: true });
watch(activeSchool, adjustPeriodsToSchoolDates);

function adjustPeriodsToSchoolDates() {
  if (!hasSchoolDates.value || localPeriods.value.length === 0 || !activeSchool.value) return;
  const start = activeSchool.value.student_start_date;
  const end = activeSchool.value.student_end_date;
  if (localPeriods.value[0].start_date !== start) {
    localPeriods.value[0].start_date = start;
  }
  if (localPeriods.value[localPeriods.value.length - 1].end_date !== end) {
    localPeriods.value[localPeriods.value.length - 1].end_date = end;
  }
}

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

function handleTransitionChange(index: number, newEndDate: string) {
  if (index < 0 || index >= localPeriods.value.length - 1) return;
  localPeriods.value[index].end_date = newEndDate;
  localPeriods.value[index + 1].start_date = addDays(newEndDate, 1);
}

function addPeriod() {
  if (!hasSchoolDates.value || !activeSchool.value || !props.periodTypeId || !selectedSchoolId.value) return;
  const typeId = props.periodTypeId;

  if (localPeriods.value.length === 0) {
    localPeriods.value.push({
      period_type_id: typeId,
      school_id: selectedSchoolId.value,
      code: 'P1',
      name: 'Période 1',
      start_date: activeSchool.value.student_start_date,
      end_date: activeSchool.value.student_end_date,
      isNew: true
    });
    return;
  }

  const lastIndex = localPeriods.value.length - 1;
  const lastPeriod = localPeriods.value[lastIndex];
  const start = new Date(lastPeriod.start_date);
  const end = new Date(lastPeriod.end_date);
  const diffDays = Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24));

  if (diffDays <= 2) {
    alert("La période est trop courte pour être divisée.");
    return;
  }

  const midDays = Math.floor(diffDays / 2);
  const midDateStr = addDays(lastPeriod.start_date, midDays);

  const oldEndDate = lastPeriod.end_date;
  lastPeriod.end_date = midDateStr;

  const nextNum = localPeriods.value.length + 1;
  localPeriods.value.push({
    period_type_id: typeId,
    school_id: selectedSchoolId.value,
    code: 'P' + nextNum,
    name: 'Période ' + nextNum,
    start_date: addDays(midDateStr, 1),
    end_date: oldEndDate,
    isNew: true
  });
}

function deletePeriod(index: number) {
  if (localPeriods.value.length <= 1) return;
  const deleted = localPeriods.value[index];
  if (deleted.id && !deleted.isNew) {
    deletedPeriodIds.value.push(deleted.id);
  }
  if (index === 0) {
    localPeriods.value[1].start_date = deleted.start_date;
  } else {
    localPeriods.value[index - 1].end_date = deleted.end_date;
  }
  localPeriods.value.splice(index, 1);
  adjustPeriodsToSchoolDates();
}

async function savePeriods() {
  saving.value = true;
  try {
    for (const id of deletedPeriodIds.value) {
      await api.deleteGenericItem('periods', id);
    }
    for (const p of localPeriods.value) {
      const payload = {
        code: p.code,
        name: p.name,
        period_type_id: p.period_type_id,
        school_id: selectedSchoolId.value,
        start_date: p.start_date,
        end_date: p.end_date
      };
      if (p.isNew) {
        await api.createGenericItem('periods', payload);
      } else if (p.id) {
        await api.updateGenericItem('periods', p.id, payload);
      }
    }
    alert("Enregistré avec succès !");
    emit('change');
    await loadPeriods();
  } catch (e: any) {
    alert("Erreur : " + (e.message || e));
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
  padding: 20px;
  box-sizing: border-box;
  overflow-y: auto;
  color: var(--text-primary);
}

.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 12px;
}

.school-selector-container {
  display: flex;
  align-items: center;
  gap: 8px;
}

.selector-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.title {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}

.school-year-badge {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-primary);
  padding: 4px 10px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
}

.placeholder-view {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: var(--text-secondary);
  text-align: center;
  padding: 40px;
}

.placeholder-icon {
  font-size: 32px;
  margin-bottom: 10px;
}

.placeholder-text {
  font-size: 13px;
  max-width: 250px;
}

.alert-warning {
  background-color: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.3);
  color: var(--accent-warning);
  padding: 12px;
  border-radius: var(--radius-lg);
  font-size: 13px;
  margin-bottom: 15px;
}

.table-wrapper {
  flex: 1;
  position: relative;
  overflow: auto;
  border: 1px solid var(--border-color);
  border-radius: 0;
  background-color: var(--bg-card);
  margin-bottom: 20px;
}

.premium-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}

.header-tr {
  background-color: var(--bg-surface);
  border-bottom: 2px solid var(--border-color);
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
  padding: 8px 16px;
  user-select: none;
  border-right: 1px solid var(--border-color);
}

.body-tr {
  border-bottom: 1px solid var(--border-color);
  transition: background-color var(--transition-fast, 0.15s);
  background-color: var(--bg-card);
}

.body-tr:hover {
  background-color: var(--bg-secondary);
}

.body-td {
  padding: 0;
  font-size: 13px;
  color: var(--text-primary);
  border-right: 1px solid var(--border-color);
  vertical-align: middle;
}

.actions-th {
  width: 45px !important;
  min-width: 45px !important;
  max-width: 45px !important;
  padding: 8px 4px !important;
  text-align: center;
  border-right: none;
}

.actions-td {
  width: 45px !important;
  min-width: 45px !important;
  max-width: 45px !important;
  padding: 0 4px !important;
  text-align: center;
  border-right: none;
}

.actions-group {
  display: flex;
  justify-content: center;
  gap: 8px;
}

.btn-action {
  background: transparent;
  border: none;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  transition: all var(--transition-fast, 0.15s);
}

.btn-action svg {
  width: 16px;
  height: 16px;
}

.btn-delete:hover {
  background-color: rgba(239, 68, 68, 0.15);
  color: var(--accent-danger, var(--accent-danger));
}

.inline-input {
  width: 100%;
  background-color: transparent;
  border: 1px solid transparent;
  color: var(--text-primary);
  padding: 6px 10px;
  border-radius: 0;
  outline: none;
  font-family: var(--font-sans);
  font-size: 13px;
  transition: all var(--transition-fast, 0.15s);
  box-sizing: border-box;
}

.inline-input:hover {
  background-color: var(--bg-secondary);
  border-color: var(--border-color);
}

.inline-input:focus {
  background-color: var(--bg-card);
  border-color: var(--accent-color, #8B5CF6);
  box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.15);
}

.date-text {
  font-family: monospace;
  color: var(--text-secondary);
  font-size: 12.5px;
  display: block;
  padding: 6px 10px;
  border: 1px solid transparent;
}

.date-text.locked {
  font-style: italic;
  color: var(--text-muted, var(--text-muted));
}

.input-date-inline {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 4px 8px;
  border-radius: var(--radius-md);
  font-family: monospace;
  font-size: 12.5px;
  outline: none;
  transition: border-color var(--transition-fast, 0.15s);
  margin: 4px 12px;
}

.input-date-inline:focus {
  border-color: var(--accent-color, #8B5CF6);
}

.actions-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.btn {
  padding: 6px 14px;
  border-radius: var(--radius-md);
  font-weight: 500;
  font-size: 12.5px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-sm {
  padding: 5px 12px;
}

.btn-secondary {
  background-color: var(--bg-primary);
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

.text-center {
  text-align: center;
}
</style>
