"""Explicit environment selection for backend startup.

Test mode is opt-in through APP_ENV=test and never reads backend/.env.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import MutableMapping

from dotenv import dotenv_values


SAFE_TEST_DB_NAME = "proposta_ja_test"
TEST_MODE = "test"


def configure_backend_environment(
    root_dir: Path,
    environ: MutableMapping[str, str] | None = None,
) -> Path:
    target = environ if environ is not None else os.environ
    mode = target.get("APP_ENV", "").strip().lower()
    env_path = root_dir / (".env.test" if mode == TEST_MODE else ".env")

    # Em produção o Render fornece as variáveis pelo ambiente e não inclui
    # o arquivo backend/.env no deploy. O arquivo continua obrigatório apenas
    # para testes, que precisam da proteção explícita de banco isolado.
    if not env_path.is_file():
        if mode == TEST_MODE:
            raise RuntimeError(f"Configuration file not found: {env_path.name}")
        return env_path

    values = {key: value for key, value in dotenv_values(env_path).items() if value is not None}
    if mode == TEST_MODE:
        configured_name = values.get("TEST_DB_NAME")
        requested_name = target.get("TEST_DB_NAME")
        if configured_name != SAFE_TEST_DB_NAME:
            raise RuntimeError("SAFETY STOP: backend/.env.test must define TEST_DB_NAME=proposta_ja_test")
        if requested_name is not None and requested_name != SAFE_TEST_DB_NAME:
            raise RuntimeError("SAFETY STOP: test mode only permits TEST_DB_NAME=proposta_ja_test")
        if not values.get("TEST_MONGO_URL"):
            raise RuntimeError("SAFETY STOP: TEST_MONGO_URL must be defined in backend/.env.test")

        # Test mode maps only the explicitly test-scoped database settings.
        target.update(values)
        target["MONGO_URL"] = values["TEST_MONGO_URL"]
        target["DB_NAME"] = SAFE_TEST_DB_NAME
        target.setdefault("JWT_SECRET", "local-test-only-secret")
    else:
        # Preserve the existing application behavior outside explicit test mode.
        target.update(values)

    return env_path
