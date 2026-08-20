import os
import re
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource

# backend/app/core/config.py -> racine du dépôt (4 parents : core, app, backend, racine)
REPO_ROOT = Path(__file__).resolve().parents[3]


class DatabaseBackend(str, Enum):
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


class DatabaseConfig(BaseModel):
    """
    Section `database:` de instance.yaml — voir instance.example.yaml. `directory` (SQLite) et
    `host` (PostgreSQL) ne sont obligatoires QUE pour le backend sélectionné, d'où la validation
    croisée ci-dessous plutôt que deux champs requis indépendamment.
    """
    backend: DatabaseBackend = DatabaseBackend.SQLITE
    directory: Optional[str] = None
    host: Optional[str] = None
    port: int = 5432
    user: Optional[str] = None
    password: Optional[str] = None
    database_prefix: str = "klepsydrix_"

    @model_validator(mode="after")
    def _check_backend_requirements(self) -> "DatabaseConfig":
        if self.backend == DatabaseBackend.SQLITE and not self.directory:
            raise ValueError("database.directory est obligatoire quand database.backend=sqlite.")
        if self.backend == DatabaseBackend.POSTGRESQL and not self.host:
            raise ValueError("database.host est obligatoire quand database.backend=postgresql.")
        return self


class ServerConfig(BaseModel):
    """Section `server:` — topologie réseau/déploiement (voir architecture.md §20.C)."""
    # Origines autorisées à appeler l'API (CORS) — voir architecture.md.
    allowed_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    # Adresses/CIDR des reverse proxies de confiance (voir core/master_auth.py::_client_ip) — vide
    # par défaut (aucun changement de comportement tant que non configuré explicitement). Une fois
    # un reverse proxy externe en place devant l'appli (§20.C), request.client.host devient l'IP DU
    # PROXY, jamais celle du client réel : sans cette liste, ip_allowlist (master_db_local_auth)
    # deviendrait inefficace (soit toujours refusé, soit toujours accepté selon ce qu'on y met).
    trusted_proxies: list[str] = []
    # URL absolue publique de CETTE instance (frontend) — nécessaire pour construire un lien
    # cliquable dans un email (une URL relative n'a aucun sens hors du navigateur), voir
    # core/mailer.py. Dev : le frontend Vite local ; prod : le nom de domaine réel derrière le
    # reverse proxy (§20.C), sans slash final.
    public_base_url: str = "http://localhost:3000"


class SmtpConfig(BaseModel):
    """
    Section `smtp:` — connexion sortante pour l'envoi d'emails (réinitialisation de mot de passe,
    voir architecture.md §17.G, core/mailer.py). Absente ou incomplète = envoi IMPOSSIBLE, erreur
    explicite levée au moment de l'envoi — jamais de repli silencieux (ex: journaliser le lien à la
    place enverrait un signal dangereux si oublié actif en production).
    """
    host: Optional[str] = None
    port: int = 587
    user: Optional[str] = None
    password: Optional[str] = None
    from_address: Optional[str] = None
    # STARTTLS (port 587, cas courant) si vrai ; SSL implicite (port 465) si faux. Un seul des deux
    # gérés pour l'instant — pas de besoin identifié d'un mode "aucun chiffrement".
    use_tls: bool = True


class AuthConfig(BaseModel):
    """Section `auth:` — règles métier d'authentification transverses, pas propres à un fournisseur
    précis (voir identity_providers pour ça)."""
    password_reset_ttl_minutes: int = 60
    # Robustesse minimale d'un mot de passe local (UserIdentityProvider._validate_password_strength,
    # models/user.py) : longueur ET diversité de caractères, jamais la longueur seule — voir ce
    # validateur pour le détail de la règle de diversité.
    password_min_length: int = 8
    # Durée maximale d'INACTIVITÉ avant qu'une session instance (core/instance_session.py) expire —
    # pas une durée fixe depuis la connexion : chaque requête authentifiée valide fait glisser la
    # fenêtre (voir instance_session.py::require_instance_session). Défaut conservé identique au
    # comportement historique (30 jours), simplement réinterprété comme glissant plutôt que fixe.
    session_idle_timeout_minutes: int = 60 * 24 * 30


