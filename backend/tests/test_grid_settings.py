"""
Tests pour la grille horaire : GridDaySettings (heures d'ouverture par jour), les nouveaux
SystemSetting (FIRST_DAY_OF_THE_WEEK, récréations), la réconciliation différentielle des
Timeslot (Timeslot.update_timeslot_on_weekgrid_change) et le wizard WizardGridSettings — voir
spec.md §0bis, architecture.md §10.D.
"""
import json
import pytest
from sqlalchemy.orm import sessionmaker
from backend.app.models.base import Base
from backend.app.models import (
    School, Discipline, Subject, SystemSetting, GridDaySettings, Timeslot, Course,
)
from backend.app.models.wizard_grid_settings import WizardGridSettings, _display_bounds
from backend.app.core.time_utils import get_standard_timeslot_duration_options
from backend.tests.db_test_utils import make_test_engine

test_engine = make_test_engine()
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        SystemSetting.create(db, {"key": "STANDARD_TIMESLOT_DURATION", "value": "30"})
        school = School.create(db, {"uai": "1234567A", "name": "Lycée Test"})
        discipline = Discipline.create(db, {"code": "GEN", "name": "Général"})
        Subject.create(db, {
            "code": "MATH", "code_nomenclature": "MATH", "name": "Mathématiques",
            "short_name": "MATH", "discipline_id": discipline.id,
        })
        for day_of_week in range(1, 8):
            db.execute(
                Base.metadata.tables["grid_day_settings"].insert().values(day_of_week=day_of_week)
            )
        db.commit()
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


def _day(db, day_of_week: int) -> GridDaySettings:
    return db.query(GridDaySettings).filter(GridDaySettings.day_of_week == day_of_week).first()


def _make_course(db, timeslot_id, name="Cours"):
    school = db.query(School).first()
    subject = db.query(Subject).first()
    return Course.create(db, {
        "name": name, "subject_id": subject.id, "duration_minutes": 30,
        "timeslot_id": timeslot_id, "school_id": school.id,
    })


class TestGridDaySettings:
    def test_seven_rows_seeded_create_and_delete_blocked(self, db_session):
        assert db_session.query(GridDaySettings).count() == 7
        with pytest.raises(ValueError, match="Impossible de créer"):
            GridDaySettings.create(db_session, {"day_of_week": 1})
        with pytest.raises(ValueError, match="Impossible de supprimer"):
            _day(db_session, 1).delete(db_session)

    def test_display_name_is_full_day_label(self, db_session):
        assert _day(db_session, 3).display_name == "Mercredi"

    def test_end_required_once_start_set(self, db_session):
        monday = _day(db_session, 1)
        with pytest.raises(ValueError, match="fermeture est obligatoire"):
            monday.update(db_session, {"hour_day_start_minutes_after_midnight": 480})

    def test_end_forbidden_without_start(self, db_session):
        monday = _day(db_session, 1)
        with pytest.raises(ValueError, match="doit rester vide"):
            monday.update(db_session, {"hour_day_end_minutes_after_midnight": 600})

    def test_end_must_be_after_start(self, db_session):
        monday = _day(db_session, 1)
        with pytest.raises(ValueError, match="postérieure"):
            monday.update(db_session, {
                "hour_day_start_minutes_after_midnight": 600,
                "hour_day_end_minutes_after_midnight": 480,
            })

    def test_end_beyond_2359_rejected(self, db_session):
        monday = _day(db_session, 1)
        with pytest.raises(ValueError, match="23h59"):
            monday.update(db_session, {
                "hour_day_start_minutes_after_midnight": 480,
                "hour_day_end_minutes_after_midnight": 1440,
            })

    def test_hours_must_be_multiple_of_standard_duration(self, db_session):
        monday = _day(db_session, 1)
        with pytest.raises(ValueError):
            monday.update(db_session, {
                "hour_day_start_minutes_after_midnight": 485,
                "hour_day_end_minutes_after_midnight": 600,
            })


