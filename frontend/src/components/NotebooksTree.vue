<template>
  <div class="notebooks-container">
    <!-- Level 1 Tabs -->
    <div class="tabs-level-1-wrapper" style="display: flex; justify-content: space-between; align-items: center;">
      <div class="tabs-level-1">
        <button
          v-for="tab in config"
          :key="tab.id"
          class="tab-btn-l1"
          :style="getTabStyle(tab, activeLevel1Id === tab.id)"
          :class="{ active: activeLevel1Id === tab.id }"
          @click="selectLevel1(tab.id)"
        >
          {{ tab.title }}
        </button>
      </div>

      <!-- Sélecteur de thème -->
      <button class="theme-toggle-btn" @click="toggleTheme" title="Changer de thème">
        {{ currentThemeIndex === 1 ? '🌙' : currentThemeIndex === 2 ? '⬛' : '☀️' }}
      </button>
    </div>

    <!-- Level 2 Sub-Tabs (if children exist on level 1) -->
    <div v-if="activeLevel1Node?.children && activeLevel1Node.children.length > 0" class="tabs-level-2-wrapper">
      <div class="tabs-level-2">
        <button
          v-for="subTab in activeLevel1Node.children"
          :key="subTab.id"
          class="tab-btn-l2"
          :style="getTabStyle(subTab, activeLevel2Id === subTab.id)"
          :class="{ active: activeLevel2Id === subTab.id }"
          @click="selectLevel2(subTab.id)"
        >
          {{ subTab.title }}
        </button>
      </div>
    </div>

    <!-- Level 3 Sub-Tabs (if children exist on level 2) -->
    <div v-if="activeLevel2Node?.children && activeLevel2Node.children.length > 0" class="tabs-level-3-wrapper">
      <div class="tabs-level-3">
        <button
          v-for="subSubTab in activeLevel2Node.children"
          :key="subSubTab.id"
          class="tab-btn-l3"
          :style="getTabStyle(subSubTab, activeLevel3Id === subSubTab.id)"
          :class="{ active: activeLevel3Id === subSubTab.id }"
          @click="selectLevel3(subSubTab.id)"
        >
          {{ subSubTab.title }}
        </button>
      </div>
    </div>

    <!-- Main Content Area -->
    <div class="notebook-content">
      <SplitPanel 
        v-if="activeLeafNode && activeLeafNode.panels && activeLeafNode.panels.length > 0" 
        :panels="activeLeafNode.panels"
      >
        <template #default="{ panel, index }">
          <slot name="panel" :panel="panel" :index="index"></slot>
        </template>
      </SplitPanel>
      <div v-else-if="activeLeafNode && (!activeLeafNode.panels || activeLeafNode.panels.length === 0)" class="empty-state-card">
        <div class="empty-illustration">📭</div>
        <span class="empty-title">{{ activeLeafNode.title }}</span>
        <span class="empty-subtitle">Cet espace est vide pour le moment.</span>
      </div>
      <div v-else class="empty-state">
        <div class="spinner"></div>
        <span>Chargement de la vue...</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import SplitPanel from './SplitPanel.vue';
import { fetchMenus } from '../services/api';

interface Panel {
  id: string;
  component: string;
  resourceKey?: string;
  width: string;
}

interface NotebookNode {
  id: string;
  title: string;
  backgroundColor?: string;
  borderColor?: string;
  children?: NotebookNode[];
  layout?: 'VERTICAL' | 'HORIZONTAL';
  panels?: Panel[];
}

const config = ref<NotebookNode[]>([]);

const themes = ['light', 'dark', 'strict'];
const currentThemeIndex = ref(0);

function toggleTheme() {
  currentThemeIndex.value = (currentThemeIndex.value + 1) % themes.length;
  const newTheme = themes[currentThemeIndex.value];
  if (newTheme === 'light') {
    document.documentElement.removeAttribute('data-theme');
  } else {
    document.documentElement.setAttribute('data-theme', newTheme);
  }
}

const activeLevel1Id = ref<string>('');
const activeLevel2Id = ref<string>('');
const activeLevel3Id = ref<string>('');

const emit = defineEmits<{
  (e: 'change-leaf', leaf: NotebookNode): void;
}>();

// Obtenir le nœud actif de niveau 1
const activeLevel1Node = computed(() => {
  return config.value.find(tab => tab.id === activeLevel1Id.value) || null;
});

onMounted(async () => {
  try {
    const data = await fetchMenus();
    config.value = data as NotebookNode[];
    // Initialiser la sélection au premier chargement si config est non vide
    if (config.value.length > 0 && !activeLevel1Id.value) {
      selectLevel1(config.value[0].id);
    }
  } catch (e) {
    console.error("Failed to load menus from backend:", e);
  }
});

// Obtenir le nœud actif de niveau 2
const activeLevel2Node = computed(() => {
  const node = activeLevel1Node.value;
  if (!node || !node.children) return null;
  return node.children.find(sub => sub.id === activeLevel2Id.value) || null;
});

// Obtenir le nœud actif de niveau 3
const activeLevel3Node = computed(() => {
  const node = activeLevel2Node.value;
  if (!node || !node.children) return null;
  return node.children.find(sub => sub.id === activeLevel3Id.value) || null;
});

// Obtenir le nœud feuille actif
const activeLeafNode = computed(() => {
  const node2 = activeLevel2Node.value;
  if (node2 && node2.children && node2.children.length > 0) {
    return node2.children.find(sub => sub.id === activeLevel3Id.value) || null;
  }
  const node1 = activeLevel1Node.value;
  if (node1 && node1.children && node1.children.length > 0) {
    return node1.children.find(sub => sub.id === activeLevel2Id.value) || null;
  }
  return node1;
});

