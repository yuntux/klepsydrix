export interface Teacher {
  id: number;
  name: string;
  // Calculé côté backend (base.py, CRUDMixin — exposé sur tout modèle), pas stocké — présent sur
  // toute ressource générique renvoyée par l'API, voir resourceFormatters.ts.
  display_name?: string;
  school_id: number;
}

export interface NonTeachingStaff {
  id: number;
  first_name: string;
  last_name: string;
  role: string;
  display_name?: string;
  school_id: number;
}

export interface Classroom {
  id: number;
  name: string;
  capacity: number;
  display_name?: string;
  school_id: number;
}

export interface Division {
  id: number;
  name: string;
  display_name?: string;
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
  // Ids des lignes CourseClassroomRequirement du cours (voir plan salles §1.4/§1.5) — PAS des ids
  // de Classroom directement (chaque ligne peut pointer vers une salle précise OU un groupe, avec
  // une quantity). Pour la salle/le groupe réel, voir CourseClassroomRequirement / dataStore
  // courseClassroomIdsMap (course_id -> classroom_id[] résolus, pour l'affichage/filtrage grille).
  classroom_requirement_ids: number[];
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
  // classroom_requirement_ids : dict {classroom_id: quantité restante}, pas un tableau plat comme
  // les 6 autres relations (voir plan salles §1.5) — CourseClassroomRequirement.quantity oblige.
  underventilated_resource_ids?: (Record<string, number[]> & { classroom_requirement_ids?: Record<string, number> }) | null;
}

export interface CourseClassroomRequirement {
  id: number;
  course_id: number;
  classroom_id: number;
  quantity: number;
}

// Descripteur de panneau (ui.json) — partagé par SplitPanel.vue (qui le reçoit en prop) et
// NotebooksTree.vue (qui le relaie via son slot #panel jusqu'à App.vue) : une seule déclaration
// pour éviter que les deux dérivent l'une de l'autre (déjà arrivé : NotebooksTree.vue avait sa
// propre copie, jamais celle qui compte réellement pour le typage du slot #panel).
export interface Panel {
  id: string;
  component: string;
  resourceKey?: string;
  width: string;
  // "detail" : liste filtrée par la sélection du panneau maître (voir App.vue, GenericList
  // role="detail") — seule valeur observée à ce jour, gardé en string pour rester permissif comme
  // le reste de cette interface pilotée par ui.json.
  role?: string;
  placeholderText?: string;
  gridConfig?: { hideWeekSelector?: boolean; hidePeriodSelector?: boolean };
  // Voir GenericPivot.vue pour la forme exacte attendue (row/columns/matrix/...) — non dupliquée
  // ici, ce descripteur de panneau reste volontairement peu typé (piloté par ui.json).
  pivotConfig?: any;
}