class TestTimeslotDifferentialReconciliation:
    def test_extending_amplitude_preserves_existing_timeslot_ids_and_courses(self, db_session):
        monday = _day(db_session, 1)
        monday.update(db_session, {"hour_day_start_minutes_after_midnight": 480, "hour_day_end_minutes_after_midnight": 600})
        ts_540 = db_session.query(Timeslot).filter(Timeslot.day_of_week == 1, Timeslot.minutes_from_midnight == 540).first()
        course = _make_course(db_session, ts_540.id)

        monday.update(db_session, {"hour_day_end_minutes_after_midnight": 660})

        db_session.refresh(course)
        still_there = db_session.query(Timeslot).filter(Timeslot.day_of_week == 1, Timeslot.minutes_from_midnight == 540).first()
        assert still_there.id == ts_540.id
        assert course.timeslot_id == ts_540.id  # jamais dépositionné par un simple élargissement

    def test_shrinking_only_deposes_courses_on_removed_timeslots(self, db_session):
        monday = _day(db_session, 1)
        monday.update(db_session, {"hour_day_start_minutes_after_midnight": 480, "hour_day_end_minutes_after_midnight": 600})
        ts_480 = db_session.query(Timeslot).filter(Timeslot.day_of_week == 1, Timeslot.minutes_from_midnight == 480).first()
        ts_570 = db_session.query(Timeslot).filter(Timeslot.day_of_week == 1, Timeslot.minutes_from_midnight == 570).first()
        survivor = _make_course(db_session, ts_480.id, "Survivor")
        victim = _make_course(db_session, ts_570.id, "Victim")

        monday.update(db_session, {"hour_day_end_minutes_after_midnight": 510})

        db_session.refresh(survivor)
        db_session.refresh(victim)
        assert survivor.timeslot_id == ts_480.id
        assert victim.timeslot_id is None
        assert db_session.query(Timeslot).filter(Timeslot.id == ts_570.id).first() is None

    def test_closing_the_day_removes_all_its_timeslots(self, db_session):
        monday = _day(db_session, 1)
        monday.update(db_session, {"hour_day_start_minutes_after_midnight": 480, "hour_day_end_minutes_after_midnight": 600})
        assert db_session.query(Timeslot).filter(Timeslot.day_of_week == 1).count() == 4

        monday.update(db_session, {"hour_day_start_minutes_after_midnight": None, "hour_day_end_minutes_after_midnight": None})
        assert db_session.query(Timeslot).filter(Timeslot.day_of_week == 1).count() == 0

    def test_reconcile_all_days_covers_duration_only_change(self, db_session):
        monday = _day(db_session, 1)
        monday.update(db_session, {"hour_day_start_minutes_after_midnight": 480, "hour_day_end_minutes_after_midnight": 570})
        assert db_session.query(Timeslot).filter(Timeslot.day_of_week == 1).count() == 3  # 480, 510, 540

        duration = db_session.query(SystemSetting).filter(SystemSetting.key == "STANDARD_TIMESLOT_DURATION").first()
        duration.update(db_session, {"value": "15"}, bypass_grid_checks=True)
        Timeslot.reconcile_all_days(db_session)

        assert db_session.query(Timeslot).filter(Timeslot.day_of_week == 1).count() == 6  # 480,495,510,525,540,555


class TestTimeslotComputedFields:
    def test_intraday_sequence_number_accounts_for_earliest_day_across_week(self, db_session):
        _day(db_session, 1).update(db_session, {"hour_day_start_minutes_after_midnight": 480, "hour_day_end_minutes_after_midnight": 510})
        _day(db_session, 2).update(db_session, {"hour_day_start_minutes_after_midnight": 780, "hour_day_end_minutes_after_midnight": 840})

        tuesday_first = db_session.query(Timeslot).filter(Timeslot.day_of_week == 2).order_by(Timeslot.minutes_from_midnight).first()
        assert tuesday_first.intraday_sequence_number == 11  # (780-480)/30 + 1

    def test_public_display_falls_back_to_real_hour_when_sequence_missing(self, db_session):
        _day(db_session, 1).update(db_session, {"hour_day_start_minutes_after_midnight": 480, "hour_day_end_minutes_after_midnight": 510})
        ts = db_session.query(Timeslot).filter(Timeslot.day_of_week == 1).first()
        assert ts.public_display_start_minutes_after_midnight == 480
        assert ts.public_display_end_minutes_after_midnight == 510

    def test_public_display_uses_configured_map_when_present(self, db_session):
        _day(db_session, 1).update(db_session, {"hour_day_start_minutes_after_midnight": 480, "hour_day_end_minutes_after_midnight": 510})
        SystemSetting.create(db_session, {"key": "PUBLIC_DISPLAY_HOURS_BY_SEQUENCE", "value": json.dumps({"1": [485, 535]})})
        ts = db_session.query(Timeslot).filter(Timeslot.day_of_week == 1).first()
        assert ts.public_display_start_minutes_after_midnight == 485
        assert ts.public_display_end_minutes_after_midnight == 535

    def test_public_display_null_means_do_not_display_not_a_fallback(self, db_session):
        # [début, null] : null est une valeur VOULUE (ne pas afficher cette heure-là), pas un
        # simple trou à combler par l'heure réelle — repli uniquement quand l'ENTRÉE elle-même est
        # absente (voir test_public_display_falls_back_when_sequence_missing), jamais quand une
        # valeur du couple est explicitement null.
        _day(db_session, 1).update(db_session, {"hour_day_start_minutes_after_midnight": 480, "hour_day_end_minutes_after_midnight": 510})
        SystemSetting.create(db_session, {"key": "PUBLIC_DISPLAY_HOURS_BY_SEQUENCE", "value": json.dumps({"1": [485, None]})})
        ts = db_session.query(Timeslot).filter(Timeslot.day_of_week == 1).first()
        assert ts.public_display_start_minutes_after_midnight == 485
        assert ts.public_display_end_minutes_after_midnight is None


