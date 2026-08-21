"""
Audit des anomalies bloquant ou dégradant la remontée vers STS-web.

Un écran de ce genre est ce qui fait la différence à l'usage : sans lui, l'utilisateur découvre ses
anomalies à l'arrivée, dans un message d'erreur de STS-web qui ne dit ni quel objet est en cause ni
quoi corriger. Les contrôles ci-dessous couvrent les défauts qui font échouer une remontée ou la
rendent fausse en silence.

Deux sévérités, et la distinction est celle validée pour ce projet :

- **BLOQUANT** — anomalie structurelle : le fichier ne peut pas être produit, ou serait rejeté.
- **AVERTISSEMENT** — écart de volume ou de cohérence : le fichier part quand même, mais quelque
  chose mérite un regard.

Module **pur** : il lit la base et renvoie des dictionnaires, il n'écrit rien et ne construit
aucun XML. L'export (`sts_export.py`) l'appelle avant de sérialiser, l'écran d'audit l'appelle
seul.
"""
from sqlalchemy.orm import Session

BLOCKING = "BLOCKING"
WARNING = "WARNING"

SEVERITY_LABELS = {BLOCKING: "Bloquant", WARNING: "Avertissement"}

# Au-delà, on ne liste plus chaque occurrence : le compte total reste annoncé. Une base entière
# mal paramétrée produirait sinon des milliers de lignes illisibles.
MAX_PAR_CONTROLE = 50


def _libelle_cours(course) -> str:
    """Course n'a pas de display_name : on compose un libellé lisible pour le rapport."""
    matiere = course.subject_relation.short_name if course.subject_relation else "?"
    publics = [d.code for d in course.divisions] + [g.name for g in course.groups]
    return f"{matiere} — {', '.join(publics) or 'sans public'}"


def _anomalie(code, severity, message, resource=None, record_id=None, label=None):
    return {
        "code": code,
        "severity": severity,
        "severity_label": SEVERITY_LABELS[severity],
        "message": message,
        "resource": resource,
        "record_id": record_id,
        "label": label or "",
    }


def audit(db: Session, school) -> list:
    """
    Toutes les anomalies d'un établissement, bloquantes d'abord. `school` borne l'audit : un
    fichier de remontée vaut pour un RNE et un seul.
    """
    anomalies = []
    for controle in (
        _cours_non_places, _cours_sans_public, _cours_composes_non_precises,
        _co_enseignement_non_declare, _enseignants_sans_epp, _matieres_sans_code_national,
        _groupes_sans_effectif, _groupes_sans_division, _classes_sans_mef,
        _alternances_manquantes, _quinzaines_non_tranchees,
        _ponderations_heterogenes, _services_non_consommes,
    ):
        anomalies.extend(controle(db, school))
    anomalies.sort(key=lambda a: (a["severity"] != BLOCKING, a["code"]))
    return anomalies


def has_blocking(anomalies: list) -> bool:
    return any(a["severity"] == BLOCKING for a in anomalies)


def _courses_a_remonter(db: Session, school) -> list:
    """
    Cours de l'établissement effectivement destinés à la remontée. Les cours exclus (trois niveaux
    de drapeaux plus la pondération nulle, voir Course.is_exported_to_sts) ne sont pas audités :
    les signaler serait du bruit, puisqu'ils ne partiront pas.
    Les cours composés parents sont écartés : ce sont leurs enfants qui portent les séances.
    """
    from backend.app.models.course import Course
    return [
        c for c in db.query(Course).filter(Course.school_id == school.id).all()
        if not c.is_composed and c.is_exported_to_sts
    ]


# --------------------------------------------------------------------------------------------
#  Contrôles bloquants
# --------------------------------------------------------------------------------------------

