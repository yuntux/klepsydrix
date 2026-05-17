import sys
import argparse
import os
import random
from datetime import date
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from backend.app.core.config import settings

# Configuration spéciale pour SQLite afin de supporter le multithreading asynchrone
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Fonction utilitaire de récupération de session de base de données
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def apply_migrations():
    """
    Migration transactionnelle et robuste de V1 vers V2 pour SQLite.
    """
    print("[MIGRATION] Analyse de la base de données existante...")
    
    # 1. Vérifier l'état actuel de la base
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    if not existing_tables:
        print("[MIGRATION] Base vide détectée. Création directe du schéma V2.")
        from backend.app.models.base import Base
        # Importer tous les modèles pour qu'ils soient enregistrés
        import backend.app.models
        Base.metadata.create_all(bind=engine)
        print("[MIGRATION] Schéma V2 créé avec succès.")
        return

    # Si la table schools existe déjà, la base est déjà en V2
    if "schools" in existing_tables:
        print("[MIGRATION] La base de données est déjà en version V2. Aucune migration requise.")
        return

    # Si on a la table courses de la V1
    if "courses" not in existing_tables:
        print("[MIGRATION] Structure de base inconnue. Création du schéma V2 par défaut.")
        from backend.app.models.base import Base
        import backend.app.models
        Base.metadata.create_all(bind=engine)
        return

    print("[MIGRATION] Base de données V1 détectée. Début de la migration vers la V2...")
    
    db = SessionLocal()
    try:
        # 1. Lire toutes les données de la V1 avant de détruire le schéma
        old_teachers = db.execute(text("SELECT id, name FROM teachers")).fetchall()
        old_classrooms = db.execute(text("SELECT id, name, capacity FROM classrooms")).fetchall()
        old_divisions = db.execute(text("SELECT id, name FROM divisions")).fetchall()
        old_timeslots = db.execute(text("SELECT id, day_of_week, hour FROM timeslots")).fetchall()
        old_courses = db.execute(text("SELECT id, subject, is_pinned, teacher_id, division_id, classroom_id, timeslot_id FROM courses")).fetchall()
        
        print(f"[MIGRATION] Extraction terminée : {len(old_teachers)} profs, {len(old_classrooms)} salles, {len(old_divisions)} classes, {len(old_courses)} cours.")
        
        # 2. Supprimer les anciennes tables
        db.execute(text("DROP TABLE IF EXISTS courses"))
        db.execute(text("DROP TABLE IF EXISTS classrooms"))
        db.execute(text("DROP TABLE IF EXISTS divisions"))
        db.execute(text("DROP TABLE IF EXISTS teachers"))
        db.execute(text("DROP TABLE IF EXISTS timeslots"))
        db.commit()
        
        # 3. Créer toutes les tables du schéma V2
        from backend.app.models.base import Base
        import backend.app.models
        Base.metadata.create_all(bind=engine)
        print("[MIGRATION] Nouveau schéma V2 créé.")

        # 4. Insérer l'Établissement par défaut
        db.execute(text(
            "INSERT INTO schools (uai, name, standard_timeslot_duration) "
            "VALUES ('0000000X', 'Établissement Pilote', 30)"
        ))
        db.commit()
        school_id = db.execute(text("SELECT id FROM schools WHERE uai = '0000000X'")).scalar()
        
        # 5. Insérer la Discipline par défaut
        db.execute(text("INSERT INTO disciplines (code, name) VALUES ('GEN', 'Enseignement Général')"))
        db.commit()
        discipline_id = db.execute(text("SELECT id FROM disciplines WHERE code = 'GEN'")).scalar()
        
        # 6. Migrer les créneaux horaires
        for ts in old_timeslots:
            db.execute(text(
                "INSERT INTO timeslots (id, day_of_week, hour) "
                "VALUES (:id, :day_of_week, :hour)"
            ), {"id": ts.id, "day_of_week": ts.day_of_week, "hour": ts.hour})
        
        # 7. Migrer les enseignants
        # Format de nom V1 : "M. Martin" -> first_name "M.", last_name "Martin", code "MARTIN.M"
        for t in old_teachers:
            parts = t.name.split(" ", 1)
            first_name = parts[0] if len(parts) > 1 else ""
            last_name = parts[1] if len(parts) > 1 else parts[0]
            code = f"{last_name.upper()}.{first_name[0]}" if first_name else last_name.upper()
            
            db.execute(text(
                "INSERT INTO teachers (id, code, first_name, last_name, name, max_weekly_hours, school_id) "
                "VALUES (:id, :code, :first_name, :last_name, :name, 18.0, :school_id)"
            ), {
                "id": t.id,
                "code": code,
                "first_name": first_name,
                "last_name": last_name,
                "name": t.name,
                "school_id": school_id
            })

        # 8. Migrer les classes (divisions)
        # Nettoyer "6ème A" -> "6EME_A"
        for d in old_divisions:
            code = d.name.replace("è", "E").replace(" ", "_").upper()
            db.execute(text(
                "INSERT INTO divisions (id, code, name, student_count, color, school_id) "
                "VALUES (:id, :code, :name, 25, '#CCCCCC', :school_id)"
            ), {
                "id": d.id,
                "code": code,
                "name": d.name,
                "school_id": school_id
            })

        # 9. Migrer les salles de classe
        for c in old_classrooms:
            code = c.name.replace(" ", "_").upper()
            db.execute(text(
                "INSERT INTO classrooms (id, code, name, capacity, quantity, school_id) "
                "VALUES (:id, :code, :name, :capacity, 1, :school_id)"
            ), {
                "id": c.id,
                "code": code,
                "name": c.name,
                "capacity": c.capacity,
                "school_id": school_id
            })

        db.commit()

        # 10. Extraire et insérer les matières uniques à partir de la table courses V1
        subjects_set = set(c.subject for c in old_courses)
        subject_mapping = {}
        for s_name in subjects_set:
            code = s_name.replace("è", "E").replace("é", "E").replace("-", "_").replace(" ", "_").upper()[:15]
            code_nomenclature = f"NOM_{code}"
            
            db.execute(text(
                "INSERT INTO subjects (code, code_nomenclature, short_label, long_label, color, is_etp, is_specialty, pedagogic_weight, discipline_id) "
                "VALUES (:code, :code_nomenclature, :short, :long, '#CCCCCC', 1, 0, 1.0, :discipline_id)"
            ), {
                "code": code,
                "code_nomenclature": code_nomenclature,
                "short": s_name[:30],
                "long": s_name,
                "discipline_id": discipline_id
            })
            db.commit()
            
            s_id = db.execute(text("SELECT id FROM subjects WHERE code = :code"), {"code": code}).scalar()
            subject_mapping[s_name] = s_id

        # 11. Migrer les cours (split Course + Session)
        for c in old_courses:
            subject_id = subject_mapping[c.subject]
            
            db.execute(text(
                "INSERT INTO courses (id, subject_id, teacher_id, division_id, duration_minutes, is_complex, lock_sessions, school_id) "
                "VALUES (:id, :subject_id, :teacher_id, :division_id, 55, 0, 0, :school_id)"
            ), {
                "id": c.id,
                "subject_id": subject_id,
                "teacher_id": c.teacher_id,
                "division_id": c.division_id,
                "school_id": school_id
            })
            db.commit()

            # Créer la session correspondante
            db.execute(text(
                "INSERT INTO sessions (course_id, timeslot_id, classroom_id, week_type, is_pinned, is_co_teaching, school_id) "
                "VALUES (:course_id, :timeslot_id, :classroom_id, 'T', :is_pinned, 0, :school_id)"
            ), {
                "course_id": c.id,
                "timeslot_id": c.timeslot_id,
                "classroom_id": c.classroom_id,
                "is_pinned": 1 if c.is_pinned else 0,
                "school_id": school_id
            })

        db.commit()
        print("[MIGRATION] Migration de V1 vers V2 effectuée avec succès !")
        
    except Exception as e:
        db.rollback()
        print(f"[ERREUR MIGRATION] Échec : {e}")
        raise e
    finally:
        db.close()


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
        db.execute(text("INSERT INTO schools (uai, name, standard_timeslot_duration) VALUES ('0750001A', 'Collège Jean Jaurès', 30)"))
        db.execute(text("INSERT INTO schools (uai, name, standard_timeslot_duration) VALUES ('0750002B', 'Lycée Jean Jaurès', 30)"))
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

        # 7. Création des Créneaux Temporels (Lundi index 1 au Samedi index 6, de 8h à 17h)
        timeslots = []
        for day in range(1, 7):
            for hour in range(8, 18):
                db.execute(text("INSERT INTO timeslots (day_of_week, hour) VALUES (:day, :hour)"), {"day": day, "hour": hour})
                db.commit()
                ts_id = db.execute(text("SELECT id FROM timeslots WHERE day_of_week = :day AND hour = :hour"), {"day": day, "hour": hour}).scalar()
                timeslots.append(ts_id)

        # 8. Saisie des périodes temporelles (Semestres) et Alternances (Semaines A/B)
        db.execute(text("INSERT INTO periods (code, name, start_date, end_date) VALUES ('S1', 'Semestre 1', '2026-09-01', '2027-01-31')"))
        db.execute(text("INSERT INTO periods (code, name, start_date, end_date) VALUES ('S2', 'Semestre 2', '2027-02-01', '2027-06-30')"))
        db.execute(text("INSERT INTO alternations (code, name, color) VALUES ('WEEK_A', 'Semaine A', '#3498DB')"))
        db.execute(text("INSERT INTO alternations (code, name, color) VALUES ('WEEK_B', 'Semaine B', '#E74C3C')"))
        db.execute(text("INSERT INTO alternations (code, name, color) VALUES ('HEBDO', 'Hebdomadaire', '#2ECC71')"))
        db.commit()

        s1_id = db.execute(text("SELECT id FROM periods WHERE code = 'S1'")).scalar()
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

        # 10. Insérer des préférences (ResourcePreference) de test pour quelques professeurs (vœux)
        # Prof 1 et 21 n'aiment pas travailler le mercredi matin (timeslot du mercredi 8h, day_of_week = 3, hour = 8)
        mercredi_8h_ts = db.execute(text("SELECT id FROM timeslots WHERE day_of_week = 3 AND hour = 8")).scalar()
        if mercredi_8h_ts:
            for t_id, s_id in [teachers[0], teachers[20]]:
                db.execute(text(
                    "INSERT INTO resource_preferences (resource_type, resource_id, timeslot_id, preference_level) "
                    "VALUES ('Teacher', :resource_id, :timeslot_id, 'Unsuited')"
                ), {"resource_id": t_id, "timeslot_id": mercredi_8h_ts})
                db.commit()
                pref_id = db.execute(text("SELECT id FROM resource_preferences WHERE resource_type = 'Teacher' AND resource_id = :resource_id"), {"resource_id": t_id}).scalar()
                
                # Liaison Période S1 et Alternance A
                db.execute(text("INSERT INTO preference_periods (preference_id, period_id) VALUES (:pref_id, :s_id)"), {"pref_id": pref_id, "s_id": s1_id})
                db.execute(text("INSERT INTO preference_alternations (preference_id, alternation_id) VALUES (:pref_id, :alt_id)"), {"pref_id": pref_id, "alt_id": week_a_id})
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
            # Matières : Maths (MATHS), Français (FRAN), Hist-Géo (HG), Sciences (PC ou SVT)
            selected_subjects = ["MATHS", "FRAN", "HG"]
            if s_id == clg_id:
                selected_subjects.append("TECHNO")
                # Associer des enseignants du collège (index 1 à 20)
                teacher_pool = [t[0] for t in teachers if t[1] == clg_id]
            else:
                selected_subjects.append("PC")
                # Associer des enseignants du lycée (index 21 à 40)
                teacher_pool = [t[0] for t in teachers if t[1] == lyc_id]

            for s_code in selected_subjects:
                subj_id = subject_ids[s_code]
                t_id = random.choice(teacher_pool)
                
                db.execute(text(
                    "INSERT INTO courses (subject_id, teacher_id, division_id, duration_minutes, is_complex, lock_sessions, school_id) "
                    "VALUES (:subject_id, :teacher_id, :division_id, 55, 0, 0, :school_id)"
                ), {"subject_id": subj_id, "teacher_id": t_id, "division_id": d_id, "school_id": s_id})
                db.commit()
                
                course_id = db.execute(text("SELECT last_insert_rowid()")).scalar()
                
                # Créer une séance non placée par défaut
                db.execute(text(
                    "INSERT INTO sessions (course_id, timeslot_id, classroom_id, week_type, is_pinned, is_co_teaching, school_id) "
                    "VALUES (:course_id, NULL, NULL, 'T', 0, 0, :school_id)"
                ), {"course_id": course_id, "school_id": s_id})
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
    parser = argparse.ArgumentParser(description="Gestion de la Base de Données SQLite Klepsydrix V2")
    parser.add_argument("--apply-migrations", action="store_true", help="Applique les migrations V1 -> V2 sur la base existante.")
    parser.add_argument("--init-db", action="store_true", help="Vide la base et réinitialise les tables.")
    parser.add_argument("--seed-v2", action="store_true", help="Injecte le jeu d'essai complet de validation V2.")
    
    args = parser.parse_args()
    
    if args.apply_migrations:
        apply_migrations()
    elif args.init_db or args.seed_v2:
        # Si on demande l'init ou le seed
        seed_v2_data()
    else:
        # Par défaut sans argument, affiche l'aide
        parser.print_help()
