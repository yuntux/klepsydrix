"""
Tests du rapport « Grille d'emploi du temps » (backend/app/reports/timetable.py) — voir
test_reports.py pour le socle générique déjà couvert (registre, droits, escaping...). Se concentre
ici sur ce qui est spécifique à ce rapport : résolution des cours par ressource (7 modèles),
exclusion des cours composés/non placés, rotation des jours, règle de couleur, et la géométrie de
la grille (jours sans créneau masqués, cases inactives grisées, hauteur des cours proportionnelle à
leur durée, trait de récréation, suppression du séparateur horaire, contenu des boîtes de cours).
"""
import json

import pytest
import weasyprint
from sqlalchemy.orm import sessionmaker

from backend.app.models.base import Base
from backend.app.models import (
    Course, Discipline, Division, GridDaySettings, Material, NonTeachingStaff, School, Subject,
    SystemSetting, Teacher, Timeslot,
)
from backend.app.reports import REGISTRY, get_report
from backend.app.reports.base import TEMPLATES_DIR, render_html, render_pdf
from backend.tests.db_test_utils import make_test_engine

test_engine = make_test_engine()
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        SystemSetting.create(db, {"key": "STANDARD_TIMESLOT_DURATION", "value": "30"})
        # Les 7 lignes de grid_day_settings (une par jour) sont fixées à l'initialisation de la
        # base — GridDaySettings.create() les refuse (voir test_grid_settings.py, même patron
        # d'insertion brute). Nécessaire à Timeslot.intraday_sequence_number (donc à l'axe des
        # lignes de la grille, voir timetable.py::_sequence_rows) : sans ça min_start reste None
        # et aucune ligne ne sortirait, contrairement à course_list.py qui n'en dépend pas.
        for day_of_week in range(1, 8):
            db.execute(Base.metadata.tables["grid_day_settings"].insert().values(day_of_week=day_of_week))
        db.commit()
        # Lundi : journée complète (4 créneaux de 30 min, 8h-10h) -> séquences 1..4.
        monday_settings = db.query(GridDaySettings).filter(GridDaySettings.day_of_week == 1).first()
        monday_settings.update(db, {
            "hour_day_start_minutes_after_midnight": 480, "hour_day_end_minutes_after_midnight": 600,
        })
        # Mercredi : demi-journée (8h-9h seulement) -> séquences 1..2 seulement. Les séquences 3 et
        # 4 (qui EXISTENT côté lundi) restent donc sans créneau mercredi : la case correspondante
        # doit apparaître grisée sur la grille de mercredi (voir TestTimetableInactiveCells).
        wednesday_settings = db.query(GridDaySettings).filter(GridDaySettings.day_of_week == 3).first()
        wednesday_settings.update(db, {
            "hour_day_start_minutes_after_midnight": 480, "hour_day_end_minutes_after_midnight": 540,
        })
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


def _make_base(db):
    school = School.create(db, {"uai": "1234567A", "name": "Collège Victor Hugo"})
    discipline = Discipline.create(db, {"code": "SCI", "name": "Sciences"})
    subject = Subject.create(db, {
        "code": "MATH", "code_nomenclature": "MATH1", "short_name": "Maths",
        "name": "Mathématiques", "discipline_id": discipline.id, "color": "#ff0000",
    })
    teacher = Teacher.create(db, {"code": "T1", "first_name": "Marc", "last_name": "Dupont", "school_id": school.id})
    division = Division.create(db, {"code": "6A", "name": "6ème A", "school_id": school.id, "color": "#00ff00"})
    # Déjà auto-créé par la réconciliation différentielle des créneaux (GridDaySettings ->
    # Timeslot.update_timeslot_on_weekgrid_change, voir la fixture db_session) — le recréer ici
    # violerait la contrainte d'unicité (day_of_week, minutes_from_midnight).
    timeslot = db.query(Timeslot).filter(Timeslot.day_of_week == 1, Timeslot.minutes_from_midnight == 480).one()
    return school, subject, teacher, division, timeslot


def _body(html: str) -> str:
    """Coupe l'en-tête <style> du gabarit — sans ça, un nom de classe CSS (ex: .timetable-course-
    box { ... }) fausse tout comptage d'occurrences dans le HTML réellement rendu."""
    return html[html.find("<body>"):]


