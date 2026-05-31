<template>
  <div class="shell">
    <div class="sidebar" :class="{ collapsed: isSidebarCollapsed }" id="sidebar">
      <button class="sidebar-toggle" @click="toggleSidebar" title="Ouvrir / fermer le menu">
        <svg viewBox="0 0 24 24" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M15 6l-6 6 6 6"/>
        </svg>
      </button>

      <div class="sidebar-inner">
        <div class="sidebar-header">
          <div class="logo">
            <div class="logo-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 3h14M5 21h14M7 3v3a5 5 0 0 0 5 5 5 5 0 0 0 5-5V3M7 21v-3a5 5 0 0 1 5-5 5 5 0 0 1 5 5v3"/></svg>
            </div>
            <span class="logo-text">Klepsydrix</span>
          </div>
        </div>

        <div class="sidebar-body">
          <template v-for="l1 in config" :key="l1.id">
            <!-- Level 1 as Group -->
            <template v-if="l1.children && l1.children.length > 0">
              <div class="nav-group-header" :class="{ open: isGroupOpen(l1.id) }" role="button" tabindex="0" @click="toggleGroup(l1, $event)" @keydown.enter="toggleGroup(l1, $event)">
                <MenuIcon :name="l1.icon || 'calendar'" />
                <span class="label">{{ l1.title }}</span>
                <svg class="chevron" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>
              </div>
              <div class="submenu" :class="{ open: isGroupOpen(l1.id) }" :style="{ maxHeight: isGroupOpen(l1.id) ? '1500px' : '0' }">
                <template v-for="l2 in l1.children" :key="l2.id">
                  <!-- Level 2 as Group -->
                  <template v-if="l2.children && l2.children.length > 0">
                    <div class="submenu-item has-children" :class="{ open: isGroupOpen(l2.id) }" role="button" tabindex="0" @click="toggleSubGroup(l2.id)" @keydown.enter="toggleSubGroup(l2.id)">
                      {{ l2.title }}
                      <svg class="sub-chevron" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>
                    </div>
                    <div class="sub-submenu" :class="{ open: isGroupOpen(l2.id) }" :style="{ maxHeight: isGroupOpen(l2.id) ? '800px' : '0' }">
                      <div v-for="l3 in l2.children" :key="l3.id" 
                           class="sub-submenu-item" 
                           :class="{ active: activeLeafId === l3.id }" 
                           role="button" tabindex="0"
                           @click="selectLeaf(l3, l2, l1)" @keydown.enter="selectLeaf(l3, l2, l1)">
                        {{ l3.title }}
                      </div>
                    </div>
                  </template>
                  <!-- Level 2 as Leaf -->
                  <template v-else>
                    <div class="submenu-item" :class="{ active: activeLeafId === l2.id }" role="button" tabindex="0" @click="selectLeaf(l2, l1, null)" @keydown.enter="selectLeaf(l2, l1, null)">
                      {{ l2.title }}
                    </div>
                  </template>
                </template>
              </div>
            </template>
            <!-- Level 1 as Leaf -->
            <template v-else>
              <div class="nav-item" :class="{ active: activeLeafId === l1.id }" role="button" tabindex="0" @click="selectLeaf(l1, null, null)" @keydown.enter="selectLeaf(l1, null, null)">
                <MenuIcon :name="l1.icon || 'calendar'" />
                <span class="label">{{ l1.title }}</span>
                <div class="tooltip-tip">{{ l1.title }}</div>
              </div>
            </template>
          </template>
        </div>

        <div class="sidebar-footer">
          <div class="nav-item" role="button" tabindex="0" @click="toggleTheme" @keydown.enter="toggleTheme">
            <div style="display:flex; align-items:center; justify-content:center; width: 18px; height: 18px; font-size: 14px; flex-shrink: 0;">
              {{ currentThemeIndex === 1 ? '🌙' : currentThemeIndex === 2 ? '⬛' : '☀️' }}
            </div>
            <span class="label">Changer de Thème</span>
            <div class="tooltip-tip">Changer le thème</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Mini Popups when collapsed -->
    <Teleport to="body">
      <div v-if="isSidebarCollapsed && activePopupNode" 
           class="mini-popup visible" 
           :style="{ top: popupPos.top + 'px', left: popupPos.left + 'px' }"
           @click.stop>
        <div class="mini-popup-title">{{ activePopupNode.title }}</div>
        
        <template v-for="l2 in activePopupNode.children" :key="l2.id">
          <template v-if="l2.children && l2.children.length > 0">
            <div class="mini-popup-item" style="font-weight:500;color:var(--text-primary);cursor:default;gap:4px">
              <span style="opacity:.4;font-size:10px">▸</span> {{ l2.title }}
            </div>
            <div v-for="l3 in l2.children" :key="l3.id"
                 class="mini-popup-item mini-popup-subitem" 
                 :class="{ active: activeLeafId === l3.id }"
                 @click="selectLeaf(l3, l2, activePopupNode)">
              {{ l3.title }}
            </div>
          </template>
          <template v-else>
            <div class="mini-popup-item" 
                 :class="{ active: activeLeafId === l2.id }"
                 @click="selectLeaf(l2, activePopupNode, null)">
              {{ l2.title }}
            </div>
          </template>
        </template>
      </div>
    </Teleport>

    <div class="main">
      <div class="topbar">
        <span class="topbar-title">
          <template v-for="(crumb, i) in breadcrumbParts" :key="i">
            <span class="breadcrumb-sep" v-if="i > 0">/</span>
            <span class="breadcrumb-segment" :class="{ 'breadcrumb-last': i === breadcrumbParts.length - 1 }">
              <MenuIcon v-if="crumb.icon" :name="crumb.icon" />
              {{ crumb.title }}
            </span>
          </template>
        </span>
      </div>
      <div class="content">
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
  </div>
