import argparse
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.core.database import engine, SessionLocal


def _all_transient_model_subclasses(cls):
    """Même parcours récursif que generic.py::get_all_transient_models — dupliqué ici plutôt
    qu'importé pour ne pas faire dépendre init_db.py (bas niveau) du module API (haut niveau)."""
    subclasses = set(cls.__subclasses__())
    return subclasses.union(s for c in subclasses for s in _all_transient_model_subclasses(c))


def seed_admin_access(db: Session):
    """
    Groupe "Admin" et droits complets sur TOUS les modèles — tables ORM réelles (Base.registry.
    mappers, comme MODEL_MAP dans generic.py) ET ressources virtuelles (TransientModel — jamais
    dans Base.registry.mappers, qui ne connaît que les classes mappées sur une vraie table),
    généré par parcours, pas une liste écrite à la main : tout futur modèle est couvert
    automatiquement, sans action à faire à chaque nouvelle classe (voir aussi le test dédié,
    test_access_control.py, qui échoue si un modèle est absent).

    ⚠️ Trouvé en vérifiant le menu réel (pas seulement via pytest) : oublier les TransientModel ici
    aurait rendu invisibles, même pour Admin, deux entrées de menu existantes (génération des cours,
    synthèse TRMD) dès que le filtrage par droits du menu est devenu actif — les deux reposent sur
    un TransientModel (WizardCourseGeneration/TrmdLine), jamais une vraie table.

    ir_model_access/res_groups eux-mêmes sont mappés, donc inclus par la première boucle — l'admin
    peut gérer les droits via l'API générique comme n'importe quel autre modèle. Fonction séparée de
    init_prod_data() (qui, elle, dépend du moteur/de la session globale de la base par défaut) pour
    rester appelable directement sur n'importe quelle session, y compris une session de test isolée.
    """
    import importlib
    import pkgutil
    from backend.app.models.base import Base, TransientModel
    import backend.app.models as models_package

    # backend.app.models (__init__.py) n'importe pas TOUS les fichiers du paquet (ex:
    # wizard_course_generation.py, trmd_synthesis.py — jamais réexportés là) : un simple `import
    # backend.app.models` ne suffit donc PAS à faire apparaître leurs classes dans
    # TransientModel.__subclasses__(), qui n'enregistre une sous-classe qu'une fois son module
    # réellement exécuté. Même parcours pkgutil que generic.py::MODEL_MAP pour garantir une
    # découverte complète, identique à celle réellement utilisée par l'API en production (où
    # generic.py déclenche cette même découverte au chargement du process).
    for _, module_name, _ in pkgutil.iter_modules(models_package.__path__):
        importlib.import_module(f"backend.app.models.{module_name}")

    db.execute(text("INSERT INTO res_groups (name) VALUES ('Admin')"))
    db.commit()
    admin_group_id = db.execute(text("SELECT id FROM res_groups WHERE name = 'Admin'")).scalar()

    tablenames = [mapper.class_.__tablename__ for mapper in Base.registry.mappers if getattr(mapper.class_, "__tablename__", None)]
    tablenames += [
        sub.__tablename__ for sub in _all_transient_model_subclasses(TransientModel)
        if getattr(sub, "__tablename__", None)
    ]
    for tablename in tablenames:
        db.execute(text(
            "INSERT INTO ir_model_access (model, group_id, perm_read, perm_write, perm_create, perm_unlink) "
            "VALUES (:model, :group_id, true, true, true, true)"
        ), {"model": tablename, "group_id": admin_group_id})
    db.commit()


def init_prod_data(slug: str = None):
    """
    Initialise le schéma et les données de référence communes à TOUTE base de production
    Klepsydrix : réglages système globaux (system_settings) et tables de référence RH en texte
    libre (ref_*). Aucune donnée d'établissement, de matière, d'enseignant ou de cours ici —
    c'est un socle générique, valable pour n'importe quel établissement réel. Le jeu d'essai de
    démonstration (backend/app/core/init_demo.py) appelle cette fonction en premier, avant
    d'ajouter par-dessus tout son propre contenu.

    `slug` : cible une base précise via le registre multi-base (voir db_registry.py) — utilisé par
    la console d'administration lors de la création d'une nouvelle base (architecture.md §20). Sans
    lui (par défaut), cible la base par défaut mono-base historique (`DEFAULT_DB_NAME`,
    "timetable") — comportement inchangé pour le script CLI (`python -m backend.app.core.init_db`).
    """
    print(f"[INIT DB] Initialisation du schéma et des données de référence de production{f' (base {slug})' if slug else ''}...")
    from backend.app.models.base import Base
    import backend.app.models

    if slug:
        from backend.app.core import db_registry
        target_engine = db_registry.engine_for(slug)
        target_session_local = db_registry.sessionmaker_for(slug)
    else:
        target_engine = engine
        target_session_local = SessionLocal

    # Recréer toutes les tables pour repartir à blanc
    Base.metadata.drop_all(bind=target_engine)
    Base.metadata.create_all(bind=target_engine)

    db = target_session_local()
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

        print("[INIT DB] Génération du groupe Admin et des droits complets sur tous les modèles...")
        seed_admin_access(db)

        print("[INIT DB] Succès ! Schéma créé, réglages système, tables de référence RH et droits Admin initialisés.")

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
