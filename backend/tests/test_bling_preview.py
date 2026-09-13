from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from bling_oauth import BlingApiError, BlingOAuthConfiguration, BlingOAuthError
from bling_preview import fetch_detail, proposal_detail, read_preview

pytestmark = pytest.mark.unit


def setup_read():
    credentials = SimpleNamespace(
        find_one=AsyncMock(return_value={"access_token_encrypted": "encrypted-old", "refresh_token_encrypted": "encrypted-refresh"}),
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1)),
    )
    config = Mock()
    config.decrypt.side_effect = lambda token: token.removeprefix("encrypted-")
    config.encrypt.side_effect = lambda token: "encrypted-" + token
    config.refresh_access_token.return_value = {"access_token": "new", "refresh_token": "rotated", "expires_in": 3600}
    return credentials, config


async def test_detail_reads_proposal_then_contact_and_whitelists_fields():
    read = AsyncMock(side_effect=[{"data": {"id": 12, "numero": 42, "contato": {"id": 9}, "total": 15,
        "observacaoInterna": "private", "itens": [{"produto": {"descricao": "Peça"}, "quantidade": 2, "unidade": "UN", "valor": 10}]}},
        {"data": {"id": 9, "nome": "Cliente", "numeroDocumento": "12345678000199", "email": "private"}}])
    result = await fetch_detail(read, "12")
    assert [call.args[0] for call in read.call_args_list] == ["/propostas-comerciais/12", "/contatos/9"]
    assert result["read_only"] is True and result["mode"] == "PREVIEW"
    detail = result["proposal"]
    assert detail["document"] == "12345678000199"
    assert detail["client_name"] == "Cliente"
    assert detail["total"] == 15
    assert detail["items"][0]["gross_total"] == 20
    assert "private" not in str(result)


@pytest.mark.parametrize("value", ["../pedidos/vendas", "0", "-1", "1?x=2", "1/2", "abc"])
async def test_invalid_ids_never_call_bling(value):
    read = AsyncMock()
    with pytest.raises(HTTPException) as error:
        await fetch_detail(read, value)
    assert error.value.status_code == 422
    read.assert_not_called()


def test_missing_and_zero_values_are_not_confused():
    result = proposal_detail({"total": 0, "itens": [{"quantidade": 0, "valor": 10}, {"valor": "NaN"}]}, {})
    assert result["total"] == 0
    assert result["items"][0]["gross_total"] == 0
    assert result["items"][1]["unit_price"] is None
    assert result["items"][1]["gross_total"] is None
    assert result["document"] is None


async def test_success_is_get_only_and_tenant_scoped():
    credentials, config = setup_read()
    config.get_json.return_value = {"data": {}}
    assert await read_preview(credentials, config, "tenant-a", "/propostas-comerciais/12") == {"data": {}}
    credentials.find_one.assert_awaited_once_with({"company_id": "tenant-a", "provider": "bling"})
    credentials.update_one.assert_not_called()
    config.refresh_access_token.assert_not_called()
    config.get_json.assert_called_once_with("/propostas-comerciais/12", "old", None)


async def test_401_refreshes_once_and_stores_only_encrypted_tokens():
    credentials, config = setup_read()
    config.get_json.side_effect = [BlingApiError(401), {"data": {}}]
    await read_preview(credentials, config, "tenant-a", "/propostas-comerciais/12")
    config.refresh_access_token.assert_called_once_with("refresh")
    assert config.get_json.call_count == 2
    updates = credentials.update_one.call_args_list
    assert all(call.args[0]["company_id"] == "tenant-a" for call in updates)
    saved = updates[1].args[1]["$set"]
    assert saved["access_token_encrypted"] == "encrypted-new"
    assert saved["refresh_token_encrypted"] == "encrypted-rotated"
    assert "$unset" in updates[2].args[1]


async def test_concurrent_refresh_does_not_reuse_refresh_token():
    credentials, config = setup_read()
    config.get_json.side_effect = BlingApiError(401)
    credentials.update_one.return_value.modified_count = 0
    with pytest.raises(HTTPException) as error:
        await read_preview(credentials, config, "tenant-a", "/propostas-comerciais/12")
    assert error.value.status_code == 409
    config.refresh_access_token.assert_not_called()