def _page_count(report, db, ids, params=None) -> int:
    """Nombre de pages RÉELLEMENT produites — un test sur le HTML rendu ne révèle aucun
    débordement de pagination (les pages n'existent qu'après la mise en page WeasyPrint). Même
    appel que render_pdf() (reports/base.py) mais arrêté à .render() : pas de dépendance
    supplémentaire, WeasyPrint expose déjà le nombre de pages avant l'écriture du PDF."""
    html = render_html(report, db, ids, params or {})
    return len(weasyprint.HTML(string=html, base_url=str(TEMPLATES_DIR)).render().pages)


_DAY_COL_MARKER = '<div class="timetable-day-col">'


def _hour_col_html(html: str) -> str:
    """Fragment de .timetable-hour-col (première page, jusqu'au premier .timetable-day-col qui le
    suit dans le flux) — sans jour, ses séparateurs suivent seulement show_divider_after (voir
    timetable.py::_day_lines), jamais filtrés par jour."""
    start = html.index('<div class="timetable-hour-col">')
    end = html.index(_DAY_COL_MARKER)
    return html[start:end]


def _day_col_html(html: str, day_index: int = 0) -> str:
    """Fragment du (day_index)-ième .timetable-day-col (première page) — jusqu'au .timetable-day-col
    suivant, ou jusqu'à la fin de la chaîne pour le dernier (légèrement trop large dans ce cas, mais
    sans effet : rien d'autre après ne contient de séparateur/récréation/boîte de cours à tort)."""
    starts = []
    pos = -1
    while True:
        pos = html.find(_DAY_COL_MARKER, pos + 1)
        if pos == -1:
            break
        starts.append(pos)
    start = starts[day_index]
    end = starts[day_index + 1] if day_index + 1 < len(starts) else len(html)
    return html[start:end]


class TestTimetableRegistry:
    def test_all_seven_resources_registered_on_the_shared_template(self):
        expected = {
            "timetable_teacher": "Teacher",
            "timetable_non_teaching_staff": "NonTeachingStaff",
            "timetable_classroom": "Classroom",
            "timetable_material": "Material",
            "timetable_division": "Division",
            "timetable_group": "Group",
            "timetable_class_part": "ClassPart",
        }
        for name, model_name in expected.items():
            report = REGISTRY[name]
            assert report.model.__name__ == model_name
            assert report.template == "timetable.html"
            assert report.paperformat == "a4-landscape"
            assert report.extra_css == "timetable.css"
            # document_title supprime le <h1> générique (chaque page rend son propre en-tête
            # compact, voir timetable.html) — voir TestTimetableTitle pour l'effet observable.
            assert report.document_title is not None
            assert report.document_title(None, []) == ""


class TestTimetableCourseResolution:
    def test_leaf_placed_course_appears_on_teacher_timetable(self, db_session):
        school, subject, teacher, division, timeslot = _make_base(db_session)
        course = Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })

        # course.name est dénormalisé, recomposé par Course.compute_name() — jamais la valeur
        # passée à create() (voir course_list.py, même remarque).
        html = render_html(get_report("timetable_teacher"), db_session, [teacher.id], {})
        assert _body(html).count("timetable-course-box") == 1

    def test_composed_parent_course_is_excluded(self, db_session):
        """Un cours composé (is_composed=True, un cours PARENT) n'a pas d'horaire propre à
        imprimer — seuls les cours feuilles (sans enfant) apparaissent sur la grille. C'est le
        SEUL cours du professeur ici : la grille doit rester entièrement vide."""
        school, subject, teacher, division, timeslot = _make_base(db_session)
        parent = Course.create(db_session, {
            "school_id": school.id, "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        parent.update(db_session, {"is_composed": True, "timeslot_id": timeslot.id})

        html = render_html(get_report("timetable_teacher"), db_session, [teacher.id], {})
        assert "timetable-course-box" not in _body(html)

    def test_unplaced_course_is_excluded(self, db_session):
        """Idem, avec un cours feuille valide mais sans timeslot_id — seul cours du professeur."""
        school, subject, teacher, division, _timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })

        html = render_html(get_report("timetable_teacher"), db_session, [teacher.id], {})
        assert "timetable-course-box" not in _body(html)

    def test_resource_without_any_course_renders_an_empty_grid(self, db_session):
        school = School.create(db_session, {"uai": "9999999A", "name": "École Vide"})
        staff = NonTeachingStaff.create(db_session, {
            "first_name": "Jean", "last_name": "Sans-Cours", "role": "AESH", "school_id": school.id,
        })
        html = render_html(get_report("timetable_non_teaching_staff"), db_session, [staff.id], {})
        assert staff.display_name in html
        assert "timetable-body-row" in html
        assert "timetable-course-box" not in _body(html)