def _cours_non_places(db, school):
    """Un cours sans créneau n'a ni jour ni heure à écrire : il disparaîtrait de la remontée."""
    fautifs = [c for c in _courses_a_remonter(db, school) if c.timeslot_id is None]
    return [
        _anomalie("COURSE_NOT_PLACED", BLOCKING,
                  "Ce cours n'est placé sur aucun créneau : il n'aurait ni jour ni heure dans le fichier.",
                  "courses", c.id, _libelle_cours(c))
        for c in fautifs[:MAX_PAR_CONTROLE]
    ] + _reste("COURSE_NOT_PLACED", BLOCKING, fautifs, "cours non placés")


def _cours_sans_public(db, school):
    """Un cours se remonte toujours pour un public : au moins une classe, un groupe ou une partie."""
    fautifs = [
        c for c in _courses_a_remonter(db, school)
        if not c.divisions and not c.groups and not c.class_parts
    ]
    return [
        _anomalie("COURSE_NO_AUDIENCE", BLOCKING,
                  "Ce cours n'a aucun public : ni classe, ni groupe, ni partie de classe.",
                  "courses", c.id, _libelle_cours(c))
        for c in fautifs[:MAX_PAR_CONTROLE]
    ] + _reste("COURSE_NO_AUDIENCE", BLOCKING, fautifs, "cours sans public")


def _cours_composes_non_precises(db, school):
    """Un cours complexe dont la répartition n'est pas tranchée n'est pas remontable : on ne sait
    pas quel enseignant assure quelle part du service."""
    from backend.app.models.course import Course, CourseDecompositionStatus
    fautifs = [
        c for c in db.query(Course).filter(Course.school_id == school.id, Course.is_composed == True).all()
        if c.is_exported_to_sts and c.decomposition_status != CourseDecompositionStatus.FULLY_VENTILATED.value
    ]
    return [
        _anomalie("COMPOSED_NOT_VENTILATED", BLOCKING,
                  "Ce cours composé n'est pas entièrement décomposé : STS-web refuse un cours complexe non précisé.",
                  "courses", c.id, _libelle_cours(c))
        for c in fautifs[:MAX_PAR_CONTROLE]
    ] + _reste("COMPOSED_NOT_VENTILATED", BLOCKING, fautifs, "cours composés non décomposés")


def _co_enseignement_non_declare(db, school):
    """
    Deux professeurs sur un cours sans le drapeau de co-enseignement en font un cours complexe non
    réparti : ni remontable en co-enseignement, ni exploitable par les logiciels de vie scolaire.
    """
    fautifs = [c for c in _courses_a_remonter(db, school) if len(c.teachers) > 1 and not c.is_co_teaching]
    return [
        _anomalie("CO_TEACHING_NOT_DECLARED", BLOCKING,
                  f"Ce cours a {len(c.teachers)} enseignants sans être déclaré en co-enseignement.",
                  "courses", c.id, _libelle_cours(c))
        for c in fautifs[:MAX_PAR_CONTROLE]
    ] + _reste("CO_TEACHING_NOT_DECLARED", BLOCKING, fautifs, "cours à plusieurs enseignants non déclarés en co-enseignement")


def _enseignants_sans_epp(db, school):
    """
    Sans identifiant EPP, l'enseignant n'est pas appariable avec la base académique : c'est une
    anomalie bloquante et non un simple champ manquant.

    Un identifiant non numérique est fautif au même titre qu'un identifiant absent : le schéma le
    contraint à des chiffres. Le contrôler ici plutôt qu'à la sérialisation, c'est la différence
    entre une ligne d'audit qui nomme l'enseignant et un échec de validation du document entier.
    """
    concernes = {
        t for c in _courses_a_remonter(db, school) for t in c.teachers
        if not t.epp_id or not str(t.epp_id).isdigit()
    }
    fautifs = sorted(concernes, key=lambda t: t.id)

    def _message(teacher):
        if not teacher.epp_id:
            return "Cet enseignant intervient sur un cours à remonter mais n'a pas d'identifiant EPP."
        return (f"L'identifiant EPP de cet enseignant n'est pas numérique "
                f"({teacher.epp_id}) : STS-web ne pourra pas l'apparier.")

    return [
        _anomalie("TEACHER_NO_EPP", BLOCKING, _message(t), "teachers", t.id, t.display_name)
        for t in fautifs[:MAX_PAR_CONTROLE]
    ] + _reste("TEACHER_NO_EPP", BLOCKING, fautifs, "enseignants sans identifiant EPP")


