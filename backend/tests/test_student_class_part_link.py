"""
Tests pour StudentClassPartLink (backend/app/models/student.py) — remplace l'ancienne table de
jointure Many-to-Many `student_class_parts` par un historique daté (begin_date/end_date), pour
qu'un élève puisse quitter une partie de classe puis y revenir plus tard.
"""
from datetime import date
import pytest
from sqlalchemy.orm import sessionmaker
from backend.app.models.base import Base
from backend.app.models import (
    School, Division, Mef, MefDivision, RefGrade, SystemSetting, Student, Subject, Discipline,
)
from backend.app.models.group import Partition, ClassPart, Group, ClassPartLink
from backend.app.models.student import StudentClassPartLink
from backend.tests.db_test_utils import make_test_engine

test_engine = make_test_engine()
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        SystemSetting.create(db, {"key": "STANDARD_TIMESLOT_DURATION", "value": "30"})
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


def _scaffold(db):
    """
    École + division + MEF liés + deux partitions dans la même division (Langues :
    Allemand/Anglais ; Sport : Foot), plus une partie de classe d'une AUTRE division (Espagnol).
    Deux partitions distinctes dans la même division permettent de tester ClassPartLink (qui
    refuse de lier deux parties d'une même partition, voir _check_partition_overlap).
    """
    school = School.create(db, {"uai": "1234567A", "name": "Collège Test"})
    ref_grade = RefGrade.create(db, {"name": "6EME"})
    mef = Mef.create(db, {
        "school_id": school.id, "code_national": "MEF_TEST", "name": "MEF", "ref_grade_id": ref_grade.id,
        "max_students_per_class": 30, "forecast_student_count": 30,
    })
    division = Division.create(db, {"code": "6A", "name": "6ème A", "school_id": school.id})
    MefDivision.create(db, {"mef_id": mef.id, "division_id": division.id, "forecast_student_count": 30})
    partition = Partition.create(db, {"code": "6A-LV", "name": "Langues", "division_id": division.id})
    allemand = ClassPart.create(db, {"partition_id": partition.id, "name": "Allemand"})
    anglais = ClassPart.create(db, {"partition_id": partition.id, "name": "Anglais"})
    sport_partition = Partition.create(db, {"code": "6A-SPORT", "name": "Sport", "division_id": division.id})
    foot = ClassPart.create(db, {"partition_id": sport_partition.id, "name": "Foot"})
    autre_division = Division.create(db, {"code": "6B", "name": "6ème B", "school_id": school.id})
    autre_partition = Partition.create(db, {"code": "6B-LV", "name": "Langues", "division_id": autre_division.id})
    ailleurs = ClassPart.create(db, {"partition_id": autre_partition.id, "name": "Espagnol"})
    student = Student.create(db, {"first_name": "Léa", "last_name": "Martin", "division_id": division.id, "mef_id": mef.id})
    return {
        "school": school, "division": division, "mef": mef, "partition": partition,
        "allemand": allemand, "anglais": anglais, "foot": foot, "ailleurs": ailleurs, "student": student,
    }


