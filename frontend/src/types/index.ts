export interface Teacher {
  id: number;
  name: string;
}

export interface Classroom {
  id: number;
  name: string;
  capacity: number;
}

export interface Division {
  id: number;
  name: string;
}

export interface Timeslot {
  id: number;
  day_of_week: number; // 1 = Lundi, 6 = Samedi
  hour: number;        // 8 to 17
}

export interface Course {
  id: number;
  subject: string;
  teacher_id: number;
  division_id: number;
  timeslot_id: number | null;
  classroom_id: number | null;
}

export interface TimetableData {
  teachers: Teacher[];
  classrooms: Classroom[];
  divisions: Division[];
  timeslots: Timeslot[];
  courses: Course[];
}
