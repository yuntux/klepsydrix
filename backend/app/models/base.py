import logging
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy import select, func
from sqlalchemy.ext.hybrid import hybrid_property
from datetime import date, datetime

logger = logging.getLogger(__name__)


class UnsupportedOperationError(Exception):
    """
    Levée par une opération CRUD volontairement non supportée par un modèle (ex:
    TransientModel.create()/update()/delete() : une ressource virtuelle/calculée ne peut pas être
    créée/modifiée/supprimée directement). Le moteur générique (generic.py) l'attrape
    spécifiquement dans create_endpoint/update_endpoint/delete_endpoint pour répondre 405, plutôt
    que le 400 générique réservé aux erreurs de validation métier (ValueError).
    """
    pass


class AccessDeniedError(Exception):
    """
    Levée par le moteur de droits (core/access_control.py) quand l'utilisateur courant
    (db.klepsydrix_user_id) n'a pas le droit demandé sur un modèle, ou que l'enregistrement visé ne
    satisfait pas le domaine restrictif applicable. Le moteur générique (generic.py) l'attrape pour
    répondre 403, plutôt que le 400 générique réservé aux erreurs de validation métier (ValueError).
    """
    pass


def requires_access(operation: str):
    """
    Marque une méthode comme appelable via /api/generic/{resource}/call/{method} ou
    /{resource}/{id}/call/{method} (voir architecture.md, moteur de droits) — `operation` ∈
    {"read", "write", "create", "unlink"}, le droit minimal exigé sur le MODÈLE (pas
    l'enregistrement précis visé) avant d'exécuter la méthode. Nécessaire en plus des contrôles
    déjà dans create()/update()/delete() : certaines méthodes RPC (calcul, export, déclenchement du
    solveur) ne passent par AUCUNE d'elles et échapperaient sinon à tout contrôle. Refus par défaut
    (generic.py) pour toute méthode non décorée.
    """
    def decorator(func):
        func._requires_access = operation
        return func
    return decorator


def constrains(*args):
    """
    Décorateur pour valider des contraintes métier.
    S'exécute lors de la création ou la modification des champs spécifiés.
    """
    def decorator(func):
        func._constrains = set(args)
        return func
    return decorator

def onchange(*args):
    """
    Décorateur pour assister la saisie dynamique dans le frontend.
    S'exécute lorsque l'un des champs spécifiés est modifié dans le formulaire.
    """
    def decorator(func):
        func._onchange = set(args)
        return func
    return decorator

