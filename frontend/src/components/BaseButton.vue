<template>
  <button
    :type="type"
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
// type par défaut 'button', PAS le défaut HTML natif ('submit') : un <button> sans attribut type,
// une fois niché dans un <form> (tout wizard, voir GenericForm.vue), soumet silencieusement ce
// formulaire au clic — un bouton purement décoratif (icône, bascule) qui n'a jamais explicitement
// demandé 'submit' ne doit jamais hériter de ce comportement par accident. Chaque bouton qui DOIT
// soumettre le déclare déjà explicitement (`type="submit"`, voir GenericForm.vue et les pages de
// connexion/mot de passe) — changer ce défaut ne change donc aucun comportement volontaire existant.
withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'danger' | 'flat' | 'action' | 'success';
  size?: 'sm' | 'md' | 'lg';
  type?: 'button' | 'submit' | 'reset';
  disabled?: boolean;
  loading?: boolean;
  iconOnly?: boolean;
}>(), {
  variant: 'primary',
  size: 'md',
  type: 'button',
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