// Émettre les changements de feuille pour que le parent se synchronise
watch(activeLeafNode, (newLeaf) => {
  if (newLeaf) {
    emit('change-leaf', newLeaf);
  }
}, { immediate: true });

function selectLevel1(id: string) {
  activeLevel1Id.value = id;
  const node = config.value.find(tab => tab.id === id);
  if (node && node.children && node.children.length > 0) {
    selectLevel2(node.children[0].id);
  } else {
    activeLevel2Id.value = '';
    activeLevel3Id.value = '';
  }
}

function selectLevel2(id: string) {
  activeLevel2Id.value = id;
  const parent = activeLevel1Node.value;
  if (!parent || !parent.children) return;
  const node = parent.children.find(sub => sub.id === id);
  if (node && node.children && node.children.length > 0) {
    activeLevel3Id.value = node.children[0].id;
  } else {
    activeLevel3Id.value = '';
  }
}

function selectLevel3(id: string) {
  activeLevel3Id.value = id;
}

// Styles dynamiques pour les onglets (couleurs personnalisées du JSON)
function getTabStyle(tab: NotebookNode, isActive: boolean) {
  const styles: Record<string, string> = {};

  if (isActive) {
    if (tab.backgroundColor) {
      styles['background-color'] = tab.backgroundColor;
      styles['color'] = '#FFFFFF';
      styles['font-weight'] = 'bold';
      styles['border-bottom'] = 'none';
    } else if (tab.borderColor) {
      styles['border-top'] = `4px solid ${tab.borderColor}`;
      styles['color'] = 'var(--text-primary)';
    }
  } else {
    // Onglet inactif
    if (tab.backgroundColor) {
      styles['border-bottom'] = `1px solid var(--border-color)`;
    }
  }
  
  return styles;
}

</script>

<style scoped>
.notebooks-container {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100vh;
  background-color: var(--bg-primary); /* Arrière-plan standard clair */
}

/* Wrappers des barres d'onglets pour une finition ultra premium */
.tabs-level-1-wrapper {
  background-color: var(--bg-secondary); /* Relief avec la seconde teinte */
  border-bottom: 1px solid var(--border-color);
  padding: 8px 16px 0 16px;
}

.tabs-level-1 {
  display: flex;
  gap: 4px;
}

.tab-btn-l1 {
  padding: 10px 20px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
  background-color: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-bottom: none;
  border-top-left-radius: var(--radius-md);
  border-top-right-radius: var(--radius-md);
  cursor: pointer;
  outline: none;
  transition: all 0.2s ease;
  position: relative;
  top: 1px;
}

.theme-toggle-btn {
  background: transparent;
  border: none;
  font-size: 18px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-md);
  transition: background-color 0.2s ease;
}

.theme-toggle-btn:hover {
  background-color: rgba(128, 128, 128, 0.15);
}

.tab-btn-l1:hover {
  background-color: var(--bg-card);
  color: var(--text-primary);
}

.tab-btn-l1.active {
  background-color: var(--bg-primary);
  color: var(--accent-primary);
  font-weight: 600;
  border-color: var(--border-color);
  border-bottom: 1px solid var(--bg-primary); /* Effet d'onglet fusionné */
  z-index: 2;
}

/* Onglets de niveau 2 */
.tabs-level-2-wrapper {
  background-color: var(--bg-surface);
  border-bottom: 1px solid var(--border-color);
  padding: 6px 16px 0 16px;
}

.tabs-level-2 {
  display: flex;
  gap: 4px;
}

.tab-btn-l2 {
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  background-color: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-bottom: none;
  border-top-left-radius: 3px;
  border-top-right-radius: 3px;
  cursor: pointer;
  outline: none;
  transition: all 0.2s ease;
  position: relative;
  top: 1px;
}

.tab-btn-l2:hover {
  background-color: var(--bg-card);
  color: var(--text-primary);
}

.tab-btn-l2.active {
  background-color: var(--bg-primary);
  color: var(--text-primary);
  font-weight: 600;
  border-color: var(--border-color);
  border-bottom: 1px solid var(--bg-primary);
  z-index: 2;
}

/* Onglets de niveau 3 (imbriqués de troisième niveau) - Style pilule premium */
.tabs-level-3-wrapper {
  background-color: var(--bg-primary);
  border-bottom: 1px solid var(--border-color);
  padding: 8px 16px 8px 16px;
}

.tabs-level-3 {
  display: flex;
  gap: 8px;
}

.tab-btn-l3 {
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  background-color: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: 20px; /* Pilule */
  cursor: pointer;
  outline: none;
  transition: all 0.2s ease;
}

.tab-btn-l3:hover {
  background-color: var(--bg-card);
  color: var(--text-primary);
}

.tab-btn-l3.active {
  background-color: var(--accent-primary);
  color: #FFFFFF;
  font-weight: 600;
  border-color: var(--accent-primary);
}

/* Zone de contenu des Notebooks */
.notebook-content {
  flex: 1;
  overflow: hidden;
  position: relative;
  background-color: var(--bg-primary);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
  gap: 12px;
}

.empty-state-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
  gap: 8px;
  background-color: var(--bg-primary);
}

.empty-illustration {
  font-size: 48px;
  margin-bottom: 8px;
}

.empty-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.empty-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-color);
  border-top-color: var(--accent-primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
