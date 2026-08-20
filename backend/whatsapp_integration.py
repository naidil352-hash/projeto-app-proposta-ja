"""Official Meta WhatsApp Cloud API integration with fail-closed controls.

Network access exists only inside WhatsAppHttpClient and is reachable only after
all SANDBOX/LIVE guards pass. Defaults block every external side effect.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import re
from typing import Any, Mapping

from communication_gateway import CommunicationAdapter

WHATSAPP_PROVIDER_VERSION = "1.0.0"
GRAPH_API_VERSION = "v25.0"
MODES = {"SIMULATION", "SANDBOX", "LIVE"}
OPT_IN_STATES = {"UNKNOWN", "OPTED_IN", "OPTED_OUT", "NOT_REQUIRED", "BLOCKED"}
MESSAGE_STATUSES = {"PREPARED", "APPROVED", "SENDING", "SENT", "DELIVERED", "READ", "FAILED", "CANCELLED", "BLOCKED"}
WEBHOOK_EVENT_TYPES = {"SENT", "DELIVERED", "READ", "FAILED", "RECEIVED", "UNKNOWN"}
ERROR_TYPES = {
    "AUTH_ERROR", "INVALID_RECIPIENT", "TEMPLATE_ERROR", "POLICY_ERROR", "RATE_LIMIT",
    "PROVIDER_ERROR", "NETWORK_ERROR", "TIMEOUT", "BUDGET_LIMIT", "KILL_SWITCH",
    "MISSING_APPROVAL", "UNKNOWN_ERROR",
}
OPT_OUT_TERMS = {"STOP", "PARAR", "SAIR", "NÃO QUERO", "NAO QUERO", "DESCADASTRAR"}
TEMPLATE_CATEGORIES = {"MARKETING", "UTILITY", "AUTHENTICATION"}
ALLOWED_TRANSITIONS = {
    "PREPARED": {"APPROVED", "CANCELLED", "BLOCKED"},
    "APPROVED": {"SENDING", "CANCELLED", "BLOCKED"},
    "SENDING": {"SENT", "DELIVERED", "READ", "FAILED"},
    "SENT": {"DELIVERED", "READ", "FAILED"},
    "DELIVERED": {"READ", "FAILED"},
    "READ": set(),
    "FAILED": set(),
    "CANCELLED": set(),
    "BLOCKED": set(),
}
DEFAULT_DAILY_MESSAGE_LIMIT = 10
DEFAULT_MONTHLY_MESSAGE_LIMIT = 100
DEFAULT_DAILY_COST_LIMIT = 5.0
DEFAULT_MONTHLY_COST_LIMIT = 25.0
DEFAULT_MIN_SEND_INTERVAL_SECONDS = 6
CUSTOMER_SERVICE_WINDOW_HOURS = 24


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True, repr=False)
class WhatsAppConfiguration:
    enabled: bool = False
    sandbox_enabled: bool = False
    live_enabled: bool = False
    require_human_approval: bool = True
    allow_external_side_effects: bool = False
    global_kill_switch: bool = True
    access_token: str = ""
    phone_number_id: str = ""
    business_account_id: str = ""
    app_id: str = ""
    app_secret: str = ""
    verify_token: str = ""
    webhook_secret: str = ""
    configured_company_id: str = ""
    test_recipients: tuple[str, ...] = ()
    graph_api_version: str = GRAPH_API_VERSION
    connect_timeout: float = 3.0
    read_timeout: float = 7.0
    total_timeout: float = 10.0
    daily_message_limit: int = DEFAULT_DAILY_MESSAGE_LIMIT
    monthly_message_limit: int = DEFAULT_MONTHLY_MESSAGE_LIMIT
    daily_cost_limit: float = DEFAULT_DAILY_COST_LIMIT
    monthly_cost_limit: float = DEFAULT_MONTHLY_COST_LIMIT
    minimum_send_interval_seconds: int = DEFAULT_MIN_SEND_INTERVAL_SECONDS
    real_test_enabled: bool = False

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "WhatsAppConfiguration":
        env = environ if environ is not None else os.environ
        recipients = tuple(sorted(filter(None, (item.strip() for item in env.get("WHATSAPP_TEST_RECIPIENTS", "").split(",")))))
        return cls(
            enabled=_bool(env.get("WHATSAPP_ENABLED")),
            sandbox_enabled=_bool(env.get("WHATSAPP_SANDBOX_ENABLED")),
            live_enabled=_bool(env.get("WHATSAPP_LIVE_ENABLED")),
            require_human_approval=_bool(env.get("WHATSAPP_REQUIRE_HUMAN_APPROVAL"), True),
            allow_external_side_effects=_bool(env.get("WHATSAPP_ALLOW_EXTERNAL_SIDE_EFFECTS")),
            global_kill_switch=_bool(env.get("WHATSAPP_GLOBAL_KILL_SWITCH"), True),
            access_token=env.get("WHATSAPP_ACCESS_TOKEN", ""),
            phone_number_id=env.get("WHATSAPP_PHONE_NUMBER_ID", ""),
            business_account_id=env.get("WHATSAPP_BUSINESS_ACCOUNT_ID", ""),
            app_id=env.get("WHATSAPP_APP_ID", ""),
            app_secret=env.get("WHATSAPP_APP_SECRET", ""),
            verify_token=env.get("WHATSAPP_VERIFY_TOKEN", ""),
            webhook_secret=env.get("WHATSAPP_WEBHOOK_SECRET", ""),
            configured_company_id=env.get("WHATSAPP_CONFIG_COMPANY_ID", ""),
            test_recipients=recipients,
            graph_api_version=env.get("WHATSAPP_GRAPH_API_VERSION", GRAPH_API_VERSION),
            connect_timeout=_float(env.get("WHATSAPP_CONNECT_TIMEOUT"), 3.0),
            read_timeout=_float(env.get("WHATSAPP_READ_TIMEOUT"), 7.0),
            total_timeout=_float(env.get("WHATSAPP_TOTAL_TIMEOUT"), 10.0),
            daily_message_limit=_int(env.get("WHATSAPP_DAILY_MESSAGE_LIMIT"), DEFAULT_DAILY_MESSAGE_LIMIT),
            monthly_message_limit=_int(env.get("WHATSAPP_MONTHLY_MESSAGE_LIMIT"), DEFAULT_MONTHLY_MESSAGE_LIMIT),
            daily_cost_limit=_float(env.get("WHATSAPP_DAILY_COST_LIMIT"), DEFAULT_DAILY_COST_LIMIT),
            monthly_cost_limit=_float(env.get("WHATSAPP_MONTHLY_COST_LIMIT"), DEFAULT_MONTHLY_COST_LIMIT),
            minimum_send_interval_seconds=_int(env.get("WHATSAPP_MIN_SEND_INTERVAL_SECONDS"), DEFAULT_MIN_SEND_INTERVAL_SECONDS),
            real_test_enabled=_bool(env.get("WHATSAPP_REAL_TEST_ENABLED")),
        )

    def public_state(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "sandbox_enabled": self.sandbox_enabled,
            "live_enabled": self.live_enabled,
            "require_human_approval": self.require_human_approval,
            "allow_external_side_effects": self.allow_external_side_effects,
            "global_kill_switch": self.global_kill_switch,
            "credentials_configured": all([self.access_token, self.phone_number_id, self.business_account_id, self.app_id, self.app_secret, self.verify_token]),
            "configured_company": bool(self.configured_company_id),
            "test_recipient_count": len(self.test_recipients),
            "graph_api_version": self.graph_api_version,
            "daily_message_limit": self.daily_message_limit,
            "monthly_message_limit": self.monthly_message_limit,
            "daily_cost_limit": self.daily_cost_limit,
            "monthly_cost_limit": self.monthly_cost_limit,
        }

    def validate(self, mode: str, company_id: str) -> None:
        if mode not in MODES:
            raise ValueError("INVALID_WHATSAPP_MODE")
        if mode == "SIMULATION":
            return
        if not self.enabled:
            raise ValueError("WHATSAPP_DISABLED")
        if self.global_kill_switch:
            raise ValueError("WHATSAPP_KILL_SWITCH_ACTIVE")
        if not self.allow_external_side_effects:
            raise ValueError("EXTERNAL_SIDE_EFFECTS_FORBIDDEN")
        if not self.require_human_approval:
            raise ValueError("HUMAN_APPROVAL_CONFIGURATION_REQUIRED")
        if not self.configured_company_id or self.configured_company_id != company_id:
            raise ValueError("WHATSAPP_TENANT_CONFIGURATION_MISMATCH")
        if mode == "SANDBOX" and not self.sandbox_enabled:
            raise ValueError("WHATSAPP_SANDBOX_DISABLED")
        if mode == "LIVE" and not self.live_enabled:
            raise ValueError("WHATSAPP_LIVE_DISABLED")
        if not all([self.access_token, self.phone_number_id, self.business_account_id, self.app_id, self.app_secret, self.verify_token]):
            raise ValueError("WHATSAPP_CONFIGURATION_INCOMPLETE")
        if mode == "LIVE" and self.global_kill_switch:
            raise ValueError("WHATSAPP_KILL_SWITCH_ACTIVE")


def whatsapp_configurations_from_env(environ: Mapping[str, str] | None = None) -> tuple[WhatsAppConfiguration, ...]:
    env = dict(environ if environ is not None else os.environ)
    raw_registry = env.get("WHATSAPP_TENANT_CONFIGS_JSON", "").strip()
    if not raw_registry:
        return (WhatsAppConfiguration.from_env(env),)
    try:
        registry = json.loads(raw_registry)
    except json.JSONDecodeError as exc:
        raise ValueError("WHATSAPP_TENANT_CONFIGS_INVALID") from exc
    if not isinstance(registry, dict) or not registry:
        raise ValueError("WHATSAPP_TENANT_CONFIGS_INVALID")
    configurations = []
    for company_id, overrides in sorted(registry.items()):
        if not isinstance(overrides, dict):
            raise ValueError("WHATSAPP_TENANT_CONFIGS_INVALID")
        tenant_env = {**env, **{str(key): str(value) for key, value in overrides.items()}}
        tenant_env.pop("WHATSAPP_TENANT_CONFIGS_JSON", None)
        tenant_env["WHATSAPP_CONFIG_COMPANY_ID"] = str(company_id)
        configurations.append(WhatsAppConfiguration.from_env(tenant_env))
    return tuple(configurations)


def whatsapp_configuration_for_company(company_id: str, environ: Mapping[str, str] | None = None) -> WhatsAppConfiguration:
    configurations = whatsapp_configurations_from_env(environ)
    matches = [item for item in configurations if item.configured_company_id == company_id]
    if len(matches) != 1:
        raise ValueError("WHATSAPP_TENANT_CONFIGURATION_NOT_FOUND")
    return matches[0]


@dataclass(frozen=True)
class NormalizedPhone:
    original_phone: str | None
    normalized_phone: str | None
    normalization_rule: str
    valid: bool


def normalize_brazil_phone(phone: Any) -> NormalizedPhone:
    original = None if phone in (None, "") else str(phone).strip()
    if not original:
        return NormalizedPhone(original, None, "MISSING", False)
    digits = re.sub(r"\D", "", original)
    if not digits.startswith("55"):
        return NormalizedPhone(original, None, "COUNTRY_CODE_REQUIRED", False)
    national = digits[2:]
    if len(national) not in {10, 11} or national[0] == "0":
        return NormalizedPhone(original, None, "INVALID_BRAZIL_LENGTH", False)
    normalized = "+" + digits
    rule = "PRESERVED_E164" if original == normalized else "REMOVED_FORMATTING_ONLY"
    return NormalizedPhone(original, normalized, rule, True)


def idempotency_key(company_id: str, draft: dict[str, Any], communication: dict[str, Any], job: dict[str, Any]) -> str:
    raw = "|".join([
        company_id,
        str(draft.get("message_draft_id")),
        str(communication.get("request_id")),
        str(job.get("execution_job_id")),
        WHATSAPP_PROVIDER_VERSION,
        str(draft.get("source_snapshot_hash")),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def customer_window_state(conversation: dict[str, Any] | None, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    last_received = (conversation or {}).get("last_received_at")
    if not last_received:
        return {"customer_initiated_window": "CLOSED", "template_required": True, "last_received_at": None}
    parsed = datetime.fromisoformat(str(last_received).replace("Z", "+00:00"))
    is_open = now - parsed <= timedelta(hours=CUSTOMER_SERVICE_WINDOW_HOURS)
    return {"customer_initiated_window": "OPEN" if is_open else "CLOSED", "template_required": not is_open, "last_received_at": last_received}


def validate_template(template: dict[str, Any] | None, required: bool) -> None:
    if not required and not template:
        return
    if not template:
        raise ValueError("TEMPLATE_REQUIRED")
    if template.get("status") != "APPROVED":
        raise ValueError("TEMPLATE_NOT_APPROVED")
    if template.get("category") not in TEMPLATE_CATEGORIES:
        raise ValueError("TEMPLATE_CATEGORY_INVALID")
    if not template.get("name") or not template.get("language") or not template.get("version"):
        raise ValueError("TEMPLATE_CONFIGURATION_INCOMPLETE")
    expected = tuple(template.get("variables") or [])
    supplied = tuple((template.get("resolved_variables") or {}).keys())
    if expected != supplied:
        raise ValueError("TEMPLATE_VARIABLES_MISMATCH")


def check_budget(usage: dict[str, Any], configuration: WhatsAppConfiguration, estimated_cost: float) -> None:
    if usage.get("daily_count", 0) >= configuration.daily_message_limit:
        raise ValueError("BUDGET_LIMIT_REACHED")
    if usage.get("monthly_count", 0) >= configuration.monthly_message_limit:
        raise ValueError("BUDGET_LIMIT_REACHED")
    if usage.get("daily_cost", 0.0) + estimated_cost > configuration.daily_cost_limit:
        raise ValueError("BUDGET_LIMIT_REACHED")
    if usage.get("monthly_cost", 0.0) + estimated_cost > configuration.monthly_cost_limit:
        raise ValueError("BUDGET_LIMIT_REACHED")


def usage_period_keys(now: datetime | None = None) -> tuple[str, str]:
    current = now or datetime.now(timezone.utc)
    return current.date().isoformat(), current.strftime("%Y-%m")


def check_rate_limit(last_sent_at: str | None, configuration: WhatsAppConfiguration, now: datetime | None = None) -> None:
    if not last_sent_at:
        return
    now = now or datetime.now(timezone.utc)
    last = datetime.fromisoformat(last_sent_at.replace("Z", "+00:00"))
    if (now - last).total_seconds() < configuration.minimum_send_interval_seconds:
        raise ValueError("RATE_LIMIT")


def transition_status(current: str, target: str) -> str:
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"INVALID_STATUS_TRANSITION:{current}->{target}")
    return target


def detect_opt_out(text: str | None, terms: set[str] | None = None) -> bool:
    normalized = re.sub(r"\s+", " ", (text or "").strip().upper())
    return normalized in (terms or OPT_OUT_TERMS)


def validate_send_guards(
    mode: str,
    configuration: WhatsAppConfiguration,
    company_id: str,
    message: dict[str, Any],
    draft: dict[str, Any],
    communication: dict[str, Any],
    job: dict[str, Any],
    consent: dict[str, Any] | None,
    usage: dict[str, Any],
    template: dict[str, Any] | None,
    conversation: dict[str, Any] | None,
    explicit_confirmation: bool,
    estimated_cost: float,
    now: datetime | None = None,
) -> None:
    configuration.validate(mode, company_id)
    if message.get("status") != "APPROVED":
        raise ValueError("MISSING_APPROVAL")
    if not explicit_confirmation:
        raise ValueError("MISSING_SEND_CONFIRMATION")
    if draft.get("status") != "APPROVED" or not draft.get("human_approved"):
        raise ValueError("MISSING_APPROVAL")
    if communication.get("status") not in {"PREPARED", "SIMULATED", "APPROVED"}:
        raise ValueError("COMMUNICATION_NOT_APPROVED")
    if job.get("status") not in {"CREATED", "SIMULATED", "APPROVED"}:
        raise ValueError("EXECUTION_JOB_NOT_APPROVED")
    consent_state = (consent or {}).get("status", "UNKNOWN")
    if consent_state != "OPTED_IN":
        raise ValueError("OPT_IN_REQUIRED")
    if (consent or {}).get("blocked"):
        raise ValueError("RECIPIENT_BLOCKED")
    window = customer_window_state(conversation, now)
    validate_template(template, window["template_required"])
    check_budget(usage, configuration, estimated_cost)
    check_rate_limit(usage.get("last_sent_at"), configuration, now)
    recipient = message.get("recipient", {}).get("normalized_phone")
    if mode == "SANDBOX" and recipient not in configuration.test_recipients:
        raise ValueError("SANDBOX_RECIPIENT_NOT_ALLOWED")


def build_internal_payload(message: dict[str, Any], draft: dict[str, Any], template: dict[str, Any] | None) -> dict[str, Any]:
    content = draft.get("edited_content") or draft.get("content") or {}
    body = "\n".join(str(content.get(key)) for key in ["opening", "body", "call_to_action", "closing"] if content.get(key))
    if template:
        return {
            "recipient": message["recipient"]["normalized_phone"],
            "message_type": "template",
            "content": None,
            "template": {"name": template["name"], "version": template["version"], "language": template["language"], "category": template["category"]},
            "variables": template.get("resolved_variables", {}),
        }
    return {"recipient": message["recipient"]["normalized_phone"], "message_type": "text", "content": body, "template": None, "variables": []}


def to_meta_payload(payload: dict[str, Any], opaque_callback_data: str) -> dict[str, Any]:
    base = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": payload["recipient"], "biz_opaque_callback_data": opaque_callback_data}
    if payload["message_type"] == "template":
        template = payload["template"]
        parameters = [
            {"type": "text", "parameter_name": name, "text": str(value)}
            for name, value in payload.get("variables", {}).items()
        ]
        return {**base, "type": "template", "template": {"name": template["name"], "language": {"code": template["language"]}, "components": [{"type": "body", "parameters": parameters}] if parameters else []}}
    return {**base, "type": "text", "text": {"preview_url": False, "body": payload["content"]}}


def prepare_whatsapp_message(
    company_id: str,
    draft: dict[str, Any],
    communication: dict[str, Any],
    job: dict[str, Any],
    client: dict[str, Any],
    mode: str,
    consent: dict[str, Any] | None,
    conversation: dict[str, Any] | None,
    template: dict[str, Any] | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if any(document.get("company_id") != company_id for document in [draft, communication, job, client]):
        raise ValueError("TENANT_MISMATCH")
    if draft.get("communication_request_id") != communication.get("request_id") or draft.get("execution_job_id") != job.get("execution_job_id"):
        raise ValueError("UPSTREAM_MISMATCH")
    phone = normalize_brazil_phone(client.get("phone"))
    window = customer_window_state(conversation, now)
    status, reason = "PREPARED", None
    if not phone.valid:
        status, reason = "BLOCKED", "INVALID_RECIPIENT"
    elif mode not in MODES:
        status, reason = "BLOCKED", "INVALID_WHATSAPP_MODE"
    elif draft.get("status") != "APPROVED" or not draft.get("human_approved"):
        status, reason = "BLOCKED", "MISSING_APPROVAL"
    elif (consent or {}).get("status", "UNKNOWN") != "OPTED_IN":
        status, reason = "BLOCKED", "OPT_IN_REQUIRED"
    elif window["template_required"]:
        try:
            validate_template(template, True)
        except ValueError as exc:
            status, reason = "BLOCKED", str(exc)
    key = idempotency_key(company_id, draft, communication, job)
    message_id = "wa-" + key[:24]
    payload = None if status == "BLOCKED" else build_internal_payload({"recipient": {"normalized_phone": phone.normalized_phone}}, draft, template if window["template_required"] else None)
    timestamp = (now or datetime.now(timezone.utc)).isoformat()
    return {
        "company_id": company_id,
        "message_id": message_id,
        "provider_message_id": None,
        "communication_request_id": communication.get("request_id"),
        "message_draft_id": draft.get("message_draft_id"),
        "execution_job_id": job.get("execution_job_id"),
        "opportunity_id": draft.get("opportunity_id"),
        "client_id": client.get("id"),
        "recipient": {"original_phone": phone.original_phone, "normalized_phone": phone.normalized_phone, "normalization_rule": phone.normalization_rule},
        "status": status,
        "provider_status": None,
        "mode": mode,
        "provider": "meta_whatsapp_cloud_api" if mode in {"SANDBOX", "LIVE"} else "simulation",
        "provider_version": WHATSAPP_PROVIDER_VERSION,
        "idempotency_key": key,
        "payload": payload,
        "template": template,
        "opt_in_status": (consent or {}).get("status", "UNKNOWN"),
        "window": window,
        "reason": reason,
        "result": {},
        "sent_at": None,
        "delivered_at": None,
        "read_at": None,
        "failed_at": None,
        "error_code": None,
        "error_message": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


class WhatsAppHttpClient:
    def __init__(self, configuration: WhatsAppConfiguration):
        self.configuration = configuration

    def send(self, meta_payload: dict[str, Any]) -> dict[str, Any]:
        import httpx

        timeout = httpx.Timeout(self.configuration.total_timeout, connect=self.configuration.connect_timeout, read=self.configuration.read_timeout, write=self.configuration.read_timeout, pool=self.configuration.connect_timeout)
        url = f"https://graph.facebook.com/{self.configuration.graph_api_version}/{self.configuration.phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {self.configuration.access_token}", "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, headers=headers, json=meta_payload)
            data = response.json()
        except httpx.TimeoutException as exc:
            raise WhatsAppProviderError("TIMEOUT", None, None, "Provider timeout") from exc
        except httpx.HTTPError as exc:
            raise WhatsAppProviderError("NETWORK_ERROR", None, None, "Provider network error") from exc
        if response.status_code >= 400:
            error = data.get("error", {}) if isinstance(data, dict) else {}
            raise WhatsAppProviderError(classify_provider_error(error.get("code")), response.status_code, error.get("code"), error.get("type") or "Provider error", error.get("fbtrace_id"))
        provider_id = ((data.get("messages") or [{}])[0]).get("id")
        if not provider_id:
            raise WhatsAppProviderError("PROVIDER_ERROR", response.status_code, None, "Missing provider message id")
        return {"provider_message_id": provider_id, "provider_request_id": data.get("fbtrace_id"), "status_code": response.status_code}


class WhatsAppProviderError(Exception):
    def __init__(self, error_type: str, status_code: int | None, error_code: int | None, safe_message: str, provider_request_id: str | None = None):
        super().__init__(safe_message)
        self.error_type = error_type if error_type in ERROR_TYPES else "UNKNOWN_ERROR"
        self.status_code = status_code
        self.error_code = error_code
        self.safe_message = safe_message
        self.provider_request_id = provider_request_id

    def as_result(self) -> dict[str, Any]:
        return {"error_type": self.error_type, "status_code": self.status_code, "error_code": self.error_code, "error_message": self.safe_message, "provider_request_id": self.provider_request_id}


def classify_provider_error(code: Any) -> str:
    if code in {0, 3, 10, 190, 200, 131005}:
        return "AUTH_ERROR"
    if code in {4, 80007, 130429, 131048, 131056}:
        return "RATE_LIMIT"
    if code in {131008, 131009, 131021, 131026}:
        return "INVALID_RECIPIENT"
    if code in {131047, 132000, 132001, 132005, 132007, 132012, 132015, 132016}:
        return "TEMPLATE_ERROR"
    if code in {368, 130497, 131031, 131049, 131050, 131063, 131064}:
        return "POLICY_ERROR"
    return "PROVIDER_ERROR"


class WhatsAppBusinessProvider(CommunicationAdapter):
    name = "meta_whatsapp_cloud_api"

    def __init__(self, configuration: WhatsAppConfiguration, mode: str, http_client: WhatsAppHttpClient | None = None):
        self.configuration = configuration
        self.mode = mode
        self.http_client = http_client or WhatsAppHttpClient(configuration)

    def validate(self, request: dict[str, Any]) -> None:
        self.configuration.validate(self.mode, request.get("company_id", ""))
        if request.get("status") != "SENDING":
            raise ValueError("MESSAGE_NOT_SENDING")
        if not request.get("payload"):
            raise ValueError("MESSAGE_PAYLOAD_MISSING")

    def prepare(self, request: dict[str, Any]) -> dict[str, Any]:
        self.validate(request)
        return to_meta_payload(request["payload"], request["idempotency_key"])

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.http_client.send(self.prepare(request))

    def health_check(self) -> dict[str, Any]:
        return {"healthy": True, "provider": self.name, "mode": self.mode, "network_probe_performed": False, **self.configuration.public_state()}


class WhatsAppSimulationProvider(CommunicationAdapter):
    name = "whatsapp_simulation"

    def validate(self, request: dict[str, Any]) -> None:
        if request.get("mode") != "SIMULATION":
            raise ValueError("INVALID_WHATSAPP_MODE")

    def prepare(self, request: dict[str, Any]) -> dict[str, Any]:
        self.validate(request)
        return request.get("payload") or {}

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        self.prepare(request)
        return {"simulated": True, "external_side_effect": False, "provider_message_id": None}

    def health_check(self) -> dict[str, Any]:
        return {"healthy": True, "provider": self.name, "mode": "SIMULATION", "network_probe_performed": False}


class WhatsAppProviderFactory:
    @staticmethod
    def create(mode: str, configuration: WhatsAppConfiguration, http_client: WhatsAppHttpClient | None = None) -> CommunicationAdapter:
        if mode == "SIMULATION":
            return WhatsAppSimulationProvider()
        if mode in {"SANDBOX", "LIVE"}:
            return WhatsAppBusinessProvider(configuration, mode, http_client)
        raise ValueError("INVALID_WHATSAPP_MODE")


def verify_webhook_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    if not raw_body or not signature_header or not signature_header.startswith("sha256=") or not app_secret:
        return False
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.split("=", 1)[1])


def verify_webhook_challenge(mode: str | None, challenge: str | None, verify_token: str | None, configured_token: str) -> str:
    if mode != "subscribe" or not challenge or not configured_token or not hmac.compare_digest(verify_token or "", configured_token):
        raise ValueError("WEBHOOK_VERIFICATION_FAILED")
    return challenge


def parse_webhook_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for entry in payload.get("entry", []):
        waba_id = entry.get("id")
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_number_id = value.get("metadata", {}).get("phone_number_id")
            for status in value.get("statuses", []):
                provider_status = str(status.get("status", "unknown")).lower()
                event_type = provider_status.upper() if provider_status.upper() in WEBHOOK_EVENT_TYPES else "UNKNOWN"
                errors = status.get("errors") or []
                event_id = "status:" + hashlib.sha256(f"{status.get('id')}:{provider_status}:{status.get('timestamp')}".encode()).hexdigest()
                events.append({"provider_event_id": event_id, "event_type": event_type, "provider_message_id": status.get("id"), "provider_status": provider_status, "timestamp": status.get("timestamp"), "recipient": status.get("recipient_id"), "error": errors[0] if errors else None, "pricing": status.get("pricing"), "waba_id": waba_id, "phone_number_id": phone_number_id, "raw": status})
            contacts = {item.get("wa_id"): item for item in value.get("contacts", [])}
            for message in value.get("messages", []):
                provider_id = message.get("id")
                event_type = "RECEIVED"
                events.append({"provider_event_id": provider_id or "received:" + hashlib.sha256(json.dumps(message, sort_keys=True).encode()).hexdigest(), "event_type": event_type, "provider_message_id": provider_id, "provider_status": "received", "timestamp": message.get("timestamp"), "recipient": message.get("from"), "contact": contacts.get(message.get("from")), "message_type": message.get("type"), "text": message.get("text", {}).get("body") if message.get("type") == "text" else None, "waba_id": waba_id, "phone_number_id": phone_number_id, "raw": message})
    return events
