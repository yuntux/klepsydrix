"""
Tests pour les 9 modes de composition des cours complexes.
"""
import pytest
from datetime import date
from sqlalchemy.orm import sessionmaker
from backend.app.models.base import Base
from backend.app.models import (
    School, Teacher, Subject, Division, Classroom,
    Period, PeriodType, Group, Course, SystemSetting, Timeslot
)
from backend.app.models.composition_mode import CompositionModes, CompositionError
from backend.tests.db_test_utils import make_test_engine

test_engine = make_test_engine()
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        School.create(db, {"uai": "1234567A", "name": "Campus Test"})
        SystemSetting.create(db, {"key": "STANDARD_TIMESLOT_DURATION", "value": "30"})
        # Nommage auto des parties de classe / groupes (mêmes valeurs par défaut que init_db.py)
        for key, value in [
            ("DIVISION_PART_NAME_HAS_DIV_CODE", "true"),
            ("DIVISION_PART_NAME_HAS_SUBJECT_CODE", "true"),
            ("DIVISION_PART_NAME_SEPARATOR", "P"),
            ("DIVISION_PART_NAME_NUMBER_FORMAT", "numerique"),
            ("GROUP_NAME_HAS_DIV_CODE", "true"),
            ("GROUP_NAME_HAS_SUBJECT_CODE", "true"),
            ("GROUP_NAME_SEPARATOR", "G"),
            ("GROUP_NAME_NUMBER_FORMAT", "numerique"),
        ]:
            SystemSetting.create(db, {"key": key, "value": value})
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)

