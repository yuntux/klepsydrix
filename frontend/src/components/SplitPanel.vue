<template>
  <div class="split-panel-container" ref="containerRef">
    <template v-for="(panel, index) in panels" :key="panel.id">
      <!-- Panel Content -->
      <div 
        class="split-panel-item" 
        :style="{ width: widths[index] || panel.width }"
      >
        <slot :panel="panel" :index="index"></slot>
      </div>
      
      <!-- Separator Splitter Bar -->
      <div 
        v-if="index < panels.length - 1" 
        class="split-panel-resizer"
        :class="{ dragging: activeResizerIndex === index }"
        @mousedown.prevent="startDrag($event, index)"
      >
        <div class="resizer-line"></div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';

interface Panel {
  id: string;
  component: string;
  resourceKey?: string;
  width: string;
}

const props = defineProps<{
  panels: Panel[];
}>();

const containerRef = ref<HTMLElement | null>(null);
const widths = ref<string[]>([]);
const activeResizerIndex = ref<number | null>(null);

// Initialiser les largeurs par défaut depuis les propriétés des panels
function initWidths() {
  widths.value = props.panels.map(p => p.width);
}

onMounted(() => {
  initWidths();
});

watch(() => props.panels, () => {
  initWidths();
}, { deep: true });

// Gestion du drag-and-drop pour le redimensionnement vertical (horizontal sizing)
let startX = 0;
let initialLeftWidth = 0;
let initialRightWidth = 0;
let leftIndex = 0;
let rightIndex = 0;

function startDrag(event: MouseEvent, index: number) {
  if (!containerRef.value) return;
  
  activeResizerIndex.value = index;
  leftIndex = index;
  rightIndex = index + 1;
  
  startX = event.clientX;
  
  // Obtenir les largeurs initiales en pixels
  const items = containerRef.value.querySelectorAll('.split-panel-item');
  const leftItem = items[leftIndex] as HTMLElement;
  const rightItem = items[rightIndex] as HTMLElement;
  
  initialLeftWidth = leftItem.getBoundingClientRect().width;
  initialRightWidth = rightItem.getBoundingClientRect().width;
  
  window.addEventListener('mousemove', handleDrag);
  window.addEventListener('mouseup', stopDrag);
}

function handleDrag(event: MouseEvent) {
  if (activeResizerIndex.value === null || !containerRef.value) return;
  
  const deltaX = event.clientX - startX;
  const newLeftWidthPx = initialLeftWidth + deltaX;
  const newRightWidthPx = initialRightWidth - deltaX;
  
  // Contrainte de largeur minimale (150px) pour chaque panneau
  if (newLeftWidthPx < 150 || newRightWidthPx < 150) return;
  
  const totalContainerWidth = containerRef.value.getBoundingClientRect().width;
  
  // Convertir en pourcentage
  const leftPercent = (newLeftWidthPx / totalContainerWidth) * 100;
  const rightPercent = (newRightWidthPx / totalContainerWidth) * 100;
  
  widths.value[leftIndex] = `${leftPercent}%`;
  widths.value[rightIndex] = `${rightPercent}%`;
}

function stopDrag() {
  activeResizerIndex.value = null;
  window.removeEventListener('mousemove', handleDrag);
  window.removeEventListener('mouseup', stopDrag);
}
</script>

<style scoped>
.split-panel-container {
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
  position: relative;
  background-color: transparent;
}

.split-panel-item {
  height: 100%;
  overflow: auto;
  position: relative;
  display: flex;
  flex-direction: column;
}

.split-panel-resizer {
  width: 10px;
  min-width: 10px;
  height: 100%;
  cursor: col-resize;
  display: flex;
  justify-content: center;
  align-items: center;
  position: relative;
  z-index: 10;
  user-select: none;
  background-color: transparent;
  transition: background-color 0.2s ease;
}

.split-panel-resizer:hover,
.split-panel-resizer.dragging {
  background-color: rgba(99, 102, 241, 0.08); /* Indigo léger */
}

.resizer-line {
  width: 2px;
  height: 100%;
  background-color: #E2E8F0; /* Border slate-200 */
  transition: background-color 0.2s ease, width 0.2s ease;
}

.split-panel-resizer:hover .resizer-line,
.split-panel-resizer.dragging .resizer-line {
  background-color: #6366F1; /* Indigo-500 */
  width: 4px;
}
</style>
