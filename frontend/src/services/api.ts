import { Course } from '../types';
import { getSelectedDatabase, clearSelectedDatabase } from './dbSession';

// ==========================================
// JETON D'ÉCRITURE (voir architecture.md, "mode exclusif") — apiFetch()
// ==========================================
// Toute requête passe par ce wrapper plutôt qu'un fetch() direct : il attache le dernier jeton
// d'écriture connu (X-Write-Token, voir core/database.py::check_write_token côté backend) sur
// CHAQUE requête, lecture ou écriture, et surveille le même en-tête sur CHAQUE réponse. Le backend
// l'annonce systématiquement : dès qu'il diffère de ce qu'on connaissait, nos données locales
// sont potentiellement périmées (ex: une résolution automatique vient de se terminer et a déplacé
// des cours) — un CustomEvent 'write-token:stale' est alors émis (même pattern que
// 'resource:mutated'), écouté une seule fois côté App.vue pour déclencher la réaction adaptée :
// rechargement silencieux pour une simple lecture périmée, notification explicite si c'est une
// écriture qui vient d'être activement rejetée (409, voir plus bas).
const WRITE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
let currentWriteToken: string | null = null;

export function getWriteToken(): string | null {
  return currentWriteToken;
}

// ==========================================
// BASE COURANTE (voir architecture.md, multi-base) — même wrapper apiFetch()
// ==========================================
// Extension directe du mécanisme ci-dessus, pas un nouveau pattern : l'en-tête
// X-Klepsydrix-Database est posé depuis le cookie sur CHAQUE requête, et l'écho de cet en-tête en
// réponse est comparé à ce qui a été envoyé. Deux anomalies distinctes, deux réactions distinctes :
// - Le backend rejette explicitement la base (428/404, code DATABASE_REQUIRED/DATABASE_UNKNOWN) :
//   le cookie est invalide/périmé, on redirige vers le sélecteur de base plutôt que de laisser
//   l'utilisateur face à des erreurs en boucle sur chaque appel API.
// - L'en-tête écho ne correspond pas à ce qui a été envoyé (course-condition, ex: un autre onglet
//   a changé la base entretemps) : rechargement forcé, pas de tentative de réconciliation côté JS.
function redirectToDatabaseSelection() {
  clearSelectedDatabase();
  const next = window.location.pathname + window.location.search;
  window.location.href = `/select-database?next=${encodeURIComponent(next)}`;
}

// Session instance absente/expirée (voir core/instance_session.py) : redirige vers /login, en
// portant la base déjà sélectionnée (?db=, pré-remplit le formulaire du provider local — voir
// pages/Login.vue) et la page de provenance (?next=) pour y revenir une fois connecté. `reason`
// optionnel (ex: "inactive") : affiché comme message explicite sur la page de connexion.
function redirectToLogin(reason?: string) {
  const next = window.location.pathname + window.location.search;
  const db = getSelectedDatabase();
  const params = new URLSearchParams({ next });
  if (db) params.set('db', db);
  if (reason) params.set('reason', reason);
  window.location.href = `/login?${params.toString()}`;
}

// PASSWORD_CHANGE_REQUIRED (voir database.py::current_db_user, UserIdentityProvider.
// must_change_password) : la session reste valide, seule une action est requise avant de continuer
// — contrairement à redirectToLogin(), on ne repart pas de zéro, `next` permet de revenir
// exactement là où l'utilisateur en était une fois le mot de passe changé (voir PasswordChange.vue).
function redirectToPasswordChange() {
  const next = window.location.pathname + window.location.search;
  window.location.href = `/password-change?forced=1&next=${encodeURIComponent(next)}`;
}

async function errorCode(response: Response): Promise<string | undefined> {
  try {
    const data = await response.clone().json();
    return typeof data?.detail === 'object' ? data.detail?.code : undefined;
  } catch {
    return undefined; // Corps non-JSON ou vide.
  }
}