class TestUniciteEtHistorique:
    def test_deux_liens_meme_triplet_refuses(self, db_session):
        ctx = _scaffold(db_session)
        StudentClassPartLink.create(db_session, {
            "student_id": ctx["student"].id, "class_part_id": ctx["allemand"].id,
            "begin_date": date(2026, 9, 2), "end_date": date(2026, 10, 1),
        })
        with pytest.raises(ValueError):
            StudentClassPartLink.create(db_session, {
                "student_id": ctx["student"].id, "class_part_id": ctx["allemand"].id,
                "begin_date": date(2026, 9, 2),
            })

    def test_meme_couple_avec_begin_date_differente_autorise_un_retour(self, db_session):
        """Un élève qui quitte une partie de classe (lien clos) peut y revenir plus tard : deux
        lignes pour le même (student_id, class_part_id), begin_date différente."""
        ctx = _scaffold(db_session)
        StudentClassPartLink.create(db_session, {
            "student_id": ctx["student"].id, "class_part_id": ctx["allemand"].id,
            "begin_date": date(2026, 9, 2), "end_date": date(2026, 10, 1),
        })
        retour = StudentClassPartLink.create(db_session, {
            "student_id": ctx["student"].id, "class_part_id": ctx["allemand"].id,
            "begin_date": date(2026, 11, 2),
        })
        assert retour.end_date is None
        assert db_session.query(StudentClassPartLink).filter(
            StudentClassPartLink.student_id == ctx["student"].id,
            StudentClassPartLink.class_part_id == ctx["allemand"].id,
        ).count() == 2

    def test_deux_liens_ouverts_simultanement_refuses(self, db_session):
        """Deux liens ouverts vers la MÊME partie de classe : bloqué. La partition étant elle
        aussi partagée (avec elle-même), _check_coherence_when_active peut lever la première —
        peu importe laquelle des deux diagnostics valides s'exprime, seul compte le refus."""
        ctx = _scaffold(db_session)
        StudentClassPartLink.create(db_session, {
            "student_id": ctx["student"].id, "class_part_id": ctx["allemand"].id, "begin_date": date(2026, 9, 2),
        })
        with pytest.raises(ValueError):
            StudentClassPartLink.create(db_session, {
                "student_id": ctx["student"].id, "class_part_id": ctx["allemand"].id, "begin_date": date(2026, 10, 15),
            })

    def test_fermer_puis_rouvrir_fonctionne(self, db_session):
        ctx = _scaffold(db_session)
        lien = StudentClassPartLink.create(db_session, {
            "student_id": ctx["student"].id, "class_part_id": ctx["allemand"].id, "begin_date": date(2026, 9, 2),
        })
        lien.update(db_session, {"end_date": date(2026, 10, 1)})
        StudentClassPartLink.create(db_session, {
            "student_id": ctx["student"].id, "class_part_id": ctx["allemand"].id, "begin_date": date(2026, 11, 2),
        })
        assert db_session.query(StudentClassPartLink).filter(
            StudentClassPartLink.student_id == ctx["student"].id,
            StudentClassPartLink.class_part_id == ctx["allemand"].id,
            StudentClassPartLink.end_date.is_(None),
        ).count() == 1

    def test_date_fin_avant_date_debut_refusee(self, db_session):
        ctx = _scaffold(db_session)
        with pytest.raises(ValueError, match="postérieure ou égale"):
            StudentClassPartLink.create(db_session, {
                "student_id": ctx["student"].id, "class_part_id": ctx["allemand"].id,
                "begin_date": date(2026, 9, 2), "end_date": date(2026, 8, 1),
            })


class TestAppartenanceActuelle:
    def test_class_parts_ignore_les_liens_clos(self, db_session):
        ctx = _scaffold(db_session)
        StudentClassPartLink.create(db_session, {
            "student_id": ctx["student"].id, "class_part_id": ctx["allemand"].id,
            "begin_date": date(2026, 9, 2), "end_date": date(2026, 10, 1),
        })
        StudentClassPartLink.create(db_session, {
            "student_id": ctx["student"].id, "class_part_id": ctx["anglais"].id, "begin_date": date(2026, 9, 2),
        })
        db_session.refresh(ctx["student"])
        actives = ctx["student"].class_parts
        assert ctx["anglais"] in actives
        assert ctx["allemand"] not in actives

    def test_students_symetrique(self, db_session):
        ctx = _scaffold(db_session)
        StudentClassPartLink.create(db_session, {
            "student_id": ctx["student"].id, "class_part_id": ctx["allemand"].id, "begin_date": date(2026, 9, 2),
        })
        db_session.refresh(ctx["allemand"])
        assert ctx["student"] in ctx["allemand"].students