class CRUDMixin:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Recherche et assigne automatiquement les champs 'related' du modèle
        cls._fields = [
            name for name, attr in cls.__dict__.items()
            if isinstance(attr, property) and getattr(attr, "_is_related", False)
        ]

        # Découverte automatique des champs calculés exposés à l'API
        exposed_fields = ["display_name"]
        for name, attr in cls.__dict__.items():
            if getattr(attr, "_is_exposed", False):
                exposed_fields.append(name)
            elif isinstance(attr, (property, hybrid_property)):
                if getattr(attr.fget, "_is_exposed", False) or getattr(attr.fset, "_is_exposed", False):
                    exposed_fields.append(name)
        existing = getattr(cls, "_extra_fields", [])
        cls._extra_fields = list(set(existing + exposed_fields))

    @property
    def display_name(self) -> str:
        if hasattr(self, "name") and getattr(self, "name") is not None:
            return str(self.name)
        return str(getattr(self, "id", "")) if getattr(self, "id", None) is not None else ""

    @requires_access("read")
    def ensure_related_record(self, relation_name: str):
        """
        Garantit que l'objet lié existe et le retourne.
        Surchargeable par les classes enfants (ex: _ensure_constraint_record).

        Appelée à distance via /call/ensure_related_record (voir App.vue::onSelectionChangeGeneric,
        panneaux GenericForm à relationName) — d'où @requires_access("read") : bien qu'un override
        comme _ensure_constraint_record puisse créer la ligne liée si elle n'existe pas encore
        (voir Division._ensure_constraint_record), l'usage réel est uniquement de charger l'onglet
        "Vœux et contraintes" pour AFFICHAGE. Exiger "write" bloquerait à tort tout utilisateur en
        lecture seule (déjà autorisé à voir ce panneau, readOnly étant géré séparément côté
        formulaire) — la sauvegarde effective d'une modification reste, elle, protégée par les
        contrôles d'accès propres à create()/update() sur le modèle lié.
        """
        handler_name = f"_ensure_{relation_name}"
        if hasattr(self, handler_name):
            return getattr(self, handler_name)()
        return getattr(self, relation_name, None)

    @classmethod
    def _coerce_values(cls, vals: dict):
        """Convertit les types basiques (str) en types complexes attendus par l'ORM (Enum Python)."""
        from sqlalchemy import inspect
        if not hasattr(cls, "__mapper__"):
            return
            
        mapper = inspect(cls)
        for key, value in list(vals.items()):
            if key in mapper.columns:
                col = mapper.columns[key]
                if hasattr(col.type, 'enum_class') and col.type.enum_class is not None:
                    if isinstance(value, str):
                        try:
                            vals[key] = col.type.enum_class(value)
                        except ValueError:
                            pass

    @classmethod
    def process_onchange(cls, db: Session, vals: dict, field_name: str) -> dict:
        """
        Traite un événement onchange sur un brouillon (Draft).
        Instancie le modèle en mémoire, applique les valeurs,
        exécute les méthodes @onchange concernées et renvoie les différences.

        L'instance elle-même reste transitoire (jamais `db.add()`-ée : aucune écriture n'est
        possible dessus, cf. les listeners `before_insert`/`before_update`). `db` sert uniquement
        à donner aux méthodes @onchange qui le demandent (paramètre nommé `db`) un accès en
        LECTURE à d'autres enregistrements déjà persistés — nécessaire dès qu'un onchange doit
        résoudre une relation à partir du seul id reçu (ex: lire le `country_id` d'une `RefCity`
        depuis `address_city_id`), impossible sans session : une relation ORM sur une instance
        jamais rattachée à une session ne se charge jamais (elle reste silencieusement vide), tout
        comme dans Odoo un `onchange` a accès à un environnement complet pour la même raison.
        """
        from sqlalchemy import inspect
        import enum

        local_vals = vals.copy()
        cls._coerce_values(local_vals)

        # Instanciation en mémoire sans base de données
        instance = cls()

        if not hasattr(cls, "__mapper__"):
            return {}

        mapper = inspect(cls)

        # Peuplement de l'instance
        for key, value in local_vals.items():
            if key in mapper.columns:
                setattr(instance, key, value)
            else:
                # Injection de relations mock pour les onchange
                for rel in mapper.relationships:
                    possible_keys = [f"{rel.key}_ids", f"{rel.key[:-1]}_ids", f"{rel.key[:-3]}y_ids"]
                    if rel.uselist and key in possible_keys and isinstance(value, list):
                        target_cls = rel.mapper.class_
                        mocks = []
                        for v in value:
                            m = target_cls()
                            m.id = v
                            mocks.append(m)
                        setattr(instance, rel.key, mocks)
                        break

        # Exécuter les méthodes @onchange qui écoutent ce field_name — les paramètres de la
        # méthode sont résolus par NOM (pas juste par position) : un paramètre nommé `db` reçoit
        # la session, tout autre nom (ex: `changed_field`, seul cas historique) reçoit field_name,
        # pour rester compatible avec les méthodes @onchange existantes qui ne demandent pas `db`.
        for attr_name in dir(instance):
            method = getattr(instance, attr_name)
            if callable(method) and hasattr(method, "_onchange"):
                trigger_fields = getattr(method, "_onchange")
                if field_name in trigger_fields:
                    import inspect as py_inspect
                    sig = py_inspect.signature(method)
                    kwargs = {p: (db if p == "db" else field_name) for p in sig.parameters}
                    method(**kwargs)

        # Extraire les différences
        result = {}
        for key in mapper.columns.keys():
            new_val = getattr(instance, key, None)
            if isinstance(new_val, enum.Enum):
                new_val = new_val.value
                
            # Si le champ n'était pas dans vals, ou si sa valeur a changé
            old_val = vals.get(key)
            if key not in vals and new_val is not None:
                result[key] = new_val
            elif key in vals and new_val != old_val:
                result[key] = new_val

        return result

    @staticmethod
    def _apply_owned_collection_commands(db: Session, obj, rel, raw_items: list):
        """
        Traite une collection possédée (relation à `parentField`, voir generic.py — même condition
        `rel.secondary is None`, systématiquement routée ici par create()/update() ci-dessous, y
        compris pour une liste vide ou une liste d'ids "à plat") sous forme de "commandes" à la
        Odoo (widget one2many) : chaque élément est soit un id nu (garder/rattacher tel quel, voir
        plus bas), soit un dict `{id?, **champs}` (id reconnu = mise à jour de cet enfant ; sans id
        = création). Tout enfant actuellement rattaché à `obj` mais absent de la liste soumise est
        supprimé.

        Ce mécanisme remplace l'ancien : une popin dédiée (GenericListModal) qui persistait
        immédiatement chaque création/modification/suppression d'un enfant, indépendamment du
        formulaire parent — deux écrivains distincts sur la même collection, à l'origine d'un bug
        réel (IntegrityError : le formulaire parent, rouvert après une mutation directe de la
        popin, resoumettait un tableau d'ids périmé ; ce module interprétait alors un enfant
        réellement en base mais absent de ce tableau comme "retiré", et tentait de mettre sa FK
        parent à NULL — échec garanti sur une colonne NOT NULL). Avec un seul écrivain (le
        formulaire, via ces commandes), la collection soumise est par construction toujours
        complète et à jour : tout ce qui n'y figure pas a été réellement supprimé par
        l'utilisateur, donc supprimé ici aussi (jamais orphelin avec FK à NULL, qui n'a de toute
        façon aucun sens pour un enfant qui n'existe pas indépendamment de son parent).

        La résolution d'un `id` soumis se fait par une requête GLOBALE (pas restreinte aux enfants
        déjà rattachés à `obj`) — même portée que l'ancien mécanisme "liste d'ids brute" qu'elle
        remplace : un enfant déjà existant mais pas encore rattaché doit pouvoir l'être (ex:
        `Course.rpc_save_composition`, qui crée d'abord chaque enfant isolément — sans `parent_id`
        — puis les rattache tous ici via `update(db, {"children_ids": [c.id for c in children]})`
        ; restreindre au parent courant romprait ce rattachement légitime et créerait à tort un
        doublon vide).
        """
        target_cls = rel.mapper.class_
        fk_attr = None
        for local_col, remote_col in rel.local_remote_pairs:
            if remote_col.table is target_cls.__table__:
                fk_attr = target_cls.__mapper__.get_property_by_column(remote_col).key
                break

        real_ids = list({cmd.get("id") if isinstance(cmd, dict) else cmd for cmd in raw_items
                          if (cmd.get("id") if isinstance(cmd, dict) else cmd) is not None})
        items_by_id = {}
        if real_ids:
            items_by_id = {item.id: item for item in db.execute(select(target_cls).filter(target_cls.id.in_(real_ids))).scalars().all()}

        current_items = getattr(obj, rel.key, None) or []
        kept_ids = set()
        ordered_items = []
        for cmd in raw_items:
            # Un entier nu (compatibilité avec l'ancienne liste d'ids "à plat") vaut "garder/
            # rattacher cette ligne telle quelle" — équivalent à un dict {id: X} sans autre champ.
            if not isinstance(cmd, dict):
                cmd = {"id": cmd}
            cmd_id = cmd.get("id")
            child_vals = {k: v for k, v in cmd.items() if k != "id"}
            if isinstance(cmd_id, int) and cmd_id in items_by_id:
                child = items_by_id[cmd_id]
                kept_ids.add(cmd_id)
                if fk_attr and getattr(child, fk_attr, None) != obj.id:
                    # Rattachement RÉEL (pas déjà lié à obj) — ex: Course.rpc_save_composition,
                    # qui crée les nouveaux enfants sans FK parent (voir docstring plus haut) puis
                    # les rattache ici par id nu. Sans ceci, cette FK n'était posée que par le
                    # setattr(obj, rel.key, ...) plus bas — une écriture ORM directe sur la
                    # collection qui ne déclenche AUCUNE règle métier de l'enfant (ex: Course ne
                    # synchronisait alors jamais timeslot_id/is_pinned depuis son nouveau parent
                    # tant qu'un solve ne repassait pas dessus — bug constaté). En l'incluant dans
                    # child_vals, le child.update() ci-dessous la traite comme n'importe quel
                    # changement de parent_id, avec toute la synchronisation que ça déclenche déjà
                    # normalement (_sync_vals_from_parent pour Course, ou l'équivalent pour tout
                    # autre modèle utilisant ce même mécanisme générique). Gardé au même niveau
                    # que child_vals plutôt qu'un setattr direct, pour ne jamais dupliquer le
                    # contournement volontaire des before_update (_via_crud_mixin_update).
                    child_vals[fk_attr] = obj.id
                if child_vals:
                    child.update(db, child_vals)
                ordered_items.append(child)
            else:
                if fk_attr:
                    child_vals[fk_attr] = obj.id
                ordered_items.append(target_cls.create(db, child_vals))

        for item in current_items:
            if item.id not in kept_ids:
                item.delete(db)

        setattr(obj, rel.key, ordered_items)

    @classmethod
    def default_get(cls, db: Session, context: dict) -> dict:
        """
        Point d'extension à surcharger par modèle pour calculer des valeurs par défaut d'un
        NOUVEL enregistrement à partir d'un contexte fourni par l'appelant (ex: la sélection
        courante d'un panneau maître dans un écran maître/détail) — pendant de default_get()
        côté Odoo. Contrairement à @onchange/process_onchange (évaluation en mémoire, sans BDD),
        cette méthode a accès à `db` et peut donc interroger la base. Retourne {} par défaut
        (aucun défaut dynamique) ; le contenu de `context` est un contrat libre entre le frontend
        et le modèle appelé, pas un schéma déclaré.
        """
        return {}

    @classmethod
    def _check_class_access(cls, db: Session, operation: str):
        """
        Vérifie que l'utilisateur courant a le droit `operation` sur ce modèle, SANS enregistrement
        précis à confronter à un domaine (création — voir architecture.md : contrairement à
        Odoo, un domaine restrictif n'est jamais évalué à la création, seul perm_create compte).
        Mode système (db.klepsydrix_user_id absent) : toujours autorisé.
        """
        user_id = getattr(db, "klepsydrix_user_id", None)
        if user_id is None:
            return
        from backend.app.core.access_control import access_rows_for
        from backend.app.models.user import User
        user = db.get(User, user_id)
        if not access_rows_for(db, cls, user, operation):
            raise AccessDeniedError(f"Droit « {operation} » refusé sur {cls.__tablename__}.")

    def _check_instance_access(self, db: Session, operation: str):
        """Pendant instance de _check_class_access, pour update()/delete() : vérifie EN PLUS que
        `self` satisfait le domaine restrictif applicable (voir access_control.access_domain_clause)."""
        user_id = getattr(db, "klepsydrix_user_id", None)
        if user_id is None:
            return
        from backend.app.core.access_control import access_domain_clause
        from backend.app.models.user import User
        cls = self.__class__
        user = db.get(User, user_id)
        has_access, clause = access_domain_clause(db, cls, user, operation)
        if not has_access:
            raise AccessDeniedError(f"Droit « {operation} » refusé sur {cls.__tablename__}.")
        if clause is not None:
            exists = db.query(cls.id).filter(cls.id == self.id).filter(clause).first()
            if exists is None:
                raise AccessDeniedError(f"Droit « {operation} » refusé sur cet enregistrement de {cls.__tablename__}.")

    @classmethod
    def create(cls, db: Session, vals: dict):
        """
        Méthode de création standard surchargeable avec gestion des related_fields.
        """
        cls._check_class_access(db, "create")
        try:
            original_vals_keys = set(vals.keys())
            # 1. Inspecter et extraire les relations de type collection (Many-to-Many / One-to-Many)
            from sqlalchemy import inspect
            collection_updates = {}
            if hasattr(cls, "__mapper__"):
                mapper = inspect(cls)
                for rel in mapper.relationships:
                    if rel.uselist:
                        possible_keys = [f"{rel.key}_ids"]
                        if rel.key.endswith("s"):
                            possible_keys.append(f"{rel.key[:-1]}_ids")
                        if rel.key.endswith("ies"):
                            possible_keys.append(f"{rel.key[:-3]}y_ids")
                        
                        for pk in possible_keys:
                            if pk in vals:
                                ids = vals.pop(pk)
                                if ids is not None:
                                    collection_updates[rel.key] = (rel, ids)
                                break

            # 2. Séparer les champs related des champs locaux
            related_vals = {}
            local_vals = {}
            for k, v in vals.items():
                if k in getattr(cls, "_fields", []):
                    prop = getattr(cls, k)
                    relation_name = prop.relation_name
                    if relation_name not in related_vals:
                        related_vals[relation_name] = {}
                    related_vals[relation_name][k] = v
                else:
                    local_vals[k] = v

            # 3. Créer l'enregistrement local principal
            cls._coerce_values(local_vals)
            instance = cls(**local_vals)
            instance._via_crud_mixin_create = True
            db.add(instance)
            db.flush()  # Génère l'ID en base sans commiter (le commit est géré par l'endpoint)

            # 4. Assurer l'existence et mettre à jour les enregistrements liés
            for relation_name, fields in related_vals.items():
                related_obj = instance.ensure_related_record(relation_name)
                if related_obj:
                    related_obj._via_crud_mixin_update = True
                    for k, v in fields.items():
                        prop = getattr(cls, k)
                        setattr(related_obj, prop.target_field, v)

            # 5. Mettre à jour les relations collection
            for rel_key, (rel, ids) in collection_updates.items():
                # Une relation possédée (rel.secondary is None, voir generic.py::parentField —
                # même condition, TOUJOURS exposée à l'identique côté schéma) passe systématiquement
                # par les commandes façon Odoo, y compris une liste vide (tout retirer) : le
                # contenu de la liste (dicts, ids nus, ou rien du tout) ne doit pas déterminer le
                # mécanisme utilisé, sans quoi une liste vide retomberait à tort sur le chemin
                # legacy ci-dessous (qui tente de mettre la FK à NULL au lieu de supprimer).
                if rel.secondary is None:
                    cls._apply_owned_collection_commands(db, instance, rel, ids)
                    continue

                target_cls = rel.mapper.class_
                items_by_id = {item.id: item for item in db.execute(select(target_cls).filter(target_cls.id.in_(ids))).scalars().all()}
                ordered_items = [items_by_id[i] for i in ids if i in items_by_id]
                setattr(instance, rel_key, ordered_items)

                # Gestion d'un champ d'ordre sur la table d'association
                order_col_name = rel.info.get("ordered_by") if rel.info else None
                if order_col_name and rel.secondary is not None:
                    db.flush()
                    local_col = next((fk.parent for fk in rel.secondary.foreign_keys if fk.column.table == cls.__table__), None)
                    target_col = next((fk.parent for fk in rel.secondary.foreign_keys if fk.column.table == target_cls.__table__), None)
                    if local_col is not None and target_col is not None and order_col_name in rel.secondary.c:
                        for i, item in enumerate(ordered_items):
                            db.execute(rel.secondary.update().where(
                                (local_col == instance.id) &
                                (target_col == item.id)
                            ).values(**{order_col_name: i}))

            db.flush()

            # Autorise les mutations directes faites par les @constrains ci-dessous (ex:
            # compute_name qui fait self.name = ...) — posé AVANT la boucle, pas après : un
            # @constrains qui accède à une relation encore jamais chargée (lazy load) déclenche
            # un autoflush SQLAlchemy qui persisterait alors une mutation antérieure de CETTE
            # même boucle hors de toute protection (voir receive_before_update), symétrique avec
            # update() ci-dessous qui pose ce flag avant sa propre boucle de contraintes.
            instance._via_crud_mixin_update = True

            # 6. Exécuter les contraintes métier
            for attr_name in dir(instance):
                method = getattr(instance, attr_name)
                if callable(method) and hasattr(method, "_constrains"):
                    constrained_fields = getattr(method, "_constrains")
                    if not constrained_fields or any(f in original_vals_keys for f in constrained_fields):
                        method(db)

            db.flush()
            db.refresh(instance)
            return instance
        except Exception as e:
            db.rollback()
            raise e

    @classmethod
    def _apply_domain(cls, query, domain: dict):
        """
        Applique un dict de filtres à une requête SQLAlchemy. Cas particulier : une valeur
        liste/tuple/set sur la clé "id" devient un IN(...) plutôt qu'une égalité — utilisé par
        l'endpoint liste générique pour le filtre ?ids=1,2,3 (voir generic.py, GenericListModal
        et GenericPivot, architecture.md section 15.L), sans quoi ce cas nécessiterait une
        branche dédiée dans generic.py plutôt qu'un simple domain["id"] = [...].
        """
        for key, value in domain.items():
            if not hasattr(cls, key):
                continue
            if key == "id" and isinstance(value, (list, tuple, set)):
                query = query.filter(cls.id.in_(value))
            else:
                query = query.filter(getattr(cls, key) == value)
        return query

    @classmethod
    def _apply_access_read_filter(cls, db: Session, query):
        """
        Filtre de lecture du moteur de droits (voir core/access_control.py, architecture.md) —
        appliqué par read() ET count() pour rester cohérent (une pagination ne doit jamais annoncer
        un total supérieur à ce que read() peut réellement renvoyer). `db.klepsydrix_user_id`
        absent (drapeau ambiant, posé UNIQUEMENT à la frontière HTTP par current_db_user, voir
        database.py) = mode système, aucun filtrage — tout le code interne (cascades, @constrains,
        seed, solveur) continue de voir l'intégralité des données.
        """
        user_id = getattr(db, "klepsydrix_user_id", None)
        if user_id is None:
            return query
        from sqlalchemy import false
        from backend.app.core.access_control import access_domain_clause
        from backend.app.models.user import User
        user = db.get(User, user_id)
        has_access, clause = access_domain_clause(db, cls, user, "read")
        if not has_access:
            return query.where(false())
        if clause is not None:
            query = query.where(clause)
        return query

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        """
        Lit des enregistrements à partir de la base de données.
        Retourne une liste d'instances Python du modèle.
        """
        query = select(cls)
        if domain:
            query = cls._apply_domain(query, domain)
        query = cls._apply_access_read_filter(db, query)
        # Tri par défaut explicite : sans lui, l'ordre de retour n'est garanti par aucun SGBD (il
        # « semble » suivre l'ordre d'insertion sur SQLite, mais c'est un hasard d'implémentation,
        # pas une garantie — non déterministe sur PostgreSQL). Surchargeable par modèle via
        # `__default_order__` (ex: un tri par nom plutôt que par id) ; silencieusement absent pour
        # un modèle sans colonne `id` (aucun cas dans ce projet à ce jour).
        order_by = getattr(cls, "__default_order__", None)
        if order_by is None and hasattr(cls, "id"):
            order_by = cls.id
        if order_by is not None:
            query = query.order_by(order_by)
        if offset is not None:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
        return db.execute(query).scalars().all()

    @classmethod
    def browse(cls, db: Session, ids: list):
        """
        Lecture par identifiants explicitement DÉSIGNÉS — pendant de read(), qui répond lui à une
        RECHERCHE. Même moteur de droits, deux comportements, parce que ce sont deux questions
        différentes (même distinction que search()/browse() chez Odoo) :

        - `read()` filtre silencieusement, et c'est correct : sur une recherche, le filtrage EST le
          résultat attendu (« les classes que j'ai le droit de voir ») ;
        - `browse()` refuse dès qu'un seul identifiant demandé manque à l'appel. L'appelant a nommé
          ce qu'il voulait : en recevoir moins sans le savoir produirait un résultat incomplet
          d'apparence complète — un PDF amputé de deux classes, un export tronqué, un traitement
          par lot qui en oublie la moitié. C'est un pire mode de défaillance qu'un refus, parce
          qu'il est indétectable côté appelant.

        Ne dit jamais QUEL identifiant a échoué, ni s'il est inexistant ou hors du domaine de
        l'utilisateur — même politique que le 404 de l'API générique sur un identifiant unique, qui
        refuse déjà de confirmer l'existence d'un enregistrement non lisible.

        Lève `AccessDeniedError` (jamais une exception HTTP : c'est la couche modèle) — la
        traduction en statut HTTP appartient à l'appelant, directement ou via le gestionnaire
        global de `core/error_handlers.py`.

        ⚠️ Repose sur `read()`, donc sur la prise en charge d'un domaine `{"id": [...]}`. Vrai pour
        tout modèle mappé ; pour un `TransientModel`, dépend de son implémentation de `read()`.
        """
        # Dédoublonne en conservant l'ordre : sans ça, browse([1, 1]) échouerait toujours, la
        # comparaison de longueurs ci-dessous portant sur des ensembles de tailles différentes.
        ids = list(dict.fromkeys(ids))
        if not ids:
            return []
        records = cls.read(db, domain={"id": ids})
        if len(records) != len(ids):
            raise AccessDeniedError(
                f"Certains enregistrements demandés de {cls.__tablename__} sont inaccessibles ou n'existent plus."
            )
        # Ordre DEMANDÉ, pas __default_order__ : sur un lot désigné (imprimer les classes dans
        # l'ordre coché), c'est l'ordre de l'appelant qui fait foi. Même comportement qu'Odoo.
        by_id = {record.id: record for record in records}
        return [by_id[identifier] for identifier in ids]

    @classmethod
    def count(cls, db: Session, domain: dict = None) -> int:
        """
        Pendant de read() pour le total non paginé (utilisé par l'endpoint liste générique). Une
        méthode dédiée plutôt qu'un simple len(read(...)) : éviter de charger tous les
        enregistrements juste pour les compter.
        """
        query = select(func.count()).select_from(cls)
        if domain:
            query = cls._apply_domain(query, domain)
        query = cls._apply_access_read_filter(db, query)
        return db.scalar(query)

    @classmethod
    def clean_payload(cls, payload_dict: dict, allow_null: bool = False) -> dict:
        """
        Filtre et type-cast un payload brut (JSON) vers des valeurs Python acceptées par create()/
        update() : ne garde que les clés qui correspondent à une vraie colonne, un champ dérivé
        (_fields) ou une relation collection (_ids), et convertit les dates/datetimes ISO en
        objets Python. Déplacé depuis generic.py (module-level clean_payload()) pour que
        TransientModel puisse fournir sa propre version triviale (aucun typage SQL à faire) sans
        que l'endpoint générique ait besoin de savoir de quel type de modèle il s'agit.

        allow_null : par défaut (create, et tout appel qui ne le précise pas), une valeur None est
        systématiquement ignorée — utile en création pour laisser les defaults SQL s'appliquer.
        make_update_endpoint passe allow_null=True : les éditeurs inline renvoient l'enregistrement
        complet, donc un champ que l'utilisateur vient d'effacer arrive à None dans ce payload — le
        filtrer silencieusement rendait le bouton "×" inopérant (voir architecture.md). On ne
        laisse passer le None que pour une vraie colonne SQL (pas les _fields/relations _ids, dont
        la sémantique de "null" n'est pas de simples colonnes nullable) ; une colonne NOT NULL
        remontera alors une erreur explicite d'intégrité au lieu d'un silence trompeur — le
        frontend ne doit de toute façon jamais proposer d'effacer un champ non-nullable (voir
        `nullable` exposé par generic.py::make_pydantic_model).
        """
        cleaned = {}
        valid_keys = [c.name for c in cls.__table__.columns if c.name != "id"]
        # Nom trompeur historique (ce n'est PAS cls._extra_fields, où vivent les champs @exposed
        # calculés à la demande comme Course.student_ids) — ce sont uniquement les related_field
        # (property _is_related, ex: Service.division_id). L'exclusion de cls._extra_fields d'un
        # payload d'écriture est VOULUE : un champ @exposed est calculé, jamais éditable, et pour
        # celui qui n'a pas de setter, le laisser passer jusqu'à CRUDMixin.update()/create() ferait
        # planter setattr()/le constructeur avec une erreur brute (bug réel constaté avec
        # Course.student_ids réémis tel quel par un formulaire qui renvoyait l'enregistrement
        # complet). Ne jamais élargir cette liste à cls._extra_fields sans garder ce filtrage.
        related_fields = getattr(cls, "_fields", [])

        relationship_keys = []
        from sqlalchemy.orm import Mapper
        if hasattr(cls, "__mapper__") and isinstance(cls.__mapper__, Mapper):
            for rel in cls.__mapper__.relationships:
                if rel.uselist:
                    field_name = f"{rel.key}_ids"
                    if rel.key.endswith("s"):
                        field_name = f"{rel.key[:-1]}_ids"
                    elif rel.key.endswith("ies"):
                        field_name = f"{rel.key[:-3]}y_ids"
                    relationship_keys.append(field_name)

        all_keys = valid_keys + related_fields + relationship_keys
        for k, v in payload_dict.items():
            if k not in all_keys:
                continue
            if v is None:
                if allow_null and k not in related_fields and k not in relationship_keys:
                    cleaned[k] = None
                continue
            if k in related_fields or k in relationship_keys:
                cleaned[k] = v
                continue
            column_type = cls.__table__.columns[k].type
            if str(column_type) == "DATE" and v:
                cleaned[k] = date.fromisoformat(v) if isinstance(v, str) else v
            elif str(column_type) == "DATETIME" and v:
                cleaned[k] = datetime.fromisoformat(v) if isinstance(v, str) else v
            else:
                cleaned[k] = v
        return cleaned


    def update(self, db: Session, vals: dict):
        """
        Méthode de mise à jour standard surchargeable avec gestion des related_fields.
        """
        self._check_instance_access(db, "write")
        try:
            original_vals_keys = set(vals.keys())
            # 1. Inspecter et extraire les relations de type collection (Many-to-Many / One-to-Many)
            from sqlalchemy import inspect
            collection_updates = {}
            if hasattr(self, "__mapper__"):
                mapper = inspect(self.__class__)
                for rel in mapper.relationships:
                    if rel.uselist:
                        possible_keys = [f"{rel.key}_ids"]
                        if rel.key.endswith("s"):
                            possible_keys.append(f"{rel.key[:-1]}_ids")
                        if rel.key.endswith("ies"):
                            possible_keys.append(f"{rel.key[:-3]}y_ids")
                        
                        for pk in possible_keys:
                            if pk in vals:
                                ids = vals.pop(pk)
                                if ids is not None:
                                    collection_updates[rel.key] = (rel, ids)
                                break

            # 2. Séparer les champs related des champs locaux
            related_vals = {}
            local_vals = {}
            for k, v in vals.items():
                if k in getattr(self, "_fields", []):
                    prop = getattr(self.__class__, k)
                    relation_name = prop.relation_name
                    if relation_name not in related_vals:
                        related_vals[relation_name] = {}
                    related_vals[relation_name][k] = v
                else:
                    local_vals[k] = v

            # 3. Mettre à jour l'enregistrement principal
            self._via_crud_mixin_update = True
            self.__class__._coerce_values(local_vals)
            for key, value in local_vals.items():
                # Un champ @exposed calculé (property sans fset, ex: Course.student_ids) ne doit
                # jamais être appliqué même s'il apparaît dans vals — clean_payload() l'exclut déjà
                # normalement (voir son commentaire), mais cette méthode peut aussi être appelée
                # directement avec un dict qui n'est jamais passé par clean_payload (scripts, code
                # métier interne). Sans ce garde-fou, setattr() plante avec une AttributeError brute
                # ("property 'X' of 'Y' object has no setter") au lieu d'être ignoré proprement —
                # bug réel constaté avec Course.student_ids (voir architecture.md, moteur générique).
                attr = getattr(type(self), key, None)
                if isinstance(attr, property) and attr.fset is None:
                    continue
                if hasattr(self, key):
                    setattr(self, key, value)

            # 4. Assurer l'existence et mettre à jour les enregistrements liés
            for relation_name, fields in related_vals.items():
                related_obj = self.ensure_related_record(relation_name)
                if related_obj:
                    related_obj._via_crud_mixin_update = True
                    for k, v in fields.items():
                        prop = getattr(self.__class__, k)
                        setattr(related_obj, prop.target_field, v)

            # 5. Mettre à jour les relations collection
            for rel_key, (rel, ids) in collection_updates.items():
                # Une relation possédée (rel.secondary is None, voir generic.py::parentField —
                # même condition, TOUJOURS exposée à l'identique côté schéma) passe systématiquement
                # par les commandes façon Odoo, y compris une liste vide (tout retirer) : le
                # contenu de la liste (dicts, ids nus, ou rien du tout) ne doit pas déterminer le
                # mécanisme utilisé, sans quoi une liste vide retomberait à tort sur le chemin
                # legacy ci-dessous (qui tentait de mettre la FK à NULL au lieu de supprimer — bug
                # d'origine, voir _apply_owned_collection_commands).
                if rel.secondary is None:
                    self._apply_owned_collection_commands(db, self, rel, ids)
                    continue

                # Chemin restant : un vrai many-to-many (rel.secondary is not None, ex:
                # Service.teachers) — ses enregistrements existent indépendamment du parent, une
                # simple liste d'ids à rattacher/détacher, jamais de create/update/delete implicite.
                target_cls = rel.mapper.class_
                items_by_id = {item.id: item for item in db.execute(select(target_cls).filter(target_cls.id.in_(ids))).scalars().all()}
                ordered_items = [items_by_id[i] for i in ids if i in items_by_id]
                setattr(self, rel_key, ordered_items)

                # Gestion d'un champ d'ordre sur la table d'association
                order_col_name = rel.info.get("ordered_by") if rel.info else None
                if order_col_name and rel.secondary is not None:
                    db.flush()
                    local_col = next((fk.parent for fk in rel.secondary.foreign_keys if fk.column.table == self.__class__.__table__), None)
                    target_col = next((fk.parent for fk in rel.secondary.foreign_keys if fk.column.table == target_cls.__table__), None)
                    if local_col is not None and target_col is not None and order_col_name in rel.secondary.c:
                        for i, item in enumerate(ordered_items):
                            db.execute(rel.secondary.update().where(
                                (local_col == self.id) &
                                (target_col == item.id)
                            ).values(**{order_col_name: i}))

            db.flush()  # Flush sans commit : le commit est géré par l'endpoint

            # 6. Exécuter les contraintes métier
            for attr_name in dir(self):
                method = getattr(self, attr_name)
                if callable(method) and hasattr(method, "_constrains"):
                    constrained_fields = getattr(method, "_constrains")
                    if not constrained_fields or any(f in original_vals_keys for f in constrained_fields):
                        method(db)

            db.flush()
            db.refresh(self)
            return self
        except Exception as e:
            db.rollback()
            raise e

    def _cascade_delete_dependents(self, db: Session):
        """
        Avant la suppression, traite explicitement CHAQUE ligne d'une autre table qui référence
        self via une clé étrangère — en se basant uniquement sur le schéma (ForeignKey.ondelete),
        systématiquement déclaré sur chaque FK de ce projet, et PAS sur une éventuelle
        relationship() ORM déclarée. Une relation qu'on aurait oublié de déclarer côté ORM (c'est
        exactement ce qui manquait pour MefDivision -> Service avant ce correctif) est donc
        protégée exactement comme les autres, sans configuration à ajouter au cas par cas.

        - ondelete="CASCADE"  : l'enfant est supprimé via son propre .delete() — cascade réelle,
          récursive (chaque enfant traite à son tour ses propres dépendants).
        - ondelete="SET NULL" : l'enfant SURVIT, mais sa FK est mise à NULL via un vrai .update(),
          ce qui revalide ses @constrains() — si ça viole un invariant métier (ex: Service exige
          exactement un de mef_division_id/group_id), l'update() lève une erreur et annule toute
          la suppression, plutôt que de corrompre silencieusement les données.
        - "RESTRICT"/"NO ACTION"/None : si au moins une ligne référence encore self, lève une
          ValueError explicite AVANT toute tentative SQL — plutôt que de laisser la BDD renvoyer
          une IntegrityError brute (message technique Postgres/SQLite) remontée telle quelle par
          l'endpoint générique. Prolongement du même principe piloté par le schéma : aucun code à
          écrire par modèle pour qu'une suppression bloquée par une FK RESTRICT (ex: un ref_ara
          encore utilisé par un teacher_ara) produise un message métier clair.
        - Tables sans classe mappée (tables d'association pures type service_teachers) : ignorées
          — aucune logique métier n'est portée par une ligne d'association, le ondelete=CASCADE de
          la table suffit.
        """
        if not hasattr(self, "__mapper__"):
            return
        from sqlalchemy import inspect
        from sqlalchemy.orm import class_mapper

        table = self.__class__.__table__
        table_to_class = {m.local_table: m.class_ for m in Base.registry.mappers}

        for other_table in Base.metadata.tables.values():
            for fk in other_table.foreign_keys:
                if fk.column.table is not table:
                    continue
                child_cls = table_to_class.get(other_table)
                if child_cls is None:
                    continue  # table d'association pure (secondary=) : pas de logique métier à protéger
                fk_attr = class_mapper(child_cls).get_property_by_column(fk.parent).key
                if fk.ondelete in ("CASCADE", "SET NULL"):
                    children = db.query(child_cls).filter(getattr(child_cls, fk_attr) == self.id).all()
                    for child in children:
                        if fk.ondelete == "CASCADE":
                            if not getattr(child, '_via_crud_mixin_delete', False):
                                child.delete(db)
                        else:
                            child.update(db, {fk_attr: None})
                elif db.query(child_cls).filter(getattr(child_cls, fk_attr) == self.id).first():
                    raise ValueError(f"Impossible de supprimer : au moins un enregistrement dans « {other_table.name} » y fait encore référence.")

    def delete(self, db: Session):
        """
        Marque l'objet pour suppression. Le commit est géré par l'endpoint.
        """
        self._check_instance_access(db, "unlink")
        self._via_crud_mixin_delete = True
        self._cascade_delete_dependents(db)
        try:
            db.delete(self)
            db.flush()
            return True
        except Exception as e:
            db.rollback()
            raise e

