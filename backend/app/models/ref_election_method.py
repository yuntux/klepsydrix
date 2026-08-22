from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String, Boolean, false as sa_false
from backend.app.models.base import Base
from backend.app.models.sts_compliance import StsComplianceMixin


class RefElectionMethod(StsComplianceMixin, Base):
    """
    Modalité d'élection d'un enseignement (facultatif, obligatoire, tronc commun…), nomenclature
    nationale STSWEB. Donnée de référence : seedée par init_db.py, au même titre que Modality.
    """
    __tablename__ = "ref_election_methods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False, info={"label": "Code de la méthode", "placeholder": "ex: STS"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Nom de la méthode", "placeholder": "ex: STSWEB"})
    export_code: Mapped[str] = mapped_column(String(20), nullable=False, info={"label": "Code d'export"})
    # Conformité à la nomenclature officielle STS-web (voir StsComplianceMixin) : vrai pour les 7
    # modes d'élection seedés par init_db.py, jamais modifiable via l'API. Un cours pointant vers
    # un mode d'élection non conforme ne peut pas être remonté (voir Course.is_exported_to_sts).
    is_sts_compliant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_false(), info={"label": "Conforme STS-web", "readOnly": True})
