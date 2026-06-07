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
    groups_gen = [Group.create(db, {"code": f"G{i}", "name": f"Group{i}"}) for i in range(2 + extra_groups)]

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
        {"teacher_ids": [teachers[0].id], "group_ids": [groups_gen[0].id], "classroom_ids": [classrooms[0].id]},
        {"teacher_ids": [teachers[1].id], "group_ids": [groups_gen[1].id], "classroom_ids": [classrooms[1].id]}
    ]

    return parent, teachers, groups_gen, divisions, periods, mock_mapping

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
        mapping.append({"teacher_ids": [teachers[2].id], "group_ids": [groups[2].id], "classroom_ids": []})
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
            {"teacher_ids": [teachers[0].id], "group_ids": [groups[0].id], "classroom_ids": []},
            {"teacher_ids": [teachers[1].id], "group_ids": [groups[0].id], "classroom_ids": []}
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
            {"teacher_ids": [teachers[0].id, teachers[1].id], "group_ids": [groups[0].id], "classroom_ids": []}
        ]
        # Application du Mode 1
        children = CompositionModes.apply(db_session, parent, 1, mapping_coteaching)
        assert len(children) == 1
        assert len(children[0].teachers) == 2
        # Vérification de l'ordre ou de la présence des IDs
        child_teacher_ids = {t.id for t in children[0].teachers}
        assert child_teacher_ids == {teachers[0].id, teachers[1].id}

    def test_dynamic_group_resolution(self, db_session):
        # Validation que plusieurs class_part_ids génèrent un groupe
        from backend.app.models.group import Partition, ClassPart
        parent, teachers, groups, divisions, periods, mapping = _prepare_parent_course(db_session)
        
        partition = Partition.create(db_session, {"code": "PART1", "name": "Test Part", "division_id": divisions[0].id})
        cp1 = ClassPart.create(db_session, {"code": "CP1", "name": "P1", "partition_id": partition.id})
        cp2 = ClassPart.create(db_session, {"code": "CP2", "name": "P2", "partition_id": partition.id})
        
        mapping_dynamic = [
            {"teacher_ids": [teachers[0].id], "class_part_ids": [cp1.id, cp2.id], "classroom_ids": []}
        ]
        
        children = CompositionModes.apply(db_session, parent, 1, mapping_dynamic)
        
        assert len(children) == 1
        # Le cours enfant ne doit pas avoir de class_parts en direct (vidé par le resolveur)
        assert len(children[0].class_parts) == 0
        # Mais il doit avoir un groupe auto-généré
        assert len(children[0].groups) == 1
        assert "Auto" in children[0].groups[0].name
        
        # Les parties de classe sont bien dans le groupe
        group_cp_ids = {cp.id for cp in children[0].groups[0].class_parts}
        assert group_cp_ids == {cp1.id, cp2.id}


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
