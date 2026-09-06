"""Server-side OAuth utilities for the Bling API.

This module never reads a token at import time and never exposes a client
secret. Callers must store the encrypted token payload themselves.
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet, InvalidToken


AUTHORIZE_URL = "https://www.bling.com.br/Api/v3/oauth/authorize"
TOKEN_URL = "https://api.bling.com.br/Api/v3/oauth/token"


class BlingOAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class BlingOAuthConfiguration:
    client_id: str
    client_secret: str
    redirect_uri: str
    token_encryption_key: str

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "BlingOAuthConfiguration":
        values = environ or os.environ
        required = ("BLING_CLIENT_ID", "BLING_CLIENT_SECRET", "BLING_REDIRECT_URI", "BLING_TOKEN_ENCRYPTION_KEY")
        missing = [name for name in required if not str(values.get(name, "")).strip()]
        if missing:
            raise BlingOAuthError("Bling integration is not configured: " + ", ".join(missing))
        config = cls(*(str(values[name]).strip() for name in required))
        try:
            Fernet(config.token_encryption_key.encode())
        except (ValueError, TypeError) as exc:
            raise BlingOAuthError("BLING_TOKEN_ENCRYPTION_KEY is invalid") from exc
        return config

    def authorization_url(self, state: str) -> str:
        return AUTHORIZE_URL + "?" + urlencode({"response_type": "code", "client_id": self.client_id, "state": state})

    def encrypt(self, value: str) -> str:
        return Fernet(self.token_encryption_key.encode()).encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return Fernet(self.token_encryption_key.encode()).decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise BlingOAuthError("stored Bling token cannot be decrypted") from exc

    def exchange_code(self, code: str) -> dict:
        credentials = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        try:
            response = requests.post(
                TOKEN_URL,
                headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded", "Accept": "1.0", "enable-jwt": "1"},
                data={"grant_type": "authorization_code", "code": code},
                timeout=15,
            )
        except requests.RequestException as exc:
            raise BlingOAuthError("Bling authorization service is unavailable") from exc
        if not response.ok:
            raise BlingOAuthError("Bling rejected the authorization code")
        payload = response.json()
        if not payload.get("access_token") or not payload.get("refresh_token"):
            raise BlingOAuthError("Bling returned an incomplete token response")
        return payload