class TestTimetableDayColumns:
    def test_day_header_respects_first_day_of_the_week(self, db_session):
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        SystemSetting.create(db_session, {"key": "FIRST_DAY_OF_THE_WEEK", "value": "3"})  # Mercredi

        html = render_html(get_report("timetable_teacher"), db_session, [teacher.id], {})
        assert html.index("Mercredi") < html.index("Lundi")

    def test_days_without_any_timeslot_are_not_shown(self, db_session):
        """Seuls lundi et mercredi ont des GridDaySettings ouverts dans la fixture — aucun autre
        jour ne doit apparaître, comme sur la grille écran (useTimeslotGrid.ts::days)."""
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        html = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        assert html.count("Lundi") == 1
        assert html.count("Mercredi") == 1
        for absent_day in ("Mardi", "Jeudi", "Vendredi", "Samedi", "Dimanche"):
            assert absent_day not in html


class TestTimetableInactiveCells:
    def test_missing_timeslot_on_a_day_renders_a_greyed_block(self, db_session):
        """Mercredi n'est ouvert que 8h-9h (séquences 1-2) alors que lundi va jusqu'à 10h
        (séquences 1-4) : les séquences 3-4 doivent apparaître grisées sur la colonne mercredi."""
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        html = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        assert "timetable-inactive-block" in html


class TestTimetableBreakLine:
    def _configure_break(self, db):
        SystemSetting.create(db, {"key": "HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT", "value": "510"})

    def test_break_line_shown_by_default(self, db_session):
        school, subject, teacher, division, timeslot = _make_base(db_session)
        self._configure_break(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        html = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        assert "timetable-break-line" in html

    def test_break_line_hidden_via_show_breaks_param(self, db_session):
        school, subject, teacher, division, timeslot = _make_base(db_session)
        self._configure_break(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        html = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {"show_breaks": False}))
        assert "timetable-break-line" not in html

    def test_no_break_line_when_setting_is_unset(self, db_session):
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        html = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        assert "timetable-break-line" not in html

    def test_break_line_is_thick_and_always_solid(self):
        """Plus épais que le pointillé de créneau (.timetable-hour-divider) et toujours en trait
        PLEIN (background-color, jamais `border-style: dotted`) — pour rester bien distinct de lui
        même quand un cours ne recouvre ni l'un ni l'autre."""
        from backend.app.reports.base import TEMPLATES_DIR
        css = (TEMPLATES_DIR / "timetable.css").read_text(encoding="utf-8")
        break_line_rule = css[css.index(".timetable-break-line {"):css.index("}", css.index(".timetable-break-line {"))]
        assert "height: 2.5pt;" in break_line_rule
        assert "background-color" in break_line_rule
        assert "dotted" not in break_line_rule


class TestTimetableCourseHeight:
    def test_course_height_is_proportional_to_duration(self, db_session):
        """Un cours de 2x la durée standard doit occuper une boîte deux fois plus haute (en % de
        la hauteur totale de la grille) qu'un cours d'une durée standard."""
        school, subject, teacher, division, timeslot = _make_base(db_session)
        # Lundi 8h-10h par pas de 30 min -> 4 séquences (voir fixture) : un cours de 60 min (2x le
        # pas standard) occupe donc 2 séquences sur 4, soit 50% de la hauteur totale.
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id], "duration_minutes": 60,
        })
        html = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        assert "height: 50.0%;" in html


