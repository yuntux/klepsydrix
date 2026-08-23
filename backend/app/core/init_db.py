import argparse
import json
from datetime import date
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.core.database import engine, SessionLocal


def _all_transient_model_subclasses(cls):
    """Même parcours récursif que generic.py::get_all_transient_models — dupliqué ici plutôt
    qu'importé pour ne pas faire dépendre init_db.py (bas niveau) du module API (haut niveau)."""
    subclasses = set(cls.__subclasses__())
    return subclasses.union(s for c in subclasses for s in _all_transient_model_subclasses(c))


def _all_tablenames() -> list:
    """
    Toutes les tables connues — ORM réelles (Base.registry.mappers, comme MODEL_MAP dans
    generic.py) ET ressources virtuelles (TransientModel, jamais dans Base.registry.mappers, qui ne
    connaît que les classes mappées sur une vraie table) — factorisé entre seed_admin_access et
    seed_readonly_access ci-dessous, qui n'en diffèrent que par les droits accordés.

    ⚠️ Trouvé en vérifiant le menu réel (pas seulement via pytest) : oublier les TransientModel ici
    aurait rendu invisibles, même pour Admin, deux entrées de menu existantes (génération des cours,
    synthèse TRMD) dès que le filtrage par droits du menu est devenu actif — les deux reposent sur
    un TransientModel (WizardCourseGeneration/TrmdLine), jamais une vraie table.
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

    tablenames = [mapper.class_.__tablename__ for mapper in Base.registry.mappers if getattr(mapper.class_, "__tablename__", None)]
    tablenames += [
        sub.__tablename__ for sub in _all_transient_model_subclasses(TransientModel)
        if getattr(sub, "__tablename__", None)
    ]
    return tablenames


def seed_admin_access(db: Session):
    """
    Groupe "Admin" et droits complets sur TOUS les modèles (voir _all_tablenames ci-dessus), généré
    par parcours, pas une liste écrite à la main : tout futur modèle est couvert automatiquement,
    sans action à faire à chaque nouvelle classe (voir aussi le test dédié, test_access_control.py,
    qui échoue si un modèle est absent).

    ir_model_access/res_groups eux-mêmes sont mappés, donc inclus par la première boucle — l'admin
    peut gérer les droits via l'API générique comme n'importe quel autre modèle. Fonction séparée de
    init_prod_data() (qui, elle, dépend du moteur/de la session globale de la base par défaut) pour
    rester appelable directement sur n'importe quelle session, y compris une session de test isolée.

    `is_system_generated=true` sur le groupe ET chaque ligne de droit (voir models/access.py) : ces
    `INSERT` bruts contournent déjà CRUDMixin, donc pas besoin du sentinel `_system_write` prévu
    pour la voie ORM — seule la colonne compte ici.
    """
    tablenames = _all_tablenames()

    db.execute(text("INSERT INTO res_groups (name, is_system_generated) VALUES ('Admin', true)"))
    db.commit()
    admin_group_id = db.execute(text("SELECT id FROM res_groups WHERE name = 'Admin'")).scalar()

    for tablename in tablenames:
        db.execute(text(
            "INSERT INTO ir_model_access (model, group_id, perm_read, perm_write, perm_create, perm_unlink, is_system_generated) "
            "VALUES (:model, :group_id, true, true, true, true, true)"
        ), {"model": tablename, "group_id": admin_group_id})
    db.commit()


# Tables de gestion des comptes/groupes/droits/connexions SSO — exclues du groupe "Consultation"
# (seed_readonly_access ci-dessous) : un simple consultant en lecture seule sur tout le reste de la
# base ne doit PAS pouvoir lister les comptes, leurs emails, ni la configuration des droits. Aucune
# ligne ir_model_access n'est créée pour ces tables → aucun accès du tout pour Consultation (même
# principe "aucune ligne = aucun accès" que pour tout autre modèle, voir access_control.py), pas
# seulement une restriction en écriture.
SECURITY_SENSITIVE_TABLENAMES = {
    "users", "user_identity_providers", "res_groups", "ir_model_access", "password_reset_tokens",
}


# Domaine de lecture restreinte pour certains modèles, même au sein du groupe "Consultation" par
# ailleurs en lecture totale sur tout le reste (voir seed_readonly_access) : custom_filters (voir
# models/custom_filter.py) ne doit exposer à un consultant que SES filtres ou les filtres marqués
# "partagé" par leur auteur, jamais les filtres privés d'un autre utilisateur. Reste néanmoins
# perm_write=perm_create=perm_unlink=false comme tout le reste du groupe (aucun carve-out
# d'écriture ici — la création/gestion de filtres personnels par un profil non-Admin nécessite un
# groupe dédié configuré explicitement par l'administrateur de la base, via l'écran de droits
# générique, comme pour n'importe quel autre modèle).
READONLY_CUSTOM_DOMAINS = {
    "custom_filters": json.dumps(["|", ["user_id", "=", "user.id"], ["is_shared", "=", True]]),
}


def seed_readonly_access(db: Session):
    """
    Groupe "Consultation" et droits de LECTURE SEULE sur tous les modèles, à l'exception de
    SECURITY_SENSITIVE_TABLENAMES ci-dessus — miroir de seed_admin_access (même parcours de
    découverte des modèles via _all_tablenames, mêmes conventions de seed en SQL brut), permissions
    et exclusion différentes. Voir READONLY_CUSTOM_DOMAINS ci-dessus pour l'unique modèle dont la
    lecture est en plus restreinte par un domaine (tous les autres restent domain=NULL, lecture
    totale).
    """
    tablenames = _all_tablenames()

    db.execute(text("INSERT INTO res_groups (name, is_system_generated) VALUES ('Consultation', true)"))
    db.commit()
    readonly_group_id = db.execute(text("SELECT id FROM res_groups WHERE name = 'Consultation'")).scalar()

    for tablename in tablenames:
        if tablename in SECURITY_SENSITIVE_TABLENAMES:
            continue
        db.execute(text(
            "INSERT INTO ir_model_access (model, group_id, perm_read, perm_write, perm_create, perm_unlink, domain, is_system_generated) "
            "VALUES (:model, :group_id, true, false, false, false, :domain, true)"
        ), {"model": tablename, "group_id": readonly_group_id, "domain": READONLY_CUSTOM_DOMAINS.get(tablename)})
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
        # Année scolaire de la base : millésime de septembre, l'année scolaire EN COURS au moment
        # de l'initialisation (2026 = année 2026-2027). Une base vaut pour une année et une seule,
        # comme toute base d'emploi du temps. Toujours modifiable ensuite depuis « Paramètres système ».
        db.execute(
            text("INSERT INTO system_settings (key, value) VALUES ('SCHOOL_YEAR', :value)"),
            {"value": str(date.today().year if date.today().month >= 6 else date.today().year - 1)},
        )
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
            # Grille horaire (voir spec.md §0bis, architecture.md §10.D) : FIRST_DAY_OF_THE_WEEK et
            # les horaires de récréation n'ont volontairement aucune valeur par défaut ici (repli
            # applicatif géré côté wizard_grid_settings.py/time_utils.py). PUBLIC_DISPLAY_HOURS_
            # BY_SEQUENCE, lui, EST seedé — voir plus bas, une fois grid_day_settings inséré (calcul
            # dépendant de cette grille). L'affichage des lignes de récréation n'est PAS un
            # SystemSetting : c'est un paramètre du composant graphique (BaseGrid.vue::displayBreaks,
            # défaut true).
        ]:
            db.execute(text("INSERT INTO system_settings (key, value) VALUES (:key, :value)"), {"key": setting_key, "value": setting_value})
        db.commit()

        # Grille horaire : 7 lignes fixes (une par jour, voir GridDaySettings — création/suppression
        # bloquées au niveau du modèle, seul ce seed raw SQL peut en produire). Défauts alignés sur
        # les logiciels du marché comparés (spec.md §0bis) : lundi-vendredi 8h-18h, samedi fermé
        # l'après-midi (8h-12h), dimanche entièrement fermé. Aucun Timeslot n'est généré ici : la
        # grille reste vide tant que le wizard « Grille horaire » n'a pas été confirmé une première
        # fois (auto-lancé à la connexion si la base n'en a aucun, voir NotebooksTree.vue).
        grid_day_defaults = [
            (1, 480, 1080), (2, 480, 1080), (3, 480, 1080), (4, 480, 1080), (5, 480, 1080),
            (6, 480, 720),
            (7, None, None),
        ]
        for day_of_week, start, end in grid_day_defaults:
            db.execute(
                text(
                    "INSERT INTO grid_day_settings (day_of_week, hour_day_start_minutes_after_midnight, hour_day_end_minutes_after_midnight) "
                    "VALUES (:day_of_week, :start, :end)"
                ),
                {"day_of_week": day_of_week, "start": start, "end": end},
            )
        db.commit()

        # PUBLIC_DISPLAY_HOURS_BY_SEQUENCE en cohérence avec la grille ci-dessus (voir spec.md
        # §0bis) : un couple [début, fin] par numéro de séquence, calculé sur la même base que
        # Timeslot.intraday_sequence_number (heure d'ouverture la plus matinale, tous jours
        # confondus, jusqu'à l'heure de fermeture la plus tardive). Exercice délibéré du mécanisme
        # de repli PAR VALEUR (voir Timeslot.public_display_start/end_minutes_after_midnight) :
        # séquence impaire -> seul le début est renseigné (fin = null, retombe sur l'heure réelle
        # à la lecture) ; séquence paire -> seule la fin est renseignée (début = null, idem).
        standard_duration = 30
        starts = [s for _, s, _ in grid_day_defaults if s is not None]
        ends = [e for _, _, e in grid_day_defaults if e is not None]
        min_start, max_end = min(starts), max(ends)
        public_display_hours_by_sequence = {}
        for seq, minute in enumerate(range(min_start, max_end, standard_duration), start=1):
            if seq % 2 == 1:
                public_display_hours_by_sequence[str(seq)] = [minute, None]
            else:
                public_display_hours_by_sequence[str(seq)] = [None, minute + standard_duration]
        db.execute(
            text("INSERT INTO system_settings (key, value) VALUES ('PUBLIC_DISPLAY_HOURS_BY_SEQUENCE', :value)"),
            {"value": json.dumps(public_display_hours_by_sequence)},
        )
        db.commit()

        # Tables de référence RH (fiche enseignant) — simples listes en texte libre. ref_country,
        # ref_inspector, ref_ara, ref_are, ref_particular_mission, ref_pacte_mission,
        # ref_external_school, ref_city, ref_exit_reasons, ref_relative_links, ref_jobs sont
        # volontairement créées vides (aucune valeur de seed demandée, nomenclature non fermée
        # complétée par les imports SIECLE) : seules les tables ci-dessous ont un contenu initial
        # connu.
        # code : valeur attendue de PERSONNE/LC_CIVILITE (ResponsablesAvecAdresses), qui n'a aucune
        # énumération fermée côté SIECLE — les deux lignes ci-dessous sont celles qui reviennent
        # dans les exemples connus, pas une liste exhaustive.
        ref_titles_data = [("Monsieur", "M."), ("Madame", "MME")]
        for name, code in ref_titles_data:
            db.execute(text("INSERT INTO ref_titles (name, code) VALUES (:name, :code)"), {"name": name, "code": code})

        # code : valeur attendue d'ELEVE/CODE_REGIME (ElevesAvecAdresses). Nomenclature fermée et
        # connue (DP/DI/EX), contrairement à ref_exit_reasons/ref_relative_links/ref_jobs ci-dessus.
        ref_regimes_data = [("DP", "Demi-pensionnaire"), ("DI", "Interne"), ("EX", "Externe")]
        for code, name in ref_regimes_data:
            db.execute(text("INSERT INTO ref_regimes (code, name) VALUES (:code, :name)"), {"code": code, "name": name})

        # code : valeur attendue de RESPONSABLE/RESP_LEGAL (ResponsablesAvecAdresses). Nomenclature
        # fermée et connue (0/1/2).
        ref_legal_guardians_data = [("0", "Autre"), ("1", "Responsable légal 1"), ("2", "Responsable légal 2")]
        for code, name in ref_legal_guardians_data:
            db.execute(text("INSERT INTO ref_legal_guardians (code, name) VALUES (:code, :name)"), {"code": code, "name": name})

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

        # code : clé d'appariement du flux STS (INDIVIDU/GRADE). Les valeurs ci-dessous sont des
        # grades de carrière, sans équivalent connu dans le flux — d'où des codes locaux. L'import
        # crée la ligne manquante quand il rencontre un code inconnu.
        ref_levels_data = [("CN", "Classe Normale"), ("HC", "Hors Classe"), ("CE", "Classe exceptionnelle")]
        for code, name in ref_levels_data:
            db.execute(text("INSERT INTO ref_levels (code, name) VALUES (:code, :name)"), {"code": code, "name": name})

        ref_affectation_modes_data = ["Poste définitif", "Réaffectation carte", "Remplacement"]
        for name in ref_affectation_modes_data:
            db.execute(text("INSERT INTO ref_affectation_modes (name) VALUES (:name)"), {"name": name})

        ref_service_modes_data = ["Mi-temps", "Temps partiel", "Temps plein"]
        for name in ref_service_modes_data:
            db.execute(text("INSERT INTO ref_service_modes (name) VALUES (:name)"), {"name": name})

        # code : clé d'appariement du flux STS (INDIVIDU/FONCTION). « ENS » est la seule valeur
        # attestée du flux (voir FORMATS_JUSTIFICATION.md §2.8) ; les autres sont des codes locaux.
        ref_functions_data = [("ENS", "Enseignant"), ("DIR", "Direction"), ("DOC", "Documentaliste"), ("SURV", "Surveillant")]
        for code, name in ref_functions_data:
            db.execute(text("INSERT INTO ref_functions (code, name) VALUES (:code, :name)"), {"code": code, "name": name})

        ref_support_types_data = ["Principal", "Secondaire", "Gelé"]
        for name in ref_support_types_data:
            db.execute(text("INSERT INTO ref_support_types (name) VALUES (:name)"), {"name": name})

        ref_support_data = [
            "CSR - Complément de service reçu",
            "BMP - Bloc de moyens provisoires",
            "CLR - Classe relais",
            "IS - Instituteur spécialisé de collèges",
            "ISES - Instituteur SES",
            "ISMF - Instituteur maître formateur",
            "PEGC - Poste de pegc des collèges",
            "UPI - Unité pédagogique d'intégration",
        ]
        for name in ref_support_data:
            db.execute(text("INSERT INTO ref_supports (name) VALUES (:name)"), {"name": name})

        # Niveaux de formation (RefGrade) — nomenclature nationale, présente dans TOUTE base de
        # production (contrairement aux tables ref_* ci-dessus, laissées vides) : frontière de
        # mutualisation de l'effectif réduit entre Service de MEF différents (voir
        # Service._reduced_pool_services, spec.md « Mutualisation de l'effectif réduit »).
        # specialty_choice_limit (plafond de vœux de spécialité, réforme du lycée) : 3 en Première,
        # 2 en Terminale, NULL (non concerné) pour les autres niveaux — voir StudentSpecialtyChoice.
        ref_grades_data = [
            ("6EME", None), ("5EME", None), ("4EME", None), ("3EME", None), ("2NDE", None),
            ("1ERE", 3), ("TERMINALE", 2),
        ]
        for name, specialty_choice_limit in ref_grades_data:
            db.execute(
                text("INSERT INTO ref_grades (name, specialty_choice_limit) VALUES (:name, :specialty_choice_limit)"),
                {"name": name, "specialty_choice_limit": specialty_choice_limit},
            )

        # Modalités de cours (CODE_MOD_COURS du flux STS), issues de la Base Académique des
        # Nomenclatures : donnée de référence nationale, présente dans toute base de production
        # au même titre que ref_grades. is_sts_compliant=true pour les neuf : c'est un INSERT SQL
        # brut, seul chemin qui puisse écrire true (voir StsComplianceMixin, jamais via l'API).
        # « CG » est inséré EN PREMIER à dessein : Course.modality_id vaut 1 par défaut, et c'est
        # la modalité par défaut d'un cours. Ne pas réordonner cette liste sans changer ce défaut.
        modalities_data = [
            ("CG", "COURS", "COURS GENERAL"),
            ("EC", "ENS. COMP.", "ENSEIGNEMENT COMPLEMENTAIRE"),
            ("AT", "ATELIER", "ATELIER"),
            ("TD", "TD", "TRAVAUX DIRIGES"),
            ("AP", "ATP", "ATELIER DE PRATIQUE"),
            ("TP", "TP", "TRAVAUX PRATIQUES"),
            ("AI", "AIDE IND", "AIDE INDIVIDUALISEE - SOUTIEN"),
            ("PL", "PLURIDISC", "PLURIDISCIPLINAIRE"),
            ("MO", "MODULE", "MODULE MONO-DISCIPLINAIRE"),
        ]
        for code, name, long_name in modalities_data:
            db.execute(
                text("INSERT INTO modalities (code, name, long_name, is_sts_compliant) VALUES (:code, :name, :long_name, true)"),
                {"code": code, "name": name, "long_name": long_name},
            )

        # Modalités d'élection (nomenclature nationale STSWEB) — même statut que modalities
        # ci-dessus : donnée de référence nationale, seedée ici et non par init_demo.py (déplacée
        # depuis init_demo.py, qui n'en gardait qu'une lecture par SELECT).
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
                "INSERT INTO ref_election_methods (code, name, export_code, is_sts_compliant) "
                "VALUES (:code, :name, :export_code, true)"
            ), {"code": code, "name": long_label, "export_code": short_label})

        # Pondérations autorisées (voir RefWeightingCoefficient, docstring). 1.00 est insérée EN
        # PREMIER à dessein : Course/CourseTeacherWeighting/MefService/Service.
        # weighting_coefficient_id valent tous 1 par défaut, et doivent donc pointer vers 1.00.
        weighting_coefficients_data = [1.00, 0.25, 0.5, 0.75, 1.25, 1.5]
        for value in weighting_coefficients_data:
            db.execute(
                text("INSERT INTO ref_weighting_coefficients (weighting_coefficient, is_sts_compliant) VALUES (:value, true)"),
                {"value": value},
            )

        db.commit()

        print("[INIT DB] Génération du groupe Admin et des droits complets sur tous les modèles...")
        seed_admin_access(db)

        print("[INIT DB] Génération du groupe Consultation et des droits en lecture seule...")
        seed_readonly_access(db)

        print("[INIT DB] Succès ! Schéma créé, réglages système, tables de référence RH et droits Admin/Consultation initialisés.")

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