export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  if (currentWriteToken) {
    headers.set('X-Write-Token', currentWriteToken);
  }
  const selectedDb = getSelectedDatabase();
  if (selectedDb) {
    headers.set('X-Klepsydrix-Database', selectedDb);
  }
  const response = await fetch(input, { ...init, headers });

  if (response.status === 401 && (await errorCode(response)) === 'NOT_AUTHENTICATED') {
    redirectToLogin();
    return response;
  }

  // Session instance valide mais issue du mot de passe maître (voir database.py::current_db_user) :
  // cette identité ne correspond à aucun vrai compte dans aucune base — jamais une impasse
  // silencieuse, retour à /login pour s'authentifier avec une vraie identité.
  if (response.status === 403 && (await errorCode(response)) === 'MASTER_IDENTITY_FORBIDDEN') {
    redirectToLogin();
    return response;
  }

  // Compte désactivé (voir database.py::current_db_user, User.active) — local ou OIDC, ce point
  // est le seul traversé par les deux. Retour à /login avec un motif explicite (voir Login.vue).
  if (response.status === 403 && (await errorCode(response)) === 'USER_INACTIVE') {
    redirectToLogin('inactive');
    return response;
  }

  // Changement de mot de passe forcé (voir database.py::current_db_user,
  // UserIdentityProvider.must_change_password) — défense en profondeur : NotebooksTree.vue
  // redirige déjà au chargement de whoami, ceci couvre le cas où le flag est posé PENDANT une
  // session déjà ouverte (le prochain appel API, quel qu'il soit, se charge de rediriger).
  if (response.status === 403 && (await errorCode(response)) === 'PASSWORD_CHANGE_REQUIRED') {
    redirectToPasswordChange();
    return response;
  }

  if (selectedDb && (response.status === 428 || response.status === 404)) {
    const code = await errorCode(response);
    if (code === 'DATABASE_REQUIRED' || code === 'DATABASE_UNKNOWN') {
      redirectToDatabaseSelection();
      return response;
    }
  }

  const echoedDb = response.headers.get('X-Klepsydrix-Database');
  if (selectedDb && echoedDb && echoedDb !== selectedDb) {
    window.dispatchEvent(new CustomEvent('database:mismatch', { detail: { expected: selectedDb, echoed: echoedDb } }));
    window.location.reload();
    return response;
  }

  const serverToken = response.headers.get('X-Write-Token');
  if (serverToken && serverToken !== currentWriteToken) {
    const wasKnown = currentWriteToken !== null;
    currentWriteToken = serverToken;
    if (wasKnown) {
      const method = (init.method || 'GET').toUpperCase();
      window.dispatchEvent(new CustomEvent('write-token:stale', {
        detail: { wasWriteAttempt: WRITE_METHODS.has(method) && response.status === 409 },
      }));
    }
  }
  return response;
}

// ==========================================
// CLIENTS D'API TIMETABLE
// ==========================================

export async function fetchMenus(): Promise<any> {
  const response = await apiFetch('/api/ui/menus');
  if (!response.ok) {
    throw new Error('Erreur lors de la récupération des menus');
  }
  return response.json();
}

// Identité de l'utilisateur connecté sur la base courante + statut admin (super-admin d'instance OU
// membre du groupe "Admin" DANS cette base) — voir architecture.md §19, ui_endpoints.py::whoami.
export async function fetchWhoAmI(): Promise<{ display_name: string; email: string | null; is_admin: boolean; must_change_password: boolean }> {
  const response = await apiFetch('/api/ui/whoami');
  if (!response.ok) {
    throw new Error("Erreur lors de la récupération de l'identité connectée");
  }
  return response.json();
}