# Base déclarative commune pour tous les modèles SQLAlchemy
class Base(DeclarativeBase, CRUDMixin):
    pass

def exposed(attr=None, *, info=None):
    """
    Décorateur pour exposer un champ virtuel (@property ou @hybrid_property) dans la
    sérialisation automatique du CRUDMixin / API générique. Utilisable nu (@exposed) ou avec
    métadonnées explicites (@exposed(info={"type": "duration", ...})) — même convention que
    Column(info=...)/related_field(info=...), lue par generic.py via le même mécanisme de
    passthrough générique déjà en place pour les champs virtuels (descriptor.info, voir
    make_pydantic_model, branche _extra_fields) : aucun changement requis côté generic.py.
    """
    if attr is not None:
        return _exposed_impl(attr, info)

    def decorator(inner_attr):
        return _exposed_impl(inner_attr, info)
    return decorator


def _exposed_impl(attr, info):
    from sqlalchemy.ext.hybrid import hybrid_property

    # 1. Si c'est un property natif (qui n'autorise pas les attributs dynamiques en C)
    if isinstance(attr, property) and not type(attr).__name__.endswith("exposed_property"):
        class custom_exposed_property(property):
            _is_exposed = True
        result = custom_exposed_property(attr.fget, attr.fset, attr.fdel, attr.__doc__)
        result.info = info or {}
        return result

    # 2. Si c'est une hybrid_property
    if isinstance(attr, hybrid_property):
        try:
            attr._is_exposed = True
            attr.info = info or {}
            return attr
        except AttributeError:
            class custom_exposed_hybrid(hybrid_property):
                _is_exposed = True
            expr = getattr(attr, "custom_expression", None)
            result = custom_exposed_hybrid(attr.fget, attr.fset, attr.fdel, expr=expr)
            result.info = info or {}
            return result

    # 3. Si c'est une fonction (décorateur placé sous @property)
    if callable(attr):
        attr._is_exposed = True
        attr.info = info or {}
        return attr

    # 4. Par défaut, on tente de poser l'attribut
    try:
        attr._is_exposed = True
        attr.info = info or {}
    except AttributeError:
        pass
    return attr