class TestTimetableTitle:
    def test_default_h1_is_suppressed_in_favor_of_the_merged_per_page_heading(self, db_session):
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        html = render_html(get_report("timetable_teacher"), db_session, [teacher.id], {})
        assert "<h1>" not in html
        # Le type de la ressource précède son nom (ex: "Division 6A") : "6A" seul ne dit pas de
        # quel type de ressource il s'agit.
        assert f'<h2 class="timetable-page-title">Emploi du temps — Professeur {teacher.display_name}</h2>' in html

    def test_title_includes_the_resource_type_label(self, db_session):
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        html = render_html(get_report("timetable_division"), db_session, [division.id], {})
        assert f'Emploi du temps — Division {division.display_name}' in html

    def test_title_is_centered_with_a_blank_line_before_the_grid(self):
        from backend.app.reports.base import TEMPLATES_DIR
        css = (TEMPLATES_DIR / "timetable.css").read_text(encoding="utf-8")
        assert "text-align: center;" in css
        # margin-bottom bien plus grand que le resserré d'origine (6pt) — une ligne vide, pas un
        # simple espacement.
        assert "margin: 0 0 14pt 0;" in css


class TestTimetablePageBudget:
    """
    Régression directe d'un bug constaté : un budget de hauteur calculé sur la mauvaise dimension
    de la page A4 (297mm, la LARGEUR en paysage, au lieu de 210mm, sa hauteur) débordait
    silencieusement sur 2-3 pages par ressource imprimée — invisible à un test sur le HTML rendu
    (aucune page n'existe avant la conversion PDF), d'où un test sur le PDF réel ici.
    """
    def test_one_resource_fits_on_a_single_pdf_page(self, db_session):
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        assert _page_count(get_report("timetable_teacher"), db_session, [teacher.id]) == 1

    def test_n_resources_produce_exactly_n_pages(self, db_session):
        school, subject, teacher, division, timeslot = _make_base(db_session)
        other_teacher = Teacher.create(db_session, {"code": "T2", "first_name": "Julie", "last_name": "Martin", "school_id": school.id})
        # Division distincte pour le 2e cours : même professeur, même créneau, même division
        # aurait été un conflit de placement (Course.validate_placement_conflicts), sans rapport
        # avec ce qui est testé ici (uniquement la pagination : N ressources -> N pages).
        other_division = Division.create(db_session, {"code": "6B", "name": "6ème B", "school_id": school.id, "color": "#0000ff"})
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [other_teacher.id], "division_ids": [other_division.id],
        })
        assert _page_count(get_report("timetable_teacher"), db_session, [teacher.id, other_teacher.id]) == 2


class TestTimetableCssIsolation:
    def test_timetable_selectors_are_not_in_the_shared_stylesheet(self):
        """Le CSS propre à ce rapport vit dans templates/timetable.css (voir ReportDef.extra_css),
        jamais dans base.css — qui, lui, est chargé par TOUS les rapports."""
        from backend.app.reports.base import TEMPLATES_DIR
        base_css = (TEMPLATES_DIR / "base.css").read_text(encoding="utf-8")
        assert ".timetable-" not in base_css

    def test_course_list_report_does_not_load_timetable_css(self, db_session):
        """course_list.py ne déclare pas extra_css : son rendu ne doit rien contenir de
        timetable.css (vérifie que extra_css est bien optionnel, pas juste absent par coïncidence)."""
        html = render_html(get_report("course_list"), db_session, [], {})
        assert ".timetable-course-box" not in html


class TestTimetablePageChrome:
    def test_printed_time_and_pagination_are_merged_top_right_on_every_page(self, db_session):
        """Un texte COURANT `@page { @top-right }` (voir base.py::_page_chrome_css), pas un
        contenu de flux : c'est ce qui garantit sa répétition sur CHAQUE page, contrairement à un
        `.report-header` en flux normal (rendu une seule fois, avant la boucle de pages) — pas
        besoin de plusieurs pages réelles pour vérifier que le fragment CSS est bien généré."""
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        html = render_html(get_report("timetable_teacher"), db_session, [teacher.id], {})
        assert "@top-right" in html
        assert '- Page " counter(page) " / " counter(pages)' in html
        # L'école et l'heure d'impression ne sont PLUS en contenu de flux (`.report-header`, qui
        # n'existe plus du tout) : elles feraient doublon sur la première page avec le texte
        # courant @top-left/@top-right, qui se répète lui sur toutes les pages.
        assert "report-header" not in html

    def test_school_running_header_uses_last_not_first(self, db_session):
        """`string()` sans second argument vaut `string(name, first)` par défaut (spec CSS GCPM) —
        piège direct pour ce mécanisme : le marqueur générique de layout.html (valeur par défaut)
        est suivi du marqueur propre à la page dans timetable.html, et c'est bien le SECOND qui
        doit gagner. Régression constatée sans `, last` explicite (voir base.py::_page_chrome_css)."""
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        html = render_html(get_report("timetable_teacher"), db_session, [teacher.id], {})
        assert "string(resource-school, last)" in html

    def test_school_marker_present_per_page_with_resource_school(self, db_session):
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        html = render_html(get_report("timetable_teacher"), db_session, [teacher.id], {})
        assert f'<div class="page-school-marker" data-school="{school.display_name}"></div>' in html

    def test_resource_without_a_school_leaves_the_marker_empty(self, db_session):
        """Material n'a pas de school_id (ni Group ni ClassPart, voir timetable.py) — « si elle est
        liée à un établissement » : rien à afficher, jamais une erreur ni une valeur héritée d'une
        autre page."""
        material = Material.create(db_session, {"code": "IPAD", "name": "Valise iPad", "quantity": 1})
        html = render_html(get_report("timetable_material"), db_session, [material.id], {})
        assert '<div class="page-school-marker" data-school=""></div>' in html