def _matieres_sans_code_national(db, school):
    """
    Une matière sans correspondance académique ne désigne aucun enseignement connu de STS-web.

    Le code national fait six caractères, chiffres et majuscules (030101, 020E00). Un code d'une
    autre forme est retenu ici plutôt qu'à la validation du document, pour la même raison que
    l'identifiant EPP : l'audit sait dire *quelle* matière est en cause.
    """
    def _mal_forme(subject):
        code = subject.code_nomenclature
        return not code or len(code) != 6 or not code.isalnum() or code != code.upper()

    concernes = {
        c.subject_relation for c in _courses_a_remonter(db, school)
        if c.subject_relation is not None and _mal_forme(c.subject_relation)
    }
    fautifs = sorted(concernes, key=lambda s: s.id)
    return [
        _anomalie("SUBJECT_NO_NATIONAL_CODE", BLOCKING,
                  f"Le code nomenclature de cette matière est absent ou mal formé "
                  f"({s.code_nomenclature or 'vide'}) : STS-web attend six caractères en chiffres "
                  f"et majuscules, et ne saura pas de quel enseignement il s'agit.",
                  "subjects", s.id, s.name)
        for s in fautifs[:MAX_PAR_CONTROLE]
    ] + _reste("SUBJECT_NO_NATIONAL_CODE", BLOCKING, fautifs, "matières sans code national")


def _groupes_sans_division(db, school):
    """
    Un groupe emprunte forcément ses élèves à une ou plusieurs divisions, et le fichier le dit par
    DIVISIONS_APPARTENANCE — qui n'admet pas d'être vide. C'est d'ailleurs le nombre de divisions
    listées qui distingue à lui seul un groupe (une seule) d'un regroupement (plusieurs).

    Dans le modèle, ce rattachement se lit par les parties de classe du groupe : un groupe sans
    partie n'a aucune division d'appartenance à déclarer.
    """
    concernes = {
        g for c in _courses_a_remonter(db, school) for g in c.groups
        if not any(cp.partition and cp.partition.division for cp in g.class_parts)
    }
    fautifs = sorted(concernes, key=lambda g: g.id)
    return [
        _anomalie("GROUP_NO_DIVISION", BLOCKING,
                  "Ce groupe n'est rattaché à aucune classe par ses parties de classe : le fichier "
                  "ne pourrait pas dire à quelles divisions il emprunte ses élèves.",
                  "groups", g.id, g.long_name or g.name)
        for g in fautifs[:MAX_PAR_CONTROLE]
    ] + _reste("GROUP_NO_DIVISION", BLOCKING, fautifs, "groupes sans division d'appartenance")


def _groupes_sans_effectif(db, school):
    """STS-web refuse la remontée d'un groupe dont l'effectif déclaré est nul : les effectifs sont
    à mettre à jour avant de générer le fichier."""
    concernes = {g for c in _courses_a_remonter(db, school) for g in c.groups if not g.student_count}
    fautifs = sorted(concernes, key=lambda g: g.id)
    return [
        _anomalie("GROUP_NO_HEADCOUNT", BLOCKING,
                  "Ce groupe est utilisé par un cours à remonter mais son effectif déclaré est nul.",
                  "groups", g.id, g.long_name or g.name)
        for g in fautifs[:MAX_PAR_CONTROLE]
    ] + _reste("GROUP_NO_HEADCOUNT", BLOCKING, fautifs, "groupes à effectif nul")


