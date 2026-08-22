from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, Float, Boolean, false as sa_false
from backend.app.models.base import Base
from backend.app.models.sts_compliance import StsComplianceMixin


class RefWeightingCoefficient(StsComplianceMixin, Base):
    """
    Valeur de pondération autorisée, référencée par `Course`, `CourseTeacherWeighting`,
    `MefService` et `Service` (tous `weighting_coefficient_id`) — plutôt qu'un flottant libre sur
    chacun, pour pouvoir distinguer une valeur conforme à la nomenclature STS-web
    (`is_sts_compliant`, voir StsComplianceMixin) d'une valeur ajoutée localement.

    **Pas de conversion flottant → pointeur nulle part** : `MefService.weighting_coefficient_id`
    est la seule saisie ; `Service` le recopie tel quel (voir `Service._MEF_SERVICE_MIRROR_FIELDS`),
    et `Course` le recopie à son tour depuis le `Service` d'origine (voir
    `wizard_course_generation.py`) — la FK voyage à l'identique sur toute la chaîne, jamais une
    valeur qu'il faudrait retrouver ou créer après coup.

    Nomenclature seedée par `init_db.py` : `1.00`, `0.25`, `0.5`, `0.75`, `1.25`, `1.5` — toutes
    `is_sts_compliant=True`. `1.00` est seedée EN PREMIER pour que le défaut (`id=1`) y corresponde,
    même convention que `Modality`/CG.
    """
    __tablename__ = "ref_weighting_coefficients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    weighting_coefficient: Mapped[float] = mapped_column(Float, unique=True, nullable=False, info={"label": "Pondération", "min": 0.0, "max": 5.0, "step": "0.05"})
    # Conformité à la nomenclature officielle STS-web (voir StsComplianceMixin) : vrai pour les
    # valeurs seedées par init_db.py, jamais modifiable via l'API.
    is_sts_compliant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_false(), info={"label": "Conforme STS-web", "readOnly": True})

    @property
    def display_name(self) -> str:
        return f"{self.weighting_coefficient:g}"