class TestTimetableColorRule:
    def test_teacher_timetable_colors_by_the_course_division(self, db_session):
        """Professeur/personnel/salle -> couleur de la classe (voir timetable.py::_class_color_for_course)."""
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        html = render_html(get_report("timetable_teacher"), db_session, [teacher.id], {})
        assert "background-color: #00ff00;" in html  # couleur de la Division, pas de la Subject

    def test_division_timetable_colors_by_the_course_subject(self, db_session):
        """Classe/groupe/partie de classe -> couleur de la matière (voir _subject_color_for_course)."""
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        html = render_html(get_report("timetable_division"), db_session, [division.id], {})
        assert "background-color: #ff0000;" in html  # couleur de la Subject, pas de la Division

    def test_no_color_when_course_has_two_divisions(self, db_session):
        school, subject, teacher, division, timeslot = _make_base(db_session)
        other_division = Division.create(db_session, {"code": "6B", "name": "6ème B", "school_id": school.id, "color": "#0000ff"})
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id, other_division.id],
        })
        html = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        assert "timetable-course-box" in html
        assert "background-color: #00ff00;" not in html
        assert "background-color: #0000ff;" not in html


class TestTimetableCourseBoxContent:
    def test_subject_shown_on_teacher_report(self, db_session):
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        html = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        assert f'<div class="timetable-course-line">{subject.short_name}</div>' in html

    def test_teacher_name_suppressed_on_own_timetable_when_sole_teacher(self, db_session):
        """La grille du professeur Dupont n'a pas besoin de répéter « Dupont » sur chacune de ses
        propres boîtes de cours — mais la classe (6A), elle, doit rester visible."""
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        html = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        # teacher.display_name apparaît légitimement dans le titre fusionné de la page (voir
        # TestTimetableTitle) — seule la boîte de cours elle-même doit rester silencieuse sur son
        # propre professeur.
        box_start = html.index("timetable-course-box")
        box_html = html[box_start:]
        assert teacher.display_name not in box_html
        assert division.display_name in box_html

    def test_teacher_name_shown_when_co_taught(self, db_session):
        """Deux professeurs sur le même cours : la grille de l'un d'eux doit quand même montrer
        les DEUX noms — la règle de silence ne vaut que pour une ressource seule et self-évidente."""
        school, subject, teacher, division, timeslot = _make_base(db_session)
        other_teacher = Teacher.create(db_session, {"code": "T2", "first_name": "Julie", "last_name": "Martin", "school_id": school.id})
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id, other_teacher.id], "division_ids": [division.id],
            "is_co_teaching": True,
        })
        html = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        assert teacher.display_name in html
        assert other_teacher.display_name in html

    def test_division_shown_on_its_own_timetable_when_multiple(self, db_session):
        """Symétrique côté classe : la grille de la 6A n'a pas besoin de répéter « 6A » si c'est
        la SEULE classe du cours, mais doit la montrer si le cours est partagé avec une autre."""
        school, subject, teacher, division, timeslot = _make_base(db_session)
        other_division = Division.create(db_session, {"code": "6B", "name": "6ème B", "school_id": school.id, "color": "#0000ff"})
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id, other_division.id],
        })
        html = _body(render_html(get_report("timetable_division"), db_session, [division.id], {}))
        assert division.display_name in html
        assert other_division.display_name in html

    def test_material_is_never_shown(self, db_session):
        school, subject, teacher, division, timeslot = _make_base(db_session)
        material = Material.create(db_session, {"code": "IPAD", "name": "Valise iPad Pro Unique", "quantity": 1})
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id], "material_ids": [material.id],
        })
        html = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        assert material.name not in html

    def test_week_badge_shown_only_for_a_or_b(self, db_session):
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id], "week_type": "A",
        })
        html = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        assert '<div class="timetable-week-badge timetable-week-badge--a">A</div>' in html

    def test_week_badge_color_class_matches_a_or_b(self, db_session):
        """Mêmes couleurs que la grille écran (CourseCard.vue) : semaine A en bleu, semaine B en
        ambre — un modificateur de classe CSS par lettre plutôt qu'une couleur en ligne, pour
        rester cohérent avec le thème plutôt qu'une valeur figée dans le HTML généré."""
        school, subject, teacher, division, timeslot = _make_base(db_session)
        course_a = Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id], "week_type": "A",
        })
        html_a = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        assert "timetable-week-badge--a" in html_a
        assert "timetable-week-badge--b" not in html_a

        course_a.update(db_session, {"week_type": "B"})
        html_b = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        assert "timetable-week-badge--b" in html_b
        assert "timetable-week-badge--a" not in html_b

    def test_no_week_badge_for_weekly_course(self, db_session):
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id], "week_type": "W",
        })
        html = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        assert "timetable-week-badge" not in html