</template>

<script setup lang="ts">
import { ref, shallowRef, onMounted, onUnmounted } from 'vue';
import SplitPanel from './SplitPanel.vue';
import MenuIcon from './MenuIcon.vue';
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
  icon?: string;
  backgroundColor?: string;
  borderColor?: string;
  children?: NotebookNode[];
  layout?: 'VERTICAL' | 'HORIZONTAL';
  panels?: Panel[];
}

const config = shallowRef<NotebookNode[]>([]);
const isSidebarCollapsed = ref(false);
const openGroupIds = ref<Set<string>>(new Set());
const activeLeafId = ref<string>('');
const activeLeafNode = ref<NotebookNode | null>(null);
const breadcrumbParts = ref<{ title: string; icon?: string }[]>([]);

const activePopupNode = ref<NotebookNode | null>(null);
const popupPos = ref({ top: 0, left: 0 });

const themes = ['light', 'dark', 'strict'];
const currentThemeIndex = ref(0);

const emit = defineEmits<{
  (e: 'change-leaf', leaf: NotebookNode): void;
}>();

function toggleSidebar() {
  isSidebarCollapsed.value = !isSidebarCollapsed.value;
  activePopupNode.value = null;
}

function toggleTheme() {
  currentThemeIndex.value = (currentThemeIndex.value + 1) % themes.length;
  const newTheme = themes[currentThemeIndex.value];
  if (newTheme === 'light') {
    document.documentElement.removeAttribute('data-theme');
  } else {
    document.documentElement.setAttribute('data-theme', newTheme);
  }
}

function toggleGroup(node: NotebookNode, event: Event) {
  if (isSidebarCollapsed.value) {
    const el = event.currentTarget as HTMLElement;
    const rect = el.getBoundingClientRect();
    if (activePopupNode.value?.id === node.id) {
      activePopupNode.value = null;
    } else {
      activePopupNode.value = node;
      popupPos.value = { top: rect.top, left: rect.right + 8 };
    }
  } else {
    if (openGroupIds.value.has(node.id)) {
      openGroupIds.value.delete(node.id);
    } else {
      openGroupIds.value.add(node.id);
    }
  }
}

function toggleSubGroup(id: string) {
  if (openGroupIds.value.has(id)) {
    openGroupIds.value.delete(id);
  } else {
    openGroupIds.value.add(id);
  }
}

