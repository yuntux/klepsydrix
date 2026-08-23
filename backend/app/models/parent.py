from typing import Optional
from sqlalchemy import Boolean, ForeignKey, Integer, String, Enum, false as sa_false
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.models.gender import Gender, gender_field_info
from backend.app.models.base import Base
from backend.app.models.user import HasUserAccount


class Parent(HasUserAccount, Base):
    __tablename__ = "parents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Nom"})
    first_name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Prénom"})
    gender: Mapped[Optional[str]] = mapped_column(Enum(Gender, name="gender_enum"), nullable=True, info=gender_field_info())
    email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, info={"label": "Email"})
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, unique=True, info={"label": "Compte utilisateur"}
    )

    # Identifiant SIECLE (ResponsablesAvecAdresses/PERSONNE/@PERSONNE_ID) : posé par l'import,
    # jamais saisi à la main — c'est la clé qui permet de retrouver le MÊME parent d'une fratrie
    # plutôt que d'en recréer un exemplaire par enfant importé.
    siecle_id: Mapped[Optional[str]] = mapped_column(String(20), unique=True, index=True, nullable=True, info={"label": "Identifiant SIECLE", "readOnly": True})

    # État civil, même patron que Teacher/Student (NOM_USAGE -> last_name, NOM_DE_FAMILLE ->
    # birth_last_name), plus la civilité (LC_CIVILITE -> title_id) et la profession (CODE_PROFESSION
    # -> job_id), toutes deux alimentées dynamiquement à l'import quand elles sont fournies.
    birth_last_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, info={"label": "Nom de naissance"})
    title_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_titles.id", ondelete="SET NULL"), nullable=True, info={"label": "Civilité"})
    job_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_jobs.id", ondelete="SET NULL"), nullable=True, info={"label": "Profession"})

    # Trois téléphones SIECLE (PERSONNE/TEL_PERSONNEL, TEL_PORTABLE, TEL_PROFESSIONNEL), là où le
    # modèle n'en portait qu'un : l'ancien champ `phone` est repris comme `mobile_phone` (le plus
    # généralement renseigné et le plus utile en contact direct), les deux autres sont neufs.
    mobile_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, info={"label": "Téléphone portable"})
    personal_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, info={"label": "Téléphone personnel"})
    professional_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, info={"label": "Téléphone professionnel"})

    accepts_sms: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_false(), info={"label": "Accepte les SMS"})
    communication_by_address: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_false(), info={"label": "Communication par courrier"})

    # Adresse (ResponsablesAvecAdresses/ADRESSE), inline sur Parent plutôt qu'une table dédiée —
    # même choix que School/Teacher : SIECLE dédoublonne l'adresse entre responsables cohabitants
    # via ADRESSE_ID, ce que ce modèle ne reproduit pas (chaque Parent porte sa propre adresse,
    # potentiellement dupliquée pour un couple). address_department_code (CODE_DEPARTEMENT) est
    # propre à ce modèle, sans équivalent sur Teacher.
    address_line1: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, info={"label": "Adresse (ligne 1)"})
    address_line2: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, info={"label": "Adresse (ligne 2)"})
    address_line3: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, info={"label": "Adresse (ligne 3)"})
    address_line4: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, info={"label": "Adresse (ligne 4)"})
    address_zipcode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, info={"label": "Code postal"})
    address_department_code: Mapped[Optional[str]] = mapped_column(String(3), nullable=True, info={"label": "Code département"})
    address_city_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_cities.id", ondelete="SET NULL"), nullable=True, info={"label": "Ville"})
    address_country_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_countries.id", ondelete="SET NULL"), nullable=True, info={"label": "Pays"})

    user: Mapped[Optional["User"]] = relationship("User", back_populates="parent", foreign_keys=[user_id])
    title: Mapped[Optional["RefTitle"]] = relationship("RefTitle", foreign_keys=[title_id])
    job: Mapped[Optional["RefJob"]] = relationship("RefJob", foreign_keys=[job_id])
    address_city: Mapped[Optional["RefCity"]] = relationship("RefCity", foreign_keys=[address_city_id])
    address_country: Mapped[Optional["RefCountry"]] = relationship("RefCountry", foreign_keys=[address_country_id])

    # Vue seule (voir StudentParentLink) : un responsable ne se rattache pas lui-même à un élève
    # depuis sa propre fiche, c'est Student.parent_links qui porte l'édition.
    student_links: Mapped[list["StudentParentLink"]] = relationship(
        "StudentParentLink", back_populates="parent", passive_deletes="all",
        info={
            "label": "Élèves rattachés",
            "readOnly": True,
            "widget": "list_preview",
            "widgetParams": {
                "columns": [
                    {"key": "student_id", "label": "Élève"},
                    {"key": "relative_link_id", "label": "Lien de parenté", "resource": "ref_relative_links"},
                    {"key": "legal_guardian_id", "label": "Responsabilité légale", "resource": "ref_legal_guardians"},
                ],
                "listConfig": {"editableInline": False, "disableAdd": True, "disableDelete": True, "allowMultiSelect": False},
            },
        },
    )

    @property
    def display_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