def _classes_sans_mef(db, school):
    """Une division sans MEF n'a pas de MEFS_APPARTENANCE à écrire, et STS-web ne saura pas à
    quelle formation rattacher ses services."""
    from backend.app.models.division import Division
    fautifs = [
        d for d in db.query(Division).filter(Division.school_id == school.id).all()
        if not d.is_excluded_from_sts and not d.mef_links
    ]
    return [
        _anomalie("DIVISION_NO_MEF", BLOCKING,
                  "Cette classe n'est rattachée à aucun MEF.",
                  "divisions", d.id, d.name)
        for d in fautifs[:MAX_PAR_CONTROLE]
    ] + _reste("DIVISION_NO_MEF", BLOCKING, fautifs, "classes sans MEF")


def _alternances_manquantes(db, school):
    """
    Les alternances sont indispensables à la remontée des services : elles disent quelles semaines
    de l'année chaque cours occupe.

    Le symptôme à guetter n'est PAS l'absence d'alternance sur le cours : un cours placé en a
    toujours une, puisque `_sync_alternation` la crée, et un cours en quinzaine indéterminée (Q)
    ne peut de toute façon pas être placé (voir Course.validate_placement_conflicts). Le vrai
    danger est une alternance qui ne couvre **aucune semaine** : le fichier porterait alors un
    `<SEMAINES/>` vide, c'est-à-dire un cours qui n'a lieu aucune semaine de l'année — accepté
    sans broncher par la validation, et faux.

    Deux causes : le calendrier des semaines n'a jamais été engendré, ou les périodes du cours ne
    recouvrent aucune semaine ouvrée.
    """
    from backend.app.models.week_calendar import WeekCalendar

    a_remonter = _courses_a_remonter(db, school)
    if not a_remonter:
        return []

    if db.query(WeekCalendar).count() == 0:
        return [_anomalie(
            "NO_WEEK_CALENDAR", BLOCKING,
            f"Le calendrier des semaines est vide : les {len(a_remonter)} séances à remonter "
            f"partiraient sans aucune semaine. Engendrez-le depuis « Calendrier des semaines ».",
            "week_calendars", None, "",
        )]

    sans_alternance = [c for c in a_remonter if c.alternation is None]
    vides = [c for c in a_remonter if c.alternation is not None and not c.alternation.week_calendar_ids]

    resultat = [
        _anomalie("COURSE_NO_ALTERNATION", BLOCKING,
                  "Ce cours n'a aucune alternance : impossible de dire quelles semaines il occupe.",
                  "courses", c.id, _libelle_cours(c))
        for c in sans_alternance[:MAX_PAR_CONTROLE]
    ] + _reste("COURSE_NO_ALTERNATION", BLOCKING, sans_alternance, "cours sans alternance")

    resultat += [
        _anomalie("ALTERNATION_NO_WEEK", BLOCKING,
                  f"L'alternance « {c.alternation.name} » de ce cours ne couvre aucune semaine : "
                  f"il partirait comme n'ayant lieu aucune semaine de l'année.",
                  "courses", c.id, _libelle_cours(c))
        for c in vides[:MAX_PAR_CONTROLE]
    ] + _reste("ALTERNATION_NO_WEEK", BLOCKING, vides, "cours dont l'alternance est vide")
    return resultat


def _quinzaines_non_tranchees(db, school):
    """
    Cours du périmètre de remontée dont le `week_type` est resté en **Q** : quinzaine dont le côté
    n'a pas encore été choisi. Ils n'ont pas d'alternance, donc rien à écrire comme calendrier, et
    `Course.is_exported_to_sts` les écarte.

    C'est justement pour ça que ce contrôle existe séparément : écartés de l'export, ils le sont
    aussi de `_courses_a_remonter`, et échapperaient donc à tous les autres contrôles — y compris
    à « cours non placés », alors qu'un cours en Q ne peut par construction pas être placé. Sans
    cette ligne, ils quitteraient la remontée sans que rien ne le signale.
    """
    from backend.app.models.course import Course, CourseWeekType

    fautifs = [
        c for c in db.query(Course).filter(
            Course.school_id == school.id, Course.week_type == CourseWeekType.Q
        ).all()
        if not c.is_composed and c.is_in_sts_scope
    ]
    return [
        _anomalie("COURSE_UNDECIDED_FORTNIGHT", BLOCKING,
                  "La quinzaine de ce cours n'est pas tranchée (semaine A ou B) : il n'a donc "
                  "aucune alternance et ne peut pas être remonté. Lancez la résolution ou "
                  "choisissez le côté à la main.",
                  "courses", c.id, _libelle_cours(c))
        for c in fautifs[:MAX_PAR_CONTROLE]
    ] + _reste("COURSE_UNDECIDED_FORTNIGHT", BLOCKING, fautifs, "cours en quinzaine non tranchée")