class SuperAdminPair(BaseModel):
    """
    Un élément de `super_admins:` (instance.yaml) — identité nommée, individuellement attribuable
    (contrairement au mot de passe maître, voir `MasterAuthConfig` ci-dessous).

    `provider_key: local` est REFUSÉ ici, volontairement — pas une simple précaution : un admin
    d'une base quelconque (droit `create`/`write` complet sur `user_identity_providers`, comme tout
    modèle, pour le groupe "Admin") peut créer LUI-MÊME un compte local avec n'importe quel
    `external_subject` de son choix, y compris une valeur qui correspond à une paire `super_admins`
    configurée ailleurs — `login_local` ne fixe la session qu'avec l'identifiant saisi, sans jamais
    retenir DANS QUELLE base il a été vérifié (voir `database.py`/`auth_endpoints.py`). Une paire
    `super_admins` en `local` serait donc usurpable par n'importe quel admin de base, sur toute
    l'instance. Un fournisseur OIDC fédéré n'a pas ce problème (le `sub` est émis par le fournisseur
    externe, hors de portée d'un admin de base Klepsydrix) — seul `local` est concerné.
    """
    provider_key: str
    subject: str

    @field_validator("provider_key")
    @classmethod
    def _forbid_local_provider(cls, value: str) -> str:
        if value == "local":
            raise ValueError(
                "super_admins: provider_key 'local' est refusé (usurpable par n'importe quel admin "
                "de base, voir SuperAdminPair) — utiliser un fournisseur OIDC fédéré, ou le mot de "
                "passe maître (master_db_local_auth) si aucun OIDC n'est encore actif."
            )
        return value


class MasterAuthConfig(BaseModel):
    """
    Section `master_db_local_auth:` — authentification par mot de passe maître pour la console
    d'administration (voir architecture.md §19.A) : nécessaire quand aucun fournisseur OIDC fédéré
    n'est actif sur l'instance — ce qui inclut le cas où "local" est le seul provider (par nature lié
    à UNE base précise, voir §17.F, et de toute façon refusé dans `super_admins`, voir
    `SuperAdminPair`) : aucun super-admin ne pourrait sinon jamais s'authentifier au niveau instance.
    **Désactivée par défaut** (`enabled: false`). Sur une instance SANS OIDC fédéré, c'est la voie
    normale et permanente vers le statut super-admin, pas juste un filet de secours ponctuel — rien
    à redésactiver. Sur une instance AVEC un OIDC fédéré actif (au moins une paire `super_admins`
    fonctionnelle), redésactiver reste recommandé : un second point d'entrée permanent affaiblirait
    l'authentification fédérée déjà en place.
    """
    enabled: bool = False
    password_hash: Optional[str] = None  # Argon2id — jamais en clair, voir instance.example.yaml
    ip_allowlist: list[str] = []


class IdentityProviderConfig(BaseModel):
    """
    Un élément de la section `identity_providers:` de instance.yaml (niveau instance, pas par
    base — voir architecture.md). `protocol` détermine comment `params` est interprété :
    - "oidc" : `server_metadata_url`, `client_id`, `client_secret`, `scopes`, `claim_mapping`
      (voir Authlib, backend/app/core/oidc.py).
    - "local_password" : aucun paramètre — les identifiants vivent dans `user_identity_providers`
      de chaque base (voir UserIdentityProvider.verify_local_password).
    """
    key: str
    label: str
    logo: Optional[str] = None
    active: bool = True
    protocol: str
    params: dict = {}


_ENV_PLACEHOLDER = re.compile(r"^\$\{env:([A-Za-z_][A-Za-z0-9_]*)\}$")


