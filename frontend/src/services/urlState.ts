// Synchronisation de l'URL avec la navigation (chemin d'IDs ui.json) et l'état complet d'une
// generic list view (sélection, domaine de filtre, regroupement, tri, pagination) — voir
// architecture.md, "URLs profondes". Fonctions pures, sans dépendance Vue : App.vue les appelle
// depuis des watchers/handlers réactifs, mais la logique de lecture/écriture de l'URL elle-même ne
// dépend d'aucun état de composant.

import type { DomainNode } from '../utils/domain';

export interface UrlListState {
  ids: Array<string | number>;
  // Domaine de filtre actif (voir utils/domain.ts) — [] si aucun filtre.
  domain: DomainNode;
  // Regroupement actif (voir ListConfig.groupBy, GenericList.vue) — "field" ou "field:granularité".
  groupBy: string[];
  sort: { key: string; desc: boolean } | null;
  // null = non spécifié dans l'URL (le composant applique son défaut, 30).
  perPage: number | null;
  // null = non spécifié (défaut = page 1).
  page: number | null;
}

export function parseLocationPath(): string[] {
  return window.location.pathname.split('/').filter(segment => segment.length > 0);
}

export function parseLocationIds(): Array<string | number> {
  const raw = new URLSearchParams(window.location.search).get('id');
  if (!raw) return [];
  return raw.split(',').map(s => s.trim()).filter(s => s.length > 0);
}

function parseIntOrNull(raw: string | null): number | null {
  if (!raw) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

// État complet d'une generic list view lu depuis l'URL courante — voir GenericList.vue::
// initialListState (prop groupée, un seul flag d'accusé de réception, même idiome que
// initialSelectedIds/initial-selection-applied déjà en place pour la seule sélection).
export function parseLocationListState(): UrlListState {
  const params = new URLSearchParams(window.location.search);

  let domain: DomainNode = [];
  const rawDomain = params.get('domain');
  if (rawDomain) {
    try {
      const parsed = JSON.parse(rawDomain);
      if (Array.isArray(parsed)) domain = parsed;
    } catch {
      // URL bricolée à la main / domaine corrompu : ignoré plutôt que de faire planter le chargement.
      domain = [];
    }
  }

  const rawGroupBy = params.get('groupBy');
  const groupBy = rawGroupBy ? rawGroupBy.split(',').map(s => s.trim()).filter(s => s.length > 0) : [];

  let sort: UrlListState['sort'] = null;
  const rawSort = params.get('sort');
  if (rawSort) {
    sort = rawSort.startsWith('-') ? { key: rawSort.slice(1), desc: true } : { key: rawSort, desc: false };
  }

  return {
    ids: parseLocationIds(),
    domain,
    groupBy,
    sort,
    perPage: parseIntOrNull(params.get('perPage')),
    page: parseIntOrNull(params.get('page')),
  };
}

export function buildUrl(pathIds: string[], state: UrlListState): string {
  const path = '/' + pathIds.join('/');
  const params = new URLSearchParams();
  if (state.ids.length > 0) params.set('id', state.ids.join(','));
  if (state.domain && state.domain.length > 0) params.set('domain', JSON.stringify(state.domain));
  if (state.groupBy && state.groupBy.length > 0) params.set('groupBy', state.groupBy.join(','));
  if (state.sort) params.set('sort', (state.sort.desc ? '-' : '') + state.sort.key);
  // 30 = défaut du composant (GenericList.vue) : omis pour ne pas polluer l'URL de tout panneau
  // (y compris ceux sans GenericList, ex: la grille EDT) avec une valeur qui ne dit rien de plus
  // que "comportement par défaut" — même logique que page===1 juste en dessous.
  if (state.perPage != null && state.perPage !== 30) params.set('perPage', String(state.perPage));
  if (state.page != null && state.page !== 1) params.set('page', String(state.page));
  const query = params.toString();
  return path + (query ? `?${query}` : '');
}

// N'écrit dans l'historique que si l'URL calculée diffère de l'URL courante — évite des entrées
// d'historique/évènements popstate redondants si l'état réactif se ré-évalue sans changer.
export function syncUrl(pathIds: string[], state: UrlListState, { push }: { push: boolean }): void {
  if (!pathIds || pathIds.length === 0) return;
  const url = buildUrl(pathIds, state);
  if (url === window.location.pathname + window.location.search) return;
  if (push) {
    window.history.pushState({}, '', url);
  } else {
    window.history.replaceState({}, '', url);
  }
}