function isGroupOpen(id: string) {
  return openGroupIds.value.has(id);
}

function selectLeaf(leaf: NotebookNode, parent?: NotebookNode | null, grandParent?: NotebookNode | null) {
  activeLeafId.value = leaf.id;
  activeLeafNode.value = leaf;
  
  const parts: { title: string; icon?: string }[] = [];
  if (grandParent) parts.push({ title: grandParent.title, icon: grandParent.icon });
  if (parent) parts.push({ title: parent.title, icon: parent.icon });
  parts.push({ title: leaf.title, icon: leaf.icon });
  breadcrumbParts.value = parts;

  activePopupNode.value = null;
  emit('change-leaf', leaf);
}

function onDocClick(e: Event) {
  const target = e.target as HTMLElement;
  if (!target.closest('.mini-popup') && !target.closest('.nav-group-header')) {
    activePopupNode.value = null;
  }
}

onMounted(async () => {
  document.addEventListener('click', onDocClick);
  try {
    const data = await fetchMenus();
    config.value = data as NotebookNode[];
    if (config.value.length > 0) {
      let firstLeaf = config.value[0];
      let p = null, gp = null;
      if (firstLeaf.children && firstLeaf.children.length > 0) {
        gp = firstLeaf;
        firstLeaf = firstLeaf.children[0];
        if (firstLeaf.children && firstLeaf.children.length > 0) {
          p = firstLeaf;
          firstLeaf = firstLeaf.children[0];
        }
      }
      if (gp) openGroupIds.value.add(gp.id);
      if (p) openGroupIds.value.add(p.id);
      selectLeaf(firstLeaf, p, gp);
    }
  } catch (e) {
    console.error("Failed to load menus from backend:", e);
  }
});

onUnmounted(() => {
  document.removeEventListener('click', onDocClick);
});
</script>

<style scoped>
*, *::before, *::after { box-sizing: border-box; }

.shell { display: flex; height: 100vh; width: 100vw; background: var(--bg-primary); }
.main { border-radius: 0; overflow: hidden; flex: 1; display: flex; flex-direction: column; min-width: 0; }

/* ── SIDEBAR ── */
.sidebar { width: 220px; min-width: 220px; background: var(--bg-secondary); border-right: 1px solid var(--border-color); display: flex; flex-direction: column; transition: width 0.22s cubic-bezier(.4,0,.2,1), min-width 0.22s cubic-bezier(.4,0,.2,1); flex-shrink: 0; position: relative; overflow: visible; z-index: 50; }
.sidebar.collapsed { width: 52px; min-width: 52px; }
.sidebar-inner { display: flex; flex-direction: column; flex: 1; overflow: hidden; }

/* ── DISQUE TOGGLE ── */
.sidebar-toggle { position: absolute; top: 68px; right: -12px; width: 24px; height: 24px; background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 50%; cursor: pointer; display: flex; align-items: center; justify-content: center; z-index: 100; box-shadow: var(--shadow-sm); padding: 0; transition: background 0.12s, box-shadow 0.12s; }
.sidebar-toggle:hover { background: var(--bg-surface); box-shadow: var(--shadow-md); }
.sidebar-toggle svg { width: 13px; height: 13px; stroke: var(--text-secondary); transition: transform 0.22s cubic-bezier(.4,0,.2,1); }
.sidebar.collapsed .sidebar-toggle svg { transform: rotate(180deg); }

