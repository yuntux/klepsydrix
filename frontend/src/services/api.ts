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

export async function fetchTimetableScore(): Promise<{ hard_score: number; soft_score: number; summary: string }> {
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
  classroomId: number | null,
  isPinned?: boolean
): Promise<{ status: string; course: Course }> {
  const response = await fetch(`/api/timetable/courses/${courseId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      timeslot_id: timeslotId,
      classroom_id: classroomId,
      is_pinned: isPinned,
    }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Conflit de planification détecté');
  }
  return response.json();
}
