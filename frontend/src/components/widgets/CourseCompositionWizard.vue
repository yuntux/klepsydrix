<template>
  <div class="composition-wizard">
    <div class="wizard-header">
      <h2>Composition du cours (ID: {{ recordId }})</h2>
      <p class="text-sm text-gray-500">Associez les ressources du parent dans le tableau ci-dessous, puis choisissez un mode de répartition temporelle.</p>
    </div>

    <div v-if="loading" class="loader-container">
      <div class="spinner"></div>
      <span>Chargement des ressources...</span>
    </div>

    <div v-else class="wizard-body">
      <!-- ERREUR / ALERTES -->
      <div v-if="errorMessage" class="error-banner">
        {{ errorMessage }}
      </div>

      <!-- ETAPE 1: MAPPING -->
      <div class="section-block">
        <h3 class="section-title">1. Répartition spatiale (Mapping)</h3>
        <table class="mapping-table">
          <thead>
            <tr>
              <th>Professeurs</th>
              <th>Groupes</th>
              <th>Parties de classe</th>
              <th>Classes</th>
              <th>Salles</th>
              <th style="width: 50px;"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in mapping" :key="index">
              <td>
                <SearchableMultiSelect 
                  v-model="row.teacher_ids" 
                  :options="teacherOptions" 
                  placeholder="Sélectionner" 
                  @change="onMappingChanged" />
              </td>
              <td>
                <SearchableMultiSelect 
                  v-model="row.group_ids" 
                  :options="groupOptions" 
                  placeholder="Sélectionner"
                  :disabled="(row.class_part_ids && row.class_part_ids.length > 0) || (row.division_ids && row.division_ids.length > 0)" 
                  @change="onMappingChanged" />
              </td>
              <td>
                <SearchableMultiSelect 
                  v-model="row.class_part_ids" 
                  :options="classPartOptions" 
                  placeholder="Sélectionner"
                  :disabled="(row.group_ids && row.group_ids.length > 0) || (row.division_ids && row.division_ids.length > 0)" 
                  @change="onMappingChanged" />
              </td>
              <td>
                <SearchableMultiSelect 
                  v-model="row.division_ids" 
                  :options="divisionOptions" 
                  placeholder="Sélectionner"
                  :disabled="(row.group_ids && row.group_ids.length > 0) || (row.class_part_ids && row.class_part_ids.length > 0)" 
                  @change="onMappingChanged" />
              </td>
              <td>
                <SearchableMultiSelect 
                  v-model="row.classroom_ids" 
                  :options="classroomOptions" 
                  placeholder="Sélectionner" 
                  @change="onMappingChanged" />
              </td>
              <td>
                <button type="button" class="btn-delete-row" @click="removeMappingRow(index)" title="Supprimer la ligne">×</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div class="mt-2">
          <BaseButton type="button" variant="secondary" @click="addMappingRow">
            + Ajouter une ligne de répartition
          </BaseButton>
        </div>
      </div>

      <!-- ETAPE 2: MODES -->
      <div class="section-block">
        <h3 class="section-title">2. Mode de répartition temporelle</h3>
        <div v-if="modesLoading" class="text-sm text-gray-500">Évaluation des modes...</div>
        <div class="modes-grid">
          <div 
            v-for="mode in 9" 
            :key="mode"
            class="mode-card"
            :class="{ 
              'disabled-mode': !availableModes.includes(mode),
              'selected-mode': selectedMode === mode 
            }"
            @click="selectMode(mode)"
            :title="!availableModes.includes(mode) ? 'Mode incompatible avec la répartition actuelle' : ''"
          >
            <div class="mode-id">{{ mode }}</div>
            <div class="mode-desc">{{ getModeLabel(mode) }}</div>
          </div>
        </div>
      </div>

      <!-- ETAPE 3: APERÇU -->
      <div v-if="previewChildren.length > 0" class="section-block preview-block">
        <h3 class="section-title text-accent">3. Aperçu des cours enfants (Brouillon)</h3>
        <p class="text-sm text-gray-400 mb-2">Vous pouvez ajuster manuellement la durée ou la quinzaine de chaque enfant avant d'enregistrer.</p>
        
        <table class="preview-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Semaine</th>
              <th>Durée (min)</th>
              <th>Offset</th>
              <th>Périodes</th>
              <th>Professeurs (IDs)</th>
              <th>Groupes (IDs)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(child, idx) in previewChildren" :key="idx">
              <td>Enfant {{ idx + 1 }}</td>
              <td>
                <select v-model="child.week_type" class="form-select">
                  <option value="W">Semaine Entière (W)</option>
                  <option value="A">Quinzaine A</option>
                  <option value="B">Quinzaine B</option>
                </select>
              </td>
              <td>
                <input type="number" v-model="child.duration_minutes" class="form-input" min="15" step="5" />
              </td>
              <td>
                <input type="number" v-model="child.parent_timeslot_offset" class="form-input" min="0" />
              </td>
              <td>
                <SearchableMultiSelect 
                  v-model="child.period_ids" 
                  :options="periodOptions" 
                  placeholder="Héritées du parent" 
                />
              </td>
              <td class="text-xs">{{ (child.teacher_ids || []).join(', ') }}</td>
              <td class="text-xs">{{ (child.group_ids || []).join(', ') }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="wizard-actions">
        <BaseButton type="button" variant="secondary" @click="$emit('cancel')">Fermer</BaseButton>
        <BaseButton 
          v-if="previewChildren.length === 0" 
          type="button" 
          variant="primary" 
          :disabled="!selectedMode || !isMappingValid" 
          @click="generatePreview"
        >
          Générer l'aperçu
        </BaseButton>
        <BaseButton 
          v-else 
          type="button" 
          variant="success" 
          @click="saveComposition"
        >
          Enregistrer définitivement
        </BaseButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import BaseButton from '../BaseButton.vue';
import SearchableMultiSelect from '../SearchableMultiSelect.vue';
import * as api from '../../services/api';

const props = defineProps<{
  recordId: number;
  model?: any;
}>();

const emit = defineEmits<{
  (e: 'cancel'): void;
  (e: 'success'): void;
}>();

const loading = ref(true);
const modesLoading = ref(false);
const errorMessage = ref('');

const teacherOptions = ref<Array<{value: number, label: string}>>([]);
const groupOptions = ref<Array<{value: number, label: string}>>([]);
const classPartOptions = ref<Array<{value: number, label: string}>>([]);
const divisionOptions = ref<Array<{value: number, label: string}>>([]);
const classroomOptions = ref<Array<{value: number, label: string}>>([]);
const periodOptions = ref<Array<{value: number, label: string}>>([]);

const mapping = ref<Array<any>>([
  { teacher_ids: [], group_ids: [], class_part_ids: [], division_ids: [], classroom_ids: [] }
]);

const availableModes = ref<number[]>([]);
const selectedMode = ref<number | null>(null);
const previewChildren = ref<any[]>([]);

const isMappingValid = computed(() => {
  if (mapping.value.length === 0) return false;
  
  const seenTeachers = new Set();
  
  return mapping.value.every((row: any) => {
    const hasTeacher = row.teacher_ids && row.teacher_ids.length > 0;
    const hasGroup = row.group_ids && row.group_ids.length > 0;
    const hasClassPart = row.class_part_ids && row.class_part_ids.length > 0;
    const hasDivision = row.division_ids && row.division_ids.length > 0;
    
    // Au moins un prof ET au moins une cible
    if (!hasTeacher) return false;
    if (!hasGroup && !hasClassPart && !hasDivision) return false;
    
    // Exclusion mutuelle: on ne peut avoir qu'un seul type de cible parmi les 3
    const targets = [hasGroup, hasClassPart, hasDivision];
    const targetsCount = targets.filter(Boolean).length;
    
    if (targetsCount !== 1) return false;
    
    // Unicité des profs
    for (const tid of (row.teacher_ids || [])) {
      if (seenTeachers.has(tid)) return false;
      seenTeachers.add(tid);
    }
    
    return true;
  });
});

let debounceTimeout: any = null;

onMounted(async () => {
  try {
    const [teachersRes, groupsRes, classPartsRes, divisionsRes, classroomsRes, periodsRes] = await Promise.all([
      api.fetchGenericList('teachers', 0, 1000),
      api.fetchGenericList('groups', 0, 1000),
      api.fetchGenericList('class_parts', 0, 1000),
      api.fetchGenericList('divisions', 0, 1000),
      api.fetchGenericList('classrooms', 0, 1000),
      api.fetchGenericList('periods', 0, 1000)
    ]);
    
    // Filtrer pour ne garder que les ressources appartenant au cours parent (si model est fourni)
    const validTeacherIds = props.model?.teacher_ids || [];
    const validGroupIds = props.model?.group_ids || [];
    const validClassPartIds = props.model?.class_part_ids || [];
    const validDivisionIds = props.model?.division_ids || [];
    const validClassroomIds = props.model?.classroom_ids || [];
    const validPeriodIds = props.model?.period_ids || [];

    const filteredTeachers = validTeacherIds.length > 0 
      ? teachersRes.items.filter((i: any) => validTeacherIds.includes(i.id))
      : teachersRes.items;
      
    const filteredGroups = validGroupIds.length > 0
      ? groupsRes.items.filter((i: any) => validGroupIds.includes(i.id))
      : groupsRes.items;
      
    const filteredClassParts = validClassPartIds.length > 0
      ? classPartsRes.items.filter((i: any) => validClassPartIds.includes(i.id))
      : classPartsRes.items;
      
    const filteredDivisions = validDivisionIds.length > 0
      ? divisionsRes.items.filter((i: any) => validDivisionIds.includes(i.id))
      : divisionsRes.items;

    const filteredClassrooms = validClassroomIds.length > 0
      ? classroomsRes.items.filter((i: any) => validClassroomIds.includes(i.id))
      : classroomsRes.items;

    const filteredPeriods = validPeriodIds.length > 0
      ? periodsRes.items.filter((i: any) => validPeriodIds.includes(i.id))
      : periodsRes.items;

    teacherOptions.value = filteredTeachers.map((i: any) => ({ value: i.id, label: `${i.first_name} ${i.last_name}` }));
    groupOptions.value = filteredGroups.map((i: any) => ({ value: i.id, label: i.name || `Groupe ${i.id}` }));
    classPartOptions.value = filteredClassParts.map((i: any) => ({ value: i.id, label: i.name || `Partie ${i.id}` }));
    divisionOptions.value = filteredDivisions.map((i: any) => ({ value: i.id, label: i.name || `Classe ${i.id}` }));
    classroomOptions.value = filteredClassrooms.map((i: any) => ({ value: i.id, label: i.name || `Salle ${i.id}` }));
    periodOptions.value = filteredPeriods.map((i: any) => ({ value: i.id, label: i.name || `Période ${i.id}` }));
    
    // Initialiser le mapping par défaut : une ligne par prof du cours
    if (validTeacherIds.length > 0) {
      mapping.value = validTeacherIds.map((teacherId: number) => ({
        teacher_ids: [teacherId],
        group_ids: [],
        class_part_ids: [],
        division_ids: [],
        classroom_ids: []
      }));
    } else {
      mapping.value = [
        { teacher_ids: [], group_ids: [], class_part_ids: [], division_ids: [], classroom_ids: [] }
      ];
    }
    
    await fetchAvailableModes();
  } catch (e: any) {
    errorMessage.value = "Erreur de chargement des ressources: " + e.message;
  } finally {
    loading.value = false;
  }
});

function getModeLabel(mode: number) {
  const labels: Record<number, string> = {
    1: '1 séance par professeur',
    2: 'Alternance par quinzaine',
    3: 'Barrette (Rotation mi-cours)',
    4: 'Barrette + Alternance quinzaine',
    5: 'Rotation quinzaine croisée',
    6: 'Alternance tri-hebdomadaire',
    7: 'Périodes fixes (1 par période)',
    8: 'Barrette sur périodes multiples',
    9: 'Alternance profs / périodes'
  };
  return labels[mode] || `Mode ${mode}`;
}

function addMappingRow() {
  mapping.value.push({ teacher_ids: [], group_ids: [], class_part_ids: [], classroom_ids: [] });
  onMappingChanged();
}

function removeMappingRow(index: number) {
  mapping.value.splice(index, 1);
  onMappingChanged();
}

function onMappingChanged() {
  previewChildren.value = []; // Reset preview if mapping changes
  if (selectedMode.value && !availableModes.value.includes(selectedMode.value)) {
    selectedMode.value = null;
  }
  
  if (debounceTimeout) clearTimeout(debounceTimeout);
  debounceTimeout = setTimeout(() => {
    fetchAvailableModes();
  }, 300);
}

function selectMode(mode: number) {
  if (availableModes.value.includes(mode)) {
    selectedMode.value = mode;
    previewChildren.value = []; // Reset preview on mode change
  }
}

async function fetchAvailableModes() {
  if (!isMappingValid.value) {
    availableModes.value = [];
    if (selectedMode.value) selectedMode.value = null;
    return;
  }
  
  modesLoading.value = true;
  errorMessage.value = '';
  try {
    const res = await api.callInstanceMethod('courses', props.recordId, 'rpc_get_available_modes', {
      kwargs: { mapping: mapping.value }
    });
    availableModes.value = res.available_modes || [];
    if (selectedMode.value && !availableModes.value.includes(selectedMode.value)) {
      selectedMode.value = null;
    }
  } catch (e: any) {
    errorMessage.value = "Impossible d'évaluer les modes: " + e.message;
    availableModes.value = [];
  } finally {
    modesLoading.value = false;
  }
}

async function generatePreview() {
  if (!selectedMode.value) return;
  loading.value = true;
  errorMessage.value = '';
  try {
    const res = await api.callInstanceMethod('courses', props.recordId, 'rpc_preview_composition', {
      kwargs: { mode: selectedMode.value, mapping: mapping.value }
    });
    previewChildren.value = res.children_vals || [];
  } catch (e: any) {
    errorMessage.value = "Erreur lors de la prévisualisation: " + e.message;
  } finally {
    loading.value = false;
  }
}

async function saveComposition() {
  if (previewChildren.value.length === 0) return;
  loading.value = true;
  errorMessage.value = '';
  try {
    await api.callInstanceMethod('courses', props.recordId, 'rpc_save_composition', {
      kwargs: { children_vals: previewChildren.value }
    });
    // Fire generic event so the grids refresh
    window.dispatchEvent(new CustomEvent('resource:mutated', { detail: { resource_name: 'courses' } }));
    emit('success');
  } catch (e: any) {
    errorMessage.value = "Erreur lors de l'enregistrement: " + e.message;
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.composition-wizard {
  display: flex;
  flex-direction: column;
  gap: 20px;
  width: 100%;
  margin: 0 auto;
}
.wizard-header h2 {
  margin: 0 0 5px 0;
  color: var(--text-primary);
}
.section-block {
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 20px;
}
.section-title {
  margin: 0 0 12px 0;
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--accent-primary);
}
.mapping-table, .preview-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}
.mapping-table th, .preview-table th {
  text-align: left;
  padding: 8px;
  background: var(--bg-body);
  font-weight: 500;
  font-size: 0.85rem;
}
.mapping-table td, .preview-table td {
  padding: 8px;
  border-bottom: 1px solid var(--border-color);
  vertical-align: top;
}
.mapping-table th:nth-child(1) { width: 22%; }
.mapping-table th:nth-child(2) { width: 18%; }
.mapping-table th:nth-child(3) { width: 18%; }
.mapping-table th:nth-child(4) { width: 18%; }
.mapping-table th:nth-child(5) { width: 18%; }
.mapping-table th:nth-child(6) { width: 6%; }
.btn-delete-row {
  background: transparent;
  border: none;
  color: var(--danger);
  font-size: 1.2rem;
  cursor: pointer;
  padding: 4px 8px;
}
.btn-delete-row:hover {
  background: rgba(239, 68, 68, 0.1);
  border-radius: 4px;
}
.modes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}
.mode-card {
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 12px;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--bg-body);
}
.mode-card:hover:not(.disabled-mode) {
  border-color: var(--accent-primary);
  box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}
.selected-mode {
  border-color: var(--accent-primary);
  background: rgba(59, 130, 246, 0.1);
}
.disabled-mode {
  opacity: 0.5;
  cursor: not-allowed;
  filter: grayscale(1);
}
.mode-id {
  font-size: 1.2rem;
  font-weight: bold;
  color: var(--accent-primary);
}
.mode-desc {
  font-size: 0.85rem;
  margin-top: 4px;
}
.wizard-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
}
.error-banner {
  background: rgba(239, 68, 68, 0.1);
  color: var(--danger);
  padding: 12px;
  border-radius: 6px;
  border-left: 4px solid var(--danger);
  margin-bottom: 20px;
}
.preview-block {
  border-color: var(--success);
  background: rgba(16, 185, 129, 0.05);
}
</style>
