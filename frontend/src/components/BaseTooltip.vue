<template>
  <span 
    class="help-tooltip-wrapper"
    @click.stop
    @mouseenter="onMouseEnter"
  >
    <span class="help-icon">?</span>
    <span class="help-tooltip" ref="tipRef" v-html="htmlContent"></span>
  </span>
</template>

<script setup lang="ts">
import { ref } from 'vue';

const props = defineProps<{
  htmlContent: string;
}>();

const tipRef = ref<HTMLElement | null>(null);

function onMouseEnter(e: MouseEvent) {
  if (!tipRef.value) return;
  const target = e.currentTarget as HTMLElement;
  const r = target.getBoundingClientRect();
  const tip = tipRef.value;
  Object.assign(tip.style, {
    position: 'fixed', 
    bottom: 'auto',
    left: Math.max(8, Math.min(r.left, window.innerWidth - 258)) + 'px',
    top: (r.top > tip.offsetHeight + 8 ? r.top - tip.offsetHeight - 8 : r.bottom + 8) + 'px'
  });
}
</script>