def _prepare_parent_course(db, extra_teachers=0, extra_groups=0, extra_divisions=0, extra_periods=0):
    from backend.app.models.discipline import Discipline
    school = School.create(db, {"uai": "CAMPUS", "name": "Campus Test"})
    discipline = Discipline.create(db, {"code": "GEN", "name": "Général"})

    subjects = [Subject.create(db, {"code": f"SUB{i}", "code_nomenclature": f"N{i}", "short_name": f"Sub{i}", "name": f"Subject{i}", "discipline_id": discipline.id}) for i in range(2)]
    teachers = [Teacher.create(db, {"code": f"T{i}", "last_name": f"Teacher{i}", "first_name": f"T{i}", "school_id": school.id}) for i in range(2 + extra_teachers)]
    classrooms = [Classroom.create(db, {"code": f"R{i}", "name": f"Room{i}", "school_id": school.id}) for i in range(2)]
    divisions = [Division.create(db, {"code": f"D{i}", "name": f"Division{i}", "school_id": school.id}) for i in range(1 + extra_divisions)]
    groups_gen = [Group.create(db, {"name": f"Group{i}"}) for i in range(2 + extra_groups)]

    period_type = None
    periods = []
    if extra_periods > 0:
        period_type = PeriodType.create(db, {"name": "Trimestre"})
        periods = [
            Period.create(db, {"code": f"P{i}", "name": f"Periode{i}", "period_type_id": period_type.id, "school_id": school.id, "start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31)})
            for i in range(extra_periods)
        ]

    parent = Course.create(db, {
        'is_composed': True,
        'school_id': school.id,
        'subject_id': subjects[0].id,
        'duration_minutes': 120,
        'week_type': 'W',
        'teacher_ids': [t.id for t in teachers],
        'classroom_requirement_ids': [{"classroom_id": r.id, "quantity": 1} for r in classrooms],
        'division_ids': [d.id for d in divisions],
        'group_ids': [g.id for g in groups_gen],
        'period_ids': [p.id for p in periods],
        'period_type_id': period_type.id if period_type else None,
    })
    
    # classroom_ids (pas classroom_requirement_ids) : c'est la vraie forme produite par la colonne
    # "Salles" du wizard (liste d'ids de Classroom bruts) — voir CompositionModes._build_base_vals,
    # qui convertit cette liste en dicts CourseClassroomRequirement.
    mock_mapping = [
        {"teacher_ids": [teachers[0].id], "group_ids": [groups_gen[0].id], "classroom_ids": [classrooms[0].id], "subject_id": subjects[0].id},
        {"teacher_ids": [teachers[1].id], "group_ids": [groups_gen[1].id], "classroom_ids": [classrooms[1].id], "subject_id": subjects[0].id}
    ]

    return parent, teachers, groups_gen, divisions, periods, mock_mapping

def _set_setting(db, key, value):
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    setting.update(db, {"value": value})

class TestCompositionModes:
    def test_mode_1_one_session_per_teacher(self, db_session):
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        children = CompositionModes.apply(db_session, parent, 1, mapping)
        assert len(children) == 2
        # Assertions d'orthogonalité
        assert len(children[0].classroom_requirements) == 1
        assert len(children[1].classroom_requirements) == 1
        assert children[0].classroom_requirements[0].classroom_id != children[1].classroom_requirements[0].classroom_id
        assert children[0].teachers[0].id == teachers[0].id
        assert children[1].teachers[0].id == teachers[1].id

    def test_mapping_classroom_ids_become_classroom_requirements(self, db_session):
        # Régression : la colonne "Salles" du wizard produit `classroom_ids` (liste d'ids de
        # Classroom bruts) sur la ligne de mapping, jamais `classroom_requirement_ids` — un id de
        # Classroom passé nu à Course.create() serait interprété comme un id de
        # CourseClassroomRequirement à conserver (voir _apply_owned_collection_commands, base.py),
        # pas comme une salle à affecter. _build_base_vals doit convertir explicitement.
        from backend.app.models.classroom import Classroom
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        classroom = db_session.query(Classroom).first()
        mapping_with_classroom = [{
            "teacher_ids": [teachers[0].id], "group_ids": [groups[0].id],
            "classroom_ids": [classroom.id], "subject_id": parent.subject_id,
        }]

        children = CompositionModes.apply(db_session, parent, 1, mapping_with_classroom)

        assert len(children[0].classroom_requirements) == 1
        assert children[0].classroom_requirements[0].classroom_id == classroom.id
        assert children[0].classroom_requirements[0].quantity == 1

    def test_mapping_without_classroom_ids_yields_no_requirement(self, db_session):
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        mapping_no_classroom = [{
            "teacher_ids": [teachers[0].id], "group_ids": [groups[0].id], "subject_id": parent.subject_id,
        }]

        children = CompositionModes.apply(db_session, parent, 1, mapping_no_classroom)

        assert children[0].classroom_requirements == []

    def test_mode_2_one_session_per_teacher_per_fortnight(self, db_session):
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        children = CompositionModes.apply(db_session, parent, 2, mapping)
        assert len(children) == 4
        assert {c.week_type.value for c in children} == {'A', 'B'}

    def test_mode_3_barrette_direct_then_inverted(self, db_session):
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        children = CompositionModes.apply(db_session, parent, 3, mapping)
        assert len(children) == 4
        
        # Vérification du calcul correct de l'offset: (120 // 2) // 30 = 2
        offsets = {c.parent_timeslot_offset for c in children}
        assert offsets == {0, 2}
        for c in children:
            assert c.duration_minutes == 60

    def test_mode_4_barrette_with_fortnight_alternation(self, db_session):
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        children = CompositionModes.apply(db_session, parent, 4, mapping)
        assert len(children) == 8

    def test_mode_5_teachers_swap_divisions_each_fortnight(self, db_session):
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        children = CompositionModes.apply(db_session, parent, 5, mapping)
        assert len(children) == 4

    def test_mode_6_three_groups_two_classes(self, db_session):
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session, extra_groups=1, extra_teachers=1)
        mapping.append({"teacher_ids": [teachers[2].id], "group_ids": [groups[2].id], "classroom_requirement_ids": [], "subject_id": parent.subject_id})
        children = CompositionModes.apply(db_session, parent, 6, mapping)
        assert len(children) == 4

    def test_mode_7_one_session_per_teacher_per_period(self, db_session):
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session, extra_periods=2)
        children = CompositionModes.apply(db_session, parent, 7, mapping)
        assert len(children) == 2

    def test_mode_8_teachers_rotate_among_groups_per_period(self, db_session):
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session, extra_periods=2)
        children = CompositionModes.apply(db_session, parent, 8, mapping)
        assert len(children) == 4

    def test_mode_9_one_group_changes_teacher_per_period(self, db_session):
        # 1 seul groupe, 2 profs, 2 périodes
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session, extra_periods=2)
        # Mapping spécifique pour le mode 9 (1 seul groupe qui change de prof)
        mapping_m9 = [
            {"teacher_ids": [teachers[0].id], "group_ids": [groups[0].id], "classroom_requirement_ids": [], "subject_id": parent.subject_id},
            {"teacher_ids": [teachers[1].id], "group_ids": [groups[0].id], "classroom_requirement_ids": [], "subject_id": parent.subject_id}
        ]
        children = CompositionModes.apply(db_session, parent, 9, mapping_m9)
        # Contrairement au mode 8 (qui crée une barrette de N cours par période), 
        # le mode 9 ne crée qu'UN seul cours par période.
        assert len(children) == 2
        assert children[0].periods[0].id == periods[0].id
        assert children[0].teachers[0].id == teachers[0].id
        assert children[1].periods[0].id == periods[1].id
        assert children[1].teachers[0].id == teachers[1].id

    def test_co_teaching_multiple_teachers_in_mapping(self, db_session):
        # Validation du support du co-enseignement
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        # Mapping avec 2 professeurs sur la même ligne
        mapping_coteaching = [
            {"teacher_ids": [teachers[0].id, teachers[1].id], "group_ids": [groups[0].id], "classroom_requirement_ids": [], "subject_id": parent.subject_id}
        ]
        # Application du Mode 1
        children = CompositionModes.apply(db_session, parent, 1, mapping_coteaching)
        assert len(children) == 1
        assert len(children[0].teachers) == 2
        # Vérification de l'ordre ou de la présence des IDs
        child_teacher_ids = {t.id for t in children[0].teachers}
        assert child_teacher_ids == {teachers[0].id, teachers[1].id}
        # Plusieurs profs sur la ligne => enfant marqué en co-enseignement, mais is_composed
        # reste False : cette notion est purement dérivée de la présence d'enfants (voir
        # course.py, _compute_is_composed), jamais du nombre de ressources liées.
        assert children[0].is_co_teaching is True
        assert children[0].is_composed is False

    def test_single_teacher_child_is_not_co_teaching(self, db_session):
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        children = CompositionModes.apply(db_session, parent, 1, mapping)
        assert children[0].is_co_teaching is False
        assert children[0].is_composed is False

    def test_co_teaching_flag_follows_teacher_rotation_across_modes(self, db_session):
        # Le mode 5 réaffecte teacher_ids d'une ligne à l'autre à la quinzaine B : is_co_teaching
        # doit refléter la liste de profs réellement utilisée par CHAQUE enfant, pas celle de la
        # ligne de mapping d'origine.
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session, extra_teachers=1)
        mapping_rotation = [
            {"teacher_ids": [teachers[0].id, teachers[2].id], "group_ids": [groups[0].id], "classroom_requirement_ids": [], "subject_id": parent.subject_id},
            {"teacher_ids": [teachers[1].id], "group_ids": [groups[1].id], "classroom_requirement_ids": [], "subject_id": parent.subject_id},
        ]
        children = CompositionModes.apply(db_session, parent, 5, mapping_rotation)
        by_week_and_group = {(c.week_type.value, c.groups[0].id): c for c in children}

        # Semaine A : ligne 0 telle quelle (2 profs -> co-enseignement), ligne 1 telle quelle (1 prof).
        assert by_week_and_group[('A', groups[0].id)].is_co_teaching is True
        assert by_week_and_group[('A', groups[1].id)].is_co_teaching is False
        # Semaine B : rotation, la ligne 0 récupère les profs de la ligne 1 (1 prof) et vice-versa.
        assert by_week_and_group[('B', groups[0].id)].is_co_teaching is False
        assert by_week_and_group[('B', groups[1].id)].is_co_teaching is True

    def test_dynamic_group_resolution(self, db_session):
        # Validation que plusieurs class_part_ids génèrent un groupe
        from backend.app.models.group import Partition, ClassPart
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        
        partition = Partition.create(db_session, {"code": "PART1", "name": "Test Part", "division_id": divisions[0].id})
        cp1 = ClassPart.create(db_session, {"name": "P1", "partition_id": partition.id})
        cp2 = ClassPart.create(db_session, {"name": "P2", "partition_id": partition.id})
        
        mapping_dynamic = [
            {"teacher_ids": [teachers[0].id], "class_part_ids": [cp1.id, cp2.id], "classroom_requirement_ids": [], "subject_id": parent.subject_id}
        ]
        
        children = CompositionModes.apply(db_session, parent, 1, mapping_dynamic)
        
        assert len(children) == 1
        # Le resolveur vide class_part_ids (le groupe englobe ces parties), mais la cascade
        # Group -> ClassPart (Course._apply_group_class_part_cascade, voir spec.md section
        # Course) les réinjecte automatiquement dès que le groupe est ajouté au cours enfant.
        assert {cp.id for cp in children[0].class_parts} == {cp1.id, cp2.id}
        # Mais il doit avoir un groupe auto-généré, nommé {1re lettre code division}{séparateur}{code matière}{numéro}
        assert len(children[0].groups) == 1
        subject = db_session.get(Subject, parent.subject_id)
        assert children[0].groups[0].name == f"{divisions[0].code[0]}G{subject.code}1"
        
        # Les parties de classe sont bien dans le groupe
        group_cp_ids = {cp.id for cp in children[0].groups[0].class_parts}
        assert group_cp_ids == {cp1.id, cp2.id}


    def test_dynamic_part_class_creates_and_reuses_by_division_subject(self, db_session):
        # Une ligne ciblant une division entière (division_ids) doit être résolue en une ClassPart
        # {division, matière de la ligne}, réutilisée si une composition ultérieure retombe sur la
        # même clé (ex: relance de "Générer l'aperçu").
        from backend.app.models.group import ClassPart
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        subject_id = parent.subject_id  # matière "chapeau" du parent, différente de celle de la ligne
        from backend.app.models.subject import Subject
        discipline_id = db_session.query(Subject).first().discipline_id
        other_subject = Subject.create(db_session, {"code": "SUBX", "code_nomenclature": "NX", "short_name": "SubX", "name": "Espagnol", "discipline_id": discipline_id})

        mapping_1 = [{"teacher_ids": [teachers[0].id], "division_ids": [divisions[0].id], "subject_id": other_subject.id, "classroom_requirement_ids": []}]
        children_1 = CompositionModes.apply(db_session, parent, 1, mapping_1)
        assert len(children_1) == 1
        assert len(children_1[0].class_parts) == 1
        # Une seule partie de classe : rattachement direct, pas de groupe dédié généré.
        assert len(children_1[0].groups) == 0
        # Nommée {1re lettre code division}{code matière}{séparateur}{numéro} (matière de la LIGNE, pas celle du parent).
        assert children_1[0].class_parts[0].name == f"{divisions[0].code[0]}{other_subject.code}P1"
        assert children_1[0].class_parts[0].subject_id == other_subject.id
        # La Partition porte la matière "chapeau" du parent (désignée), pas celle de la ligne.
        parent_subject = db_session.get(Subject, subject_id)
        assert children_1[0].class_parts[0].partition.name == parent_subject.code

        mapping_2 = [{"teacher_ids": [teachers[1].id], "division_ids": [divisions[0].id], "subject_id": other_subject.id, "classroom_requirement_ids": []}]
        children_2 = CompositionModes.apply(db_session, parent, 1, mapping_2)
        assert len(children_2) == 1
        assert children_2[0].class_parts[0].id == children_1[0].class_parts[0].id

        # Une seule ClassPart existe pour cette clé fonctionnelle {division, matière}, malgré 2 appels.
        all_parts_for_key = db_session.query(ClassPart).filter(
            ClassPart.subject_id == other_subject.id
        ).all()
        assert len(all_parts_for_key) == 1

    def test_class_part_naming_respects_custom_system_settings(self, db_session):
        # Séparateur personnalisé, codes division/matière désactivés, numérotation alphabétique.
        _set_setting(db_session, "DIVISION_PART_NAME_HAS_DIV_CODE", "false")
        _set_setting(db_session, "DIVISION_PART_NAME_HAS_SUBJECT_CODE", "false")
        _set_setting(db_session, "DIVISION_PART_NAME_SEPARATOR", "X")
        _set_setting(db_session, "DIVISION_PART_NAME_NUMBER_FORMAT", "alphabetique")
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)

        mapping_1 = [{"teacher_ids": [teachers[0].id], "division_ids": [divisions[0].id], "subject_id": parent.subject_id, "classroom_requirement_ids": []}]
        children_1 = CompositionModes.apply(db_session, parent, 1, mapping_1)
        assert children_1[0].class_parts[0].name == "XA"

        from backend.app.models.subject import Subject
        discipline_id = db_session.query(Subject).first().discipline_id
        other_subject = Subject.create(db_session, {"code": "AUTREMAT", "code_nomenclature": "NY", "short_name": "AutreMat", "name": "Autre matière", "discipline_id": discipline_id})
        mapping_2 = [{"teacher_ids": [teachers[1].id], "division_ids": [divisions[0].id], "subject_id": other_subject.id, "classroom_requirement_ids": []}]
        children_2 = CompositionModes.apply(db_session, parent, 1, mapping_2)
        # Même préfixe "X" (codes désactivés) : 2e lettre de la séquence, malgré une matière différente.
        assert children_2[0].class_parts[0].name == "XB"

    def test_group_naming_respects_custom_system_settings(self, db_session):
        _set_setting(db_session, "GROUP_NAME_HAS_DIV_CODE", "false")
        _set_setting(db_session, "GROUP_NAME_HAS_SUBJECT_CODE", "false")
        _set_setting(db_session, "GROUP_NAME_SEPARATOR", "Y")
        _set_setting(db_session, "GROUP_NAME_NUMBER_FORMAT", "alphabetique")
        # 2 divisions sur une même ligne : _resolve_dynamic_part_class y génère 2 parties de classe,
        # que _resolve_dynamic_groups regroupe alors dans un groupe auto (cp_ids > 1).
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session, extra_divisions=1)

        mapping_2div = [{
            "teacher_ids": [teachers[0].id],
            "division_ids": [divisions[0].id, divisions[1].id],
            "subject_id": parent.subject_id,
            "classroom_requirement_ids": [],
        }]
        children = CompositionModes.apply(db_session, parent, 1, mapping_2div)
        assert children[0].groups[0].name == "YA"

    def test_dynamic_part_class_shares_partition_across_subjects_same_division(self, db_session):
        # Sans matière "chapeau" désignée (cours complexe type "Pôle"), toutes les parties de
        # classe générées pour une même division lors d'un même appel partagent une Partition
        # nommée par la concaténation triée des codes matière.
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        parent.update(db_session, {"subject_id": None})
        from backend.app.models.subject import Subject
        subjects = db_session.query(Subject).order_by(Subject.code).all()

        mapping_pole = [
            {"teacher_ids": [teachers[0].id], "division_ids": [divisions[0].id], "subject_id": subjects[0].id, "classroom_requirement_ids": []},
            {"teacher_ids": [teachers[1].id], "division_ids": [divisions[0].id], "subject_id": subjects[1].id, "classroom_requirement_ids": []},
        ]
        children = CompositionModes.apply(db_session, parent, 1, mapping_pole)
        assert len(children) == 2
        cp_a = children[0].class_parts[0]
        cp_b = children[1].class_parts[0]
        assert cp_a.partition_id == cp_b.partition_id
        assert cp_a.partition.name == f"{subjects[0].code}+{subjects[1].code}"

    def test_cleanup_cascades_through_group_and_partitions_when_child_deleted(self, db_session):
        # Une ligne à 2 divisions génère 2 parties de classe (1 par division, donc 2 partitions
        # distinctes) regroupées dans un groupe auto (_resolve_dynamic_groups). La cascade Group
        # -> ClassPart (Course._apply_group_class_part_cascade) réinjecte automatiquement ces 2
        # parties en direct sur l'enfant dès que le groupe lui est ajouté. Supprimer cet enfant
        # doit malgré tout nettoyer les 2 parties, le groupe, et les 2 partitions.
        from backend.app.models.group import ClassPart, Group, Partition
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session, extra_divisions=1)

        mapping_multi_division = [{
            "teacher_ids": [teachers[0].id],
            "division_ids": [divisions[0].id, divisions[1].id],
            "subject_id": parent.subject_id,
            "classroom_requirement_ids": [],
        }]
        children = CompositionModes.apply(db_session, parent, 1, mapping_multi_division)
        assert len(children) == 1
        child = children[0]
        assert len(child.class_parts) == 2
        assert len(child.groups) == 1

        group = child.groups[0]
        group_id = group.id
        cp_ids = [cp.id for cp in group.class_parts]
        assert len(cp_ids) == 2
        partition_ids = list({cp.partition_id for cp in group.class_parts})
        assert len(partition_ids) == 2

        child.delete(db_session)

        assert db_session.get(Group, group_id) is None
        for cp_id in cp_ids:
            assert db_session.get(ClassPart, cp_id) is None
        for partition_id in partition_ids:
            assert db_session.get(Partition, partition_id) is None

    def test_cleanup_ignores_manually_created_or_still_used_resources(self, db_session):
        from backend.app.models.group import ClassPart, Partition, cleanup_orphaned_class_part
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)

        # Créée à la main (is_system_generated=False par défaut) : jamais touchée par le nettoyage.
        manual_partition = Partition.create(db_session, {"code": "MAN", "name": "Manuelle", "division_id": divisions[0].id})
        manual_cp = ClassPart.create(db_session, {"partition_id": manual_partition.id, "name": "Manuelle"})
        cleanup_orphaned_class_part(db_session, manual_cp.id)
        assert db_session.get(ClassPart, manual_cp.id) is not None

        # Auto-générée mais toujours utilisée par un cours réel : pas de suppression.
        mapping_1 = [{"teacher_ids": [teachers[0].id], "division_ids": [divisions[0].id], "subject_id": parent.subject_id, "classroom_requirement_ids": []}]
        children = CompositionModes.apply(db_session, parent, 1, mapping_1)
        used_cp_id = children[0].class_parts[0].id
        cleanup_orphaned_class_part(db_session, used_cp_id)
        assert db_session.get(ClassPart, used_cp_id) is not None

    def test_cleanup_drops_class_part_no_longer_referenced_after_reapply(self, db_session):
        from backend.app.models.group import ClassPart
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)

        mapping_1 = [{"teacher_ids": [teachers[0].id], "division_ids": [divisions[0].id], "subject_id": parent.subject_id, "classroom_requirement_ids": []}]
        children_1 = CompositionModes.apply(db_session, parent, 1, mapping_1)
        class_part_id = children_1[0].class_parts[0].id

        # Nouvelle composition sans rapport (mapping par défaut, basé sur des groupes manuels) :
        # la partie de classe générée précédemment n'est plus référencée par rien.
        CompositionModes.apply(db_session, parent, 1, mapping)

        assert db_session.get(ClassPart, class_part_id) is None

    def test_preview_creates_no_class_part_leaves_pending_token_instead(self, db_session):
        # Depuis l'écriture différée (voir composition_mode.py, _resolve_dynamic_part_class avec
        # materialize=False), "Générer l'aperçu" ne crée plus la moindre ClassPart/Partition/Group
        # réelle : une ligne ciblant une division entière reçoit un jeton virtuel dans
        # pending_class_parts, class_part_ids reste vide, et rien n'est ajouté sur le parent.
        from backend.app.models.group import ClassPart, Partition, Group
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        cp_count, partition_count, group_count = (
            db_session.query(ClassPart).count(), db_session.query(Partition).count(), db_session.query(Group).count()
        )

        mapping_1 = [{"teacher_ids": [teachers[0].id], "division_ids": [divisions[0].id], "subject_id": parent.subject_id, "classroom_requirement_ids": []}]
        result = parent.rpc_preview_composition(db_session, 1, mapping_1)
        child_vals = result["children_vals"][0]

        assert child_vals["class_part_ids"] == []
        assert len(child_vals["pending_class_parts"]) == 1
        assert child_vals["pending_class_parts"][0]["division_id"] == divisions[0].id
        assert child_vals["pending_class_parts"][0]["subject_id"] == parent.subject_id
        assert child_vals["pending_summary"] != ""
        assert db_session.query(ClassPart).count() == cp_count
        assert db_session.query(Partition).count() == partition_count
        assert db_session.query(Group).count() == group_count
        assert list(parent.class_parts) == []

    def test_rpc_cancel_composition_is_a_pure_noop(self, db_session):
        # rpc_preview_composition n'ayant plus rien créé (voir test ci-dessus), il n'y a
        # structurellement plus rien à nettoyer — plus de piège possible sur un cours pas encore
        # composé (is_composed=False), qui laissait auparavant fuir des ressources orphelines.
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        simple_parent = Course.create(db_session, {
            "school_id": parent.school_id, "subject_id": parent.subject_id, "duration_minutes": 60,
        })
        assert simple_parent.is_composed is False

        mapping_1 = [{"teacher_ids": [teachers[0].id], "division_ids": [divisions[0].id], "subject_id": parent.subject_id, "classroom_requirement_ids": []}]
        simple_parent.rpc_preview_composition(db_session, 1, mapping_1)
        result = simple_parent.rpc_cancel_composition(db_session)

        assert result == {"status": "ok"}

    def test_preview_regeneration_with_same_mapping_yields_same_token(self, db_session):
        # Idempotence : rouvrir "Générer l'aperçu" avec un mapping inchangé (ex: bouton "Précédent"
        # puis re-soumission) doit produire le même jeton virtuel, jamais un doublon.
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        mapping_1 = [{"teacher_ids": [teachers[0].id], "division_ids": [divisions[0].id], "subject_id": parent.subject_id, "classroom_requirement_ids": []}]

        result_a = parent.rpc_preview_composition(db_session, 1, [dict(row) for row in mapping_1])
        result_b = parent.rpc_preview_composition(db_session, 1, [dict(row) for row in mapping_1])

        token_a = result_a["children_vals"][0]["pending_class_parts"][0]["token"]
        token_b = result_b["children_vals"][0]["pending_class_parts"][0]["token"]
        assert token_a == token_b

    def test_save_composition_materializes_pending_class_part_and_group(self, db_session):
        # rpc_save_composition doit résoudre pour de vrai les jetons pending_* reçus (round-trip
        # depuis un rpc_preview_composition édité par l'utilisateur) — c'est le seul moment où la
        # ClassPart/le Group sont réellement créés.
        from backend.app.models.group import ClassPart, Group
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session, extra_divisions=1)
        mapping_2div = [{
            "teacher_ids": [teachers[0].id],
            "division_ids": [divisions[0].id, divisions[1].id],
            "subject_id": parent.subject_id,
            "classroom_requirement_ids": [],
        }]
        preview = parent.rpc_preview_composition(db_session, 1, mapping_2div)
        child_vals = preview["children_vals"][0]
        assert child_vals["class_part_ids"] == []
        assert len(child_vals["pending_class_parts"]) == 2
        assert child_vals["pending_group"] is not None
        cp_count_before = db_session.query(ClassPart).count()
        group_count_before = db_session.query(Group).count()

        res = parent.rpc_save_composition(db_session, preview["children_vals"])

        assert res["status"] == "ok"
        assert db_session.query(ClassPart).count() == cp_count_before + 2
        assert db_session.query(Group).count() == group_count_before + 1
        child = parent.children[0]
        assert len(child.class_parts) == 2
        assert len(child.groups) == 1
        # La cascade ressources -> parent (Course._cascade_resources_to_parent) doit avoir propagé
        # ces ressources fraîchement matérialisées sur le parent, sans intervention manuelle.
        assert {cp.id for cp in child.class_parts}.issubset({cp.id for cp in parent.class_parts})
        assert {g.id for g in child.groups}.issubset({g.id for g in parent.groups})

    def test_save_composition_single_pending_class_part_without_group(self, db_session):
        # Régression : une ligne à UNE seule division en attente (pending_class_parts non vide,
        # mais pending_group=None puisqu'un seul jeton ne déclenche jamais de groupe) doit pouvoir
        # être sauvegardée — _build_base_vals pose toujours la clé 'pending_group' (valant None
        # quand absente) sur children_vals, que materialize_pending_resources doit retirer même
        # dans ce cas, sous peine de faire échouer Course.create() ("'pending_group' is an invalid
        # keyword argument for Course").
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        mapping_1div = [{
            "teacher_ids": [teachers[0].id],
            "division_ids": [divisions[0].id],
            "subject_id": parent.subject_id,
            "classroom_requirement_ids": [],
        }]
        preview = parent.rpc_preview_composition(db_session, 1, mapping_1div)
        child_vals = preview["children_vals"][0]
        assert len(child_vals["pending_class_parts"]) == 1
        assert child_vals["pending_group"] is None

        res = parent.rpc_save_composition(db_session, preview["children_vals"])

        assert res["status"] == "ok"
        assert len(parent.children[0].class_parts) == 1
        assert parent.children[0].class_parts[0].partition.division_id == divisions[0].id

    def test_course_rpc_compose_by_mode_method(self, db_session):
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        result = parent.compose_by_mode(db_session, mode=1, mapping=mapping)
        assert result["status"] == "ok"
        assert result["count"] == 2

    def test_reapply_new_mode_removes_previous_children(self, db_session):
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        children_1 = CompositionModes.apply(db_session, parent, 1, mapping)
        assert len(children_1) == 2
        children_2 = CompositionModes.apply(db_session, parent, 2, mapping)
        assert len(children_2) == 4
        from sqlalchemy import select
        remaining_ids = db_session.execute(select(Course.id).where(Course.parent_id == parent.id)).scalars().all()
        assert len(remaining_ids) == 4

    def test_get_available_modes_and_validation(self, db_session):
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session, extra_periods=2)
        # Mapping avec 1 ligne : seulement 1 et 2 dispo
        mapping_1_row = [mapping[0]]
        available_1_row = CompositionModes.get_available_modes(db_session, parent, mapping_1_row)
        assert available_1_row == [1, 2]
        
        # Mapping avec 2 lignes et périodes : 1 à 5 + 7, 8, 9 (donc tout sauf 6)
        available_2_rows = CompositionModes.get_available_modes(db_session, parent, mapping)
        assert set(available_2_rows) == {1, 2, 3, 4, 5, 7, 8, 9}
        
        # Test d'exception sur mode impossible
        with pytest.raises(CompositionError) as excinfo:
            CompositionModes.apply(db_session, parent, 3, mapping_1_row)
        assert "pas applicable" in str(excinfo.value)
        
        # Test d'exception sur mapping vide
        with pytest.raises(CompositionError) as excinfo:
            CompositionModes.apply(db_session, parent, 1, [])
        assert "obligatoire" in str(excinfo.value)

    def test_rpc_save_composition_safe_update(self, db_session):
        """Vérifie que rpc_save_composition peut s'exécuter sans provoquer l'erreur de sécurité 'Mise à jour directe interdite'."""
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session, extra_periods=2)
        
        # Simuler les données retournées par l'interface via rpc_preview_composition
        children_vals = [
            {"subject_id": parent.subject_id, "duration_minutes": 30, "teacher_ids": [teachers[0].id], "parent_id": parent.id},
            {"subject_id": parent.subject_id, "duration_minutes": 30, "teacher_ids": [teachers[1].id], "parent_id": parent.id}
        ]
        
        # Exécuter la sauvegarde RPC
        res = parent.rpc_save_composition(db_session, children_vals)
        db_session.flush() # Force le flush pour s'assurer qu'aucune sécurité n'est levée
        
        assert res["status"] == "ok"
        assert res["count"] == 2
        assert len(parent.children) == 2
        # Vérifie que la surcharge métier a bien tourné (is_composed doit être True)
        assert parent.is_composed is True

    def test_rpc_save_composition_syncs_timeslot_and_pin_from_already_placed_parent(self, db_session):
        """
        Régression : les enfants créés par rpc_save_composition sont d'abord créés SANS parent_id
        (voir son commentaire "éviter les flushs conflictuels"), puis rattachés au parent via
        `self.update(db, {"children_ids": [...]})` — un rattachement par id nu qui, jusqu'ici,
        posait la FK parent_id par un setattr direct sur la relation ORM (base.py::
        _apply_owned_collection_commands, juste avant de retourner), sans jamais appeler
        `child.update()`. Conséquence : `Course._sync_vals_from_parent` (qui recopie
        timeslot_id/is_pinned depuis le parent à chaque changement de parent_id) ne se déclenchait
        JAMAIS pour ces enfants — décomposer un cours composé déjà PLACÉ laissait ses nouveaux
        enfants avec timeslot_id=NULL, malgré un parent déjà résolu. Corrigé en incluant
        explicitement la FK dans les vals du rattachement dès qu'elle diffère réellement de la
        valeur courante, pour que child.update() se déclenche et fasse tourner la synchronisation
        normale — comme n'importe quel autre changement de parent_id.
        """
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)

        # Grille couvrant au moins 480-600 (parent.duration_minutes=120, std=30, voir
        # _prepare_parent_course) : Course.validate_placement_conflicts borne la fin de journée à
        # (dernier timeslot.minutes_from_midnight + durée standard), pas à une simple absence de
        # chevauchement — sans les 3 créneaux suivants, le placement du parent lui-même échouerait
        # pour débordement de grille avant même d'atteindre le rattachement testé ici.
        ts = Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": 480})
        for minutes in (510, 540, 570):
            Timeslot.create(db_session, {"day_of_week": 1, "minutes_from_midnight": minutes})
        parent.update(db_session, {"timeslot_id": ts.id, "is_pinned": True})

        children_vals = [
            {"subject_id": parent.subject_id, "duration_minutes": 30, "teacher_ids": [teachers[0].id]},
            {"subject_id": parent.subject_id, "duration_minutes": 30, "teacher_ids": [teachers[1].id]},
        ]
        res = parent.rpc_save_composition(db_session, children_vals)
        db_session.flush()

        assert res["status"] == "ok"
        assert len(parent.children) == 2
        for child in parent.children:
            assert child.parent_timeslot_offset == 0
            assert child.timeslot_id == ts.id, "L'enfant n'a pas hérité du timeslot de son parent déjà placé"
            assert child.is_pinned is True, "L'enfant n'a pas hérité de is_pinned de son parent"