class TestTimetableHourColumn:
    def test_start_and_end_labels_rendered(self, db_session):
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        html = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        assert '<span class="timetable-hour-start"' in html
        assert '<span class="timetable-hour-end"' in html
        assert "8h00" in html

    def test_divider_suppressed_when_both_adjacent_bounds_are_blank(self, db_session):
        """PUBLIC_DISPLAY_HOURS_BY_SEQUENCE : fin de la séquence 1 ET début de la séquence 2 tous
        deux nuls -> le trait entre les deux lignes correspondantes ne doit pas être affiché. Vérifié
        sur .timetable-hour-col : ce fragment n'est jamais filtré par jour (voir _day_lines), donc
        n'illustre QUE cette règle-là, indépendamment des cases grisées d'un jour ou d'un autre."""
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        display_map = {"1": [480, None], "2": [None, 540], "3": [540, 570], "4": [570, 600]}
        SystemSetting.create(db_session, {"key": "PUBLIC_DISPLAY_HOURS_BY_SEQUENCE", "value": json.dumps(display_map)})

        html = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        # 4 séquences -> 3 frontières possibles ; celle entre la 1 et la 2 est supprimée (blanc des
        # deux côtés), les deux autres (2->3 et 3->4) ont chacune une borne renseignée et restent.
        assert _hour_col_html(html).count("timetable-hour-divider") == 2

    def test_divider_appears_in_hour_column_and_in_each_active_day_column(self, db_session):
        """Le trait doit traverser TOUTES les colonnes (horaire + jours), pas seulement la colonne
        horaire — posé séparément dans .timetable-hour-col ET dans chaque .timetable-day-col actif
        (voir timetable.py::_day_lines et son commentaire : un bloc unique pleine largeur, essayé
        d'abord, laissait WeasyPrint ignorer le z-index face aux boîtes de cours)."""
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        html = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        assert "timetable-hour-divider" in _hour_col_html(html)
        # Lundi (jour du cours créé ci-dessus) est ouvert toute la plage -> ses frontières visibles
        # sont les mêmes que celles de la colonne horaire.
        assert "timetable-hour-divider" in _day_col_html(html, 0)

    def test_divider_and_break_line_absent_from_a_fully_inactive_day(self, db_session):
        """Mercredi n'est ouvert que 8h-9h (séquences 1-2, voir la fixture) : la frontière entre les
        séquences 3 et 4 (9h30, ENTIÈREMENT dans sa case grisée — ni l'une ni l'autre ouverte ce
        jour-là) ne doit apparaître sur SA colonne ni comme séparateur, ni comme récréation —
        contrairement à lundi, ouvert toute la plage, où cette même frontière reste visible."""
        school, subject, teacher, division, timeslot = _make_base(db_session)
        SystemSetting.create(db_session, {"key": "HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT", "value": "570"})  # 9h30, dans la case grisée de mercredi
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        html = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        monday_html = _day_col_html(html, 0)
        wednesday_html = _day_col_html(html, 1)
        # 4 séquences -> frontière 9h30 = top_pct 75.0% (3/4).
        divider_at_9h30 = 'timetable-hour-divider" style="top: 75.0%'
        break_at_9h30 = 'timetable-break-line" style="top: 75.0%'
        assert divider_at_9h30 in monday_html
        assert break_at_9h30 in monday_html
        assert divider_at_9h30 not in wednesday_html
        assert break_at_9h30 not in wednesday_html

    def test_divider_shown_at_the_edge_between_an_active_and_an_inactive_slot(self, db_session):
        """La frontière entre le dernier créneau ouvert de mercredi (8h30-9h) et le premier fermé
        (9h-9h30) doit rester visible sur SA colonne — seule une frontière entièrement DANS une case
        grisée (aucun des deux côtés ouvert) est supprimée, pas celle qui la borde."""
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        html = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        wednesday_html = _day_col_html(html, 1)
        assert "timetable-hour-divider" in wednesday_html

    def test_divider_and_break_line_are_siblings_of_course_boxes(self, db_session):
        """Structurel : posés à l'intérieur de .timetable-day-col, frères directs des boîtes de
        cours qu'ils doivent pouvoir recouvrir — pas un bloc à part dans .timetable-body-row (voir
        le commentaire de timetable.py::_day_lines : c'est précisément ce qui rend leur z-index
        fiable, vérifié par rasterisation d'un PDF réel)."""
        school, subject, teacher, division, timeslot = _make_base(db_session)
        SystemSetting.create(db_session, {"key": "HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT", "value": "510"})
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        html = _body(render_html(get_report("timetable_teacher"), db_session, [teacher.id], {}))
        monday_html = _day_col_html(html, 0)
        assert "timetable-hour-divider" in monday_html
        assert "timetable-break-line" in monday_html
        assert "timetable-course-box" in monday_html

    def test_divider_is_dotted_and_behind_course_boxes(self):
        """En pointillés, et sous les boîtes de cours (z-index strictement inférieur) : un cours à
        cheval sur la ligne doit la recouvrir entièrement (fond opaque de la boîte), pas laisser
        transparaître le trait."""
        from backend.app.reports.base import TEMPLATES_DIR
        css = (TEMPLATES_DIR / "timetable.css").read_text(encoding="utf-8")
        divider_rule = css[css.index(".timetable-hour-divider {"):css.index("}", css.index(".timetable-hour-divider {"))]
        box_rule = css[css.index(".timetable-course-box {"):css.index("}", css.index(".timetable-course-box {"))]
        assert "dotted" in divider_rule
        divider_z = int(divider_rule[divider_rule.index("z-index:") + len("z-index:"):divider_rule.index(";", divider_rule.index("z-index:"))].strip())
        box_z = int(box_rule[box_rule.index("z-index:") + len("z-index:"):box_rule.index(";", box_rule.index("z-index:"))].strip())
        assert divider_z < box_z


class TestTimetablePdf:
    def test_pdf_is_actually_produced(self, db_session):
        school, subject, teacher, division, timeslot = _make_base(db_session)
        Course.create(db_session, {
            "subject_id": subject.id, "school_id": school.id, "timeslot_id": timeslot.id,
            "teacher_ids": [teacher.id], "division_ids": [division.id],
        })
        pdf = render_pdf(get_report("timetable_teacher"), db_session, [teacher.id], {})
        assert pdf.startswith(b"%PDF-")


class TestDemoSeedRecessDefaults:
    """Vérifie le SOURCE du seed (pas une exécution réelle de seed_demo_data(), lente et
    destructive pour la base ciblée) : récréation du matin à 10h00 (600 min après minuit),
    après-midi à 15h30 (930 min) — demandées explicitement pour le jeu de démonstration."""
    def test_morning_and_afternoon_break_defaults_are_seeded(self):
        import inspect
        from backend.app.core import init_demo
        source = inspect.getsource(init_demo)
        assert "'HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT', '600'" in source
        assert "'HOUR_AFTERNOON_BREAK_START_MINUTES_AFTER_MIDNIGHT', '930'" in source
