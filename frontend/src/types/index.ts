export interface Teacher {
  id: number;
  name: string;
  school_id: number;
}

export interface NonTeachingStaff {
  id: number;
  first_name: string;
  last_name: string;
  role: string;
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
  day_of_week: number;
  day_of_week_str?: string;
  minutes_from_midnight: number;
}

export interface Group {
  id: number;
  display_name: string;
  school_id?: number;
}

export interface ClassPart {
  id: number;
  display_name: string;
}

export interface Material {
  id: number;
  name: string;
  display_name?: string;
}

export interface Period {
  id: number;
  code: string;
  name: string;
  period_type_id: number;
}

export interface Course {
  id: number;
  subject_id?: number | null;
  teacher_ids: number[];
  non_teaching_staff_ids: number[];
  division_ids: number[];
  timeslot_id: number | null;
  classroom_ids: number[];
  group_ids: number[];
  class_part_ids?: number[];
  material_ids?: number[];
  period_ids?: number[];
  period_type_id?: number | null;
  is_pinned: boolean;
  duration_minutes: number;
  week_type: 'A' | 'B' | 'W' | 'Q';
  parent_id?: number | null;
  is_composed?: boolean;
  children_ids?: number[];
  decomposition_status?: string | null;
  underventilated_resource_ids?: Record<string, number[]> | null;
}