def _make_division(db, code="DIVX"):
    school = db.query(School).first()
    return Division.create(db, {"code": code, "name": f"Division {code}", "student_count": 25, "color": "#CCCCCC", "school_id": school.id})


class TestPartitionSpecialType:
    def test_cannot_be_set_by_user(self, db_session):
        from backend.app.models.group import Partition
        division = _make_division(db_session)
        with pytest.raises(ValueError, match="système"):
            Partition.create(db_session, {"code": "P1", "name": "P1", "division_id": division.id, "special_type": "HALF_GENDER"})
        db_session.rollback()

    def test_settable_via_system_bypass(self, db_session):
        from backend.app.models.group import Partition, PartitionSpecialType
        division = _make_division(db_session)
        partition = Partition.create(db_session, {"code": "P1", "name": "P1", "division_id": division.id, "special_type": PartitionSpecialType.HALF_GENDER, "_system_write": True})
        assert partition.special_type == PartitionSpecialType.HALF_GENDER

    def test_typed_partition_cannot_be_renamed(self, db_session):
        from backend.app.models.group import Partition, PartitionSpecialType
        division = _make_division(db_session)
        partition = Partition.create(db_session, {"code": "P1", "name": "P1", "division_id": division.id, "special_type": PartitionSpecialType.HALF_GENDER, "_system_write": True})
        with pytest.raises(ValueError, match="renommée"):
            partition.update(db_session, {"name": "Nouveau nom"})
        db_session.rollback()

    def test_typed_partition_class_parts_cannot_be_changed_via_update(self, db_session):
        from backend.app.models.group import Partition, PartitionSpecialType
        division = _make_division(db_session)
        partition = Partition.create(db_session, {"code": "P1", "name": "P1", "division_id": division.id, "special_type": PartitionSpecialType.HALF_GENDER, "_system_write": True})
        with pytest.raises(ValueError, match="manuellement"):
            partition.update(db_session, {"class_part_ids": [cp.id for cp in partition.class_parts]})
        db_session.rollback()

    def test_typed_partition_class_part_cannot_be_created_manually(self, db_session):
        from backend.app.models.group import Partition, ClassPart, PartitionSpecialType
        division = _make_division(db_session)
        partition = Partition.create(db_session, {"code": "P1", "name": "P1", "division_id": division.id, "special_type": PartitionSpecialType.HALF_GENDER, "_system_write": True})
        with pytest.raises(ValueError, match="manuellement"):
            ClassPart.create(db_session, {"partition_id": partition.id, "name": "Extra"})
        db_session.rollback()

    def test_typed_partition_class_part_cannot_be_deleted_manually(self, db_session):
        from backend.app.models.group import Partition, ClassPart, PartitionSpecialType
        division = _make_division(db_session)
        partition = Partition.create(db_session, {"code": "P1", "name": "P1", "division_id": division.id, "special_type": PartitionSpecialType.HALF_GENDER, "_system_write": True})
        cp = ClassPart.create(db_session, {"partition_id": partition.id, "name": "Garçons", "_system_write": True})
        with pytest.raises(ValueError, match="manuellement"):
            cp.delete(db_session)
        db_session.rollback()

    def test_deleting_typed_partition_cascades_to_its_class_parts(self, db_session):
        """La contrainte 'pas de retrait manuel' n'empêche pas la suppression de la partition entière (composition)."""
        from backend.app.models.group import Partition, ClassPart, PartitionSpecialType
        division = _make_division(db_session)
        partition = Partition.create(db_session, {"code": "P1", "name": "P1", "division_id": division.id, "special_type": PartitionSpecialType.HALF_GENDER, "_system_write": True})
        cp1 = ClassPart.create(db_session, {"partition_id": partition.id, "name": "Garçons", "_system_write": True})
        cp2 = ClassPart.create(db_session, {"partition_id": partition.id, "name": "Filles", "_system_write": True})
        partition_id, cp1_id, cp2_id = partition.id, cp1.id, cp2.id

        partition.delete(db_session)

        assert db_session.get(Partition, partition_id) is None
        assert db_session.get(ClassPart, cp1_id) is None
        assert db_session.get(ClassPart, cp2_id) is None


