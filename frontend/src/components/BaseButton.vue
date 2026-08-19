<template>
  <button 
    :class="['btn', `btn-${variant}`, `btn-${size}`, { 'btn-icon-only': iconOnly }]" 
    :disabled="disabled || loading"
    @click="$emit('click', $event)"
  >
    <span v-if="loading" class="spinner-small"></span>
    <slot name="icon" v-else></slot>
    <span v-if="!iconOnly && $slots.default" class="btn-text">
      <slot></slot>
    </span>
  </button>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'danger' | 'flat' | 'action' | 'success';
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
  loading?: boolean;
  iconOnly?: boolean;
}>(), {
  variant: 'primary',
  size: 'md',
  disabled: false,
  loading: false,
  iconOnly: false
});

defineEmits<{
  (e: 'click', event: MouseEvent): void;
}>();
</script>

<style scoped>
.btn-text {
  display: inline-block;
}
.spinner-small {
  width: 16px;
  height: 16px;
  border: 2px solid color-mix(in srgb, currentColor 30%, transparent);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  display: inline-block;
}
</style>
