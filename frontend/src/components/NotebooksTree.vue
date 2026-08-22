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
          <BaseLogo size="sm" />
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
                      <a v-for="l3 in l2.children" :key="l3.id"
                           class="sub-submenu-item"
                           :class="{ active: activeLeafId === l3.id }"
                           :href="leafHref(l3, l2, l1)" tabindex="0"
                           @click="onLeafClick($event, l3, l2, l1)" @keydown.enter="selectLeaf(l3, l2, l1)">
                        {{ l3.title }}
                      </a>
                    </div>
                  </template>
                  <!-- Level 2 as Leaf -->
                  <template v-else>
                    <a class="submenu-item" :class="{ active: activeLeafId === l2.id }" :href="leafHref(l2, l1, null)" tabindex="0" @click="onLeafClick($event, l2, l1, null)" @keydown.enter="selectLeaf(l2, l1, null)">
                      {{ l2.title }}
                    </a>
                  </template>
                </template>
              </div>
            </template>
            <!-- Level 1 as Leaf -->
            <template v-else>
              <a class="nav-item" :class="{ active: activeLeafId === l1.id }" :href="leafHref(l1, null, null)" tabindex="0" @click="onLeafClick($event, l1, null, null)" @keydown.enter="selectLeaf(l1, null, null)">
                <MenuIcon :name="l1.icon || 'calendar'" />
                <span class="label">{{ l1.title }}</span>
                <div class="tooltip-tip">{{ l1.title }}</div>
              </a>
            </template>
          </template>
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
            <a v-for="l3 in l2.children" :key="l3.id"
                 class="mini-popup-item mini-popup-subitem"
                 :class="{ active: activeLeafId === l3.id }"
                 :href="leafHref(l3, l2, activePopupNode)"
                 @click="onLeafClick($event, l3, l2, activePopupNode)">
              {{ l3.title }}
            </a>
          </template>
          <template v-else>
            <a class="mini-popup-item"
                 :class="{ active: activeLeafId === l2.id }"
                 :href="leafHref(l2, activePopupNode, null)"
                 @click="onLeafClick($event, l2, activePopupNode, null)">
              {{ l2.title }}
            </a>
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

        <!-- Actions globales (thème, base, utilisateur) — anciennement en bas de la sidebar
             (.sidebar-footer), remontées ici pour rester visibles même sidebar repliée, et
             volontairement compactes : seule une icône pour le thème, seul le nom pour
             l'utilisateur (déconnexion/mot de passe regroupés dans son menu déroulant). -->
        <div class="topbar-actions">
          <button type="button" class="topbar-icon-btn" @click="toggleTheme" title="Changer le thème">
            {{ currentThemeIndex === 1 ? '🌙' : currentThemeIndex === 2 ? '⬛' : '☀️' }}
          </button>
          <button
            type="button"
            class="topbar-db-btn"
            @click="goToDatabaseSelection"
            :title="`Changer de base de données (${currentDatabase})`"
          >
            <span class="topbar-icon">🗄️</span>
            <span class="topbar-db-label">{{ currentDatabase || 'Base inconnue' }}</span>
          </button>
          <a v-if="whoAmI?.is_admin" href="/admin" class="topbar-icon-btn topbar-admin-link" title="Console d'administration">⚙️</a>
          <div class="topbar-user-wrapper" ref="userMenuRef">
            <button type="button" class="topbar-user-btn" @click="showUserMenu = !showUserMenu">
              <span class="topbar-user-name">{{ whoAmI?.display_name || '…' }}</span>
              <svg class="topbar-user-chevron" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>
            </button>
            <div v-if="showUserMenu" class="topbar-user-menu">
              <a href="/password-change" class="topbar-user-menu-item">
                <span class="topbar-icon">🔑</span> Changer mon mot de passe
              </a>
              <button type="button" class="topbar-user-menu-item" @click="logout">
                <span class="topbar-icon">🚪</span> Se déconnecter
              </button>
            </div>
          </div>
        </div>
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
import { ref, shallowRef, onMounted, onUnmounted, watch } from 'vue';
import SplitPanel from './SplitPanel.vue';
import MenuIcon from './MenuIcon.vue';
import BaseLogo from './BaseLogo.vue';
import { fetchMenus, fetchWhoAmI, fetchGenericList } from '../services/api';
import { getSelectedDatabase, clearSelectedDatabase } from '../services/dbSession';
import type { Panel } from '../types';

