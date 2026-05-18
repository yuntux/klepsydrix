<template>
  <header class="app-header">
    <div class="brand-section">
      <div class="logo-icon">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
        </svg>
      </div>
      <div>
        <h1 class="brand-name">Klepsydrix</h1>
        <div class="brand-tagline">Moteur d'Optimisation d'Emplois du Temps</div>
      </div>
    </div>

    <!-- Navigation principale -->
    <div class="header-nav">
      <button 
        class="nav-tab" 
        :class="{ active: activeTab === 'timetable' }"
        @click="$emit('update:activeTab', 'timetable')"
      >
        📅 Emploi du Temps
      </button>
      <button 
        class="nav-tab" 
        :class="{ active: activeTab === 'preferences' }"
        @click="$emit('update:activeTab', 'preferences')"
      >
        🎨 Saisie des Vœux
      </button>
      <button 
        class="nav-tab" 
        :class="{ active: activeTab === 'admin' }"
        @click="$emit('update:activeTab', 'admin')"
      >
        ⚙️ Gestion du Socle
      </button>
    </div>

    <!-- Filtres actifs (uniquement en mode Emploi du Temps) -->
    <div class="filters-bar" v-if="activeTab === 'timetable'">
      <div class="filter-item">
        <label>Mode de vue :</label>
        <select :value="viewMode" @change="$emit('update:viewMode', ($event.target as HTMLSelectElement).value)" class="select-custom">
          <option value="division">Par Classe (Division)</option>
          <option value="teacher">Par Enseignant</option>
          <option value="classroom">Par Salle</option>
        </select>
      </div>

      <div class="filter-item" v-if="viewMode === 'division'">
        <label>Classe :</label>
        <select :value="selectedId" @change="$emit('update:selectedId', Number(($event.target as HTMLSelectElement).value))" class="select-custom">
          <option v-for="d in divisions" :key="d.id" :value="d.id">{{ d.name }}</option>
        </select>
      </div>

      <div class="filter-item" v-else-if="viewMode === 'teacher'">
        <label>Enseignant :</label>
        <select :value="selectedId" @change="$emit('update:selectedId', Number(($event.target as HTMLSelectElement).value))" class="select-custom">
          <option v-for="t in teachers" :key="t.id" :value="t.id">{{ t.name }}</option>
        </select>
      </div>

      <div class="filter-item" v-else-if="viewMode === 'classroom'">
        <label>Salle :</label>
        <select :value="selectedId" @change="$emit('update:selectedId', Number(($event.target as HTMLSelectElement).value))" class="select-custom">
          <option v-for="c in classrooms" :key="c.id" :value="c.id">{{ c.name }} (Cap. {{ c.capacity }})</option>
        </select>
      </div>
    </div>

    <!-- Actions principales -->
    <div class="controls-group">
      <div class="score-pill" :class="{ 'score-perfect': scoreData && scoreData.hard_score === 0 && scoreData.soft_score === 0, 'score-warning': scoreData && (scoreData.hard_score < 0 || scoreData.soft_score < 0) }" :title="scoreData ? scoreData.summary : 'En attente...'">
        Score: {{ scoreData ? scoreData.hard_score : '?' }}H / {{ scoreData ? scoreData.soft_score : '?' }}S
      </div>

      <button class="btn btn-secondary" @click="$emit('reset')" :disabled="loading">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" width="16" height="16">
          <path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
        </svg>
        Réinitialiser
      </button>

      <button v-if="!loading" class="btn btn-primary" @click="$emit('solve')">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" width="16" height="16">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904 9 21l8.982-11.795M20.614 4c-.754.902-1.455 1.89-2.115 2.948m-2.115 2.948c-.07.112-.14.224-.21.336m-2.285 3.655A17.228 17.228 0 0 1 8.134 16m-4.82-4.48A17.185 17.185 0 0 1 11.25 8.134m0 0a17.185 17.185 0 0 1 4.82 4.48M11.25 8.134a17.228 17.228 0 0 0-3.116 7.866m0 0a17.22 17.22 0 0 0-4.819-4.48M12 8.5c.5-1 1.5-1.5 2.5-1.5s2 1 2.5 2c.5 1 .5 2-1 3.5s-2.5 2-3 3.5m0-7.5c-1-1-1.5-2.5-1.5-4s1-3 2.5-3s2.5 1.5 2.5 3c0 1.5-.5 3-1.5 4" />
        </svg>
        Résolution Auto
      </button>

      <button v-else class="btn" style="background-color: var(--accent-danger); color: white;" @click="$emit('stop')">
        <span class="spinner-small"></span>
        Arrêter
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { Division, Teacher, Classroom } from '../types';

defineProps<{
  activeTab: string;
  viewMode: string;
  selectedId: number | null;
  divisions: Division[];
  teachers: Teacher[];
  classrooms: Classroom[];
  loading: boolean;
  scoreData: { hard_score: number; soft_score: number; summary: string } | null;
}>();

defineEmits<{
  (e: 'update:activeTab', value: string): void;
  (e: 'update:viewMode', value: string): void;
  (e: 'update:selectedId', value: number): void;
  (e: 'solve'): void;
  (e: 'stop'): void;
  (e: 'reset'): void;
}>();
</script>

<style scoped>
.spinner-small {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.2);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  display: inline-block;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

.header-nav {
  display: flex;
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-color);
  padding: 4px;
  border-radius: 10px;
  gap: 4px;
}

.nav-tab {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  transition: all var(--transition-fast);
  font-family: var(--font-sans);
}

.nav-tab:hover {
  color: var(--text-primary);
  background-color: var(--bg-surface);
}

.nav-tab.active {
  color: var(--text-primary);
  background-color: var(--bg-card);
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--border-color);
}

.score-pill {
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 0.9rem;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  margin-right: 1rem;
  cursor: help;
  transition: all 0.2s;
  background-color: var(--bg-surface);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.score-perfect {
  background-color: rgba(34, 197, 94, 0.1);
  color: #22c55e;
  border: 1px solid rgba(34, 197, 94, 0.2);
}

.score-warning {
  background-color: rgba(239, 68, 68, 0.1);
  color: #ef4444;
  border: 1px solid rgba(239, 68, 68, 0.2);
}
</style>