// progress/elapsed_seconds/time_limit_seconds : null tant qu'aucune résolution n'est en cours (ou
// pas encore de score connu pour `progress` — voir solver.py::_on_best_solution_changed, le
// listener Timefold ne se déclenche pas de façon garantie, à traiter comme "pas encore de
// donnée", jamais comme une erreur). status peut valoir NOT_SOLVING/QUEUED/SOLVING (voir
// solver.py::SolverState, "Concurrence des résolutions") — queue_position/queue_length ne sont
// significatifs que pour QUEUED (null/0 sinon).
// kind : COURSE_PLACEMENT/CLASSROOM_ASSIGNMENT/OPTIMIZE_COURSE_PLACEMENT/
// OPTIMIZE_CLASSROOM_ASSIGNMENT/null (voir plan salles §4, solver.py::SolverState) — null hors
// résolution, ou pour une résolution legacy (POST /solve, jamais taguée). pipeline_step/
// pipeline_total_steps : 1/1 pour un solve simple, 1 ou 2 sur 2 pour le pipeline /optimize.
export async function fetchTimetableStatus(): Promise<{
  status: string;
  progress: { hard_score: number; soft_score: number } | null;
  elapsed_seconds: number | null;
  time_limit_seconds: number | null;
  queue_position: number | null;
  queue_length: number;
  kind: string | null;
  pipeline_step: number;
  pipeline_total_steps: number;
}> {
  const response = await apiFetch('/api/timetable/status');
  if (!response.ok) {
    throw new Error('Erreur lors de la récupération du statut');
  }
  return response.json();
}

export async function fetchTimetableScore(): Promise<{ hard_score: number; soft_score: number; summary: string; matches: Record<string, { hard: number; soft: number; count: number }> }> {
  const response = await apiFetch('/api/timetable/score');
  if (!response.ok) {
    throw new Error('Erreur lors de la récupération du score');
  }
  return response.json();
}