class TestCoherenceEleve:
    def test_deux_parties_actives_de_la_meme_partition_refusees(self, db_session):
        ctx = _scaffold(db_session)
        StudentClassPartLink.create(db_session, {
            "student_id": ctx["student"].id, "class_part_id": ctx["allemand"].id, "begin_date": date(2026, 9, 2),
        })
        with pytest.raises(ValueError, match="deux parties de la même partition"):
            StudentClassPartLink.create(db_session, {
                "student_id": ctx["student"].id, "class_part_id": ctx["anglais"].id, "begin_date": date(2026, 9, 2),
            })

    def test_partie_d_une_autre_division_refusee_si_active(self, db_session):
        ctx = _scaffold(db_session)
        with pytest.raises(ValueError, match="autre division"):
            StudentClassPartLink.create(db_session, {
                "student_id": ctx["student"].id, "class_part_id": ctx["ailleurs"].id, "begin_date": date(2026, 9, 2),
            })

    def test_lien_clos_vers_une_autre_division_n_est_pas_bloquant(self, db_session):
        """Un lien historique (clos) peut légitimement pointer vers une division que l'élève a
        quittée depuis — la cohérence ne porte que sur les liens actifs (voir student.py)."""
        ctx = _scaffold(db_session)
        # Créé déjà clos : ne viole jamais la contrainte, puisque celle-ci ne lit que les liens
        # actifs (end_date NULL) au moment de la vérification.
        lien = StudentClassPartLink.create(db_session, {
            "student_id": ctx["student"].id, "class_part_id": ctx["allemand"].id,
            "begin_date": date(2026, 9, 2), "end_date": date(2026, 10, 1),
        })
        assert lien.end_date is not None


def _auto_link(db, cp_a, cp_b) -> ClassPartLink:
    """Le lien Allemand<->Foot (deux partitions distinctes de la même division) est généré
    automatiquement à la création de `foot` (voir ClassPart._auto_generate_links) — on le
    retrouve, on ne le recrée pas (la contrainte d'unicité du couple le refuserait)."""
    a_id, b_id = min(cp_a.id, cp_b.id), max(cp_a.id, cp_b.id)
    link = db.query(ClassPartLink).filter_by(class_part_a_id=a_id, class_part_b_id=b_id).first()
    assert link is not None, "lien système attendu, absent — _auto_generate_links a-t-il changé ?"
    return link


class TestSuppressionClassPartLink:
    def test_suppression_bloquee_si_eleves_communs_actifs(self, db_session):
        ctx = _scaffold(db_session)
        # Allemand (partition Langues) et Foot (partition Sport) : deux partitions distinctes de
        # la MÊME division, seul cas que ClassPartLink accepte de lier (voir _check_partition_overlap).
        cpl = _auto_link(db_session, ctx["allemand"], ctx["foot"])
        StudentClassPartLink.create(db_session, {
            "student_id": ctx["student"].id, "class_part_id": ctx["allemand"].id, "begin_date": date(2026, 9, 2),
        })
        StudentClassPartLink.create(db_session, {
            "student_id": ctx["student"].id, "class_part_id": ctx["foot"].id, "begin_date": date(2026, 9, 2),
        })
        with pytest.raises(ValueError, match="Impossible de supprimer"):
            cpl.delete(db_session)

    def test_suppression_autorisee_sans_eleve_commun(self, db_session):
        ctx = _scaffold(db_session)
        cpl = _auto_link(db_session, ctx["allemand"], ctx["foot"])
        eleve2 = Student.create(db_session, {
            "first_name": "Tom", "last_name": "Petit", "division_id": ctx["division"].id, "mef_id": ctx["mef"].id,
        })
        StudentClassPartLink.create(db_session, {
            "student_id": ctx["student"].id, "class_part_id": ctx["allemand"].id, "begin_date": date(2026, 9, 2),
        })
        StudentClassPartLink.create(db_session, {
            "student_id": eleve2.id, "class_part_id": ctx["foot"].id, "begin_date": date(2026, 9, 2),
        })
        cpl.delete(db_session)  # ne lève pas : aucun élève commun aux deux parties

    def test_suppression_autorisee_si_l_eleve_commun_a_un_lien_clos(self, db_session):
        """Un élève qui a fréquenté les deux parties à des moments distincts (un lien clos, un
        lien ouvert) ne fait pas obstacle à la suppression — seul un chevauchement ACTUEL bloque."""
        ctx = _scaffold(db_session)
        cpl = _auto_link(db_session, ctx["allemand"], ctx["foot"])
        StudentClassPartLink.create(db_session, {
            "student_id": ctx["student"].id, "class_part_id": ctx["allemand"].id,
            "begin_date": date(2026, 9, 2), "end_date": date(2026, 10, 1),
        })
        StudentClassPartLink.create(db_session, {
            "student_id": ctx["student"].id, "class_part_id": ctx["foot"].id, "begin_date": date(2026, 9, 2),
        })
        cpl.delete(db_session)  # ne lève pas : le lien vers Allemand est clos
