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

