"""
Tests du calendrier des semaines et des alternances (lot C).

Rappel de conception : le solveur ne connaît RIEN de tout cela. Il raisonne sur une semaine type
et sur `Course.week_type` ; `WeekCalendar` et `Alternation` ne servent qu'à l'export STS et à
l'affichage. Un test dédié vérifie que les faits passés au solveur sont inchangés.
"""
import datetime
import pytest
from sqlalchemy.orm import sessionmaker

from backend.app.models.base import Base
from backend.app.models import School, SystemSetting, Period, PeriodType, Holidays, WeekCalendar, Alternation
from backend.app.models.week_calendar import generate_week_calendar
from backend.tests.db_test_utils import make_test_engine

test_engine = make_test_engine()
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

RENTREE = datetime.date(2026, 9, 2)      # un mercredi
LUNDI_RENTREE = datetime.date(2026, 8, 31)
FIN = datetime.date(2027, 7, 4)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        SystemSetting.create(db, {"key": "STANDARD_TIMESLOT_DURATION", "value": "30"})
        SystemSetting.create(db, {"key": "SCHOOL_YEAR", "value": "2026"})
        School.create(db, {
            "uai": "0750001A", "name": "Collège",
            "student_start_date": RENTREE, "student_end_date": FIN,
        })
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


def _periode(db, code, debut, fin, type_id=None):
    if type_id is None:
        type_id = PeriodType.create(db, {"name": f"Type {code}"}).id
    return Period.create(db, {
        "period_type_id": type_id, "school_id": db.query(School).first().id,
        "code": code, "name": code, "start_date": debut, "end_date": fin,
    })


class TestHolidays:
    def test_fin_avant_debut_refusee(self, db_session):
        with pytest.raises(ValueError, match="antérieure"):
            Holidays.create(db_session, {
                "name": "Toussaint",
                "begin_date": datetime.date(2026, 10, 25),
                "end_date": datetime.date(2026, 10, 17),
            })

    def test_bornes_incluses(self, db_session):
        vac = Holidays.create(db_session, {
            "name": "Toussaint",
            "begin_date": datetime.date(2026, 10, 17),
            "end_date": datetime.date(2026, 11, 1),
        })
        assert vac.contains(datetime.date(2026, 10, 17))
        assert vac.contains(datetime.date(2026, 11, 1))
        assert not vac.contains(datetime.date(2026, 11, 2))


class TestWeekCalendar:
    def test_la_semaine_de_rentree_est_acceptee(self, db_session):
        """La rentrée tombe un mercredi : sa semaine commence le lundi précédent, qui est
        antérieur à student_start_date. Le début d'année est donc ramené au lundi."""
        semaine = WeekCalendar.create(db_session, {"begin_date": LUNDI_RENTREE, "week_type": "A"})
        assert semaine.id is not None

    def test_semaine_avant_l_annee_refusee(self, db_session):
        with pytest.raises(ValueError, match="avant le début de l'année"):
            WeekCalendar.create(db_session, {"begin_date": datetime.date(2026, 8, 24), "week_type": "A"})

    def test_semaine_apres_l_annee_refusee(self, db_session):
        with pytest.raises(ValueError, match="après la fin de l'année"):
            WeekCalendar.create(db_session, {"begin_date": datetime.date(2027, 8, 30), "week_type": "A"})

    def test_semaine_commencant_en_vacances_refusee(self, db_session):
        Holidays.create(db_session, {
            "name": "Toussaint",
            "begin_date": datetime.date(2026, 10, 17), "end_date": datetime.date(2026, 11, 1),
        })
        with pytest.raises(ValueError, match="Toussaint"):
            WeekCalendar.create(db_session, {"begin_date": datetime.date(2026, 10, 19), "week_type": "A"})

    def test_type_w_refuse(self, db_session):
        """W qualifie un cours ou une alternance, jamais une semaine du calendrier."""
        with pytest.raises(ValueError, match="A ou B"):
            WeekCalendar.create(db_session, {"begin_date": LUNDI_RENTREE, "week_type": "W"})

    def test_begin_date_unique(self, db_session):
        WeekCalendar.create(db_session, {"begin_date": LUNDI_RENTREE, "week_type": "A"})
        with pytest.raises(Exception):
            WeekCalendar.create(db_session, {"begin_date": LUNDI_RENTREE, "week_type": "B"})

    def test_end_date_vaut_begin_plus_six(self, db_session):
        semaine = WeekCalendar.create(db_session, {"begin_date": LUNDI_RENTREE, "week_type": "A"})
        assert semaine.end_date == LUNDI_RENTREE + datetime.timedelta(days=6)

    def test_end_date_rabotee_par_les_vacances(self, db_session):
        """Des vacances qui commencent le samedi ramènent la fin de semaine au vendredi."""
        Holidays.create(db_session, {
            "name": "Toussaint",
            "begin_date": datetime.date(2026, 10, 17), "end_date": datetime.date(2026, 11, 1),
        })
        semaine = WeekCalendar.create(db_session, {"begin_date": datetime.date(2026, 10, 12), "week_type": "A"})
        assert semaine.end_date == datetime.date(2026, 10, 16)

    def test_end_date_rabotee_par_la_fin_d_annee(self, db_session):
        semaine = WeekCalendar.create(db_session, {"begin_date": datetime.date(2027, 6, 28), "week_type": "A"})
        assert semaine.end_date == FIN


