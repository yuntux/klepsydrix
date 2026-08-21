from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Date, Float, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.models.base import Base, requires_access

class School(Base):
    __tablename__ = "schools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    uai: Mapped[str] = mapped_column(String(8), unique=True, index=True, nullable=False, info={"label": "Code UAI (RNE)", "placeholder": "ex: 0750001A"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Nom de l'établissement", "placeholder": "ex: Collège Jean Jaurès"})
    student_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Date de rentrée des élèves"})
    student_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Date de sortie des élèves"})

    # --- Données communes de l'établissement (PARAMETRES/UAJ du flux STS) ---
    # Toutes alimentées par l'import STS quand la case « Données communes de l'établissement »
    # est cochée (voir wizard_sts_import.py). `name` reçoit DENOM_PRINC, `long_name` DENOM_COMPL.
    long_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, info={"label": "Dénomination complète", "placeholder": "ex: Collège Jean Jaurès de Paris"})
    academie_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_academies.id", ondelete="RESTRICT"), nullable=True, info={"label": "Académie"})
    sigle: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, info={"label": "Sigle", "placeholder": "ex: CLG"})
    code_nature: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, info={"label": "Code nature", "placeholder": "ex: 340"})
    code_categorie: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, info={"label": "Code catégorie"})
    statut: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, info={"label": "Statut"})
    etablissement_sensible: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, info={"label": "Établissement sensible"})

    # --- Coordonnées ---
    address: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, info={"label": "Adresse"})
    city_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_cities.id", ondelete="SET NULL"), nullable=True, info={"label": "Commune"})
    zip_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, info={"label": "Code postal"})
    po_box: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, info={"label": "Boîte postale"})
    cedex: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, info={"label": "Cedex"})
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, info={"label": "Téléphone"})

    # Limites de poids pédagogique (matières lourdes)
    max_pedagogic_weight_per_day: Mapped[Optional[float]] = mapped_column(Float, nullable=True, info={"label": "Poids pédagogique max par jour", "min": "0.0", "step": "0.5"})
    max_pedagogic_weight_per_morning: Mapped[Optional[float]] = mapped_column(Float, nullable=True, info={"label": "Poids pédagogique max par matinée", "min": "0.0", "step": "0.5"})
    max_pedagogic_weight_per_afternoon: Mapped[Optional[float]] = mapped_column(Float, nullable=True, info={"label": "Poids pédagogique max par après-midi", "min": "0.0", "step": "0.5"})

    # Relations de navigation
    academie: Mapped[Optional["RefAcademie"]] = relationship("RefAcademie", back_populates="schools")
    city: Mapped[Optional["RefCity"]] = relationship("RefCity")
    # PAS de collections inverses vers teachers, divisions, classrooms, courses ni periods : elles
    # existaient, elles ont été retirées. Le moteur générique expose toute relation `uselist` comme
    # un champ `<relation>_ids` du modèle — la fiche Établissement se retrouvait donc à déclarer
    # cinq collections entières, dont les cours de tout l'établissement, et le frontend chargeait
    # leurs options FK à chaque affichage du panneau (voir App.vue, watch sur activeAdminModel).
    # Le sens qui porte le métier est l'autre : c'est `Teacher.school_id` qui rattache, et les
    # écrans listent les enseignants d'un établissement en filtrant sur ce champ.
    # La suppression en cascade ne dépend pas de ces relations non plus : elle parcourt les clés
    # étrangères et leur `ondelete=` (voir CRUDMixin._cascade_delete_dependents, §15.H).

    @classmethod
    def test_class_method(cls, db, multiplier: int):
        # Volontairement NON décorée @requires_access — voir test_access_control.py::TestRpcGuard,
        # exercice du refus par défaut pour toute méthode RPC non décorée.
        return db.query(cls).count() * multiplier

    @requires_access("write")
    def test_instance_method(self, db, prefix: str):
        return f"{prefix} {self.name}"