class TestClassPartDeleteRestrict:
    def test_cannot_delete_class_part_attached_to_a_course(self, db_session):
        from backend.app.models.group import Partition, ClassPart
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        partition = Partition.create(db_session, {"code": "PX", "name": "PX", "division_id": divisions[0].id})
        cp = ClassPart.create(db_session, {"partition_id": partition.id, "name": "CPX"})
        Course.create(db_session, {
            "school_id": teachers[0].school_id, "subject_id": parent.subject_id, "duration_minutes": 30,
            "teacher_ids": [teachers[0].id], "class_part_ids": [cp.id],
        })

        with pytest.raises(ValueError, match="rattachée à 1 cours"):
            cp.delete(db_session)
        db_session.rollback()

    def test_deleting_partition_cascades_to_its_class_parts(self, db_session):
        """Relation de composition Partition -> ClassPart (voir ForeignKey ondelete=CASCADE)."""
        from backend.app.models.group import Partition, ClassPart
        division = _make_division(db_session)
        partition = Partition.create(db_session, {"code": "PC", "name": "PC", "division_id": division.id})
        cp = ClassPart.create(db_session, {"partition_id": partition.id, "name": "CPC"})
        partition_id, cp_id = partition.id, cp.id

        partition.delete(db_session)

        assert db_session.get(Partition, partition_id) is None
        assert db_session.get(ClassPart, cp_id) is None