class related_field(property):
    """
    Subclass de property qui simule un champ 'related' à la Odoo dans SQLAlchemy.
    Permet la découverte dynamique des propriétés virtuelles.
    """
    def __init__(self, relation_name: str, target_field: str, default=None, info=None):
        self.relation_name = relation_name
        self.target_field = target_field
        self.default = default
        self.info = info or {}
        self._is_related = True

        def getter(instance):
            related_obj = getattr(instance, relation_name)
            if not related_obj:
                return default
            return getattr(related_obj, target_field, default)

        def setter(instance, value):
            related_obj = getattr(instance, relation_name)
            if related_obj:
                setattr(related_obj, target_field, value)

        super().__init__(getter, setter)

class TransientModel:
    """
    Classe de base pour les objets métiers virtuels/transitoires.
    Ces objets ne sont pas stockés en base de données physique
    mais exposent l'interface standard CRUDMixin pour l'API générique.
    """
    __tablename__ = None
    _fields = []
    # Métadonnées par champ (label/type/readOnly/...), pendant de column.info pour un modèle SQL
    # réel — lu par make_pydantic_model (generic.py) pour exposer ui_type/title au frontend, ex:
    # {"info_html": {"type": "html", "label": "", "readOnly": True}}. Vide par défaut : aucun
    # changement de comportement pour un TransientModel qui ne le déclare pas.
    _field_info: dict = {}

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        raise NotImplementedError("Les modèles transitoires doivent implémenter la méthode read().")

    @classmethod
    def count(cls, db: Session, domain: dict = None) -> int:
        """
        Pas de requête dédiée possible (pas de table) : read() porte déjà tout le calcul, donc
        count() se contente d'en mesurer le résultat non paginé. Les sous-classes coûteuses à
        calculer peuvent surcharger count() si nécessaire.
        """
        return len(cls.read(db, domain=domain))

    @classmethod
    def clean_payload(cls, payload_dict: dict, allow_null: bool = False) -> dict:
        """Aucune colonne SQL à typer/filtrer pour une ressource virtuelle : payload accepté tel quel."""
        return payload_dict

    @classmethod
    def create(cls, db: Session, vals: dict):
        raise UnsupportedOperationError(f"La création n'est pas supportée pour la ressource transitoire {cls.__tablename__ or cls.__name__}.")

    def update(self, db: Session, vals: dict):
        raise UnsupportedOperationError(f"La mise à jour n'est pas supportée pour la ressource transitoire {self.__class__.__tablename__ or self.__class__.__name__}.")

    def delete(self, db: Session):
        raise UnsupportedOperationError(f"La suppression n'est pas supportée pour la ressource transitoire {self.__class__.__tablename__ or self.__class__.__name__}.")

