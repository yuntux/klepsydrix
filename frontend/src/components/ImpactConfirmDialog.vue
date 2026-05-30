<template>
  <div v-if="show" class="modal-overlay" @click.self="$emit('cancel')">
    <div class="modal-card glass-morphism animate-pop">
      <!-- En-tête -->
      <div class="modal-header">
        <div class="header-icon-wrapper">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="icon-warning">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
          </svg>
        </div>
        <div class="header-text">
          <h3 class="modal-title">{{ title }}</h3>
          <p class="modal-subtitle">Impact structurel détecté sur la grille horaire</p>
        </div>
      </div>

      <!-- Corps du modal -->
      <div class="modal-body">
        <div class="alert-message">
          <span class="highlight">{{ impactedCount }} séance(s)</span> vont être impactée(s) et passées au statut <span class="unplaced-badge">NON PLANIFIÉ</span> si vous validez ce changement.
        </div>

        <div class="sessions-list-container">
          <div class="list-header">Liste des séances impactées :</div>
          <div class="sessions-scroll">
            <div v-for="sess in impactedSessions" :key="sess.session_id" class="session-item">
              <div class="session-main">
                <span class="session-label">{{ sess.course_label }}</span>
                <span class="session-reason">{{ sess.reason }}</span>
              </div>
              <div class="session-meta">
                <span class="session-ts">{{ sess.timeslot }}</span>
              </div>
            </div>
          </div>
        </div>

        <p class="confirmation-question">Voulez-vous vraiment appliquer cette action ? Cette opération est irréversible.</p>
      </div>

      <!-- Pied de page -->
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="$emit('cancel')">Annuler</button>
        <button class="btn btn-danger" @click="$emit('confirm')">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="icon-btn">
            <path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
          </svg>
          Confirmer la suppression
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface ImpactedSession {
  session_id: number;
  course_label: string;
  timeslot: string;
  reason: string;
}

defineProps<{
  show: boolean;
  title: string;
  impactedCount: number;
  impactedSessions: ImpactedSession[];
}>();

defineEmits<{
  (e: 'confirm'): void;
  (e: 'cancel'): void;
}>();
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(6, 8, 12, 0.75);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 9999;
  backdrop-filter: blur(8px);
}

.modal-card {
  width: 100%;
  max-width: 580px;
  background: rgba(30, 36, 48, 0.95);
  border: 1px solid rgba(239, 68, 68, 0.35);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 10px 10px -5px rgba(0, 0, 0, 0.4);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.glass-morphism {
  background: rgba(32, 38, 50, 0.9);
  backdrop-filter: blur(20px);
}

.animate-pop {
  animation: popIn 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes popIn {
  from {
    opacity: 0;
    transform: scale(0.92) translateY(10px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

.modal-header {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.header-icon-wrapper {
  background-color: rgba(239, 68, 68, 0.15);
  color: #f87171;
  padding: 12px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.icon-warning {
  width: 28px;
  height: 28px;
}

.header-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.modal-title {
  font-size: 18px;
  font-weight: 700;
  color: #fff;
}

.modal-subtitle {
  font-size: 13px;
  color: var(--text-muted);
}

.modal-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.alert-message {
  background-color: rgba(239, 68, 68, 0.08);
  border-left: 4px solid var(--accent-danger);
  padding: 12px 16px;
  border-radius: 0 8px 8px 0;
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.5;
}

.highlight {
  font-weight: 700;
  color: #f87171;
}

.unplaced-badge {
  background-color: rgba(239, 68, 68, 0.2);
  color: #f87171;
  padding: 2px 6px;
  border-radius: var(--radius-md);
  font-size: 12px;
  font-weight: 700;
}

.sessions-list-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.list-header {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.sessions-scroll {
  max-height: 220px;
  overflow-y: auto;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background-color: rgba(10, 12, 16, 0.35);
  border-radius: var(--radius-md);
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.session-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background-color: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: var(--radius-md);
  transition: background-color 0.2s;
}

.session-item:hover {
  background-color: rgba(255, 255, 255, 0.04);
}

.session-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.session-label {
  font-size: 13px;
  font-weight: 600;
  color: #fff;
}

.session-reason {
  font-size: 11px;
  color: var(--accent-danger);
}

.session-meta {
  display: flex;
  align-items: center;
}

.session-ts {
  background-color: rgba(99, 102, 241, 0.15);
  color: #818cf8;
  border: 1px solid rgba(99, 102, 241, 0.25);
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-weight: 600;
}

.confirmation-question {
  font-size: 13.5px;
  font-weight: 500;
  color: var(--bg-secondary);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  padding-top: 16px;
}

/* Boutons premium */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 20px;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  outline: none;
  font-family: inherit;
}

.btn-secondary {
  background-color: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: var(--bg-secondary);
}

.btn-secondary:hover {
  background-color: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.btn-danger {
  background-color: var(--accent-danger);
  border: none;
  color: #fff;
}

.btn-danger:hover {
  background-color: #dc2626;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.35);
}

.btn-danger:active {
  transform: translateY(0);
}

.icon-btn {
  width: 16px;
  height: 16px;
}
</style>