/* ── HEADER ── */
.sidebar-header { display: flex; align-items: center; padding: 0 24px 0 14px; border-bottom: 1px solid var(--border-color); height: 44px; flex-shrink: 0; }
.sidebar.collapsed .sidebar-header { padding: 0; justify-content: center; }
.logo { display: flex; align-items: center; gap: 8px; overflow: hidden; white-space: nowrap; }
.logo-icon { width: 26px; height: 26px; background: var(--accent-primary); border-radius: var(--radius-md); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.logo-icon svg { width: 15px; height: 15px; stroke: #fff; }
.logo-text { font-size: 15px; font-weight: 600; color: var(--text-primary); white-space: nowrap; opacity: 1; transition: opacity 0.15s; }
.sidebar.collapsed .logo-text { opacity: 0; width: 0; margin-left: 0; gap: 0; }

/* ── NAV ── */
.sidebar-body { flex: 1; overflow-y: auto; overflow-x: hidden; padding: 8px 0; }
.sidebar-body::-webkit-scrollbar { width: 6px; }
.sidebar-body::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 3px; }

.nav-item { display: flex; align-items: center; gap: 10px; padding: 10px 14px; cursor: pointer; color: var(--text-secondary); font-size: 14px; white-space: nowrap; position: relative; transition: background 0.12s; user-select: none; }
.nav-item:hover { background: var(--bg-surface); color: var(--text-primary); }
.nav-item.active { background: rgba(59, 130, 246, 0.1); color: var(--accent-primary); font-weight: 500; }
.nav-item .label { flex: 1; }
.sidebar.collapsed .nav-item .label { opacity: 0; width: 0; }
.sidebar.collapsed .nav-item { padding: 10px; justify-content: center; }
.sidebar.collapsed .nav-item.active::before { content: ''; position: absolute; left: 0; top: 6px; bottom: 6px; width: 3px; background: var(--accent-primary); border-radius: 0 3px 3px 0; }

.tooltip-tip { position: absolute; left: 60px; top: 50%; transform: translateY(-50%); background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 4px 10px; font-size: 13px; color: var(--text-primary); white-space: nowrap; pointer-events: none; opacity: 0; transition: opacity 0.12s; z-index: 300; box-shadow: var(--shadow-md); }
.sidebar.collapsed .nav-item:hover .tooltip-tip { opacity: 1; }

/* ── NIVEAU 1 : GROUP HEADER ── */
.nav-group-header { display: flex; align-items: center; gap: 10px; padding: 10px 14px; cursor: pointer; color: var(--text-secondary); font-size: 14px; white-space: nowrap; position: relative; transition: background 0.12s; user-select: none; }
.nav-group-header:hover { background: var(--bg-surface); color: var(--text-primary); }
.nav-group-header.open { color: var(--accent-primary); background: var(--bg-surface); }
.nav-group-header .label { flex: 1; }
.sidebar.collapsed .nav-group-header .label { opacity: 0; width: 0; }
.sidebar.collapsed .nav-group-header { padding: 10px; justify-content: center; }
.sidebar.collapsed .nav-group-header.open { background: rgba(59, 130, 246, 0.1); }

.chevron { width: 16px; height: 16px; stroke: currentColor; flex-shrink: 0; transition: transform 0.2s; }
.nav-group-header.open .chevron { transform: rotate(90deg); }
.sidebar.collapsed .chevron { display: none; }

/* ── NIVEAU 1 : SUBMENU ── */
.submenu { overflow: hidden; transition: max-height 0.3s cubic-bezier(.4,0,.2,1); background: rgba(0, 0, 0, 0.02); }
.sidebar.collapsed .submenu { display: none !important; }

/* ── NIVEAU 2 : SUBMENU-ITEM ── */
.submenu-item { display: flex; align-items: center; padding: 8px 14px 8px 44px; cursor: pointer; color: var(--text-secondary); font-size: 13.5px; white-space: nowrap; transition: background 0.12s; position: relative; user-select: none; }
.submenu-item:hover { background: var(--bg-surface); color: var(--text-primary); }
.submenu-item.active { color: var(--accent-primary); font-weight: 500; background: rgba(59, 130, 246, 0.05); }
.submenu-item::before { content: ''; position: absolute; left: 28px; top: 50%; width: 5px; height: 5px; border-radius: 50%; background: currentColor; transform: translateY(-50%); opacity: 0.4; }
.submenu-item.active::before { opacity: 1; }

.submenu-item.has-children::before { display: none; }
.submenu-item.has-children { gap: 6px; }
.submenu-item.has-children .sub-chevron { width: 14px; height: 14px; stroke: currentColor; flex-shrink: 0; margin-left: auto; transition: transform 0.18s; }
.submenu-item.has-children.open { color: var(--accent-primary); background: rgba(59, 130, 246, 0.03); font-weight: 500; }
.submenu-item.has-children.open .sub-chevron { transform: rotate(90deg); }

/* ── NIVEAU 3 : SUB-SUBMENU ── */
.sub-submenu { overflow: hidden; transition: max-height 0.2s cubic-bezier(.4,0,.2,1); background: rgba(0, 0, 0, 0.04); }

.sub-submenu-item { display: flex; align-items: center; padding: 7px 14px 7px 60px; cursor: pointer; color: var(--text-muted); font-size: 13px; white-space: nowrap; transition: background 0.1s; position: relative; }
.sub-submenu-item:hover { background: var(--bg-surface); color: var(--text-primary); }
.sub-submenu-item.active { color: var(--accent-primary); font-weight: 500; background: rgba(59, 130, 246, 0.08); }
.sub-submenu-item::before { content: '–'; position: absolute; left: 44px; font-size: 10px; color: currentColor; opacity: 0.5; }
.sub-submenu-item.active::before { opacity: 1; }

/* ── MINI POPUP (sidebar fermée) ── */
.mini-popup { position: fixed; background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-lg); box-shadow: var(--shadow-lg); padding: 4px 0; z-index: 9999; min-width: 200px; }
.mini-popup-title { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.08em; padding: 7px 12px 5px; border-bottom: 1px solid var(--border-color); margin-bottom: 3px; }
.mini-popup-item { display: flex; align-items: center; gap: 8px; padding: 8px 12px; cursor: pointer; color: var(--text-primary); font-size: 13px; white-space: nowrap; transition: background 0.1s; }
.mini-popup-item:hover { background: var(--bg-surface); }
.mini-popup-item.active { color: var(--accent-primary); font-weight: 500; }
.mini-popup-item::before { content: ''; width: 5px; height: 5px; border-radius: 50%; background: currentColor; opacity: 0.4; flex-shrink: 0; }
.mini-popup-item.active::before { opacity: 1; }
.mini-popup-subitem { padding-left: 22px; font-size: 12.5px; color: var(--text-secondary); }
.mini-popup-subitem:hover { background: var(--bg-surface); color: var(--accent-primary); }