// Endpoint 2 (plan salles §4) — remplace le legacy /solve (retiré) : ne résout plus que
// timeslot/week_type (domaine COURSE_PLACEMENT), s'arrête dès la 1ère solution faisable.
export async function startCoursePlacement(): Promise<{ status: string; message: string }> {
  const response = await apiFetch('/api/timetable/course-placement', {
    method: 'POST',
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Erreur lors du placement automatique');
  }
  return response.json();
}

// Endpoint 3 (plan salles §4) — « Attribuer les salles » : résout la salle précise (domaine
// CLASSROOM_ASSIGNMENT) sur tous les cours porteurs d'une exigence de groupe.
export async function startClassroomAssignment(): Promise<{ status: string; message: string }> {
  const response = await apiFetch('/api/timetable/classroom-assignment', {
    method: 'POST',
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || "Erreur lors de l'attribution des salles");
  }
  return response.json();
}

export async function stopTimetable(): Promise<{ status: string; message: string }> {
  const response = await apiFetch('/api/timetable/stop', {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error('Erreur lors de l\'interruption du solveur');
  }
  return response.json();
}

export async function resetTimetable(): Promise<{ status: string }> {
  const response = await apiFetch('/api/timetable/reset', {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error('Erreur lors de la réinitialisation de l\'emploi du temps');
  }
  return response.json();
}

export async function updateCourse(
  courseId: number,
  timeslotId: number | null,
  isPinned?: boolean,
  weekType?: 'A' | 'B'
): Promise<{ status: string; courses: Course[] }> {
  const response = await apiFetch(`/api/timetable/courses/${courseId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      timeslot_id: timeslotId,
      is_pinned: isPinned,
      week_type: weekType,
    }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Conflit de planification détecté');
  }
  return response.json();
}

// ==========================================
// CLIENTS D'API CRUD GÉNÉRIQUES V2
// ==========================================

export async function fetchGenericList(
  resourceName: string,
  skip: number = 0,
  limit: number = 1000,
  schoolId?: number,
  filters?: Record<string, any>
): Promise<{ total: number; items: any[] }> {
  let url = `/api/generic/${resourceName}?skip=${skip}&limit=${limit}`;
  if (schoolId !== undefined && schoolId !== null) {
    url += `&school_id=${schoolId}`;
  }
  if (filters) {
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null) {
        // Une valeur non scalaire (tableau/objet — ex: le mapping du wizard de composition de
        // cours) doit être sérialisée en JSON avant l'URL-encodage : String([...]) produirait
        // "[object Object]", illisible côté serveur (voir generic.py, domain[key] reçoit alors la
        // chaîne brute et la parse lui-même avec json.loads). Une valeur déjà string traverse
        // inchangée pour ne rien changer au comportement existant (filtres scalaires classiques,
        // ex: address_city_id/zip_code).
        const raw = typeof value === 'string' ? value : JSON.stringify(value);
        url += `&${encodeURIComponent(key)}=${encodeURIComponent(raw)}`;
      }
    }
  }
  const response = await apiFetch(url);
  if (!response.ok) {
    throw new Error(`Erreur lors du chargement de la ressource ${resourceName}`);
  }
  return response.json();
}

// Récupère TOUS les enregistrements d'une ressource, en paginant par appels successifs de
// fetchGenericList plutôt qu'un unique appel avec une limite arbitraire (1000, 2000, 5000...)
// codée en dur à chaque site d'appel — ce plafond tronquait silencieusement toute ressource qui
// le dépasserait un jour (aucune erreur, aucun avertissement, juste des lignes manquantes). Ne
// fait PAS de pagination serveur réelle (voir le mode `lazy` d'une bibliothèque de type
// DataTable pour ça, hors périmètre ici) : charge tout en mémoire, comme le faisaient déjà tous
// les appelants existants, juste sans plafond arbitraire et de façon homogène.
export async function fetchAllGenericItems(
  resourceName: string,
  schoolId?: number,
  filters?: Record<string, any>
): Promise<{ total: number; items: any[] }> {
  const pageSize = 500;
  let skip = 0;
  let items: any[] = [];
  let total = Infinity;
  while (skip < total) {
    const res = await fetchGenericList(resourceName, skip, pageSize, schoolId, filters);
    items = items.concat(res.items);
    total = res.total;
    skip += pageSize;
    if (res.items.length === 0) break; // Garde-fou anti-boucle infinie si total est incohérent.
  }
  return { total, items };
}

export async function createGenericItem(resourceName: string, payload: any): Promise<any> {
  const response = await apiFetch(`/api/generic/${resourceName}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    let msg = `Erreur de création de la ressource ${resourceName}`;
    if (errorData.detail) {
      if (Array.isArray(errorData.detail)) {
        msg = errorData.detail.map((e: any) => `${e.loc?.join('.')} : ${e.msg}`).join('\n');
      } else {
        msg = errorData.detail;
      }
    }
    throw new Error(msg);
  }
  return response.json();
}

// Valeurs par défaut d'un nouvel enregistrement, dépendantes d'un contexte (ex: la sélection
// courante d'un panneau maître) — pendant de default_get() côté Odoo. À appeler depuis TOUT point
// d'entrée qui crée un nouvel objet (pas seulement un écran maître/détail précis), pour que
// n'importe quel modèle bénéficie automatiquement de son propre default_get() backend sans que le
// frontend ait à connaître sa logique.
export async function fetchDefaults(resourceName: string, context: Record<string, any> = {}): Promise<any> {
  const response = await apiFetch(`/api/generic/${resourceName}/defaults`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ context }),
  });
  if (!response.ok) {
    return {};
  }
  return response.json();
}

export async function updateGenericItem(resourceName: string, id: number, payload: any): Promise<any> {
  const response = await apiFetch(`/api/generic/${resourceName}/${id}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    let msg = `Erreur de mise à jour de la ressource ${resourceName}`;
    if (errorData.detail) {
      if (Array.isArray(errorData.detail)) {
        msg = errorData.detail.map((e: any) => `${e.loc?.join('.')} : ${e.msg}`).join('\n');
      } else {
        msg = errorData.detail;
      }
    }
    throw new Error(msg);
  }
  return response.json();
}

export async function deleteGenericItem(resourceName: string, id: number): Promise<any> {
  const response = await apiFetch(`/api/generic/${resourceName}/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    let msg = `Erreur de suppression de la ressource ${resourceName}`;
    if (errorData.detail) {
      if (Array.isArray(errorData.detail)) {
        msg = errorData.detail.map((e: any) => `${e.loc?.join('.')} : ${e.msg}`).join('\n');
      } else {
        msg = errorData.detail;
      }
    }
    throw new Error(msg);
  }
  return response.json();
}

