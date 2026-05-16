from backend.app.core.database import engine, SessionLocal
from backend.app.models.base import Base
from backend.app.models.teacher import Teacher
from backend.app.models.classroom import Classroom
from backend.app.models.division import Division
from backend.app.models.timeslot import Timeslot
from backend.app.models.course import Course

def init_db():
    # Suppression et recréation de toutes les tables pour repartir sur une base propre
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 1. Insertion des Créneaux Temporels (Lundi index 1 au Samedi index 6, de 8h à 17h)
        timeslots = []
        for day in range(1, 7): # 1=Lundi, 2=Mardi, 3=Mercredi, 4=Jeudi, 5=Vendredi, 6=Samedi
            for hour in range(8, 18): # Séquences d'une heure de 8h à 17h inclus (17h représente le créneau 17h-18h)
                ts = Timeslot(day_of_week=day, hour=hour)
                db.add(ts)
                timeslots.append(ts)
        
        # 2. Insertion des Enseignants (10 enseignants)
        teachers_data = [
            "M. Martin", "Mme Bernard", "M. Dubois", "Mme Thomas", "M. Robert",
            "Mme Richard", "M. Petit", "Mme Durand", "M. Leroy", "Mme Moreau"
        ]
        teachers = []
        for name in teachers_data:
            t = Teacher(name=name)
            db.add(t)
            teachers.append(t)

        # 3. Insertion des Divisions (5 classes d'élèves)
        divisions_data = ["6ème A", "5ème A", "4ème A", "3ème A", "2nde A"]
        divisions = []
        for name in divisions_data:
            div = Division(name=name)
            db.add(div)
            divisions.append(div)

        # 4. Insertion des Salles de Classe (5 salles)
        classrooms_data = [
            ("Salle 101", 30),
            ("Salle 102", 30),
            ("Salle 103", 35),
            ("Salle 104", 35),
            ("Salle 105", 40)
        ]
        classrooms = []
        for name, capacity in classrooms_data:
            c = Classroom(name=name, capacity=capacity)
            db.add(c)
            classrooms.append(c)

        db.commit() # Committer les entités de base pour obtenir leurs IDs générés

        # 5. Insertion de 30 Cours Individuels non placés (timeslot_id et classroom_id à NULL)
        # Chaque cours relie une matière, un enseignant et une classe (division)
        courses_data = [
            # 6ème A (6 cours)
            ("Mathématiques", "M. Martin", "6ème A"),
            ("Français", "Mme Bernard", "6ème A"),
            ("Histoire-Géo", "M. Dubois", "6ème A"),
            ("Sciences", "Mme Thomas", "6ème A"),
            ("Anglais", "M. Robert", "6ème A"),
            ("Arts Plastiques", "Mme Richard", "6ème A"),

            # 5ème A (6 cours)
            ("Mathématiques", "M. Martin", "5ème A"),
            ("Français", "Mme Bernard", "5ème A"),
            ("Histoire-Géo", "M. Dubois", "5ème A"),
            ("Sciences", "Mme Thomas", "5ème A"),
            ("Anglais", "M. Robert", "5ème A"),
            ("Musique", "M. Petit", "5ème A"),

            # 4ème A (6 cours)
            ("Mathématiques", "M. Leroy", "4ème A"),
            ("Français", "Mme Moreau", "4ème A"),
            ("Histoire-Géo", "Mme Durand", "4ème A"),
            ("Sciences", "Mme Thomas", "4ème A"),
            ("Anglais", "M. Robert", "4ème A"),
            ("Technologie", "Mme Richard", "4ème A"),

            # 3ème A (6 cours)
            ("Mathématiques", "M. Leroy", "3ème A"),
            ("Français", "Mme Moreau", "3ème A"),
            ("Histoire-Géo", "Mme Durand", "3ème A"),
            ("Sciences", "M. Martin", "3ème A"),
            ("Anglais", "Mme Bernard", "3ème A"),
            ("E.P.S.", "M. Petit", "3ème A"),

            # 2nde A (6 cours)
            ("Mathématiques", "M. Leroy", "2nde A"),
            ("Français", "Mme Moreau", "2nde A"),
            ("Histoire-Géo", "Mme Durand", "2nde A"),
            ("Physique-Chimie", "M. Martin", "2nde A"),
            ("Anglais", "Mme Bernard", "2nde A"),
            ("S.V.T.", "Mme Thomas", "2nde A"),
        ]

        # Résoudre les correspondances de noms pour obtenir les clés étrangères
        for subject, t_name, div_name in courses_data:
            teacher_obj = next(t for t in teachers if t.name == t_name)
            division_obj = next(d for d in divisions if d.name == div_name)
            
            c = Course(
                subject=subject,
                teacher_id=teacher_obj.id,
                division_id=division_obj.id,
                classroom_id=None, # Non planifié
                timeslot_id=None   # Non planifié
            )
            db.add(c)

        db.commit()
        print("[OK] Base de données initialisée avec succès avec le jeu d'essai V1.")

    except Exception as e:
        db.rollback()
        print(f"[ERREUR] Échec de l'initialisation de la base : {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