from sqlalchemy import event
from sqlalchemy.orm import object_session

@event.listens_for(Base, 'before_insert', propagate=True)
def receive_before_insert(mapper, connection, target):
    if not getattr(target, '_via_crud_mixin_create', False):
        raise RuntimeError(f"Création directe interdite pour {target.__class__.__name__}. Utilisez la méthode create() de CRUDMixin.")

@event.listens_for(Base, 'before_update', propagate=True)
def receive_before_update(mapper, connection, target):
    session = object_session(target)
    if session and not session.is_modified(target, include_collections=False):
        return
    if not getattr(target, '_via_crud_mixin_update', False):
        obj_id = getattr(target, 'id', 'Unknown')
        from sqlalchemy.orm.attributes import get_history
        from sqlalchemy import inspect
        insp = inspect(target)
        modified = [c.key for c in insp.mapper.column_attrs if get_history(target, c.key).has_changes()]
        logger.warning("Mise à jour directe interdite pour %s (ID: %s), attributs modifiés : %s", target.__class__.__name__, obj_id, modified)
        raise RuntimeError(f"Mise à jour directe interdite pour {target.__class__.__name__} (ID: {obj_id}). Utilisez la méthode update() de CRUDMixin.")

@event.listens_for(Base, 'before_delete', propagate=True)
def receive_before_delete(mapper, connection, target):
    if not getattr(target, '_via_crud_mixin_delete', False):
        raise RuntimeError(f"Suppression directe interdite pour {target.__class__.__name__}. Utilisez la méthode delete() de CRUDMixin.")

