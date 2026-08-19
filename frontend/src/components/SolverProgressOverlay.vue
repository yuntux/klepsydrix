<template>
  <div class="solver-overlay-fullscreen" v-if="loading">
    <div class="spinner"></div>
    <div class="solver-overlay-label">
      {{ solverIsQueued ? 'En file d\'attente...' : solverStatusLabel }}
    </div>
    <div v-if="!solverIsQueued && solverPipelineTotalSteps > 1" class="solver-pipeline-step">
      Étape {{ solverPipelineStep }} sur {{ solverPipelineTotalSteps }}
    </div>
    <!-- Progression best-effort (voir solver.py) : le score dur/doux le plus récent connu peut
         manquer par intermittence (limitation du paquet timefold bêta), le temps écoulé/limite
         reste lui toujours fiable. Tant que la résolution est seulement en file d'attente (voir
         solver.py::SolverState, "Concurrence des résolutions"), ni le score ni le temps écoulé
         n'ont de sens (la résolution n'a pas encore démarré) — seule la position dans la file est
         affichée. -->
    <div class="solver-progress-info">
      <span v-if="solverIsQueued">
        Position {{ solverQueuePosition }} sur {{ solverQueueLength }}
      </span>
      <template v-else>
        <span v-if="solverProgress">Score : {{ solverProgress.hard_score }}H / {{ solverProgress.soft_score }}S</span>
        <span v-if="solverElapsedSeconds != null">
          Temps écoulé : {{ Math.round(solverElapsedSeconds) }}s{{ solverTimeLimitSeconds ? ` / ${solverTimeLimitSeconds}s max` : '' }}
        </span>
      </template>
      <BaseButton variant="danger" size="sm" @click="$emit('stop-solve')">
        Arrêter le calcul
      </BaseButton>
    </div>
  </div>
</template>

<script setup lang="ts">
// Couche plein écran affichée pendant toute résolution asynchrone du solveur (placement
// automatique, attribution des salles, optimisation — les trois lancés depuis un wizard générique,
// voir GenericWizard.vue::startsBackgroundJob), montée au niveau d'App.vue plutôt que dans
// TimetableGrid.vue : un wizard peut être déclenché depuis n'importe quel onglet (menu "Emploi du
// temps"), pas seulement depuis la grille elle-même, et la progression doit rester visible même si
// l'utilisateur navigue vers un autre onglet pendant le calcul.
import { computed } from 'vue';
import BaseButton from './BaseButton.vue';

const props = defineProps<{
  loading: boolean;
  solverProgress: { hard_score: number; soft_score: number } | null;
  solverElapsedSeconds: number | null;
  solverTimeLimitSeconds: number | null;
  solverIsQueued: boolean;
  solverQueuePosition: number | null;
  solverQueueLength: number;
  solverKind: string | null;
  solverPipelineStep: number;
  solverPipelineTotalSteps: number;
}>();

defineEmits<{
  (e: 'stop-solve'): void;
}>();

// Même table que l'ancien TimetableGrid.vue (voir SolverState.kind côté backend) — null/undefined
// (pas encore reçu un premier /status) retombe sur le libellé générique historique.
const SOLVER_KIND_LABELS: Record<string, string> = {
  COURSE_PLACEMENT: 'Placement automatique en cours...',
  CLASSROOM_ASSIGNMENT: 'Attribution des salles en cours...',
  OPTIMIZE_COURSE_PLACEMENT: 'Optimisation — placement des cours...',
  OPTIMIZE_CLASSROOM_ASSIGNMENT: 'Optimisation — attribution des salles...',
};
const solverStatusLabel = computed(() => {
  return (props.solverKind && SOLVER_KIND_LABELS[props.solverKind]) || 'Calcul de l\'emploi du temps optimal...';
});
</script>

<style scoped>
/* Même gabarit que .modal-overlay de BaseModal.vue (position fixed, z-index 1000) — seul pattern
   plein écran déjà établi dans le code — plutôt que .loader-overlay (position absolute, partagé
   avec d'autres loaders scopés à leur panneau, voir GenericList.vue) qui ne peut pas couvrir tout
   le viewport sans effet de bord sur ces autres usages. */
.solver-overlay-fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(4px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  gap: 16px;
  animation: fadeIn var(--transition-normal);
}

.spinner {
  width: 48px;
  height: 48px;
  border: 4px solid rgba(99, 102, 241, 0.15);
  border-top-color: var(--accent-primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.solver-overlay-label {
  color: var(--text-primary, #1e293b);
  font-weight: 500;
  font-size: 16px;
}

.solver-pipeline-step {
  font-size: 13px;
  color: #64748b;
}

.solver-progress-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  color: #475569;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}
</style>