interface NotebookNode {
  id: string;
  title: string;
  icon?: string;
  backgroundColor?: string;
  borderColor?: string;
  children?: NotebookNode[];
  layout?: 'VERTICAL' | 'HORIZONTAL';
  panels?: Panel[];
  // Feuille "action pure" (pas de navigation) : au lieu de devenir la feuille active et de changer
  // le contenu affiché, un clic déclenche uniquement trigger-action — le contenu déjà à l'écran
  // reste inchangé derrière la popin ouverte par cette action (voir App.vue, onTriggerAction).
  action?: { resourceKey: string; actionId: string };
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

// Nom de la base courante, affiché sous le sélecteur de thème (voir architecture.md, multi-base).
const currentDatabase = ref(getSelectedDatabase());

// Identité connectée + statut admin (voir architecture.md §19, ui_endpoints.py::whoami) — purement
// cosmétique (lien vers la console, identité sur le bouton de déconnexion) : un échec ici ne doit
// jamais bloquer le reste de l'IHM, `whoAmI` reste simplement `null` (les éléments qui en dépendent
// ne s'affichent pas, comportement identique à avant l'ajout de cet appel).
const whoAmI = ref<{ display_name: string; email: string | null; is_admin: boolean; must_change_password: boolean } | null>(null);

// Menu déroulant du bloc utilisateur (barre du haut) — déconnexion + changement de mot de passe,
// voir onDocClick pour la fermeture au clic extérieur.
const showUserMenu = ref(false);
const userMenuRef = ref<HTMLElement | null>(null);

function goToDatabaseSelection() {
  clearSelectedDatabase();
  const next = window.location.pathname + window.location.search;
  window.location.href = `/select-database?next=${encodeURIComponent(next)}`;
}

async function logout() {
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
  } finally {
    window.location.href = '/login';
  }
}

// Chemin d'IDs ui.json (racine -> feuille) à restaurer depuis l'URL — voir architecture.md, "URLs
// profondes". Surveillé en continu (pas juste lu au montage) : App.vue le remet à jour sur un
// retour navigateur (popstate), et ce composant doit alors résoudre et sélectionner la nouvelle
// cible sans être remonté.
const props = defineProps<{
  initialPath?: string[];
}>();

const emit = defineEmits<{
  (e: 'change-leaf', leaf: NotebookNode, pathIds: string[]): void;
  (e: 'trigger-action', action: { resourceKey: string; actionId: string }): void;
}>();

// Résout un chemin d'IDs (ex: ['timetable_root', 'teachers_setting', 'teachers_preferences_tab'])
// en parcourant l'arbre déjà chargé — l'arbre ne dépasse jamais 3 niveaux (voir template : l1/l2
// groupes, l3 toujours une feuille), donc pas besoin d'une résolution récursive générique.
function findNodeByPath(path: string[]): { leaf: NotebookNode; parent: NotebookNode | null; grandParent: NotebookNode | null } | null {
  if (!path || path.length === 0) return null;
  const l1 = config.value.find(n => n.id === path[0]);
  if (!l1) return null;
  if (path.length === 1) return { leaf: l1, parent: null, grandParent: null };

  const l2 = l1.children?.find(n => n.id === path[1]);
  if (!l2) return null;
  if (path.length === 2) return { leaf: l2, parent: l1, grandParent: null };

  const l3 = l2.children?.find(n => n.id === path[2]);
  if (!l3) return null;
  return { leaf: l3, parent: l2, grandParent: l1 };
}

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

// URL réelle d'une feuille (même construction que le pathIds émis par selectLeaf ci-dessous, voir
// urlState.ts::buildUrl côté App.vue pour le format complet incluant l'état de liste — ici on ne
// veut que le chemin, pas cet état transitoire) — pose un vrai `href` sur chaque entrée navigable
// du menu pour que le clic droit du navigateur propose nativement "Ouvrir le lien dans un nouvel
// onglet"/"Copier le lien". `undefined` pour une feuille "action" (wizard) : elle ne correspond à
// aucune page réelle, un clic droit dessus ne doit rien proposer de plus qu'avant.
function leafHref(leaf: NotebookNode, parent?: NotebookNode | null, grandParent?: NotebookNode | null): string | undefined {
  if (leaf.action) return undefined;
  const pathIds = [grandParent?.id, parent?.id, leaf.id].filter((id): id is string => !!id);
  return '/' + pathIds.join('/');
}