# --------------------------------------------------------------------------------------------
#  Avertissements
# --------------------------------------------------------------------------------------------

def _ponderations_heterogenes(db, school):
    """
    STS-web n'accepte qu'une pondération par service. Plutôt que d'arbitrer en silence, on le
    signale : l'export retient la pondération du cours.
    """
    fautifs = [c for c in _courses_a_remonter(db, school) if c.has_heterogeneous_weighting]
    return [
        _anomalie("HETEROGENEOUS_WEIGHTING", WARNING,
                  "Les intervenants de ce cours n'ont pas tous la même pondération ; STS-web n'en "
                  "accepte qu'une par service, c'est celle du cours qui sera retenue.",
                  "courses", c.id, _libelle_cours(c))
        for c in fautifs[:MAX_PAR_CONTROLE]
    ] + _reste("HETEROGENEOUS_WEIGHTING", WARNING, fautifs, "cours à pondérations hétérogènes")


def _services_non_consommes(db, school):
    """
    Un service dont le volume n'est pas entièrement placé peut valoir refus d'export ou simple
    indicateur, selon la sévérité qu'on lui prête. Retenu ici en **avertissement** : c'est un écart
    de volume, pas une impossibilité de produire le fichier.

    Aucun lien direct n'existe entre un `Course` et le `Service` dont il descend : la comparaison
    se fait donc par couple (classe, matière), en confrontant le volume hebdomadaire déclaré au
    service à la somme des durées des cours effectivement placés. C'est une approximation — deux
    services de la même matière sur la même classe seraient agrégés — mais elle est fidèle dans
    l'écrasante majorité des cas et n'exige aucune colonne supplémentaire.
    """
    from backend.app.models.service import Service
    from backend.app.models.division import Division

    divisions = {d.id: d for d in db.query(Division).filter(Division.school_id == school.id).all()}
    if not divisions:
        return []

    place = {}
    for course in _courses_a_remonter(db, school):
        if course.timeslot_id is None or course.subject_id is None:
            continue
        for division in course.divisions:
            cle = (division.id, course.subject_id)
            place[cle] = place.get(cle, 0) + (course.duration_minutes or 0)

    fautifs = []
    for service in db.query(Service).all():
        if service.division_id not in divisions or service.is_excluded_from_sts:
            continue
        attendu = sum(r.raw_need_weekly_duration_minutes or 0 for r in service.repartitions)
        if attendu and place.get((service.division_id, service.subject_id), 0) < attendu:
            fautifs.append(service)

    return [
        _anomalie("SERVICE_NOT_CONSUMED", WARNING,
                  "Les cours placés pour cette classe et cette matière ne couvrent pas le volume "
                  "horaire déclaré au service.",
                  "services", s.id,
                  f"{divisions[s.division_id].code} — {s.subject.short_name if s.subject else '?'}")
        for s in fautifs[:MAX_PAR_CONTROLE]
    ] + _reste("SERVICE_NOT_CONSUMED", WARNING, fautifs, "services non consommés")


def _reste(code, severity, fautifs, libelle):
    """Ligne de synthèse quand la liste a été tronquée : le compte total ne doit jamais
    disparaître, sous peine de faire croire à un audit complet."""
    surplus = len(fautifs) - MAX_PAR_CONTROLE
    if surplus <= 0:
        return []
    return [_anomalie(code, severity, f"… et {surplus} autres {libelle}.", None, None, "")]
