import { TimetableData, Course } from '../types';

export async function fetchTimetable(): Promise<TimetableData> {
  const response = await fetch('/api/timetable');
  if (!response.ok) {
    throw new Error('Erreur lors de la récupération de l\'emploi du temps');
  }
  return response.json();
}

export async function fetchTimetableStatus(): Promise<{ status: string }> {
  const response = await fetch('/api/timetable/status');
  if (!response.ok) {
    throw new Error('Erreur lors de la récupération du statut');
  }
  return response.json();
}

export async function fetchTimetableScore(): Promise<{ hard_score: number; soft_score: number; summary: string; matches: Record<string, { hard: number; soft: number; count: number }> }> {
  const response = await fetch('/api/timetable/score');
  if (!response.ok) {
    throw new Error('Erreur lors de la récupération du score');
  }
  return response.json();
}

export async function solveTimetable(): Promise<{ status: string; message: string }> {
  const response = await fetch('/api/timetable/solve', {
    method: 'POST',
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Erreur lors de la résolution automatique');
  }
  return response.json();
}

export async function stopTimetable(): Promise<{ status: string; message: string }> {
  const response = await fetch('/api/timetable/stop', {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error('Erreur lors de l\'interruption du solveur');
  }
  return response.json();
}

export async function resetTimetable(): Promise<{ status: string }> {
  const response = await fetch('/api/timetable/reset', {
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
  isPinned?: boolean
): Promise<{ status: string; course: Course }> {
  const response = await fetch(`/api/timetable/courses/${courseId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      timeslot_id: timeslotId,
      is_pinned: isPinned,
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
  limit: number = 100,
  schoolId?: number
): Promise<{ total: number; items: any[] }> {
  let url = `/api/generic/${resourceName}?skip=${skip}&limit=${limit}`;
  if (schoolId !== undefined && schoolId !== null) {
    url += `&school_id=${schoolId}`;
  }
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Erreur lors du chargement de la ressource ${resourceName}`);
  }
  return response.json();
}

export async function createGenericItem(resourceName: string, payload: any): Promise<any> {
  const response = await fetch(`/api/generic/${resourceName}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Erreur de création de la ressource ${resourceName}`);
  }
  return response.json();
}

export async function updateGenericItem(resourceName: string, id: number, payload: any): Promise<any> {
  const response = await fetch(`/api/generic/${resourceName}/${id}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Erreur de mise à jour de la ressource ${resourceName}`);
  }
  return response.json();
}

export async function deleteGenericItem(resourceName: string, id: number): Promise<any> {
  const response = await fetch(`/api/generic/${resourceName}/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Erreur de suppression de la ressource ${resourceName}`);
  }
  return response.json();
}

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
  const response = await fetch('/api/timetable/structures/simulate-change', {
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
  const response = await fetch('/api/timetable/structures/apply-change', {
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
  const response = await fetch(`/api/generic/${resourceName}/${id}/call/${methodName}`, {
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



