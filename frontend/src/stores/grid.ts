import { defineStore } from 'pinia';
import { ref } from 'vue';

export const useGridStore = defineStore('grid', () => {
  // Sélection des cours sur la grille
  const selectedCourseIds = ref<number[]>([]);
  
  // Options d'affichage et outils d'aide au placement
  const autoTarget = ref<boolean>(false);
  const layoutMode = ref<string>('merged');
  const placementAssistantActive = ref<boolean>(false);
  const isDetailedView = ref<boolean>(false);
  
  function toggleCourseSelection(id: number, isMulti: boolean) {
    const isSelected = selectedCourseIds.value.includes(id);

    if (isMulti) {
      if (isSelected) {
        selectedCourseIds.value = selectedCourseIds.value.filter(x => x !== id);
      } else {
        selectedCourseIds.value.push(id);
      }
    } else {
      // Single selection mode
      if (isSelected && selectedCourseIds.value.length === 1) {
        selectedCourseIds.value = [];
      } else {
        selectedCourseIds.value = [id];
      }
    }
  }

  function clearCourseSelection() {
    selectedCourseIds.value = [];
  }

  return {
    selectedCourseIds,
    autoTarget,
    layoutMode,
    placementAssistantActive,
    isDetailedView,
    toggleCourseSelection,
    clearCourseSelection
  };
});
