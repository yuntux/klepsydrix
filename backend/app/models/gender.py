import enum


class Gender(str, enum.Enum):
    """
    Sexe d'une personne, tel que le portent les flux de l'Éducation nationale : `INDIVIDU/SEXE`
    du flux STS et `SEXE` des fichiers SIECLE valent `1` (masculin) ou `2` (féminin).

    Stocké en `M`/`F` et non en `1`/`2` : la valeur reste lisible dans la base et dans l'IHM sans
    table de correspondance, et la traduction depuis le flux tient en une ligne à l'import. La
    colonne est nullable partout — le flux laisse le champ vide pour les personnels créés
    localement dans STS (voir FORMATS_JUSTIFICATION.md §2.4), et rien n'oblige à le renseigner.

    Partagé par les quatre modèles de personnes (Teacher, NonTeachingStaff, Student, Parent) :
    un seul enum, une seule liste d'options dans les formulaires génériques.
    """
    M = "M"
    F = "F"


GENDER_OPTIONS = [
    {"value": Gender.M.value, "label": "Masculin"},
    {"value": Gender.F.value, "label": "Féminin"},
]

# Valeurs du flux STS/SIECLE vers l'enum. Toute autre valeur (chaîne vide comprise) donne None.
GENDER_FROM_STS = {"1": Gender.M.value, "2": Gender.F.value}


def gender_field_info(label: str = "Sexe") -> dict:
    """`info={}` partagé par les quatre colonnes — un seul endroit où changer le libellé."""
    return {"label": label, "type": "select", "options": GENDER_OPTIONS}