// Gestionnaire de clic sur une feuille devenue un vrai <a href> (voir leafHref) : un clic gauche
// simple continue de naviguer via l'état réactif interne (SPA, aucun rechargement de page) — seul
// un Ctrl/Cmd/Maj+clic est laissé au navigateur (ouverture native en nouvel onglet/fenêtre). Le
// clic milieu n'a besoin d'aucun traitement particulier : il déclenche `auxclick`, jamais `click`,
// donc ce gestionnaire ne s'exécute même pas pour lui — le navigateur ouvre déjà nativement le
// `href` dans un nouvel onglet.
function onLeafClick(event: MouseEvent, leaf: NotebookNode, parent?: NotebookNode | null, grandParent?: NotebookNode | null) {
  if (event.ctrlKey || event.metaKey || event.shiftKey) return;
  event.preventDefault();
  selectLeaf(leaf, parent, grandParent);
}

function selectLeaf(leaf: NotebookNode, parent?: NotebookNode | null, grandParent?: NotebookNode | null) {
  if (leaf.action) {
    // Ne touche ni activeLeafId ni activeLeafNode : le contenu déjà affiché reste tel quel
    // derrière la popin que ce déclenchement va ouvrir (voir App.vue, onTriggerAction).
    activePopupNode.value = null;
    emit('trigger-action', leaf.action);
    return;
  }

  // Replie toutes les branches de PREMIER NIVEAU (l1) qui ne sont pas celle de la feuille cliquée —
  // sans jamais toucher aux ids de niveau 2 (openGroupIds est un Set PARTAGÉ entre les deux niveaux,
  // voir toggleGroup/toggleSubGroup) : l'état "ouvert" qu'un utilisateur a déjà construit à
  // l'intérieur d'une branche, même une autre que celle-ci, reste intact et réapparaît tel quel s'il
  // y revient plus tard — seule la visibilité de la branche elle-même change, pas ce qu'elle
  // contient.
  const activeL1Id = grandParent?.id ?? parent?.id ?? leaf.id;
  const l1Ids = new Set(config.value.map(n => n.id));
  for (const id of openGroupIds.value) {
    if (l1Ids.has(id) && id !== activeL1Id) {
      openGroupIds.value.delete(id);
    }
  }

  activeLeafId.value = leaf.id;
  activeLeafNode.value = leaf;

  const parts: { title: string; icon?: string }[] = [];
  if (grandParent) parts.push({ title: grandParent.title, icon: grandParent.icon });
  if (parent) parts.push({ title: parent.title, icon: parent.icon });
  parts.push({ title: leaf.title, icon: leaf.icon });
  breadcrumbParts.value = parts;

  activePopupNode.value = null;
  // Chemin racine -> feuille, dans cet ordre quel que soit le niveau de profondeur de la feuille
  // (grandParent est toujours l'ancêtre le plus haut quand il existe — voir findNodeByPath) :
  // App.vue s'en sert pour synchroniser l'URL (voir architecture.md, "URLs profondes").
  const pathIds = [grandParent?.id, parent?.id, leaf.id].filter((id): id is string => !!id);
  emit('change-leaf', leaf, pathIds);
}

// Recherche en profondeur d'une feuille "action" par resourceKey — utilisé uniquement pour
// l'auto-lancement du wizard de grille horaire ci-dessous (voir onMounted). L'arbre reçu de
// fetchMenus() est déjà filtré par droits côté backend (filter_menu_for_user, ui_endpoints.py) :
// un nœud "action" n'y survit que si l'utilisateur a le droit d'ÉCRITURE sur son resourceKey —
// donc le trouver ici suffit à prouver ce droit, sans second appel réseau dédié.
function findActionNode(nodes: NotebookNode[], resourceKey: string): NotebookNode | null {
  for (const node of nodes) {
    if (node.action?.resourceKey === resourceKey) return node;
    if (node.children) {
      const found = findActionNode(node.children, resourceKey);
      if (found) return found;
    }
  }
  return null;
}

// Auto-lancement du wizard de paramétrage de grille horaire (voir wizard_grid_settings.py) tant
// qu'aucun Timeslot n'existe — best-effort, ne bloque jamais le montage normal du menu si le
// contrôle échoue (ex: ressource "timeslots" inaccessible en lecture pour une autre raison).
async function maybeAutoLaunchGridWizard() {
  const actionNode = findActionNode(config.value, 'wizard_grid_settings');
  if (!actionNode?.action) return;
  try {
    const { total } = await fetchGenericList('timeslots', 0, 1);
    if (total === 0) {
      emit('trigger-action', actionNode.action);
    }
  } catch {
    // Best-effort : pas de wizard forcé si la vérification elle-même échoue.
  }
}

