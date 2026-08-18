"""
Tests du socle d'impression PDF (backend/app/reports/, api/report.py) — voir architecture.md §21.

Deux niveaux, comme prévu par le socle :
- le rendu HTML (`?format=html`) porte les assertions de CONTENU — rapides, et lisibles en cas
  d'échec, là où comparer des octets de PDF n'apprendrait rien ;
- un test par rapport vérifie que le PDF sort réellement (en-tête `%PDF-`), pour attraper une
  régression du moteur de rendu que le HTML ne verrait pas.
"""
import pytest
from sqlalchemy.orm import sessionmaker

from backend.app.models.base import Base, AccessDeniedError
from backend.app.models import (
    Course, Discipline, Division, Mef, MefDivision, RefGrade, School, Student, Subject,
    SystemSetting, Timeslot, User, ResGroup, IrModelAccess,
)
from backend.app.reports import REGISTRY, get_report
from backend.app.reports.base import render_html, render_pdf
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


def _make_courses(db):
    """Une école, deux cours : un placé le lundi 8h, un non placé."""
    school = School.create(db, {"uai": "1234567A", "name": "Collège Victor Hugo"})
    discipline = Discipline.create(db, {"code": "SCI", "name": "Sciences"})
    subject = Subject.create(db, {
        "code": "MATH", "code_nomenclature": "MATH1", "short_name": "Maths",
        "name": "Mathématiques", "discipline_id": discipline.id,
    })
    # Grille de trois créneaux consécutifs : un cours dure 60 min par défaut, et Course valide
    # qu'il ne déborde pas de la fin de la journée (dernier créneau + durée standard).
    timeslot = Timeslot.create(db, {"day_of_week": 1, "minutes_from_midnight": 480})
    for minutes in (510, 540):
        Timeslot.create(db, {"day_of_week": 1, "minutes_from_midnight": minutes})
    placed = Course.create(db, {"subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id})
    unplaced = Course.create(db, {"subject_id": subject.id, "school_id": school.id})
    return school, placed, unplaced


class TestCourseListReport:
    def test_html_contains_course_name_and_schedule(self, db_session):
        _make_courses(db_session)
        html = render_html(get_report("course_list"), db_session, [], {})

        assert "Liste des cours" in html
        assert "Collège Victor Hugo" in html
        assert "Mathématiques" in html    # Course.name, dénormalisé par Course.compute_name()
        assert "Lundi 08h00" in html      # Timeslot.display_name
        assert "Non placé" in html        # le cours sans créneau
        assert "2 cours" in html

    def test_html_uses_course_name_when_set(self, db_session):
        _, placed, _ = _make_courses(db_session)
        placed.update(db_session, {"name": "Soutien mathématiques"})
        html = render_html(get_report("course_list"), db_session, [], {})
        assert "Soutien mathématiques" in html

    def test_unplaced_courses_are_sorted_last(self, db_session):
        _make_courses(db_session)
        html = render_html(get_report("course_list"), db_session, [], {})
        assert html.index("Lundi 08h00") < html.index("Non placé")

    def test_courses_are_sorted_chronologically_not_alphabetically(self, db_session):
        """
        Trier sur le libellé donnerait « Jeudi » avant « Lundi » — un ordre alphabétique des jours,
        qui passe pour un défaut sur une liste imprimée. Le tri porte donc sur (jour, heure).
        """
        school, placed, _ = _make_courses(db_session)
        # Une journée complète, comme pour le lundi : la grille du jeudi doit pouvoir contenir un
        # cours de 60 min (voir _make_courses).
        jeudi = Timeslot.create(db_session, {"day_of_week": 4, "minutes_from_midnight": 480})
        for minutes in (510, 540):
            Timeslot.create(db_session, {"day_of_week": 4, "minutes_from_midnight": minutes})
        subject_id = placed.subject_id
        Course.create(db_session, {"subject_id": subject_id, "school_id": school.id, "timeslot_id": jeudi.id})

        html = render_html(get_report("course_list"), db_session, [], {})
        assert html.index("Lundi 08h00") < html.index("Jeudi 08h00")

    def test_printing_a_single_designated_course_excludes_the_others(self, db_session):
        """
        Portée « enregistrement courant », celle du bouton posé sur le formulaire : demander un
        identifiant précis ne doit ramener QUE celui-là. Une première version imprimait toute la
        liste depuis le formulaire d'un cours — écart constaté au premier usage réel.
        """
        _, placed, unplaced = _make_courses(db_session)
        placed.update(db_session, {"name": "Cours imprimé"})
        unplaced.update(db_session, {"name": "Cours à ne pas imprimer"})

        html = render_html(get_report("course_list"), db_session, [placed.id], {})
        assert "Cours imprimé" in html
        assert "Cours à ne pas imprimer" not in html
        assert "1 cours" in html

    def test_empty_database_renders_a_readable_message(self, db_session):
        html = render_html(get_report("course_list"), db_session, [], {})
        assert "Aucun cours à afficher." in html

    def test_user_input_is_escaped(self, db_session):
        """
        Un nom de cours est une saisie libre et le gabarit est du HTML rendu : sans autoescape,
        une balise saisie par un utilisateur casserait la mise en page du document imprimé.
        """
        _, placed, _ = _make_courses(db_session)
        placed.update(db_session, {"name": "<b>Maths</b>"})
        html = render_html(get_report("course_list"), db_session, [], {})
        assert "<b>Maths</b>" not in html
        assert "&lt;b&gt;Maths&lt;/b&gt;" in html

    def test_pdf_is_actually_produced(self, db_session):
        """Le HTML peut être correct et le rendu PDF cassé (police, CSS non supporté) : on vérifie."""
        _make_courses(db_session)
        pdf = render_pdf(get_report("course_list"), db_session, [], {})
        assert pdf.startswith(b"%PDF-")
        assert len(pdf) > 1000


class TestReportRights:
    """
    Le socle ne fait AUCUN contrôle de droits explicite : `get_values` lit via `read()`/`browse()`,
    donc le moteur de droits s'applique déjà. Ces tests vérifient que c'est bien le cas — c'est la
    seule chose qui empêche un rapport de devenir un contournement du moteur de droits.
    """
    def _restricted_student(self, db):
        school = School.create(db, {"uai": "7654321Z", "name": "Collège Test"})
        division = Division.create(db, {"code": "6A", "name": "6ème A", "school_id": school.id})
        ref_grade = RefGrade.create(db, {"name": "6EME"})
        mef = Mef.create(db, {
            "school_id": school.id, "code_national": "MEF_T", "name": "MEF", "ref_grade_id": ref_grade.id,
            "max_students_per_class": 30, "forecast_student_count": 30,
        })
        MefDivision.create(db, {"mef_id": mef.id, "division_id": division.id, "forecast_student_count": 30})
        student = Student.create(db, {"first_name": "Léa", "last_name": "Martin", "division_id": division.id, "mef_id": mef.id})
        discipline = Discipline.create(db, {"code": "SCI", "name": "Sciences"})
        subject = Subject.create(db, {
            "code": "MATH", "code_nomenclature": "MATH1", "short_name": "Maths",
            "name": "Mathématiques", "discipline_id": discipline.id,
        })
        own = Course.create(db, {"subject_id": subject.id, "school_id": school.id, "division_ids": [division.id]})
        other_division = Division.create(db, {"code": "5A", "name": "5ème A", "school_id": school.id})
        foreign = Course.create(db, {"subject_id": subject.id, "school_id": school.id, "division_ids": [other_division.id]})

        user = User.create(db, {"first_name": "Léa", "last_name": "Martin", "email": None})
        student.update(db, {"user_id": user.id})
        group = ResGroup.create(db, {"name": "Élève"})
        group.update(db, {"user_ids": [user.id]})
        import json
        IrModelAccess.create(db, {
            "model": "courses", "group_id": group.id, "perm_read": True,
            "domain": json.dumps([("divisions.students.user_id", "=", "user.id")]),
        })
        db.klepsydrix_user_id = user.id
        return own, foreign

    def test_report_without_ids_only_shows_accessible_courses(self, db_session):
        """Les deux cours ne se distinguent que par leur division, présente dans `Course.name`."""
        self._restricted_student(db_session)
        html = render_html(get_report("course_list"), db_session, [], {})
        assert "6ème A" in html       # la division de l'élève
        assert "5ème A" not in html   # celle qu'il n'a pas le droit de voir
        assert "1 cours" in html

    def test_school_name_is_omitted_when_not_readable(self, db_session):
        """
        L'élève n'a aucun droit sur `schools` : l'en-tête reste vide plutôt que de révéler le nom
        de l'établissement. Conséquence directe du passage par `School.read()` — le mécanisme
        tient tout seul, sans contrôle spécifique dans le rapport.
        """
        self._restricted_student(db_session)
        html = render_html(get_report("course_list"), db_session, [], {})
        assert "Collège Test" not in html

    def test_report_with_an_inaccessible_id_refuses_rather_than_truncating(self, db_session):
        """
        Le point qui justifie `browse()` : produire un PDF de 1 cours quand 2 ont été demandés
        serait un document incomplet d'apparence complète, indétectable par son lecteur.
        """
        own, foreign = self._restricted_student(db_session)
        with pytest.raises(AccessDeniedError):
            render_html(get_report("course_list"), db_session, [own.id, foreign.id], {})


class TestRegistry:
    def test_every_registered_report_has_a_coherent_definition(self):
        """
        Attrape à moindre frais l'erreur d'inattention typique d'un ajout de rapport : clé du
        registre désaccordée du nom, format papier inexistant, gabarit absent du dossier.
        """
        from backend.app.reports.base import PAPERFORMATS, TEMPLATES_DIR

        assert REGISTRY, "Le registre ne doit pas être vide."
        for key, report in REGISTRY.items():
            assert key == report.name
            assert report.paperformat in PAPERFORMATS
            assert (TEMPLATES_DIR / report.template).exists()
            assert hasattr(report.model, "__tablename__")
