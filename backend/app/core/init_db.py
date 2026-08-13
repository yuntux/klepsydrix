import argparse
from sqlalchemy import text
from backend.app.core.database import engine, SessionLocal


def init_prod_data():
    """
    Initialise le schéma et les données de référence communes à TOUTE base de production
    Klepsydrix : réglages système globaux (system_settings) et tables de référence RH en texte
    libre (ref_*). Aucune donnée d'établissement, de matière, d'enseignant ou de cours ici —
    c'est un socle générique, valable pour n'importe quel établissement réel. Le jeu d'essai de
    démonstration (backend/app/core/init_demo.py) appelle cette fonction en premier, avant
    d'ajouter par-dessus tout son propre contenu.
    """
    print("[INIT DB] Initialisation du schéma et des données de référence de production...")
    from backend.app.models.base import Base
    import backend.app.models

    # Recréer toutes les tables pour repartir à blanc
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Réglages système globaux
        db.execute(text("INSERT INTO system_settings (key, value) VALUES ('STANDARD_TIMESLOT_DURATION', '30')"))
        # Nommage automatique des parties de classe et des groupes générés lors de la composition
        # de cours (voir CompositionModes._compute_class_part_name / _compute_group_name)
        for setting_key, setting_value in [
            ('DIVISION_PART_NAME_HAS_DIV_CODE', 'true'),
            ('DIVISION_PART_NAME_HAS_SUBJECT_CODE', 'true'),
            ('DIVISION_PART_NAME_SEPARATOR', 'P'),
            ('DIVISION_PART_NAME_NUMBER_FORMAT', 'numerique'),
            ('GROUP_NAME_HAS_DIV_CODE', 'true'),
            ('GROUP_NAME_HAS_SUBJECT_CODE', 'true'),
            ('GROUP_NAME_SEPARATOR', 'G'),
            ('GROUP_NAME_NUMBER_FORMAT', 'numerique'),
            ('MUTUALIZE_REDUCED_GROUPS_WITHOUT_ALIGNMENT', 'false'),
        ]:
            db.execute(text("INSERT INTO system_settings (key, value) VALUES (:key, :value)"), {"key": setting_key, "value": setting_value})
        db.commit()

        # Tables de référence RH (fiche enseignant) — simples listes en texte libre. ref_country,
        # ref_inspector, ref_support, ref_ara, ref_are, ref_particular_mission, ref_pacte_mission,
        # ref_external_school, ref_city sont volontairement créées vides (aucune valeur de seed
        # demandée) : seules les tables ci-dessous ont un contenu initial connu.
        ref_titles_data = ["Monsieur", "Madame"]
        for name in ref_titles_data:
            db.execute(text("INSERT INTO ref_titles (name) VALUES (:name)"), {"name": name})

        ref_degrees_data = [
            "CAP, BEP",
            "Baccalauréat, BP",
            "DEUG, BTS, DUT, DEUST",
            "Licence, licence professionnelle, BUT",
            "Maîtrise",
            "Master, diplôme d'études approfondies, diplôme d'études supérieures spécialisées, diplôme d'ingénieur",
            "Doctorat, habilitation à diriger des recherches",
        ]
        for name in ref_degrees_data:
            db.execute(text("INSERT INTO ref_degrees (name) VALUES (:name)"), {"name": name})

        ref_administrative_groups_data = [
            "Professeurs certifiés",
            "Professeurs d’éducation physique et sportive (PEPS)",
            "Professeurs de lycée professionnel (PLP)",
            "Professeurs agrégés",
            "Professeurs de chaire supérieure",
        ]
        for name in ref_administrative_groups_data:
            db.execute(text("INSERT INTO ref_administrative_groups (name) VALUES (:name)"), {"name": name})

        ref_levels_data = ["Classe Normale", "Hors Classe", "Classe exceptionnelle"]
        for name in ref_levels_data:
            db.execute(text("INSERT INTO ref_levels (name) VALUES (:name)"), {"name": name})

        ref_affectation_modes_data = ["Poste définitif", "Réaffectation carte", "Remplacement"]
        for name in ref_affectation_modes_data:
            db.execute(text("INSERT INTO ref_affectation_modes (name) VALUES (:name)"), {"name": name})

        ref_service_modes_data = ["Mi-temps", "Temps partiel", "Temps plein"]
        for name in ref_service_modes_data:
            db.execute(text("INSERT INTO ref_service_modes (name) VALUES (:name)"), {"name": name})

        ref_functions_data = ["Enseignant", "Direction", "Documentaliste", "Surveillant"]
        for name in ref_functions_data:
            db.execute(text("INSERT INTO ref_functions (name) VALUES (:name)"), {"name": name})

        ref_support_types_data = ["Principal", "Secondaire", "Gelé"]
        for name in ref_support_types_data:
            db.execute(text("INSERT INTO ref_support_types (name) VALUES (:name)"), {"name": name})

        # Niveaux de formation (RefGrade) — nomenclature nationale, présente dans TOUTE base de
        # production (contrairement aux tables ref_* ci-dessus, laissées vides) : frontière de
        # mutualisation de l'effectif réduit entre Service de MEF différents (voir
        # Service._reduced_pool_services, spec.md « Mutualisation de l'effectif réduit »).
        ref_grades_data = ["6EME", "5EME", "4EME", "3EME", "2NDE", "1ERE", "TERMINALE"]
        for name in ref_grades_data:
            db.execute(text("INSERT INTO ref_grades (name) VALUES (:name)"), {"name": name})

        db.commit()
        print("[INIT DB] Succès ! Schéma créé, réglages système et tables de référence RH initialisés.")

    except Exception as e:
        db.rollback()
        print(f"[INIT DB ERREUR] Échec de l'initialisation : {e}")
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialisation d'une base de données de production Klepsydrix (schéma + réglages système + tables de référence RH). Pour un jeu de démonstration complet, voir backend/app/core/init_demo.py.")
    parser.parse_args()
    init_prod_data()
