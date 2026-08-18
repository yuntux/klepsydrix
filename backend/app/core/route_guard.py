"""
Garde-fou de portée des routes, vérifié au démarrage (voir architecture.md, moteur de droits).

Le moteur de droits ne s'active que si `db.klepsydrix_user_id` est posé sur la session, ce que
seul `current_db_user` fait, à la frontière HTTP (voir core/database.py). Une route applicative
montée sans cette dépendance ne PLANTE PAS : elle répond normalement, en mode système, avec
l'intégralité des données de la base — `CRUDMixin.read()` considère alors être appelé par du code
interne (seed, cascades, solveur) et ne filtre rien (voir models/base.py::_apply_access_read_filter).

C'est le seul type de défaillance qui ne se découvre jamais à l'usage : aucune erreur, aucun log,
juste des lignes qui n'auraient pas dû sortir. D'où une vérification au démarrage plutôt qu'une
relecture attentive : TOUTE route est concernée par défaut, et une route qui doit y échapper doit
le déclarer sur elle-même via @system_scoped. Rien à tenir à jour au centre — ajouter un routeur
sans dépendance de portée fait échouer le démarrage en nommant les routes fautives.
"""
from fastapi.routing import APIRoute


def system_scoped(reason: str):
    """
    Déclare une route délibérément hors moteur de droits (mode système).

    `reason` n'est pas décoratif : il force à formuler pourquoi, et c'est ce qu'on relit lors d'un
    audit. Réservé aux routes qui ne PEUVENT pas être authentifiées (l'authentification elle-même,
    le healthcheck) — pas un moyen de faire taire le garde-fou.
    """
    def decorator(func):
        func._system_scoped_reason = reason
        return func
    return decorator


def _depends_on(dependant, target) -> bool:
    """
    Cherche `target` dans l'arbre de dépendances d'une route. Récursif : une dépendance de routeur
    (`include_router(dependencies=[...])`) et une dépendance d'endpoint se retrouvent au même
    endroit, mais `current_db_user` peut aussi être atteint indirectement (il dépend lui-même de
    `require_instance_session` et de `get_db`) — un simple parcours du premier niveau raterait ces
    cas et donnerait un faux positif.
    """
    return any(d.call is target or _depends_on(d, target) for d in dependant.dependencies)


def assert_all_routes_scoped(app) -> None:
    """
    Lève au démarrage si une route n'est ni authentifiée ni explicitement marquée. Appelé depuis le
    `lifespan` (voir main.py) : toutes les routes sont déjà enregistrées à ce moment (les
    `include_router` s'exécutent à l'import du module), et le coût est nul en fonctionnement.
    """
    from backend.app.core.database import current_db_user
    from backend.app.core.instance_session import require_instance_session

    offenders = []
    for route in app.routes:
        # Les routes Starlette (/docs, /openapi.json, montages statiques) ne sont pas des endpoints
        # applicatifs : elles n'ont pas d'arbre de dépendances et ne servent aucune donnée de base.
        if not isinstance(route, APIRoute):
            continue
        if getattr(route.endpoint, "_system_scoped_reason", None):
            continue
        # Deux portées authentifiées distinctes, toutes deux acceptables :
        # - `current_db_user` : données d'UNE base, moteur de droits complet ;
        # - `require_instance_session` : administration de l'INSTANCE (crée/sauvegarde/supprime des
        #   bases). Ces routes n'agissent sur aucune ligne applicative, le moteur de droits n'a donc
        #   rien à y dire — mais l'identité doit être vérifiée, et elle l'est.
        if _depends_on(route.dependant, current_db_user) or _depends_on(route.dependant, require_instance_session):
            continue
        offenders.append(f"{'/'.join(sorted(route.methods))} {route.path}")

    if offenders:
        raise RuntimeError(
            "Routes ni authentifiées ni marquées @system_scoped — elles s'exécuteraient en mode "
            "système, moteur de droits désactivé :\n  "
            + "\n  ".join(sorted(offenders))
            + "\n\nAjoutez Depends(current_db_user) (données d'une base) ou "
              "Depends(require_instance_session) (administration de l'instance), ou "
              "@system_scoped(\"raison\") si l'absence d'authentification est délibérée."
        )
