"""Social sign-in: provider definitions, the code exchange, and account linking."""

from app.services.oauth.accounts import ProviderEmailUnverified, link_or_create
from app.services.oauth.flow import (
    IdTokenInvalid,
    OAuthError,
    ProviderIdentity,
    TokenExchangeFailed,
    exchange_code,
    new_pkce_verifier,
    pkce_challenge,
    verify_id_token,
)
from app.services.oauth.providers import (
    APPLE,
    GOOGLE,
    Provider,
    enabled_provider_ids,
    get_provider,
)
from app.services.oauth.redirects import SPA_CALLBACK_PATH, safe_next_path

__all__ = [
    "APPLE",
    "GOOGLE",
    "IdTokenInvalid",
    "OAuthError",
    "Provider",
    "ProviderEmailUnverified",
    "ProviderIdentity",
    "SPA_CALLBACK_PATH",
    "TokenExchangeFailed",
    "enabled_provider_ids",
    "exchange_code",
    "get_provider",
    "link_or_create",
    "new_pkce_verifier",
    "pkce_challenge",
    "safe_next_path",
    "verify_id_token",
]
