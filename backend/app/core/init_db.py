import argparse
import sys
import random
from datetime import date
from sqlalchemy import text
from backend.app.core.database import engine, SessionLocal

def seed_v2_data():
    """
    Remplir la base avec un jeu d'essai V2 multi-établissement complet et réaliste.
    """
    print("[SEED V2] Initialisation de la base de données avec le jeu d'essai V2...")
    from backend.app.models.base import Base
    import backend.app.models
    
    # 1. Recréer toutes les tables pour repartir à blanc
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # 2. Création des Établissements de la Cité Scolaire
        db.execute(text("INSERT INTO schools (uai, name, student_start_date, student_end_date) VALUES ('0750001A', 'Collège Jean Jaurès', '2026-09-01', '2027-06-30')"))
        db.execute(text("INSERT INTO schools (uai, name, student_start_date, student_end_date) VALUES ('0750002B', 'Lycée Jean Jaurès', '2026-09-01', '2027-06-30')"))
        db.commit()

        # Seed global system settings
        db.execute(text("INSERT INTO system_settings (key, value) VALUES ('STANDARD_TIMESLOT_DURATION', '30')"))
        db.commit()
        
        clg_id = db.execute(text("SELECT id FROM schools WHERE uai = '0750001A'")).scalar()
        lyc_id = db.execute(text("SELECT id FROM schools WHERE uai = '0750002B'")).scalar()
        
        # 3. Création des Disciplines nationales
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
            
        # 4. Création des Budgets TRMD pour les deux écoles
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

        # 5. Création des Matières (Subjects)
        subjects_data = [
            ("MATHS", "006600", "Maths", "Mathématiques", "#3498DB", "L0100"),
            ("FRAN", "004300", "Français", "Lettres Modernes", "#E74C3C", "L0200"),
            ("HG", "003200", "Hist-Géo", "Histoire-Géographie", "#F1C40F", "L0420"),
            ("PC", "005500", "Phys-Chimie", "Sciences Physiques", "#9B59B6", "L1500"),
            ("SVT", "005600", "SVT", "Sciences de la Vie et de la Terre", "#2ECC71", "L1600"),
            ("ANG", "002200", "Anglais", "Langue Vivante : Anglais", "#E67E22", "L0400"),
            ("ARTS", "001100", "Arts Plast.", "Arts Plastiques", "#1ABC9C", "L1800"),
            ("EPS", "009900", "EPS", "Éducation Physique et Sportive", "#34495E", "L1900"),
            ("TECHNO", "008800", "Techno", "Technologie", "#7F8C8D", "L1400")
        ]
        subject_ids = {}
        for code, nomenclature, short, long, color, d_code in subjects_data:
            db.execute(text(
                "INSERT INTO subjects (code, code_nomenclature, short_label, long_label, color, is_etp, is_specialty, pedagogic_weight, discipline_id) "
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

        # 6. Création des MEFs (2 pour collège, 2 pour lycée)
        db.execute(text("INSERT INTO mefs (school_id, code_national, label, forecast_student_count, max_students_per_class) VALUES (:school_id, '10010012110', '6EME GENERALE', 120, 30)"), {"school_id": clg_id})
        db.execute(text("INSERT INTO mefs (school_id, code_national, label, forecast_student_count, max_students_per_class) VALUES (:school_id, '10010012111', '5EME GENERALE', 115, 30)"), {"school_id": clg_id})
        db.execute(text("INSERT INTO mefs (school_id, code_national, label, forecast_student_count, max_students_per_class) VALUES (:school_id, '20010012110', '2NDE GENERALE', 150, 35)"), {"school_id": lyc_id})
        db.execute(text("INSERT INTO mefs (school_id, code_national, label, forecast_student_count, max_students_per_class) VALUES (:school_id, '20010012111', '1ERE GENERALE', 140, 35)"), {"school_id": lyc_id})
        db.commit()
        
        mef_6_id = db.execute(text("SELECT id FROM mefs WHERE code_national = '10010012110'")).scalar()
        mef_2_id = db.execute(text("SELECT id FROM mefs WHERE code_national = '20010012110'")).scalar()

        # 7. Création des Créneaux Temporels (Lundi index 1 au Samedi index 6, de 8h à 18h, pas de 15 minutes = 0.25h)
        timeslots = []
        for day in range(1, 7):
            h_val = 8.0
            while h_val < 18.0:
                db.execute(text("INSERT INTO timeslots (day_of_week, hour) VALUES (:day, :hour)"), {"day": day, "hour": h_val})
                db.commit()
                ts_id = db.execute(text("SELECT id FROM timeslots WHERE day_of_week = :day AND hour = :hour"), {"day": day, "hour": h_val}).scalar()
                timeslots.append(ts_id)
                h_val += 0.25

        # 8. Saisie des period_types, périodes temporelles (Semestres) et Alternances (Semaines A/B)
        db.execute(text("INSERT INTO period_types (label) VALUES ('Trimestre')"))
        db.execute(text("INSERT INTO period_types (label) VALUES ('Semestre')"))
        db.commit()

        sem_type_id = db.execute(text("SELECT id FROM period_types WHERE label = 'Semestre'")).scalar()

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

        # 9. Création des Enseignants (40 profs : 20 collège, 20 lycée)
        teachers = []
        for i in range(1, 41):
            school_idx = clg_id if i <= 20 else lyc_id
            first_name = "Prof"
            last_name = f"Teacher_{i}"
            code = f"T{i}"
            name = f"M. {last_name}"
            db.execute(text(
                "INSERT INTO teachers (code, first_name, last_name, name, max_weekly_hours, school_id) "
                "VALUES (:code, :first_name, :last_name, :name, 18.0, :school_id)"
            ), {"code": code, "first_name": first_name, "last_name": last_name, "name": name, "school_id": school_idx})
            db.commit()
            t_id = db.execute(text("SELECT id FROM teachers WHERE code = :code"), {"code": code}).scalar()
            teachers.append((t_id, school_idx))

        # 9b. Création de personnel non enseignant (AESH, Labo, etc.)
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

        # 10. Insérer des préférences (ResourcePreference) de test pour quelques professeurs (vœux)
        # Prof 1 et 21 n'aiment pas travailler le mercredi matin (timeslot du mercredi 8h, day_of_week = 3, hour = 8)
        mercredi_8h_ts = db.execute(text("SELECT id FROM timeslots WHERE day_of_week = 3 AND hour = 8")).scalar()
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

        # 11. Création des Divisions (Classes d'élèves) : 3 pour Collège, 3 pour Lycée
        clg_divisions_data = ["6ème A", "6ème B", "5ème A"]
        lyc_divisions_data = ["2nde A", "2nde B", "1ère A"]
        divisions = []
        
        for name in clg_divisions_data:
            code = name.replace("è", "E").replace(" ", "_").upper()
            db.execute(text(
                "INSERT INTO divisions (code, name, student_count, color, school_id, mef_id) "
                "VALUES (:code, :name, 28, '#3498DB', :school_id, :mef_id)"
            ), {"code": code, "name": name, "school_id": clg_id, "mef_id": mef_6_id})
            db.commit()
            d_id = db.execute(text("SELECT id FROM divisions WHERE code = :code"), {"code": code}).scalar()
            divisions.append((d_id, clg_id))

        for name in lyc_divisions_data:
            code = name.replace("è", "E").replace(" ", "_").upper()
            db.execute(text(
                "INSERT INTO divisions (code, name, student_count, color, school_id, mef_id) "
                "VALUES (:code, :name, 32, '#E74C3C', :school_id, :mef_id)"
            ), {"code": code, "name": name, "school_id": lyc_id, "mef_id": mef_2_id})
            db.commit()
            d_id = db.execute(text("SELECT id FROM divisions WHERE code = :code"), {"code": code}).scalar()
            divisions.append((d_id, lyc_id))

        # 12. Création des Salles de Classe (10 salles)
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

        # 13. Création d'une suite de cours & sessions (simple / complexes / co-enseignements)
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
                duration = 55
                
                db.execute(text(
                    "INSERT INTO courses (subject_id, duration_minutes, is_composed, lock_structure, week_type, is_pinned, is_co_teaching, school_id, parent_timeslot_offset) "
                    "VALUES (:subject_id, :duration_minutes, 0, 0, 'W', 0, 0, :school_id, 0)"
                ), {
                    "subject_id": subj_id,
                    "duration_minutes": duration,
                    "school_id": s_id
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
            db.execute(text("INSERT INTO partitions (code, name, division_id) VALUES ('SCI', 'Groupes Sciences', :division_id)"), {"division_id": d_id})
            part_id = db.execute(text("SELECT last_insert_rowid()")).scalar()
            
            # 2. ClassParts & Groups (3 groupes)
            div_groups = []
            for g_idx in range(1, 4):
                cp_code = f"{d_id}_SCI_G{g_idx}"
                db.execute(text(
                    "INSERT INTO class_parts (division_id, partition_id, code, name, student_count, color) "
                    "VALUES (:div_id, :part_id, :code, :name, 10, '#CCCCCC')"
                ), {"div_id": d_id, "part_id": part_id, "code": cp_code, "name": f"Groupe {g_idx}"})
                cp_id = db.execute(text("SELECT last_insert_rowid()")).scalar()
                
                grp_code = f"GRP_{cp_code}"
                db.execute(text(
                    "INSERT INTO groups (code, name, student_count, color, is_variable_size) VALUES (:code, :name, 10, '#CCCCCC', 0)"
                ), {"code": grp_code, "name": f"Groupe Sciences {g_idx}"})
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
                "INSERT INTO courses (subject_id, duration_minutes, is_composed, lock_structure, week_type, is_pinned, is_co_teaching, school_id, label, parent_timeslot_offset) "
                "VALUES (NULL, 90, 1, 0, 'W', 0, 0, :school_id, 'Pôle Sciences', 0)"
            ), {"school_id": s_id})
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
                    "INSERT INTO courses (subject_id, parent_id, duration_minutes, is_composed, lock_structure, week_type, is_pinned, is_co_teaching, school_id, parent_timeslot_offset) "
                    "VALUES (:subject_id, :parent_id, :duration_minutes, 0, 0, 'W', 0, 0, :school_id, 0)"
                ), {
                    "subject_id": subj_id,
                    "parent_id": parent_id,
                    "duration_minutes": duration,
                    "school_id": s_id
                })
                course_id = db.execute(text("SELECT last_insert_rowid()")).scalar()
                
                db.execute(text("INSERT INTO course_teachers (course_id, teacher_id) VALUES (:course_id, :teacher_id)"), {"course_id": course_id, "teacher_id": t_id})
                db.execute(text("INSERT INTO course_classrooms (course_id, classroom_id) VALUES (:course_id, :r_id)"), {"course_id": course_id, "r_id": r_id})
                db.execute(text("INSERT INTO course_groups (course_id, group_id) VALUES (:course_id, :g_id)"), {"course_id": course_id, "g_id": g_id})
                # Ne pas associer directement toute la division au sous-cours, il n'a qu'un groupe.
                # db.execute(text("INSERT INTO course_divisions (course_id, division_id) VALUES (:course_id, :division_id)"), {"course_id": course_id, "division_id": d_id})
                
                course_count += 1
                
        db.commit()
        print(f"[SEED V2] Succès ! Jeu d'essai V2 généré avec : 2 établissements, 9 disciplines, 9 matières, 40 profs, {len(divisions)} divisions, {len(classrooms)} salles et {course_count} cours/séances.")
        
    except Exception as e:
        db.rollback()
        print(f"[SEED V2 ERREUR] Échec de la génération du jeu d'essai V2 : {e}")
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gestion de la Base de Données SQLite Klepsydrix V2 (Initialisation et Seeding)")
    parser.add_argument("--init-db", action="store_true", help="Vide la base et réinitialise les tables.")
    parser.add_argument("--seed-v2", action="store_true", help="Injecte le jeu d'essai complet de validation V2.")
    
    args = parser.parse_args()
    
    # Par défaut, si lancé sans argument, on fait l'initialisation et le seed
    if len(sys.argv) == 1:
        seed_v2_data()
    elif args.init_db or args.seed_v2:
        seed_v2_data()
    else:
        parser.print_help()
