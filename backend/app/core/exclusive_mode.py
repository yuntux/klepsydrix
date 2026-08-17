"""
Mode exclusif : empêche toute écriture en base pendant qu'une résolution automatique du solveur
est en cours (voir solver.py::_run_job_phases) — sans ça, un utilisateur pourrait modifier
des données (ex: contraintes d'un enseignant) sur lesquelles le solveur travaille déjà, ou voir
son écriture silencieusement écrasée par le résultat du solveur à la fin.

État stocké en base (pas seulement en mémoire, comme SolverState) : ce serveur applicatif pourra
un jour cohabiter avec plusieurs bases différentes sur une même instance Python/Java (voir
architecture.md) — le verrou doit donc vivre avec la base qu'il protège, pas dans un singleton
process-wide qui n'aurait aucun sens dès qu'il y aura plusieurs bases dans le même process.

Volontairement PAS un SystemSetting : ce n'est pas un paramètre utilisateur, et SystemSetting est
exposé tel quel via l'API générique (n'importe qui pourrait le modifier/supprimer depuis l'écran
de paramètres système). `exclusive_mode_state` est une Table SQLAlchemy Core, PAS une classe ORM
dérivée de Base : generic.py découvre ses ressources via Base.registry.mappers (uniquement les
classes ORM mappées), qui n'inclut jamais une Table Core brute — cette table reste donc invisible
à /api/generic/* sans qu'il faille de liste d'exclusion explicite à maintenir.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Table, Column, Integer, Boolean, String, DateTime, select, update, insert, event
from sqlalchemy.orm import Session
from backend.app.models.base import Base

_ROW_ID = 1

exclusive_mode_state = Table(
    "exclusive_mode_state",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("exclusive_active", Boolean, nullable=False, default=False),
    Column("exclusive_user", String(100), nullable=True),
    Column("exclusive_started_at", DateTime, nullable=True),
    Column("exclusive_ended_at", DateTime, nullable=True),
    Column("write_token", String(36), nullable=False),
)


class ExclusiveModeActiveError(Exception):
    """
    Levée par le garde-fou before_flush ci-dessous quand une écriture ORM est tentée pendant le
    mode exclusif, hors de la session du solveur lui-même. Capturée par generic.py pour répondre
    HTTP 423 (Locked) plutôt que le 400 générique.
    """
    pass


def _ensure_row(db: Session):
    existing = db.execute(select(exclusive_mode_state.c.id).where(exclusive_mode_state.c.id == _ROW_ID)).first()
    if existing is None:
        db.execute(insert(exclusive_mode_state).values(id=_ROW_ID, exclusive_active=False, write_token=str(uuid.uuid4())))


def enter_exclusive_mode(db: Session, user: str = "admin"):
    """
    Commit immédiatement, dans une transaction dédiée : le mode exclusif doit être visible par les
    AUTRES sessions/requêtes dès cet instant, pas seulement quand la session du solveur commitera
    (à la toute fin de la résolution) — sans quoi il ne bloquerait littéralement rien pendant toute
    la durée du solve.
    """
    _ensure_row(db)
    db.execute(update(exclusive_mode_state).where(exclusive_mode_state.c.id == _ROW_ID).values(
        exclusive_active=True, exclusive_user=user,
        exclusive_started_at=datetime.now(timezone.utc), exclusive_ended_at=None,
    ))
    db.commit()


def exit_exclusive_mode_and_rotate_token(db: Session) -> str:
    """
    NE COMMIT PAS elle-même : appelée juste avant le commit final qui persiste aussi les résultats
    du solveur (voir _run_job_phases), pour que sortie du mode exclusif + rotation du jeton +
    écriture des résultats forment une seule transaction atomique. Un crash entre deux commits
    séparés laisserait sinon un jeton périmé pointer vers des données pourtant déjà changées (ou,
    à l'inverse, un jeton fraîchement roté alors que les données n'ont en réalité pas bougé).
    """
    _ensure_row(db)
    new_token = str(uuid.uuid4())
    db.execute(update(exclusive_mode_state).where(exclusive_mode_state.c.id == _ROW_ID).values(
        exclusive_active=False, exclusive_ended_at=datetime.now(timezone.utc), write_token=new_token,
    ))
    return new_token


def clear_exclusive_mode(db: Session):
    """
    Lève le mode exclusif SANS toucher au jeton d'écriture : les données n'ont pas changé, aucune
    raison d'invalider les navigateurs déjà à jour. Deux appelants :
    - Le démarrage du process (main.py) : on sait qu'aucune résolution n'est réellement en cours
      juste après un boot, quel que soit l'état laissé en base par un arrêt brutal précédent.
    - Le chemin d'erreur de _run_job_phases : une exception pendant la résolution fait
      échouer le commit final qui aurait normalement levé le mode exclusif via
      exit_exclusive_mode_and_rotate_token — sans ce rattrapage, une résolution en erreur
      laisserait le mode exclusif bloqué jusqu'au prochain redémarrage du process.
    Commit dédié, comme enter_exclusive_mode : doit être visible immédiatement.
    """
    _ensure_row(db)
    db.execute(update(exclusive_mode_state).where(exclusive_mode_state.c.id == _ROW_ID).values(
        exclusive_active=False, exclusive_user=None, exclusive_started_at=None, exclusive_ended_at=None,
    ))
    db.commit()


def is_exclusive_mode_active(db: Session) -> bool:
    row = db.execute(select(exclusive_mode_state.c.exclusive_active).where(exclusive_mode_state.c.id == _ROW_ID)).first()
    return bool(row and row[0])


def get_write_token(db: Session) -> str:
    _ensure_row(db)
    db.commit()
    row = db.execute(select(exclusive_mode_state.c.write_token).where(exclusive_mode_state.c.id == _ROW_ID)).first()
    return row[0] if row else None


@event.listens_for(Session, "before_flush")
def _check_exclusive_mode(session, flush_context, instances):
    """
    Garde-fou global, au niveau SESSION (pas par instance comme les listeners before_insert/
    update/delete de base.py) : contrairement à ceux-ci, le mode exclusif doit bloquer TOUTE
    écriture ORM quel que soit son origine, y compris un futur code qui n'utiliserait pas
    CRUDMixin. La session du solveur lui-même échappe à ce contrôle via un simple flag posé sur
    sa propre session (session.info), le même principe que les flags _via_crud_mixin_* existants
    — jamais une vérification de rôle/utilisateur, juste "est-ce la session qui a légitimement le
    droit d'écrire pendant SA PROPRE fenêtre de mode exclusif".

    Écritures EXEMPTÉES par MODÈLE (`__exclusive_mode_exempt__ = True`, voir models/user.py,
    models/access.py, models/password_reset_token.py) : le mode exclusif protège les données de
    PLANNING dont le solveur dépend (cours, contraintes, préférences...) — pas la gestion des
    comptes/de la sécurité (connexion, jeton de réinitialisation, appartenance à un groupe), qui
    doit continuer à fonctionner normalement PENDANT une résolution (ex: le simple fait de
    consulter /status met à jour last_login_at à chaque requête, voir database.py::
    current_db_user — bloquer cette écriture cassait le polling de statut lui-même, trouvé en
    conditions réelles). Exemption tout ou rien PAR FLUSH, pas par écriture individuelle : si les
    objets en attente sont TOUS exemptés, le flush entier passe ; dès qu'UN SEUL objet ne l'est
    pas (ex: une écriture mêlée touchant aussi une donnée de planning), le blocage habituel
    s'applique à tout le flush — plus sûr que de trier écriture par écriture.
    """
    if session.info.get("bypass_exclusive_mode"):
        return
    pending = list(session.new) + list(session.dirty) + list(session.deleted)
    if not pending:
        return
    if all(getattr(obj, "__exclusive_mode_exempt__", False) for obj in pending):
        return
    if is_exclusive_mode_active(session):
        raise ExclusiveModeActiveError(
            "Une résolution automatique est en cours : aucune écriture n'est autorisée tant qu'elle n'est pas terminée."
        )