class TestFindOrCreatePartition:
    def test_validates_exactly_one_strategy(self, db_session):
        from backend.app.models.group import find_or_create_partition
        division = _make_division(db_session)
        with pytest.raises(ValueError):
            find_or_create_partition(db_session, division.id, "X")
        with pytest.raises(ValueError):
            find_or_create_partition(db_session, division.id, "X", subject_ids=[1], part_count=2)

    def test_by_subjects_creates_then_reuses_by_coverage(self, db_session):
        from backend.app.models.group import find_or_create_partition
        from backend.app.models.discipline import Discipline
        division = _make_division(db_session)
        discipline = Discipline.create(db_session, {"code": "GENX", "name": "GénéralX"})
        s1 = Subject.create(db_session, {"code": "S1", "code_nomenclature": "N1", "short_name": "S1", "name": "Subj1", "discipline_id": discipline.id})
        s2 = Subject.create(db_session, {"code": "S2", "code_nomenclature": "N2", "short_name": "S2", "name": "Subj2", "discipline_id": discipline.id})
        s3 = Subject.create(db_session, {"code": "S3", "code_nomenclature": "N3", "short_name": "S3", "name": "Subj3", "discipline_id": discipline.id})

        partition = find_or_create_partition(db_session, division.id, "Langues", subject_ids=[s1.id, s2.id])
        assert {cp.subject_id for cp in partition.class_parts} == {s1.id, s2.id}

        # s1 seule est déjà couverte par la partition existante (au moins, pas exactement) -> réutilisée
        reused = find_or_create_partition(db_session, division.id, "Langues", subject_ids=[s1.id])
        assert reused.id == partition.id

        # s3 n'est couverte par aucune partition existante -> nouvelle partition
        created = find_or_create_partition(db_session, division.id, "Options", subject_ids=[s3.id])
        assert created.id != partition.id

    def test_by_special_type_creates_then_reuses(self, db_session):
        from backend.app.models.group import find_or_create_partition, PartitionSpecialType
        division = _make_division(db_session)
        partition = find_or_create_partition(db_session, division.id, "ignored", special_type=PartitionSpecialType.HALF_GENDER)
        assert partition.special_type == PartitionSpecialType.HALF_GENDER
        assert {cp.name for cp in partition.class_parts} == {"Garçons", "Filles"}

        reused = find_or_create_partition(db_session, division.id, "ignored", special_type=PartitionSpecialType.HALF_GENDER)
        assert reused.id == partition.id

    def test_by_special_type_half_alpha_names_parts_p1_p2(self, db_session):
        from backend.app.models.group import find_or_create_partition, PartitionSpecialType
        division = _make_division(db_session)
        partition = find_or_create_partition(db_session, division.id, "ignored", special_type=PartitionSpecialType.HALF_ALPHA)
        assert {cp.name for cp in partition.class_parts} == {"P1", "P2"}

    def test_by_part_count_creates_then_reuses(self, db_session):
        from backend.app.models.group import find_or_create_partition
        division = _make_division(db_session)
        partition = find_or_create_partition(db_session, division.id, "Ateliers", part_count=3)
        assert len(partition.class_parts) == 3

        reused = find_or_create_partition(db_session, division.id, "Ateliers", part_count=3)
        assert reused.id == partition.id

        different = find_or_create_partition(db_session, division.id, "Ateliers4", part_count=4)
        assert different.id != partition.id