def _substitute_env_placeholders(value):
    """
    Convention `${env:NOM_VAR}` dans instance.yaml (voir instance.example.yaml) : permet de
    référencer un secret via une variable d'environnement plutôt que de l'écrire en clair dans le
    fichier de configuration. Récursif sur les dicts/listes pour couvrir toute section future
    (SMTP, clients OIDC...) sans code supplémentaire à écrire pour chacune.
    """
    if isinstance(value, str):
        match = _ENV_PLACEHOLDER.match(value)
        return os.environ.get(match.group(1)) if match else value
    if isinstance(value, dict):
        return {k: _substitute_env_placeholders(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env_placeholders(v) for v in value]
    return value


class _YamlSourceWithEnvSubstitution(YamlConfigSettingsSource):
    def __call__(self):
        return _substitute_env_placeholders(super().__call__())


class Settings(BaseSettings):
    PROJECT_NAME: str = "Klepsydrix"
    API_V1_STR: str = "/api"

    database: DatabaseConfig = DatabaseConfig(backend=DatabaseBackend.SQLITE, directory=str(REPO_ROOT))
    server: ServerConfig = ServerConfig()
    identity_providers: list[IdentityProviderConfig] = [
        IdentityProviderConfig(key="local", label="Compte local", protocol="local_password", active=True),
    ]
    super_admins: list[SuperAdminPair] = []
    master_db_local_auth: MasterAuthConfig = MasterAuthConfig()
    smtp: SmtpConfig = SmtpConfig()
    auth: AuthConfig = AuthConfig()
    # Signe les cookies de session instance (itsdangerous, voir core/instance_session.py) — valeur
    # de démonstration ci-dessous, à surcharger IMPÉRATIVEMENT en production (${env:...}, voir
    # instance.example.yaml) : quiconque la connaît peut forger une session pour n'importe qui.
    secret_key: str = "klepsydrix-dev-secret-change-me"

    # Limite de temps pour le solveur Timefold en secondes
    SOLVER_TIME_LIMIT_SECONDS: int = 300
    SOLVER_UNIMPROVED_TIME_LIMIT_SECONDS: int = 10

    # Voir plan salles §4 — Placement automatique (endpoint /course-placement) : s'arrête dès la
    # 1ère solution faisable (best_score_feasible), avec ce plafond de durée comme filet de
    # sécurité si aucune solution faisable n'est jamais atteinte.
    SOLVER_COURSE_PLACEMENT_CEILING_SECONDS: int = 300

    # Wizard "Optimiser l'emploi du temps" (endpoint /optimize) : bornes/défauts des paramètres
    # saisis par l'utilisateur (OptimizeTimetableRequest, endpoints.py).
    SOLVER_OPTIMIZE_MAX_COMPUTE_CEILING_SECONDS: int = 43200   # 12h, borne dure
    SOLVER_OPTIMIZE_DEFAULT_MAX_COMPUTE_SECONDS: int = 3600    # 1h
    SOLVER_OPTIMIZE_DEFAULT_MAX_NO_PROGRESS_SECONDS: int = 900  # 15 min

    # Nombre de résolutions Timefold autorisées à tourner EN MÊME TEMPS, toutes bases confondues
    # (voir architecture.md, "Concurrence des résolutions") — au-delà, une nouvelle demande passe
    # en file d'attente (SolverState, statut QUEUED) plutôt que de démarrer immédiatement. Chaque
    # résolution étant mono-thread côté Timefold et CPU-intensive, aligner cette valeur sur le
    # nombre de cœurs disponibles évite de diluer le CPU entre trop de résolutions à la fois — ce
    # qui dégraderait leur qualité (le solveur s'arrête sur un budget de TEMPS, pas d'itérations :
    # moins de CPU réel par résolution = moins d'itérations dans le même budget, pas une résolution
    # plus longue). Défaut : nombre de cœurs de la machine (`os.cpu_count()`), avec un repli à 4 si
    # indéterminable — à ajuster à la baisse si l'API doit rester réactive avec une marge de cœurs
    # dédiés (rien ne garantit ici une priorité OS à l'API face aux résolutions, une seule limite
    # de comptage — voir architecture.md pour la nuance).
    SOLVER_MAX_CONCURRENT_SOLVES: int = Field(default_factory=lambda: os.cpu_count() or 4)

    # Borne explicite du tas JVM (-Xmx, en Mo — voir solver/constraints.py::timefold.solver.init).
    # Sans cette borne, la JVM (partagée par
    # toutes les résolutions du process, voir architecture.md §9.F) utilise par défaut jusqu'à 1/4
    # de la RAM de la machine (comportement par défaut de la JVM, indépendant du nombre de
    # résolutions réellement en cours) — un plafond explicite protège contre l'épuisement de la RAM
    # de l'hôte si plusieurs résolutions volumineuses tournent en même temps (le pire scénario :
    # swap, largement plus dommageable pour la réactivité de l'API qu'une simple contention CPU,
    # déjà observé sur ce poste de dev avec Playwright).
    SOLVER_JVM_MAX_HEAP_MB: int = 2048

    model_config = SettingsConfigDict(
        yaml_file=os.environ.get("KLEPSYDRIX_CONFIG", str(REPO_ROOT / "instance.yaml")),
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
        # Priorité : arguments explicites > variables d'environnement > instance.yaml > .env
        # (le .env ne porte plus que SOLVER_*, la config BDD vit désormais dans instance.yaml).
        return (
            init_settings,
            env_settings,
            _YamlSourceWithEnvSubstitution(settings_cls),
            dotenv_settings,
        )


settings = Settings()


def build_database_url(db_name: str) -> str:
    """
    Construit l'URL SQLAlchemy d'une base nommée `db_name`, selon `settings.database.backend`.
    Pont temporaire mono-base pour ce lot : `database.py` l'appelle avec un nom fixe en attendant
    le registre multi-base (résolution par en-tête HTTP, voir specs/) qui appellera cette même
    fonction avec le slug de base résolu par requête.
    """
    cfg = settings.database
    if cfg.backend == DatabaseBackend.SQLITE:
        directory = Path(cfg.directory).expanduser()
        # Un chemin relatif est résolu contre la racine du dépôt, pas le répertoire courant du
        # process (indéterminé selon comment/où le serveur ou pytest sont lancés) — reproduit le
        # comportement de l'ancienne config (DATABASE_URL=sqlite:///./timetable.db).
        if not directory.is_absolute():
            directory = REPO_ROOT / directory
        path = directory.resolve() / f"{db_name}.db"
        return f"sqlite:///{path}"

    # PostgreSQL : host commençant par "/" = connexion par socket local (peer/ident), sinon TCP.
    auth = cfg.user or ""
    if cfg.password:
        auth += f":{cfg.password}"
    if cfg.host.startswith("/"):
        return f"postgresql+psycopg://{auth}@/{db_name}?host={cfg.host}"
    return f"postgresql+psycopg://{auth}@{cfg.host}:{cfg.port}/{db_name}"
