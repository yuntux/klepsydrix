<template>
  <div class="base-toggle-container" :style="wrapperStyle" :class="{ 'disabled-container': disabled }">
    <span v-if="$slots.left" class="toggle-label toggle-label-left" :class="{ 'active': !modelValue }" @click="!disabled && $emit('update:modelValue', false)">
      <slot name="left"></slot>
    </span>
    
    <label class="switch" :class="{
      'disabled-switch': disabled,
      'switch-divergent': isDivergent,
      'switch-modified': isModified
    }">
      <input type="checkbox" :checked="modelValue" :disabled="disabled" @change="$emit('update:modelValue', ($event.target as HTMLInputElement).checked)" />
      <span class="slider round"></span>
    </label>

    <span v-if="$slots.right" class="toggle-label toggle-label-right" :class="{ 'active': modelValue }" @click="!disabled && $emit('update:modelValue', true)">
      <slot name="right"></slot>
    </span>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: boolean;
  disabled?: boolean;
  isDivergent?: boolean;
  isModified?: boolean;
  wrapperStyle?: any;
}>();
defineEmits<{
  (e: 'update:modelValue', val: boolean): void;
}>();
</script>

<style scoped>
.base-toggle-container {
  display: inline-flex;
  align-items: center;
  gap: 12px;
}

.toggle-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: color 0.2s ease;
  user-select: none;
}

.toggle-label.active {
  color: var(--text-primary);
  font-weight: 600;
}

.disabled-container .toggle-label {
  cursor: not-allowed;
  opacity: 0.6;
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

.switch-divergent .slider {
  border-color: var(--color-divergent);
  background-color: rgba(245, 158, 11, 0.1);
}

.switch-modified .slider {
  border-color: var(--color-modified);
  background-color: rgba(16, 185, 129, 0.1);
}

.disabled-switch {
  cursor: not-allowed !important;
  opacity: 0.6;
  pointer-events: none;
}
</style>
