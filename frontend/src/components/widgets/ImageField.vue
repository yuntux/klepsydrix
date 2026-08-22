<template>
  <div class="image-field">
    <!-- L'aperçu porte le ratio de l'image RÉELLEMENT stockée (voir onPreviewLoad) : une photo
         d'identité 35/45 s'affiche en 35/45, une image large en large. `object-fit: contain` en
         filet de sécurité — mieux vaut une bande vide qu'un visage rogné ou étiré. -->
    <img
      v-if="previewSrc"
      :src="previewSrc"
      class="image-field-preview"
      :style="previewStyle"
      alt=""
      @load="onPreviewLoad"
    />

    <div class="image-field-actions">
      <BinaryFileField
        :modelValue="modelValue"
        :disabled="disabled"
        @update:modelValue="$emit('update:modelValue', $event)"
      />
      <button
        v-if="!disabled"
        type="button"
        class="btn-webcam"
        title="Prendre une photo avec la webcam"
        @click.stop="captureOpen = true"
      >
        📷 Photo
      </button>
    </div>

    <WebcamCaptureModal
      v-if="!disabled"
      v-model="captureOpen"
      :ratio="ratio"
      :outputWidth="outputWidth"
      @capture="$emit('update:modelValue', $event)"
    />
  </div>
</template>

<script setup lang="ts">
// Widget spécialisé sélectionné via info={"widget": "image"} sur un champ binaire générique (voir
// BinaryFileField.vue et architecture.md) : ajoute un aperçu visuel et une capture par webcam
// au-dessus des mêmes actions Télécharger/Effacer/Parcourir, sans dupliquer leur logique.
// Enregistré dans widgets/registry.ts, contexts: ['form'] uniquement — une liste (GenericList.vue)
// n'affiche jamais l'image elle-même, seulement un badge de présence.
//
// `widgetParams` (déclarables dans le dict `info` du modèle ou dans ui.json) :
// - `photoRatio` : largeur/hauteur de la photo capturée. Défaut 35/45, le format d'une photo
//   d'identité française et européenne.
// - `photoWidth` : largeur en pixels de l'image produite (défaut 350, soit 250 dpi en 35×45 mm).
import { computed, ref } from 'vue';
import BinaryFileField, { type BinaryValue } from './BinaryFileField.vue';
import WebcamCaptureModal from './WebcamCaptureModal.vue';
import { ID_PHOTO_OUTPUT_WIDTH, ID_PHOTO_RATIO } from './photoCrop';

const props = defineProps<{
  modelValue: BinaryValue | null;
  field?: any;
  widgetParams?: any;
  disabled?: boolean;
  parentRecord?: any;
}>();

defineEmits<{
  (e: 'update:modelValue', value: BinaryValue | null): void;
}>();

const captureOpen = ref(false);
const naturalRatio = ref<number | null>(null);

const ratio = computed<number>(() => props.widgetParams?.photoRatio || ID_PHOTO_RATIO);
const outputWidth = computed<number>(() => props.widgetParams?.photoWidth || ID_PHOTO_OUTPUT_WIDTH);

const previewSrc = computed(() => {
  if (!props.modelValue?.data_base64) return null;
  return `data:${props.modelValue.mime_type || 'image/png'};base64,${props.modelValue.data_base64}`;
});

// Ratio lu sur l'image chargée, pas déduit du format de capture : le champ peut très bien contenir
// une image déposée par « Parcourir… », qui n'a aucune raison d'être au format photo d'identité.
// Tant qu'elle n'est pas chargée, on retombe sur le ratio de capture — jamais sur un carré, qui
// ferait sauter l'aperçu de forme au premier rendu.
const previewStyle = computed(() => ({ aspectRatio: String(naturalRatio.value ?? ratio.value) }));

function onPreviewLoad(event: Event) {
  const img = event.target as HTMLImageElement;
  if (img.naturalWidth && img.naturalHeight) {
    naturalRatio.value = img.naturalWidth / img.naturalHeight;
  }
}
</script>

<style scoped>
.image-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
}

.image-field-preview {
  /* Hauteur maîtrisée, largeur déduite du ratio réel de l'image (voir previewStyle) — l'inverse
     (deux dimensions figées) est exactement ce qui déformait ou rognait l'aperçu.
     `align-self: flex-start` est indispensable et non décoratif : le conteneur est un flex en
     colonne, dont l'`align-items: stretch` par défaut impose sa pleine largeur à l'image et écrase
     le `width: auto`. Mesuré : la boîte rendue faisait un ratio de 2,03 au lieu de 0,78, l'image
     flottant au milieu de bandes vides (invisible sans mesurer, `object-fit: contain` empêchant
     toute déformation apparente). */
  align-self: flex-start;
  /* Deux PLAFONDS, aucune dimension imposée : l'image prend sa taille naturelle, réduite si elle
     dépasse la hauteur d'aperçu ou la largeur disponible — dans les deux cas proportionnellement.
     Une `height` fixe convenait à une photo d'identité (plus haute que large) et donnait, pour une
     image panoramique, une boîte 285×140 au ratio 2,03 pour une image au ratio 4. */
  max-height: 140px;
  max-width: 100%;
  height: auto;
  width: auto;
  object-fit: contain;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  background: var(--bg-subtle, transparent);
}

.image-field-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.image-field-actions > :first-child {
  flex: 1;
  min-width: 0;
}

.btn-webcam {
  flex-shrink: 0;
  padding: 4px 10px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--text-primary);
  font-size: 0.85rem;
  cursor: pointer;
  white-space: nowrap;
  transition: background var(--transition-fast), border-color var(--transition-fast);
}

.btn-webcam:hover {
  background: var(--bg-hover, var(--bg-subtle));
  border-color: var(--color-primary);
}
</style>
