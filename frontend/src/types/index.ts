export interface Teacher {
  id: number;
  name: string;
  school_id: number;
}

export interface Classroom {
  id: number;
  name: string;
  capacity: number;
  school_id: number;
}

export interface Division {
  id: number;
  name: string;
  school_id: number;
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
  is_pinned: boolean;
}

export interface TimetableData {
  teachers: Teacher[];
  classrooms: Classroom[];
  divisions: Division[];
  timeslots: Timeslot[];
  courses: Course[];
}
