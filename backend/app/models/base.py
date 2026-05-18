from sqlalchemy.orm import declarative_base, Session

class CRUDMixin:
    @classmethod
    def create(cls, db: Session, vals: dict):
        """
        Méthode de création standard surchargeable.
        """
        try:
            instance = cls(**vals)
            db.add(instance)
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
        Méthode de mise à jour standard surchargeable.
        """
        try:
            for key, value in vals.items():
                if hasattr(self, key):
                    setattr(self, key, value)
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


