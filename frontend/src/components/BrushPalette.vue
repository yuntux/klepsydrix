<template>
  <div class="brush-palette" :class="{ 'is-disabled': disabled }">
    <span class="palette-label">Outil Vœu :</span>
    <div class="brush-buttons">
      <button 
        class="btn-brush brush-preferred" 
        :class="{ active: modelValue === 'Preferred' }"
        :disabled="disabled"
        @click="updateBrush('Preferred')"
        title="Préféré (Vert - Bonus)"
      >
        <span class="brush-dot bg-green"></span>
        Préféré
      </button>
      
      <button 
        class="btn-brush brush-undesirable" 
        :class="{ active: modelValue === 'Undesirable' }"
        :disabled="disabled"
        @click="updateBrush('Undesirable')"
        title="Indésirable (Orange - Pénalité)"
      >
        <span class="brush-dot bg-orange"></span>
        Indésirable
      </button>
      
      <button 
        class="btn-brush brush-unsuited" 
        :class="{ active: modelValue === 'Unsuited' }"
        :disabled="disabled"
        @click="updateBrush('Unsuited')"
        title="Indisponible / Strict (Rouge - Interdit)"
      >
        <span class="brush-dot bg-red"></span>
        Indisponible
      </button>

      <button 
        class="btn-brush brush-neutral" 
        :class="{ active: modelValue === 'Neutral' }"
        :disabled="disabled"
        @click="updateBrush('Neutral')"
        title="Gomme (Neutre - Pas de contrainte)"
      >
        <span class="brush-dot bg-neutral"></span>
        Neutre
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
type BrushType = 'Preferred' | 'Undesirable' | 'Unsuited' | 'Neutral';

const props = defineProps<{
  modelValue: BrushType;
  disabled?: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: BrushType): void;
}>();

function updateBrush(value: BrushType) {
  if (!props.disabled) {
    emit('update:modelValue', value);
  }
}
</script>

<style scoped>
.brush-palette {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brush-palette.is-disabled {
  opacity: 0.6;
  pointer-events: none;
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

.btn-brush:hover:not(:disabled) {
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
</style>