class TestSystemSettingGridValidation:
    def test_first_day_of_week_must_be_between_1_and_7(self, db_session):
        with pytest.raises(ValueError, match="entre 1"):
            SystemSetting.create(db_session, {"key": "FIRST_DAY_OF_THE_WEEK", "value": "8"})
        setting = SystemSetting.create(db_session, {"key": "FIRST_DAY_OF_THE_WEEK", "value": "3"})
        assert setting.value == "3"

    def test_morning_break_must_be_within_grid_and_multiple_of_duration(self, db_session):
        _day(db_session, 1).update(db_session, {"hour_day_start_minutes_after_midnight": 480, "hour_day_end_minutes_after_midnight": 1080})
        with pytest.raises(ValueError, match="au moins un pas horaire"):
            SystemSetting.create(db_session, {"key": "HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT", "value": "480"})
        with pytest.raises(ValueError):
            SystemSetting.create(db_session, {"key": "HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT", "value": "545"})
        setting = SystemSetting.create(db_session, {"key": "HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT", "value": "570"})
        assert setting.value == "570"

    def test_afternoon_break_must_follow_morning_break(self, db_session):
        _day(db_session, 1).update(db_session, {"hour_day_start_minutes_after_midnight": 480, "hour_day_end_minutes_after_midnight": 1080})
        SystemSetting.create(db_session, {"key": "HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT", "value": "570"})
        with pytest.raises(ValueError, match="après la récréation du matin"):
            SystemSetting.create(db_session, {"key": "HOUR_AFTERNOON_BREAK_START_MINUTES_AFTER_MIDNIGHT", "value": "540"})
        afternoon = SystemSetting.create(db_session, {"key": "HOUR_AFTERNOON_BREAK_START_MINUTES_AFTER_MIDNIGHT", "value": "600"})
        assert afternoon.value == "600"

    def test_morning_break_cannot_be_pushed_after_afternoon_break(self, db_session):
        _day(db_session, 1).update(db_session, {"hour_day_start_minutes_after_midnight": 480, "hour_day_end_minutes_after_midnight": 1080})
        morning = SystemSetting.create(db_session, {"key": "HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT", "value": "570"})
        SystemSetting.create(db_session, {"key": "HOUR_AFTERNOON_BREAK_START_MINUTES_AFTER_MIDNIGHT", "value": "600"})
        with pytest.raises(ValueError, match="antérieure à la récréation de l'après-midi"):
            morning.update(db_session, {"value": "630"})

    def test_bypass_grid_checks_skips_validation(self, db_session):
        # Aucune amplitude définie -> validation normale impossible, mais le wizard doit pouvoir
        # traverser un état intermédiaire incohérent (voir wizard_grid_settings.rpc_apply).
        setting = SystemSetting.create(
            db_session, {"key": "HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT", "value": "9999"},
            bypass_grid_checks=True,
        )
        assert setting.value == "9999"


