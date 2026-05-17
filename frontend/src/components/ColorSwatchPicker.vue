<template>
  <!-- Déclencheur : pastille colorée cliquable (ou disque barré si vide) -->
  <div
    ref="triggerRef"
    class="swatch-trigger"
    :class="{ 'swatch-trigger--empty': !localValue }"
    :style="localValue ? { backgroundColor: localValue } : {}"
    :title="localValue || 'Aucune couleur'"
    @click="togglePicker"
  >
    <span v-if="!localValue" class="swatch-empty-icon">Ø</span>
  </div>

  <!-- Palette téléportée au niveau <body> pour éviter tout problème d'overflow -->
  <Teleport to="body">
    <div
      v-if="isOpen"
      class="swatch-overlay"
      @mousedown.self="closePicker"
    >
      <div
        class="swatch-panel"
        :style="panelStyle"
      >
        <!-- Grille de 30 couleurs -->
        <div class="swatch-grid">
          <button
            v-for="color in colorPalette"
            :key="color"
            type="button"
            class="swatch-btn"
            :class="{ active: localValue === color }"
            :style="{ backgroundColor: color }"
            :title="color"
            @click="selectColor(color)"
          ></button>
        </div>
        <!-- Saisie libre du code hex -->
        <div class="swatch-hex-row">
          <span class="hex-hash">#</span>
          <input
            type="text"
            class="hex-input"
            :value="localValue?.replace('#', '') || ''"
            @change="selectColor('#' + ($event.target as HTMLInputElement).value.trim())"
            @keyup.enter="selectColor('#' + ($event.target as HTMLInputElement).value.trim()); closePicker()"
            placeholder="RRGGBB"
          />
          <div class="hex-preview" :style="{ backgroundColor: localValue || 'transparent' }"></div>
        </div>
        <!-- Bouton Effacer -->
        <button type="button" class="swatch-clear-btn" @click="clearColor">
          Ø Effacer la couleur
        </button>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';

const props = defineProps<{
  modelValue: string;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void;
  (e: 'change', value: string): void;
}>();

const localValue = ref(props.modelValue || '#3B82F6');
const isOpen = ref(false);
const triggerRef = ref<HTMLElement | null>(null);

// Position calculée du panneau (juste sous le déclencheur)
const panelTop = ref(0);
const panelLeft = ref(0);

const panelStyle = computed(() => ({
  position: 'fixed' as const,
  top: panelTop.value + 'px',
  left: panelLeft.value + 'px',
}));

// Sync prop → local
import { watch } from 'vue';
watch(() => props.modelValue, (v) => {
  localValue.value = v || '#3B82F6';
});

function togglePicker() {
  if (isOpen.value) {
    closePicker();
    return;
  }
  // Calculer la position du déclencheur dans le viewport
  if (triggerRef.value) {
    const rect = triggerRef.value.getBoundingClientRect();
    panelTop.value = rect.bottom + 6;
    panelLeft.value = rect.left;
  }
  isOpen.value = true;
}

function closePicker() {
  isOpen.value = false;
}

function clearColor() {
  localValue.value = '';
  emit('update:modelValue', '');
  emit('change', '');
  closePicker();
}

function selectColor(color: string) {
  localValue.value = color;
  emit('update:modelValue', color);
  emit('change', color);
  closePicker();
}

// Fermer sur Escape
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') closePicker();
}

onMounted(() => document.addEventListener('keydown', onKeydown));
onUnmounted(() => document.removeEventListener('keydown', onKeydown));

const colorPalette = [
  '#F87171', '#F97316', '#F59E0B', '#EAB308', '#84CC16', '#22C55E',
  '#10B981', '#14B8A6', '#06B6D4', '#0EA5E9', '#3B82F6', '#6366F1',
  '#8B5CF6', '#A855F7', '#D946EF', '#EC4899', '#F43F5E', '#6B7280',
  '#4F46E5', '#059669', '#DC2626', '#D97706', '#0891B2', '#2563EB',
  '#7C3AED', '#DB2777', '#0284C7', '#4B5563', '#9CA3AF', '#374151',
];
</script>

<style scoped>
.swatch-trigger {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.2);
  cursor: pointer;
  transition: transform 0.15s ease, border-color 0.15s ease;
  box-shadow: 0 1px 4px rgba(0,0,0,0.4);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.swatch-trigger:hover {
  transform: scale(1.15);
  border-color: rgba(255, 255, 255, 0.7);
}

.swatch-trigger--empty {
  background-color: rgba(255,255,255,0.06) !important;
  border-style: dashed;
}

.swatch-empty-icon {
  font-size: 11px;
  color: rgba(255,255,255,0.4);
  line-height: 1;
  user-select: none;
}

/* Overlay transparent qui capte le clic extérieur */
.swatch-overlay {
  position: fixed;
  inset: 0;
  z-index: 9998;
}

/* Panneau de la palette */
.swatch-panel {
  z-index: 9999;
  background: #202632;
  border: 1px solid #2b3342;
  border-radius: 10px;
  padding: 10px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.6);
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 196px;
  animation: fadeIn 0.1s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}

.swatch-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 6px;
}

.swatch-btn {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 1px solid rgba(255,255,255,0.15);
  cursor: pointer;
  padding: 0;
  transition: transform 0.1s ease, border-color 0.1s ease;
  box-shadow: inset 0 0 3px rgba(0,0,0,0.3);
}

.swatch-btn:hover {
  transform: scale(1.2);
  border-color: #fff;
}

.swatch-btn.active {
  border-color: #fff;
  box-shadow: 0 0 0 2px #6366f1;
  transform: scale(1.1);
}

.swatch-hex-row {
  display: flex;
  align-items: center;
  gap: 6px;
  border-top: 1px solid #2b3342;
  padding-top: 8px;
}

.hex-hash {
  color: #6b7280;
  font-family: monospace;
  font-weight: 700;
  font-size: 13px;
}

.hex-input {
  flex: 1;
  background: rgba(10,12,16,0.6);
  border: 1px solid #2b3342;
  border-radius: 4px;
  padding: 2px 6px;
  color: #f3f4f6;
  font-family: monospace;
  font-size: 12px;
  outline: none;
  text-transform: uppercase;
}

.hex-input:focus {
  border-color: #6366f1;
}

.hex-preview {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 1px solid rgba(255,255,255,0.15);
  flex-shrink: 0;
}

.swatch-clear-btn {
  width: 100%;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.25);
  border-radius: 6px;
  color: #f87171;
  font-size: 12px;
  font-family: var(--font-sans, sans-serif);
  padding: 5px 8px;
  cursor: pointer;
  text-align: center;
  transition: background 0.15s ease, border-color 0.15s ease;
  letter-spacing: 0.02em;
}

.swatch-clear-btn:hover {
  background: rgba(239, 68, 68, 0.18);
  border-color: rgba(239, 68, 68, 0.5);
}
</style>