function onDocClick(e: Event) {
  const target = e.target as HTMLElement;
  if (!target.closest('.mini-popup') && !target.closest('.nav-group-header')) {
    activePopupNode.value = null;
  }
  if (!target.closest('.topbar-user-wrapper')) {
    showUserMenu.value = false;
  }
}

onMounted(async () => {
  document.addEventListener('click', onDocClick);
  fetchWhoAmI().then(r => {
    whoAmI.value = r;
    // Défense en profondeur côté client (le serveur bloque déjà toute autre route, voir
    // database.py::current_db_user) : redirige avant même que l'utilisateur ait l'occasion
    // d'interagir avec le reste de l'appli, plutôt que d'attendre l'échec 403 du premier appel API
    // qu'il déclencherait lui-même.
    if (r.must_change_password) {
      const next = window.location.pathname + window.location.search;
      window.location.href = `/password-change?forced=1&next=${encodeURIComponent(next)}`;
    }
  }).catch(() => {});
  try {
    const data = await fetchMenus();
    config.value = data as NotebookNode[];
    if (config.value.length > 0) {
      // Restauration depuis l'URL (voir architecture.md, "URLs profondes") si un chemin valide
      // est fourni ; repli sur le comportement historique (première feuille de l'arbre) sinon —
      // aucune régression pour un premier chargement sans URL de navigation.
      const restored = props.initialPath && props.initialPath.length > 0 ? findNodeByPath(props.initialPath) : null;
      if (restored) {
        if (restored.grandParent) openGroupIds.value.add(restored.grandParent.id);
        if (restored.parent) openGroupIds.value.add(restored.parent.id);
        selectLeaf(restored.leaf, restored.parent, restored.grandParent);
      } else {
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
    }
    maybeAutoLaunchGridWizard();
  } catch (e) {
    console.error("Failed to load menus from backend:", e);
  }
});

// Retour navigateur (popstate) : App.vue remet à jour initialPath, qu'il faut alors résoudre et
// appliquer sans attendre un nouveau montage du composant (le montage n'a lieu qu'une fois).
watch(() => props.initialPath, (newPath) => {
  if (!newPath || newPath.length === 0 || config.value.length === 0) return;
  const resolved = findNodeByPath(newPath);
  if (resolved) {
    if (resolved.grandParent) openGroupIds.value.add(resolved.grandParent.id);
    if (resolved.parent) openGroupIds.value.add(resolved.parent.id);
    selectLeaf(resolved.leaf, resolved.parent, resolved.grandParent);
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
.sidebar-header :deep(.base-logo-text) { opacity: 1; transition: opacity 0.15s; }
.sidebar.collapsed :deep(.base-logo-text) { opacity: 0; width: 0; }

/* ── NAV ── */
.sidebar-body { flex: 1; overflow-y: auto; overflow-x: hidden; padding: 8px 0; }
.sidebar-body::-webkit-scrollbar { width: 6px; }
.sidebar-body::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 3px; }

/* .nav-item, .submenu-item, .sub-submenu-item et .mini-popup-item sont maintenant de vrais <a href>
   (voir leafHref/onLeafClick, script) — sans cette ligne, ils hériteraient du soulignement/couleur
   par défaut du navigateur pour un lien, jamais nécessaire ici puisque la couleur est déjà pilotée
   explicitement par ces mêmes règles. */
.nav-item { display: flex; align-items: center; gap: 10px; padding: 10px 14px; cursor: pointer; color: var(--text-secondary); font-size: 14px; white-space: nowrap; position: relative; transition: background 0.12s; user-select: none; text-decoration: none; }
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
.submenu-item { display: flex; align-items: center; padding: 8px 14px 8px 44px; cursor: pointer; color: var(--text-secondary); font-size: 13.5px; white-space: nowrap; transition: background 0.12s; position: relative; user-select: none; text-decoration: none; }
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

.sub-submenu-item { display: flex; align-items: center; padding: 7px 14px 7px 60px; cursor: pointer; color: var(--text-muted); font-size: 13px; white-space: nowrap; transition: background 0.1s; position: relative; text-decoration: none; }
.sub-submenu-item:hover { background: var(--bg-surface); color: var(--text-primary); }
.sub-submenu-item.active { color: var(--accent-primary); font-weight: 500; background: rgba(59, 130, 246, 0.08); }
.sub-submenu-item::before { content: '–'; position: absolute; left: 44px; font-size: 10px; color: currentColor; opacity: 0.5; }
.sub-submenu-item.active::before { opacity: 1; }

/* ── MINI POPUP (sidebar fermée) ── */
.mini-popup { position: fixed; background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-lg); box-shadow: var(--shadow-lg); padding: 4px 0; z-index: 9999; min-width: 200px; }
.mini-popup-title { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.08em; padding: 7px 12px 5px; border-bottom: 1px solid var(--border-color); margin-bottom: 3px; }
.mini-popup-item { display: flex; align-items: center; gap: 8px; padding: 8px 12px; cursor: pointer; color: var(--text-primary); font-size: 13px; white-space: nowrap; transition: background 0.1s; text-decoration: none; }
.mini-popup-item:hover { background: var(--bg-surface); }
.mini-popup-item.active { color: var(--accent-primary); font-weight: 500; }
.mini-popup-item::before { content: ''; width: 5px; height: 5px; border-radius: 50%; background: currentColor; opacity: 0.4; flex-shrink: 0; }
.mini-popup-item.active::before { opacity: 1; }
.mini-popup-subitem { padding-left: 22px; font-size: 12.5px; color: var(--text-secondary); }
.mini-popup-subitem:hover { background: var(--bg-surface); color: var(--accent-primary); }

/* ── MAIN ── */
.topbar { background: var(--bg-secondary); border-bottom: 1px solid var(--border-color); height: 44px; display: flex; align-items: center; justify-content: space-between; padding: 0 20px; flex-shrink: 0; }
.topbar-title { font-size: 15px; font-weight: 500; color: var(--text-primary); display: flex; align-items: center; gap: 6px; }
.breadcrumb-segment { display: inline-flex; align-items: center; gap: 5px; color: var(--text-muted); }

/* ── ACTIONS GLOBALES (barre du haut) — thème, base de données, utilisateur ── */
.topbar-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.topbar-icon { display: flex; align-items: center; justify-content: center; font-size: 13px; flex-shrink: 0; }

.topbar-icon-btn {
  display: flex; align-items: center; justify-content: center;
  width: 30px; height: 30px;
  background: transparent; border: 1px solid transparent; border-radius: var(--radius-md);
  color: var(--text-secondary); font-size: 14px; cursor: pointer;
  text-decoration: none;
  transition: background 0.12s, border-color 0.12s;
}
.topbar-icon-btn:hover { background: var(--bg-surface); border-color: var(--border-color); }

.topbar-db-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 0 10px; height: 30px;
  background: transparent; border: 1px solid transparent; border-radius: var(--radius-md);
  color: var(--text-secondary); font-size: 12.5px; font-weight: 500; cursor: pointer;
  white-space: nowrap; max-width: 160px;
  transition: background 0.12s, border-color 0.12s;
}
.topbar-db-btn:hover { background: var(--bg-surface); border-color: var(--border-color); }
.topbar-db-label { overflow: hidden; text-overflow: ellipsis; }

.topbar-user-wrapper { position: relative; }
.topbar-user-btn {
  display: flex; align-items: center; gap: 4px;
  padding: 0 10px; height: 30px;
  background: transparent; border: 1px solid var(--border-color); border-radius: var(--radius-full);
  color: var(--text-primary); font-size: 12.5px; font-weight: 600; cursor: pointer;
  white-space: nowrap; max-width: 160px;
  transition: background 0.12s;
}
.topbar-user-btn:hover { background: var(--bg-surface); }
.topbar-user-name { overflow: hidden; text-overflow: ellipsis; }
.topbar-user-chevron { width: 12px; height: 12px; stroke: currentColor; flex-shrink: 0; opacity: 0.6; }

.topbar-user-menu {
  position: absolute; top: calc(100% + 6px); right: 0;
  min-width: 210px;
  background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg); z-index: 300; padding: 4px; display: flex; flex-direction: column; gap: 2px;
}
.topbar-user-menu-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; border: none; background: transparent; border-radius: var(--radius-sm);
  color: var(--text-primary); font-size: 13px; text-align: left; text-decoration: none; cursor: pointer;
  width: 100%;
}
.topbar-user-menu-item:hover { background: var(--bg-surface); }
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
