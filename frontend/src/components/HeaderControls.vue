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

    <!-- Filtres actifs -->
    <div class="filters-bar">
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
      <button class="btn btn-secondary" @click="$emit('reset')" :disabled="loading">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" width="16" height="16">
          <path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
        </svg>
        Réinitialiser
      </button>

      <button class="btn btn-primary" @click="$emit('solve')" :disabled="loading">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" width="16" height="16" v-if="!loading">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904 9 21l8.982-11.795M20.614 4c-.754.902-1.455 1.89-2.115 2.948m-2.115 2.948c-.07.112-.14.224-.21.336m-2.285 3.655A17.228 17.228 0 0 1 8.134 16m-4.82-4.48A17.185 17.185 0 0 1 11.25 8.134m0 0a17.185 17.185 0 0 1 4.82 4.48M11.25 8.134a17.228 17.228 0 0 0-3.116 7.866m0 0a17.22 17.22 0 0 0-4.819-4.48M12 8.5c.5-1 1.5-1.5 2.5-1.5s2 1 2.5 2c.5 1 .5 2-1 3.5s-2.5 2-3 3.5m0-7.5c-1-1-1.5-2.5-1.5-4s1-3 2.5-3s2.5 1.5 2.5 3c0 1.5-.5 3-1.5 4" />
        </svg>
        <span class="spinner-small" v-else></span>
        {{ loading ? 'Résolution...' : 'Résolution Auto' }}
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { Division, Teacher, Classroom } from '../types';

defineProps<{
  viewMode: string;
  selectedId: number | null;
  divisions: Division[];
  teachers: Teacher[];
  classrooms: Classroom[];
  loading: boolean;
}>();

defineEmits<{
  (e: 'update:viewMode', value: string): void;
  (e: 'update:selectedId', value: number): void;
  (e: 'solve'): void;
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
</style>
