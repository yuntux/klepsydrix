import { Teacher, Division, Classroom } from '../types';

export function getTeacherName(teachers: Teacher[] | undefined, id: number): string {
  if (!teachers) return 'Enseignant inconnu';
  return teachers.find(t => t.id === id)?.display_name || 'Enseignant inconnu';
}

export function getDivisionName(divisions: Division[] | undefined, id: number): string {
  if (!divisions) return 'Classe inconnue';
  return divisions.find(d => d.id === id)?.display_name || 'Classe inconnue';
}

export function getClassroomName(classrooms: Classroom[] | undefined, id: number | null): string {
  if (id === null) return 'Non affectée';
  if (!classrooms) return 'Salle inconnue';
  return classrooms.find(c => c.id === id)?.display_name || 'Salle inconnue';
}

export function onCourseDragStart(event: DragEvent, courseId: number) {
  if (event.dataTransfer) {
    event.dataTransfer.setData('text/plain', courseId.toString());
    event.dataTransfer.effectAllowed = 'move';
  }
}