/* ── FOOTER ── */
.sidebar-footer { border-top: 1px solid var(--border-color); padding: 8px 0; flex-shrink: 0; }

/* ── MAIN ── */
.topbar { background: var(--bg-secondary); border-bottom: 1px solid var(--border-color); height: 44px; display: flex; align-items: center; padding: 0 20px; flex-shrink: 0; }
.topbar-title { font-size: 15px; font-weight: 500; color: var(--text-primary); display: flex; align-items: center; gap: 6px; }
.breadcrumb-segment { display: inline-flex; align-items: center; gap: 5px; color: var(--text-muted); }
.breadcrumb-segment .icon { width: 16px; height: 16px; }
.breadcrumb-last { color: var(--text-primary); font-weight: 600; }
.breadcrumb-sep { color: var(--text-muted); font-size: 13px; opacity: 0.5; margin: 0 2px; }
.content { flex: 1; height: calc(100vh - 44px); overflow: hidden; position: relative; }

/* Empty states */
.empty-state, .empty-state-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
}
.empty-state-card {
  background: var(--bg-card);
  margin: var(--spacing-lg);
  border-radius: var(--radius-lg);
  border: 1px dashed var(--border-color);
  height: calc(100% - var(--spacing-lg) * 2);
}
.empty-illustration { font-size: 48px; margin-bottom: var(--spacing-md); }
.empty-title { font-size: 18px; font-weight: 600; color: var(--text-primary); margin-bottom: var(--spacing-xs); }
.empty-subtitle { font-size: 14px; }
.spinner { border: 3px solid rgba(0,0,0,0.1); border-top-color: var(--accent-primary); border-radius: 50%; width: 24px; height: 24px; animation: spin 1s linear infinite; margin-bottom: 12px; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
