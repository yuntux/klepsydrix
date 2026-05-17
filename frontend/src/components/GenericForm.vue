<template>
  <div class="modal-overlay">
    <div class="generic-form-modal glass-morphism">
      <div class="form-header">
        <h3 class="form-title">{{ title }}</h3>
        <button class="btn-close" @click="$emit('cancel')">×</button>
      </div>

      <form @submit.prevent="handleSubmit" class="form-body">
        <div class="fields-grid">
          <div 
            v-for="field in fields" 
            :key="field.key" 
            class="form-group"
            :class="{ 'full-width': field.fullWidth }"
          >
            <label :for="field.key" class="form-label">
              {{ field.label }}
              <span v-if="field.required" class="required-indicator">*</span>
            </label>

            <!-- Input TEXTE -->
            <input 
              v-if="field.type === 'text'"
              :id="field.key"
              type="text"
              v-model="localModel[field.key]"
              :required="field.required"
              :placeholder="field.placeholder || ''"
              class="form-input"
            />

            <!-- Input NUMÉRIQUE -->
            <input 
              v-else-if="field.type === 'number'"
              :id="field.key"
              type="number"
              v-model.number="localModel[field.key]"
              :required="field.required"
              :min="field.min"
              :max="field.max"
              :step="field.step || '1'"
              class="form-input"
            />

            <!-- Input DATE -->
            <input 
              v-else-if="field.type === 'date'"
              :id="field.key"
              type="date"
              v-model="localModel[field.key]"
              :required="field.required"
              class="form-input"
            />

            <!-- Input BOOLEAN (Checkbox / Toggle) -->
            <div v-else-if="field.type === 'boolean'" class="toggle-wrapper">
              <label class="switch">
                <input 
                  type="checkbox" 
                  v-model="localModel[field.key]"
                />
                <span class="slider round"></span>
              </label>
              <span class="toggle-status">
                {{ localModel[field.key] ? 'Oui' : 'Non' }}
              </span>
            </div>

            <!-- Input SELECT (Menu déroulant optionnel) -->
            <select 
              v-else-if="field.type === 'select'"
              :id="field.key"
              v-model="localModel[field.key]"
              :required="field.required"
              class="select-custom form-select"
            >
              <option :value="null">-- Choisir --</option>
              <option 
                v-for="opt in field.options" 
                :key="opt.value" 
                :value="opt.value"
              >
                {{ opt.label }}
              </option>
            </select>
          </div>
        </div>

        <div class="form-actions">
          <button type="button" class="btn btn-secondary" @click="$emit('cancel')">
            Annuler
          </button>
          <button type="submit" class="btn btn-primary">
            Enregistrer
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';

interface FormField {
  key: string;
  label: string;
  type: 'text' | 'number' | 'boolean' | 'date' | 'select';
  required?: boolean;
  placeholder?: string;
  min?: number;
  max?: number;
  step?: string;
  fullWidth?: boolean;
  options?: Array<{ value: any; label: string }>;
}

const props = defineProps<{
  title: string;
  fields: FormField[];
  modelValue: Record<string, any>;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: Record<string, any>): void;
  (e: 'submit', value: Record<string, any>): void;
  (e: 'cancel'): void;
}>();

// Copie locale réactive pour éviter de modifier directement le modèle parent avant soumission
const localModel = ref<Record<string, any>>({});

watch(() => props.modelValue, (newVal) => {
  localModel.value = { ...newVal };
  // Initialiser les champs booléens par défaut
  props.fields.forEach(field => {
    if (field.type === 'boolean' && localModel.value[field.key] === undefined) {
      localModel.value[field.key] = false;
    }
    if (field.type === 'select' && localModel.value[field.key] === undefined) {
      localModel.value[field.key] = null;
    }
  });
}, { immediate: true, deep: true });

function handleSubmit() {
  emit('update:modelValue', localModel.value);
  emit('submit', localModel.value);
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(10, 12, 16, 0.8);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
  animation: fadeIn var(--transition-fast);
}

.generic-form-modal {
  width: 580px;
  max-width: 95%;
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 14px;
  overflow: hidden;
  box-shadow: var(--shadow-lg), 0 0 30px rgba(99, 102, 241, 0.15);
  display: flex;
  flex-direction: column;
}

.form-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 24px;
  border-bottom: 1px solid var(--border-color);
  background-color: rgba(23, 28, 36, 0.5);
}

.form-title {
  font-size: 16px;
  font-weight: 700;
  color: #fff;
}

.btn-close {
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-size: 24px;
  cursor: pointer;
  transition: color var(--transition-fast);
  line-height: 1;
}

.btn-close:hover {
  color: #fff;
}

.form-body {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-height: 80vh;
  overflow-y: auto;
}

.fields-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-group.full-width {
  grid-column: span 2;
}

.form-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.required-indicator {
  color: var(--accent-danger);
  margin-left: 2px;
}

.form-input, .form-select {
  background-color: rgba(10, 12, 16, 0.6);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 10px 14px;
  color: #fff;
  font-size: 14px;
  outline: none;
  font-family: var(--font-sans);
  transition: all var(--transition-fast);
}

.form-input:focus, .form-select:focus {
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
}

.form-select {
  width: 100%;
}

/* Switch toggle style */
.toggle-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 42px;
}

.switch {
  position: relative;
  display: inline-block;
  width: 48px;
  height: 24px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
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

.slider:before {
  position: absolute;
  content: "";
  height: 16px;
  width: 16px;
  left: 3px;
  bottom: 3px;
  background-color: var(--text-secondary);
  transition: .3s;
}

input:checked + .slider {
  background-color: rgba(99, 102, 241, 0.2);
  border-color: var(--accent-primary);
}

input:checked + .slider:before {
  transform: translateX(24px);
  background-color: var(--accent-primary);
}

.slider.round {
  border-radius: 34px;
}

.slider.round:before {
  border-radius: 50%;
}

.toggle-status {
  font-size: 13px;
  color: var(--text-primary);
}

/* Actions */
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 10px;
  border-top: 1px solid var(--border-color);
  padding-top: 16px;
}

.glass-morphism {
  background: rgba(32, 38, 50, 0.85);
  backdrop-filter: blur(12px);
}
</style>
