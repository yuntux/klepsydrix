<template>
  <div class="generic-wizard">
    <div v-if="loading" class="wizard-loading">
      <div class="spinner"></div>
    </div>
    <div v-if="errorMessage" class="wizard-error">{{ errorMessage }}</div>

    <div v-if="steps.length > 1" class="wizard-steps-indicator">
      <span
        v-for="(s, i) in steps"
        :key="s.id"
        class="wizard-step-pill"
        :class="{ 'is-active': i === currentStepIndex, 'is-done': i < currentStepIndex }"
      >{{ s.title || s.id }}</span>
    </div>

    <GenericForm
      v-if="currentStep"
      :key="currentStep.id"
      :title="currentStep.title || ''"
      :fields="currentStepFields"
      :modelValue="draft"
      inline
      :submitLabel="currentStep.submitLabel"
      @submit="onStepSubmit"
      @cancel="$emit('cancel')"
    />
  </div>
</template>

<script setup lang="ts">
// Coquille d'orchestration générique pour les assistants multi-étapes ("wizards") — pendant, pour
// les flux pilotés par RPC sans ressource propre, de ce que GenericForm.vue est pour l'édition
// d'un enregistrement unique. Ne réinvente pas le rendu de champ : chaque étape délègue
// entièrement à GenericForm (réutilisé tel quel), avec un `submitLabel` propre à l'étape. Pas de
// persistance en base du brouillon (délibéré, voir architecture.md) : l'état vit ici, dans ce
// composant, entre les appels RPC.
//
// Contrat d'une étape (déclaré côté backend, sur __actions__ du modèle, voir Course.__actions__) :
//   { id, title?, fields: FormField[], submitLabel?, rpc?: string,
//     rpcParams?: Record<paramName, cheminPointDansLeBrouillon>, isLast?: boolean }
// - fields : mêmes objets FormField que GenericForm (type, widget, widgetParams...) — les champs
//   complexes passent par le registre de widgets partagé (voir widgets/registry.ts), exactement
//   comme dans un formulaire classique.
// - rpc : nom de la méthode d'instance à appeler à la soumission de cette étape (facultatif : une
//   étape sans rpc avance simplement au brouillon accumulé, sans aller-retour serveur).
// - rpcParams : associe chaque paramètre attendu par la méthode RPC à un chemin (à points) dans le
//   brouillon accumulé — nécessaire quand un widget porte plusieurs valeurs sous une seule clé de
//   champ (ex: {mapping, mode} sous la clé "composition", voir CourseCompositionMapping.vue).
// - Le résultat JSON de l'appel RPC est fusionné tel quel dans le brouillon (Object.assign) : si
//   une clé de la réponse correspond à la clé d'un champ d'une étape suivante, ce champ est déjà
//   peuplé sans code de "plomberie" supplémentaire (ex: rpc_preview_composition renvoie
//   children_vals, lu directement par l'étape suivante qui porte un champ de cette même clé).
// - isLast (ou la dernière étape déclarée) : après l'appel RPC, ferme le wizard (`success`) au
//   lieu d'avancer à l'étape suivante.
import { ref, computed, reactive } from 'vue';
import GenericForm from '../GenericForm.vue';
import * as api from '../../services/api';

interface WizardStep {
  id: string;
  title?: string;
  fields: any[];
  submitLabel?: string;
  rpc?: string;
  rpcParams?: Record<string, string>;
  isLast?: boolean;
}

const props = defineProps<{
  recordId: number;
  model?: any;
  resourceKey: string;
  steps: WizardStep[];
}>();

const emit = defineEmits<{
  (e: 'cancel'): void;
  (e: 'success'): void;
}>();

const currentStepIndex = ref(0);
const loading = ref(false);
const errorMessage = ref('');
const draft = reactive<Record<string, any>>({});

const currentStep = computed<WizardStep | undefined>(() => props.steps[currentStepIndex.value]);

// Injecte dans widgetParams le contexte que seul le wizard connaît (l'enregistrement concret sur
// lequel il opère) — les steps sont déclarées génériquement sur le modèle, sans connaître à
// l'avance quel enregistrement sera composé.
const currentStepFields = computed(() => {
  return (currentStep.value?.fields || []).map((f: any) => ({
    ...f,
    widgetParams: {
      ...(f.widgetParams || {}),
      recordId: props.recordId,
      resourceKey: props.resourceKey,
      sourceRecord: props.model,
    },
  }));
});

function resolvePath(obj: any, path: string): any {
  return path.split('.').reduce((acc, key) => (acc == null ? undefined : acc[key]), obj);
}

async function onStepSubmit(payload: Record<string, any>) {
  Object.assign(draft, payload);
  const step = currentStep.value;
  if (!step) return;

  if (!step.rpc) {
    advanceOrFinish(step);
    return;
  }

  errorMessage.value = '';
  loading.value = true;
  try {
    const kwargs: Record<string, any> = {};
    for (const [paramName, path] of Object.entries(step.rpcParams || {})) {
      kwargs[paramName] = resolvePath(draft, path);
    }
    const result = await api.callInstanceMethod(props.resourceKey, props.recordId, step.rpc, { kwargs });
    if (result && typeof result === 'object') Object.assign(draft, result);
    advanceOrFinish(step);
  } catch (e: any) {
    errorMessage.value = e.message || "Erreur lors de l'exécution de l'étape.";
  } finally {
    loading.value = false;
  }
}

function advanceOrFinish(step: WizardStep) {
  const isLastStep = step.isLast || currentStepIndex.value === props.steps.length - 1;
  if (isLastStep) {
    window.dispatchEvent(new CustomEvent('resource:mutated', { detail: { resource_name: props.resourceKey } }));
    emit('success');
  } else {
    currentStepIndex.value++;
  }
}
</script>

<style scoped>
.generic-wizard {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.wizard-loading {
  display: flex;
  justify-content: center;
  padding: 20px;
}
.spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--border-color);
  border-top-color: var(--accent-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.wizard-error {
  background: rgba(239, 68, 68, 0.1);
  color: var(--accent-danger, #e74c3c);
  padding: 12px;
  border-radius: 6px;
  border-left: 4px solid var(--accent-danger, #e74c3c);
}
.wizard-steps-indicator {
  display: flex;
  gap: 8px;
}
.wizard-step-pill {
  font-size: 12px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  color: var(--text-muted);
}
.wizard-step-pill.is-active {
  color: var(--accent-primary);
  border-color: var(--accent-primary);
}
.wizard-step-pill.is-done {
  color: var(--accent-success, #10b981);
  border-color: var(--accent-success, #10b981);
}
</style>
