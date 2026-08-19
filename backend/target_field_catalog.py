"""Central target-field catalog for candidate mapping.

Aliases are evidence only. They never constitute a definitive mapping.
"""

from __future__ import annotations

from typing import Any


def _field(
    field: str,
    entity: str,
    data_type: str,
    aliases: tuple[str, ...],
    compatible_types: tuple[str, ...],
    patterns: tuple[str, ...] = (),
    contexts: tuple[str, ...] = (),
    cardinality: str | None = None,
) -> dict[str, Any]:
    return {
        "field": field,
        "entity": entity,
        "type": data_type,
        "required": False,
        "aliases": list(aliases),
        "patterns": list(patterns),
        "compatible_types": list(compatible_types),
        "sheet_context": list(contexts),
        "cardinality_hint": cardinality,
    }


TARGET_FIELD_CATALOG: tuple[dict[str, Any], ...] = (
    _field("client_id", "CLIENT", "STRING", ("client id", "id cliente"), ("STRING", "IDENTIFIER_LIKE"), ("IDENTIFIER_LIKE",), ("cliente", "clientes"), "high"),
    _field("client_code", "CLIENT", "STRING", ("client code", "codigo cliente", "cod cliente"), ("STRING", "IDENTIFIER_LIKE"), ("CODE_LIKE", "IDENTIFIER_LIKE"), ("cliente", "clientes"), "high"),
    _field("client_name", "CLIENT", "STRING", ("cliente", "nome cliente", "nome do cliente", "customer", "customer name"), ("STRING", "MIXED"), (), ("cliente", "clientes", "orcamento", "pedido")),
    _field("client_legal_name", "CLIENT", "STRING", ("razao social", "empresa", "nome empresarial", "legal name"), ("STRING", "MIXED"), (), ("cliente", "clientes")),
    _field("client_document", "CLIENT", "STRING", ("cnpj", "documento", "cpf cnpj", "documento cliente"), ("STRING", "IDENTIFIER_LIKE"), ("CNPJ_LIKE", "CPF_LIKE"), ("cliente", "clientes"), "high"),
    _field("client_email", "CLIENT", "STRING", ("email", "e mail", "correio eletronico"), ("STRING",), ("EMAIL_LIKE",), ("cliente", "clientes"), "high"),
    _field("client_phone", "CLIENT", "STRING", ("telefone", "tel", "celular", "phone", "fone"), ("STRING", "INTEGER"), ("PHONE_LIKE",), ("cliente", "clientes")),
    _field("client_address", "CLIENT", "STRING", ("endereco", "endereco cliente", "logradouro"), ("STRING",), (), ("cliente", "clientes")),
    _field("client_city", "CLIENT", "STRING", ("cidade", "city"), ("STRING",), (), ("cliente", "clientes")),
    _field("client_state", "CLIENT", "STRING", ("estado", "uf", "state"), ("STRING",), (), ("cliente", "clientes")),
    _field("client_zip_code", "CLIENT", "STRING", ("cep", "codigo postal", "zip code"), ("STRING", "INTEGER", "IDENTIFIER_LIKE"), ("CEP_LIKE",), ("cliente", "clientes")),
    _field("proposal_id", "PROPOSAL", "STRING", ("proposal id", "id proposta"), ("STRING", "IDENTIFIER_LIKE"), ("IDENTIFIER_LIKE",), ("orcamento", "orcamentos", "proposta", "propostas"), "high"),
    _field("proposal_code", "PROPOSAL", "STRING", ("orcamento", "orcamento numero", "numero orcamento", "codigo proposta", "proposal code"), ("STRING", "IDENTIFIER_LIKE"), ("CODE_LIKE", "IDENTIFIER_LIKE"), ("orcamento", "orcamentos", "pedido"), "high"),
    _field("proposal_date", "PROPOSAL", "DATE", ("data proposta", "data orcamento", "data pedido", "date"), ("DATE", "DATETIME", "STRING"), ("DATE_LIKE",), ("orcamento", "orcamentos", "proposta", "pedido")),
    _field("proposal_valid_until", "PROPOSAL", "DATE", ("validade", "validade proposta", "valid until", "data validade"), ("DATE", "DATETIME", "STRING"), ("DATE_LIKE",), ("orcamento", "orcamentos", "proposta")),
    _field("proposal_status", "PROPOSAL", "STRING", ("status", "situacao", "estado proposta"), ("STRING",), (), ("orcamento", "orcamentos", "proposta", "propostas"), "low"),
    _field("proposal_description", "PROPOSAL", "STRING", ("descricao proposta", "observacao proposta", "description"), ("STRING", "MIXED"), (), ("orcamento", "orcamentos", "proposta")),
    _field("proposal_total", "PROPOSAL", "DECIMAL", ("total", "valor total", "valor", "total orcamento", "valor final"), ("DECIMAL", "INTEGER", "CURRENCY_LIKE", "MIXED"), ("CURRENCY_LIKE",), ("orcamento", "orcamentos", "proposta", "pedido")),
    _field("proposal_discount", "PROPOSAL", "DECIMAL", ("desconto", "desconto proposta", "discount"), ("DECIMAL", "INTEGER", "CURRENCY_LIKE", "PERCENTAGE_LIKE"), ("CURRENCY_LIKE", "PERCENTAGE_LIKE"), ("orcamento", "orcamentos", "proposta")),
    _field("proposal_net_total", "PROPOSAL", "DECIMAL", ("total liquido", "valor liquido", "net total"), ("DECIMAL", "INTEGER", "CURRENCY_LIKE"), ("CURRENCY_LIKE",), ("orcamento", "orcamentos", "proposta")),
    _field("product_id", "PRODUCT", "STRING", ("product id", "id produto"), ("STRING", "IDENTIFIER_LIKE"), ("IDENTIFIER_LIKE",), ("produto", "produtos"), "high"),
    _field("product_code", "PRODUCT", "STRING", ("sku", "codigo", "cod", "codigo produto", "referencia", "ref", "product code"), ("STRING", "IDENTIFIER_LIKE", "INTEGER"), ("SKU_LIKE", "CODE_LIKE", "IDENTIFIER_LIKE"), ("produto", "produtos", "item", "itens"), "high"),
    _field("product_description", "PRODUCT", "STRING", ("produto", "descricao", "descricao produto", "material", "descricao material", "desc mat"), ("STRING", "MIXED"), (), ("produto", "produtos", "item", "itens")),
    _field("product_unit", "PRODUCT", "STRING", ("unidade", "unid", "un", "unit", "unidade medida"), ("STRING",), (), ("produto", "produtos", "item", "itens"), "low"),
    _field("product_category", "PRODUCT", "STRING", ("categoria", "category", "grupo"), ("STRING",), (), ("produto", "produtos"), "low"),
    _field("product_brand", "PRODUCT", "STRING", ("marca", "brand", "fabricante"), ("STRING",), (), ("produto", "produtos")),
    _field("product_price", "PRODUCT", "DECIMAL", ("preco produto", "preco venda", "valor produto", "price"), ("DECIMAL", "INTEGER", "CURRENCY_LIKE", "MIXED"), ("CURRENCY_LIKE",), ("produto", "produtos")),
    _field("product_cost", "PRODUCT", "DECIMAL", ("custo", "custo produto", "cost"), ("DECIMAL", "INTEGER", "CURRENCY_LIKE"), ("CURRENCY_LIKE",), ("produto", "produtos")),
    _field("item_code", "PROPOSAL_ITEM", "STRING", ("item", "codigo item", "item codigo"), ("STRING", "IDENTIFIER_LIKE"), ("CODE_LIKE", "SKU_LIKE", "IDENTIFIER_LIKE"), ("item", "itens", "orcamento"), "high"),
    _field("item_description", "PROPOSAL_ITEM", "STRING", ("descricao item", "descricao material", "material item"), ("STRING", "MIXED"), (), ("item", "itens", "orcamento")),
    _field("item_unit", "PROPOSAL_ITEM", "STRING", ("un item", "unidade item", "un item", "unit item"), ("STRING",), (), ("item", "itens", "orcamento"), "low"),
    _field("item_quantity", "PROPOSAL_ITEM", "INTEGER", ("qtd", "quantidade", "qtde", "qty", "qtd item"), ("INTEGER", "DECIMAL", "STRING"), (), ("item", "itens", "orcamento", "pedido"), "low"),
    _field("item_unit_price", "PROPOSAL_ITEM", "DECIMAL", ("preco", "preco unitario", "valor unitario", "vlr unit", "vlr unitario", "preco unit"), ("DECIMAL", "INTEGER", "CURRENCY_LIKE", "MIXED"), ("CURRENCY_LIKE",), ("item", "itens", "orcamento", "pedido")),
    _field("item_discount", "PROPOSAL_ITEM", "DECIMAL", ("desconto item", "desconto produto", "discount item"), ("DECIMAL", "INTEGER", "CURRENCY_LIKE", "PERCENTAGE_LIKE"), ("CURRENCY_LIKE", "PERCENTAGE_LIKE"), ("item", "itens", "orcamento")),
    _field("item_total", "PROPOSAL_ITEM", "DECIMAL", ("total item", "valor item", "valor final", "total", "valor total", "valor"), ("DECIMAL", "INTEGER", "CURRENCY_LIKE", "MIXED"), ("CURRENCY_LIKE",), ("item", "itens", "orcamento", "pedido")),
    _field("seller_id", "SELLER", "STRING", ("seller id", "id vendedor"), ("STRING", "IDENTIFIER_LIKE"), ("IDENTIFIER_LIKE",), ("vendedor", "vendedores"), "high"),
    _field("seller_code", "SELLER", "STRING", ("codigo vendedor", "cod vendedor", "seller code"), ("STRING", "IDENTIFIER_LIKE"), ("CODE_LIKE", "IDENTIFIER_LIKE"), ("vendedor", "vendedores"), "high"),
    _field("seller_name", "SELLER", "STRING", ("vendedor", "nome vendedor", "representante", "seller"), ("STRING", "MIXED"), (), ("vendedor", "vendedores")),
    _field("seller_email", "SELLER", "STRING", ("email vendedor", "seller email"), ("STRING",), ("EMAIL_LIKE",), ("vendedor", "vendedores"), "high"),
    _field("seller_phone", "SELLER", "STRING", ("telefone vendedor", "seller phone"), ("STRING", "INTEGER"), ("PHONE_LIKE",), ("vendedor", "vendedores")),
    _field("payment_condition", "PAYMENT", "STRING", ("condicao pagamento", "condicao de pagamento", "payment condition"), ("STRING",), (), ("financeiro", "pagamento", "orcamento")),
    _field("payment_method", "PAYMENT", "STRING", ("forma pagamento", "metodo pagamento", "payment method"), ("STRING",), (), ("financeiro", "pagamento")),
    _field("installment_count", "PAYMENT", "INTEGER", ("parcelas", "numero parcelas", "installments"), ("INTEGER", "DECIMAL", "STRING"), (), ("financeiro", "pagamento"), "low"),
    _field("payment_term", "PAYMENT", "INTEGER", ("prazo pagamento", "prazo", "payment term"), ("INTEGER", "DECIMAL", "STRING"), (), ("financeiro", "pagamento")),
    _field("shipping_method", "SHIPPING", "STRING", ("forma entrega", "metodo entrega", "shipping method"), ("STRING",), (), ("entrega", "shipping")),
    _field("shipping_cost", "SHIPPING", "DECIMAL", ("frete", "custo frete", "shipping cost"), ("DECIMAL", "INTEGER", "CURRENCY_LIKE"), ("CURRENCY_LIKE",), ("entrega", "shipping")),
    _field("shipping_address", "SHIPPING", "STRING", ("endereco entrega", "shipping address"), ("STRING",), (), ("entrega", "shipping")),
    _field("shipping_city", "SHIPPING", "STRING", ("cidade entrega", "shipping city"), ("STRING",), (), ("entrega", "shipping")),
    _field("shipping_state", "SHIPPING", "STRING", ("estado entrega", "uf entrega", "shipping state"), ("STRING",), (), ("entrega", "shipping")),
    _field("shipping_zip_code", "SHIPPING", "STRING", ("cep entrega", "codigo postal entrega", "shipping zip code"), ("STRING", "INTEGER", "IDENTIFIER_LIKE"), ("CEP_LIKE",), ("entrega", "shipping")),
    _field("company_id", "COMPANY", "STRING", ("company id", "id empresa"), ("STRING", "IDENTIFIER_LIKE"), ("IDENTIFIER_LIKE",), ("empresa", "company"), "high"),
    _field("company_name", "COMPANY", "STRING", ("empresa", "nome empresa", "company", "razao social"), ("STRING", "MIXED"), (), ("empresa", "company")),
    _field("company_document", "COMPANY", "STRING", ("cnpj empresa", "documento empresa"), ("STRING", "IDENTIFIER_LIKE"), ("CNPJ_LIKE",), ("empresa", "company"), "high"),
    _field("contact_name", "CONTACT", "STRING", ("contato", "nome contato", "contact name"), ("STRING", "MIXED"), (), ("contato", "contact")),
    _field("contact_email", "CONTACT", "STRING", ("email contato", "contact email"), ("STRING",), ("EMAIL_LIKE",), ("contato", "contact"), "high"),
    _field("contact_phone", "CONTACT", "STRING", ("telefone contato", "contact phone"), ("STRING", "INTEGER"), ("PHONE_LIKE",), ("contato", "contact")),
    _field("financial_subtotal", "FINANCIAL", "DECIMAL", ("subtotal", "sub total", "financial subtotal"), ("DECIMAL", "INTEGER", "CURRENCY_LIKE"), ("CURRENCY_LIKE",), ("financeiro", "financial")),
    _field("financial_tax", "FINANCIAL", "DECIMAL", ("imposto", "taxa", "tributo", "tax"), ("DECIMAL", "INTEGER", "CURRENCY_LIKE", "PERCENTAGE_LIKE"), ("CURRENCY_LIKE", "PERCENTAGE_LIKE"), ("financeiro", "financial")),
    _field("financial_total", "FINANCIAL", "DECIMAL", ("total financeiro", "total", "valor financeiro"), ("DECIMAL", "INTEGER", "CURRENCY_LIKE", "MIXED"), ("CURRENCY_LIKE",), ("financeiro", "financial")),
)

TARGET_FIELD_BY_NAME = {field["field"]: field for field in TARGET_FIELD_CATALOG}


def get_target_field_catalog() -> tuple[dict[str, Any], ...]:
    """Return immutable-by-convention catalog metadata."""
    return TARGET_FIELD_CATALOG
