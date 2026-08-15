"""
Client OpenID Connect (Authlib — voir architecture.md, choix de librairie) pour les fournisseurs
d'identité fédérés (`protocol: oidc` dans `identity_providers:`, instance.yaml). Un seul registre
`oauth`, construit une fois au chargement du module à partir de la config — Authlib ne récupère le
document de découverte (`server_metadata_url`) qu'au moment réel de l'usage (authorize_redirect/
authorize_access_token), donc enregistrer un provider "fictif" (ex: EduConnect, métadonnées non
joignables) au démarrage ne déclenche aucun appel réseau tant qu'il n'est pas réellement utilisé.
"""
from authlib.integrations.starlette_client import OAuth
from backend.app.core.config import settings

oauth = OAuth()

for _provider in settings.identity_providers:
    if _provider.protocol == "oidc":
        oauth.register(
            name=_provider.key,
            server_metadata_url=_provider.params.get("server_metadata_url"),
            client_id=_provider.params.get("client_id"),
            client_secret=_provider.params.get("client_secret"),
            client_kwargs={"scope": " ".join(_provider.params.get("scopes", ["openid", "profile", "email"]))},
        )


def claim_mapping_for(provider_key: str) -> dict:
    for provider in settings.identity_providers:
        if provider.key == provider_key:
            return provider.params.get("claim_mapping", {
                "sub": "external_subject", "given_name": "first_name",
                "family_name": "last_name", "email": "email",
            })
    return {}
