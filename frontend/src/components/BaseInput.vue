<template>
  <div class="base-input-wrapper">
    <label v-if="label" class="base-input-label">
      {{ label }}
      <span v-if="required" class="required-asterisk">*</span>
    </label>
    <div class="input-container" :class="{ 'has-error': !!error, 'is-disabled': disabled }">
      <slot name="prepend"></slot>
      <input
        class="base-input"
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :required="required"
        :min="min"
        :max="max"
        :step="step"
        @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
        @blur="$emit('blur', $event)"
      />
      <slot name="append"></slot>
    </div>
    <span v-if="error" class="error-message">{{ error }}</span>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  modelValue: string | number | null;
  label?: string;
  type?: string;
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
  error?: string;
  min?: number | string;
  max?: number | string;
  step?: number | string;
}>(), {
  type: 'text',
  disabled: false,
  required: false,
});

defineEmits<{
  (e: 'update:modelValue', value: string): void;
  (e: 'blur', event: FocusEvent): void;
}>();
</script>

<style scoped>
.base-input-wrapper {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
}
.base-input-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}
.required-asterisk {
  color: var(--accent-danger);
  margin-left: 2px;
}
.input-container {
  display: flex;
  align-items: center;
  background-color: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
  overflow: hidden;
}
.input-container:focus-within {
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent-primary) 20%, transparent);
}
.input-container.has-error {
  border-color: var(--accent-danger);
}
.input-container.has-error:focus-within {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent-danger) 20%, transparent);
}
.input-container.is-disabled {
  background-color: var(--bg-secondary);
  opacity: 0.7;
}
.base-input {
  flex: 1;
  border: none;
  background: transparent;
  padding: 8px 12px;
  font-size: 14px;
  color: var(--text-primary);
  outline: none;
  min-width: 0;
}
.base-input:disabled {
  cursor: not-allowed;
}
.error-message {
  font-size: 12px;
  color: var(--accent-danger);
  margin-top: 2px;
}
</style>