async def test_concurrent_completed_refresh_uses_latest_token():
    credentials, config = setup_read()
    original = credentials.find_one.return_value
    credentials.find_one.side_effect = [original, {**original, "access_token_encrypted": "encrypted-latest"}]
    credentials.update_one.return_value.modified_count = 0
    config.get_json.side_effect = [BlingApiError(401), {"data": {}}]
    await read_preview(credentials, config, "tenant-a", "/propostas-comerciais/12")
    config.refresh_access_token.assert_not_called()
    assert config.get_json.call_args.args[1] == "latest"


async def test_connection_change_during_refresh_does_not_use_unsaved_token():
    credentials, config = setup_read()
    credentials.update_one.side_effect = [SimpleNamespace(modified_count=1), SimpleNamespace(modified_count=0), SimpleNamespace(modified_count=1)]
    config.get_json.side_effect = BlingApiError(401)
    with pytest.raises(HTTPException) as error:
        await read_preview(credentials, config, "tenant-a", "/propostas-comerciais/12")
    assert error.value.status_code == 409
    assert config.get_json.call_count == 1


async def test_refresh_failure_releases_lease_and_redacts_error():
    credentials, config = setup_read()
    config.get_json.side_effect = BlingApiError(401)
    config.refresh_access_token.side_effect = BlingOAuthError("secret-token")
    with pytest.raises(HTTPException) as error:
        await read_preview(credentials, config, "tenant-a", "/propostas-comerciais/12")
    assert "secret-token" not in error.value.detail
    assert "$unset" in credentials.update_one.call_args.args[1]


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
async def test_upstream_errors_are_safe_and_retry_is_bounded(status):
    credentials, config = setup_read()
    config.get_json.side_effect = BlingApiError(status, "secret-token")
    with pytest.raises(HTTPException) as error:
        await read_preview(credentials, config, "tenant-a", "/propostas-comerciais/12")
    assert error.value.status_code == (502 if status == 500 else status)
    assert "secret-token" not in error.value.detail
    assert config.get_json.call_count == (2 if status == 401 else 1)


async def test_no_connection_and_disallowed_paths_never_call_provider():
    credentials, config = setup_read()
    credentials.find_one.return_value = None
    for path, status in [("/pedidos/vendas", 422), ("/propostas-comerciais/12", 409)]:
        with pytest.raises(HTTPException) as error:
            await read_preview(credentials, config, "tenant-b", path)
        assert error.value.status_code == status
    config.get_json.assert_not_called()


@pytest.mark.parametrize("payload", [{}, {"data": []}, {"data": {"id": 99}}, {"data": {"id": 12, "itens": "bad"}}])
async def test_malformed_proposal_is_rejected(payload):
    with pytest.raises(HTTPException) as error:
        await fetch_detail(AsyncMock(return_value=payload), "12")
    assert error.value.status_code == 502


def test_http_transport_is_get_with_no_redirects(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {"data": {}}
    request = Mock(return_value=response)
    monkeypatch.setattr("bling_oauth.requests.request", request)
    config = BlingOAuthConfiguration("id", "secret", "redirect", "key")
    config.get_json("/propostas-comerciais/12", "token")
    assert request.call_args.args[0] == "GET"
    assert request.call_args.kwargs["allow_redirects"] is False
    assert request.call_args.kwargs["timeout"] == 15
    response.json.side_effect = ValueError("sensitive upstream body")
    with pytest.raises(BlingOAuthError, match="invalid response"):
        config.get_json("/propostas-comerciais/12", "token")


def test_post_transport_is_json_with_no_redirects(monkeypatch):
    response = Mock(status_code=201)
    response.json.return_value = {"data": {"id": 12}}
    request = Mock(return_value=response)
    monkeypatch.setattr("bling_oauth.requests.request", request)
    config = BlingOAuthConfiguration("id", "secret", "redirect", "key")
    assert config.post_json("/pedidos/vendas", "token", {"contato": {"id": 1}}) == {"data": {"id": 12}}
    assert request.call_args.args[0] == "POST"
    assert request.call_args.kwargs["allow_redirects"] is False
    assert request.call_args.kwargs["json"] == {"contato": {"id": 1}}
