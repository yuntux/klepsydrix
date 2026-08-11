// Synchronisation de l'URL avec la navigation (chemin d'IDs ui.json) et la sélection du panneau
// maître (?id=1,3,8) — voir architecture.md, "URLs profondes". Fonctions pures, sans dépendance
// Vue : App.vue les appelle depuis des watchers/handlers réactifs, mais la logique de lecture/
// écriture de l'URL elle-même ne dépend d'aucun état de composant.

export function parseLocationPath(): string[] {
  return window.location.pathname.split('/').filter(segment => segment.length > 0);
}

export function parseLocationIds(): Array<string | number> {
  const raw = new URLSearchParams(window.location.search).get('id');
  if (!raw) return [];
  return raw.split(',').map(s => s.trim()).filter(s => s.length > 0);
}

export function buildUrl(pathIds: string[], ids: Array<string | number>): string {
  const path = '/' + pathIds.join('/');
  const query = ids.length > 0 ? `?id=${ids.join(',')}` : '';
  return path + query;
}

// N'écrit dans l'historique que si l'URL calculée diffère de l'URL courante — évite des entrées
// d'historique/évènements popstate redondants si l'état réactif se ré-évalue sans changer.
export function syncUrl(pathIds: string[], ids: Array<string | number>, { push }: { push: boolean }): void {
  if (!pathIds || pathIds.length === 0) return;
  const url = buildUrl(pathIds, ids);
  if (url === window.location.pathname + window.location.search) return;
  if (push) {
    window.history.pushState({}, '', url);
  } else {
    window.history.replaceState({}, '', url);
  }
}
