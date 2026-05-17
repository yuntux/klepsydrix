<template>
  <div 
    class="consolidated-chip" 
    :class="{ 
      'is-divergent': isDivergent, 
      'is-common': !isDivergent 
    }"
    v-tooltip="tooltipText"
  >
    <!-- Label -->
    <span class="chip-label">{{ label }}</span>

    <!-- Proportion Badge -->
    <span v-if="isDivergent" class="proportion-badge">
      [{{ count }}/{{ total }}]
    </span>
    
    <!-- Star/Indicator for common -->
    <span v-else class="common-check">✓</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  label: string;
  count: number;
  total: number;
  isDivergent: boolean;
}>();

const tooltipText = computed(() => {
  if (props.isDivergent) {
    return `${props.count} cours sur ${props.total} possèdent cet attribut (${props.label})`;
  }
  return `Attribut commun aux ${props.total} cours sélectionnés`;
});
</script>

<style scoped>
.consolidated-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  border-radius: 9999px;
  font-size: 12.5px;
  font-weight: 600;
  user-select: none;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  cursor: help;
}

/* Attribut divergent : style orange/jaune chaud texturé avec légère lueur */
.consolidated-chip.is-divergent {
  background: rgba(245, 158, 11, 0.12);
  border: 1px solid rgba(245, 158, 11, 0.45);
  color: #fbbf24;
}

.consolidated-chip.is-divergent:hover {
  background: rgba(245, 158, 11, 0.2);
  border-color: rgba(245, 158, 11, 0.7);
  box-shadow: 0 0 8px rgba(245, 158, 11, 0.35);
  transform: translateY(-1px);
}

/* Attribut commun : style violet/indigo doux */
.consolidated-chip.is-common {
  background: rgba(99, 102, 241, 0.12);
  border: 1px solid rgba(99, 102, 241, 0.35);
  color: #818cf8;
}

.consolidated-chip.is-common:hover {
  background: rgba(99, 102, 241, 0.2);
  border-color: rgba(99, 102, 241, 0.6);
  box-shadow: 0 0 8px rgba(99, 102, 241, 0.3);
  transform: translateY(-1px);
}

.chip-label {
  white-space: nowrap;
}

.proportion-badge {
  font-family: monospace;
  font-size: 11px;
  background-color: rgba(245, 158, 11, 0.2);
  padding: 1px 5px;
  border-radius: 4px;
  color: #fbbf24;
  font-weight: 700;
}

.common-check {
  font-size: 11px;
  color: #818cf8;
  font-weight: 700;
}
</style>
