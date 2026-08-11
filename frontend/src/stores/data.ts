import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { Teacher, Classroom, Division, NonTeachingStaff, Timeslot, Course } from '../types';
import { getTimeslotHour } from '../composables/useTimeslotGrid';

export const useDataStore = defineStore('data', () => {
  const teachers = ref<Teacher[]>([]);
  const classrooms = ref<Classroom[]>([]);
  const divisions = ref<Division[]>([]);
  const nonTeachingStaffs = ref<NonTeachingStaff[]>([]);
  const timeslots = ref<Timeslot[]>([]);
  const courses = ref<Course[]>([]);

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

  return {
    teachers, classrooms, divisions, nonTeachingStaffs, timeslots, courses,
    teacherMap, classroomMap, divisionMap, nonTeachingStaffMap, timeslotMap, courseMap,
    getTimeslot,
    setTeachers, setClassrooms, setDivisions, setNonTeachingStaffs, setTimeslots, setCourses
  };
});
