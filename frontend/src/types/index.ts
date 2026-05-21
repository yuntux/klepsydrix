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
  teacher_ids: number[];
  division_ids: number[];
  timeslot_id: number | null;
  classroom_ids: number[];
  group_ids: number[];
  is_pinned: boolean;
  duration_minutes: number;
  week_type: 'A' | 'B' | 'W';
}

export interface TimetableData {
  teachers: Teacher[];
  classrooms: Classroom[];
  divisions: Division[];
  timeslots: Timeslot[];
  courses: Course[];
}