// ==========================================
// CLIENTS D'API STRUCTURES
// ==========================================

export async function simulateChange(action: string, resourceType: string, resourceId: number, payload: any = {}): Promise<{
  can_proceed: boolean;
  impacted_sessions_count: number;
  impacted_sessions: Array<{
    session_id: number;
    course_label: string;
    timeslot: string;
    reason: string;
  }>;
}> {
  const response = await apiFetch('/api/timetable/structures/simulate-change', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ action, resource_type: resourceType, resource_id: resourceId, payload }),
  });
  if (!response.ok) {
    throw new Error('Erreur lors de la simulation de changement de structure');
  }
  return response.json();
}

export async function applyChange(action: string, resourceType: string, resourceId: number, payload: any = {}): Promise<{
  success: boolean;
  deplaced_sessions_count: number;
  diagnostic_history_id: number;
}> {
  const response = await apiFetch('/api/timetable/structures/apply-change', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ action, resource_type: resourceType, resource_id: resourceId, payload }),
  });
  if (!response.ok) {
    throw new Error('Erreur lors de l\'application de changement de structure');
  }
  return response.json();
}

export async function callInstanceMethod(
  resourceName: string,
  id: number,
  methodName: string,
  payload: { args?: any[]; kwargs?: Record<string, any> } = {}
): Promise<any> {
  const response = await apiFetch(`/api/generic/${resourceName}/${id}/call/${methodName}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Erreur d'appel de méthode ${methodName} sur la ressource ${resourceName}`);
  }
  return response.json();
}

export async function callClassMethod(
  resourceName: string,
  methodName: string,
  payload: { args?: any[]; kwargs?: Record<string, any> } = {}
): Promise<any> {
  const response = await apiFetch(`/api/generic/${resourceName}/call/${methodName}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Erreur d'appel de méthode ${methodName} sur la ressource ${resourceName}`);
  }
  return response.json();
}

export async function fetchGenericActions(resourceName: string): Promise<any[]> {
  const response = await apiFetch(`/api/generic/${resourceName}/actions`);
  if (!response.ok) {
    throw new Error(`Erreur de chargement des actions pour ${resourceName}`);
  }
  return response.json();
}

// ==========================================
// IMPRESSION PDF (voir architecture.md §22, backend/app/reports/)
// ==========================================
// Téléchargement via apiFetch() + blob, et NON par window.open()/<a href> comme le fait Odoo avec
// sa route /report/download : une navigation directe du navigateur ne porte pas l'en-tête
// X-Klepsydrix-Database, que resolve_database exige (428 sinon — voir core/database.py). Ce
// détour a l'avantage de garder l'impression sur le chemin unique d'apiFetch, donc de continuer à
// bénéficier du suivi du jeton d'écriture et des redirections d'authentification.
export async function downloadReport(
  reportName: string,
  ids: number[] = [],
  params: Record<string, string> = {},
): Promise<void> {
  const query = new URLSearchParams({ ...params });
  if (ids.length) query.set('ids', ids.join(','));

  const response = await apiFetch(`/api/report/${reportName}?${query}`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || "Erreur lors de la génération du document.");
  }

  // Nom de fichier calculé côté serveur (équivalent de print_report_name chez Odoo), jamais
  // reconstruit ici — sinon deux sources de vérité pour le même nom.
  const disposition = response.headers.get('Content-Disposition') || '';
  const filename = /filename="?([^";]+)"?/.exec(disposition)?.[1] || `${reportName}.pdf`;

  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
