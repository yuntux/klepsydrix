from sqlalchemy.orm import declarative_base, Session

class CRUDMixin:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Recherche et assigne automatiquement les champs 'related' du modèle
        cls._fields = [
            name for name, attr in cls.__dict__.items()
            if isinstance(attr, property) and getattr(attr, "_is_related", False)
        ]

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
    def create(cls, db: Session, vals: dict):
        """
        Méthode de création standard surchargeable avec gestion des related_fields.
        """
        try:
            # 1. Séparer les champs related des champs locaux
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

            # 2. Créer l'enregistrement local principal
            instance = cls(**local_vals)
            db.add(instance)
            db.flush() # Génère l'ID en base sans commiter tout de suite

            # 3. Assurer l'existence et mettre à jour les enregistrements liés
            for relation_name, fields in related_vals.items():
                related_obj = instance.ensure_related_record(relation_name)
                if related_obj:
                    for k, v in fields.items():
                        prop = getattr(cls, k)
                        setattr(related_obj, prop.target_field, v)

            db.commit()
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
        query = db.query(cls)
        if domain:
            for key, value in domain.items():
                if hasattr(cls, key):
                    query = query.filter(getattr(cls, key) == value)
        if offset is not None:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
        return query.all()


    def update(self, db: Session, vals: dict):
        """
        Méthode de mise à jour standard surchargeable avec gestion des related_fields.
        """
        try:
            # 1. Séparer les champs related des champs locaux
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

            # 2. Mettre à jour l'enregistrement principal
            for key, value in local_vals.items():
                if hasattr(self, key):
                    setattr(self, key, value)

            # 3. Assurer l'existence et mettre à jour les enregistrements liés
            for relation_name, fields in related_vals.items():
                related_obj = self.ensure_related_record(relation_name)
                if related_obj:
                    for k, v in fields.items():
                        prop = getattr(self.__class__, k)
                        setattr(related_obj, prop.target_field, v)

            db.commit()
            db.refresh(self)
            return self
        except Exception as e:
            db.rollback()
            raise e

    def delete(self, db: Session):
        """
        Méthode de suppression standard surchargeable.
        """
        try:
            db.delete(self)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            raise e

# Base déclarative commune pour tous les modèles SQLAlchemy
Base = declarative_base(cls=CRUDMixin)

class related_field(property):
    """
    Subclass de property qui simule un champ 'related' à la Odoo dans SQLAlchemy.
    Permet la découverte dynamique des propriétés virtuelles.
    """
    def __init__(self, relation_name: str, target_field: str, default=None):
        self.relation_name = relation_name
        self.target_field = target_field
        self.default = default
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


