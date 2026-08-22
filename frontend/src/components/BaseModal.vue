<template>
  <!-- Téléporté <body> : sans ça, un ancêtre établissant son propre bloc de confinement pour les
       éléments `position: fixed` (transform, filter, backdrop-filter, contain…) — ex: .generic-
       list-container (backdrop-filter: blur, voir GenericList.vue) — confine ce modal à SES propres
       limites au lieu du plein viewport, malgré le `position: fixed` ci-dessous (bug constaté : la
       popin "Filtre personnalisé" rognée par le panneau qui l'héberge). -->
  <Teleport to="body">
    <div v-if="modelValue" class="modal-overlay" @mousedown.self="closeOnOutside ? $emit('update:modelValue', false) : null">
      <div class="modal-container glass-morphism" :style="{ maxWidth, width }">
        <div class="modal-header">
          <h3 class="modal-title">{{ title }}</h3>
          <button class="btn-close" @click="$emit('update:modelValue', false)">&times;</button>
        </div>
        <div class="modal-body" :class="{ 'no-padding': noPadding }">
          <slot></slot>
        </div>
        <div class="modal-footer" v-if="$slots.footer">
          <slot name="footer"></slot>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  modelValue: boolean;
  title?: string;
  maxWidth?: string;
  width?: string;
  closeOnOutside?: boolean;
  noPadding?: boolean;
}>(), {
  title: '',
  maxWidth: '800px',
  width: '100%',
  closeOnOutside: true,
  noPadding: false
});

defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
}>();
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: color-mix(in srgb, var(--text-primary) 80%, transparent);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn var(--transition-normal);
}
.modal-container {
  background-color: var(--bg-surface);
  border-radius: 12px;
  box-shadow: var(--shadow-lg);
  display: flex;
  flex-direction: column;
  max-height: 90vh;
  overflow: hidden;
  animation: slideUp var(--transition-normal);
  border: 1px solid var(--border-color);
}
.modal-header {
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.modal-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}
.btn-close {
  background: none;
  border: none;
  font-size: 24px;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0 4px;
  transition: color var(--transition-fast);
}
.btn-close:hover {
  color: var(--accent-danger);
}
.modal-body {
  padding: 24px;
  overflow-y: auto;
  flex: 1;
}

.modal-body.no-padding {
  padding: 0;
}
.modal-footer {
  padding: 16px 24px;
  border-top: 1px solid var(--border-color);
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  background-color: color-mix(in srgb, var(--text-primary) 5%, transparent);
}
@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>
