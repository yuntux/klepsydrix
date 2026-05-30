from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy import select
from sqlalchemy.ext.hybrid import hybrid_property

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

    def ensure_related_record(self, relation_name: str):
        """
        Garantit que l'objet lié existe et le retourne.
        Surchargeable par les classes enfants (ex: _ensure_constraint_record).
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
    def process_onchange(cls, vals: dict, field_name: str) -> dict:
        """
        Traite un événement onchange sur un brouillon (Draft).
        Instancie le modèle en mémoire, applique les valeurs, 
        exécute les méthodes @onchange concernées et renvoie les différences.
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
                
        # Exécuter les méthodes @onchange qui écoutent ce field_name
        for attr_name in dir(instance):
            method = getattr(instance, attr_name)
            if callable(method) and hasattr(method, "_onchange"):
                trigger_fields = getattr(method, "_onchange")
                if field_name in trigger_fields:
                    import inspect as py_inspect
                    sig = py_inspect.signature(method)
                    if len(sig.parameters) > 0:
                        method(field_name)
                    else:
                        method()
                    
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


    @classmethod
    def create(cls, db: Session, vals: dict):
        """
        Méthode de création standard surchargeable avec gestion des related_fields.
        """
        try:
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
                                    collection_updates[rel.key] = (rel.mapper.class_, ids)
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
            for rel_key, (target_cls, ids) in collection_updates.items():
                items = db.execute(select(target_cls).filter(target_cls.id.in_(ids))).scalars().all()
                setattr(instance, rel_key, items)

            db.flush()

            # 6. Exécuter les contraintes métier
            for attr_name in dir(instance):
                method = getattr(instance, attr_name)
                if callable(method) and hasattr(method, "_constrains"):
                    constrained_fields = getattr(method, "_constrains")
                    if not constrained_fields or any(f in vals for f in constrained_fields):
                        method(db)

            db.refresh(instance)
            return instance
        except Exception as e:
            db.rollback()
            raise e

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        """
        Lit des enregistrements à partir de la base de données.
        Retourne une liste d'instances Python du modèle.
        """
        query = select(cls)
        if domain:
            for key, value in domain.items():
                if hasattr(cls, key):
                    query = query.filter(getattr(cls, key) == value)
        if offset is not None:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
        return db.execute(query).scalars().all()


    def update(self, db: Session, vals: dict):
        """
        Méthode de mise à jour standard surchargeable avec gestion des related_fields.
        """
        try:
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
                                    collection_updates[rel.key] = (rel.mapper.class_, ids)
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
            for rel_key, (target_cls, ids) in collection_updates.items():
                items = db.execute(select(target_cls).filter(target_cls.id.in_(ids))).scalars().all()
                setattr(self, rel_key, items)

            db.flush()  # Flush sans commit : le commit est géré par l'endpoint

            # 6. Exécuter les contraintes métier
            for attr_name in dir(self):
                method = getattr(self, attr_name)
                if callable(method) and hasattr(method, "_constrains"):
                    constrained_fields = getattr(method, "_constrains")
                    if not constrained_fields or any(f in vals for f in constrained_fields):
                        method(db)

            db.refresh(self)
            return self
        except Exception as e:
            db.rollback()
            raise e

    def delete(self, db: Session):
        """
        Marque l'objet pour suppression. Le commit est géré par l'endpoint.
        """
        self._via_crud_mixin_delete = True
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

def exposed(attr):
    """
    Décorateur pour exposer un champ virtuel (@property ou @hybrid_property)
    dans la sérialisation automatique du CRUDMixin / API générique.
    """
    from sqlalchemy.ext.hybrid import hybrid_property
    
    # 1. Si c'est un property natif (qui n'autorise pas les attributs dynamiques en C)
    if isinstance(attr, property) and not type(attr).__name__.endswith("exposed_property"):
        class custom_exposed_property(property):
            _is_exposed = True
        return custom_exposed_property(attr.fget, attr.fset, attr.fdel, attr.__doc__)
        
    # 2. Si c'est une hybrid_property
    if isinstance(attr, hybrid_property):
        try:
            attr._is_exposed = True
            return attr
        except AttributeError:
            class custom_exposed_hybrid(hybrid_property):
                _is_exposed = True
            expr = getattr(attr, "custom_expression", None)
            return custom_exposed_hybrid(attr.fget, attr.fset, attr.fdel, expr=expr)
            
    # 3. Si c'est une fonction (décorateur placé sous @property)
    if callable(attr):
        attr._is_exposed = True
        return attr
        
    # 4. Par défaut, on tente de poser l'attribut
    try:
        attr._is_exposed = True
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

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        raise NotImplementedError("Les modèles transitoires doivent implémenter la méthode read().")

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
        raise RuntimeError(f"Mise à jour directe interdite pour {target.__class__.__name__}. Utilisez la méthode update() de CRUDMixin.")

@event.listens_for(Base, 'before_delete', propagate=True)
def receive_before_delete(mapper, connection, target):
    if not getattr(target, '_via_crud_mixin_delete', False):
        raise RuntimeError(f"Suppression directe interdite pour {target.__class__.__name__}. Utilisez la méthode delete() de CRUDMixin.")

