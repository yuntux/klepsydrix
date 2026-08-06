"""
Tests pour les 9 modes de composition des cours complexes.
"""
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.models.base import Base
from backend.app.models import (
    School, Teacher, Subject, Division, Classroom,
    Period, PeriodType, Group, Course, SystemSetting
)
from backend.app.models.composition_mode import CompositionModes, CompositionError

TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(TEST_DATABASE_URL, echo=False)
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
        'classroom_ids': [r.id for r in classrooms],
        'division_ids': [d.id for d in divisions],
        'group_ids': [g.id for g in groups_gen],
        'period_ids': [p.id for p in periods],
        'period_type_id': period_type.id if period_type else None,
    })
    
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
        assert len(children[0].classrooms) == 1
        assert len(children[1].classrooms) == 1
        assert children[0].classrooms[0].id != children[1].classrooms[0].id
        assert children[0].teachers[0].id == teachers[0].id
        assert children[1].teachers[0].id == teachers[1].id

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
        mapping.append({"teacher_ids": [teachers[2].id], "group_ids": [groups[2].id], "classroom_ids": [], "subject_id": parent.subject_id})
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
            {"teacher_ids": [teachers[0].id], "group_ids": [groups[0].id], "classroom_ids": [], "subject_id": parent.subject_id},
            {"teacher_ids": [teachers[1].id], "group_ids": [groups[0].id], "classroom_ids": [], "subject_id": parent.subject_id}
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
            {"teacher_ids": [teachers[0].id, teachers[1].id], "group_ids": [groups[0].id], "classroom_ids": [], "subject_id": parent.subject_id}
        ]
        # Application du Mode 1
        children = CompositionModes.apply(db_session, parent, 1, mapping_coteaching)
        assert len(children) == 1
        assert len(children[0].teachers) == 2
        # Vérification de l'ordre ou de la présence des IDs
        child_teacher_ids = {t.id for t in children[0].teachers}
        assert child_teacher_ids == {teachers[0].id, teachers[1].id}
        # Plusieurs profs sur la ligne => enfant marqué en co-enseignement, ce qui doit
        # empêcher _compute_is_composed de le marquer à tort comme composé (voir course.py).
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
            {"teacher_ids": [teachers[0].id, teachers[2].id], "group_ids": [groups[0].id], "classroom_ids": [], "subject_id": parent.subject_id},
            {"teacher_ids": [teachers[1].id], "group_ids": [groups[1].id], "classroom_ids": [], "subject_id": parent.subject_id},
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
            {"teacher_ids": [teachers[0].id], "class_part_ids": [cp1.id, cp2.id], "classroom_ids": [], "subject_id": parent.subject_id}
        ]
        
        children = CompositionModes.apply(db_session, parent, 1, mapping_dynamic)
        
        assert len(children) == 1
        # Le cours enfant ne doit pas avoir de class_parts en direct (vidé par le resolveur)
        assert len(children[0].class_parts) == 0
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

        mapping_1 = [{"teacher_ids": [teachers[0].id], "division_ids": [divisions[0].id], "subject_id": other_subject.id, "classroom_ids": []}]
        children_1 = CompositionModes.apply(db_session, parent, 1, mapping_1)
        assert len(children_1) == 1
        assert len(children_1[0].class_parts) == 1
        # Une seule partie de classe : rattachement direct, pas de groupe dédié généré.
        assert len(children_1[0].groups) == 0
        # Nommée {code division}{séparateur}{code matière}{numéro} (matière de la LIGNE, pas celle du parent).
        assert children_1[0].class_parts[0].name == f"{divisions[0].code}P{other_subject.code}1"
        assert children_1[0].class_parts[0].subject_id == other_subject.id
        # La Partition porte la matière "chapeau" du parent (désignée), pas celle de la ligne.
        parent_subject = db_session.get(Subject, subject_id)
        assert children_1[0].class_parts[0].partition.name == parent_subject.code

        mapping_2 = [{"teacher_ids": [teachers[1].id], "division_ids": [divisions[0].id], "subject_id": other_subject.id, "classroom_ids": []}]
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

        mapping_1 = [{"teacher_ids": [teachers[0].id], "division_ids": [divisions[0].id], "subject_id": parent.subject_id, "classroom_ids": []}]
        children_1 = CompositionModes.apply(db_session, parent, 1, mapping_1)
        assert children_1[0].class_parts[0].name == "XA"

        from backend.app.models.subject import Subject
        discipline_id = db_session.query(Subject).first().discipline_id
        other_subject = Subject.create(db_session, {"code": "AUTREMAT", "code_nomenclature": "NY", "short_name": "AutreMat", "name": "Autre matière", "discipline_id": discipline_id})
        mapping_2 = [{"teacher_ids": [teachers[1].id], "division_ids": [divisions[0].id], "subject_id": other_subject.id, "classroom_ids": []}]
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
            "classroom_ids": [],
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
            {"teacher_ids": [teachers[0].id], "division_ids": [divisions[0].id], "subject_id": subjects[0].id, "classroom_ids": []},
            {"teacher_ids": [teachers[1].id], "division_ids": [divisions[0].id], "subject_id": subjects[1].id, "classroom_ids": []},
        ]
        children = CompositionModes.apply(db_session, parent, 1, mapping_pole)
        assert len(children) == 2
        cp_a = children[0].class_parts[0]
        cp_b = children[1].class_parts[0]
        assert cp_a.partition_id == cp_b.partition_id
        assert cp_a.partition.name == f"{subjects[0].code}+{subjects[1].code}"

    def test_cleanup_cascades_through_group_and_partitions_when_child_deleted(self, db_session):
        # Une ligne à 2 divisions génère 2 parties de classe (1 par division, donc 2 partitions
        # distinctes) regroupées dans un groupe auto (_resolve_dynamic_groups) : l'enfant ne
        # référence donc que le groupe, pas les parties de classe directement. Supprimer cet
        # enfant doit malgré tout nettoyer les 2 parties, le groupe, et les 2 partitions.
        from backend.app.models.group import ClassPart, Group, Partition
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session, extra_divisions=1)

        mapping_multi_division = [{
            "teacher_ids": [teachers[0].id],
            "division_ids": [divisions[0].id, divisions[1].id],
            "subject_id": parent.subject_id,
            "classroom_ids": [],
        }]
        children = CompositionModes.apply(db_session, parent, 1, mapping_multi_division)
        assert len(children) == 1
        child = children[0]
        assert len(child.class_parts) == 0
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
        mapping_1 = [{"teacher_ids": [teachers[0].id], "division_ids": [divisions[0].id], "subject_id": parent.subject_id, "classroom_ids": []}]
        children = CompositionModes.apply(db_session, parent, 1, mapping_1)
        used_cp_id = children[0].class_parts[0].id
        cleanup_orphaned_class_part(db_session, used_cp_id)
        assert db_session.get(ClassPart, used_cp_id) is not None

    def test_cleanup_drops_class_part_no_longer_referenced_after_reapply(self, db_session):
        from backend.app.models.group import ClassPart
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)

        mapping_1 = [{"teacher_ids": [teachers[0].id], "division_ids": [divisions[0].id], "subject_id": parent.subject_id, "classroom_ids": []}]
        children_1 = CompositionModes.apply(db_session, parent, 1, mapping_1)
        class_part_id = children_1[0].class_parts[0].id

        # Nouvelle composition sans rapport (mapping par défaut, basé sur des groupes manuels) :
        # la partie de classe générée précédemment n'est plus référencée par rien.
        CompositionModes.apply(db_session, parent, 1, mapping)

        assert db_session.get(ClassPart, class_part_id) is None

    def test_rpc_cancel_composition_cleans_up_unsaved_preview_resources(self, db_session):
        from backend.app.models.group import ClassPart
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)

        mapping_1 = [{"teacher_ids": [teachers[0].id], "division_ids": [divisions[0].id], "subject_id": parent.subject_id, "classroom_ids": []}]
        result = parent.rpc_preview_composition(db_session, 1, mapping_1)
        class_part_id = result["children_vals"][0]["class_part_ids"][0]
        assert db_session.get(ClassPart, class_part_id) is not None

        parent.rpc_cancel_composition(db_session)

        assert db_session.get(ClassPart, class_part_id) is None

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