class TestDisplayBounds:
    """_display_bounds (wizard_grid_settings.py) : les fenêtres min/max de deux ancres distantes
    exactement du pas horaire (real_start, real_end = real_start + pas) ne se chevauchent jamais
    — garantit structurellement début public < fin publique, pour tout pas horaire valide."""

    def test_start_max_always_below_end_min_for_every_valid_duration(self):
        for option in get_standard_timeslot_duration_options():
            duration = option["value"]
            for real_start in range(0, 600, duration):
                real_end = real_start + duration
                _, start_max = _display_bounds(real_start, duration)
                end_min, _ = _display_bounds(real_end, duration)
                assert start_max < end_min, f"duration={duration} real_start={real_start}"


class TestGetNoonBoundaryMinutes:
    def test_falls_back_to_noon_when_no_grid_configured(self, db_session):
        assert Timeslot.get_noon_boundary_minutes(db_session) == 720

    def test_absolute_midpoint_of_configured_grid(self, db_session):
        _day(db_session, 1).update(db_session, {"hour_day_start_minutes_after_midnight": 480, "hour_day_end_minutes_after_midnight": 1080})
        # (1080-480)/2 = 300, milieu ABSOLU = 480+300 = 780 (13h) -- pas 300 (5h du matin), qui
        # classerait tout l'après-midi comme "avant la césure".
        assert Timeslot.get_noon_boundary_minutes(db_session) == 780


class TestWizardGridSettingsEarlyValidation:
    """rpc_validate_day_rows (étape 2) doit lever la même erreur que rpc_apply, mais SANS attendre
    la dernière étape — et sans jamais rien écrire en base (candidate n'est jamais db.add())."""

    def test_rejects_end_before_start_at_step_2(self, db_session):
        wizard = WizardGridSettings.read(db_session)[0]
        day_rows = wizard.rpc_load_day_rows(db_session, first_day_of_week=1)["day_rows"]
        for row in day_rows:
            if row["day_of_week"] == 1:
                row["hour_day_start_minutes_after_midnight"] = 600
                row["hour_day_end_minutes_after_midnight"] = 480

        with pytest.raises(ValueError, match="postérieure à l'heure d'ouverture"):
            wizard.rpc_validate_day_rows(db_session, day_rows=day_rows)

        assert db_session.query(GridDaySettings).filter(GridDaySettings.day_of_week == 1).first().hour_day_start_minutes_after_midnight is None

    def test_accepts_valid_day_rows(self, db_session):
        wizard = WizardGridSettings.read(db_session)[0]
        day_rows = wizard.rpc_load_day_rows(db_session, first_day_of_week=1)["day_rows"]
        for row in day_rows:
            if row["day_of_week"] == 1:
                row["hour_day_start_minutes_after_midnight"] = 480
                row["hour_day_end_minutes_after_midnight"] = 600
        wizard.rpc_validate_day_rows(db_session, day_rows=day_rows)  # ne lève pas


class TestWizardPreviewDisplayNullHandling:
    """rpc_preview_display (étape 4) doit montrer exactement ce que la grille affichera une fois
    appliqué : une valeur explicitement null dans PUBLIC_DISPLAY_HOURS_BY_SEQUENCE reste None
    dans l'aperçu, pas de repli sur l'heure réelle (voir Timeslot.public_display_start/end_...)."""

    def test_null_half_of_an_existing_entry_stays_none_in_the_preview(self, db_session):
        _day(db_session, 1).update(db_session, {"hour_day_start_minutes_after_midnight": 480, "hour_day_end_minutes_after_midnight": 540})
        SystemSetting.create(db_session, {"key": "PUBLIC_DISPLAY_HOURS_BY_SEQUENCE", "value": json.dumps({"1": [480, None], "2": [None, 540]})})

        wizard = WizardGridSettings.read(db_session)[0]
        day_rows = wizard.rpc_load_day_rows(db_session, first_day_of_week=1)["day_rows"]
        display_rows = wizard.rpc_preview_display(db_session, day_rows=day_rows, standard_timeslot_duration=30)["display_rows"]

        seq1 = next(r for r in display_rows if r["sequence_number"] == 1)
        seq2 = next(r for r in display_rows if r["sequence_number"] == 2)
        assert seq1["public_display_start_minutes_after_midnight"] == 480
        assert seq1["public_display_end_minutes_after_midnight"] is None
        assert seq2["public_display_start_minutes_after_midnight"] is None
        assert seq2["public_display_end_minutes_after_midnight"] == 540