class TestFindOrCreateGroup:
    def test_exact_match_reuses_regardless_of_order(self, db_session):
        from backend.app.models.group import find_or_create_group, Partition, ClassPart
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        partition = Partition.create(db_session, {"code": "PG", "name": "PG", "division_id": divisions[0].id})
        cp1 = ClassPart.create(db_session, {"partition_id": partition.id, "name": "CP1"})
        cp2 = ClassPart.create(db_session, {"partition_id": partition.id, "name": "CP2"})

        group = find_or_create_group(db_session, [cp1.id, cp2.id], parent.subject_id)
        reused = find_or_create_group(db_session, [cp2.id, cp1.id], parent.subject_id)

        assert reused.id == group.id
        assert group.is_system_generated is True

    def test_no_match_creates_new_group_not_subset_or_superset(self, db_session):
        from backend.app.models.group import find_or_create_group, Partition, ClassPart
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        partition = Partition.create(db_session, {"code": "PG2", "name": "PG2", "division_id": divisions[0].id})
        cp1 = ClassPart.create(db_session, {"partition_id": partition.id, "name": "CP1"})
        cp2 = ClassPart.create(db_session, {"partition_id": partition.id, "name": "CP2"})
        cp3 = ClassPart.create(db_session, {"partition_id": partition.id, "name": "CP3"})

        group_ab = find_or_create_group(db_session, [cp1.id, cp2.id], parent.subject_id)
        group_abc = find_or_create_group(db_session, [cp1.id, cp2.id, cp3.id], parent.subject_id)

        assert group_abc.id != group_ab.id


