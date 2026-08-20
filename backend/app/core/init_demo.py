import argparse
import random
from argon2 import PasswordHasher
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
                "INSERT INTO ref_election_methods (code, name, export_code) VALUES (:code, :name, :export_code)"
            ), {"code": code, "name": long_label, "export_code": short_label})
        db.commit()
        election_method_s_id = db.execute(text("SELECT id FROM ref_election_methods WHERE code = 'S'")).scalar()

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
        # is_specialty=True (réforme du lycée) sur les 4 matières qui servent d'enseignements de
        # spécialité en 1ère générale dans ce jeu de démo (voir StudentSpecialtyChoice/
        # SpecialtyGroupConfig/wizard_specialty_group_generation.py plus bas).
        specialty_codes = {"MATHS", "SVT", "PC", "HG"}
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
                "VALUES (:code, :nomenclature, :short, :long, :color, 1, :is_specialty, 1.0, :discipline_id)"
            ), {
                "code": code,
                "nomenclature": nomenclature,
                "short": short,
                "long": long,
                "color": color,
                "is_specialty": 1 if code in specialty_codes else 0,
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

        # 6. Génération des Créneaux Temporels à partir de la grille horaire déjà seedée par
        # init_prod_data() (grid_day_settings + STANDARD_TIMESLOT_DURATION, voir spec.md §0bis) —
        # réutilise le mécanisme de réconciliation générique plutôt qu'un INSERT raw indépendant,
        # pour que les Timeslot du jeu de démo restent PAR CONSTRUCTION cohérents avec ce que le
        # wizard « Grille horaire » afficherait (lundi-vendredi 8h-18h, samedi 8h-12h, dimanche fermé).
        Timeslot.reconcile_all_days(db)

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
                "INSERT INTO teachers (code, first_name, last_name, max_hsa_duration_minutes, school_id, "
                "photo_diffusion_authorized, phone_diffusion_authorized, email_diffusion_authorized, "
                "is_board_member, is_temporary_support) "
                "VALUES (:code, :first_name, :last_name, 120, :school_id, 0, 0, 0, 0, 0)"
            ), {"code": code, "first_name": first_name, "last_name": last_name, "school_id": school_idx})
            db.commit()
            t_id = db.execute(text("SELECT id FROM teachers WHERE code = :code"), {"code": code}).scalar()
            teachers.append((t_id, school_idx))

        # 8a2. Rattachement à une discipline (TeacherDiscipline) : chaque enseignant doit toujours
        # être rattaché à au moins une discipline (Volet C, "discipline obligatoire partout" —
        # évite une ligne "Sans discipline" dans le TRMD, voir architecture.md) — répartition
        # round-robin sur les disciplines nationales, apport de 18h/semaine par défaut.
        discipline_codes = list(discipline_ids.keys())
        for idx, (t_id, _school_idx) in enumerate(teachers):
            d_id = discipline_ids[discipline_codes[idx % len(discipline_codes)]]
            db.execute(text(
                "INSERT INTO teacher_disciplines (teacher_id, discipline_id, duration_minutes) "
                "VALUES (:teacher_id, :discipline_id, 1080)"
            ), {"teacher_id": t_id, "discipline_id": d_id})
        db.commit()

        # 8a3. TeacherGradePreference (voir teacher_grade_preference.py) : le seed insère en SQL
        # brut, donc ne passe jamais par Teacher.create()/RefGrade.create() — la cascade qui
        # génère normalement une ligne par (professeur, niveau) ne se déclenche donc pas ici (même
        # raison que teacher_disciplines juste au-dessus, cohérent avec le reste du seed qui
        # contourne systématiquement la logique métier ORM). On reproduit donc à la main ce que la
        # cascade aurait produit : priorité neutre 2, aucun plafond de classes, pour chaque couple.
        ref_grade_ids = [row[0] for row in db.execute(text("SELECT id FROM ref_grades")).all()]
        for t_id, _school_idx in teachers:
            for rg_id in ref_grade_ids:
                db.execute(text(
                    "INSERT INTO teacher_grade_preferences (teacher_id, ref_grade_id, priority) "
                    "VALUES (:teacher_id, :ref_grade_id, 2)"
                ), {"teacher_id": t_id, "ref_grade_id": rg_id})
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

        # 9bis. Classes de 1ère GENERALE (2 divisions, 8 élèves chacune) + vœux de spécialité, pour
        # disposer d'un jeu de données réaliste testant le wizard de génération des groupes de
        # spécialité (wizard_specialty_group_generation.py) : chaque élève choisit 3 des 4
        # matières marquées is_specialty (MATHS/SVT/PC/HG ci-dessus), en 4 combinaisons différentes
        # tournantes pour obtenir une vraie variété de parcours à l'aperçu.
        mef_1ere_id = db.execute(text("SELECT id FROM mefs WHERE code_national = '20010012111'")).scalar()
        specialty_first_names = ["Emma", "Nathan", "Jade", "Louis", "Alice", "Tom", "Inès", "Rayan"]
        specialty_combos = [
            ("MATHS", "SVT", "PC"),
            ("MATHS", "SVT", "HG"),
            ("MATHS", "PC", "HG"),
            ("SVT", "PC", "HG"),
        ]

        for div_name in ["1ère A", "1ère B"]:
            code = div_name.replace("è", "E").replace(" ", "_").upper()
            db.execute(text(
                "INSERT INTO divisions (code, name, student_count, color, school_id) "
                "VALUES (:code, :name, 32, '#F97316', :school_id)"
            ), {"code": code, "name": div_name, "school_id": lyc_id})
            db.commit()
            d_id = db.execute(text("SELECT id FROM divisions WHERE code = :code"), {"code": code}).scalar()
            divisions.append((d_id, lyc_id))
            db.execute(text(
                "INSERT INTO mef_divisions (mef_id, division_id, forecast_student_count) "
                "VALUES (:mef_id, :division_id, 32)"
            ), {"mef_id": mef_1ere_id, "division_id": d_id})
            db.commit()

            for i, fn in enumerate(specialty_first_names):
                ln = f"{student_last_names[i % len(student_last_names)]}_{code}"
                db.execute(text(
                    "INSERT INTO students (first_name, last_name, division_id, mef_id) "
                    "VALUES (:fn, :ln, :division_id, :mef_id)"
                ), {"fn": fn, "ln": ln, "division_id": d_id, "mef_id": mef_1ere_id})
                db.commit()
                student_id = db.execute(
                    text("SELECT id FROM students WHERE first_name = :fn AND last_name = :ln"),
                    {"fn": fn, "ln": ln}
                ).scalar()
                combo = specialty_combos[i % len(specialty_combos)]
                for rank, subject_code in enumerate(combo, start=1):
                    db.execute(text(
                        "INSERT INTO student_specialty_choices (student_id, subject_id, rank) "
                        "VALUES (:student_id, :subject_id, :rank)"
                    ), {"student_id": student_id, "subject_id": subject_ids[subject_code], "rank": rank})
            db.commit()

        # Seuils de constitution des groupes de spécialité (SpecialtyGroupConfig) pour le niveau
        # 1ère : 5 élèves max par groupe — avec 12 élèves par matière (3 combinaisons sur 4 la
        # portent), ça déclenche bien 3 groupes par matière, sur les 2 divisions.
        one_ere_grade_id = grade_ids["1ERE"]
        for subject_code in ["MATHS", "SVT", "PC", "HG"]:
            db.execute(text(
                "INSERT INTO specialty_group_configs (subject_id, ref_grade_id, max_students_per_group, max_groups_count) "
                "VALUES (:subject_id, :ref_grade_id, 5, NULL)"
            ), {"subject_id": subject_ids[subject_code], "ref_grade_id": one_ere_grade_id})
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
                "weekly_duration_split_minutes, alignment_id, teachers_locked) "
                "VALUES (:mef_service_id, :mef_division_id, :subject_id, :discipline_id, :election_method_id, 28, 1.0, 120, 0, 30, :alignment_id, 0)"
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

        # 10d. Matière enseignée (m2m teacher_subjects) + preferred_subject_id pour TOUS les
        # enseignants, par répartition tournante sur les 8 matières réellement utilisées à l'étape
        # 12 (cours simples + complexes + alternés — EPS exclue, aucun cours n'y est jamais généré,
        # préférer EPS ne servirait donc jamais la pré-saisie du wizard) -> calculé manuellement
        # (le seed est en raw SQL, donc le @constrains de Teacher._sync_preferred_subject ne se
        # déclenche jamais ici, comme pour tout autre champ calculé du seed, ex: ServiceRepartition.
        # name). `teachers_by_course_subject_id` (indexé par subject_id ET school_id, un enseignant
        # n'enseignant jamais hors de son établissement) est réutilisé à l'étape 12 pour que les
        # cours générés restent cohérents avec cette préférence : un professeur affecté à un cours
        # de Maths y a de bonnes chances d'avoir Maths pour matière préférée, plutôt qu'un tirage
        # totalement indépendant comme auparavant. Sert aussi à tester la pré-saisie automatique de
        # la matière dans l'assistant de décomposition de cours (Course.composition_mapping).
        course_subject_codes = ["MATHS", "FRAN", "HG", "SVT", "PC", "TECHNO", "ARTS", "ANG"]
        teachers_by_course_subject_id: dict[tuple[int, int], list[int]] = {}
        for idx, (t_id, school_idx) in enumerate(teachers):
            subject_code = course_subject_codes[idx % len(course_subject_codes)]
            subj_id = subject_ids[subject_code]
            db.execute(text(
                "INSERT INTO teacher_subjects (teacher_id, subject_id) VALUES (:teacher_id, :subject_id)"
            ), {"teacher_id": t_id, "subject_id": subj_id})
            db.execute(text(
                "UPDATE teachers SET preferred_subject_id = :subject_id WHERE id = :teacher_id"
            ), {"teacher_id": t_id, "subject_id": subj_id})
            teachers_by_course_subject_id.setdefault((subj_id, school_idx), []).append(t_id)
        db.commit()

        def teacher_for_subject(subj_id: int, school_idx: int, pool: list) -> int:
            """Pioche en priorité un enseignant dont la matière préférée est `subj_id` (voir
            teachers_by_course_subject_id ci-dessus) — repli sur tout le pool si, par construction
            de la répartition tournante, aucun n'est disponible pour cette matière/école."""
            preferred = teachers_by_course_subject_id.get((subj_id, school_idx))
            return random.choice(preferred) if preferred else random.choice(pool)

        # 10e. Référentiel des types de salles (nomenclature ministérielle) — pas de contrainte
        # d'unicité sur code (voir ref_classroom_type.py) : la donnée de référence fournie contient
        # 4 lignes de code "22", reproduites telles quelles.
        ref_classroom_types_data = [
            ("01", "COURS DE RECREATION", "Cours de récréation"),
            ("02", "ESPACE DES PERSONNEL", "Espace de travail et de convivialité des personnels"),
            ("03", "SALLE ENS. GENERAL", "Salle d'enseignement général"),
            ("04", "ESPACE PROFESSIONNEL", "Espace professionnel, plateaux technique et ateliers d'application"),
            ("05", "SANITAIRES ELEVE", "Sanitaires élèves"),
            ("06", "ATELIERS MAINTENANCE", "Atelier de maintenance"),
            ("07", "BUREAUX ADMINIS.", "Bureau de direction et espace administratifs"),
            ("08", "ESPACE CIRCULATION", "Hall et espace de circulation"),
            ("09", "ESPACE VIE SCOLAIRE", "Espace vie scolaire"),
            ("10", "ESPACE PARENTS", "Espace parents"),
            ("11", "ESPACE SANTE", "Espace santé"),
            ("12", "SERVICE SOCIAL", "Espace service social"),
            ("13", "FOYERS DES ELEVES", "Foyers des élèves"),
            ("14", "CUISINE", "Office ou cuisine de restauration"),
            ("15", "PARVIS ET ENCEINTES", "Parvis et enceinte"),
            ("16", "SALLE PHYS&SPORTIVE", "Salle d'activités physiques et sportives"),
            ("17", "SALLE D'ARTS", "Salle d'arts plastiques-arts appliqués et culture artistique"),
            ("18", "SALLE DE MUSIQUE", "Salle d'éducation musicale - salle de musique"),
            ("19", "SALLE RESTAURATION", "Salle de restauration"),
            ("20", "SALLE D'ETUDE", "Salle d'étude"),
            ("21", "SALLE POLYVALENTE", "Salle polyvalente"),
            ("22", "SALLE SCIENTIFIQUE", "Salle scientifique et technologique"),
            ("22", "SALLE ENS. TECHNO", "Salle d'enseignement technologique"),
            ("22", "SALLE DE TP", "Salle de travaux pratiques"),
            ("22", "SALLE INFORMATIQUE", "Salle informatique"),
            ("23", "SANITAIRES ADULTES", "Sanitaire adulte"),
            ("24", "VESTIAIRES", "Vestiaire et local d'entretien"),
            ("25", "SALLE VIRTUELLE", "Salle virtuelle"),
            ("26", "CDI", "Centre de documentation et d'information"),
        ]
        for code, name, long_name in ref_classroom_types_data:
            db.execute(text(
                "INSERT INTO ref_classroom_types (code, name, long_name) VALUES (:code, :name, :long_name)"
            ), {"code": code, "name": name, "long_name": long_name})
        db.commit()
        salle_type_id = db.execute(text("SELECT id FROM ref_classroom_types WHERE name = 'SALLE ENS. GENERAL'")).scalar()

        # 11. Création des Salles de Classe (10 salles)
        classrooms = []
        for i in range(1, 11):
            school_idx = clg_id if i <= 5 else lyc_id
            name = f"Salle {100 + i}"
            code = f"S{100 + i}"
            db.execute(text(
                "INSERT INTO classrooms (code, name, capacity, school_id, ref_classroom_type_id) "
                "VALUES (:code, :name, 35, :school_id, :ref_classroom_type_id)"
            ), {"code": code, "name": name, "school_id": school_idx, "ref_classroom_type_id": salle_type_id})
            db.commit()
            c_id = db.execute(text("SELECT id FROM classrooms WHERE code = :code"), {"code": code}).scalar()
            classrooms.append((c_id, school_idx))

        # 11bis. Groupe de salles "Salles science" (lycée) : 3 sous-groupes (Labo SVT, Labo
        # Physique, Salles techno), chacun peuplé de 4 salles-feuilles de 30 places — arbre
        # (parent_classroom_id, voir classroom.py/classroom_closure.py). Les groupes eux-mêmes
        # (nœuds intermédiaires) n'ont ni capacité ni ref_classroom_type_id (réservés aux
        # salles-feuilles, voir Classroom._validate_group_has_no_type). La seed insère en SQL brut
        # (ne passe jamais par Classroom.create()/update()), donc classroom_closure — normalement
        # maintenue par _validate_and_sync_classroom_tree à chaque écriture ORM — est reconstituée
        # ici à la main (même convention que la cascade TeacherGradePreference, voir ref_grade.py) :
        # sans ça, leaf_classroom_ids_under() ne résoudrait aucune salle sous ces groupes.
        def _insert_closure_row(ancestor_id, descendant_id, depth):
            db.execute(text(
                "INSERT INTO classroom_closure (ancestor_id, descendant_id, depth) VALUES (:a, :d, :depth)"
            ), {"a": ancestor_id, "d": descendant_id, "depth": depth})

        tp_type_id = db.execute(text("SELECT id FROM ref_classroom_types WHERE name = 'SALLE DE TP'")).scalar()
        techno_type_id = db.execute(text("SELECT id FROM ref_classroom_types WHERE name = 'SALLE ENS. TECHNO'")).scalar()

        db.execute(text(
            "INSERT INTO classrooms (code, name, capacity, school_id) VALUES ('SCI_GRP', 'Salles science', NULL, :school_id)"
        ), {"school_id": lyc_id})
        db.commit()
        sci_group_id = db.execute(text("SELECT id FROM classrooms WHERE code = 'SCI_GRP'")).scalar()
        _insert_closure_row(sci_group_id, sci_group_id, 0)

        science_subgroups = [
            ("SCI_SVT_GRP", "Labo SVT", "SVT", tp_type_id),
            ("SCI_PHYS_GRP", "Labo Physique", "PHYS", tp_type_id),
            ("SCI_TECHNO_GRP", "Salles techno", "TECHNO", techno_type_id),
        ]
        for group_code, group_name, room_prefix, leaf_type_id in science_subgroups:
            db.execute(text(
                "INSERT INTO classrooms (code, name, capacity, school_id, parent_classroom_id) "
                "VALUES (:code, :name, NULL, :school_id, :parent_id)"
            ), {"code": group_code, "name": group_name, "school_id": lyc_id, "parent_id": sci_group_id})
            db.commit()
            subgroup_id = db.execute(text("SELECT id FROM classrooms WHERE code = :code"), {"code": group_code}).scalar()
            _insert_closure_row(subgroup_id, subgroup_id, 0)
            _insert_closure_row(sci_group_id, subgroup_id, 1)

            for i in range(1, 5):
                db.execute(text(
                    "INSERT INTO classrooms (code, name, capacity, school_id, parent_classroom_id, ref_classroom_type_id) "
                    "VALUES (:code, :name, 30, :school_id, :parent_id, :type_id)"
                ), {
                    "code": f"{room_prefix}{i}", "name": f"{group_name} {i}",
                    "school_id": lyc_id, "parent_id": subgroup_id, "type_id": leaf_type_id,
                })
                db.commit()
                leaf_id = db.execute(text("SELECT id FROM classrooms WHERE code = :code"), {"code": f"{room_prefix}{i}"}).scalar()
                _insert_closure_row(leaf_id, leaf_id, 0)
                _insert_closure_row(subgroup_id, leaf_id, 1)
                _insert_closure_row(sci_group_id, leaf_id, 2)
            db.commit()

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
                t_id = teacher_for_subject(subj_id, s_id, teacher_pool)
                duration = 60

                db.execute(text(
                    "INSERT INTO courses (subject_id, duration_minutes, weighting_coefficient, is_composed, lock_structure, week_type, is_pinned, is_co_teaching, school_id, election_method_id, parent_timeslot_offset) "
                    "VALUES (:subject_id, :duration_minutes, 1.0, 0, 0, 'W', 0, 0, :school_id, :election_method_id, 0)"
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

            # Sélection de 3 professeurs distincts, un par matière du Pôle Sciences (voir
            # teacher_for_subject ci-dessus) : selected_teachers[idx] enseigne complex_subjects[idx]
            # ci-dessous (idx % 3 == idx, les deux listes ont la même longueur) -> cohérent avec sa
            # matière préférée, plutôt qu'un tirage indépendant des 3 matières effectivement affectées.
            selected_teachers = [teacher_for_subject(subject_ids[code], s_id, teacher_pool) for code in complex_subjects]
            # Sélection de 3 salles distinctes (classrooms contient (id, school_id))
            room_pool = [c[0] for c in classrooms if c[1] == s_id]
            selected_rooms = random.sample(room_pool, 3) if len(room_pool) >= 3 else room_pool

            # 2. Cours complexe (Pôle Sciences) - sans matière (NULL)
            db.execute(text(
                "INSERT INTO courses (subject_id, duration_minutes, weighting_coefficient, is_composed, lock_structure, week_type, is_pinned, is_co_teaching, school_id, name, election_method_id, parent_timeslot_offset) "
                "VALUES (NULL, 90, 1.0, 1, 0, 'W', 0, 0, :school_id, 'Pôle Sciences', :election_method_id, 0)"
            ), {"school_id": s_id, "election_method_id": election_method_s_id})
            parent_id = db.execute(text("SELECT last_insert_rowid()")).scalar()
            course_count += 1

            # Affectation des 3 profs, 3 salles et 3 groupes au cours PARENT
            for t_id in selected_teachers:
                db.execute(text("INSERT INTO course_teachers (course_id, teacher_id) VALUES (:c_id, :t_id)"), {"c_id": parent_id, "t_id": t_id})
            for r_id in selected_rooms:
                db.execute(text("INSERT INTO course_classroom_requirements (course_id, classroom_id, quantity) VALUES (:c_id, :r_id, 1)"), {"c_id": parent_id, "r_id": r_id})
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
                    "INSERT INTO courses (subject_id, parent_id, duration_minutes, weighting_coefficient, is_composed, lock_structure, week_type, is_pinned, is_co_teaching, school_id, election_method_id, parent_timeslot_offset) "
                    "VALUES (:subject_id, :parent_id, :duration_minutes, 1.0, 0, 0, 'W', 0, 0, :school_id, :election_method_id, 0)"
                ), {
                    "subject_id": subj_id,
                    "parent_id": parent_id,
                    "duration_minutes": duration,
                    "school_id": s_id,
                    "election_method_id": election_method_s_id
                })
                course_id = db.execute(text("SELECT last_insert_rowid()")).scalar()

                db.execute(text("INSERT INTO course_teachers (course_id, teacher_id) VALUES (:course_id, :teacher_id)"), {"course_id": course_id, "teacher_id": t_id})
                db.execute(text("INSERT INTO course_classroom_requirements (course_id, classroom_id, quantity) VALUES (:course_id, :r_id, 1)"), {"course_id": course_id, "r_id": r_id})
                db.execute(text("INSERT INTO course_groups (course_id, group_id) VALUES (:course_id, :g_id)"), {"course_id": course_id, "g_id": g_id})

            # 4. Cours alternés (Semaine A / Semaine B)
            # Ajout d'Arts Plastiques en Semaine A, et Anglais en Semaine B
            for s_code, w_type in [("ARTS", "A"), ("ANG", "B")]:
                subj_id = subject_ids[s_code]
                t_id = teacher_for_subject(subj_id, s_id, teacher_pool)

                db.execute(text(
                    "INSERT INTO courses (subject_id, duration_minutes, weighting_coefficient, is_composed, lock_structure, week_type, is_pinned, is_co_teaching, school_id, election_method_id, parent_timeslot_offset) "
                    "VALUES (:subject_id, 60, 1.0, 0, 0, :week_type, 0, 0, :school_id, :election_method_id, 0)"
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

        # 14. Compte de connexion locale de démonstration (voir architecture.md, provider "local")
        # — identifiants en clair UNIQUEMENT ici, dans un jeu de démo : le hash Argon2id est
        # calculé au moment du seed (comme tout champ calculé-et-stocké inséré en SQL brut, voir
        # architecture.md section F), jamais stocké en clair en base.
        # Mot de passe conforme à la politique de robustesse (UserIdentityProvider.
        # _validate_password_strength, models/user.py — 8 car. min + 3 des 4 catégories) : ce seed
        # contourne le validateur (hash calculé directement, comme tout champ calculé-et-stocké
        # inséré en SQL brut), mais un mot de passe de démo qu'aucun vrai formulaire ne laisserait
        # poser serait un exemple trompeur.
        print("[SEED DEMO] Ajout du compte de connexion locale de démonstration (demo@klepsydrix.fr / Demo1234!)...")
        db.execute(text("INSERT INTO users (first_name, last_name, email, active) VALUES ('Démo', 'Klepsydrix', 'demo@klepsydrix.fr', true)"))
        db.commit()
        demo_user_id = db.execute(text("SELECT id FROM users WHERE email = 'demo@klepsydrix.fr'")).scalar()
        password_hash = PasswordHasher().hash("Demo1234!")
        db.execute(text(
            "INSERT INTO user_identity_providers (user_id, provider_key, external_subject, password_hash) "
            "VALUES (:user_id, 'local', 'demo@klepsydrix.fr', :password_hash)"
        ), {"user_id": demo_user_id, "password_hash": password_hash})
        # Membre du groupe "Admin" (créé par seed_admin_access(), voir init_prod_data() appelé en
        # tout début de cette fonction) — sans ça, le compte de démo n'aurait plus aucun accès dès
        # que le moteur de droits est actif (aucune ligne ir_model_access sans groupe).
        admin_group_id = db.execute(text("SELECT id FROM res_groups WHERE name = 'Admin'")).scalar()
        db.execute(text("INSERT INTO res_group_users (group_id, user_id) VALUES (:group_id, :user_id)"), {"group_id": admin_group_id, "user_id": demo_user_id})
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