class TestGenerationDuCalendrier:
    def test_alternance_a_b_et_saut_des_vacances(self, db_session):
        Holidays.create(db_session, {
            "name": "Toussaint",
            "begin_date": datetime.date(2026, 10, 17), "end_date": datetime.date(2026, 11, 1),
        })
        creees = generate_week_calendar(db_session)
        semaines = db_session.query(WeekCalendar).order_by(WeekCalendar.begin_date).all()
        assert creees == len(semaines) > 30
        assert semaines[0].begin_date == LUNDI_RENTREE
        # Aucune semaine ne commence pendant les vacances.
        assert not any(datetime.date(2026, 10, 17) <= s.begin_date <= datetime.date(2026, 11, 1) for s in semaines)
        # Les vacances ne consomment pas de tour : l'alternance reprend là où elle s'est arrêtée.
        types = [s.week_type.value for s in semaines]
        assert types[:3] == ["A", "B", "A"]
        assert all(types[i] != types[i + 1] for i in range(len(types) - 1))

    def test_idempotent(self, db_session):
        generate_week_calendar(db_session)
        total = db_session.query(WeekCalendar).count()
        assert generate_week_calendar(db_session) == 0
        assert db_session.query(WeekCalendar).count() == total

    def test_sans_dates_d_annee_le_calendrier_est_refuse(self, db_session):
        db_session.query(School).first().update(db_session, {"student_start_date": None})
        with pytest.raises(ValueError, match="date de rentrée"):
            generate_week_calendar(db_session)


class TestAlternation:
    def test_semaines_d_une_alternance_annuelle(self, db_session):
        generate_week_calendar(db_session)
        alt = Alternation.search_or_create(db_session, "W", [])
        assert len(alt.week_calendar_ids) == db_session.query(WeekCalendar).count()

    def test_une_alternance_a_ne_retient_que_les_semaines_a(self, db_session):
        generate_week_calendar(db_session)
        alt = Alternation.search_or_create(db_session, "A", [])
        semaines_a = db_session.query(WeekCalendar).filter(WeekCalendar.week_type == "A").count()
        assert len(alt.week_calendar_ids) == semaines_a

    def test_les_periodes_restreignent_les_semaines(self, db_session):
        generate_week_calendar(db_session)
        t1 = _periode(db_session, "T1", datetime.date(2026, 9, 1), datetime.date(2026, 11, 30))
        alt = Alternation.search_or_create(db_session, "W", [t1.id])
        toutes = db_session.query(WeekCalendar).count()
        assert 0 < len(alt.week_calendar_ids) < toutes

    def test_l_ordre_des_periodes_n_est_pas_discriminant(self, db_session):
        type_id = PeriodType.create(db_session, {"name": "Trimestre"}).id
        t1 = _periode(db_session, "T1", datetime.date(2026, 9, 1), datetime.date(2026, 11, 30), type_id)
        t2 = _periode(db_session, "T2", datetime.date(2026, 12, 1), datetime.date(2027, 3, 15), type_id)
        a = Alternation.search_or_create(db_session, "A", [t1.id, t2.id])
        b = Alternation.search_or_create(db_session, "A", [t2.id, t1.id])
        assert a.id == b.id

    def test_deux_types_de_semaine_donnent_deux_alternances(self, db_session):
        a = Alternation.search_or_create(db_session, "A", [])
        b = Alternation.search_or_create(db_session, "B", [])
        assert a.id != b.id
        assert db_session.query(Alternation).count() == 2

    def test_le_code_est_deterministe(self, db_session):
        t1 = _periode(db_session, "T1", datetime.date(2026, 9, 1), datetime.date(2026, 11, 30))
        assert Alternation.search_or_create(db_session, "A", [t1.id]).code == "A-T1"
        assert Alternation.search_or_create(db_session, "W", []).code == "W"
