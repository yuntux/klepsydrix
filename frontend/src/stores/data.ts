import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { Teacher, Classroom, Division, NonTeachingStaff, Timeslot, Course, CourseClassroomRequirement } from '../types';
import { getTimeslotHour } from '../composables/useTimeslotGrid';

export const useDataStore = defineStore('data', () => {
  const teachers = ref<Teacher[]>([]);
  const classrooms = ref<Classroom[]>([]);
  const divisions = ref<Division[]>([]);
  const nonTeachingStaffs = ref<NonTeachingStaff[]>([]);
  const timeslots = ref<Timeslot[]>([]);
  const courses = ref<Course[]>([]);
  const courseClassroomRequirements = ref<CourseClassroomRequirement[]>([]);

  // Dictionnaires pour un accès en O(1)
  const teacherMap = computed(() => {
    return teachers.value.reduce((map, t) => {
      map[t.id] = t;
      return map;
    }, {} as Record<number, Teacher>);
  });

  const classroomMap = computed(() => {
    return classrooms.value.reduce((map, c) => {
      map[c.id] = c;
      return map;
    }, {} as Record<number, Classroom>);
  });

  const divisionMap = computed(() => {
    return divisions.value.reduce((map, d) => {
      map[d.id] = d;
      return map;
    }, {} as Record<number, Division>);
  });

  const nonTeachingStaffMap = computed(() => {
    return nonTeachingStaffs.value.reduce((map, s) => {
      map[s.id] = s;
      return map;
    }, {} as Record<number, NonTeachingStaff>);
  });

  const timeslotMap = computed(() => {
    return timeslots.value.reduce((map, t) => {
      map[t.id] = t;
      return map;
    }, {} as Record<number, Timeslot>);
  });

  const courseMap = computed(() => {
    return courses.value.reduce((map, c) => {
      map[c.id] = c;
      return map;
    }, {} as Record<number, Course>);
  });

  // course_id -> classroom_id[] résolus (voir plan salles §1.4) — CourseClassroomRequirement.
  // classroom_id pointe soit vers une salle précise, soit vers un groupe encore non résolu ; les
  // deux sont inclus ici tels quels (pas de distinction feuille/groupe), pour l'affichage/filtrage
  // en lecture seule de la grille EDT (TimetableGrid.vue, Sidebar.vue) — remplace l'ancien
  // Course.classroom_ids (M2M directe, supprimée avec course_classrooms, voir plan salles §1.5).
  const courseClassroomIdsMap = computed(() => {
    return courseClassroomRequirements.value.reduce((map, r) => {
      (map[r.course_id] ||= []).push(r.classroom_id);
      return map;
    }, {} as Record<number, number[]>);
  });

  // Helper pour trouver un timeslot par jour/heure en O(1)
  // Clé: `day_of_week-hour`
  const timeslotByTimeMap = computed(() => {
    return timeslots.value.reduce((map, ts) => {
      const hour = Math.round(getTimeslotHour(ts) * 100) / 100;
      const key = `${ts.day_of_week}-${hour}`;
      map[key] = ts;
      return map;
    }, {} as Record<string, Timeslot>);
  });

  function getTimeslot(day: number, hour: number) {
    const key = `${day}-${Math.round(hour * 100) / 100}`;
    return timeslotByTimeMap.value[key];
  }

  function setTeachers(data: Teacher[]) { teachers.value = data; }
  function setClassrooms(data: Classroom[]) { classrooms.value = data; }
  function setDivisions(data: Division[]) { divisions.value = data; }
  function setNonTeachingStaffs(data: NonTeachingStaff[]) { nonTeachingStaffs.value = data; }
  function setTimeslots(data: Timeslot[]) { timeslots.value = data; }
  function setCourses(data: Course[]) { courses.value = data; }
  function setCourseClassroomRequirements(data: CourseClassroomRequirement[]) { courseClassroomRequirements.value = data; }

  return {
    teachers, classrooms, divisions, nonTeachingStaffs, timeslots, courses, courseClassroomRequirements,
    teacherMap, classroomMap, divisionMap, nonTeachingStaffMap, timeslotMap, courseMap, courseClassroomIdsMap,
    getTimeslot,
    setTeachers, setClassrooms, setDivisions, setNonTeachingStaffs, setTimeslots, setCourses, setCourseClassroomRequirements
  };
});
