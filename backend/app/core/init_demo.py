import argparse
import random
from sqlalchemy import text
from backend.app.core.database import SessionLocal
from backend.app.core.init_db import init_prod_data


def seed_demo_data():
    """
    Remplir la base avec un jeu d'essai V2 multi-établissement complet et réaliste.

    Reseeder une base de démo commence toujours par ce qui initialise une base de production
    (schéma + réglages système + tables de référence RH) — d'où l'appel à init_prod_data() en
    tout premier, avant d'ajouter par-dessus tout le contenu propre à la démo (établissements,
    matières, enseignants, classes, cours...).
    """
    init_prod_data()
    print("[SEED DEMO] Ajout du jeu d'essai de démonstration...")
    from backend.app.models.timeslot import Timeslot

    db = SessionLocal()
    try:
        # 1. Création des Établissements de la Cité Scolaire
        db.execute(text("INSERT INTO schools (uai, name, student_start_date, student_end_date) VALUES ('0750001A', 'Collège Jean Jaurès', '2026-09-01', '2027-06-30')"))
        db.execute(text("INSERT INTO schools (uai, name, student_start_date, student_end_date) VALUES ('0750002B', 'Lycée Jean Jaurès', '2026-09-01', '2027-06-30')"))
        db.commit()

        clg_id = db.execute(text("SELECT id FROM schools WHERE uai = '0750001A'")).scalar()
        lyc_id = db.execute(text("SELECT id FROM schools WHERE uai = '0750002B'")).scalar()

        # 2. Création des Disciplines nationales
        disciplines_data = [
            ("L0100", "Mathématiques"),
            ("L0200", "Lettres Modernes"),
            ("L0420", "Histoire-Géographie"),
            ("L1500", "Sciences Physiques"),
            ("L1600", "Sciences de la Vie et de la Terre"),
            ("L0400", "Anglais"),
            ("L1800", "Arts Plastiques"),
            ("L1900", "Éducation Physique et Sportive"),
            ("L1400", "Technologie")
        ]
        discipline_ids = {}
        for code, name in disciplines_data:
            db.execute(text("INSERT INTO disciplines (code, name) VALUES (:code, :name)"), {"code": code, "name": name})
            db.commit()
            d_id = db.execute(text("SELECT id FROM disciplines WHERE code = :code"), {"code": code}).scalar()
            discipline_ids[code] = d_id

        # 2b. Modalités d'élection (nomenclature nationale STSWEB)
        election_methods_data = [
            ("F", "FACULTATIF", "MATIERE ENSEIGNEE OPTION FACULTATIVE"),
            ("L", "AJOUT ACAD", "AJOUT ACADEMIQUE AU PROGRAMME"),
            ("N", "OBL OU FAC", "MATIERE ENSEIGNEE OBLIG. OU FACULTATIVE"),
            ("O", "OBLIGATOIR", "MATIERE ENSEIGNEE OPTION OBLIGATOIRE"),
            ("R", "ENS.RELIG.", "ENSEIGNEMENT RELIGIEUX"),
            ("S", "TRONC COMM", "MATIERE ENSEIGNEE EN TRONC COMMUN"),
            ("X", "MESURE SPE", "MESURE SPECIFIQUE"),
        ]
        for code, short_label, long_label in election_methods_data:
            db.execute(text(
                "INSERT INTO election_methods (code, name, export_code) VALUES (:code, :name, :export_code)"
            ), {"code": code, "name": long_label, "export_code": short_label})
        db.commit()
        election_method_s_id = db.execute(text("SELECT id FROM election_methods WHERE code = 'S'")).scalar()

        # 3. Création des Budgets TRMD pour les deux écoles
        for code, d_id in discipline_ids.items():
            # Collège
            db.execute(text(
                "INSERT INTO trmd_budgets (school_id, discipline_id, allocated_hp, allocated_hsa, allocated_posts) "
                "VALUES (:school_id, :discipline_id, 36.0, 4.0, 2.0)"
            ), {"school_id": clg_id, "discipline_id": d_id})
            # Lycée
            db.execute(text(
                "INSERT INTO trmd_budgets (school_id, discipline_id, allocated_hp, allocated_hsa, allocated_posts) "
                "VALUES (:school_id, :discipline_id, 45.0, 6.0, 2.5)"
            ), {"school_id": lyc_id, "discipline_id": d_id})
        db.commit()

        # 4. Création des Matières (Subjects)
        subjects_data = [
            ("MATHS", "006600", "Maths", "Mathématiques", "#a5b4fc", "L0100"),
            ("FRAN", "004300", "Français", "Lettres Modernes", "#f9a8d4", "L0200"),
            ("HG", "003200", "Hist-Géo", "Histoire-Géographie", "#fcd34d", "L0420"),
            ("PC", "005500", "Phys-Chimie", "Sciences Physiques", "#5eead4", "L1500"),
            ("SVT", "005600", "SVT", "Sciences de la Vie et de la Terre", "#86efac", "L1600"),
            ("ANG", "002200", "Anglais", "Langue Vivante : Anglais", "#67e8f9", "L0400"),
            ("ARTS", "001100", "Arts Plast.", "Arts Plastiques", "#c4b5fd", "L1800"),
            ("EPS", "009900", "EPS", "Éducation Physique et Sportive", "#bef264", "L1900"),
            ("TECHNO", "008800", "Techno", "Technologie", "#7dd3fc", "L1400")
        ]
        subject_ids = {}
        for code, nomenclature, short, long, color, d_code in subjects_data:
            db.execute(text(
                "INSERT INTO subjects (code, code_nomenclature, short_name, name, color, is_etp, is_specialty, pedagogic_weight, discipline_id) "
                "VALUES (:code, :nomenclature, :short, :long, :color, 1, 0, 1.0, :discipline_id)"
            ), {
                "code": code,
                "nomenclature": nomenclature,
                "short": short,
                "long": long,
                "color": color,
                "discipline_id": discipline_ids[d_code]
            })
            db.commit()
            s_id = db.execute(text("SELECT id FROM subjects WHERE code = :code"), {"code": code}).scalar()
            subject_ids[code] = s_id

        # 4bis. Niveaux de formation (RefGrade) — déjà seedés par init_db.py::init_prod_data()
        # (nomenclature nationale, présente dans toute base de production), appelée avant ce
        # script (voir seed_demo_data ci-dessous) : simple lookup, pas de nouvelle insertion.
        grade_ids = {}
        for grade_name in ["6EME", "5EME", "2NDE", "1ERE"]:
            grade_ids[grade_name] = db.execute(text("SELECT id FROM ref_grades WHERE name = :name"), {"name": grade_name}).scalar()

        # 5. Création des MEFs (2 pour collège, 2 pour lycée)
        db.execute(text("INSERT INTO mefs (school_id, code_national, name, ref_grade_id, forecast_student_count, max_students_per_class) VALUES (:school_id, '10010012110', '6EME GENERALE', :ref_grade_id, 120, 30)"), {"school_id": clg_id, "ref_grade_id": grade_ids["6EME"]})
        db.execute(text("INSERT INTO mefs (school_id, code_national, name, ref_grade_id, forecast_student_count, max_students_per_class) VALUES (:school_id, '10010012111', '5EME GENERALE', :ref_grade_id, 115, 30)"), {"school_id": clg_id, "ref_grade_id": grade_ids["5EME"]})
        db.execute(text("INSERT INTO mefs (school_id, code_national, name, ref_grade_id, forecast_student_count, max_students_per_class) VALUES (:school_id, '20010012110', '2NDE GENERALE', :ref_grade_id, 150, 35)"), {"school_id": lyc_id, "ref_grade_id": grade_ids["2NDE"]})
        db.execute(text("INSERT INTO mefs (school_id, code_national, name, ref_grade_id, forecast_student_count, max_students_per_class) VALUES (:school_id, '20010012111', '1ERE GENERALE', :ref_grade_id, 140, 35)"), {"school_id": lyc_id, "ref_grade_id": grade_ids["1ERE"]})
        db.commit()

        mef_6_id = db.execute(text("SELECT id FROM mefs WHERE code_national = '10010012110'")).scalar()
        mef_2_id = db.execute(text("SELECT id FROM mefs WHERE code_national = '20010012110'")).scalar()

        # 6. Création des Créneaux Temporels (Lundi index 1 au Samedi index 6, de 8h à 18h, pas de 15 minutes)
        timeslots = []
        for day in range(1, 7):
            m_val = 480
            while m_val < 1080:
                if day == 3 and m_val >= Timeslot.get_noon_boundary_minutes():
                    m_val += 15
                    continue
                db.execute(text("INSERT INTO timeslots (day_of_week, minutes_from_midnight) VALUES (:day, :minutes_from_midnight)"), {"day": day, "minutes_from_midnight": m_val})
                db.commit()
                ts_id = db.execute(text("SELECT id FROM timeslots WHERE day_of_week = :day AND minutes_from_midnight = :minutes_from_midnight"), {"day": day, "minutes_from_midnight": m_val}).scalar()
                timeslots.append(ts_id)
                m_val += 15

        # 7. Saisie des period_types, périodes temporelles (Semestres) et Alternances (Semaines A/B)
        db.execute(text("INSERT INTO period_types (name) VALUES ('Trimestre')"))
        db.execute(text("INSERT INTO period_types (name) VALUES ('Semestre')"))
        db.commit()

        sem_type_id = db.execute(text("SELECT id FROM period_types WHERE name = 'Semestre'")).scalar()

        db.execute(text("INSERT INTO periods (period_type_id, school_id, code, name, start_date, end_date) VALUES (:type_id, :school_id, 'S1_CLG', 'Semestre 1 Collège', '2026-09-01', '2027-01-31')"), {"type_id": sem_type_id, "school_id": clg_id})
        db.execute(text("INSERT INTO periods (period_type_id, school_id, code, name, start_date, end_date) VALUES (:type_id, :school_id, 'S2_CLG', 'Semestre 2 Collège', '2027-02-01', '2027-06-30')"), {"type_id": sem_type_id, "school_id": clg_id})
        db.execute(text("INSERT INTO periods (period_type_id, school_id, code, name, start_date, end_date) VALUES (:type_id, :school_id, 'S1_LYC', 'Semestre 1 Lycée', '2026-09-01', '2027-01-31')"), {"type_id": sem_type_id, "school_id": lyc_id})
        db.execute(text("INSERT INTO periods (period_type_id, school_id, code, name, start_date, end_date) VALUES (:type_id, :school_id, 'S2_LYC', 'Semestre 2 Lycée', '2027-02-01', '2027-06-30')"), {"type_id": sem_type_id, "school_id": lyc_id})
        db.execute(text("INSERT INTO alternations (code, name, color) VALUES ('WEEK_A', 'Semaine A', '#3498DB')"))
        db.execute(text("INSERT INTO alternations (code, name, color) VALUES ('WEEK_B', 'Semaine B', '#E74C3C')"))
        db.execute(text("INSERT INTO alternations (code, name, color) VALUES ('HEBDO', 'Hebdomadaire', '#2ECC71')"))
        db.commit()

        s1_id = db.execute(text("SELECT id FROM periods WHERE code = 'S1_CLG'")).scalar()
        week_a_id = db.execute(text("SELECT id FROM alternations WHERE code = 'WEEK_A'")).scalar()

        # 8. Création des Enseignants (40 profs : 20 collège, 20 lycée)
        teachers = []
        for i in range(1, 41):
            school_idx = clg_id if i <= 20 else lyc_id
            first_name = "Prof"
            last_name = f"Teacher_{i}"
            code = f"T{i}"
            db.execute(text(
                "INSERT INTO teachers (code, first_name, last_name, max_weekly_hours, school_id, "
                "photo_diffusion_authorized, phone_diffusion_authorized, email_diffusion_authorized, "
                "is_board_member, is_temporary_support) "
                "VALUES (:code, :first_name, :last_name, 18.0, :school_id, 0, 0, 0, 0, 0)"
            ), {"code": code, "first_name": first_name, "last_name": last_name, "school_id": school_idx})
            db.commit()
            t_id = db.execute(text("SELECT id FROM teachers WHERE code = :code"), {"code": code}).scalar()
            teachers.append((t_id, school_idx))

        # 8a2. Rattachement à une discipline (TeacherDiscipline) : chaque enseignant doit toujours
        # être rattaché à au moins une discipline (Volet C, "discipline obligatoire partout" —
        # évite une ligne "Sans discipline" dans le TRMD, voir architecture.md) — répartition
        # round-robin sur les disciplines nationales, 18h/semaine (= max_weekly_hours) par défaut.
        discipline_codes = list(discipline_ids.keys())
        for idx, (t_id, _school_idx) in enumerate(teachers):
            d_id = discipline_ids[discipline_codes[idx % len(discipline_codes)]]
            db.execute(text(
                "INSERT INTO teacher_disciplines (teacher_id, discipline_id, duration_minutes) "
                "VALUES (:teacher_id, :discipline_id, 1080)"
            ), {"teacher_id": t_id, "discipline_id": d_id})
        db.commit()

        # 8b. Création de personnel non enseignant (AESH, Labo, etc.)
        non_teaching_staffs = []
        staff_roles = ["AESH", "Technicien de laboratoire", "Surveillant", "Infirmière"]
        for i in range(1, 11):
            school_idx = clg_id if i <= 5 else lyc_id
            db.execute(text(
                "INSERT INTO non_teaching_staffs (first_name, last_name, role, school_id) "
                "VALUES (:fn, :ln, :role, :school_id)"
            ), {"fn": "Staff", "ln": f"NonTeaching_{i}", "role": random.choice(staff_roles), "school_id": school_idx})
            db.commit()
            s_id = db.execute(text("SELECT id FROM non_teaching_staffs WHERE last_name = :ln"), {"ln": f"NonTeaching_{i}"}).scalar()
            non_teaching_staffs.append((s_id, school_idx))

        # 9. Insérer des préférences (ResourcePreference) de test pour quelques professeurs (vœux)
        # Prof 1 et 21 n'aiment pas travailler le mercredi matin (timeslot du mercredi 8h, day_of_week = 3, minutes_from_midnight = 480)
        mercredi_8h_ts = db.execute(text("SELECT id FROM timeslots WHERE day_of_week = 3 AND minutes_from_midnight = 480")).scalar()
        if mercredi_8h_ts:
            for t_id, s_id in [teachers[0], teachers[20]]:
                db.execute(text(
                    "INSERT INTO resource_preferences (resource_type, resource_id, timeslot_id, preference_level, week_type) "
                    "VALUES ('Teacher', :resource_id, :timeslot_id, 'Unsuited', 'A')"
                ), {"resource_id": t_id, "timeslot_id": mercredi_8h_ts})
                db.commit()
                pref_id = db.execute(text("SELECT id FROM resource_preferences WHERE resource_type = 'Teacher' AND resource_id = :resource_id AND week_type = 'A'"), {"resource_id": t_id}).scalar()

                # Liaison Période S1 uniquement
                db.execute(text("INSERT INTO preference_periods (preference_id, period_id) VALUES (:pref_id, :s_id)"), {"pref_id": pref_id, "s_id": s1_id})
                db.commit()

        # 10. Création des Divisions (Classes d'élèves) : 3 pour Collège, 3 pour Lycée
        clg_divisions_data = ["6A", "6B", "5A"]
        lyc_divisions_data = ["2A", "2B", "1A"]
        divisions = []
        student_first_names = ["Léa", "Hugo", "Chloé"]
        student_last_names = ["Bernard", "Petit", "Robert"]

        for name in clg_divisions_data:
            code = name.replace("è", "E").replace(" ", "_").upper()
            db.execute(text(
                "INSERT INTO divisions (code, name, student_count, color, school_id) "
                "VALUES (:code, :name, 28, '#3498DB', :school_id)"
            ), {"code": code, "name": name, "school_id": clg_id})
            db.commit()
            d_id = db.execute(text("SELECT id FROM divisions WHERE code = :code"), {"code": code}).scalar()
            divisions.append((d_id, clg_id))
            db.execute(text(
                "INSERT INTO mef_divisions (mef_id, division_id, forecast_student_count) "
                "VALUES (:mef_id, :division_id, 28)"
            ), {"mef_id": mef_6_id, "division_id": d_id})
            db.commit()
            for fn, ln in zip(student_first_names, student_last_names):
                db.execute(text(
                    "INSERT INTO students (first_name, last_name, division_id, mef_id) "
                    "VALUES (:fn, :ln, :division_id, :mef_id)"
                ), {"fn": fn, "ln": f"{ln}_{code}", "division_id": d_id, "mef_id": mef_6_id})
            db.commit()

        for name in lyc_divisions_data:
            code = name.replace("è", "E").replace(" ", "_").upper()
            db.execute(text(
                "INSERT INTO divisions (code, name, student_count, color, school_id) "
                "VALUES (:code, :name, 32, '#E74C3C', :school_id)"
            ), {"code": code, "name": name, "school_id": lyc_id})
            db.commit()
            d_id = db.execute(text("SELECT id FROM divisions WHERE code = :code"), {"code": code}).scalar()
            divisions.append((d_id, lyc_id))
            db.execute(text(
                "INSERT INTO mef_divisions (mef_id, division_id, forecast_student_count) "
                "VALUES (:mef_id, :division_id, 32)"
            ), {"mef_id": mef_2_id, "division_id": d_id})
            db.commit()
            for fn, ln in zip(student_first_names, student_last_names):
                db.execute(text(
                    "INSERT INTO students (first_name, last_name, division_id, mef_id) "
                    "VALUES (:fn, :ln, :division_id, :mef_id)"
                ), {"fn": fn, "ln": f"{ln}_{code}", "division_id": d_id, "mef_id": mef_2_id})
            db.commit()

        # 10b. Création de MefService (gabarit Maths), et propagation manuelle en Service opérationnel
        # pour 6ème A et 6ème B, alignés (même modèle de répartition : 2x1h hebdo + 1x30min dédoublé)
        maths_id = subject_ids["MATHS"]
        mef_service_6_id = db.execute(text(
            "INSERT INTO mef_services (mef_id, subject_id, discipline_id, election_method_id, student_count, weighting_coefficient, "
            "weekly_duration_full_class_minutes, weekly_duration_reduced_minutes, weekly_duration_split_minutes, reduced_group_student_count) "
            "VALUES (:mef_id, :subject_id, :discipline_id, :election_method_id, 28, 1.0, 120, 0, 30, 14)"
        ), {"mef_id": mef_6_id, "subject_id": maths_id, "discipline_id": discipline_ids["L0100"], "election_method_id": election_method_s_id})
        db.commit()
        mef_service_6_id = db.execute(text("SELECT id FROM mef_services WHERE mef_id = :mef_id AND subject_id = :subject_id"), {"mef_id": mef_6_id, "subject_id": maths_id}).scalar()

        alignment_id = db.execute(text("INSERT INTO alignments (code, name, color) VALUES ('AL_MATHS_6EME', 'Maths - Alignement 6ème A/B', '#3498DB')"))
        db.commit()
        alignment_id = db.execute(text("SELECT id FROM alignments WHERE code = 'AL_MATHS_6EME'")).scalar()

        service_ids = []
        for code in ["6A", "6B"]:
            mef_division_id = db.execute(text(
                "SELECT md.id FROM mef_divisions md JOIN divisions d ON d.id = md.division_id WHERE d.code = :code"
            ), {"code": code}).scalar()
            db.execute(text(
                "INSERT INTO services (mef_service_id, mef_division_id, subject_id, discipline_id, election_method_id, student_count, "
                "weighting_coefficient, weekly_duration_full_class_minutes, weekly_duration_reduced_minutes, "
                "weekly_duration_split_minutes, alignment_id) "
                "VALUES (:mef_service_id, :mef_division_id, :subject_id, :discipline_id, :election_method_id, 28, 1.0, 120, 0, 30, :alignment_id)"
            ), {"mef_service_id": mef_service_6_id, "mef_division_id": mef_division_id, "subject_id": maths_id, "discipline_id": discipline_ids["L0100"], "election_method_id": election_method_s_id, "alignment_id": alignment_id})
            db.commit()
            service_id = db.execute(text("SELECT id FROM services WHERE mef_division_id = :mef_division_id"), {"mef_division_id": mef_division_id}).scalar()
            service_ids.append(service_id)

        # occurrence_count = séances par ÉLÈVE par semaine, group_count = groupes parallèles
        # nécessaires (plan Volet B) — désormais deux colonnes distinctes. FULL_CLASS :
        # occurrence_count=2 (2 séances d'1h/semaine), group_count=1. SPLIT : occurrence_count=1
        # (1 séance de 30min/semaine par élève), group_count=2 (fixe, deux demi-classes en
        # parallèle) — raw_need_weekly_duration_minutes reflète le besoin en heures-PROFESSEUR
        # (30min x 2 groupes = 60min), distinct de weekly_duration_split_minutes (30min, le besoin
        # côté ÉLÈVE). raw/weighted_need calculés à la main (le seed contourne les @constrains,
        # voir _compute_need_durations) : weighting_coefficient=1.0 pour ces deux services (défaut).
        for service_id in service_ids:
            db.execute(text(
                "INSERT INTO service_repartitions (service_id, occurrence_count, duration_minutes, periodicity, group_type, group_count, raw_need_weekly_duration_minutes, weighted_need_weekly_duration_minutes, name) "
                "VALUES (:service_id, 2, 60, 'WEEKLY', 'FULL_CLASS', 1, 120, 120, '2x1h(H/C)')"
            ), {"service_id": service_id})
            db.execute(text(
                "INSERT INTO service_repartitions (service_id, occurrence_count, duration_minutes, periodicity, group_type, group_count, raw_need_weekly_duration_minutes, weighted_need_weekly_duration_minutes, name) "
                "VALUES (:service_id, 1, 30, 'WEEKLY', 'SPLIT', 2, 60, 60, '1x0h30(H/D)')"
            ), {"service_id": service_id})
            db.commit()

        # 10c. Rattachement de professeurs aux Services Maths 6ème (m2m service_teachers) : 6ème A
        # en co-enseignement (2 profs), 6ème B avec 1 seul prof partagé avec 6ème A — donne des
        # données non triviales pour la vue pivot "Services par prof" (GenericPivot, un prof lié à
        # plusieurs services est crédité en entier de chacun, voir architecture.md section 15.L).
        teacher_pool_clg = [t[0] for t in teachers if t[1] == clg_id]
        service_teachers_map = {
            service_ids[0]: teacher_pool_clg[:2],
            service_ids[1]: [teacher_pool_clg[1]],
        }
        for s_id, t_ids in service_teachers_map.items():
            for t_id in t_ids:
                db.execute(text(
                    "INSERT INTO service_teachers (service_id, teacher_id) VALUES (:service_id, :teacher_id)"
                ), {"service_id": s_id, "teacher_id": t_id})
        db.commit()

        # 10d. Matière(s) enseignée(s) pour 2 profs du collège (m2m teacher_subjects) : chacun
        # n'a que Maths -> preferred_subject_id calculé manuellement (le seed est en raw SQL, donc
        # le @constrains de Teacher._sync_preferred_subject ne se déclenche jamais ici, comme pour
        # tout autre champ calculé du seed, ex: ServiceRepartition.name). Sert à tester la
        # pré-saisie automatique de la matière dans l'assistant de décomposition de cours.
        for t_id in teacher_pool_clg[:2]:
            db.execute(text(
                "INSERT INTO teacher_subjects (teacher_id, subject_id) VALUES (:teacher_id, :subject_id)"
            ), {"teacher_id": t_id, "subject_id": maths_id})
            db.execute(text(
                "UPDATE teachers SET preferred_subject_id = :subject_id WHERE id = :teacher_id"
            ), {"teacher_id": t_id, "subject_id": maths_id})
        db.commit()

        # 11. Création des Salles de Classe (10 salles)
        classrooms = []
        for i in range(1, 11):
            school_idx = clg_id if i <= 5 else lyc_id
            name = f"Salle {100 + i}"
            code = f"S{100 + i}"
            db.execute(text(
                "INSERT INTO classrooms (code, name, capacity, quantity, school_id) "
                "VALUES (:code, :name, 35, 1, :school_id)"
            ), {"code": code, "name": name, "school_id": school_idx})
            db.commit()
            c_id = db.execute(text("SELECT id FROM classrooms WHERE code = :code"), {"code": code}).scalar()
            classrooms.append((c_id, school_idx))

        # 12. Création d'une suite de cours & sessions (simple / complexes / co-enseignements)
        # Chaque classe a au moins 4 cours de base
        course_count = 0
        for d_id, s_id in divisions:
            # Matières simples : Maths (MATHS), Français (FRAN), Hist-Géo (HG)
            simple_subjects = ["MATHS", "FRAN", "HG"]
            complex_subjects = ["SVT", "PC", "TECHNO"]

            if s_id == clg_id:
                # Associer des enseignants du collège (index 1 à 20)
                teacher_pool = [t[0] for t in teachers if t[1] == clg_id]
            else:
                # Associer des enseignants du lycée (index 21 à 40)
                teacher_pool = [t[0] for t in teachers if t[1] == lyc_id]

            # 1. Cours simples
            for s_code in simple_subjects:
                subj_id = subject_ids[s_code]
                t_id = random.choice(teacher_pool)
                duration = 60

                db.execute(text(
                    "INSERT INTO courses (subject_id, duration_minutes, is_composed, lock_structure, week_type, is_pinned, is_co_teaching, school_id, election_method_id, parent_timeslot_offset) "
                    "VALUES (:subject_id, :duration_minutes, 0, 0, 'W', 0, 0, :school_id, :election_method_id, 0)"
                ), {
                    "subject_id": subj_id,
                    "duration_minutes": duration,
                    "school_id": s_id,
                    "election_method_id": election_method_s_id
                })
                course_id = db.execute(text("SELECT last_insert_rowid()")).scalar()

                db.execute(text("INSERT INTO course_teachers (course_id, teacher_id) VALUES (:course_id, :teacher_id)"), {"course_id": course_id, "teacher_id": t_id})
                db.execute(text("INSERT INTO course_divisions (course_id, division_id) VALUES (:course_id, :division_id)"), {"course_id": course_id, "division_id": d_id})

                # Affecter aléatoirement du personnel non enseignant
                if random.random() < 0.15:
                    staff_pool = [s[0] for s in non_teaching_staffs if s[1] == s_id]
                    if staff_pool:
                        st_id = random.choice(staff_pool)
                        db.execute(text("INSERT INTO course_non_teaching_staffs (course_id, non_teaching_staff_id) VALUES (:course_id, :staff_id)"), {"course_id": course_id, "staff_id": st_id})

                course_count += 1

            # --- Création des Groupes pour le Pôle Sciences ---
            # 1. Partition
            db.execute(text("INSERT INTO partitions (code, name, division_id, is_system_generated) VALUES ('SCI', 'Groupes Sciences', :division_id, 0)"), {"division_id": d_id})
            part_id = db.execute(text("SELECT last_insert_rowid()")).scalar()

            # 2. ClassParts & Groups (3 groupes)
            div_groups = []
            for g_idx in range(1, 4):
                db.execute(text(
                    "INSERT INTO class_parts (partition_id, name, student_count, color, is_system_generated) "
                    "VALUES (:part_id, :name, 10, '#CCCCCC', 0)"
                ), {"part_id": part_id, "name": f"Groupe {g_idx}"})
                cp_id = db.execute(text("SELECT last_insert_rowid()")).scalar()

                db.execute(text(
                    "INSERT INTO groups (name, student_count, color, is_variable_size, is_system_generated) VALUES (:name, 10, '#CCCCCC', 0, 0)"
                ), {"name": f"Groupe Sciences {g_idx}"})
                grp_id = db.execute(text("SELECT last_insert_rowid()")).scalar()

                db.execute(text("INSERT INTO group_class_parts (group_id, class_part_id) VALUES (:g_id, :cp_id)"), {"g_id": grp_id, "cp_id": cp_id})
                div_groups.append(grp_id)

            # Sélection de 3 professeurs distincts
            selected_teachers = random.sample(teacher_pool, 3)
            # Sélection de 3 salles distinctes (classrooms contient (id, school_id))
            room_pool = [c[0] for c in classrooms if c[1] == s_id]
            selected_rooms = random.sample(room_pool, 3) if len(room_pool) >= 3 else room_pool

            # 2. Cours complexe (Pôle Sciences) - sans matière (NULL)
            db.execute(text(
                "INSERT INTO courses (subject_id, duration_minutes, is_composed, lock_structure, week_type, is_pinned, is_co_teaching, school_id, name, election_method_id, parent_timeslot_offset) "
                "VALUES (NULL, 90, 1, 0, 'W', 0, 0, :school_id, 'Pôle Sciences', :election_method_id, 0)"
            ), {"school_id": s_id, "election_method_id": election_method_s_id})
            parent_id = db.execute(text("SELECT last_insert_rowid()")).scalar()
            course_count += 1

            # Affectation des 3 profs, 3 salles et 3 groupes au cours PARENT
            for t_id in selected_teachers:
                db.execute(text("INSERT INTO course_teachers (course_id, teacher_id) VALUES (:c_id, :t_id)"), {"c_id": parent_id, "t_id": t_id})
            for r_id in selected_rooms:
                db.execute(text("INSERT INTO course_classrooms (course_id, classroom_id) VALUES (:c_id, :r_id)"), {"c_id": parent_id, "r_id": r_id})
            for g_id in div_groups:
                db.execute(text("INSERT INTO course_groups (course_id, group_id) VALUES (:c_id, :g_id)"), {"c_id": parent_id, "g_id": g_id})

            # 3. Enfants du cours complexe
            for idx, s_code in enumerate(complex_subjects):
                subj_id = subject_ids[s_code]
                t_id = selected_teachers[idx % len(selected_teachers)]
                r_id = selected_rooms[idx % len(selected_rooms)]
                g_id = div_groups[idx % len(div_groups)]
                duration = 90

                db.execute(text(
                    "INSERT INTO courses (subject_id, parent_id, duration_minutes, is_composed, lock_structure, week_type, is_pinned, is_co_teaching, school_id, election_method_id, parent_timeslot_offset) "
                    "VALUES (:subject_id, :parent_id, :duration_minutes, 0, 0, 'W', 0, 0, :school_id, :election_method_id, 0)"
                ), {
                    "subject_id": subj_id,
                    "parent_id": parent_id,
                    "duration_minutes": duration,
                    "school_id": s_id,
                    "election_method_id": election_method_s_id
                })
                course_id = db.execute(text("SELECT last_insert_rowid()")).scalar()

                db.execute(text("INSERT INTO course_teachers (course_id, teacher_id) VALUES (:course_id, :teacher_id)"), {"course_id": course_id, "teacher_id": t_id})
                db.execute(text("INSERT INTO course_classrooms (course_id, classroom_id) VALUES (:course_id, :r_id)"), {"course_id": course_id, "r_id": r_id})
                db.execute(text("INSERT INTO course_groups (course_id, group_id) VALUES (:course_id, :g_id)"), {"course_id": course_id, "g_id": g_id})

            # 4. Cours alternés (Semaine A / Semaine B)
            # Ajout d'Arts Plastiques en Semaine A, et Anglais en Semaine B
            for s_code, w_type in [("ARTS", "A"), ("ANG", "B")]:
                subj_id = subject_ids[s_code]
                t_id = random.choice(teacher_pool)

                db.execute(text(
                    "INSERT INTO courses (subject_id, duration_minutes, is_composed, lock_structure, week_type, is_pinned, is_co_teaching, school_id, election_method_id, parent_timeslot_offset) "
                    "VALUES (:subject_id, 60, 0, 0, :week_type, 0, 0, :school_id, :election_method_id, 0)"
                ), {
                    "subject_id": subj_id,
                    "week_type": w_type,
                    "school_id": s_id,
                    "election_method_id": election_method_s_id
                })
                course_id = db.execute(text("SELECT last_insert_rowid()")).scalar()
                db.execute(text("INSERT INTO course_teachers (course_id, teacher_id) VALUES (:course_id, :teacher_id)"), {"course_id": course_id, "teacher_id": t_id})
                db.execute(text("INSERT INTO course_divisions (course_id, division_id) VALUES (:course_id, :division_id)"), {"course_id": course_id, "division_id": d_id})
                course_count += 1

        # 13. Création de contraintes métier entre les matières
        print("[SEED DEMO] Ajout des contraintes matière (SubjectToSubjectConstraint)...")
        # Contrainte 1 : Interdire les cours de maths après les cours d'EPS
        db.execute(text(
            "INSERT INTO subject_to_subject_constraints (target_subject_a_id, target_subject_b_id, is_optional, prevent_consecutive_a_then_b, incompatible_same_day, incompatible_same_half_day, incompatible_two_consecutive_days, weekly_order, group_course_order, max_separation) "
            "VALUES (:eps_id, :maths_id, 0, 1, 0, 0, 0, 'NONE', 'NONE', 'NONE')"
        ), {"eps_id": subject_ids["EPS"], "maths_id": subject_ids["MATHS"]})

        # Contrainte 2 : Max 2 heures de français par jour
        db.execute(text(
            "INSERT INTO subject_to_subject_constraints (target_subject_a_id, target_subject_b_id, is_optional, max_hours_per_day, incompatible_same_day, incompatible_same_half_day, incompatible_two_consecutive_days, weekly_order, group_course_order, max_separation) "
            "VALUES (:fran_id, :fran_id, 0, 2.0, 0, 0, 0, 'NONE', 'NONE', 'NONE')"
        ), {"fran_id": subject_ids["FRAN"]})

        # Contrainte 3 : 2 jours minimum entre deux cours d'EPS
        db.execute(text(
            "INSERT INTO subject_to_subject_constraints (target_subject_a_id, target_subject_b_id, is_optional, min_free_half_days_between, incompatible_same_day, incompatible_same_half_day, incompatible_two_consecutive_days, weekly_order, group_course_order, max_separation) "
            "VALUES (:eps_id, :eps_id, 0, 4, 0, 0, 0, 'NONE', 'NONE', 'NONE')"
        ), {"eps_id": subject_ids["EPS"]})

        db.commit()
        print(f"[SEED DEMO] Succès ! Jeu d'essai V2 généré avec : 2 établissements, 9 disciplines, 9 matières, 40 profs, {len(divisions)} divisions, {len(classrooms)} salles et {course_count} cours/séances.")

    except Exception as e:
        db.rollback()
        print(f"[SEED DEMO ERREUR] Échec de la génération du jeu d'essai V2 : {e}")
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset complet d'une base de données de démonstration Klepsydrix V2 (appelle d'abord init_db.py, puis ajoute le jeu d'essai complet).")
    parser.parse_args()
    seed_demo_data()
