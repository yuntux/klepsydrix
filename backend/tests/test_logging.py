"""
Régression pour `core/log_context.py::attach_to_handlers` (voir sa docstring pour le détail du
piège) : un `DbContextFilter` posé via `logger.addFilter(...)` ne s'applique qu'aux enregistrements
qui ORIGINENT de ce logger précis, jamais à ceux propagés depuis un logger enfant — ça ne lève
AUCUNE exception visible (Python avale les erreurs de formatage de log), mais fait échouer
silencieusement le formatage de la quasi-totalité des appels réels (`logging.getLogger(__name__).
info/warning/exception(...)`, faits depuis n'importe quel module, jamais depuis le logger racine
lui-même). Bug réel trouvé en vérifiant en conditions réelles (pas par pytest seul) : la trace d'une
vraie exception (échec d'envoi d'email, voir test_password_reset.py) était remplacée par une erreur
de formatage de log, pas par le contenu utile qu'on cherchait à journaliser.

Tests isolés (un `logging.Logger` frais à chaque fois, jamais `logging.getLogger()` — le registre
global, mutable par n'importe quel autre test de la suite) pour ne dépendre d'aucun état ambiant ni
ordre d'exécution des autres fichiers de test.
"""
import io
import logging

from backend.app.core.log_context import DbContextFilter, attach_to_handlers, current_db_slug


def _isolated_logger_with_handler():
    logger = logging.Logger("test-isolated-logger", level=logging.INFO)
    capture = io.StringIO()
    handler = logging.StreamHandler(capture)
    handler.setFormatter(logging.Formatter("[db=%(db_slug)s] %(message)s"))
    logger.addHandler(handler)
    return logger, capture


def test_attach_to_handlers_puts_the_filter_on_the_handler_not_the_logger():
    logger, _ = _isolated_logger_with_handler()

    attach_to_handlers(logger)

    assert logger.filters == [], "le filtre ne doit jamais être posé sur le logger lui-même"
    assert any(isinstance(f, DbContextFilter) for f in logger.handlers[0].filters)


def test_a_log_call_formats_without_error_once_attached():
    logger, capture = _isolated_logger_with_handler()
    attach_to_handlers(logger)

    logger.info("message de test")

    output = capture.getvalue()
    assert "Logging error" not in output
    assert "message de test" in output


def test_the_wrong_placement_reproduces_the_original_bug(capsys):
    """Documente précisément ce qui casse si on revient à l'ancienne forme (`logger.addFilter` sur
    le logger RACINE) — sert de garde-fou si quelqu'un « simplifie » `attach_to_handlers` par erreur
    plus tard. Reproduit la vraie topologie du bug (parent/enfant, comme root vs.
    `logging.getLogger(__name__)` dans un module applicatif quelconque) : le filtre posé sur le
    PARENT ne s'applique qu'aux enregistrements qui ORIGINENT du parent lui-même, jamais à ceux
    propagés depuis l'enfant — appeler `.info()` directement sur le même logger où le filtre est
    posé (comme le ferait un test qui n'aurait pas cette hiérarchie) ne reproduirait PAS le bug.
    L'échec de formatage est avalé par `Handler.handleError` (écrit sur stderr, JAMAIS levé comme
    exception Python normale — voir `capsys`, pas le flux `capture` du handler lui-même, qui ne
    reçoit rien puisque le formatage échoue avant l'écriture)."""
    parent, capture = _isolated_logger_with_handler()
    parent.addFilter(DbContextFilter())  # l'ancienne forme, fautive : posée sur le LOGGER, pas le handler
    child = logging.Logger("test-isolated-logger.child", level=logging.INFO)
    child.parent = parent
    child.propagate = True

    child.info("message de test")

    assert capture.getvalue() == ""  # le message réel n'atteint jamais le flux de sortie
    assert "Logging error" in capsys.readouterr().err


def test_db_slug_from_the_contextvar_appears_in_the_formatted_line():
    logger, capture = _isolated_logger_with_handler()
    attach_to_handlers(logger)

    token = current_db_slug.set("timetable")
    try:
        logger.info("message de test")
    finally:
        current_db_slug.reset(token)

    assert "[db=timetable]" in capture.getvalue()
