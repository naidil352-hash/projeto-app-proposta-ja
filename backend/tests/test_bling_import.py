import pytest

from bling_import import BlingImportValidationError, build_proposal_input


def detail(**changes):
    base = {
        "external_id": "42",
        "number": "8",
        "client_name": "Cliente Teste",
        "document": "12345678000199",
        "total": "90",
        "items": [{"description": "Peça", "quantity": "2", "unit": "UN", "unit_price": "50"}],
    }
    base.update(changes)
    return base


def test_builds_manual_proposal_and_preserves_source_identity():
    result = build_proposal_input(detail())
    assert result["products"] == [{"name": "Peça", "code": "", "description": "", "quantity": 2.0, "unit_price": 50.0, "unit": "UN"}]
    assert result["discount"] == 10.0
    assert result["source"] == {"provider": "bling", "external_id": "42", "external_number": "8", "provider_total": 90.0}
    assert "ID externo 42" in result["notes"]


@pytest.mark.parametrize("changes", [
    {"client_name": "Cliente não informado"},
    {"items": []},
    {"items": [{"description": "Peça", "quantity": 0, "unit_price": 1}]},
    {"items": [{"description": "", "quantity": 1, "unit_price": 1}]},
    {"total": "NaN"},
])
def test_rejects_incomplete_details(changes):
    with pytest.raises(BlingImportValidationError):
        build_proposal_input(detail(**changes))


def test_preserves_provider_total_in_note_when_freight_makes_it_larger_than_subtotal():
    result = build_proposal_input(detail(total=120))
    assert result["discount"] == 0.0
    assert "120.00" in result["notes"]
