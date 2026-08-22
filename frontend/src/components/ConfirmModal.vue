<!--
  Confirmation générique (Annuler / Confirmer) sur BaseModal — remplace window.confirm() partout où
  une simple question oui/non suffit (voir App.vue::onDeleteGeneric). Pour un cas qui a besoin de
  détailler un impact structurel (liste d'éléments affectés, etc.), voir ImpactConfirmDialog.vue,
  volontairement distinct : mélanger les deux aurait alourdi ce composant pour le cas simple, qui
  est de loin le plus fréquent.
-->
<template>
  <BaseModal
    :modelValue="show"
    :title="title"
    max-width="440px"
    :closeOnOutside="true"
    @update:modelValue="!$event && $emit('cancel')"
  >
    <p class="confirm-message">{{ message }}</p>

    <template #footer>
      <BaseButton variant="secondary" @click="$emit('cancel')">{{ cancelLabel }}</BaseButton>
      <BaseButton :variant="variant" @click="$emit('confirm')">{{ confirmLabel }}</BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import BaseModal from './BaseModal.vue';
import BaseButton from './BaseButton.vue';

withDefaults(defineProps<{
  show: boolean;
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'primary' | 'secondary';
}>(), {
  title: 'Confirmation',
  confirmLabel: 'Confirmer',
  cancelLabel: 'Annuler',
  variant: 'danger',
});

defineEmits<{
  (e: 'confirm'): void;
  (e: 'cancel'): void;
}>();
</script>

<style scoped>
.confirm-message {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.5;
}
</style>
