import { useDataStore } from '../stores/data';

export function getTeacherName(teachers: any[] | undefined, id: number): string {
  const store = useDataStore();
  return store.teacherMap[id]?.display_name || 'Enseignant inconnu';
}

export function getDivisionName(divisions: any[] | undefined, id: number): string {
  const store = useDataStore();
  return store.divisionMap[id]?.display_name || 'Classe inconnue';
}

export function getClassroomName(classrooms: any[] | undefined, id: number | null): string {
  if (id === null) return 'Non affectée';
  const store = useDataStore();
  return store.classroomMap[id]?.display_name || 'Salle inconnue';
}

export function onCourseDragStart(event: DragEvent, courseId: number) {
  if (event.dataTransfer) {
    event.dataTransfer.setData('text/plain', courseId.toString());
    event.dataTransfer.effectAllowed = 'move';
  }
}

export function getNonTeachingStaffName(staffs: any[] | undefined, id: number): string {
  const store = useDataStore();
  return store.nonTeachingStaffMap[id]?.display_name || 'Personnel inconnu';
}
