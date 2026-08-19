"""
pytest conftest.py - Minimal async test configuration
"""

import os
import pytest
from pathlib import Path
from dotenv import load_dotenv

# Carregar o arquivo de configuração de teste do diretório backend.
ENV_TEST_PATH = Path(__file__).parent.parent / ".env.test"
if ENV_TEST_PATH.exists():
    load_dotenv(ENV_TEST_PATH, override=True)

# Nunca permita que os testes de integração usem o banco de produção.
TEST_MONGO_URL = os.environ.get("TEST_MONGO_URL")
TEST_DB_NAME = os.environ.get("TEST_DB_NAME")
if TEST_DB_NAME != "proposta_ja_test":
    raise RuntimeError(
        "SAFETY STOP: TEST_DB_NAME must be proposta_ja_test; "
        f"got {TEST_DB_NAME!r}"
    )


def pytest_configure(config):
    """Register test markers."""
    config.addinivalue_line("markers", "unit: unit tests without infrastructure")
    config.addinivalue_line("markers", "integration: integration tests requiring MongoDB")
    config.addinivalue_line("markers", "legacy_external: legacy tests requiring explicit external infrastructure")


def pytest_addoption(parser):
    parser.addoption(
        "--run-legacy-external",
        action="store_true",
        default=False,
        help="Run unclassified legacy tests that may require an external server or non-test environment.",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-legacy-external"):
        return
    skip = pytest.mark.skip(reason="legacy external test disabled; pass --run-legacy-external explicitly")
    for item in items:
        if item.get_closest_marker("unit") or item.get_closest_marker("integration"):
            continue
        item.add_marker(pytest.mark.legacy_external)
        item.add_marker(skip)