class TestDefaultCompositionMapping:
    def test_one_row_per_existing_teacher_with_preferred_subject(self, db_session):
        # Course.composition_mapping (course.py) délègue à CompositionModes.default_mapping —
        # bootstrap de l'étape 1 du wizard, une ligne par professeur déjà affecté au cours,
        # matière pré-remplie depuis sa matière préférée (voir GenericWizard.vue,
        # draft = {...props.model}).
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        teachers[0].update(db_session, {"preferred_subject_id": parent.subject_id})

        rows = parent.composition_mapping

        assert len(rows) == len(teachers)
        by_teacher = {row["teacher_ids"][0]: row for row in rows}
        assert by_teacher[teachers[0].id]["subject_id"] == parent.subject_id
        assert by_teacher[teachers[1].id]["subject_id"] is None
        for row in rows:
            assert row["group_ids"] == [] and row["class_part_ids"] == []
            assert row["division_ids"] == [] and row["classroom_ids"] == []

    def test_rows_have_unique_ids(self, db_session):
        # Régression : GenericList.vue suit chaque ligne éditable par item.id (Map d'édition en
        # attente, :key de la boucle de rendu) — sans id unique par ligne, toutes les lignes
        # partagent la même clé `undefined` et éditer une ligne (matière, professeur...) se
        # répercute silencieusement sur toutes les autres.
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session, extra_teachers=2)

        rows = parent.composition_mapping

        assert len(rows) == len(teachers)
        ids = [row["id"] for row in rows]
        assert all(isinstance(i, int) for i in ids)
        assert len(set(ids)) == len(ids), "chaque ligne doit avoir un id unique"

    def test_empty_when_course_has_no_teacher(self, db_session):
        from backend.app.models.discipline import Discipline
        school = db_session.query(School).first()
        discipline = Discipline.create(db_session, {"code": "GENY", "name": "GénéralY"})
        subject = Subject.create(db_session, {"code": "SUBY", "code_nomenclature": "NY", "short_name": "SubY", "name": "SubjY", "discipline_id": discipline.id})
        course = Course.create(db_session, {"school_id": school.id, "subject_id": subject.id, "duration_minutes": 60})
        assert course.composition_mapping == []


class TestCompositionModeOption:
    def test_read_returns_available_modes_filtered_by_course_and_mapping(self, db_session):
        from backend.app.models.composition_mode import CompositionModeOption
        import json
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session, extra_periods=2)

        rows = CompositionModeOption.read(db_session, domain={
            "course_id": str(parent.id),
            "mapping": json.dumps(mapping),
        })

        assert {row.id for row in rows} == {1, 2, 3, 4, 5, 7, 8, 9}
        # "name" (jamais "label") : convention de libellé résolue par SearchableSelect.vue/
        # App.vue::fkOptionsCache (display_name || name || code || id) — voir CompositionModeOption.
        assert all(row.name for row in rows)
        assert all(row.name.startswith(f"{row.id} - ") for row in rows)

    def test_read_without_course_id_returns_empty(self, db_session):
        from backend.app.models.composition_mode import CompositionModeOption
        assert CompositionModeOption.read(db_session, domain={}) == []
        assert CompositionModeOption.read(db_session, domain={"mapping": "[]"}) == []

    def test_read_without_mapping_matches_empty_mapping(self, db_session):
        from backend.app.models.composition_mode import CompositionModeOption
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        assert CompositionModeOption.read(db_session, domain={"course_id": str(parent.id)}) == []
