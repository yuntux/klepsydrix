<template>
  <div class="base-logo" :class="size">
    <div class="base-logo-icon">
      <svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 3h14M5 21h14M7 3v3a5 5 0 0 0 5 5 5 5 0 0 0 5-5V3M7 21v-3a5 5 0 0 1 5-5 5 5 0 0 1 5 5v3"/></svg>
    </div>
    <span v-if="showText" class="base-logo-text">{{ label }}</span>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  size?: 'sm' | 'lg';
  showText?: boolean;
  label?: string;
}>(), {
  size: 'sm',
  showText: true,
  label: 'Klepsydrix',
});
</script>

<style scoped>
.base-logo { display: flex; align-items: center; gap: var(--spacing-sm); overflow: hidden; white-space: nowrap; }
.base-logo-icon { background: var(--accent-primary); border-radius: var(--radius-md); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.base-logo-icon svg { stroke: #fff; }
.base-logo-text { font-weight: 600; color: var(--text-primary); white-space: nowrap; }

.base-logo.sm .base-logo-icon { width: 26px; height: 26px; }
.base-logo.sm .base-logo-icon svg { width: 15px; height: 15px; }
.base-logo.sm .base-logo-text { font-size: 15px; }

.base-logo.lg .base-logo-icon { width: 32px; height: 32px; }
.base-logo.lg .base-logo-icon svg { width: 18px; height: 18px; }
.base-logo.lg .base-logo-text { font-size: 1.1rem; }
</style>
