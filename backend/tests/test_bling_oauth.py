from cryptography.fernet import Fernet
import pytest

from bling_oauth import AUTHORIZE_URL, BlingOAuthConfiguration, BlingOAuthError


def configured():
    return {
        "BLING_CLIENT_ID": "client-id",
        "BLING_CLIENT_SECRET": "client-secret",
        "BLING_REDIRECT_URI": "https://example.test/api/integrations/bling/callback",
        "BLING_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    }


def test_oauth_url_uses_state_without_exposing_secret():
    config = BlingOAuthConfiguration.from_environment(configured())
    url = config.authorization_url("state-value")
    assert url.startswith(AUTHORIZE_URL)
    assert "client_id=client-id" in url
    assert "state=state-value" in url
    assert "client-secret" not in url


def test_tokens_are_encrypted_and_round_trip():
    config = BlingOAuthConfiguration.from_environment(configured())
    encrypted = config.encrypt("access-token")
    assert encrypted != "access-token"
    assert config.decrypt(encrypted) == "access-token"


def test_configuration_fails_closed_when_key_is_missing():
    env = configured()
    env.pop("BLING_TOKEN_ENCRYPTION_KEY")
    with pytest.raises(BlingOAuthError, match="BLING_TOKEN_ENCRYPTION_KEY"):
        BlingOAuthConfiguration.from_environment(env)
