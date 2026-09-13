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


class BlingApiError(BlingOAuthError):
    def __init__(self, status_code: int, message: str = "Bling request failed"):
        self.status_code = status_code
        super().__init__(message)


def _provider_error_message(response: requests.Response) -> str:
    """Return a short, credential-free validation message from Bling."""
    try:
        payload = response.json()
    except ValueError:
        return ""
    if not isinstance(payload, dict):
        return ""
    candidates = [payload.get("message"), payload.get("detail"), payload.get("description")]
    error = payload.get("error")
    if isinstance(error, dict):
        candidates.extend([error.get("message"), error.get("detail"), error.get("description")])
    elif isinstance(error, str):
        candidates.append(error)
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()[:500]
    return ""


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
        return self._token_request({"grant_type": "authorization_code", "code": code})

    def refresh_access_token(self, refresh_token: str) -> dict:
        return self._token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})

    def _token_request(self, body: dict[str, str]) -> dict:
        credentials = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        try:
            response = requests.post(
                TOKEN_URL,
                headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded", "Accept": "1.0", "enable-jwt": "1"},
                data=body,
                timeout=15,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise BlingOAuthError("Bling authorization service is unavailable") from exc
        if not 200 <= response.status_code < 300:
            raise BlingOAuthError("Bling rejected the authorization code")
        try:
            payload = response.json()
        except ValueError as exc:
            raise BlingOAuthError("Bling returned an invalid token response") from exc
        if not isinstance(payload, dict) or not payload.get("access_token") or not payload.get("refresh_token"):
            raise BlingOAuthError("Bling returned an incomplete token response")
        return payload

    def get_json(self, path: str, access_token: str, params: dict[str, str | int] | None = None) -> dict:
        return self._json_request("GET", path, access_token, params=params)

    def post_json(self, path: str, access_token: str, body: dict) -> dict:
        return self._json_request("POST", path, access_token, body=body)

    def _json_request(self, method: str, path: str, access_token: str, *, params: dict[str, str | int] | None = None, body: dict | None = None) -> dict:
        try:
            response = requests.request(
                method,
                "https://api.bling.com.br/Api/v3" + path,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json", "Content-Type": "application/json", "enable-jwt": "1"},
                params=params,
                json=body,
                timeout=15,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise BlingOAuthError("Bling service is unavailable") from exc
        if not 200 <= response.status_code < 300:
            message = _provider_error_message(response) or f"Bling respondeu HTTP {response.status_code}"
            raise BlingApiError(response.status_code, message)
        try:
            payload = response.json()
        except ValueError as exc:
            raise BlingOAuthError("Bling returned an invalid response") from exc
        if not isinstance(payload, dict):
            raise BlingOAuthError("Bling returned an invalid response")
        return payload