class TestWizardGridSettings:
    def test_full_flow_preserves_survivor_and_deposes_victim(self, db_session):
        for d in range(1, 6):
            _day(db_session, d).update(db_session, {"hour_day_start_minutes_after_midnight": 480, "hour_day_end_minutes_after_midnight": 1080})

        mon_8h = db_session.query(Timeslot).filter(Timeslot.day_of_week == 1, Timeslot.minutes_from_midnight == 480).first()
        mon_1730 = db_session.query(Timeslot).filter(Timeslot.day_of_week == 1, Timeslot.minutes_from_midnight == 1050).first()
        survivor = _make_course(db_session, mon_8h.id, "Survivor")
        victim = _make_course(db_session, mon_1730.id, "Victim")

        wizard = WizardGridSettings.read(db_session)[0]
        assert wizard.first_day_of_week == 1
        assert wizard.standard_timeslot_duration == 30

        day_rows = wizard.rpc_load_day_rows(db_session, first_day_of_week=1)["day_rows"]
        assert len(day_rows) == 7
        for row in day_rows:
            if row["day_of_week"] == 1:
                row["hour_day_end_minutes_after_midnight"] = 1020  # ferme à 17h au lieu de 18h

        display_rows = wizard.rpc_preview_display(db_session, day_rows=day_rows, standard_timeslot_duration=30)["display_rows"]
        assert len(display_rows) == 20  # (1080-480)/30
        # Bornes min/max déjà calculées côté serveur pour ClockTimeField.vue (jamais montrées en
        # colonne, voir _DISPLAY_ROWS_WIDGET_PARAMS) — séquence 1 : réel 8h00-8h30, pas 30 min.
        # Début borné autour de 480 (8h00) : (465, 495) exclu -> [466, 494].
        assert display_rows[0]["start_display_min_minutes_after_midnight"] == 466
        assert display_rows[0]["start_display_max_minutes_after_midnight"] == 494
        # Fin bornée autour de 510 (8h30) : (495, 525) exclu -> [496, 524].
        assert display_rows[0]["end_display_min_minutes_after_midnight"] == 496
        assert display_rows[0]["end_display_max_minutes_after_midnight"] == 524
        # Fenêtres adjacentes, jamais chevauchantes : la fin publique reste structurellement
        # toujours postérieure au début public.
        assert display_rows[0]["start_display_max_minutes_after_midnight"] < display_rows[0]["end_display_min_minutes_after_midnight"]

        impact = wizard.rpc_compute_impact(db_session, day_rows=day_rows, standard_timeslot_duration=30)
        assert "1 cours" in impact["confirm_html"]

        result = wizard.rpc_apply(
            db_session,
            first_day_of_week=1, standard_timeslot_duration=30, day_rows=day_rows,
            morning_break_start_minutes_after_midnight=570,
            afternoon_break_start_minutes_after_midnight=None,
            display_rows=display_rows,
        )
        assert "timeslots" in result["mutated_resources"]

        db_session.refresh(survivor)
        db_session.refresh(victim)
        assert survivor.timeslot_id == mon_8h.id
        assert victim.timeslot_id is None

        first_day_setting = db_session.query(SystemSetting).filter(SystemSetting.key == "FIRST_DAY_OF_THE_WEEK").first()
        assert first_day_setting.value == "1"
        morning_setting = db_session.query(SystemSetting).filter(SystemSetting.key == "HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT").first()
        assert morning_setting.value == "570"

    def test_nothing_persisted_before_apply(self, db_session):
        wizard = WizardGridSettings.read(db_session)[0]
        day_rows = wizard.rpc_load_day_rows(db_session, first_day_of_week=1)["day_rows"]
        for row in day_rows:
            row["hour_day_start_minutes_after_midnight"] = 480
            row["hour_day_end_minutes_after_midnight"] = 600
        wizard.rpc_preview_display(db_session, day_rows=day_rows, standard_timeslot_duration=30)
        wizard.rpc_compute_impact(db_session, day_rows=day_rows, standard_timeslot_duration=30)

        # Aucune écriture réelle avant rpc_apply : la base ne reflète toujours aucune heure d'ouverture.
        assert db_session.query(Timeslot).count() == 0
        assert all(d.hour_day_start_minutes_after_midnight is None for d in db_session.query(GridDaySettings).all())
