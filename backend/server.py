from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env", override=True)

import os
import uuid
import csv
import json
import hashlib
import logging
import asyncio
import zipfile
import secrets
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Literal
from xml.etree import ElementTree as ET

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr
from structure_analyzer import ANALYZER_VERSION, analyze_structure
from mapping_engine import MAPPING_ENGINE_VERSION, generate_candidate_mappings
from decision_engine import DECISION_ENGINE_VERSION, decide_mapping_candidates
from mapping_application import (
    APPLICATION_STATES,
    build_application_plan,
    build_source_signature,
    create_confirmation,
    create_template as create_mapping_template,
    apply_standard_records,
    detect_template_drift,
    source_key,
    validate_source,
)
from learning_engine import (
    LEARNING_VERSION,
    build_learning_summary,
    create_learning_event,
    feedback_event_type,
    project_knowledge,
    pattern_signature,
)
from knowledge_adapter import KNOWLEDGE_ADAPTER_VERSION, build_learned_evidence_index
from commercial_context import COMMERCIAL_CONTEXT_VERSION, build_commercial_context
from sales_intelligence import SALES_INTELLIGENCE_VERSION, build_sales_insight
from action_planning import ACTION_PLANNING_VERSION, build_action_plan
from action_execution import (
    ACTION_EXECUTOR_VERSION,
    build_execution_job,
    cancel_execution_job,
    simulate_execution_job,
)
from communication_gateway import (
    COMMUNICATION_GATEWAY_VERSION,
    build_communication_request,
    cancel_communication_request,
    simulate_communication_request,
)
from message_intelligence import (
    MESSAGE_INTELLIGENCE_VERSION,
    build_message_draft,
)
from modules.message_drafts.repository import (
    MessageDraftInputsIncomplete,
    MessageDraftInputsNotFound,
    load_message_draft_inputs,
)
from modules.startup.indexes import ensure_indexes
from modules.integration_hub.adapters import create_default_registry
from modules.integration_hub.router import create_integration_hub_router
from bling_oauth import BlingApiError, BlingOAuthConfiguration, BlingOAuthError
from whatsapp_integration import (
    WhatsAppConfiguration,
    WhatsAppProviderError,
    WhatsAppProviderFactory,
    build_internal_payload,
    check_budget as check_whatsapp_budget,
    detect_opt_out,
    normalize_brazil_phone,
    parse_webhook_events,
    prepare_whatsapp_message,
    to_meta_payload,
    transition_status as transition_whatsapp_status,
    validate_send_guards,
    verify_webhook_challenge,
    verify_webhook_signature,
    whatsapp_configuration_for_company,
    whatsapp_configurations_from_env,
)

import stripe

import cloudinary
import cloudinary.uploader

from fastapi import UploadFile, File

# ---------- DB ----------
mongo_url = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
client = None
db = None


def ensure_db_for_current_loop():
    global client, db
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    current_loop_id = id(loop)
    if client is None:
        client = AsyncIOMotorClient(mongo_url)
        db = client[DB_NAME]
        return

    io_loop = getattr(client, "_io_loop", None)
    if io_loop is None or current_loop_id != id(io_loop):
        try:
            client.close()
        except Exception:
            pass
        client = AsyncIOMotorClient(mongo_url)
        db = client[DB_NAME]


ensure_db_for_current_loop()


# ---------- App ----------
app = FastAPI(title="PROPOSTA JÁ API")
api_router = APIRouter(prefix="/api")


# ---------- Auth helpers ----------
JWT_ALGORITHM = "HS256"
JWT_SECRET = os.environ["JWT_SECRET"]
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
if STRIPE_API_KEY:
    stripe.api_key = STRIPE_API_KEY

# ---------- Cloudinary ----------
CLOUDINARY_CLOUD_NAME = os.environ.get(
    "CLOUDINARY_CLOUD_NAME",
    ""
)

CLOUDINARY_API_KEY = os.environ.get(
    "CLOUDINARY_API_KEY",
    ""
)

CLOUDINARY_API_SECRET = os.environ.get(
    "CLOUDINARY_API_SECRET",
    ""
)

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True,
)

# Fixed subscription packages (price defined server-side)
SUBSCRIPTION_PLANS = {
    "pro_monthly": {"amount": 29.90, "currency": "brl", "days": 30, "label": "Pro Mensal"},
    "pro_yearly": {"amount": 299.00, "currency": "brl", "days": 365, "label": "Pro Anual"},
}
FREE_MONTHLY_QUOTA = 10


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


async def log_audit(
    action: str,
    entity_type: str,
    entity_id: str | None,
    old_value: dict | None,
    new_value: dict | None,
    user_id: str | None = None,
    company_id: str | None = None
):
    try:
        def clean_val(v):
            if not v:
                return v
            cleaned = dict(v)
            cleaned.pop("_id", None)
            cleaned.pop("password_hash", None)
            cleaned.pop("reset_token", None)
            cleaned.pop("verification_token", None)
            return cleaned

        log_doc = {
            "id": str(uuid.uuid4()),
            "company_id": company_id,
            "user_id": user_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "old_value": clean_val(old_value),
            "new_value": clean_val(new_value),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.audit_logs.insert_one(log_doc)
    except Exception as e:
        logging.error(f"Erro ao salvar audit log: {e}")


async def check_rate_limit(action: str, identifier: str, limit: int, window_seconds: int, request: Request):
    ensure_db_for_current_loop()
    ip = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=window_seconds)

    # Clean old entries
    await db.rate_limits.delete_many({"timestamp": {"$lt": window_start}})

    # Limit by identifier
    if identifier:
        id_key = f"{action}:{identifier.lower().strip()}"
        id_count = await db.rate_limits.count_documents({"key": id_key, "timestamp": {"$gte": window_start}})
        if id_count >= limit:
            raise HTTPException(
                status_code=429,
                detail="Muitas tentativas. Por favor, tente novamente mais tarde."
            )

    # Limit by IP
    ip_key = f"{action}:{ip}"
    ip_count = await db.rate_limits.count_documents({"key": ip_key, "timestamp": {"$gte": window_start}})
    if ip_count >= limit:
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas. Por favor, tente novamente mais tarde."
        )

    # Insert new entries
    insert_docs = []
    if identifier:
        insert_docs.append({"key": id_key, "timestamp": now})
    insert_docs.append({"key": ip_key, "timestamp": now})
    await db.rate_limits.insert_many(insert_docs)


def create_access_token(user_id: str, email: str, session_id: Optional[str] = None) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
        "type": "access",
    }
    if session_id:
        payload["session_id"] = session_id
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(request: Request) -> dict:
    ensure_db_for_current_loop()
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado")
    token = auth[7:]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sessão expirada")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    
    # Force founder/lifetime properties to remain active, owner, and undeleted
    if user.get("founder") or user.get("lifetime"):
        user["role"] = "owner"
        user["active"] = True
        user["deleted"] = False
        
    # Soft delete / deactivation check
    if "active" not in user:
        user["active"] = True
    if user.get("deleted") is True or not user.get("active"):
        raise HTTPException(status_code=403, detail="Usuário desativado")
        
    # Check session_id validity if present in token payload
    token_session_id = payload.get("session_id")
    if token_session_id:
        db_session_id = user.get("session_id")
        if token_session_id != db_session_id:
            raise HTTPException(status_code=401, detail="Sessão inválida ou expirada")

    # Update activity automatically
    now = datetime.now(timezone.utc).isoformat()
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"last_activity_at": now}}
    )
    user["last_activity_at"] = now
        
    # Temporary transition fallbacks (to be removed after migration_v11.py execution)
    # WARNING: Maintain fallback for legacy users during V1.1 transition.
    # Future integrity note: Ensure company_id is mandatory and indexable in future releases.
    if not user.get("role"):
        user["role"] = "owner"
    if not user.get("company_id"):
        user["company_id"] = await get_company_id(user["id"])
        
    return user


def require_role(allowed_roles: List[str]):
    async def dependency(user: dict = Depends(get_current_user)) -> dict:
        role = user.get("role", "owner")
        if role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Acesso negado: permissão insuficiente")
        return user
    return dependency

require_owner = require_role(["owner"])
require_admin = require_role(["owner", "admin"])
require_seller = require_role(["owner", "admin", "seller"])

MAX_IMPORT_FILE_SIZE_BYTES = int(os.environ.get("MAX_IMPORT_FILE_SIZE_BYTES", 10 * 1024 * 1024))
IMPORT_STORAGE_ROOT = ROOT_DIR / "uploads"
ALLOWED_IMPORT_EXTENSIONS = {".csv": "CSV", ".xlsx": "XLSX"}
IMPORT_PARSER_VERSION = "1.0.0"


class OriginalFileStorage:
    root_dir = IMPORT_STORAGE_ROOT

    @classmethod
    def ensure_company_dir(cls, company_id: str) -> Path:
        company_dir = cls.root_dir / company_id
        company_dir.mkdir(parents=True, exist_ok=True)
        return company_dir

    @classmethod
    def save(cls, company_id: str, filename: str, content: bytes) -> str:
        safe_name = sanitize_filename(filename)
        company_dir = cls.ensure_company_dir(company_id)
        storage_name = f"{uuid.uuid4()}_{safe_name}"
        target_path = company_dir / storage_name
        with open(target_path, "wb") as fh:
            fh.write(content)
        return str(target_path)

    @classmethod
    def delete(cls, ref: str) -> bool:
        try:
            path = Path(ref)
            if path.exists():
                path.unlink()
                return True
        except Exception:
            return False
        return False


def sanitize_filename(filename: str) -> str:
    name = (filename or "import").strip()
    name = name.replace("\\", "/").split("/")[-1]
    safe_name = "".join(ch for ch in name if ch.isalnum() or ch in "._- ")
    safe_name = safe_name.strip() or "import"
    return safe_name


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_company_id(user: dict) -> str:
    company_id = user.get("company_id") or user.get("company")
    if not company_id:
        raise HTTPException(status_code=400, detail="Empresa não vinculada ao usuário")
    return company_id


def _csv_sniffer_delimiter(sample: str) -> str:
    try:
        sample = sample.replace("\r", "\n")
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except Exception:
        return ";" if ";" in sample else ","


def _xlsx_cell_value(cell: ET.Element | None, shared_strings: list[str]) -> str:
    if cell is None:
        return ""
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        text = "".join(node.text or "" for node in cell.iter() if node.tag.endswith("}t"))
        return text
    if cell_type == "s":
        idx = int((cell.find("{*}v") or cell.find("v")).text or "0")
        return shared_strings[idx] if idx < len(shared_strings) else ""
    value_node = cell.find("{*}v") or cell.find("v")
    return (value_node.text if value_node is not None else "")


def _parse_xlsx_file(file_path: str) -> list[dict]:
    rows_by_sheet: list[dict] = []
    with zipfile.ZipFile(file_path, "r") as zf:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("{*}si"):
                text = "".join(node.text or "" for node in si.iter() if node.tag.endswith("}t"))
                shared_strings.append(text)

        workbook_root = ET.fromstring(zf.read("xl/workbook.xml"))
        ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
        rels_root = None
        rel_map: dict[str, str] = {}
        if "xl/_rels/workbook.xml.rels" in zf.namelist():
            rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            ns_rel = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
            for rel in rels_root.findall("{*}Relationship"):
                rel_map[rel.attrib.get("Id", "")] = rel.attrib.get("Target", "")

        for sheet in workbook_root.findall("a:sheets/a:sheet", ns):
            sheet_name = sheet.attrib.get("name", "Sheet")
            rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            target = rel_map.get(rel_id, "")
            target_path = "xl/" + target if not target.startswith("/") and not target.startswith("xl/") else target
            if target_path.startswith("/"):
                target_path = target_path.lstrip("/")
            if target_path.startswith("xl/"):
                actual_sheet_path = target_path
            else:
                actual_sheet_path = f"xl/{target}"

            try:
                sheet_xml = ET.fromstring(zf.read(actual_sheet_path))
            except Exception:
                continue

            rows_data: list[dict] = []
            total_rows = 0
            max_cols = 0
            for row in sheet_xml.findall(".//a:sheetData/a:row", ns):
                total_rows += 1
                row_values: list[str] = []
                for cell in row.findall("a:c", ns):
                    cell_ref = cell.attrib.get("r") or ""
                    column_index = 0
                    for ch in cell_ref:
                        if ch.isalpha():
                            column_index = column_index * 26 + (ord(ch.upper()) - 64)
                    if cell_ref:
                        while len(row_values) < column_index:
                            row_values.append("")
                    row_values.append(_xlsx_cell_value(cell, shared_strings))
                if row_values:
                    max_cols = max(max_cols, len(row_values))
                    rows_data.append({"row_index": total_rows, "values": row_values})

            if not rows_data:
                rows_by_sheet.append({
                    "sheet": sheet_name,
                    "rows": 0,
                    "columns": 0,
                    "headers": [],
                    "header_row": None,
                    "header_detection_method": "structural",
                    "header_detection_status": "NOT_APPLICABLE",
                    "records": [],
                })
                continue

            header_row_index = 1
            header_values: list[str] = []
            for row in rows_data:
                cleaned = [v.strip() for v in row["values"] if v is not None]
                if cleaned and any(cleaned):
                    header_values = [str(v).strip() for v in row["values"]]
                    header_row_index = row["row_index"]
                    break

            detected_rows = []
            if header_values:
                for row in rows_data:
                    if row["row_index"] <= header_row_index:
                        continue
                    row_values = row["values"]
                    record: dict[str, str] = {}
                    for idx, header in enumerate(header_values):
                        if idx >= len(row_values):
                            record[header] = ""
                        else:
                            record[header] = row_values[idx]
                    if any(str(v).strip() for v in record.values()):
                        detected_rows.append({
                            "source_row": row["row_index"],
                            "original_record_json": record,
                        })

            rows_by_sheet.append({
                "sheet": sheet_name,
                "rows": total_rows,
                "columns": max_cols,
                "headers": header_values,
                "header_row": header_row_index,
                "header_detection_method": "structural",
                "header_detection_status": "DETECTED" if header_values else "AMBIGUOUS",
                "records": detected_rows,
            })
    return rows_by_sheet


def _extract_csv_records(file_path: str) -> list[dict]:
    rows_by_sheet = []
    with open(file_path, "r", encoding="utf-8-sig", newline="") as fh:
        sample = fh.read(8192)
        fh.seek(0)
        delimiter = _csv_sniffer_delimiter(sample)
        reader = csv.reader(fh, delimiter=delimiter)
        table_rows = list(reader)

    if not table_rows:
        return [{"sheet": "CSV", "rows": 0, "columns": 0, "records": []}]

    header_row = None
    for idx, row in enumerate(table_rows):
        cleaned = [str(v).strip() for v in row]
        if any(cleaned):
            header_row = idx + 1
            header_values = row
            break

    if header_row is None:
        return [{"sheet": "CSV", "rows": len(table_rows), "columns": 0, "records": []}]

    records = []
    for row_index, row in enumerate(table_rows[header_row:], start=header_row + 1):
        if not row or not any(str(v).strip() for v in row):
            continue
        record: dict[str, str] = {}
        for idx, header in enumerate(header_values):
            value = row[idx] if idx < len(row) else ""
            record[str(header).strip()] = value
        if any(str(v).strip() for v in record.values()):
            records.append({"source_row": row_index, "original_record_json": record})

    rows_by_sheet.append({
        "sheet": "CSV",
        "rows": len(table_rows),
        "columns": max(len(r) for r in table_rows),
        "headers": [str(header).strip() for header in header_values],
        "header_row": header_row,
        "header_detection_method": "structural",
        "header_detection_status": "DETECTED",
        "records": records,
    })
    return rows_by_sheet


def _extract_raw_records(file_path: str, file_type: str) -> list[dict]:
    if file_type == "XLSX":
        sheet_entries = _parse_xlsx_file(file_path)
    else:
        sheet_entries = _extract_csv_records(file_path)

    raw_records: list[dict] = []
    total_rows = 0
    for sheet in sheet_entries:
        total_rows += int(sheet.get("rows") or 0)
        for record in sheet.get("records", []):
            raw_records.append({
                "source_sheet": sheet.get("sheet", "Sheet"),
                "source_row": record["source_row"],
                "original_record_json": record["original_record_json"],
                "raw_metadata": {
                    "headers": sheet.get("headers", []),
                    "header_row": sheet.get("header_row"),
                    "header_detection_method": sheet.get("header_detection_method"),
                    "header_detection_status": sheet.get("header_detection_status"),
                    "sheet_rows": sheet.get("rows"),
                    "sheet_columns": sheet.get("columns"),
                },
            })
    return raw_records, total_rows


def _build_import_report(batch_doc: dict, raw_records: list[dict]) -> dict:
    return {
        "import_id": batch_doc["id"],
        "filename": batch_doc["filename"],
        "status": batch_doc["status"],
        "sheets_detected": len({r["source_sheet"] for r in raw_records}) if raw_records else 0,
        "records_detected": batch_doc.get("records_detected", 0),
        "records_extracted": len(raw_records),
        "records_with_errors": batch_doc.get("records_with_errors", 0),
        "records_skipped": batch_doc.get("records_skipped", 0),
    }


def get_import_batch_filter(user: dict, batch_id: Optional[str] = None) -> dict:
    company_id = _safe_company_id(user)
    filters = {"company_id": company_id, "deleted": {"$ne": True}}
    if batch_id:
        filters["id"] = batch_id
    return filters


def get_import_raw_filter(user: dict, batch_id: str) -> dict:
    company_id = _safe_company_id(user)
    return {"company_id": company_id, "import_batch_id": batch_id}


def get_import_bucket_path(company_id: str, filename: str) -> Path:
    directory = IMPORT_STORAGE_ROOT / company_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory / sanitize_filename(filename)


def get_import_file_size(file_path: Path) -> int:
    try:
        return file_path.stat().st_size
    except Exception:
        return 0


def _ensure_import_collection_indexes():
    try:
        if db is None:
            return
        db.import_batches.create_index("company_id")
        db.import_batches.create_index([("company_id", 1), ("created_at", -1)])
        db.import_batches.create_index([("company_id", 1), ("checksum", 1)])
        db.raw_records.create_index("company_id")
        db.raw_records.create_index([("company_id", 1), ("import_batch_id", 1)])
        db.raw_records.create_index([("company_id", 1), ("import_batch_id", 1), ("source_sheet", 1)])
        db.raw_records.create_index([("company_id", 1), ("import_batch_id", 1), ("source_row", 1)])
    except Exception:
        pass


_ensure_import_collection_indexes()


def get_company_trial_status(company: dict) -> dict:
    import math
    if not company or "trial_expires_at" not in company:
        return {
            "days_remaining": 60,
            "is_expired": False,
            "trial_days": 60,
            "trial_started_at": "",
            "trial_expires_at": ""
        }
    try:
        expires_at_str = company["trial_expires_at"].replace("Z", "+00:00")
        expires_at_dt = datetime.fromisoformat(expires_at_str)
    except Exception:
        return {
            "days_remaining": 0,
            "is_expired": True,
            "trial_days": 60,
            "trial_started_at": "",
            "trial_expires_at": ""
        }
    now_dt = datetime.now(expires_at_dt.tzinfo or timezone.utc)
    if now_dt > expires_at_dt:
        return {
            "days_remaining": 0,
            "is_expired": True,
            "trial_days": company.get("trial_days", 60),
            "trial_started_at": company.get("trial_started_at", ""),
            "trial_expires_at": company.get("trial_expires_at", "")
        }
    else:
        diff_sec = (expires_at_dt - now_dt).total_seconds()
        days_remaining = math.ceil(diff_sec / 86400.0)
        days_remaining = max(1, min(60, days_remaining))
        return {
            "days_remaining": days_remaining,
            "is_expired": False,
            "trial_days": company.get("trial_days", 60),
            "trial_started_at": company.get("trial_started_at", ""),
            "trial_expires_at": company.get("trial_expires_at", "")
        }

async def generate_unique_public_code() -> str:
    import random
    import string
    chars = string.ascii_uppercase + string.digits
    while True:
        code = "".join(random.choices(chars, k=6))
        exists = await db.proposals.find_one({"public_code": code})
        if not exists:
            return code

async def verify_trial_not_expired(company_id: str, user_id: str):
    plan_state = await get_user_plan_state(user_id)
    if plan_state["is_pro"]:
        return
    company = await db.companies.find_one({"id": company_id})
    if company:
        trial_status = get_company_trial_status(company)
        if trial_status["is_expired"]:
            proposals_count = await db.proposals.count_documents({"company_id": company_id, "deleted": {"$ne": True}})
            clients_count = await db.clients.count_documents({"company_id": company_id, "deleted": {"$ne": True}})
            negotiations_count = await db.proposals.count_documents({"company_id": company_id, "deleted": {"$ne": True}, "status": "aprovado"})
            raise HTTPException(
                status_code=403,
                detail=(
                    "Seu período de avaliação terminou.\n\n"
                    "Você já gerou:\n"
                    f"* {proposals_count} propostas\n"
                    f"* {clients_count} clientes\n"
                    f"* {negotiations_count} negociações\n\n"
                    "Assine o Plano Pro para continuar utilizando."
                )
            )

async def get_user_plan_state(user_id: str) -> dict:
    """Returns {plan, pro_until, month_count, month_quota, is_pro, is_trial, trial_days, trial_started_at, trial_expires_at, trial_days_remaining, trial_is_expired, trial_stats}."""
    user = await db.users.find_one({"id": user_id})
    company_id = user.get("company_id") if user else None
    
    if not company_id and user:
        comp = await db.companies.find_one({"user_id": user_id})
        if comp:
            company_id = comp.get("id")
            
    company = await db.companies.find_one({"id": company_id}) if company_id else None
    trial_status = get_company_trial_status(company)
    
    proposals_count = 0
    clients_count = 0
    negotiations_count = 0
    if company_id:
        proposals_count = await db.proposals.count_documents({"company_id": company_id, "deleted": {"$ne": True}})
        clients_count = await db.clients.count_documents({"company_id": company_id, "deleted": {"$ne": True}})
        negotiations_count = await db.proposals.count_documents({"company_id": company_id, "deleted": {"$ne": True}, "status": "aprovado"})
        
    trial_stats = {
        "proposals_count": proposals_count,
        "clients_count": clients_count,
        "negotiations_count": negotiations_count
    }
    
    if user and (user.get("founder") or user.get("lifetime")):
        now = datetime.now(timezone.utc)
        month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        if company_id:
            month_count = await db.proposals.count_documents(
                {"company_id": company_id, "deleted": {"$ne": True}, "created_at": {"$gte": month_start.isoformat()}}
            )
        else:
            month_count = await db.proposals.count_documents(
                {"user_id": user_id, "deleted": {"$ne": True}, "created_at": {"$gte": month_start.isoformat()}}
            )
        return {
            "plan": "pro",
            "pro_until": None,
            "month_count": month_count,
            "month_quota": None,
            "is_pro": True,
            "is_trial": False,
            "subscription_status": "active",
            "founder": True,
            "lifetime": True,
            "trial_days": None,
            "trial_started_at": None,
            "trial_expires_at": None,
            "trial_days_remaining": None,
            "trial_is_expired": False,
            "trial_stats": trial_stats
        }
        
    # Resolve owner_id for fallback
    owner_id = user_id
    if company_id:
        if company and company.get("user_id"):
            owner_id = company["user_id"]
            
    sub = None
    if company_id:
        sub = await db.subscriptions.find_one({"company_id": company_id}, {"_id": 0})
    if not sub:
        sub = await db.subscriptions.find_one({"user_id": owner_id}, {"_id": 0})
        
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    
    if company_id:
        month_count = await db.proposals.count_documents(
            {"company_id": company_id, "deleted": {"$ne": True}, "created_at": {"$gte": month_start.isoformat()}}
        )
    else:
        month_count = await db.proposals.count_documents(
            {"user_id": user_id, "deleted": {"$ne": True}, "created_at": {"$gte": month_start.isoformat()}}
        )
        
    is_pro = False
    is_trial = False
    pro_until = None
    if sub and sub.get("pro_until"):
        try:
            pu = datetime.fromisoformat(sub["pro_until"])
            if pu > now:
                is_pro = True
                pro_until = sub["pro_until"]
                if sub.get("last_plan_id") == "trial":
                    is_trial = True
        except Exception:
            pass
            
    return {
        "plan": "pro" if is_pro else "free",
        "pro_until": pro_until,
        "month_count": month_count,
        "month_quota": None,
        "is_pro": is_pro,
        "is_trial": is_trial,
        "subscription_status": "active" if is_pro else "inactive",
        "trial_days": trial_status["trial_days"],
        "trial_started_at": trial_status["trial_started_at"],
        "trial_expires_at": trial_status["trial_expires_at"],
        "trial_days_remaining": trial_status["days_remaining"],
        "trial_is_expired": trial_status["is_expired"],
        "trial_stats": trial_stats
    }


async def get_company_id(user_id: str) -> str | None:
    """Return the company.id for the given user_id, generating it if missing."""
    company = await db.companies.find_one({"user_id": user_id}, {"_id": 0})
    if not company:
        return None
    if not company.get("id"):
        company_id = str(uuid.uuid4())
        await db.companies.update_one(
            {"user_id": user_id},
            {"$set": {"id": company_id}},
        )
        return company_id
    return company["id"]


async def ensure_company_ids() -> None:
    """Backfill missing company ids for existing company documents."""
    print("START ensure_company_ids")
    cursor = db.companies.find({"id": {"$exists": False}}, {"_id": 0, "user_id": 1})
    async for doc in cursor:
        if not doc.get("user_id"):
            continue
        print("Company without id:", doc["user_id"])
        generated_id = str(uuid.uuid4())
        print("Generated company id:", generated_id)
        await db.companies.update_one(
            {"user_id": doc["user_id"]},
            {"$set": {"id": generated_id}},
        )
    print("END ensure_company_ids")


async def ensure_company_trials() -> None:
    """Backfill missing trial fields for existing company documents."""
    print("START ensure_company_trials")
    cursor = db.companies.find({"trial_expires_at": {"$exists": False}})
    async for company in cursor:
        user_id = company.get("user_id")
        user_created_at = None
        if user_id:
            user = await db.users.find_one({"id": user_id})
            if user:
                user_created_at = user.get("created_at")
        
        started_at = user_created_at or company.get("created_at") or datetime.now(timezone.utc).isoformat()
        try:
            started_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        except Exception:
            started_dt = datetime.now(timezone.utc)
            started_at = started_dt.isoformat()
            
        expires_dt = started_dt + timedelta(days=60)
        
        await db.companies.update_one(
            {"_id": company["_id"]},
            {"$set": {
                "trial_days": 60,
                "trial_started_at": started_at,
                "trial_expires_at": expires_dt.isoformat()
            }}
        )
        print(f"Backfilled trial for company: {company.get('id') or user_id}")
    print("END ensure_company_trials")


async def get_scope_filter(user: dict) -> dict:
    """Return scope filter based on user's company_id or user_id.
    
    Args:
        user: User document with 'id' and optional 'company_id'
    
    Returns:
        dict: {"company_id": company_id} or {"user_id": user_id}
    """
    if user.get("company_id"):
        return {"company_id": user["company_id"]}
    return {"user_id": user["id"]}


async def resolve_client_id(
    company_id: str,
    name: str,
    document: str,
    phone: str,
    user_id: str | None = None,
    email: str = "",
    company: str = "",
    city: str = "",
    state: str = "",
    address: str = ""
) -> str:
    # Restringe a busca por company_id e document
    client_doc = await db.clients.find_one({"company_id": company_id, "document": document})
    now = datetime.now(timezone.utc).isoformat()
    if client_doc:
        # If client doc exists, update its fields with any non-empty values
        update_fields = {}
        if name and name != client_doc.get("name"):
            update_fields["name"] = name
        if phone and phone != client_doc.get("phone"):
            update_fields["phone"] = phone
        if email and email != client_doc.get("email"):
            update_fields["email"] = email
        if company and company != client_doc.get("company"):
            update_fields["company"] = company
        if city and city != client_doc.get("city"):
            update_fields["city"] = city
        if state and state != client_doc.get("state"):
            update_fields["state"] = state
        if address and address != client_doc.get("address"):
            update_fields["address"] = address
        if client_doc.get("deleted") is True:
            update_fields["deleted"] = False
            
        if update_fields:
            update_fields["updated_at"] = now
            await db.clients.update_one({"id": client_doc["id"]}, {"$set": update_fields})
            reactivated = await db.clients.find_one({"id": client_doc["id"]})
            await log_audit(
                action="update",
                entity_type="client",
                entity_id=client_doc["id"],
                old_value=client_doc,
                new_value=reactivated,
                user_id=user_id,
                company_id=company_id
            )
        return client_doc["id"]
    
    # Se não existir, criar automaticamente
    if user_id:
        await verify_trial_not_expired(company_id, user_id)
    client_id = f"cli_{uuid.uuid4().hex[:16]}"
    new_client = {
        "id": client_id,
        "company_id": company_id,
        "name": name,
        "document": document,
        "phone": phone,
        "email": email,
        "company": company,
        "city": city,
        "state": state,
        "address": address,
        "created_at": now,
        "updated_at": now,
        "deleted": False
    }
    await db.clients.insert_one(new_client)
    
    # Audit log creation!
    await log_audit(
        action="create",
        entity_type="client",
        entity_id=client_id,
        old_value=None,
        new_value=new_client,
        user_id=user_id,
        company_id=company_id
    )
    return client_id


async def _push_opportunity_timeline(opportunity_id: str, event_type: str, description: str, user_id: str | None = None, metadata: dict | None = None):
    now = datetime.now(timezone.utc).isoformat()
    ev = {
        "id": str(uuid.uuid4()),
        "event_type": event_type,
        "description": description,
        "user_id": user_id or "",
        "created_at": now,
        "metadata": metadata or {}
    }
    await db.opportunities.update_one({"id": opportunity_id}, {"$push": {"timeline": ev}, "$set": {"updated_at": now}})
    return ev


def normalize_proposal_items(products: List[dict]) -> List[dict]:
    normalized = []
    for item in products:
        item_copy = dict(item)
        if "item_type" not in item_copy:
            if item_copy.get("product_id"):
                item_copy["item_type"] = "catalog"
            else:
                item_copy["item_type"] = "manual"
        normalized.append(item_copy)
    return normalized


def normalize_proposal(p: dict) -> dict:
    if not p:
        return p
    # Normalize status: realizado -> aprovado
    if p.get("status") == "realizado":
        p["status"] = "aprovado"
    # Ensure status_updated_at exists
    if "status_updated_at" not in p:
        p["status_updated_at"] = p.get("updated_at") or p.get("created_at") or ""
    # Ensure client_id exists
    if "client_id" not in p:
        p["client_id"] = ""
    # Normalize items to have item_type
    if "products" in p:
        p["products"] = normalize_proposal_items(p["products"])
    # Ensure seller snapshot fields exist
    p["seller_name"] = p.get("seller_name") or ""
    p["seller_email"] = p.get("seller_email") or ""
    p["seller_phone"] = p.get("seller_phone") or ""
    p["seller_whatsapp"] = p.get("seller_whatsapp") or ""
    p["seller_role"] = p.get("seller_role") or ""
    p["seller_signature"] = p.get("seller_signature") or ""
    # Ensure code and view tracking fields exist
    p["public_code"] = p.get("public_code") or ""
    p["proposal_viewed_at"] = p.get("proposal_viewed_at") or ""
    p["proposal_viewed_ip"] = p.get("proposal_viewed_ip") or ""
    p["proposal_viewed_ua"] = p.get("proposal_viewed_ua") or ""
    # Ensure acceptance fields exist
    p["acceptance_status"] = p.get("acceptance_status") or "pending"
    p["accept_name"] = p.get("accept_name") or ""
    p["accept_document"] = p.get("accept_document") or ""
    p["accept_role"] = p.get("accept_role") or ""
    p["accept_date"] = p.get("accept_date") or ""
    p["accept_ip"] = p.get("accept_ip") or ""
    p["accept_device"] = p.get("accept_device") or ""
    # Sprint 6 fields
    p["timeline"] = p.get("timeline") or []
    p["next_action_date"] = p.get("next_action_date") or None
    p["next_action_description"] = p.get("next_action_description") or ""
    p["temperature"] = p.get("temperature") or "morna"
    # Sprint 7 fields
    p["shipping_type"] = p.get("shipping_type") or ""
    p["shipping_responsible"] = p.get("shipping_responsible") or ""
    p["shipping_company"] = p.get("shipping_company") or ""
    p["manufacturing_days"] = p.get("manufacturing_days") or ""
    p["delivery_days"] = p.get("delivery_days") or ""
    p["warranty"] = p.get("warranty") or ""
    p["delivery_place"] = p.get("delivery_place") or ""
    p["incoterm"] = p.get("incoterm") or ""
    p["currency"] = p.get("currency") or "BRL"
    p["commercial_conditions"] = p.get("commercial_conditions") or ""
    p["internal_notes"] = p.get("internal_notes") or ""
    # Hotfix Beta 02 fields
    p["client_company"] = p.get("client_company") or ""
    p["client_email"] = p.get("client_email") or ""
    p["client_city"] = p.get("client_city") or ""
    p["client_state"] = p.get("client_state") or ""
    p["client_address"] = p.get("client_address") or ""
    return p


def get_role_label(role: str) -> str:
    if role == "owner":
        return "Proprietário"
    elif role == "admin":
        return "Administrador"
    elif role == "seller":
        return "Consultor Comercial"
    return role or ""


# ---------- Models ----------
class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6)
    referral_code: Optional[str] = None


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str = Field(min_length=6)


class SendVerificationIn(BaseModel):
    email: EmailStr


class VerifyEmailIn(BaseModel):
    token: str


class ClientIn(BaseModel):
    name: str
    document: str
    phone: str
    email: Optional[str] = ""
    company: Optional[str] = ""
    city: Optional[str] = ""
    state: Optional[str] = ""
    address: Optional[str] = ""


class ClientUpdateIn(BaseModel):
    name: Optional[str] = None
    document: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    address: Optional[str] = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class AuthOut(BaseModel):
    token: str
    user: dict


class CompanyIn(BaseModel):
    company_name: Optional[str] = ""
    cnpj: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    address: Optional[str] = ""
    logo_base64: Optional[str] = ""
    default_payment_terms: Optional[str] = ""
    default_shipping_type: Optional[str] = ""
    default_shipping_responsible: Optional[str] = ""
    default_shipping_company: Optional[str] = ""
    default_manufacturing_days: Optional[str] = ""
    default_delivery_days: Optional[str] = ""
    default_warranty: Optional[str] = ""
    default_validity_days: Optional[int] = 15
    default_incoterm: Optional[str] = ""
    default_currency: Optional[str] = "BRL"
    default_commercial_conditions: Optional[str] = ""

class CommercialTemplateIn(BaseModel):
    name: str
    is_default: Optional[bool] = False
    payment_terms: Optional[str] = ""
    shipping_type: Optional[str] = ""
    shipping_responsible: Optional[str] = ""
    shipping_company: Optional[str] = ""
    manufacturing_days: Optional[str] = ""
    delivery_days: Optional[str] = ""
    warranty: Optional[str] = ""
    validity_days: Optional[int] = 15
    incoterm: Optional[str] = ""
    currency: Optional[str] = "BRL"
    commercial_conditions: Optional[str] = ""
    internal_notes: Optional[str] = ""


class ProposalItemIn(BaseModel):
    product_id: Optional[str] = None
    quantity: float
    name: Optional[str] = None
    unit_price: Optional[float] = None
    price: Optional[float] = None  # legacy fallback
    description: Optional[str] = ""
    unit: Optional[str] = "UN"


class CatalogProductIn(BaseModel):
    code: str
    name: str
    description: Optional[str] = ""
    price: float
    unit: str = "UN"


class CatalogProductUpdateIn(BaseModel):
    code: str
    name: str
    description: Optional[str] = ""
    price: float
    unit: str = "UN"
    active: bool = True


class CatalogProductOut(BaseModel):
    id: str
    company_id: str
    code: str
    name: str
    description: str
    price: float
    unit: str
    active: bool
    created_at: str


class TimelineEntry(BaseModel):
    id: str
    type: str
    description: str
    created_at: str
    created_by: str
    next_action_date: Optional[str] = None
    next_action_description: Optional[str] = ""


class TimelineInput(BaseModel):
    type: str
    description: str
    next_action_date: Optional[str] = None
    next_action_description: Optional[str] = ""
    temperature: Optional[str] = None


ProposalStatus = Literal["aberto", "qualificado", "negociacao", "aprovado", "perdido", "realizado"]


class ProposalIn(BaseModel):
    client_name: str
    client_document: str
    client_phone: str
    client_email: Optional[str] = ""
    client_company: Optional[str] = ""
    client_city: Optional[str] = ""
    client_state: Optional[str] = ""
    client_address: Optional[str] = ""
    client_id: Optional[str] = ""
    products: List[ProposalItemIn]
    shipping_deadline: str
    notes: Optional[str] = ""
    discount: Optional[float] = 0.0
    payment_terms: Optional[str] = ""
    validity_days: Optional[int] = 15
    images: Optional[List[str]] = []
    temperature: Optional[str] = "morna"
    shipping_type: Optional[str] = ""
    shipping_responsible: Optional[str] = ""
    shipping_company: Optional[str] = ""
    manufacturing_days: Optional[str] = ""
    delivery_days: Optional[str] = ""
    warranty: Optional[str] = ""
    delivery_place: Optional[str] = ""
    incoterm: Optional[str] = ""
    currency: Optional[str] = "BRL"
    commercial_conditions: Optional[str] = ""
    internal_notes: Optional[str] = ""


OPPORTUNITY_STAGE = Literal[
    "NOVO",
    "PROPOSTA_ENVIADA",
    "FOLLOWUP_1",
    "FOLLOWUP_2",
    "FOLLOWUP_3",
    "NEGOCIACAO",
    "AGUARDANDO_CLIENTE",
    "AGUARDANDO_APROVACAO",
    "ALTA_INTENCAO",
    "VENDA_GANHA",
    "VENDA_PERDIDA",
    "SEM_MOMENTO",
    "SEM_RETORNO",
    "CANCELADA",
    "HUMANO",
]

OPPORTUNITY_STATUS = Literal[
    "OPEN",
    "WAITING",
    "HUMAN_ACTION",
    "WON",
    "LOST",
    "CANCELLED",
]

OPPORTUNITY_TEMPERATURE = Literal[
    "FRIO",
    "MORNO",
    "QUENTE",
    "MUITO_QUENTE",
]


class OpportunityTimelineEntry(BaseModel):
    id: str
    event_type: str
    description: str
    user_id: str
    created_at: str
    metadata: Optional[dict] = None


class OpportunityIn(BaseModel):
    title: str
    description: Optional[str] = ""
    client_id: Optional[str] = ""
    contact_id: Optional[str] = ""
    proposal_id: Optional[str] = ""
    seller_id: Optional[str] = ""
    proposal_number: Optional[str] = ""
    proposal_date: Optional[str] = ""
    proposal_value: Optional[float] = 0.0
    product_summary: Optional[str] = ""
    products: Optional[List[ProposalItemIn]] = []
    client_name: Optional[str] = ""
    client_document: Optional[str] = ""
    client_phone: Optional[str] = ""
    client_email: Optional[str] = ""
    client_company: Optional[str] = ""
    client_city: Optional[str] = ""
    client_state: Optional[str] = ""
    client_address: Optional[str] = ""
    notes: Optional[str] = ""
    estimated_value: Optional[float] = 0.0
    estimated_close_date: Optional[str] = ""
    next_action_date: Optional[str] = None
    next_action_description: Optional[str] = ""
    stage: Optional[OPPORTUNITY_STAGE] = "NOVO"
    status: Optional[OPPORTUNITY_STATUS] = "OPEN"
    temperature: Optional[OPPORTUNITY_TEMPERATURE] = "MORNO"
    probability: Optional[int] = 0
    last_contact_at: Optional[str] = None
    last_customer_response_at: Optional[str] = None
    next_action_at: Optional[str] = None
    next_action_type: Optional[str] = ""
    next_action_reason: Optional[str] = ""
    customer_intent: Optional[str] = ""
    customer_sentiment: Optional[str] = ""
    objection_type: Optional[str] = ""
    objection_details: Optional[str] = ""
    loss_reason: Optional[str] = ""
    competitor: Optional[str] = ""
    competitor_price: Optional[float] = 0.0
    purchase_timeline: Optional[str] = ""
    decision_maker: Optional[str] = ""
    ai_summary: Optional[str] = ""
    ai_recommendation: Optional[str] = ""
    ai_confidence: Optional[float] = 0.0
    closed_at: Optional[str] = None


class OpportunityUpdateIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    client_id: Optional[str] = None
    contact_id: Optional[str] = None
    proposal_id: Optional[str] = None
    seller_id: Optional[str] = None
    proposal_number: Optional[str] = None
    proposal_date: Optional[str] = None
    proposal_value: Optional[float] = None
    product_summary: Optional[str] = None
    products: Optional[List[ProposalItemIn]] = None
    client_name: Optional[str] = None
    client_document: Optional[str] = None
    client_phone: Optional[str] = None
    client_email: Optional[str] = None
    client_company: Optional[str] = None
    client_city: Optional[str] = None
    client_state: Optional[str] = None
    client_address: Optional[str] = None
    notes: Optional[str] = None
    estimated_value: Optional[float] = None
    estimated_close_date: Optional[str] = None
    next_action_date: Optional[str] = None
    next_action_description: Optional[str] = None
    stage: Optional[OPPORTUNITY_STAGE] = None
    status: Optional[OPPORTUNITY_STATUS] = None
    temperature: Optional[OPPORTUNITY_TEMPERATURE] = None
    probability: Optional[int] = None
    last_contact_at: Optional[str] = None
    last_customer_response_at: Optional[str] = None
    next_action_at: Optional[str] = None
    next_action_type: Optional[str] = None
    next_action_reason: Optional[str] = None
    customer_intent: Optional[str] = None
    customer_sentiment: Optional[str] = None
    objection_type: Optional[str] = None
    objection_details: Optional[str] = None
    loss_reason: Optional[str] = None
    competitor: Optional[str] = None
    competitor_price: Optional[float] = None
    purchase_timeline: Optional[str] = None
    decision_maker: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_recommendation: Optional[str] = None
    ai_confidence: Optional[float] = None
    closed_at: Optional[str] = None


class OpportunityOut(BaseModel):
    id: str
    company_id: str
    title: str
    description: str
    client_id: str
    contact_id: str
    proposal_id: str
    seller_id: str
    seller_name: str
    seller_email: str
    proposal_number: str
    proposal_date: str
    proposal_value: float
    product_summary: str
    stage: str
    status: str
    temperature: str
    probability: int
    last_contact_at: Optional[str] = None
    last_customer_response_at: Optional[str] = None
    next_action_at: Optional[str] = None
    next_action_type: str = ""
    next_action_reason: str = ""
    customer_intent: str = ""
    customer_sentiment: str = ""
    objection_type: str = ""
    objection_details: str = ""
    loss_reason: str = ""
    competitor: str = ""
    competitor_price: float = 0.0
    purchase_timeline: str = ""
    decision_maker: str = ""
    ai_summary: str = ""
    ai_recommendation: str = ""
    ai_confidence: float = 0.0
    created_at: str
    updated_at: str
    closed_at: Optional[str] = None
    timeline: List[OpportunityTimelineEntry]


class OpportunityStatusUpdate(BaseModel):
    status: OPPORTUNITY_STATUS
    lost_reason: Optional[str] = None


class OpportunityStageUpdate(BaseModel):
    stage: OPPORTUNITY_STAGE


class OpportunityTemperatureUpdate(BaseModel):
    temperature: OPPORTUNITY_TEMPERATURE


class StatusUpdate(BaseModel):
    status: ProposalStatus
    lost_reason: Optional[str] = None


class CheckoutIn(BaseModel):
    plan: str  # pro_monthly | pro_yearly


TRIAL_DAYS = 60
REFERRAL_REWARD_DAYS = 30


def make_referral_code(user_id: str) -> str:
    """Short, readable referral code from user_id."""
    return user_id.replace("-", "")[:8].upper()


# ---------- Startup ----------
@app.on_event("startup")
async def on_startup():
    ensure_db_for_current_loop()
    await ensure_indexes(db)
    # Migrate existing users
    await db.users.update_many(
        {"verified_email": {"$exists": False}},
        {"$set": {
            "verified_email": True,
            "verification_sent_at": None,
            "verification_token": None,
            "last_login_at": None,
            "last_activity_at": None,
            "session_id": None,
            "deleted": False
        }}
    )

    await ensure_company_ids()
    await ensure_company_trials()


@app.on_event("shutdown")
async def on_shutdown():
    # Do not close the shared Mongo client here: it is created at module scope and
    # reused across requests/tests. Closing it in shutdown breaks subsequent
    # requests when the event loop has already changed or closed.
    pass


# ---------- Auth routes ----------
@api_router.post("/auth/register", response_model=AuthOut)
async def register(data: RegisterIn, request: Request):
    email = data.email.lower().strip()
    
    # Rate limit: 10 per hour
    await check_rate_limit(action="register", identifier=email, limit=10, window_seconds=3600, request=request)
    
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email já cadastrado")
        
    user_id = str(uuid.uuid4())
    referral_code = make_referral_code(user_id)
    now = datetime.now(timezone.utc)
    session_id = str(uuid.uuid4())
    
    # Generate verification fields
    verification_token = str(uuid.uuid4())
    verification_sent_at = now.isoformat()

    referred_by = None
    if data.referral_code:
        ref_user = await db.users.find_one({"referral_code": data.referral_code.upper().strip()})
        if ref_user and ref_user["id"] != user_id:
            referred_by = ref_user["id"]

    # Step 1: Create user
    doc = {
        "id": user_id,
        "email": email,
        "name": data.name,
        "password_hash": hash_password(data.password),
        "referral_code": referral_code,
        "referred_by": referred_by,
        "created_at": now.isoformat(),
        "verified_email": False,
        "verification_token": verification_token,
        "verification_sent_at": verification_sent_at,
        "session_id": session_id,
        "last_login_at": now.isoformat(),
        "last_activity_at": now.isoformat(),
        "deleted": False,
        "active": True
    }
    await db.users.insert_one(doc)

    # Step 2: Initialize empty company profile
    await db.companies.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {
            "user_id": user_id,
            "company_name": "",
            "cnpj": "",
            "phone": "",
            "email": email,
            "address": "",
            "logo_base64": "",
            "trial_days": 60,
            "trial_started_at": now.isoformat(),
            "trial_expires_at": (now + timedelta(days=60)).isoformat(),
        }},
        upsert=True,
    )

    # Step 3: Get or create company.id
    company_id = await get_company_id(user_id)

    # Step 4: Update user with company_id and role
    if company_id:
        await db.users.update_one(
            {"id": user_id},
            {"$set": {"company_id": company_id, "role": "owner"}},
        )
        doc["company_id"] = company_id
        doc["role"] = "owner"

    # Grant 7-day Pro trial automatically
    trial_until = now + timedelta(days=TRIAL_DAYS)
    await db.subscriptions.insert_one({
        "user_id": user_id,
        "company_id": company_id,
        "plan": "pro",
        "last_plan_id": "trial",
        "pro_until": trial_until.isoformat(),
        "trial_used": True,
        "updated_at": now.isoformat(),
    })

    # Log to audit (register)
    await log_audit(
        action="register",
        entity_type="auth",
        entity_id=user_id,
        old_value=None,
        new_value=doc,
        user_id=user_id,
        company_id=company_id
    )

    token = create_access_token(user_id, email, session_id=session_id)
    return {"token": token, "user": {"id": user_id, "email": email, "name": data.name}}


@api_router.post("/auth/login", response_model=AuthOut)
async def login(data: LoginIn, request: Request):
    email = data.email.lower().strip()
    
    # Rate limit: 5 attempts per minute
    await check_rate_limit(action="login", identifier=email, limit=5, window_seconds=60, request=request)
    
    user = await db.users.find_one({"email": email})
    if not user or user.get("deleted") is True:
        raise HTTPException(status_code=401, detail="Email ou senha inválidos")
        
    if not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email ou senha inválidos")
        
    # Check if active
    if not user.get("active", True):
        raise HTTPException(status_code=403, detail="Usuário desativado")
        
    session_id = user.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        
    now = datetime.now(timezone.utc).isoformat()
    
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "session_id": session_id,
            "last_login_at": now,
            "last_activity_at": now
        }}
    )
    
    # Audit log login
    await log_audit(
        action="login",
        entity_type="auth",
        entity_id=user["id"],
        old_value=None,
        new_value={"session_id": session_id, "last_login_at": now},
        user_id=user["id"],
        company_id=user.get("company_id")
    )
    
    token = create_access_token(user["id"], email, session_id=session_id)
    return {
        "token": token,
        "user": {"id": user["id"], "email": email, "name": user["name"]},
    }


@api_router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    plan_state = await get_user_plan_state(user["id"])
    res = {**user, **plan_state}
    res.pop("password_hash", None)
    res.pop("verification_token", None)
    res.pop("password_reset_token", None)
    return res


# ---------- Company profile ----------
@api_router.get("/company")
async def get_company(user=Depends(get_current_user)):
    doc = await db.companies.find_one({"id": user["company_id"]}, {"_id": 0})
    if not doc:
        doc = await db.companies.find_one({"user_id": user["id"]}, {"_id": 0})
    if not doc:
        return {
            "id": user["company_id"],
            "user_id": user["id"],
            "company_name": "",
            "cnpj": "",
            "phone": "",
            "email": user.get("email", ""),
            "address": "",
            "logo_base64": "",
        }
    return doc


@api_router.put("/company")
async def update_company(data: CompanyIn, user=Depends(require_admin)):
    payload = data.dict()
    payload["id"] = user["company_id"]
    await db.companies.update_one(
        {"id": user["company_id"]}, {"$set": payload}, upsert=True
    )
    doc = await db.companies.find_one({"id": user["company_id"]}, {"_id": 0})
    return doc

# Helper function to ensure default commercial template exists
async def ensure_default_template(company_id: str):
    existing = await db.commercial_templates.find_one({"company_id": company_id, "deleted": {"$ne": True}})
    if not existing:
        tid = f"tpl_{uuid.uuid4().hex[:16]}"
        now = datetime.now(timezone.utc).isoformat()
        company = await db.companies.find_one({"id": company_id}) or {}
        tpl = {
            "id": tid,
            "company_id": company_id,
            "name": "Condições Comerciais Padrão",
            "is_default": True,
            "payment_terms": company.get("default_payment_terms") or "",
            "shipping_type": company.get("default_shipping_type") or "",
            "shipping_responsible": company.get("default_shipping_responsible") or "",
            "shipping_company": company.get("default_shipping_company") or "",
            "manufacturing_days": company.get("default_manufacturing_days") or "",
            "delivery_days": company.get("default_delivery_days") or "",
            "warranty": company.get("default_warranty") or "",
            "validity_days": company.get("default_validity_days") or 15,
            "incoterm": company.get("default_incoterm") or "",
            "currency": company.get("default_currency") or "BRL",
            "commercial_conditions": company.get("default_commercial_conditions") or "",
            "internal_notes": "",
            "created_at": now,
            "updated_at": now,
            "deleted": False
        }
        await db.commercial_templates.insert_one(tpl)

# ---------- Commercial Templates CRUD ----------

@api_router.get("/commercial-templates")
async def list_templates(user=Depends(get_current_user)):
    company_id = user.get("company_id")
    if not company_id:
        return []
    await ensure_default_template(company_id)
    cursor = db.commercial_templates.find({"company_id": company_id, "deleted": {"$ne": True}}, {"_id": 0})
    templates = []
    async for doc in cursor:
        templates.append(doc)
    return templates


@api_router.post("/commercial-templates")
async def create_template(data: CommercialTemplateIn, user=Depends(require_admin)):
    company_id = user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="Usuário sem empresa associada")
        
    tid = f"tpl_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc).isoformat()
    
    payload = data.dict()
    payload["id"] = tid
    payload["company_id"] = company_id
    payload["created_at"] = now
    payload["updated_at"] = now
    payload["deleted"] = False
    
    if payload.get("is_default"):
        await db.commercial_templates.update_many(
            {"company_id": company_id},
            {"$set": {"is_default": False}}
        )
        
    await db.commercial_templates.insert_one(payload)
    doc = await db.commercial_templates.find_one({"id": tid}, {"_id": 0})
    return doc


@api_router.put("/commercial-templates/{tid}")
async def update_template(tid: str, data: CommercialTemplateIn, user=Depends(require_admin)):
    company_id = user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="Usuário sem empresa associada")
        
    orig = await db.commercial_templates.find_one({"id": tid, "company_id": company_id, "deleted": {"$ne": True}})
    if not orig:
        raise HTTPException(status_code=404, detail="Template não encontrado")
        
    payload = data.dict()
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    if payload.get("is_default"):
        await db.commercial_templates.update_many(
            {"company_id": company_id},
            {"$set": {"is_default": False}}
        )
        
    await db.commercial_templates.update_one(
        {"id": tid, "company_id": company_id},
        {"$set": payload}
    )
    doc = await db.commercial_templates.find_one({"id": tid}, {"_id": 0})
    return doc


@api_router.delete("/commercial-templates/{tid}")
async def delete_template(tid: str, user=Depends(require_admin)):
    company_id = user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="Usuário sem empresa associada")
        
    orig = await db.commercial_templates.find_one({"id": tid, "company_id": company_id, "deleted": {"$ne": True}})
    if not orig:
        raise HTTPException(status_code=404, detail="Template não encontrado")
        
    await db.commercial_templates.update_one(
        {"id": tid, "company_id": company_id},
        {"$set": {"deleted": True, "is_default": False, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if orig.get("is_default"):
        other = await db.commercial_templates.find_one({"company_id": company_id, "deleted": {"$ne": True}})
        if other:
            await db.commercial_templates.update_one(
                {"id": other["id"]},
                {"$set": {"is_default": True}}
            )
            
    return {"status": "success"}


@api_router.post("/commercial-templates/{tid}/set-default")
async def set_default_template(tid: str, user=Depends(require_admin)):
    company_id = user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="Usuário sem empresa associada")
        
    orig = await db.commercial_templates.find_one({"id": tid, "company_id": company_id, "deleted": {"$ne": True}})
    if not orig:
        raise HTTPException(status_code=404, detail="Template não encontrado")
        
    await db.commercial_templates.update_many(
        {"company_id": company_id},
        {"$set": {"is_default": False}}
    )
    
    await db.commercial_templates.update_one(
        {"id": tid, "company_id": company_id},
        {"$set": {"is_default": True, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"status": "success"}
    
# ---------- Products Catalog ----------

@api_router.get("/products")
async def list_products(
    search: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
    user=Depends(get_current_user),
):
    import re
    company_id = user.get("company_id")

    if not company_id:
        return []

    # Query: multi-company isolation and returning active + inactive (excluding soft-deleted)
    q = {"company_id": company_id, "deleted": {"$ne": True}}

    if search:
        safe_search = re.escape(search)
        q["$or"] = [
            {"name": {"$regex": safe_search, "$options": "i"}},
            {"code": {"$regex": safe_search, "$options": "i"}}
        ]

    # Sort validation (whitelist)
    ALLOWED_SORTS = {
        "name": "name",
        "price": "price",
        "code": "code"
    }
    if sort_by is not None:
        if sort_by not in ALLOWED_SORTS:
            raise HTTPException(status_code=400, detail="Campo de ordenação inválido")
        sb = ALLOWED_SORTS[sort_by]
    else:
        sb = "name"

    if sort_order is not None:
        if sort_order not in ("asc", "desc"):
            raise HTTPException(status_code=400, detail="Ordem de ordenação inválida")
        ord_val = 1 if sort_order == "asc" else -1
    else:
        ord_val = 1

    # Pagination logic matching Fase 2E-C exactly
    if page is None and page_size is None:
        # legado
        cursor = db.products.find(q, {"_id": 0}).sort(sb, ord_val)
        items = await cursor.to_list(5000)
    elif page is not None and page_size is not None:
        # paginado
        skip = (page - 1) * page_size
        limit = page_size
        cursor = db.products.find(q, {"_id": 0}).sort(sb, ord_val)
        items = await cursor.skip(skip).limit(limit).to_list(limit)
    else:
        raise HTTPException(
            status_code=422,
            detail="Ambos os parâmetros 'page' e 'page_size' devem ser informados."
        )

    return items


@api_router.post("/products")
async def create_product(
    data: CatalogProductIn,
    user=Depends(require_admin),
):
    await verify_trial_not_expired(user["company_id"], user["id"])
    company_id = user.get("company_id")

    if not company_id:
        raise HTTPException(
            status_code=400,
            detail="Empresa não vinculada"
        )

    # Validations
    if not data.code or not data.code.strip():
        raise HTTPException(status_code=422, detail="Código é obrigatório")
    if not data.name or not data.name.strip():
        raise HTTPException(status_code=422, detail="Nome é obrigatório")
    if not data.unit or not data.unit.strip():
        raise HTTPException(status_code=422, detail="Unidade é obrigatória")
    if data.price is None or data.price < 0:
        raise HTTPException(status_code=422, detail="Preço deve ser maior ou igual a zero")

    # Duplicity validation (company_id, code)
    code_upper = data.code.strip().upper()
    existing = await db.products.find_one({"company_id": company_id, "code": code_upper})
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Produto com este código já cadastrado nesta empresa"
        )

    doc = {
        "id": str(uuid.uuid4()),
        "company_id": company_id,
        "code": code_upper,
        "name": data.name.strip(),
        "description": data.description.strip() if data.description else "",
        "price": float(data.price),
        "unit": data.unit.strip().upper(),
        "active": True,
        "deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.products.insert_one(doc)
    doc.pop("_id", None)
    
    # Audit log creation
    await log_audit(
        action="create",
        entity_type="product",
        entity_id=doc["id"],
        old_value=None,
        new_value=doc,
        user_id=user["id"],
        company_id=company_id
    )
    
    return doc


@api_router.get("/products/{product_id}")
async def get_product(
    product_id: str,
    user=Depends(get_current_user),
):
    company_id = user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    doc = await db.products.find_one({"id": product_id, "company_id": company_id, "deleted": {"$ne": True}}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return doc


@api_router.put("/products/{product_id}")
async def update_product(
    product_id: str,
    data: CatalogProductUpdateIn,
    user=Depends(require_admin),
):
    company_id = user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    # Validations
    if not data.code or not data.code.strip():
        raise HTTPException(status_code=422, detail="Código é obrigatório")
    if not data.name or not data.name.strip():
        raise HTTPException(status_code=422, detail="Nome é obrigatório")
    if not data.unit or not data.unit.strip():
        raise HTTPException(status_code=422, detail="Unidade é obrigatória")
    if data.price is None or data.price < 0:
        raise HTTPException(status_code=422, detail="Preço deve ser maior ou igual a zero")

    existing_product = await db.products.find_one({"id": product_id, "company_id": company_id, "deleted": {"$ne": True}})
    if not existing_product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    code_upper = data.code.strip().upper()
    if code_upper != existing_product.get("code"):
        # Duplicity validation
        code_exists = await db.products.find_one({"company_id": company_id, "code": code_upper})
        if code_exists:
            raise HTTPException(
                status_code=409,
                detail="Código já cadastrado para outro produto"
            )

    update = {
        "code": code_upper,
        "name": data.name.strip(),
        "description": data.description.strip() if data.description else "",
        "price": float(data.price),
        "unit": data.unit.strip().upper(),
        "active": data.active
    }
    await db.products.update_one({"id": product_id, "company_id": company_id}, {"$set": update})
    
    updated_doc = await db.products.find_one({"id": product_id, "company_id": company_id}, {"_id": 0})
    
    # Audit log update
    await log_audit(
        action="update",
        entity_type="product",
        entity_id=product_id,
        old_value=existing_product,
        new_value=updated_doc,
        user_id=user["id"],
        company_id=company_id
    )
    
    return updated_doc


@api_router.delete("/products/{product_id}")
async def delete_product(
    product_id: str,
    user=Depends(require_admin),
):
    company_id = user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    existing_product = await db.products.find_one({"id": product_id, "company_id": company_id, "deleted": {"$ne": True}})
    if not existing_product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    now = datetime.now(timezone.utc).isoformat()
    await db.products.update_one(
        {"id": product_id, "company_id": company_id},
        {"$set": {
            "deleted": True,
            "active": False,
            "deleted_at": now,
            "deleted_by": user["id"]
        }}
    )
    
    updated_prod = await db.products.find_one({"id": product_id, "company_id": company_id})
    
    # Audit log deletion
    await log_audit(
        action="delete",
        entity_type="product",
        entity_id=product_id,
        old_value=existing_product,
        new_value=updated_prod,
        user_id=user["id"],
        company_id=company_id
    )
    
    return {"ok": True}    


# ---------- Proposals ----------
def _proposal_total(products: List[dict], discount: float = 0.0) -> float:
    subtotal = sum((p.get("quantity", 0) or 0) * (p.get("price", 0) or 0) for p in products)
    return round(max(subtotal - (discount or 0), 0), 2)


@api_router.post("/proposals")
async def create_proposal(data: ProposalIn, user=Depends(get_current_user)):
    await verify_trial_not_expired(user["company_id"], user["id"])


    resolved_products = []
    subtotal = 0.0
    for item in data.products:
        if item.product_id and item.product_id.strip():
            p_doc = await db.products.find_one({
                "id": item.product_id,
                "company_id": user["company_id"],
                "active": True,
                "deleted": {"$ne": True}
            })
            if not p_doc:
                raise HTTPException(status_code=404, detail="Produto não encontrado")
            
            item_total = round(item.quantity * p_doc["price"], 2)
            subtotal += item_total
            resolved_products.append({
                "product_id": item.product_id,
                "code": p_doc["code"],
                "name": p_doc["name"],
                "description": p_doc.get("description", ""),
                "unit": p_doc.get("unit", "UN"),
                "quantity": item.quantity,
                "unit_price": p_doc["price"],
                "total": item_total,
                "item_type": "catalog"
            })
        else:
            resolved_unit_price = item.unit_price if item.unit_price is not None else item.price
            if not item.name or not item.name.strip() or resolved_unit_price is None or item.quantity is None:
                raise HTTPException(status_code=422, detail="Item manual requer name, unit_price e quantity")
            
            item_total = round(item.quantity * resolved_unit_price, 2)
            subtotal += item_total
            resolved_products.append({
                "product_id": "",
                "code": "",
                "name": item.name.strip(),
                "description": item.description or "",
                "unit": item.unit or "UN",
                "quantity": item.quantity,
                "unit_price": resolved_unit_price,
                "total": item_total,
                "item_type": "manual"
            })

    subtotal = round(subtotal, 2)
    discount = float(data.discount or 0.0)
    grand_total = round(max(subtotal - discount, 0.0), 2)

    # Resolve client_id
    client_id = await resolve_client_id(
        company_id=user["company_id"],
        name=data.client_name,
        document=data.client_document,
        phone=data.client_phone,
        user_id=user["id"],
        email=data.client_email or "",
        company=data.client_company or "",
        city=data.client_city or "",
        state=data.client_state or "",
        address=data.client_address or ""
    )

    pid = str(uuid.uuid4())
    public_code = await generate_unique_public_code()
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": pid,
        "public_code": public_code,
        "user_id": user["id"],
        "company_id": user["company_id"],
        "seller_name": user.get("name") or "",  # Historical snapshot of seller name
        "seller_email": user.get("email") or "",
        "seller_phone": user.get("phone") or "",
        "seller_whatsapp": user.get("whatsapp") or "",
        "seller_role": user.get("role") or "owner",
        "seller_signature": user.get("signature_url") or user.get("seller_signature") or "",
        "client_id": client_id,
        "client_name": data.client_name,
        "client_document": data.client_document,
        "client_phone": data.client_phone,
        "client_email": data.client_email or "",
        "client_company": data.client_company or "",
        "client_city": data.client_city or "",
        "client_state": data.client_state or "",
        "client_address": data.client_address or "",
        "products": resolved_products,
        "shipping_deadline": data.shipping_deadline,
        "notes": data.notes or "",
        "discount": discount,
        "subtotal": subtotal,
        "grand_total": grand_total,
        "total": grand_total,
        "payment_terms": data.payment_terms or "",
        "validity_days": int(data.validity_days or 15),
        "images": data.images or [],
        "status": "aberto",
        "status_updated_at": now,
        "lost_reason": "",
        "acceptance_status": "pending",
        "accept_name": "",
        "accept_document": "",
        "accept_role": "",
        "accept_date": "",
        "accept_ip": "",
        "accept_device": "",
        "created_at": now,
        "updated_at": now,
        "last_reminded_at": None,
        "deleted": False,
        "temperature": data.temperature or "morna",
        "next_action_date": None,
        "next_action_description": "",
        "shipping_type": data.shipping_type or "",
        "shipping_responsible": data.shipping_responsible or "",
        "shipping_company": data.shipping_company or "",
        "manufacturing_days": data.manufacturing_days or "",
        "delivery_days": data.delivery_days or "",
        "warranty": data.warranty or "",
        "delivery_place": data.delivery_place or "",
        "incoterm": data.incoterm or "",
        "currency": data.currency or "BRL",
        "commercial_conditions": data.commercial_conditions or "",
        "internal_notes": data.internal_notes or "",
        "timeline": [
            {
                "id": str(uuid.uuid4()),
                "type": "created",
                "description": "Proposta criada.",
                "created_at": now,
                "created_by": user["id"],
                "next_action_date": None,
                "next_action_description": ""
            },
            {
                "id": str(uuid.uuid4()),
                "type": "sent",
                "description": "📤 Proposta enviada.",
                "created_at": now,
                "created_by": user["id"],
                "next_action_date": None,
                "next_action_description": ""
            }
        ]
    }
    await db.proposals.insert_one(doc)
    doc.pop("_id", None)
    
    # Audit log creation
    await log_audit(
        action="create",
        entity_type="proposal",
        entity_id=pid,
        old_value=None,
        new_value=doc,
        user_id=user["id"],
        company_id=user["company_id"]
    )
    
    return normalize_proposal(doc)


@api_router.get("/proposals")
async def list_proposals(
    status: Optional[str] = None,
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
    scope: Optional[str] = None,
    seller_id: Optional[str] = None,
    seller_name: Optional[str] = None,
    search: Optional[str] = None,
    user=Depends(get_current_user),
):
    role = user.get("role", "owner")
    if role == "seller":
        permission_filter = {"company_id": user["company_id"], "user_id": user["id"]}
    else:
        if scope in ("meu_time", "team"):
            permission_filter = {
                "company_id": user["company_id"],
                "user_id": {"$ne": user["id"]}
            }
        elif scope == "vendedor" and seller_id:
            permission_filter = {
                "company_id": user["company_id"],
                "user_id": seller_id
            }
        else:
            permission_filter = {"$or": [{"company_id": user["company_id"]}, {"user_id": user["id"]}]}
            
    filters = {"deleted": {"$ne": True}}
        
    if status:
        if status in ("aberto", "qualificado", "negociacao", "aprovado", "perdido", "realizado"):
            if status in ("aprovado", "realizado"):
                filters["status"] = {"$in": ["aprovado", "realizado"]}
            else:
                filters["status"] = status

    if seller_name:
        filters["seller_name"] = {"$regex": seller_name, "$options": "i"}

    if search:
        search_regex = {"$regex": search, "$options": "i"}
        filters["$or"] = [
            {"client_name": search_regex},
            {"client_document": search_regex},
            {"client_phone": search_regex},
            {"seller_name": search_regex}
        ]

    q = {"$and": [permission_filter, filters]}

    if page is None and page_size is None:
        # legado
        cursor = db.proposals.find(q, {"_id": 0}).sort("created_at", -1)
        items = await cursor.to_list(1000)
    elif page is not None and page_size is not None:
        # paginado
        skip = (page - 1) * page_size
        limit = page_size
        cursor = db.proposals.find(q, {"_id": 0}).sort("created_at", -1)
        items = await cursor.skip(skip).limit(limit).to_list(limit)
    else:
        raise HTTPException(
            status_code=422,
            detail="Ambos os parâmetros 'page' e 'page_size' devem ser informados."
        )

    return [normalize_proposal(item) for item in items]


@api_router.get("/proposals/{pid}")
async def get_proposal(pid: str, user=Depends(get_current_user)):
    role = user.get("role", "owner")
    doc = await db.proposals.find_one({"id": pid, "deleted": {"$ne": True}}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")

    belongs_to_company = doc.get("company_id") == user["company_id"] or doc.get("user_id") == user["id"]
    if not belongs_to_company:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    if role == "seller" and doc.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    return normalize_proposal(doc)


@api_router.put("/proposals/{pid}")
async def update_proposal(pid: str, data: ProposalIn, user=Depends(get_current_user)):
    role = user.get("role", "owner")
    doc = await db.proposals.find_one({"id": pid, "deleted": {"$ne": True}})
    if not doc:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    belongs_to_company = doc.get("company_id") == user["company_id"] or doc.get("user_id") == user["id"]
    if not belongs_to_company:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    if role == "seller" and doc.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    if doc.get("acceptance_status") == "accepted":
        raise HTTPException(status_code=400, detail="Não é permitido editar uma proposta que já foi aceita")
        
    resolved_products = []
    subtotal = 0.0
    for item in data.products:
        if item.quantity <= 0:
            raise HTTPException(status_code=422, detail="A quantidade do item deve ser maior que zero")

        if item.product_id and item.product_id.strip():
            p_doc = await db.products.find_one({
                "id": item.product_id,
                "company_id": user["company_id"],
                "active": True,
                "deleted": {"$ne": True}
            })
            if not p_doc:
                raise HTTPException(status_code=404, detail="Produto não encontrado")
            
            resolved_name = item.name.strip() if item.name and item.name.strip() else p_doc["name"]
            resolved_description = item.description if item.description is not None else p_doc.get("description", "")
            resolved_unit = item.unit.strip() if item.unit and item.unit.strip() else p_doc.get("unit", "UN")
            resolved_unit_price = item.unit_price if item.unit_price is not None else item.price
            if resolved_unit_price is None:
                resolved_unit_price = p_doc["price"]
            if resolved_unit_price < 0:
                raise HTTPException(status_code=422, detail="O preço unitário deve ser maior ou igual a zero")

            item_total = round(item.quantity * resolved_unit_price, 2)
            subtotal += item_total
            resolved_products.append({
                "product_id": item.product_id,
                "code": p_doc["code"],
                "name": resolved_name,
                "description": resolved_description,
                "unit": resolved_unit,
                "quantity": item.quantity,
                "unit_price": resolved_unit_price,
                "total": item_total,
                "item_type": "catalog"
            })
        else:
            resolved_unit_price = item.unit_price if item.unit_price is not None else item.price
            if not item.name or not item.name.strip() or resolved_unit_price is None or item.quantity is None:
                raise HTTPException(status_code=422, detail="Item manual requer name, unit_price e quantity")
            if resolved_unit_price < 0:
                raise HTTPException(status_code=422, detail="O preço unitário deve ser maior ou igual a zero")
            
            item_total = round(item.quantity * resolved_unit_price, 2)
            subtotal += item_total
            resolved_products.append({
                "product_id": "",
                "code": "",
                "name": item.name.strip(),
                "description": item.description or "",
                "unit": item.unit or "UN",
                "quantity": item.quantity,
                "unit_price": resolved_unit_price,
                "total": item_total,
                "item_type": "manual"
            })

    subtotal = round(subtotal, 2)
    discount = float(data.discount or 0.0)
    grand_total = round(max(subtotal - discount, 0.0), 2)

    # Resolve client_id
    client_id = await resolve_client_id(
        company_id=user["company_id"],
        name=data.client_name,
        document=data.client_document,
        phone=data.client_phone,
        user_id=user["id"],
        email=data.client_email or "",
        company=data.client_company or "",
        city=data.client_city or "",
        state=data.client_state or "",
        address=data.client_address or ""
    )

    update = {
        "client_id": client_id,
        "client_name": data.client_name,
        "client_document": data.client_document,
        "client_phone": data.client_phone,
        "client_email": data.client_email or "",
        "client_company": data.client_company or "",
        "client_city": data.client_city or "",
        "client_state": data.client_state or "",
        "client_address": data.client_address or "",
        "products": resolved_products,
        "shipping_deadline": data.shipping_deadline,
        "notes": data.notes or "",
        "discount": discount,
        "subtotal": subtotal,
        "grand_total": grand_total,
        "total": grand_total,
        "payment_terms": data.payment_terms or "",
        "validity_days": int(data.validity_days or 15),
        "images": data.images or [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "shipping_type": data.shipping_type or "",
        "shipping_responsible": data.shipping_responsible or "",
        "shipping_company": data.shipping_company or "",
        "manufacturing_days": data.manufacturing_days or "",
        "delivery_days": data.delivery_days or "",
        "warranty": data.warranty or "",
        "delivery_place": data.delivery_place or "",
        "incoterm": data.incoterm or "",
        "currency": data.currency or "BRL",
        "commercial_conditions": data.commercial_conditions or "",
        "internal_notes": data.internal_notes or "",
    }
    await db.proposals.update_one({"id": pid}, {"$set": update})
    updated_doc = await db.proposals.find_one({"id": pid}, {"_id": 0})
    
    # Audit log update proposal
    await log_audit(
        action="update",
        entity_type="proposal",
        entity_id=pid,
        old_value=doc,
        new_value=updated_doc,
        user_id=user["id"],
        company_id=user["company_id"]
    )
    
    # Audit log discount change if applicable
    if doc.get("discount") != discount:
        await log_audit(
            action="change_discount",
            entity_type="proposal",
            entity_id=pid,
            old_value=doc,
            new_value=updated_doc,
            user_id=user["id"],
            company_id=user["company_id"]
        )
        
    return normalize_proposal(updated_doc)


@api_router.patch("/proposals/{pid}/status")
async def change_status(pid: str, data: StatusUpdate, user=Depends(get_current_user)):
    role = user.get("role", "owner")
    doc = await db.proposals.find_one({"id": pid, "deleted": {"$ne": True}})
    if not doc:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    belongs_to_company = doc.get("company_id") == user["company_id"] or doc.get("user_id") == user["id"]
    if not belongs_to_company:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    if role == "seller" and doc.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    if doc.get("acceptance_status") == "accepted":
        raise HTTPException(status_code=400, detail="Não é permitido alterar o status de uma proposta aceita. O proprietário deve reabri-la primeiro.")
        
    # ENFORCE TRANSITION GRAPH HERE
    current_status = doc.get("status", "aberto")
    if current_status == "realizado":
        current_status = "aprovado"
        
    target_status = data.status
    if target_status == "realizado":
        target_status = "aprovado"
        
    if current_status != target_status:
        allowed = False
        if current_status == "aberto" and target_status in ("qualificado", "negociacao", "aprovado", "perdido"):
            allowed = True
        elif current_status == "qualificado" and target_status in ("negociacao", "aprovado", "perdido"):
            allowed = True
        elif current_status == "negociacao" and target_status in ("aprovado", "perdido"):
            allowed = True
            
        if not allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Transição de status não permitida: {current_status} -> {target_status}"
            )

    if target_status == "perdido" and not (data.lost_reason and data.lost_reason.strip()):
        raise HTTPException(status_code=400, detail="Motivo da perda é obrigatório")

    now = datetime.now(timezone.utc).isoformat()
    update = {
        "status": target_status,
        "lost_reason": data.lost_reason or "" if target_status == "perdido" else "",
        "status_updated_at": now,
        "updated_at": now,
    }
    await db.proposals.update_one({"id": pid}, {"$set": update})
    updated_doc = await db.proposals.find_one({"id": pid}, {"_id": 0})
    
    # Audit log status change
    await log_audit(
        action="change_status",
        entity_type="proposal",
        entity_id=pid,
        old_value=doc,
        new_value=updated_doc,
        user_id=user["id"],
        company_id=user["company_id"]
    )
    
    return normalize_proposal(updated_doc)


@api_router.post("/proposals/{pid}/duplicate")
async def duplicate_proposal(pid: str, user=Depends(get_current_user)):
    await verify_trial_not_expired(user["company_id"], user["id"])
    role = user.get("role", "owner")
    orig = await db.proposals.find_one({"id": pid, "deleted": {"$ne": True}}, {"_id": 0})
    if not orig:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    belongs_to_company = orig.get("company_id") == user["company_id"] or orig.get("user_id") == user["id"]
    if not belongs_to_company:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    if role == "seller" and orig.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        

    now = datetime.now(timezone.utc).isoformat()
    new_id = str(uuid.uuid4())
    public_code = await generate_unique_public_code()
    
    products = orig.get("products", [])
    subtotal = sum(item.get("quantity", 0) * (item.get("unit_price") or item.get("price") or 0.0) for item in products)
    subtotal = round(subtotal, 2)
    discount = float(orig.get("discount", 0.0))
    grand_total = round(max(subtotal - discount, 0.0), 2)

    # Resolve client_id
    client_id = await resolve_client_id(
        company_id=user["company_id"],
        name=orig["client_name"],
        document=orig["client_document"],
        phone=orig["client_phone"],
        user_id=user["id"]
    )
    
    clone = {
        **orig,
        "id": new_id,
        "public_code": public_code,
        "user_id": user["id"],
        "company_id": user["company_id"],
        "seller_name": user.get("name") or "",
        "seller_email": user.get("email") or "",
        "seller_phone": user.get("phone") or "",
        "seller_whatsapp": user.get("whatsapp") or "",
        "seller_role": user.get("role") or "owner",
        "seller_signature": user.get("signature_url") or user.get("seller_signature") or "",
        "client_id": client_id,
        "status": "aberto",
        "status_updated_at": now,
        "lost_reason": "",
        "acceptance_status": "pending",
        "accept_name": "",
        "accept_document": "",
        "accept_role": "",
        "accept_date": "",
        "accept_ip": "",
        "accept_device": "",
        "products": products,
        "subtotal": subtotal,
        "discount": discount,
        "grand_total": grand_total,
        "total": grand_total,
        "created_at": now,
        "updated_at": now,
        "last_reminded_at": None,
        "deleted": False
    }
    clone.pop("_id", None)
    await db.proposals.insert_one(clone)
    clone.pop("_id", None)
    
    # Audit log duplicate (creation)
    await log_audit(
        action="create",
        entity_type="proposal",
        entity_id=new_id,
        old_value=None,
        new_value=clone,
        user_id=user["id"],
        company_id=user["company_id"]
    )
    
    return normalize_proposal(clone)


@api_router.delete("/proposals/{pid}")
async def delete_proposal(pid: str, user=Depends(get_current_user)):
    role = user.get("role", "owner")
    doc = await db.proposals.find_one({"id": pid, "deleted": {"$ne": True}})
    if not doc:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    belongs_to_company = doc.get("company_id") == user["company_id"] or doc.get("user_id") == user["id"]
    if not belongs_to_company:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    if role == "seller" and doc.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    if doc.get("acceptance_status") == "accepted":
        raise HTTPException(status_code=400, detail="Não é permitido deletar uma proposta que já foi aceita")
        
    now = datetime.now(timezone.utc).isoformat()
    await db.proposals.update_one(
        {"id": pid},
        {"$set": {
            "deleted": True,
            "deleted_at": now,
            "deleted_by": user["id"]
        }}
    )
    
    updated_doc = await db.proposals.find_one({"id": pid})
    
    # Audit log logical deletion
    await log_audit(
        action="delete",
        entity_type="proposal",
        entity_id=pid,
        old_value=doc,
        new_value=updated_doc,
        user_id=user["id"],
        company_id=user["company_id"]
    )
    
    return {"ok": True}


class AcceptIn(BaseModel):
    name: str
    document: str
    role: str
    accepted: bool


@api_router.post("/proposals/{pid}/accept")
async def accept_proposal(pid: str, data: AcceptIn, request: Request):
    doc = await db.proposals.find_one({"id": pid, "deleted": {"$ne": True}})
    if not doc:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    current_status = doc.get("acceptance_status", "pending")
    if current_status in ("accepted", "rejected"):
        raise HTTPException(status_code=400, detail="Este aceite já foi finalizado e não pode ser alterado")
        
    ip = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")
    
    device = "Desconhecido"
    ua_lower = user_agent.lower()
    if "iphone" in ua_lower:
        device = "iPhone"
    elif "ipad" in ua_lower:
        device = "iPad"
    elif "android" in ua_lower:
        device = "Android"
    elif "windows" in ua_lower:
        device = "Windows Desktop"
    elif "macintosh" in ua_lower or "mac os" in ua_lower:
        device = "Mac Desktop"
    elif "linux" in ua_lower:
        device = "Linux Desktop"
        
    target_status = "accepted" if data.accepted else "rejected"
    now = datetime.now(timezone.utc).isoformat()
    
    update = {
        "acceptance_status": target_status,
        "accept_name": data.name,
        "accept_document": data.document,
        "accept_role": data.role,
        "accept_date": now,
        "accept_ip": ip,
        "accept_device": f"{device} ({user_agent[:100]})" if user_agent else device
    }
    
    if data.accepted:
        update["status"] = "aprovado"
        update["status_updated_at"] = now
    else:
        update["status"] = "perdido"
        update["lost_reason"] = "Recusado pelo cliente no aceite digital"
        update["status_updated_at"] = now
        
    timeline_event = {
        "id": str(uuid.uuid4()),
        "type": "accepted" if data.accepted else "rejected",
        "description": "✅ Cliente aceitou." if data.accepted else "❌ Cliente recusou.",
        "created_at": now,
        "created_by": "client",
        "next_action_date": None,
        "next_action_description": ""
    }
    await db.proposals.update_one(
        {"id": pid},
        {
            "$set": update,
            "$push": {
                "timeline": timeline_event
            }
        }
    )
    updated_doc = await db.proposals.find_one({"id": pid}, {"_id": 0})
    
    await log_audit(
        action="accept" if data.accepted else "reject",
        entity_type="proposal",
        entity_id=pid,
        old_value=doc,
        new_value=updated_doc,
        user_id=doc.get("user_id", ""),
        company_id=doc.get("company_id", "")
    )
    
    return normalize_proposal(updated_doc)


@api_router.post("/proposals/{pid}/reopen")
async def reopen_proposal(pid: str, user=Depends(get_current_user)):
    role = user.get("role", "owner")
    if role != "owner":
        raise HTTPException(status_code=403, detail="Apenas o proprietário (owner) pode reabrir a proposta")
        
    doc = await db.proposals.find_one({"id": pid, "deleted": {"$ne": True}})
    if not doc:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    update = {
        "acceptance_status": "pending",
        "accept_name": "",
        "accept_document": "",
        "accept_role": "",
        "accept_date": "",
        "accept_ip": "",
        "accept_device": ""
    }
    await db.proposals.update_one({"id": pid}, {"$set": update})
    updated_doc = await db.proposals.find_one({"id": pid}, {"_id": 0})
    
    await log_audit(
        action="reopen",
        entity_type="proposal",
        entity_id=pid,
        old_value=doc,
        new_value=updated_doc,
        user_id=user["id"],
        company_id=user["company_id"]
    )
    return normalize_proposal(updated_doc)


@api_router.post("/proposals/{pid}/timeline")
async def add_timeline_event(pid: str, data: TimelineInput, user=Depends(get_current_user)):
    role = user.get("role", "owner")
    company_id = user.get("company_id")
    
    # Check access
    q = {"id": pid, "deleted": {"$ne": True}}
    if role == "seller":
        q["user_id"] = user["id"]
    else:
        if company_id:
            q["company_id"] = company_id
            
    doc = await db.proposals.find_one(q)
    if not doc:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    # Check trial expiration
    await verify_trial_not_expired(user["company_id"], user["id"])
    
    # Validate manually allowed types
    allowed_types = ["call", "whatsapp", "visit", "meeting", "negotiation", "note"]
    if data.type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Tipo de interação inválido. Permitidos: {', '.join(allowed_types)}")
        
    now = datetime.now(timezone.utc).isoformat()
    
    timeline_event = {
        "id": str(uuid.uuid4()),
        "type": data.type,
        "description": data.description.strip(),
        "created_at": now,
        "created_by": user.get("name") or user["id"],
        "next_action_date": data.next_action_date or None,
        "next_action_description": data.next_action_description or ""
    }
    
    update_ops = {
        "$push": {"timeline": timeline_event},
        "$set": {"updated_at": now}
    }
    
    # Update next action on root level (can be set to None if cleared)
    update_ops["$set"]["next_action_date"] = data.next_action_date or None
    update_ops["$set"]["next_action_description"] = data.next_action_description or ""
        
    # If temperature is specified and valid, update it
    if data.temperature:
        if data.temperature not in ("FRIO", "MORNO", "QUENTE", "MUITO_QUENTE"):
            raise HTTPException(status_code=400, detail="Temperatura inválida. Permitidos: FRIO, MORNO, QUENTE, MUITO_QUENTE")
        update_ops["$set"]["temperature"] = data.temperature
        
    await db.proposals.update_one({"id": pid}, update_ops)
    updated_doc = await db.proposals.find_one({"id": pid}, {"_id": 0})
    
    await log_audit(
        action="add_timeline",
        entity_type="proposal",
        entity_id=pid,
        old_value=doc,
        new_value=updated_doc,
        user_id=user["id"],
        company_id=user.get("company_id")
    )
    
    return normalize_proposal(updated_doc)


@api_router.patch("/proposals/{pid}/temperature")
async def update_proposal_temperature(pid: str, data: dict, user=Depends(get_current_user)):
    role = user.get("role", "owner")
    company_id = user.get("company_id")
    
    temperature = data.get("temperature")
    if not temperature or temperature not in ("FRIO", "MORNO", "QUENTE", "MUITO_QUENTE"):
        raise HTTPException(status_code=400, detail="Temperatura inválida. Permitidos: FRIO, MORNO, QUENTE, MUITO_QUENTE")
        
    # Check access
    q = {"id": pid, "deleted": {"$ne": True}}
    if role == "seller":
        q["user_id"] = user["id"]
    else:
        if company_id:
            q["company_id"] = company_id
            
    doc = await db.proposals.find_one(q)
    if not doc:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    now = datetime.now(timezone.utc).isoformat()
    await db.proposals.update_one(
        {"id": pid},
        {"$set": {"temperature": temperature, "updated_at": now}}
    )
    
    updated_doc = await db.proposals.find_one({"id": pid}, {"_id": 0})
    
    await log_audit(
        action="update_temperature",
        entity_type="proposal",
        entity_id=pid,
        old_value=doc,
        new_value=updated_doc,
        user_id=user["id"],
        company_id=user.get("company_id")
    )
    
    return normalize_proposal(updated_doc)


# ---------- Opportunities ----------

def _opportunity_total(products: List[dict]) -> float:
    subtotal = sum((p.get("quantity", 0) or 0) * (p.get("price", p.get("unit_price", 0)) or 0) for p in products)
    return round(max(subtotal, 0), 2)


def normalize_opportunity(o: dict) -> dict:
    if not o:
        return o
    o["status"] = o.get("status", "OPEN")
    o["status_updated_at"] = o.get("status_updated_at") or o.get("updated_at") or o.get("created_at") or ""
    o["client_id"] = o.get("client_id") or ""
    o["client_company"] = o.get("client_company") or ""
    o["client_email"] = o.get("client_email") or ""
    o["client_city"] = o.get("client_city") or ""
    o["client_state"] = o.get("client_state") or ""
    o["client_address"] = o.get("client_address") or ""
    o["estimated_value"] = float(o.get("estimated_value") or 0.0)
    o["temperature"] = o.get("temperature") or "MORNO"
    o["next_action_date"] = o.get("next_action_date") or None
    o["next_action_description"] = o.get("next_action_description") or ""
    o["timeline"] = o.get("timeline") or []
    o["products"] = normalize_proposal_items(o.get("products") or [])
    o["description"] = o.get("description") or ""
    o["title"] = o.get("title") or ""
    o["notes"] = o.get("notes") or ""
    o["stage"] = o.get("stage") or "NOVO"
    return o


@api_router.post("/opportunities")
async def create_opportunity(data: OpportunityIn, user=Depends(get_current_user)):
    resolved_products = []
    subtotal = 0.0
    for item in data.products or []:
        if item.product_id and item.product_id.strip():
            p_doc = await db.products.find_one({
                "id": item.product_id,
                "company_id": user["company_id"],
                "active": True,
                "deleted": {"$ne": True}
            })
            if not p_doc:
                raise HTTPException(status_code=404, detail="Produto não encontrado")
            item_total = round(item.quantity * p_doc["price"], 2)
            subtotal += item_total
            resolved_products.append({
                "product_id": item.product_id,
                "code": p_doc["code"],
                "name": p_doc["name"],
                "description": p_doc.get("description", ""),
                "unit": p_doc.get("unit", "UN"),
                "quantity": item.quantity,
                "unit_price": p_doc["price"],
                "total": item_total,
                "item_type": "catalog"
            })
        else:
            resolved_unit_price = item.unit_price if item.unit_price is not None else item.price
            if not item.name or not item.name.strip() or resolved_unit_price is None or item.quantity is None:
                raise HTTPException(status_code=422, detail="Item manual requer name, unit_price e quantity")
            item_total = round(item.quantity * resolved_unit_price, 2)
            subtotal += item_total
            resolved_products.append({
                "product_id": "",
                "code": "",
                "name": item.name.strip(),
                "description": item.description or "",
                "unit": item.unit or "UN",
                "quantity": item.quantity,
                "unit_price": resolved_unit_price,
                "total": item_total,
                "item_type": "manual"
            })

    estimated_value = round(subtotal, 2) if resolved_products else float(data.estimated_value or 0.0)
    now = datetime.now(timezone.utc).isoformat()
    # Validate probability
    if data.probability is None:
        probability = 0
    else:
        probability = int(data.probability)
    if probability < 0 or probability > 100:
        raise HTTPException(status_code=422, detail="Probability must be between 0 and 100")

    # Validate client_id if provided
    if data.client_id:
        client = await db.clients.find_one({"id": data.client_id, "company_id": user["company_id"], "deleted": {"$ne": True}})
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Validate proposal_id if provided and ensure no duplicate
    if data.proposal_id:
        prop = await db.proposals.find_one({"id": data.proposal_id, "deleted": {"$ne": True}})
        if not prop or (prop.get("company_id") != user["company_id"] and prop.get("user_id") != user["id"]):
            raise HTTPException(status_code=404, detail="Proposta não encontrada ou pertence a outra empresa")
        # Check duplicate opportunity for same company+proposal
        exists = await db.opportunities.find_one({"company_id": user["company_id"], "proposal_id": data.proposal_id, "deleted": {"$ne": True}})
        if exists:
            raise HTTPException(status_code=409, detail="Já existe uma oportunidade para esta proposta nesta empresa")

    # Validate seller_id if provided
    if data.seller_id:
        seller = await db.users.find_one({"id": data.seller_id})
        if not seller or seller.get("company_id") != user.get("company_id"):
            raise HTTPException(status_code=404, detail="Vendedor não encontrado na empresa")
        if user.get("role") == "seller" and data.seller_id != user.get("id"):
            raise HTTPException(status_code=403, detail="Vendedor não pode atribuir outra pessoa")
    client_id = await resolve_client_id(
        company_id=user["company_id"],
        name=data.client_name,
        document=data.client_document,
        phone=data.client_phone,
        user_id=user["id"],
        email=data.client_email or "",
        company=data.client_company or "",
        city=data.client_city or "",
        state=data.client_state or "",
        address=data.client_address or ""
    )

    oid = str(uuid.uuid4())
    doc = {
        "id": oid,
        "user_id": user["id"],
        "company_id": user["company_id"],
        "proposal_id": data.proposal_id or "",
        "seller_name": user.get("name") or "",
        "seller_email": user.get("email") or "",
        "seller_phone": user.get("phone") or "",
        "seller_whatsapp": user.get("whatsapp") or "",
        "seller_role": user.get("role") or "owner",
        "seller_signature": user.get("signature_url") or user.get("seller_signature") or "",
        "client_id": client_id,
        "client_name": data.client_name,
        "client_document": data.client_document,
        "client_phone": data.client_phone,
        "client_email": data.client_email or "",
        "client_company": data.client_company or "",
        "client_city": data.client_city or "",
        "client_state": data.client_state or "",
        "client_address": data.client_address or "",
        "title": data.title,
        "description": data.description or "",
        "products": resolved_products,
        "estimated_value": estimated_value,
        "estimated_close_date": data.estimated_close_date or "",
        "notes": data.notes or "",
        "status": "OPEN",
        "status_updated_at": now,
        "lost_reason": "",
        "temperature": data.temperature or "MORNO",
        "probability": probability,
        "next_action_date": data.next_action_date or None,
        "next_action_description": data.next_action_description or "",
        "created_at": now,
        "updated_at": now,
        "deleted": False,
        "timeline": [
            {
                "id": str(uuid.uuid4()),
                "type": "created",
                "description": "Oportunidade criada.",
                "created_at": now,
                "created_by": user["id"],
                "next_action_date": None,
                "next_action_description": ""
            }
        ]
    }
    await db.opportunities.insert_one(doc)
    doc.pop("_id", None)

    await log_audit(
        action="create",
        entity_type="opportunity",
        entity_id=oid,
        old_value=None,
        new_value=doc,
        user_id=user["id"],
        company_id=user["company_id"]
    )
    # automatic timeline event
    await _push_opportunity_timeline(oid, "OPPORTUNITY_CREATED", "Oportunidade criada.", user.get("id"))
    return normalize_opportunity(doc)


@api_router.get("/opportunities")
async def list_opportunities(
    status: Optional[str] = None,
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
    scope: Optional[str] = None,
    seller_id: Optional[str] = None,
    seller_name: Optional[str] = None,
    search: Optional[str] = None,
    user=Depends(get_current_user),
):
    role = user.get("role", "owner")
    if role == "seller":
        permission_filter = {"company_id": user["company_id"], "user_id": user["id"]}
    else:
        if scope in ("meu_time", "team"):
            permission_filter = {
                "company_id": user["company_id"],
                "user_id": {"$ne": user["id"]}
            }
        elif scope == "vendedor" and seller_id:
            permission_filter = {
                "company_id": user["company_id"],
                "user_id": seller_id
            }
        else:
            permission_filter = {"$or": [{"company_id": user["company_id"]}, {"user_id": user["id"]}]}

    filters = {"deleted": {"$ne": True}}
    if status:
        if status in ("OPEN", "WAITING", "HUMAN_ACTION", "WON", "LOST", "CANCELLED"):
            filters["status"] = status

    if seller_name:
        filters["seller_name"] = {"$regex": seller_name, "$options": "i"}

    if search:
        search_regex = {"$regex": search, "$options": "i"}
        filters["$or"] = [
            {"client_name": search_regex},
            {"client_document": search_regex},
            {"client_phone": search_regex},
            {"seller_name": search_regex},
            {"title": search_regex},
        ]

    q = {"$and": [permission_filter, filters]}
    if page is None and page_size is None:
        cursor = db.opportunities.find(q, {"_id": 0}).sort("created_at", -1)
        items = await cursor.to_list(1000)
    elif page is not None and page_size is not None:
        skip = (page - 1) * page_size
        limit = page_size
        cursor = db.opportunities.find(q, {"_id": 0}).sort("created_at", -1)
        items = await cursor.skip(skip).limit(limit).to_list(limit)
    else:
        raise HTTPException(
            status_code=422,
            detail="Ambos os parâmetros 'page' e 'page_size' devem ser informados."
        )
    return [normalize_opportunity(item) for item in items]


@api_router.get("/opportunities/{oid}")
async def get_opportunity(oid: str, user=Depends(get_current_user)):
    role = user.get("role", "owner")
    doc = await db.opportunities.find_one({"id": oid, "deleted": {"$ne": True}}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")

    belongs_to_company = doc.get("company_id") == user["company_id"] or doc.get("user_id") == user["id"]
    if not belongs_to_company:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")

    if role == "seller" and doc.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")

    return normalize_opportunity(doc)


@api_router.put("/opportunities/{oid}")
async def update_opportunity(oid: str, data: OpportunityUpdateIn, user=Depends(get_current_user)):
    role = user.get("role", "owner")
    doc = await db.opportunities.find_one({"id": oid, "deleted": {"$ne": True}})
    if not doc:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")

    belongs_to_company = doc.get("company_id") == user["company_id"] or doc.get("user_id") == user["id"]
    if not belongs_to_company:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")

    if role == "seller" and doc.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")

    resolved_products = []
    subtotal = 0.0
    for item in data.products or []:
        if item.product_id and item.product_id.strip():
            p_doc = await db.products.find_one({
                "id": item.product_id,
                "company_id": user["company_id"],
                "active": True,
                "deleted": {"$ne": True}
            })
            if not p_doc:
                raise HTTPException(status_code=404, detail="Produto não encontrado")
            item_total = round(item.quantity * p_doc["price"], 2)
            subtotal += item_total
            resolved_products.append({
                "product_id": item.product_id,
                "code": p_doc["code"],
                "name": p_doc["name"],
                "description": p_doc.get("description", ""),
                "unit": p_doc.get("unit", "UN"),
                "quantity": item.quantity,
                "unit_price": p_doc["price"],
                "total": item_total,
                "item_type": "catalog"
            })
        else:
            resolved_unit_price = item.unit_price if item.unit_price is not None else item.price
            if not item.name or not item.name.strip() or resolved_unit_price is None or item.quantity is None:
                raise HTTPException(status_code=422, detail="Item manual requer name, unit_price e quantity")
            item_total = round(item.quantity * resolved_unit_price, 2)
            subtotal += item_total
            resolved_products.append({
                "product_id": "",
                "code": "",
                "name": item.name.strip(),
                "description": item.description or "",
                "unit": item.unit or "UN",
                "quantity": item.quantity,
                "unit_price": resolved_unit_price,
                "total": item_total,
                "item_type": "manual"
            })

    estimated_value = round(subtotal, 2) if resolved_products else float(data.estimated_value or 0.0)
    now = datetime.now(timezone.utc).isoformat()
    # Validate probability
    if data.probability is not None:
        prob = int(data.probability)
        if prob < 0 or prob > 100:
            raise HTTPException(status_code=422, detail="Probability must be between 0 and 100")

    # Validate client_id if provided
    if data.client_id:
        client = await db.clients.find_one({"id": data.client_id, "company_id": user["company_id"], "deleted": {"$ne": True}})
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Validate proposal_id if provided (and check duplicates)
    if data.proposal_id:
        prop = await db.proposals.find_one({"id": data.proposal_id, "deleted": {"$ne": True}})
        if not prop or (prop.get("company_id") != user["company_id"] and prop.get("user_id") != user["id"]):
            raise HTTPException(status_code=404, detail="Proposta não encontrada ou pertence a outra empresa")
        # if changing proposal_id, ensure no duplicate
        if data.proposal_id != doc.get("proposal_id"):
            exists = await db.opportunities.find_one({"company_id": user["company_id"], "proposal_id": data.proposal_id, "deleted": {"$ne": True}})
            if exists:
                raise HTTPException(status_code=409, detail="Já existe uma oportunidade para esta proposta nesta empresa")

    # Validate seller_id if provided
    if data.seller_id:
        seller = await db.users.find_one({"id": data.seller_id})
        if not seller or seller.get("company_id") != user.get("company_id"):
            raise HTTPException(status_code=404, detail="Vendedor não encontrado na empresa")
        if user.get("role") == "seller" and data.seller_id != user.get("id"):
            raise HTTPException(status_code=403, detail="Vendedor não pode atribuir outra pessoa")

    # Resolve client_id (fallback to existing behavior using name/document)
    client_id = await resolve_client_id(
        company_id=user["company_id"],
        name=data.client_name,
        document=data.client_document,
        phone=data.client_phone,
        user_id=user["id"],
        email=data.client_email or "",
        company=data.client_company or "",
        city=data.client_city or "",
        state=data.client_state or "",
        address=data.client_address or ""
    )

    payload = data.model_dump(exclude_none=True)
    update = {
        "client_id": client_id,
        "proposal_id": payload.get("proposal_id", doc.get("proposal_id", "")) or "",
        "client_name": payload.get("client_name", doc.get("client_name", "")),
        "client_document": payload.get("client_document", doc.get("client_document", "")),
        "client_phone": payload.get("client_phone", doc.get("client_phone", "")),
        "client_email": payload.get("client_email", doc.get("client_email", "")) or "",
        "client_company": payload.get("client_company", doc.get("client_company", "")) or "",
        "client_city": payload.get("client_city", doc.get("client_city", "")) or "",
        "client_state": payload.get("client_state", doc.get("client_state", "")) or "",
        "client_address": payload.get("client_address", doc.get("client_address", "")) or "",
        "title": payload.get("title", doc.get("title", "")),
        "description": payload.get("description", doc.get("description", "")) or "",
        "products": resolved_products if payload.get("products") is not None else doc.get("products", []),
        "estimated_value": estimated_value if payload.get("estimated_value") is not None or payload.get("products") is not None else doc.get("estimated_value", 0.0),
        "estimated_close_date": payload.get("estimated_close_date", doc.get("estimated_close_date", "")) or "",
        "notes": payload.get("notes", doc.get("notes", "")) or "",
        "temperature": payload.get("temperature", doc.get("temperature", "MORNO")) or "MORNO",
        "next_action_date": payload.get("next_action_date", doc.get("next_action_date")) or None,
        "next_action_description": payload.get("next_action_description", doc.get("next_action_description", "")) or "",
        "probability": int(payload["probability"]) if "probability" in payload else doc.get("probability", 0),
        "updated_at": now,
    }
    await db.opportunities.update_one({"id": oid}, {"$set": update})
    updated_doc = await db.opportunities.find_one({"id": oid}, {"_id": 0})

    await log_audit(
        action="update",
        entity_type="opportunity",
        entity_id=oid,
        old_value=doc,
        new_value=updated_doc,
        user_id=user["id"],
        company_id=user["company_id"]
    )
    # If temperature changed, add timeline event
    if doc.get("temperature") != updated_doc.get("temperature"):
        await _push_opportunity_timeline(oid, "TEMPERATURE_CHANGED", f"Temperatura alterada para {updated_doc.get('temperature')}", user.get("id"), {"old": doc.get("temperature"), "new": updated_doc.get("temperature")})
    return normalize_opportunity(updated_doc)


@api_router.patch("/opportunities/{oid}/status")
async def change_opportunity_status(oid: str, data: OpportunityStatusUpdate, user=Depends(get_current_user)):
    role = user.get("role", "owner")
    doc = await db.opportunities.find_one({"id": oid, "deleted": {"$ne": True}})
    if not doc:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")

    belongs_to_company = doc.get("company_id") == user["company_id"] or doc.get("user_id") == user["id"]
    if not belongs_to_company:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")

    if role == "seller" and doc.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")

    current_status = doc.get("status", "aberto")
    target_status = data.status
    # Simple rules: do not allow reopening WON/LOST
    if current_status in ("WON", "LOST") and target_status != current_status:
        raise HTTPException(status_code=400, detail="Não é permitido reabrir uma oportunidade já ganha/perdida")

    if target_status == "LOST" and not (data.lost_reason and data.lost_reason.strip()):
        raise HTTPException(status_code=400, detail="Motivo da perda é obrigatório")

    now = datetime.now(timezone.utc).isoformat()
    update = {
        "status": target_status,
        "lost_reason": data.lost_reason or "" if target_status == "LOST" else "",
        "status_updated_at": now,
        "updated_at": now,
    }
    await db.opportunities.update_one({"id": oid}, {"$set": update})
    updated_doc = await db.opportunities.find_one({"id": oid}, {"_id": 0})

    await log_audit(
        action="change_status",
        entity_type="opportunity",
        entity_id=oid,
        old_value=doc,
        new_value=updated_doc,
        user_id=user["id"],
        company_id=user["company_id"]
    )
    # Timeline event
    await _push_opportunity_timeline(oid, "STATUS_CHANGED", f"Status alterado para {target_status}", user.get("id"), {"old": doc.get("status"), "new": target_status})
    # closed_at handling
    if target_status == "WON" or target_status == "LOST":
        closed_at = datetime.now(timezone.utc).isoformat()
        await db.opportunities.update_one({"id": oid}, {"$set": {"closed_at": closed_at, "updated_at": closed_at}})
        updated_doc = await db.opportunities.find_one({"id": oid}, {"_id": 0})
        if target_status == "WON":
            await _push_opportunity_timeline(oid, "SALE_WON", "Oportunidade marcada como ganha.", user.get("id"))
        else:
            await _push_opportunity_timeline(oid, "SALE_LOST", "Oportunidade marcada como perdida.", user.get("id"))
    return normalize_opportunity(updated_doc)


@api_router.patch("/opportunities/{oid}/stage")
async def change_opportunity_stage(oid: str, data: OpportunityStageUpdate, user=Depends(get_current_user)):
    role = user.get("role", "owner")
    doc = await db.opportunities.find_one({"id": oid, "deleted": {"$ne": True}})
    if not doc:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")

    belongs_to_company = doc.get("company_id") == user["company_id"] or doc.get("user_id") == user["id"]
    if not belongs_to_company:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")

    if role == "seller" and doc.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")

    current_stage = doc.get("stage") or "NOVO"
    target_stage = data.stage
    if current_stage == target_stage:
        return normalize_opportunity(doc)

    now = datetime.now(timezone.utc).isoformat()
    await db.opportunities.update_one({"id": oid}, {"$set": {"stage": target_stage, "stage_updated_at": now, "updated_at": now}})
    updated_doc = await db.opportunities.find_one({"id": oid}, {"_id": 0})

    await log_audit(
        action="change_stage",
        entity_type="opportunity",
        entity_id=oid,
        old_value=doc,
        new_value=updated_doc,
        user_id=user["id"],
        company_id=user["company_id"]
    )

    await _push_opportunity_timeline(oid, "STAGE_CHANGED", f"Estágio alterado para {target_stage}", user.get("id"), {"old": current_stage, "new": target_stage})
    return normalize_opportunity(updated_doc)


@api_router.post("/opportunities/{oid}/timeline")
async def add_opportunity_timeline_event(oid: str, data: TimelineInput, user=Depends(get_current_user)):
    role = user.get("role", "owner")
    company_id = user.get("company_id")
    q = {"id": oid, "deleted": {"$ne": True}}
    if role == "seller":
        q["user_id"] = user["id"]
    else:
        if company_id:
            q["company_id"] = company_id
    doc = await db.opportunities.find_one(q)
    if not doc:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")

    allowed_types = ["call", "whatsapp", "visit", "meeting", "negotiation", "note"]
    if data.type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Tipo de interação inválido. Permitidos: {', '.join(allowed_types)}")

    now = datetime.now(timezone.utc).isoformat()
    timeline_event = {
        "id": str(uuid.uuid4()),
        "type": data.type,
        "description": data.description.strip(),
        "created_at": now,
        "created_by": user.get("name") or user["id"],
        "next_action_date": data.next_action_date or None,
        "next_action_description": data.next_action_description or ""
    }
    update_ops = {
        "$push": {"timeline": timeline_event},
        "$set": {
            "updated_at": now,
            "next_action_date": data.next_action_date or None,
            "next_action_description": data.next_action_description or ""
        }
    }
    if data.temperature:
        if data.temperature.upper() not in ["FRIO", "MORNO", "QUENTE", "MUITO_QUENTE"]:
            raise HTTPException(status_code=400, detail="Temperatura inválida. Permitidos: FRIO, MORNO, QUENTE, MUITO_QUENTE")
        update_ops["$set"]["temperature"] = data.temperature.upper()

    await db.opportunities.update_one({"id": oid}, update_ops)
    updated_doc = await db.opportunities.find_one({"id": oid}, {"_id": 0})

    await log_audit(
        action="add_timeline",
        entity_type="opportunity",
        entity_id=oid,
        old_value=doc,
        new_value=updated_doc,
        user_id=user["id"],
        company_id=company_id
    )
    # also push standardized event
    await _push_opportunity_timeline(oid, data.type.upper(), data.description.strip(), user.get("id"))
    return normalize_opportunity(updated_doc)


@api_router.patch("/opportunities/{oid}/temperature")
async def update_opportunity_temperature(oid: str, data: dict, user=Depends(get_current_user)):
    role = user.get("role", "owner")
    company_id = user.get("company_id")
    temperature = data.get("temperature")
    normalized_temperature = temperature.upper() if isinstance(temperature, str) else temperature
    if not normalized_temperature or normalized_temperature not in ["FRIO", "MORNO", "QUENTE", "MUITO_QUENTE"]:
        raise HTTPException(status_code=400, detail="Temperatura inválida. Permitidos: FRIO, MORNO, QUENTE, MUITO_QUENTE")

    q = {"id": oid, "deleted": {"$ne": True}}
    if role == "seller":
        q["user_id"] = user["id"]
    else:
        if company_id:
            q["company_id"] = company_id

    doc = await db.opportunities.find_one(q)
    if not doc:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")

    now = datetime.now(timezone.utc).isoformat()
    await db.opportunities.update_one(
        {"id": oid},
        {"$set": {"temperature": normalized_temperature, "updated_at": now}}
    )

    updated_doc = await db.opportunities.find_one({"id": oid}, {"_id": 0})
    await log_audit(
        action="update_temperature",
        entity_type="opportunity",
        entity_id=oid,
        old_value=doc,
        new_value=updated_doc,
        user_id=user["id"],
        company_id=company_id
    )
    # Timeline event
    await _push_opportunity_timeline(oid, "TEMPERATURE_CHANGED", f"Temperatura alterada para {temperature}", user.get("id"), {"old": doc.get("temperature"), "new": temperature})
    return normalize_opportunity(updated_doc)


@api_router.delete("/opportunities/{oid}")
async def delete_opportunity(oid: str, user=Depends(get_current_user)):
    role = user.get("role", "owner")
    doc = await db.opportunities.find_one({"id": oid, "deleted": {"$ne": True}})
    if not doc:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")

    belongs_to_company = doc.get("company_id") == user["company_id"] or doc.get("user_id") == user["id"]
    if not belongs_to_company:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")

    if role == "seller" and doc.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")

    now = datetime.now(timezone.utc).isoformat()
    await db.opportunities.update_one(
        {"id": oid},
        {"$set": {
            "deleted": True,
            "deleted_at": now,
            "deleted_by": user["id"]
        }}
    )
    updated_doc = await db.opportunities.find_one({"id": oid}, {"_id": 0})
    await log_audit(
        action="delete",
        entity_type="opportunity",
        entity_id=oid,
        old_value=doc,
        new_value=updated_doc,
        user_id=user["id"],
        company_id=user["company_id"]
    )
    return {"ok": True}


@api_router.get("/public/proposals/{pid}")
async def get_public_proposal(pid: str, request: Request):
    doc = await db.proposals.find_one({"id": pid, "deleted": {"$ne": True}}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")

    client_ip = request.client.host if request.client else ""
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        client_ip = x_forwarded_for.split(",")[0].strip()

    user_agent = request.headers.get("user-agent", "")
    now = datetime.now(timezone.utc).isoformat()

    new_event = {
        "id": str(uuid.uuid4()),
        "type": "viewed",
        "description": "👁 Cliente visualizou.",
        "created_at": now,
        "created_by": "client",
        "next_action_date": None,
        "next_action_description": ""
    }
    await db.proposals.update_one(
        {"id": pid},
        {
            "$set": {
                "proposal_viewed_at": now,
                "proposal_viewed_ip": client_ip,
                "proposal_viewed_ua": user_agent,
                "updated_at": now
            },
            "$push": {
                "timeline": new_event
            }
        }
    )

    doc["proposal_viewed_at"] = now
    doc["proposal_viewed_ip"] = client_ip
    doc["proposal_viewed_ua"] = user_agent
    if "timeline" not in doc or doc["timeline"] is None:
        doc["timeline"] = []
    doc["timeline"].append(new_event)

    company_id = doc.get("company_id")
    company = None
    if company_id:
        company = await db.companies.find_one({"id": company_id}, {"_id": 0})

    return {
        "proposal": normalize_proposal(doc),
        "company": company or {}
    }


@api_router.get("/public/proposals/code/{code}")
async def get_public_proposal_by_code(code: str, request: Request):
    code_upper = code.upper().strip()
    doc = await db.proposals.find_one({"public_code": code_upper, "deleted": {"$ne": True}}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")

    client_ip = request.client.host if request.client else ""
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        client_ip = x_forwarded_for.split(",")[0].strip()

    user_agent = request.headers.get("user-agent", "")
    now = datetime.now(timezone.utc).isoformat()

    new_event = {
        "id": str(uuid.uuid4()),
        "type": "viewed",
        "description": "👁 Cliente visualizou.",
        "created_at": now,
        "created_by": "client",
        "next_action_date": None,
        "next_action_description": ""
    }
    await db.proposals.update_one(
        {"id": doc["id"]},
        {
            "$set": {
                "proposal_viewed_at": now,
                "proposal_viewed_ip": client_ip,
                "proposal_viewed_ua": user_agent,
                "updated_at": now
            },
            "$push": {
                "timeline": new_event
            }
        }
    )

    doc["proposal_viewed_at"] = now
    doc["proposal_viewed_ip"] = client_ip
    doc["proposal_viewed_ua"] = user_agent
    if "timeline" not in doc or doc["timeline"] is None:
        doc["timeline"] = []
    doc["timeline"].append(new_event)

    company_id = doc.get("company_id")
    company = None
    if company_id:
        company = await db.companies.find_one({"id": company_id}, {"_id": 0})

    return {
        "proposal": normalize_proposal(doc),
        "company": company or {}
    }


# ---------- Upload image ----------
@api_router.post("/upload/image")
async def upload_image(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):

    try:

        result = cloudinary.uploader.upload(
            file.file,

            folder="propostaapp",

            resource_type="image",
        )

        return {
            "url": result["secure_url"]
        }

    except Exception as e:

        logging.exception(
            "cloudinary upload error"
        )

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ---------- Import Engine (Etapa 1) ----------
@api_router.post("/imports")
async def upload_import(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    company_id = _safe_company_id(user)
    filename = sanitize_filename(file.filename or "import")
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_IMPORT_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Tipo de arquivo não suportado. Use CSV ou XLSX.")

    content = await file.read()
    if not content or len(content) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    if len(content) > MAX_IMPORT_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Arquivo excedeu o tamanho máximo permitido.")

    file_type = ALLOWED_IMPORT_EXTENSIONS.get(extension, "UNKNOWN")
    checksum = sha256_bytes(content)

    existing = await db.import_batches.find_one({"company_id": company_id, "checksum": checksum, "deleted": {"$ne": True}})
    if existing:
        return {
            "message": "Arquivo anteriormente importado.",
            "import_id": existing["id"],
            "duplicate": True,
            "status": existing["status"],
        }

    storage_ref = OriginalFileStorage.save(company_id, filename, content)
    now = datetime.now(timezone.utc).isoformat()
    batch_id = str(uuid.uuid4())
    batch_doc = {
        "id": batch_id,
        "company_id": company_id,
        "user_id": user["id"],
        "filename": filename,
        "file_type": file_type,
        "file_size": len(content),
        "source_type": file_type,
        "checksum": checksum,
        "original_storage_ref": storage_ref,
        "status": "UPLOADED",
        "profile_id": None,
        "profile_version": None,
        "records_detected": 0,
        "records_extracted": 0,
        "records_imported": 0,
        "records_updated": 0,
        "records_skipped": 0,
        "records_with_errors": 0,
        "parser_version": IMPORT_PARSER_VERSION,
        "jobs": [
            {
                "job_type": "UPLOAD",
                "status": "COMPLETED",
                "started_at": now,
                "finished_at": now,
                "records_processed": 0,
                "errors": [],
            },
            {
                "job_type": "VALIDATING",
                "status": "COMPLETED",
                "started_at": now,
                "finished_at": now,
                "records_processed": 0,
                "errors": [],
            },
        ],
        "created_at": now,
        "updated_at": now,
        "deleted": False,
    }

    await db.import_batches.insert_one(batch_doc)
    await log_audit(
        action="IMPORT_CREATED",
        entity_type="import_batch",
        entity_id=batch_id,
        old_value=None,
        new_value=batch_doc,
        user_id=user["id"],
        company_id=company_id,
    )

    try:
        raw_records, total_rows = _extract_raw_records(storage_ref, file_type)
        records_detected = max(len(raw_records), 0)
        await db.raw_records.delete_many({"import_batch_id": batch_id, "company_id": company_id})
        for index, rec in enumerate(raw_records, start=1):
            raw_doc = {
                "id": str(uuid.uuid4()),
                "import_batch_id": batch_id,
                "company_id": company_id,
                "source_file": filename,
                "source_sheet": rec["source_sheet"],
                "source_row": rec["source_row"],
                "original_record_json": rec["original_record_json"],
                "raw_metadata": rec["raw_metadata"],
                "record_status": "EXTRACTED",
                "created_at": now,
            }
            await db.raw_records.insert_one(raw_doc)

        await db.import_batches.update_one(
            {"id": batch_id},
            {"$set": {
                "status": "COMPLETED",
                "records_detected": records_detected,
                "records_extracted": records_detected,
                "records_imported": 0,
                "records_updated": 0,
                "records_skipped": 0,
                "records_with_errors": 0,
                "updated_at": now,
                "jobs": [
                    {
                        "job_type": "UPLOAD",
                        "status": "COMPLETED",
                        "started_at": batch_doc["created_at"],
                        "finished_at": now,
                        "records_processed": records_detected,
                        "errors": [],
                    },
                    {
                        "job_type": "VALIDATING",
                        "status": "COMPLETED",
                        "started_at": now,
                        "finished_at": now,
                        "records_processed": records_detected,
                        "errors": [],
                    },
                    {
                        "job_type": "RAW_EXTRACTION",
                        "status": "COMPLETED",
                        "started_at": now,
                        "finished_at": now,
                        "records_processed": records_detected,
                        "errors": [],
                    },
                    {
                        "job_type": "COMPLETED",
                        "status": "COMPLETED",
                        "started_at": now,
                        "finished_at": now,
                        "records_processed": records_detected,
                        "errors": [],
                    },
                ],
            }},
        )

        await log_audit(
            action="IMPORT_RAW_EXTRACTED",
            entity_type="import_batch",
            entity_id=batch_id,
            old_value={"records_detected": 0},
            new_value={"records_extracted": records_detected},
            user_id=user["id"],
            company_id=company_id,
        )

        final_batch = await db.import_batches.find_one({"id": batch_id}, {"_id": 0})
        return {
            "import_id": batch_id,
            "filename": filename,
            "status": "COMPLETED",
            "records_detected": records_detected,
            "records_extracted": records_detected,
            "records_skipped": 0,
            "records_with_errors": 0,
            "import_batch": final_batch,
        }
    except Exception as exc:
        await db.import_batches.update_one(
            {"id": batch_id},
            {"$set": {"status": "FAILED", "updated_at": now, "records_with_errors": 1}},
        )
        await log_audit(
            action="IMPORT_FAILED",
            entity_type="import_batch",
            entity_id=batch_id,
            old_value={"status": "UPLOADED"},
            new_value={"status": "FAILED", "error": str(exc)},
            user_id=user["id"],
            company_id=company_id,
        )
        raise HTTPException(status_code=400, detail=str(exc))


@api_router.get("/imports")
async def list_import_batches(user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    batches = await db.import_batches.find({"company_id": company_id, "deleted": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return batches


@api_router.get("/imports/{batch_id}")
async def get_import_batch(batch_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    batch = await db.import_batches.find_one({"id": batch_id, "company_id": company_id, "deleted": {"$ne": True}}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Importação não encontrada")
    return batch


@api_router.get("/imports/{batch_id}/report")
async def get_import_report(batch_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    batch = await db.import_batches.find_one({"id": batch_id, "company_id": company_id, "deleted": {"$ne": True}}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Importação não encontrada")
    raw_records = await db.raw_records.find({"company_id": company_id, "import_batch_id": batch_id}, {"_id": 0}).to_list(1000)
    return _build_import_report(batch, raw_records)


@api_router.get("/imports/{batch_id}/raw")
async def get_import_raw(
    batch_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user),
):
    company_id = _safe_company_id(user)
    batch = await db.import_batches.find_one({"id": batch_id, "company_id": company_id, "deleted": {"$ne": True}}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Importação não encontrada")

    skip = (page - 1) * page_size
    raw_records = await db.raw_records.find({"company_id": company_id, "import_batch_id": batch_id}, {"_id": 0}).sort("source_row", 1).skip(skip).limit(page_size).to_list(page_size)
    total = await db.raw_records.count_documents({"company_id": company_id, "import_batch_id": batch_id})
    return {
        "batch_id": batch_id,
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": raw_records,
    }


def _get_structure_profile_filter(user: dict, batch_id: str) -> dict:
    return {"company_id": _safe_company_id(user), "import_batch_id": batch_id}


@api_router.post("/imports/{batch_id}/analyze")
async def analyze_import_structure(batch_id: str, user=Depends(get_current_user)):
    """Analyze existing RawRecords without assigning business meanings."""
    ensure_db_for_current_loop()
    company_id = _safe_company_id(user)
    batch = await db.import_batches.find_one(
        {"id": batch_id, "company_id": company_id, "deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not batch:
        raise HTTPException(status_code=404, detail="Importação não encontrada")

    existing = await db.import_structure_profiles.find_one(
        {**_get_structure_profile_filter(user, batch_id), "analyzer_version": ANALYZER_VERSION},
        {"_id": 0},
    )
    if existing:
        return existing

    await log_audit(
        action="STRUCTURE_ANALYSIS_STARTED",
        entity_type="import_structure_profile",
        entity_id=batch_id,
        old_value=None,
        new_value={"import_batch_id": batch_id, "analyzer_version": ANALYZER_VERSION},
        user_id=user["id"],
        company_id=company_id,
    )
    now = datetime.now(timezone.utc).isoformat()
    try:
        raw_records = await db.raw_records.find(
            {"company_id": company_id, "import_batch_id": batch_id},
            {"_id": 0},
        ).sort("source_row", 1).to_list(100000)
        sheet_entries = []
        storage_ref = batch.get("original_storage_ref")
        if storage_ref and Path(storage_ref).exists():
            if batch.get("file_type") == "XLSX":
                sheet_entries = _parse_xlsx_file(storage_ref)
            else:
                sheet_entries = _extract_csv_records(storage_ref)
        file_summary = {
            "filename": batch.get("filename", ""),
            "file_type": batch.get("file_type", "UNKNOWN"),
            "file_size": batch.get("file_size", 0),
            "checksum": batch.get("checksum", ""),
            "sheets_count": len(sheet_entries) or len({record.get("source_sheet") for record in raw_records}),
        }
        profile = analyze_structure(file_summary, raw_records, sheet_entries)
        profile.update({
            "id": str(uuid.uuid4()),
            "company_id": company_id,
            "import_batch_id": batch_id,
            "created_at": now,
            "updated_at": now,
        })
        await db.import_structure_profiles.insert_one(profile)
        await db.import_batches.update_one(
            {"id": batch_id, "company_id": company_id},
            {"$set": {"profile_id": profile["id"], "profile_version": ANALYZER_VERSION, "updated_at": now}},
        )
        await log_audit(
            action="STRUCTURE_ANALYSIS_COMPLETED",
            entity_type="import_structure_profile",
            entity_id=profile["id"],
            old_value=None,
            new_value={"import_batch_id": batch_id, "analyzer_version": ANALYZER_VERSION},
            user_id=user["id"],
            company_id=company_id,
        )
        return profile
    except Exception as exc:
        await log_audit(
            action="STRUCTURE_ANALYSIS_FAILED",
            entity_type="import_structure_profile",
            entity_id=batch_id,
            old_value=None,
            new_value={"error": str(exc)},
            user_id=user["id"],
            company_id=company_id,
        )
        raise HTTPException(status_code=400, detail="Não foi possível analisar a estrutura") from exc


@api_router.get("/imports/{batch_id}/structure")
async def get_import_structure(batch_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    profile = await db.import_structure_profiles.find_one(
        _get_structure_profile_filter(user, batch_id), {"_id": 0},
        sort=[("created_at", -1)],
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil estrutural não encontrado")
    return profile


@api_router.get("/imports/{batch_id}/structure/sheets/{sheet_name}")
async def get_import_structure_sheet(batch_id: str, sheet_name: str, user=Depends(get_current_user)):
    profile = await db.import_structure_profiles.find_one(
        _get_structure_profile_filter(user, batch_id), {"_id": 0},
        sort=[("created_at", -1)],
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil estrutural não encontrado")
    for sheet in profile.get("sheets", []):
        if sheet.get("sheet_name") == sheet_name:
            return sheet
    raise HTTPException(status_code=404, detail="Aba não encontrada")


def _get_mapping_candidates_filter(user: dict, batch_id: str) -> dict:
    return {"company_id": _safe_company_id(user), "import_batch_id": batch_id}


@api_router.post("/imports/{batch_id}/mapping-candidates")
async def analyze_import_mapping_candidates(batch_id: str, user=Depends(get_current_user)):
    """Generate ranked mapping suggestions without applying any mapping."""
    ensure_db_for_current_loop()
    company_id = _safe_company_id(user)
    profile = await db.import_structure_profiles.find_one(
        {"company_id": company_id, "import_batch_id": batch_id},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil estrutural não encontrado")

    existing = await db.mapping_candidates.find_one(
        {**_get_mapping_candidates_filter(user, batch_id), "mapping_engine_version": MAPPING_ENGINE_VERSION},
        {"_id": 0},
    )
    if existing:
        return existing

    await log_audit(
        action="MAPPING_ANALYSIS_STARTED",
        entity_type="mapping_candidates",
        entity_id=batch_id,
        old_value=None,
        new_value={"structure_profile_id": profile.get("id"), "mapping_engine_version": MAPPING_ENGINE_VERSION},
        user_id=user["id"],
        company_id=company_id,
    )
    now = datetime.now(timezone.utc).isoformat()
    try:
        result = generate_candidate_mappings(profile)
        document = {
            "id": str(uuid.uuid4()),
            "company_id": company_id,
            "import_batch_id": batch_id,
            "structure_profile_id": profile.get("id"),
            "mapping_engine_version": MAPPING_ENGINE_VERSION,
            "candidates": result.get("sources", []),
            "warnings": result.get("warnings", []),
            "global_statistics": result.get("global_statistics", {}),
            "created_at": now,
            "updated_at": now,
        }
        await db.mapping_candidates.insert_one(document)
        await log_audit(
            action="MAPPING_ANALYSIS_COMPLETED",
            entity_type="mapping_candidates",
            entity_id=document["id"],
            old_value=None,
                new_value={"import_batch_id": batch_id, "source_fields": len(document["candidates"])},
            user_id=user["id"],
            company_id=company_id,
        )
        return document
    except Exception as exc:
        await log_audit(
            action="MAPPING_ANALYSIS_FAILED",
            entity_type="mapping_candidates",
            entity_id=batch_id,
            old_value=None,
            new_value={"error": str(exc)},
            user_id=user["id"],
            company_id=company_id,
        )
        raise HTTPException(status_code=400, detail="Não foi possível gerar candidatos de mapping") from exc


@api_router.get("/imports/{batch_id}/mapping-candidates")
async def get_import_mapping_candidates(batch_id: str, user=Depends(get_current_user)):
    document = await db.mapping_candidates.find_one(
        _get_mapping_candidates_filter(user, batch_id),
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if not document:
        raise HTTPException(status_code=404, detail="Candidatos de mapping não encontrados")
    return document


@api_router.get("/imports/{batch_id}/mapping-candidates/{source_field}")
async def get_import_mapping_candidates_for_field(
    batch_id: str,
    source_field: str,
    sheet_name: Optional[str] = Query(None),
    user=Depends(get_current_user),
):
    document = await db.mapping_candidates.find_one(
        _get_mapping_candidates_filter(user, batch_id),
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if not document:
        raise HTTPException(status_code=404, detail="Candidatos de mapping não encontrados")
    matches = [
        source for source in document.get("candidates", document.get("sources", []))
        if source.get("source_field", {}).get("source_name") == source_field
        and (sheet_name is None or source.get("source_field", {}).get("sheet_name") == sheet_name)
    ]
    if not matches:
        raise HTTPException(status_code=404, detail="Campo de origem não encontrado")
    return {"batch_id": batch_id, "source_field": source_field, "matches": matches}


def _get_mapping_decisions_filter(user: dict, batch_id: str) -> dict:
    return {"company_id": _safe_company_id(user), "import_batch_id": batch_id}


async def _get_mapping_decisions_response(user: dict, batch_id: str) -> dict:
    documents = await db.mapping_decisions.find(
        _get_mapping_decisions_filter(user, batch_id),
        {"_id": 0},
    ).sort([
        ("source_field.sheet_name", 1),
        ("source_field.source_index", 1),
    ]).to_list(10000)
    if not documents:
        raise HTTPException(status_code=404, detail="Decisões de mapping não encontradas")
    counts = {"auto": 0, "suggest": 0, "confirm": 0, "unknown": 0}
    for document in documents:
        key = str(document.get("decision", "UNKNOWN")).lower()
        counts[key] = counts.get(key, 0) + 1
    first = documents[0]
    return {
        "import_batch_id": batch_id,
        "structure_profile_id": first.get("structure_profile_id"),
        "mapping_engine_version": first.get("mapping_engine_version"),
        "decision_engine_version": first.get("decision_engine_version"),
        "decisions": documents,
        "summary": {"total": len(documents), **counts},
    }


@api_router.post("/imports/{batch_id}/mapping-decisions")
async def analyze_import_mapping_decisions(batch_id: str, user=Depends(get_current_user)):
    """Classify candidates; never applies or mutates a mapping."""
    ensure_db_for_current_loop()
    company_id = _safe_company_id(user)
    mapping_document = await db.mapping_candidates.find_one(
        {"company_id": company_id, "import_batch_id": batch_id},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if not mapping_document:
        raise HTTPException(status_code=404, detail="Candidatos de mapping não encontrados")
    expected = len(mapping_document.get("candidates", mapping_document.get("sources", [])))
    existing_count = await db.mapping_decisions.count_documents({
        **_get_mapping_decisions_filter(user, batch_id),
        "decision_engine_version": DECISION_ENGINE_VERSION,
    })
    if expected and existing_count == expected:
        return await _get_mapping_decisions_response(user, batch_id)

    await log_audit(
        action="DECISION_ANALYSIS_STARTED",
        entity_type="mapping_decisions",
        entity_id=batch_id,
        old_value=None,
        new_value={"mapping_engine_version": mapping_document.get("mapping_engine_version"), "decision_engine_version": DECISION_ENGINE_VERSION},
        user_id=user["id"],
        company_id=company_id,
    )
    now = datetime.now(timezone.utc).isoformat()
    try:
        structure_profile = await db.import_structure_profiles.find_one(
            {"company_id": company_id, "import_batch_id": batch_id}, {"_id": 0}, sort=[("created_at", -1)]
        )
        knowledge_items = await db.company_knowledge.find(
            {"company_id": company_id, "status": {"$in": ["ACTIVE", "CONFLICTED"]}}, {"_id": 0}
        ).to_list(10000)
        learned_evidence_index = build_learned_evidence_index(structure_profile, mapping_document, knowledge_items)
        result = decide_mapping_candidates(mapping_document, learned_evidence_index=learned_evidence_index)
        fusion_applied = [
            decision for decision in result["decisions"]
            if decision.get("knowledge_influence") or any(r["code"] == "LEARNING_CONFLICT" for r in decision.get("blocking_reasons", []))
        ]
        for decision in result["decisions"]:
            document = {
                "id": str(uuid.uuid4()),
                "company_id": company_id,
                "import_batch_id": batch_id,
                "structure_profile_id": mapping_document.get("structure_profile_id"),
                **decision,
                "created_at": now,
                "updated_at": now,
            }
            source_field = document["source_field"]
            await db.mapping_decisions.update_one(
                {
                    "company_id": company_id,
                    "import_batch_id": batch_id,
                    "source_field": source_field,
                    "decision_engine_version": DECISION_ENGINE_VERSION,
                },
                {"$setOnInsert": document},
                upsert=True,
            )
        response = await _get_mapping_decisions_response(user, batch_id)
        await log_audit(
            action="DECISION_ANALYSIS_COMPLETED",
            entity_type="mapping_decisions",
            entity_id=batch_id,
            old_value=None,
            new_value={"summary": response["summary"]},
            user_id=user["id"],
            company_id=company_id,
        )
        if fusion_applied:
            await log_audit(
                action="DECISION_KNOWLEDGE_FUSION_APPLIED",
                entity_type="mapping_decisions",
                entity_id=batch_id,
                old_value=None,
                new_value={"affected_sources": len(fusion_applied), "knowledge_adapter_version": KNOWLEDGE_ADAPTER_VERSION},
                user_id=user["id"],
                company_id=company_id,
            )
        return response
    except Exception as exc:
        await log_audit(
            action="DECISION_ANALYSIS_FAILED",
            entity_type="mapping_decisions",
            entity_id=batch_id,
            old_value=None,
            new_value={"error": str(exc)},
            user_id=user["id"],
            company_id=company_id,
        )
        raise HTTPException(status_code=400, detail="Não foi possível gerar decisões de mapping") from exc


@api_router.get("/imports/{batch_id}/mapping-decisions")
async def get_import_mapping_decisions(batch_id: str, user=Depends(get_current_user)):
    return await _get_mapping_decisions_response(user, batch_id)


@api_router.get("/imports/{batch_id}/mapping-decisions/summary")
async def get_import_mapping_decisions_summary(batch_id: str, user=Depends(get_current_user)):
    response = await _get_mapping_decisions_response(user, batch_id)
    return response["summary"]


@api_router.get("/imports/{batch_id}/mapping-decisions/{source_field}")
async def get_import_mapping_decision_for_field(batch_id: str, source_field: str, user=Depends(get_current_user)):
    response = await _get_mapping_decisions_response(user, batch_id)
    matches = [
        decision for decision in response["decisions"]
        if decision.get("source_field", {}).get("source_name") == source_field
    ]
    if not matches:
        raise HTTPException(status_code=404, detail="Decisão para campo não encontrada")
    return {"batch_id": batch_id, "source_field": source_field, "decisions": matches}


@api_router.post("/imports/{batch_id}/mapping-confirmations")
async def create_import_mapping_confirmation(batch_id: str, request: Request, user=Depends(get_current_user)):
    body = await request.json()
    company_id = _safe_company_id(user)
    source_field = body.get("source_field_identity") or body.get("source_field") or {}
    action = str(body.get("action", "")).upper()
    profile = await db.import_structure_profiles.find_one({"company_id": company_id, "import_batch_id": batch_id}, {"_id": 0}, sort=[("created_at", -1)])
    if not profile or not validate_source(profile, source_field):
        raise HTTPException(status_code=400, detail="Campo de origem não existe no StructureProfile")
    target = body.get("target_field")
    previous = await db.mapping_decisions.find_one({"company_id": company_id, "import_batch_id": batch_id, "source_field": source_field}, {"_id": 0})
    try:
        confirmation = create_confirmation(company_id, batch_id, source_field, target, action, user["id"], previous, body.get("template_id"), body.get("template_version"), body.get("reason", ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if confirmation.get("target_field") and action != "REJECT":
        conflict = await db.mapping_confirmations.find_one({"company_id": company_id, "import_batch_id": batch_id, "target_field": confirmation["target_field"], "decision": "CONFIRMED", "source_field": {"$ne": source_field}}, {"_id": 0})
        if conflict:
            raise HTTPException(status_code=409, detail="TARGET_CONFLICT: target já está confirmado para outro campo")
    await db.mapping_confirmations.insert_one(confirmation)
    await log_audit(action=f"MAPPING_CONFIRMATION_{confirmation['decision']}", entity_type="mapping_confirmation", entity_id=confirmation["id"], old_value=previous, new_value={"target_field": target, "decision": confirmation["decision"]}, user_id=user["id"], company_id=company_id)
    try:
        learning_type = {"CONFIRMED": "MAPPING_CONFIRMED", "REJECTED": "MAPPING_REJECTED", "MODIFIED": "MAPPING_MODIFIED"}[confirmation["decision"]]
        source_pattern = {"normalized_name": source_field.get("source_name", ""), "type": "UNKNOWN", "sheet_context": source_field.get("sheet_name", ""), "patterns": []}
        await _create_learning_event_and_project(company_id, learning_type, "mapping_confirmation", confirmation["id"], {"source_pattern": source_pattern, "target_field": target}, {"decision": confirmation["decision"]}, user["id"])
    except Exception:
        logging.exception("Learning event could not be recorded for confirmation")
    return {key: value for key, value in confirmation.items() if key != "_id"}


@api_router.get("/imports/{batch_id}/mapping-confirmations")
async def list_import_mapping_confirmations(batch_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    return await db.mapping_confirmations.find({"company_id": company_id, "import_batch_id": batch_id}, {"_id": 0}).sort("confirmed_at", 1).to_list(10000)


@api_router.post("/imports/{batch_id}/mapping-template")
async def create_import_mapping_template(batch_id: str, request: Request, user=Depends(get_current_user)):
    body = await request.json()
    company_id = _safe_company_id(user)
    profile = await db.import_structure_profiles.find_one({"company_id": company_id, "import_batch_id": batch_id}, {"_id": 0}, sort=[("created_at", -1)])
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil estrutural não encontrado")
    confirmations = await db.mapping_confirmations.find({"company_id": company_id, "import_batch_id": batch_id}, {"_id": 0}).to_list(10000)
    if not confirmations:
        raise HTTPException(status_code=400, detail="Nenhum mapping confirmado")
    latest = await db.mapping_templates.find_one({"company_id": company_id, "name": body.get("name", "Template de importação")}, sort=[("template_version", -1)])
    version = int(latest.get("template_version", 0)) + 1 if latest else 1
    template = create_mapping_template(company_id, body.get("name", "Template de importação"), profile, confirmations, user["id"], version, latest.get("template_version") if latest else None, body.get("change_reason", ""))
    await db.mapping_templates.insert_one(template)
    await log_audit(action="MAPPING_TEMPLATE_VERSION_CREATED" if latest else "MAPPING_TEMPLATE_CREATED", entity_type="mapping_template", entity_id=template["template_id"], old_value=latest, new_value={"template_version": version, "mapping_count": len(template["mappings"])}, user_id=user["id"], company_id=company_id)
    try:
        await _create_learning_event_and_project(company_id, "TEMPLATE_CREATED", "mapping_template", template["template_id"], {"source_pattern": {"normalized_name": "template", "type": "STRUCTURE", "sheet_context": "", "patterns": []}, "target_field": "template"}, {"template_version": version}, user["id"])
    except Exception:
        logging.exception("Learning event could not be recorded for template")
    return template


@api_router.get("/mapping-templates")
async def list_mapping_templates(user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    return await db.mapping_templates.find({"company_id": company_id, "status": "ACTIVE"}, {"_id": 0}).sort("updated_at", -1).to_list(1000)


@api_router.get("/mapping-templates/{template_id}")
async def get_mapping_template(template_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    template = await db.mapping_templates.find_one({"company_id": company_id, "template_id": template_id}, {"_id": 0}, sort=[("template_version", -1)])
    if not template:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    return template


@api_router.put("/mapping-templates/{template_id}")
async def update_mapping_template(template_id: str, request: Request, user=Depends(get_current_user)):
    body = await request.json()
    company_id = _safe_company_id(user)
    current = await db.mapping_templates.find_one({"company_id": company_id, "template_id": template_id}, {"_id": 0}, sort=[("template_version", -1)])
    if not current:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    update = {"status": body.get("status", current.get("status", "ACTIVE")), "updated_at": utc_now() if "utc_now" in globals() else datetime.now(timezone.utc).isoformat()}
    await db.mapping_templates.update_one({"company_id": company_id, "template_id": template_id, "template_version": current["template_version"]}, {"$set": update})
    return {**current, **update}


@api_router.post("/mapping-templates/{template_id}/apply")
async def preview_mapping_template(template_id: str, request: Request, user=Depends(get_current_user)):
    body = await request.json()
    batch_id = body.get("import_batch_id")
    if not batch_id:
        raise HTTPException(status_code=400, detail="import_batch_id é obrigatório")
    return await _build_mapping_application_plan(batch_id, user, template_id)


async def _build_mapping_application_plan(batch_id: str, user: dict, template_id: str | None = None) -> dict:
    company_id = _safe_company_id(user)
    profile = await db.import_structure_profiles.find_one({"company_id": company_id, "import_batch_id": batch_id}, {"_id": 0}, sort=[("created_at", -1)])
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil estrutural não encontrado")
    template = None
    if template_id:
        template = await db.mapping_templates.find_one({"company_id": company_id, "template_id": template_id}, {"_id": 0}, sort=[("template_version", -1)])
        if not template:
            raise HTTPException(status_code=404, detail="Template não encontrado")
        confirmations = [{"source_field": item["source_field"], "target_field": item["target_field"], "decision": "CONFIRMED"} for item in template.get("mappings", [])]
    else:
        confirmations = await db.mapping_confirmations.find({"company_id": company_id, "import_batch_id": batch_id}, {"_id": 0}).to_list(10000)
        template = await db.mapping_templates.find_one({"company_id": company_id, "template_id": {"$exists": True}}, {"_id": 0}, sort=[("updated_at", -1)])
    plan = build_application_plan(profile, confirmations, template)
    plan.update({"import_batch_id": batch_id, "template_id": template.get("template_id") if template else None, "template_version": template.get("template_version") if template else None})
    return plan


@api_router.post("/imports/{batch_id}/mapping-application/plan")
async def create_mapping_application_plan(batch_id: str, request: Request, user=Depends(get_current_user)):
    body = await request.json()
    return await _build_mapping_application_plan(batch_id, user, body.get("template_id"))


@api_router.get("/imports/{batch_id}/mapping-application/plan")
async def get_mapping_application_plan(batch_id: str, user=Depends(get_current_user)):
    return await _build_mapping_application_plan(batch_id, user)


@api_router.post("/imports/{batch_id}/mapping-application/apply")
async def apply_mapping_application(batch_id: str, request: Request, user=Depends(get_current_user)):
    body = await request.json()
    company_id = _safe_company_id(user)
    template_id = body.get("template_id")
    template = await db.mapping_templates.find_one({"company_id": company_id, "template_id": template_id}, {"_id": 0}, sort=[("template_version", -1)]) if template_id else None
    plan = await _build_mapping_application_plan(batch_id, user, template_id)
    if plan["status"] == "BLOCKED":
        raise HTTPException(status_code=409, detail="Application plan is blocked")
    version = template.get("template_version") if template else 0
    retry = bool(body.get("retry", False))
    existing = await db.mapping_applications.find_one({"company_id": company_id, "import_batch_id": batch_id, "template_id": template_id, "template_version": version, "run_number": 1}, {"_id": 0})
    run_number = 1
    if existing and existing.get("status") in {"COMPLETED", "RUNNING"}:
        return existing
    if existing and existing.get("status") == "PARTIAL" and not retry:
        existing_records = await db.standard_records.count_documents({"company_id": company_id, "application_id": existing["application_id"]})
        if existing_records:
            return existing
    if retry:
        last_run = await db.mapping_applications.find_one({"company_id": company_id, "import_batch_id": batch_id, "template_id": template_id, "template_version": version}, sort=[("run_number", -1)])
        run_number = int(last_run.get("run_number", 1)) + 1 if last_run else 2
    application_id = "application-" + str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    application = {"application_id": application_id, "company_id": company_id, "import_batch_id": batch_id, "template_id": template_id, "template_version": version, "run_number": run_number, "retry_of_application_id": existing.get("application_id") if retry and existing else None, "status": "RUNNING", "total_records": 0, "processed_records": 0, "created_records": 0, "blocked_records": sum(item["status"] == "BLOCKED" for item in plan["items"]), "error_records": 0, "started_at": now, "completed_at": None}
    await db.mapping_applications.insert_one(application)
    await log_audit(action="MAPPING_APPLICATION_STARTED", entity_type="mapping_application", entity_id=application_id, old_value=None, new_value={"batch_id": batch_id}, user_id=user["id"], company_id=company_id)
    try:
        raw_records = await db.raw_records.find({"company_id": company_id, "import_batch_id": batch_id}, {"_id": 0}).sort("source_row", 1).to_list(100000)
        existing_source_ids = {
            item.get("source_record_id")
            async for item in db.standard_records.find(
                {"company_id": company_id, "import_batch_id": batch_id, "mapping_template_id": template_id, "mapping_template_version": version},
                {"source_record_id": 1},
            )
        }
        raw_records = [record for record in raw_records if record.get("id") not in existing_source_ids]
        confirmations = await db.mapping_confirmations.find({"company_id": company_id, "import_batch_id": batch_id}, {"_id": 0}).to_list(10000)
        if template:
            confirmations = [{"source_field": item["source_field"], "target_field": item["target_field"], "decision": "CONFIRMED"} for item in template.get("mappings", [])]
        records, errors = apply_standard_records(raw_records, plan, application_id, company_id, batch_id, template)
        if records:
            await db.standard_records.insert_many(records, ordered=False)
        if errors:
            await db.application_errors.insert_many(errors, ordered=False)
        status = "PARTIAL" if errors or application["blocked_records"] else "COMPLETED"
        update = {"status": status, "total_records": len(raw_records), "processed_records": len(records), "created_records": len(records), "error_records": len(errors), "completed_at": datetime.now(timezone.utc).isoformat()}
        await db.mapping_applications.update_one({"application_id": application_id, "company_id": company_id}, {"$set": update})
        await log_audit(action="MAPPING_APPLICATION_PARTIAL" if status == "PARTIAL" else "MAPPING_APPLICATION_COMPLETED", entity_type="mapping_application", entity_id=application_id, old_value=application, new_value=update, user_id=user["id"], company_id=company_id)
        try:
            learning_type = "APPLICATION_PARTIAL" if status == "PARTIAL" else "APPLICATION_COMPLETED"
            await _create_learning_event_and_project(company_id, learning_type, "mapping_application", application_id, {"source_pattern": {"normalized_name": "application", "type": "APPLICATION", "sheet_context": "", "patterns": []}, "target_field": "application"}, {"created_records": len(records), "error_records": len(errors)}, user["id"])
        except Exception:
            logging.exception("Learning event could not be recorded for application")
        return {**application, **update}
    except Exception as exc:
        await db.mapping_applications.update_one({"application_id": application_id, "company_id": company_id}, {"$set": {"status": "FAILED", "completed_at": datetime.now(timezone.utc).isoformat()}})
        await log_audit(action="MAPPING_APPLICATION_FAILED", entity_type="mapping_application", entity_id=application_id, old_value=application, new_value={"error": str(exc)}, user_id=user["id"], company_id=company_id)
        raise HTTPException(status_code=400, detail="Falha na aplicação do mapping") from exc


@api_router.get("/imports/{batch_id}/mapping-application")
async def get_mapping_application(batch_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    return await db.mapping_applications.find({"company_id": company_id, "import_batch_id": batch_id}, {"_id": 0}).sort("started_at", -1).to_list(100)


@api_router.get("/mapping-applications/{application_id}")
async def get_mapping_application_status(application_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    application = await db.mapping_applications.find_one({"company_id": company_id, "application_id": application_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Aplicação não encontrada")
    return application


async def _rebuild_company_knowledge(company_id: str, user_id: str | None = None) -> list[dict]:
    events = await db.learning_events.find({"company_id": company_id}, {"_id": 0}).sort("created_at", 1).to_list(100000)
    knowledge = project_knowledge(events)
    await db.company_knowledge.delete_many({"company_id": company_id})
    if knowledge:
        await db.company_knowledge.insert_many(knowledge, ordered=False)
    await db.learning_observations.delete_many({"company_id": company_id})
    if knowledge:
        await db.learning_observations.insert_many(knowledge, ordered=False)
    await db.learning_versions.update_one(
        {"company_id": company_id, "learning_version": LEARNING_VERSION},
        {"$set": {"company_id": company_id, "learning_version": LEARNING_VERSION, "last_rebuilt_at": datetime.now(timezone.utc).isoformat(), "rebuilt_by": user_id}},
        upsert=True,
    )
    return knowledge


async def _create_learning_event_and_project(company_id: str, event_type: str, source: str, source_id: str, subject: dict, observation: dict, user_id: str | None = None, event_id: str | None = None):
    event = create_learning_event(company_id, event_type, source, source_id, subject, observation, user_id, event_id=event_id)
    existing = await db.learning_events.find_one({"company_id": company_id, "event_id": event["event_id"]}, {"_id": 0})
    if existing:
        knowledge = await db.company_knowledge.find({"company_id": company_id}, {"_id": 0}).to_list(100000)
        return existing, knowledge
    try:
        await db.learning_events.insert_one(event)
    except Exception as exc:
        if getattr(exc, "code", None) == 11000:
            return event, await db.company_knowledge.find({"company_id": company_id}, {"_id": 0}).to_list(100000)
        raise
    knowledge = await _rebuild_company_knowledge(company_id, user_id)
    await log_audit("LEARNING_EVENT_CREATED", "learning_event", event["event_id"], None, {"event_type": event_type, "source": source}, user_id, company_id)
    return event, knowledge


@api_router.post("/learning/feedback")
async def create_learning_feedback(request: Request, user=Depends(get_current_user)):
    body = await request.json()
    company_id = _safe_company_id(user)
    action = str(body.get("action", "")).upper()
    source_pattern = dict(body.get("source_pattern") or {})
    target_field = body.get("target_field")
    if not source_pattern or not target_field:
        raise HTTPException(status_code=400, detail="source_pattern e target_field são obrigatórios")
    try:
        event_type = feedback_event_type(action)
        signature = pattern_signature(source_pattern, target_field)
        subject = {"source_pattern": {key: source_pattern.get(key) for key in ("normalized_name", "type", "sheet_context", "patterns") if source_pattern.get(key) is not None}, "target_field": target_field, "pattern_signature": signature}
        import hashlib
        idempotency_key = body.get("idempotency_key") or hashlib.sha256(f"{company_id}:{action}:{signature}:{target_field}".encode()).hexdigest()
        event, knowledge = await _create_learning_event_and_project(company_id, event_type, "learning_feedback", body.get("source_id", signature), subject, {"action": action}, user["id"], event_id="learning-event-" + idempotency_key[:24])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    feedback = {"feedback_id": "feedback-" + event["event_id"], "company_id": company_id, "event_id": event["event_id"], "action": action, "source_pattern": subject["source_pattern"], "target_field": target_field, "created_by": user["id"], "created_at": event["created_at"], "learning_version": LEARNING_VERSION}
    try:
        await db.learning_feedback.insert_one(feedback)
    except Exception as exc:
        if getattr(exc, "code", None) != 11000:
            raise
    return {"event": event, "feedback": feedback, "knowledge": [item for item in knowledge if item.get("pattern_signature") == signature]}


@api_router.get("/learning/feedback")
async def list_learning_feedback(user=Depends(get_current_user)):
    return await db.learning_feedback.find({"company_id": _safe_company_id(user)}, {"_id": 0}).sort("created_at", -1).to_list(10000)


@api_router.get("/learning/knowledge")
async def list_company_knowledge(user=Depends(get_current_user)):
    return await db.company_knowledge.find({"company_id": _safe_company_id(user)}, {"_id": 0}).sort("confidence", -1).to_list(10000)


@api_router.get("/learning/knowledge/summary")
async def get_company_knowledge_summary(user=Depends(get_current_user)):
    knowledge = await db.company_knowledge.find({"company_id": _safe_company_id(user)}, {"_id": 0}).to_list(10000)
    return build_learning_summary(knowledge)


@api_router.get("/learning/knowledge/{knowledge_id}")
async def get_company_knowledge_item(knowledge_id: str, user=Depends(get_current_user)):
    item = await db.company_knowledge.find_one({"company_id": _safe_company_id(user), "observation_id": knowledge_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge não encontrado")
    return item


@api_router.post("/learning/knowledge/{knowledge_id}/disable")
async def disable_company_knowledge(knowledge_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    item = await db.company_knowledge.find_one({"company_id": company_id, "observation_id": knowledge_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge não encontrado")
    subject = {"source_pattern": item.get("source_pattern", {}), "target_field": item.get("target_field"), "pattern_signature": item.get("pattern_signature")}
    await _create_learning_event_and_project(company_id, "KNOWLEDGE_DISABLED", "knowledge", knowledge_id, subject, {}, user["id"])
    await log_audit("LEARNING_DISABLED", "company_knowledge", knowledge_id, item, None, user["id"], company_id)
    return {"disabled": True, "observation_id": knowledge_id}


@api_router.post("/learning/knowledge/{knowledge_id}/reactivate")
async def reactivate_company_knowledge(knowledge_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    item = await db.company_knowledge.find_one({"company_id": company_id, "observation_id": knowledge_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge não encontrado")
    subject = {"source_pattern": item.get("source_pattern", {}), "target_field": item.get("target_field"), "pattern_signature": item.get("pattern_signature")}
    await _create_learning_event_and_project(company_id, "KNOWLEDGE_REACTIVATED", "knowledge", knowledge_id, subject, {}, user["id"])
    return {"reactivated": True, "observation_id": knowledge_id}


@api_router.get("/learning/events")
async def list_learning_events(user=Depends(get_current_user)):
    return await db.learning_events.find({"company_id": _safe_company_id(user)}, {"_id": 0}).sort("created_at", -1).to_list(10000)


@api_router.post("/learning/rebuild")
async def rebuild_learning_knowledge(user=Depends(get_current_user)):
    knowledge = await _rebuild_company_knowledge(_safe_company_id(user), user["id"])
    await log_audit("LEARNING_OBSERVATION_UPDATED", "company_knowledge", None, None, {"count": len(knowledge), "rebuild": True}, user["id"], _safe_company_id(user))
    return {"rebuilt": True, "summary": build_learning_summary(knowledge)}


async def _gather_commercial_context_sources(company_id: str, opportunity: dict) -> tuple:
    """Fetch only already-existing, tenant-scoped commercial data. Never fabricates."""
    client = None
    related_opportunities = None
    if opportunity.get("client_id"):
        client = await db.clients.find_one({"id": opportunity["client_id"], "company_id": company_id}, {"_id": 0})
        related_docs = await db.opportunities.find(
            {"company_id": company_id, "client_id": opportunity["client_id"], "deleted": {"$ne": True}},
            {"_id": 0, "status": 1, "estimated_value": 1},
        ).to_list(1000)
        related_opportunities = [{"status": doc.get("status"), "value": doc.get("estimated_value")} for doc in related_docs]

    proposal = None
    if opportunity.get("proposal_id"):
        proposal = await db.proposals.find_one({"id": opportunity["proposal_id"], "company_id": company_id}, {"_id": 0})

    seller_stats = None
    seller_id = opportunity.get("seller_id") or opportunity.get("user_id")
    if seller_id:
        seller_docs = await db.opportunities.find(
            {"company_id": company_id, "$or": [{"seller_id": seller_id}, {"user_id": seller_id}], "deleted": {"$ne": True}},
            {"_id": 0, "status": 1},
        ).to_list(5000)
        seller_stats = {
            "total": len(seller_docs),
            "won": sum(1 for doc in seller_docs if doc.get("status") == "WON"),
            "lost": sum(1 for doc in seller_docs if doc.get("status") == "LOST"),
            "open": sum(1 for doc in seller_docs if doc.get("status") in {"OPEN", "WAITING", "HUMAN_ACTION"}),
        }
    return client, proposal, related_opportunities, seller_stats


@api_router.post("/commercial-context/{opportunity_id}/refresh")
async def refresh_commercial_context(opportunity_id: str, user=Depends(get_current_user)):
    """Rebuild the Commercial Context projection. Never mutates the Opportunity."""
    company_id = _safe_company_id(user)
    opportunity = await db.opportunities.find_one(
        {"id": opportunity_id, "company_id": company_id, "deleted": {"$ne": True}}, {"_id": 0}
    )
    if not opportunity:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")

    try:
        client, proposal, related_opportunities, seller_stats = await _gather_commercial_context_sources(company_id, opportunity)
        context = build_commercial_context(company_id, opportunity, client, proposal, related_opportunities, seller_stats)

        existing_same_snapshot = await db.commercial_contexts.find_one(
            {
                "company_id": company_id,
                "opportunity_id": opportunity_id,
                "snapshot_version": COMMERCIAL_CONTEXT_VERSION,
                "source_snapshot_hash": context["source_snapshot_hash"],
            },
            {"_id": 0},
        )
        if existing_same_snapshot:
            return existing_same_snapshot

        had_previous = await db.commercial_contexts.count_documents({"company_id": company_id, "opportunity_id": opportunity_id}) > 0
        now_iso = datetime.now(timezone.utc).isoformat()
        document = {**context, "created_at": now_iso, "updated_at": now_iso}
        await db.commercial_contexts.insert_one(document)
        await log_audit(
            action="COMMERCIAL_CONTEXT_REFRESHED" if had_previous else "COMMERCIAL_CONTEXT_CREATED",
            entity_type="commercial_context",
            entity_id=context["context_id"],
            old_value=None,
            new_value={"opportunity_id": opportunity_id, "data_quality": context["context"]["data_quality"]},
            user_id=user["id"],
            company_id=company_id,
        )
        return document
    except Exception as exc:
        await log_audit(
            action="COMMERCIAL_CONTEXT_FAILED",
            entity_type="commercial_context",
            entity_id=opportunity_id,
            old_value=None,
            new_value={"error": str(exc)},
            user_id=user["id"],
            company_id=company_id,
        )
        raise HTTPException(status_code=400, detail="Não foi possível gerar o contexto comercial") from exc


@api_router.get("/commercial-context/summary")
async def get_commercial_context_summary(user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    pipeline = [
        {"$match": {"company_id": company_id}},
        {"$sort": {"created_at": -1}},
        {"$group": {"_id": "$opportunity_id", "doc": {"$first": "$$ROOT"}}},
    ]
    docs = [item["doc"] async for item in db.commercial_contexts.aggregate(pipeline)]
    total = len(docs)
    quality_counts = {"COMPLETE": 0, "PARTIAL": 0, "LIMITED": 0, "INSUFFICIENT": 0}
    high_priority_signals = 0
    stale_opportunities = 0
    for doc in docs:
        quality = doc.get("context", {}).get("data_quality", "INSUFFICIENT")
        quality_counts[quality] = quality_counts.get(quality, 0) + 1
        signals = doc.get("context", {}).get("signals", [])
        high_priority_signals += sum(1 for signal in signals if signal.get("severity") in {"HIGH", "CRITICAL"})
        if any(signal.get("signal") == "STALE_OPPORTUNITY" for signal in signals):
            stale_opportunities += 1
    return {
        "total_contexts": total,
        "complete": quality_counts["COMPLETE"],
        "partial": quality_counts["PARTIAL"],
        "limited": quality_counts["LIMITED"],
        "high_priority_signals": high_priority_signals,
        "stale_opportunities": stale_opportunities,
    }


@api_router.get("/commercial-context/{opportunity_id}")
async def get_commercial_context(opportunity_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    context = await db.commercial_contexts.find_one(
        {"company_id": company_id, "opportunity_id": opportunity_id}, {"_id": 0}, sort=[("created_at", -1)]
    )
    if not context:
        raise HTTPException(status_code=404, detail="Contexto comercial não encontrado")
    return context


async def _gather_sales_intelligence_inputs(company_id: str, opportunity: dict) -> tuple:
    """Reuse existing tenant-scoped data only; never touches RawRecords."""
    knowledge_items = await db.company_knowledge.find(
        {"company_id": company_id, "status": {"$in": ["ACTIVE", "CONFLICTED"]}}, {"_id": 0}
    ).to_list(50)
    related_loss_reasons = []
    if opportunity.get("client_id"):
        lost_docs = await db.opportunities.find(
            {"company_id": company_id, "client_id": opportunity["client_id"], "status": "LOST", "deleted": {"$ne": True}},
            {"_id": 0, "loss_reason": 1},
        ).to_list(200)
        related_loss_reasons = [doc.get("loss_reason") for doc in lost_docs if doc.get("loss_reason")]
    return knowledge_items, related_loss_reasons


@api_router.post("/sales-intelligence/{opportunity_id}/analyze")
async def analyze_sales_intelligence(opportunity_id: str, user=Depends(get_current_user)):
    """Advisory-only analysis. Never executes an action or mutates the Opportunity."""
    company_id = _safe_company_id(user)
    opportunity = await db.opportunities.find_one(
        {"id": opportunity_id, "company_id": company_id, "deleted": {"$ne": True}}, {"_id": 0}
    )
    if not opportunity:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")

    await log_audit(
        action="SALES_INTELLIGENCE_STARTED",
        entity_type="sales_insight",
        entity_id=opportunity_id,
        old_value=None,
        new_value=None,
        user_id=user["id"],
        company_id=company_id,
    )
    try:
        commercial_context = await refresh_commercial_context(opportunity_id, user)
        knowledge_items, related_loss_reasons = await _gather_sales_intelligence_inputs(company_id, opportunity)
        insight = build_sales_insight(
            company_id, opportunity, commercial_context,
            knowledge_items=knowledge_items, related_loss_reasons=related_loss_reasons,
        )

        existing_same_snapshot = await db.sales_insights.find_one(
            {
                "company_id": company_id,
                "opportunity_id": opportunity_id,
                "engine_version": SALES_INTELLIGENCE_VERSION,
                "source_snapshot_hash": insight["source_snapshot_hash"],
            },
            {"_id": 0},
        )
        if existing_same_snapshot:
            return existing_same_snapshot

        now_iso = datetime.now(timezone.utc).isoformat()
        document = {**insight, "created_at": now_iso, "updated_at": now_iso}
        await db.sales_insights.insert_one(document)
        await log_audit(
            action="SALES_INTELLIGENCE_COMPLETED",
            entity_type="sales_insight",
            entity_id=insight["insight_id"],
            old_value=None,
            new_value={"priority": insight["priority"], "urgency": insight["urgency"]},
            user_id=user["id"],
            company_id=company_id,
        )
        return document
    except Exception as exc:
        await log_audit(
            action="SALES_INTELLIGENCE_FAILED",
            entity_type="sales_insight",
            entity_id=opportunity_id,
            old_value=None,
            new_value={"error": str(exc)},
            user_id=user["id"],
            company_id=company_id,
        )
        raise HTTPException(status_code=400, detail="Não foi possível gerar a análise comercial") from exc


@api_router.get("/sales-intelligence/summary")
async def get_sales_intelligence_summary(user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    pipeline = [
        {"$match": {"company_id": company_id}},
        {"$sort": {"created_at": -1}},
        {"$group": {"_id": "$opportunity_id", "doc": {"$first": "$$ROOT"}}},
    ]
    docs = [item["doc"] async for item in db.sales_insights.aggregate(pipeline)]
    priority_counts: dict[str, int] = {}
    urgency_counts: dict[str, int] = {}
    for doc in docs:
        priority_counts[doc.get("priority", "P4_NONE")] = priority_counts.get(doc.get("priority", "P4_NONE"), 0) + 1
        urgency_counts[doc.get("urgency", "NONE")] = urgency_counts.get(doc.get("urgency", "NONE"), 0) + 1
    return {
        "total_insights": len(docs),
        "by_priority": priority_counts,
        "by_urgency": urgency_counts,
        "overdue_followups": sum(1 for doc in docs if doc.get("insight", {}).get("followup_state", {}).get("state") in {"OVERDUE", "URGENT"}),
    }


@api_router.get("/sales-intelligence/{opportunity_id}")
async def get_sales_intelligence(opportunity_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    insight = await db.sales_insights.find_one(
        {"company_id": company_id, "opportunity_id": opportunity_id}, {"_id": 0}, sort=[("created_at", -1)]
    )
    if not insight:
        raise HTTPException(status_code=404, detail="Análise comercial não encontrada")
    return insight


async def _load_action_plan_inputs(opportunity_id: str, user: dict) -> tuple[dict, dict, dict]:
    company_id = _safe_company_id(user)
    opportunity = await db.opportunities.find_one(
        {"id": opportunity_id, "company_id": company_id, "deleted": {"$ne": True}}, {"_id": 0}
    )
    if not opportunity:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")
    insight = await db.sales_insights.find_one(
        {"company_id": company_id, "opportunity_id": opportunity_id}, {"_id": 0}, sort=[("created_at", -1)]
    )
    if not insight:
        raise HTTPException(status_code=409, detail="STALE_INSIGHT: gere uma nova análise comercial antes do plano")
    context = await db.commercial_contexts.find_one(
        {"company_id": company_id, "opportunity_id": opportunity_id}, {"_id": 0}, sort=[("created_at", -1)]
    )
    if not context:
        raise HTTPException(status_code=409, detail="Contexto comercial não encontrado")
    return opportunity, insight, context


@api_router.post("/action-plans/{opportunity_id}/generate")
async def generate_action_plan(opportunity_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    await log_audit(
        action="ACTION_PLAN_GENERATION_STARTED",
        entity_type="action_plan",
        entity_id=opportunity_id,
        old_value=None,
        new_value=None,
        user_id=user["id"],
        company_id=company_id,
    )
    try:
        opportunity, insight, context = await _load_action_plan_inputs(opportunity_id, user)
        plan = build_action_plan(company_id, opportunity, insight, context)
        existing = await db.action_plans.find_one(
            {
                "company_id": company_id,
                "opportunity_id": opportunity_id,
                "engine_version": ACTION_PLANNING_VERSION,
                "source_snapshot_hash": plan["source_snapshot_hash"],
            },
            {"_id": 0},
        )
        if existing:
            return existing

        await db.action_plans.update_many(
            {
                "company_id": company_id,
                "opportunity_id": opportunity_id,
                "status": {"$in": ["DRAFT", "PENDING_REVIEW", "APPROVED"]},
                "source_snapshot_hash": {"$ne": plan["source_snapshot_hash"]},
            },
            {"$set": {"status": "SUPERSEDED", "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        await db.action_plans.insert_one(plan)
        await log_audit(
            action="ACTION_PLAN_GENERATED",
            entity_type="action_plan",
            entity_id=plan["action_plan_id"],
            old_value=None,
            new_value={"opportunity_id": opportunity_id, "status": plan["status"], "actions": len(plan["actions"])},
            user_id=user["id"],
            company_id=company_id,
        )
        return plan
    except HTTPException as exc:
        await log_audit(
            action="ACTION_PLAN_GENERATION_FAILED",
            entity_type="action_plan",
            entity_id=opportunity_id,
            old_value=None,
            new_value={"error": str(exc.detail)},
            user_id=user["id"],
            company_id=company_id,
        )
        raise
    except ValueError as exc:
        await log_audit(
            action="ACTION_PLAN_GENERATION_FAILED",
            entity_type="action_plan",
            entity_id=opportunity_id,
            old_value=None,
            new_value={"error": str(exc)},
            user_id=user["id"],
            company_id=company_id,
        )
        status_code = 409 if "STALE" in str(exc) or "MISMATCH" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except Exception as exc:
        await log_audit(
            action="ACTION_PLAN_GENERATION_FAILED",
            entity_type="action_plan",
            entity_id=opportunity_id,
            old_value=None,
            new_value={"error": str(exc)},
            user_id=user["id"],
            company_id=company_id,
        )
        raise HTTPException(status_code=400, detail="Não foi possível gerar o plano de ação") from exc


@api_router.get("/action-plans/summary")
async def get_action_plan_summary(user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    pipeline = [
        {"$match": {"company_id": company_id}},
        {"$sort": {"updated_at": -1}},
        {"$group": {"_id": "$opportunity_id", "doc": {"$first": "$$ROOT"}}},
    ]
    docs = [item["doc"] async for item in db.action_plans.aggregate(pipeline)]
    counts = {status.lower(): 0 for status in ["DRAFT", "PENDING_REVIEW", "APPROVED", "REJECTED", "EXPIRED"]}
    for doc in docs:
        status = doc.get("status", "DRAFT").lower()
        if status in counts:
            counts[status] += 1
    return {
        "total": len(docs),
        **counts,
        "high_priority": sum(1 for doc in docs if doc.get("plan", {}).get("priority") in {"P0_CRITICAL", "P1_HIGH"}),
    }


@api_router.get("/action-plans/{opportunity_id}")
async def get_action_plan(opportunity_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    plan = await db.action_plans.find_one(
        {"company_id": company_id, "opportunity_id": opportunity_id, "status": {"$ne": "SUPERSEDED"}},
        {"_id": 0},
        sort=[("updated_at", -1)],
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Action Plan não encontrado")
    return plan


@api_router.post("/action-plans/{plan_id}/approve")
async def approve_action_plan(plan_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    plan = await db.action_plans.find_one({"company_id": company_id, "action_plan_id": plan_id}, {"_id": 0})
    if not plan:
        raise HTTPException(status_code=404, detail="Action Plan não encontrado")
    if plan.get("status") not in {"DRAFT", "PENDING_REVIEW"}:
        raise HTTPException(status_code=409, detail="Action Plan não pode ser aprovado neste estado")
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.action_plans.update_one(
        {"company_id": company_id, "action_plan_id": plan_id},
        {"$set": {"status": "APPROVED", "updated_at": now_iso}},
    )
    await log_audit("ACTION_PLAN_APPROVED", "action_plan", plan_id, {"status": plan["status"]}, {"status": "APPROVED"}, user["id"], company_id)
    plan["status"] = "APPROVED"
    plan["updated_at"] = now_iso
    return plan


@api_router.post("/action-plans/{plan_id}/reject")
async def reject_action_plan(plan_id: str, request: Request, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    plan = await db.action_plans.find_one({"company_id": company_id, "action_plan_id": plan_id}, {"_id": 0})
    if not plan:
        raise HTTPException(status_code=404, detail="Action Plan não encontrado")
    if plan.get("status") not in {"DRAFT", "PENDING_REVIEW"}:
        raise HTTPException(status_code=409, detail="Action Plan não pode ser rejeitado neste estado")
    body = await request.json()
    reason = str(body.get("reason") or "Rejeitado pelo usuário.").strip()
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.action_plans.update_one(
        {"company_id": company_id, "action_plan_id": plan_id},
        {"$set": {"status": "REJECTED", "rejection": {"reason": reason, "user_id": user["id"], "timestamp": now_iso}, "updated_at": now_iso}},
    )
    await log_audit("ACTION_PLAN_REJECTED", "action_plan", plan_id, {"status": plan["status"]}, {"status": "REJECTED", "reason": reason}, user["id"], company_id)
    plan["status"] = "REJECTED"
    plan["rejection"] = {"reason": reason, "user_id": user["id"], "timestamp": now_iso}
    plan["updated_at"] = now_iso
    return plan


async def _load_execution_inputs(action_plan_id: str, action_id: str, user: dict) -> tuple[dict, dict, dict, dict, dict]:
    company_id = _safe_company_id(user)
    plan = await db.action_plans.find_one(
        {"company_id": company_id, "action_plan_id": action_plan_id}, {"_id": 0}
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Action Plan não encontrado")
    action = next((item for item in plan.get("actions", []) if item.get("action_id") == action_id), None)
    if not action:
        raise HTTPException(status_code=404, detail="Action não pertence ao plano")
    opportunity = await db.opportunities.find_one(
        {"company_id": company_id, "id": plan.get("opportunity_id"), "deleted": {"$ne": True}}, {"_id": 0}
    )
    insight = await db.sales_insights.find_one(
        {"company_id": company_id, "opportunity_id": plan.get("opportunity_id")}, {"_id": 0}, sort=[("created_at", -1)]
    )
    context = await db.commercial_contexts.find_one(
        {"company_id": company_id, "opportunity_id": plan.get("opportunity_id")}, {"_id": 0}, sort=[("created_at", -1)]
    )
    if not opportunity or not insight or not context:
        raise HTTPException(status_code=409, detail="Execution blocked: cadeia comercial incompleta")
    return plan, action, opportunity, insight, context


@api_router.post("/execution-jobs/{action_plan_id}/create")
async def create_execution_job(action_plan_id: str, request: Request, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    body = await request.json()
    action_id = str(body.get("action_id") or "").strip()
    mode = str(body.get("mode") or "SIMULATION").upper()
    try:
        plan, action, opportunity, insight, context = await _load_execution_inputs(action_plan_id, action_id, user)
        job = build_execution_job(
            company_id,
            plan,
            action,
            opportunity,
            insight,
            context,
            mode=mode,
            requested_policy=body.get("policy"),
            expires_at=body.get("expires_at"),
        )
        existing = await db.execution_jobs.find_one(
            {
                "company_id": company_id,
                "action_plan_id": action_plan_id,
                "action_id": action_id,
                "mode": mode,
                "executor_version": ACTION_EXECUTOR_VERSION,
                "source_snapshot_hash": job["source_snapshot_hash"],
            },
            {"_id": 0},
        )
        if existing:
            return existing
        await db.execution_jobs.insert_one(job)
        await log_audit(
            "EXECUTION_JOB_CREATED", "execution_job", job["execution_job_id"], None,
            {"action_plan_id": action_plan_id, "action_id": action_id, "mode": mode}, user["id"], company_id,
        )
        return job
    except (HTTPException, ValueError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        await log_audit(
            "EXECUTION_JOB_BLOCKED", "execution_job", action_plan_id, None,
            {"action_id": action_id, "mode": mode, "reason": str(detail)}, user["id"], company_id,
        )
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await log_audit(
            "EXECUTION_JOB_FAILED", "execution_job", action_plan_id, None,
            {"action_id": action_id, "error": str(exc)}, user["id"], company_id,
        )
        raise HTTPException(status_code=400, detail="Não foi possível criar o Execution Job") from exc


@api_router.post("/execution-jobs/{job_id}/simulate")
async def simulate_execution(job_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    job = await db.execution_jobs.find_one({"company_id": company_id, "execution_job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Execution Job não encontrado")
    await log_audit(
        "EXECUTION_JOB_SIMULATION_STARTED", "execution_job", job_id, {"status": job.get("status")}, None,
        user["id"], company_id,
    )
    try:
        simulated = simulate_execution_job(job)
        await db.execution_jobs.replace_one(
            {"company_id": company_id, "execution_job_id": job_id}, simulated
        )
        if simulated["status"] == "EXPIRED":
            await log_audit(
                "EXECUTION_JOB_FAILED", "execution_job", job_id, {"status": job.get("status")},
                {"status": "EXPIRED", "external_side_effect": False}, user["id"], company_id,
            )
            return simulated
        await log_audit(
            "EXECUTION_JOB_SIMULATED", "execution_job", job_id, {"status": job.get("status")},
            {"status": simulated["status"], "external_side_effect": False}, user["id"], company_id,
        )
        return simulated
    except ValueError as exc:
        await log_audit(
            "EXECUTION_JOB_FAILED", "execution_job", job_id, {"status": job.get("status")},
            {"error": str(exc)}, user["id"], company_id,
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@api_router.get("/execution-jobs")
async def list_execution_jobs(
    status: str | None = None,
    channel: str | None = None,
    action_type: str | None = None,
    opportunity_id: str | None = None,
    date: str | None = None,
    user=Depends(get_current_user),
):
    query: dict = {"company_id": _safe_company_id(user)}
    for key, value in {
        "status": status,
        "channel": channel,
        "action_type": action_type,
        "opportunity_id": opportunity_id,
    }.items():
        if value:
            query[key] = value
    if date:
        query["created_at"] = {"$gte": date}
    return await db.execution_jobs.find(query, {"_id": 0}).sort("created_at", -1).to_list(10000)


@api_router.get("/execution-jobs/{job_id}")
async def get_execution_job(job_id: str, user=Depends(get_current_user)):
    job = await db.execution_jobs.find_one(
        {"company_id": _safe_company_id(user), "execution_job_id": job_id}, {"_id": 0}
    )
    if not job:
        raise HTTPException(status_code=404, detail="Execution Job não encontrado")
    return job


@api_router.post("/execution-jobs/{job_id}/cancel")
async def cancel_execution(job_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    job = await db.execution_jobs.find_one({"company_id": company_id, "execution_job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Execution Job não encontrado")
    try:
        cancelled = cancel_execution_job(job)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.execution_jobs.replace_one({"company_id": company_id, "execution_job_id": job_id}, cancelled)
    await log_audit(
        "EXECUTION_JOB_CANCELLED", "execution_job", job_id, {"status": job.get("status")},
        {"status": "CANCELLED"}, user["id"], company_id,
    )
    return cancelled


async def _load_communication_inputs(execution_job_id: str, user: dict) -> tuple[dict, dict, dict, dict | None]:
    company_id = _safe_company_id(user)
    job = await db.execution_jobs.find_one(
        {"company_id": company_id, "execution_job_id": execution_job_id}, {"_id": 0}
    )
    if not job:
        raise HTTPException(status_code=404, detail="Execution Job não encontrado")
    plan = await db.action_plans.find_one(
        {"company_id": company_id, "action_plan_id": job.get("action_plan_id")}, {"_id": 0}
    )
    opportunity = await db.opportunities.find_one(
        {"company_id": company_id, "id": job.get("opportunity_id"), "deleted": {"$ne": True}}, {"_id": 0}
    )
    if not plan or not opportunity:
        raise HTTPException(status_code=409, detail="Communication blocked: cadeia de execução inconsistente")
    client = None
    if opportunity.get("client_id"):
        client = await db.clients.find_one(
            {"company_id": company_id, "id": opportunity["client_id"], "deleted": {"$ne": True}}, {"_id": 0}
        )
        if not client:
            raise HTTPException(status_code=409, detail="MISSING_RECIPIENT_CLIENT")
    return job, plan, opportunity, client


@api_router.post("/communication-requests/{execution_job_id}/prepare")
async def prepare_communication_request(execution_job_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    await log_audit(
        "COMMUNICATION_REQUEST_RECEIVED", "communication_request", execution_job_id, None,
        {"execution_job_id": execution_job_id}, user["id"], company_id,
    )
    try:
        job, plan, opportunity, client = await _load_communication_inputs(execution_job_id, user)
        communication = build_communication_request(company_id, job, plan, opportunity, client)
        existing = await db.communication_requests.find_one(
            {
                "company_id": company_id,
                "execution_job_id": execution_job_id,
                "communication_request_hash": communication["communication_request_hash"],
                "gateway_version": COMMUNICATION_GATEWAY_VERSION,
            },
            {"_id": 0},
        )
        if existing:
            return existing
        await db.communication_requests.insert_one(communication)
        if communication["status"] == "PREPARED":
            await log_audit(
                "COMMUNICATION_REQUEST_VALIDATED", "communication_request", communication["request_id"], None,
                {"channel": communication["channel"]}, user["id"], company_id,
            )
            await log_audit(
                "COMMUNICATION_REQUEST_PREPARED", "communication_request", communication["request_id"], None,
                {"adapter": communication["adapter"], "external_side_effect": False}, user["id"], company_id,
            )
        elif communication["status"] == "BLOCKED":
            await log_audit(
                "COMMUNICATION_REQUEST_BLOCKED", "communication_request", communication["request_id"], None,
                {"reason": communication["reason"]}, user["id"], company_id,
            )
        else:
            await log_audit(
                "COMMUNICATION_REQUEST_REJECTED", "communication_request", communication["request_id"], None,
                {"reason": communication["reason"]}, user["id"], company_id,
            )
        return communication
    except (HTTPException, ValueError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        event = "COMMUNICATION_REQUEST_BLOCKED" if "MISSING" in str(detail) else "COMMUNICATION_REQUEST_FAILED"
        await log_audit(event, "communication_request", execution_job_id, None, {"reason": str(detail)}, user["id"], company_id)
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_router.post("/communication-requests/{request_id}/simulate")
async def simulate_communication(request_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    communication = await db.communication_requests.find_one(
        {"company_id": company_id, "request_id": request_id}, {"_id": 0}
    )
    if not communication:
        raise HTTPException(status_code=404, detail="Communication Request não encontrada")
    try:
        simulated = simulate_communication_request(communication)
        await db.communication_requests.replace_one(
            {"company_id": company_id, "request_id": request_id}, simulated
        )
        event = "COMMUNICATION_REQUEST_SIMULATED" if simulated["status"] == "SIMULATED" else "COMMUNICATION_REQUEST_PREPARED"
        await log_audit(
            event, "communication_request", request_id, {"status": communication["status"]},
            {"status": simulated["status"], "external_side_effect": False}, user["id"], company_id,
        )
        return simulated
    except ValueError as exc:
        await log_audit(
            "COMMUNICATION_REQUEST_FAILED", "communication_request", request_id, {"status": communication.get("status")},
            {"error": str(exc)}, user["id"], company_id,
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@api_router.get("/communication-requests")
async def list_communication_requests(
    channel: str | None = None,
    action_type: str | None = None,
    status: str | None = None,
    opportunity_id: str | None = None,
    execution_job_id: str | None = None,
    created_at: str | None = None,
    user=Depends(get_current_user),
):
    query: dict = {"company_id": _safe_company_id(user)}
    for key, value in {
        "channel": channel,
        "action_type": action_type,
        "status": status,
        "opportunity_id": opportunity_id,
        "execution_job_id": execution_job_id,
    }.items():
        if value:
            query[key] = value
    if created_at:
        query["created_at"] = {"$gte": created_at}
    return await db.communication_requests.find(query, {"_id": 0}).sort("created_at", -1).to_list(10000)


@api_router.get("/communication-requests/{request_id}")
async def get_communication_request(request_id: str, user=Depends(get_current_user)):
    communication = await db.communication_requests.find_one(
        {"company_id": _safe_company_id(user), "request_id": request_id}, {"_id": 0}
    )
    if not communication:
        raise HTTPException(status_code=404, detail="Communication Request não encontrada")
    return communication


@api_router.post("/communication-requests/{request_id}/cancel")
async def cancel_communication(request_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    communication = await db.communication_requests.find_one(
        {"company_id": company_id, "request_id": request_id}, {"_id": 0}
    )
    if not communication:
        raise HTTPException(status_code=404, detail="Communication Request não encontrada")
    try:
        cancelled = cancel_communication_request(communication)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.communication_requests.replace_one(
        {"company_id": company_id, "request_id": request_id}, cancelled
    )
    await log_audit(
        "COMMUNICATION_REQUEST_REJECTED", "communication_request", request_id,
        {"status": communication["status"]}, {"status": "REJECTED", "reason": "CANCELLED_BY_USER"},
        user["id"], company_id,
    )
    return cancelled


async def _load_message_intelligence_inputs(communication_request_id: str, user: dict) -> tuple:
    company_id = _safe_company_id(user)
    try:
        return await load_message_draft_inputs(db, company_id, communication_request_id)
    except MessageDraftInputsNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MessageDraftInputsIncomplete as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


async def _generate_message_draft(communication_request_id: str, user: dict) -> dict:
    company_id = _safe_company_id(user)
    await log_audit(
        "MESSAGE_DRAFT_GENERATION_STARTED", "message_draft", communication_request_id, None,
        {"communication_request_id": communication_request_id}, user["id"], company_id,
    )
    try:
        inputs = await _load_message_intelligence_inputs(communication_request_id, user)
        draft = build_message_draft(company_id, *inputs)
        existing = await db.message_drafts.find_one(
            {
                "company_id": company_id,
                "communication_request_id": communication_request_id,
                "message_intelligence_version": MESSAGE_INTELLIGENCE_VERSION,
                "source_snapshot_hash": draft["source_snapshot_hash"],
            },
            {"_id": 0},
        )
        if existing:
            return existing
        now_iso = datetime.now(timezone.utc).isoformat()
        document = {**draft, "created_at": now_iso, "updated_at": now_iso}
        if draft["status"] == "READY_FOR_REVIEW":
            previous = await db.message_drafts.find(
                {
                    "company_id": company_id,
                    "communication_request_id": communication_request_id,
                    "status": {"$in": ["CREATED", "READY_FOR_REVIEW", "APPROVED"]},
                },
                {"_id": 0},
            ).to_list(100)
            if previous:
                await db.message_drafts.update_many(
                    {"company_id": company_id, "message_draft_id": {"$in": [item["message_draft_id"] for item in previous]}},
                    {"$set": {"status": "SUPERSEDED", "updated_at": now_iso}},
                )
                for item in previous:
                    await log_audit(
                        "MESSAGE_DRAFT_SUPERSEDED", "message_draft", item["message_draft_id"],
                        {"status": item["status"]}, {"status": "SUPERSEDED", "superseded_by": draft["message_draft_id"]},
                        user["id"], company_id,
                    )
        await db.message_drafts.insert_one(document)
        event = "MESSAGE_DRAFT_BLOCKED" if draft["status"] == "BLOCKED" else "MESSAGE_DRAFT_GENERATED"
        await log_audit(
            event, "message_draft", draft["message_draft_id"], None,
            {"status": draft["status"], "template_id": draft["template_id"], "confidence": draft["confidence"]},
            user["id"], company_id,
        )
        return document
    except HTTPException as exc:
        await log_audit(
            "MESSAGE_DRAFT_BLOCKED", "message_draft", communication_request_id, None,
            {"error": str(exc.detail)}, user["id"], company_id,
        )
        raise
    except ValueError as exc:
        await log_audit(
            "MESSAGE_DRAFT_BLOCKED", "message_draft", communication_request_id, None,
            {"error": str(exc)}, user["id"], company_id,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await log_audit(
            "MESSAGE_DRAFT_BLOCKED", "message_draft", communication_request_id, None,
            {"error": str(exc)}, user["id"], company_id,
        )
        raise HTTPException(status_code=400, detail="Não foi possível gerar o Message Draft") from exc


@api_router.post("/message-drafts/{communication_request_id}/generate")
async def generate_message_draft(communication_request_id: str, user=Depends(get_current_user)):
    return await _generate_message_draft(communication_request_id, user)


@api_router.get("/message-drafts")
async def list_message_drafts(
    company: str | None = None,
    opportunity: str | None = None,
    channel: str | None = None,
    action_type: str | None = None,
    status: str | None = None,
    created_at: str | None = None,
    user=Depends(get_current_user),
):
    company_id = _safe_company_id(user)
    if company and company != company_id:
        raise HTTPException(status_code=403, detail="Empresa não autorizada")
    query: dict = {"company_id": company_id}
    for key, value in {"opportunity_id": opportunity, "channel": channel, "action_type": action_type, "status": status}.items():
        if value:
            query[key] = value
    if created_at:
        query["created_at"] = {"$gte": created_at}
    return await db.message_drafts.find(query, {"_id": 0}).sort("created_at", -1).to_list(10000)


@api_router.get("/message-drafts/{draft_id}")
async def get_message_draft(draft_id: str, user=Depends(get_current_user)):
    draft = await db.message_drafts.find_one(
        {"company_id": _safe_company_id(user), "message_draft_id": draft_id}, {"_id": 0}
    )
    if not draft:
        raise HTTPException(status_code=404, detail="Message Draft não encontrado")
    return draft


@api_router.post("/message-drafts/{draft_id}/regenerate")
async def regenerate_message_draft(draft_id: str, user=Depends(get_current_user)):
    draft = await get_message_draft(draft_id, user)
    return await _generate_message_draft(draft["communication_request_id"], user)


@api_router.post("/message-drafts/{draft_id}/approve")
async def approve_message_draft(draft_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    draft = await db.message_drafts.find_one({"company_id": company_id, "message_draft_id": draft_id}, {"_id": 0})
    if not draft:
        raise HTTPException(status_code=404, detail="Message Draft não encontrado")
    if draft.get("status") != "READY_FOR_REVIEW":
        raise HTTPException(status_code=409, detail="Message Draft não pode ser aprovado neste estado")
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.message_drafts.update_one(
        {"company_id": company_id, "message_draft_id": draft_id},
        {"$set": {"status": "APPROVED", "human_approved": True, "updated_at": now_iso}},
    )
    await log_audit("MESSAGE_DRAFT_APPROVED", "message_draft", draft_id, {"status": draft["status"]}, {"status": "APPROVED"}, user["id"], company_id)
    return {**draft, "status": "APPROVED", "human_approved": True, "updated_at": now_iso}


@api_router.post("/message-drafts/{draft_id}/reject")
async def reject_message_draft(draft_id: str, request: Request, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    draft = await db.message_drafts.find_one({"company_id": company_id, "message_draft_id": draft_id}, {"_id": 0})
    if not draft:
        raise HTTPException(status_code=404, detail="Message Draft não encontrado")
    if draft.get("status") != "READY_FOR_REVIEW":
        raise HTTPException(status_code=409, detail="Message Draft não pode ser rejeitado neste estado")
    body = await request.json()
    reason = str(body.get("reason") or "Rejeitado pelo usuário.").strip()
    now_iso = datetime.now(timezone.utc).isoformat()
    rejection = {"reason": reason, "user_id": user["id"], "timestamp": now_iso}
    await db.message_drafts.update_one(
        {"company_id": company_id, "message_draft_id": draft_id},
        {"$set": {"status": "REJECTED", "human_rejected": True, "rejection": rejection, "updated_at": now_iso}},
    )
    await log_audit("MESSAGE_DRAFT_REJECTED", "message_draft", draft_id, {"status": draft["status"]}, {"status": "REJECTED", "reason": reason}, user["id"], company_id)
    return {**draft, "status": "REJECTED", "human_rejected": True, "rejection": rejection, "updated_at": now_iso}


@api_router.post("/message-drafts/{draft_id}/edit")
async def edit_message_draft(draft_id: str, request: Request, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    draft = await db.message_drafts.find_one({"company_id": company_id, "message_draft_id": draft_id}, {"_id": 0})
    if not draft:
        raise HTTPException(status_code=404, detail="Message Draft não encontrado")
    if draft.get("status") != "READY_FOR_REVIEW":
        raise HTTPException(status_code=409, detail="Message Draft não pode ser editado neste estado")
    body = await request.json()
    edited_content = body.get("content")
    if not isinstance(edited_content, dict):
        raise HTTPException(status_code=400, detail="Conteúdo editado inválido")
    allowed_fields = {"subject", "opening", "body", "call_to_action", "closing"}
    if set(edited_content) != allowed_fields or any(value is not None and not isinstance(value, str) for value in edited_content.values()):
        raise HTTPException(status_code=400, detail="Campos de conteúdo inválidos")
    length = sum(len(value) for value in edited_content.values() if value)
    if length > draft.get("policy", {}).get("max_message_length", 1000):
        raise HTTPException(status_code=400, detail="Mensagem excede o limite do canal")
    now_iso = datetime.now(timezone.utc).isoformat()
    reason = str(body.get("reason") or "Edição humana.").strip()
    history_item = {
        "original_content": draft["original_content"], "edited_content": edited_content,
        "edited_by": user["id"], "edited_at": now_iso, "edit_reason": reason,
    }
    changed_fields = sorted(field for field in allowed_fields if draft["original_content"].get(field) != edited_content.get(field))
    await db.message_drafts.update_one(
        {"company_id": company_id, "message_draft_id": draft_id},
        {"$set": {"edited_content": edited_content, "human_edited": True, "edit_delta": changed_fields, "updated_at": now_iso}, "$push": {"edit_history": history_item}},
    )
    await log_audit(
        "MESSAGE_DRAFT_EDITED", "message_draft", draft_id, draft["original_content"],
        {"content": edited_content, "reason": reason, "timestamp": now_iso}, user["id"], company_id,
    )
    return {**draft, "edited_content": edited_content, "human_edited": True, "edit_delta": changed_fields, "edit_history": draft.get("edit_history", []) + [history_item], "updated_at": now_iso}


def _whatsapp_configuration(company_id: str) -> WhatsAppConfiguration:
    return whatsapp_configuration_for_company(company_id)


async def _load_whatsapp_chain(draft_id: str, company_id: str) -> tuple:
    draft = await db.message_drafts.find_one({"company_id": company_id, "message_draft_id": draft_id}, {"_id": 0})
    if not draft:
        raise HTTPException(status_code=404, detail="Message Draft não encontrado")
    communication = await db.communication_requests.find_one(
        {"company_id": company_id, "request_id": draft.get("communication_request_id")}, {"_id": 0}
    )
    job = await db.execution_jobs.find_one(
        {"company_id": company_id, "execution_job_id": draft.get("execution_job_id")}, {"_id": 0}
    )
    plan = await db.action_plans.find_one(
        {"company_id": company_id, "action_plan_id": draft.get("action_plan_id")}, {"_id": 0}
    )
    opportunity = await db.opportunities.find_one(
        {"company_id": company_id, "id": draft.get("opportunity_id"), "deleted": {"$ne": True}}, {"_id": 0}
    )
    if not all([communication, job, plan, opportunity]):
        raise HTTPException(status_code=409, detail="WhatsApp blocked: cadeia comercial incompleta")
    if plan.get("status") != "APPROVED":
        raise HTTPException(status_code=409, detail="MISSING_APPROVAL")
    client_doc = None
    if opportunity.get("client_id"):
        client_doc = await db.clients.find_one(
            {"company_id": company_id, "id": opportunity["client_id"], "deleted": {"$ne": True}}, {"_id": 0}
        )
    if not client_doc:
        raise HTTPException(status_code=409, detail="INVALID_RECIPIENT")
    consent = await db.whatsapp_recipient_consents.find_one(
        {"company_id": company_id, "client_id": client_doc["id"]}, {"_id": 0}
    )
    conversation = await db.whatsapp_conversations.find_one(
        {"company_id": company_id, "client_id": client_doc["id"]}, {"_id": 0}
    )
    return draft, communication, job, plan, opportunity, client_doc, consent, conversation


async def _whatsapp_usage_snapshot(company_id: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    day = now.date().isoformat()
    month = now.strftime("%Y-%m")
    daily = await db.whatsapp_usage.find({"company_id": company_id, "day": day}, {"_id": 0}).to_list(1000)
    monthly = await db.whatsapp_usage.find({"company_id": company_id, "month": month}, {"_id": 0}).to_list(10000)
    latest = await db.whatsapp_messages.find_one(
        {"company_id": company_id, "sent_at": {"$ne": None}}, {"_id": 0}, sort=[("sent_at", -1)]
    )
    return {
        "day": day,
        "month": month,
        "daily_count": sum(item.get("count", 0) for item in daily),
        "monthly_count": sum(item.get("count", 0) for item in monthly),
        "daily_cost": round(sum(item.get("estimated_cost", 0.0) for item in daily), 6),
        "monthly_cost": round(sum(item.get("estimated_cost", 0.0) for item in monthly), 6),
        "last_sent_at": latest.get("sent_at") if latest else None,
    }


@api_router.post("/whatsapp/test/health")
async def whatsapp_health(user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    try:
        configuration = _whatsapp_configuration(company_id)
    except ValueError:
        configuration = WhatsAppConfiguration()
    state = configuration.public_state()
    usage = await _whatsapp_usage_snapshot(company_id)
    return {
        "provider": "meta_whatsapp_cloud_api",
        "provider_version": "1.0.0",
        "company_configured": configuration.configured_company_id == company_id,
        "network_probe_performed": False,
        "usage": usage,
        **state,
    }


@api_router.post("/whatsapp/consents/{client_id}")
async def register_whatsapp_consent(client_id: str, request: Request, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    client_doc = await db.clients.find_one({"company_id": company_id, "id": client_id, "deleted": {"$ne": True}}, {"_id": 0})
    if not client_doc:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    body = await request.json()
    status = str(body.get("status") or "").upper()
    if status not in {"OPTED_IN", "OPTED_OUT"}:
        raise HTTPException(status_code=400, detail="Estado de consentimento inválido")
    evidence = str(body.get("evidence") or "").strip()
    source = str(body.get("source") or "").strip()
    if not evidence or not source:
        raise HTTPException(status_code=400, detail="Evidência e origem do consentimento são obrigatórias")
    now_iso = datetime.now(timezone.utc).isoformat()
    document = {
        "company_id": company_id,
        "client_id": client_id,
        "status": status,
        "blocked": status == "OPTED_OUT",
        "evidence": evidence,
        "source": source,
        "recorded_by": user["id"],
        "recorded_at": now_iso,
        "updated_at": now_iso,
    }
    await db.whatsapp_recipient_consents.update_one(
        {"company_id": company_id, "client_id": client_id}, {"$set": document}, upsert=True
    )
    await log_audit(
        "WHATSAPP_OPT_OUT" if status == "OPTED_OUT" else "WHATSAPP_OPT_IN",
        "whatsapp_consent", client_id, None, {"status": status, "source": source}, user["id"], company_id,
    )
    return document


@api_router.post("/whatsapp/messages/{draft_id}/prepare")
async def prepare_whatsapp_send(draft_id: str, request: Request, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    body = await request.json()
    allowed_fields = {"mode", "template_name", "template_language", "template_version"}
    if set(body) - allowed_fields:
        raise HTTPException(status_code=400, detail="Parâmetros de preparação não permitidos")
    mode = str(body.get("mode") or "SIMULATION").upper()
    draft, communication, job, _, _, client_doc, consent, conversation = await _load_whatsapp_chain(draft_id, company_id)
    template = None
    if body.get("template_name"):
        template = await db.whatsapp_templates.find_one(
            {
                "company_id": company_id,
                "name": str(body["template_name"]),
                "language": str(body.get("template_language") or "pt_BR"),
                "version": str(body.get("template_version") or "1"),
            },
            {"_id": 0},
        )
    message = prepare_whatsapp_message(
        company_id, draft, communication, job, client_doc, mode, consent, conversation, template
    )
    message["estimated_cost"] = float((template or {}).get("estimated_cost", 0.0))
    existing = await db.whatsapp_messages.find_one(
        {"company_id": company_id, "idempotency_key": message["idempotency_key"]}, {"_id": 0}
    )
    if existing:
        return existing
    await db.whatsapp_messages.insert_one(message)
    await log_audit(
        "WHATSAPP_SEND_REQUESTED", "whatsapp_message", message["message_id"], None,
        {"status": message["status"], "mode": mode, "recipient": message["recipient"].get("normalized_phone"), "reason": message.get("reason")},
        user["id"], company_id,
    )
    return message


@api_router.post("/whatsapp/messages/{draft_id}/send")
async def send_whatsapp_message(draft_id: str, request: Request, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    body = await request.json()
    if set(body) - {"confirm_send"}:
        raise HTTPException(status_code=400, detail="Parâmetros de envio não permitidos")
    explicit_confirmation = body.get("confirm_send") is True
    message = await db.whatsapp_messages.find_one(
        {"company_id": company_id, "message_draft_id": draft_id}, {"_id": 0}, sort=[("created_at", -1)]
    )
    if not message:
        raise HTTPException(status_code=404, detail="Mensagem WhatsApp não preparada")
    if message.get("provider_message_id") or message.get("provider_status") == "SIMULATED":
        return message
    draft, communication, job, plan, _, _, consent, conversation = await _load_whatsapp_chain(draft_id, company_id)
    if plan.get("status") != "APPROVED":
        raise HTTPException(status_code=409, detail="MISSING_APPROVAL")
    usage = await _whatsapp_usage_snapshot(company_id)
    try:
        try:
            configuration = _whatsapp_configuration(company_id)
        except ValueError:
            if message["mode"] != "SIMULATION":
                raise
            configuration = WhatsAppConfiguration()
        validate_send_guards(
            message["mode"], configuration, company_id, {**message, "status": "APPROVED"}, draft,
            communication, job, consent, usage, message.get("template"), conversation,
            explicit_confirmation, message.get("estimated_cost", 0.0),
        )
    except ValueError as exc:
        await db.whatsapp_messages.update_one(
            {"company_id": company_id, "message_id": message["message_id"]},
            {"$set": {"status": "BLOCKED", "reason": str(exc), "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        await log_audit("WHATSAPP_SEND_FAILED", "whatsapp_message", message["message_id"], None, {"error_type": str(exc)}, user["id"], company_id)
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    now_iso = datetime.now(timezone.utc).isoformat()
    await log_audit("WHATSAPP_SEND_APPROVED", "whatsapp_message", message["message_id"], {"status": message["status"]}, {"status": "APPROVED"}, user["id"], company_id)
    if message["mode"] == "SIMULATION":
        provider = WhatsAppProviderFactory.create("SIMULATION", configuration)
        result = provider.execute(message)
        simulated = {**message, "status": "APPROVED", "provider_status": "SIMULATED", "result": result, "updated_at": now_iso}
        await db.whatsapp_messages.replace_one({"company_id": company_id, "message_id": message["message_id"]}, simulated)
        return simulated

    approved_at = datetime.now(timezone.utc).isoformat()
    approved = await db.whatsapp_messages.update_one(
        {"company_id": company_id, "message_id": message["message_id"], "status": "PREPARED", "provider_message_id": None},
        {"$set": {"status": "APPROVED", "approved_at": approved_at, "approved_by": user["id"], "updated_at": approved_at}},
    )
    if approved.modified_count != 1:
        current = await db.whatsapp_messages.find_one({"company_id": company_id, "message_id": message["message_id"]}, {"_id": 0})
        return current
    claimed = await db.whatsapp_messages.update_one(
        {"company_id": company_id, "message_id": message["message_id"], "status": "APPROVED", "provider_message_id": None},
        {"$set": {"status": "SENDING", "updated_at": now_iso}},
    )
    if claimed.modified_count != 1:
        current = await db.whatsapp_messages.find_one({"company_id": company_id, "message_id": message["message_id"]}, {"_id": 0})
        return current
    sending = {**message, "status": "SENDING", "updated_at": now_iso}
    await log_audit("WHATSAPP_SEND_STARTED", "whatsapp_message", message["message_id"], {"status": "APPROVED"}, {"status": "SENDING"}, user["id"], company_id)
    try:
        provider = WhatsAppProviderFactory.create(message["mode"], configuration)
        result = provider.execute(sending)
        accepted = {
            **sending,
            "provider_message_id": result["provider_message_id"],
            "provider_status": "ACCEPTED",
            "result": result,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.whatsapp_messages.replace_one({"company_id": company_id, "message_id": message["message_id"]}, accepted)
        await db.whatsapp_usage.update_one(
            {
                "company_id": company_id, "day": usage["day"], "month": usage["month"],
                "message_type": message["payload"]["message_type"],
                "template_name": (message.get("template") or {}).get("name"), "status": "ACCEPTED",
            },
            {"$inc": {"count": 1, "estimated_cost": message.get("estimated_cost", 0.0)}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
        await log_audit("WHATSAPP_SEND_SUCCEEDED", "whatsapp_message", message["message_id"], {"status": "SENDING"}, {"provider_status": "ACCEPTED", "provider_message_id": result["provider_message_id"]}, user["id"], company_id)
        return accepted
    except WhatsAppProviderError as exc:
        failed_at = datetime.now(timezone.utc).isoformat()
        failed = {**sending, "status": "FAILED", "provider_status": "FAILED", "failed_at": failed_at, "updated_at": failed_at, **exc.as_result()}
        await db.whatsapp_messages.replace_one({"company_id": company_id, "message_id": message["message_id"]}, failed)
        await log_audit("WHATSAPP_SEND_FAILED", "whatsapp_message", message["message_id"], {"status": "SENDING"}, exc.as_result(), user["id"], company_id)
        raise HTTPException(status_code=502, detail=exc.error_type) from exc


@api_router.get("/whatsapp/messages/{message_id}")
async def get_whatsapp_message(message_id: str, user=Depends(get_current_user)):
    message = await db.whatsapp_messages.find_one(
        {"company_id": _safe_company_id(user), "message_id": message_id}, {"_id": 0}
    )
    if not message:
        raise HTTPException(status_code=404, detail="Mensagem WhatsApp não encontrada")
    return message


@api_router.get("/whatsapp/messages")
async def list_whatsapp_messages(
    opportunity_id: str | None = None,
    status: str | None = None,
    mode: str | None = None,
    user=Depends(get_current_user),
):
    query: dict = {"company_id": _safe_company_id(user)}
    if opportunity_id:
        query["opportunity_id"] = opportunity_id
    if status:
        query["status"] = status
    if mode:
        query["mode"] = mode
    return await db.whatsapp_messages.find(query, {"_id": 0}).sort("created_at", -1).to_list(10000)


@api_router.get("/whatsapp/conversations/{client_id}")
async def get_whatsapp_conversation(client_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    client_doc = await db.clients.find_one({"company_id": company_id, "id": client_id, "deleted": {"$ne": True}}, {"_id": 0})
    if not client_doc:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    conversation = await db.whatsapp_conversations.find_one({"company_id": company_id, "client_id": client_id}, {"_id": 0})
    messages = await db.whatsapp_messages.find({"company_id": company_id, "client_id": client_id}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    consent = await db.whatsapp_recipient_consents.find_one({"company_id": company_id, "client_id": client_id}, {"_id": 0})
    return {"conversation": conversation, "messages": messages, "consent": consent}


@api_router.get("/webhooks/whatsapp", response_class=PlainTextResponse)
async def verify_whatsapp_webhook(request: Request):
    for configuration in whatsapp_configurations_from_env():
        try:
            challenge = verify_webhook_challenge(
                request.query_params.get("hub.mode"), request.query_params.get("hub.challenge"),
                request.query_params.get("hub.verify_token"), configuration.verify_token,
            )
            return PlainTextResponse(challenge)
        except ValueError:
            continue
    raise HTTPException(status_code=403, detail="WEBHOOK_VERIFICATION_FAILED")


@api_router.post("/webhooks/whatsapp")
async def receive_whatsapp_webhook(request: Request):
    raw_body = await request.body()
    configurations = [
        item for item in whatsapp_configurations_from_env()
        if verify_webhook_signature(raw_body, request.headers.get("X-Hub-Signature-256"), item.app_secret)
    ]
    if len(configurations) != 1:
        raise HTTPException(status_code=403, detail="INVALID_WEBHOOK_SIGNATURE")
    configuration = configurations[0]
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="INVALID_WEBHOOK_PAYLOAD") from exc
    if payload.get("object") != "whatsapp_business_account":
        raise HTTPException(status_code=400, detail="INVALID_WEBHOOK_OBJECT")
    company_id = configuration.configured_company_id
    if not company_id:
        raise HTTPException(status_code=503, detail="WHATSAPP_CONFIGURATION_INCOMPLETE")
    processed = 0
    duplicates = 0
    for event in parse_webhook_events(payload):
        if event.get("waba_id") != configuration.business_account_id or event.get("phone_number_id") != configuration.phone_number_id:
            continue
        exists = await db.whatsapp_webhook_events.find_one({"provider_event_id": event["provider_event_id"]}, {"_id": 1})
        if exists:
            duplicates += 1
            continue
        now_iso = datetime.now(timezone.utc).isoformat()
        stored_event = {key: value for key, value in event.items() if key != "raw"}
        business_event = {
            "SENT": "MESSAGE_SENT", "DELIVERED": "MESSAGE_DELIVERED", "READ": "MESSAGE_READ",
            "FAILED": "MESSAGE_FAILED", "RECEIVED": "MESSAGE_RECEIVED",
        }.get(event["event_type"])
        stored_event.update({"company_id": company_id, "business_event": business_event, "created_at": now_iso})
        await db.whatsapp_webhook_events.insert_one(stored_event)
        processed += 1
        if event["event_type"] in {"SENT", "DELIVERED", "READ", "FAILED"}:
            message = await db.whatsapp_messages.find_one(
                {"company_id": company_id, "provider_message_id": event.get("provider_message_id")}, {"_id": 0}
            )
            if message:
                target = event["event_type"]
                try:
                    transition_whatsapp_status(message["status"], target)
                except ValueError:
                    target = message["status"]
                timestamp_field = {"SENT": "sent_at", "DELIVERED": "delivered_at", "READ": "read_at", "FAILED": "failed_at"}[event["event_type"]]
                update = {"status": target, "provider_status": event["provider_status"], timestamp_field: now_iso, "updated_at": now_iso}
                if event.get("error"):
                    update["error_code"] = event["error"].get("code")
                    update["error_message"] = event["error"].get("error_data", {}).get("details") or event["error"].get("message")
                await db.whatsapp_messages.update_one({"company_id": company_id, "message_id": message["message_id"]}, {"$set": update})
                await log_audit("WHATSAPP_STATUS_RECEIVED", "whatsapp_message", message["message_id"], {"status": message["status"]}, {"status": target}, None, company_id)
        elif event["event_type"] == "RECEIVED":
            normalized = normalize_brazil_phone(event.get("recipient"))
            matches = []
            if normalized.valid:
                candidates = await db.clients.find({"company_id": company_id, "phone": {"$nin": [None, ""]}, "deleted": {"$ne": True}}, {"_id": 0, "id": 1, "phone": 1}).to_list(10000)
                matches = [candidate for candidate in candidates if normalize_brazil_phone(candidate.get("phone")).normalized_phone == normalized.normalized_phone]
            client_id = matches[0]["id"] if len(matches) == 1 else None
            previous_outbound = None
            if client_id:
                previous_outbound = await db.whatsapp_messages.find_one(
                    {"company_id": company_id, "client_id": client_id, "direction": {"$ne": "INBOUND"}},
                    {"_id": 0}, sort=[("created_at", -1)]
                )
            inbound_id = "inbound-" + hashlib.sha256(str(event["provider_event_id"]).encode()).hexdigest()[:24]
            inbound = {
                "company_id": company_id, "message_id": inbound_id, "provider_message_id": event.get("provider_message_id"),
                "client_id": client_id, "recipient": {"original_phone": event.get("recipient"), "normalized_phone": normalized.normalized_phone},
                "direction": "INBOUND", "status": "RECEIVED", "provider_status": "received", "message_type": event.get("message_type"),
                "inbound_message": {"text": event.get("text")}, "correlation": "MATCHED" if client_id else "UNKNOWN",
                "opportunity_id": previous_outbound.get("opportunity_id") if previous_outbound else None,
                "communication_request_id": previous_outbound.get("communication_request_id") if previous_outbound else None,
                "message_draft_id": previous_outbound.get("message_draft_id") if previous_outbound else None,
                "execution_job_id": previous_outbound.get("execution_job_id") if previous_outbound else None,
                "business_event": "MESSAGE_REPLIED" if previous_outbound else "MESSAGE_RECEIVED",
                "created_at": now_iso, "updated_at": now_iso,
            }
            await db.whatsapp_messages.insert_one(inbound)
            if client_id:
                await db.whatsapp_conversations.update_one(
                    {"company_id": company_id, "client_id": client_id},
                    {"$set": {"company_id": company_id, "client_id": client_id, "last_received_at": now_iso, "updated_at": now_iso}, "$setOnInsert": {"created_at": now_iso}},
                    upsert=True,
                )
                if detect_opt_out(event.get("text")):
                    await db.whatsapp_recipient_consents.update_one(
                        {"company_id": company_id, "client_id": client_id},
                        {"$set": {"company_id": company_id, "client_id": client_id, "status": "OPTED_OUT", "blocked": True, "source": "WHATSAPP_INBOUND", "evidence": event.get("text"), "recorded_at": now_iso, "updated_at": now_iso}},
                        upsert=True,
                    )
                    await log_audit("WHATSAPP_OPT_OUT", "whatsapp_consent", client_id, None, {"status": "OPTED_OUT", "source": "WHATSAPP_INBOUND"}, None, company_id)
            await log_audit("WHATSAPP_MESSAGE_RECEIVED", "whatsapp_message", inbound_id, None, {"client_id": client_id, "correlation": inbound["correlation"]}, None, company_id)
    return {"received": True, "processed": processed, "duplicates": duplicates}


@api_router.get("/imports/{batch_id}/standard-records")
async def get_standard_records(batch_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    return await db.standard_records.find({"company_id": company_id, "import_batch_id": batch_id}, {"_id": 0}).sort("created_at", 1).to_list(100000)


@api_router.delete("/imports/{batch_id}")
async def delete_import_batch(batch_id: str, user=Depends(get_current_user)):
    company_id = _safe_company_id(user)
    batch = await db.import_batches.find_one({"id": batch_id, "company_id": company_id, "deleted": {"$ne": True}}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Importação não encontrada")

    await db.import_batches.update_one({"id": batch_id}, {"$set": {"deleted": True, "status": "CANCELLED", "updated_at": datetime.now(timezone.utc).isoformat()}})
    await log_audit(
        action="IMPORT_CANCELLED",
        entity_type="import_batch",
        entity_id=batch_id,
        old_value=batch,
        new_value={**batch, "deleted": True, "status": "CANCELLED"},
        user_id=user["id"],
        company_id=company_id,
    )
    return {"ok": True, "status": "CANCELLED"}

# ---------- Stats / Dashboard ----------
@api_router.get("/stats")
async def get_stats(user=Depends(get_current_user)):
    role = user.get("role", "owner")
    company_id = user.get("company_id")
    
    if role == "seller":
        q = {"user_id": user["id"]}
    else:
        if company_id:
            q = {"company_id": company_id}
        else:
            q = {"user_id": user["id"]}

    q["deleted"] = {"$ne": True}

    cursor = db.proposals.find(q, {"_id": 0})
    items = await cursor.to_list(5000)
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    total_open = sum(1 for p in items if p["status"] == "aberto")
    total_won = sum(1 for p in items if p["status"] in ("realizado", "aprovado"))
    total_lost = sum(1 for p in items if p["status"] == "perdido")
    total_qualified = sum(1 for p in items if p["status"] == "qualificado")
    total_negotiation = sum(1 for p in items if p["status"] == "negociacao")

    month_won_value = 0.0
    open_value = 0.0
    stale_count = 0
    for p in items:
        try:
            created = datetime.fromisoformat(p["created_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        val = p.get("grand_total", p.get("total", 0.0))
        if p["status"] == "aberto":
            open_value += val
            if (now - created).days >= 3:
                stale_count += 1
        if p["status"] in ("realizado", "aprovado") and created >= month_start:
            month_won_value += val

    # Helper to parse dates robustly
    def parse_dt(dt_str):
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
        except Exception:
            pass
        for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(dt_str).strip(), fmt)
            except Exception:
                pass
        return None

    # Calculate Sprint 6 metrics
    br_now = now - timedelta(hours=3)
    br_today = br_now.date()
    
    followup_count = 0
    overdue_count = 0
    viewed_today_count = 0
    waiting_count = 0
    
    for p in items:
        # 1. Need follow-up (open/active & last interaction > 3 days)
        if p["status"] in ("aberto", "qualificado", "negociacao"):
            created_str = p.get("created_at")
            last_dt = parse_dt(created_str)
            if last_dt:
                timeline = p.get("timeline") or []
                for t in timeline:
                    t_created = t.get("created_at")
                    if t_created:
                        t_dt = parse_dt(t_created)
                        if t_dt and t_dt > last_dt:
                            last_dt = t_dt
                if (now - last_dt).days >= 3:
                    followup_count += 1
                    
        # 2. Overdue (open/active & next_action_date < today)
        if p["status"] in ("aberto", "qualificado", "negociacao"):
            next_act = p.get("next_action_date")
            if next_act:
                dt = parse_dt(next_act)
                if dt:
                    br_dt = dt - timedelta(hours=3) if dt.tzinfo else dt
                    if br_dt.date() < br_today:
                        overdue_count += 1
                        
        # 3. Viewed today (proposal_viewed_at is today)
        viewed_str = p.get("proposal_viewed_at")
        if viewed_str:
            v_dt = parse_dt(viewed_str)
            if v_dt:
                v_br = v_dt - timedelta(hours=3)
                if v_br.date() == br_today:
                    viewed_today_count += 1
                    
        # 4. Waiting return (open/active & last timeline event type is waiting)
        if p["status"] in ("aberto", "qualificado", "negociacao"):
            timeline = p.get("timeline") or []
            if timeline:
                try:
                    sorted_timeline = sorted(timeline, key=lambda x: x.get("created_at", ""))
                    if sorted_timeline and sorted_timeline[-1].get("type") == "waiting":
                        waiting_count += 1
                except Exception:
                    pass

    # Dashboard Gestão (Conversão por usuário / Gestão por usuário)
    users_stats = []
    if role == "owner" and company_id:
        company_users = await db.users.find({"company_id": company_id, "deleted": {"$ne": True}}).to_list(1000)
        for u in company_users:
            u_proposals = [p for p in items if p.get("user_id") == u["id"]]
            u_enviadas = len(u_proposals)
            u_visualizadas = sum(1 for p in u_proposals if p.get("proposal_viewed_at"))
            u_aceitas = sum(1 for p in u_proposals if p.get("status") in ("realizado", "aprovado"))
            u_conversion = round((u_aceitas / u_enviadas * 100), 2) if u_enviadas > 0 else 0.0
            users_stats.append({
                "user_id": u["id"],
                "name": u.get("name") or u["email"],
                "enviadas": u_enviadas,
                "visualizadas": u_visualizadas,
                "aceitas": u_aceitas,
                "conversao": u_conversion
            })

    total_proposals = len(items)
    approved_proposals = total_won
    pending_proposals = total_open
    rejected_proposals = total_lost
    conversion_rate = round((approved_proposals / total_proposals * 100), 2) if total_proposals > 0 else 0.0
    total_revenue = sum(p.get("grand_total", p.get("total", 0.0)) for p in items if p["status"] in ("realizado", "aprovado"))

    if company_id:
        clients_count = await db.clients.count_documents({"company_id": company_id, "deleted": {"$ne": True}})
    else:
        clients_count = 0

    client_last_proposal = {}
    for p in items:
        client_key = p.get("client_id") or p.get("client_document") or p.get("client_name")
        if not client_key:
            continue
        created_str = p.get("created_at")
        if not created_str:
            continue
        try:
            created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        except Exception:
            continue
            
        if client_key not in client_last_proposal:
            client_last_proposal[client_key] = created_dt
        else:
            if created_dt > client_last_proposal[client_key]:
                client_last_proposal[client_key] = created_dt
                
    clients_active = 0
    clients_lost = 0
    limit_90 = now - timedelta(days=90)
    limit_180 = now - timedelta(days=180)
    
    for client_key, last_dt in client_last_proposal.items():
        if last_dt >= limit_90:
            clients_active += 1
        if last_dt < limit_180:
            clients_lost += 1

    acceptance_pending_count = sum(1 for p in items if p.get("acceptance_status", "pending") == "pending")
    acceptance_accepted_count = sum(1 for p in items if p.get("acceptance_status", "pending") == "accepted")
    acceptance_rejected_count = sum(1 for p in items if p.get("acceptance_status", "pending") == "rejected")
    acceptance_rate = round((acceptance_accepted_count / total_proposals * 100), 2) if total_proposals > 0 else 0.0

    ticket_average = total_revenue / approved_proposals if approved_proposals > 0 else 0.0

    plan_state = await get_user_plan_state(user["id"])
    return {
        "open_count": total_open,
        "won_count": total_won,
        "lost_count": total_lost,
        "open_value": round(open_value, 2),
        "month_won_value": round(month_won_value, 2),
        "stale_count": stale_count,
        # Sprint 6 fields
        "followup_count": followup_count,
        "overdue_count": overdue_count,
        "viewed_today_count": viewed_today_count,
        "waiting_count": waiting_count,
        "users_stats": users_stats,
        # New stats fields
        "total_proposals": total_proposals,
        "approved_proposals": approved_proposals,
        "pending_proposals": pending_proposals,
        "rejected_proposals": rejected_proposals,
        "conversion_rate": conversion_rate,
        "total_revenue": round(total_revenue, 2),
        # BLOCO 8 fields
        "ticket_average": round(ticket_average, 2),
        "clients_count": clients_count,
        "clients_active": clients_active,
        "clients_lost": clients_lost,
        "negotiation_count": total_negotiation,
        # Acceptance fields
        "acceptance_pending_count": acceptance_pending_count,
        "acceptance_accepted_count": acceptance_accepted_count,
        "acceptance_rejected_count": acceptance_rejected_count,
        "acceptance_rate": acceptance_rate,
        **plan_state,
    }


# ---------- Clients history ----------
@api_router.get("/clients")
async def list_clients(user=Depends(get_current_user)):
    company_id = user.get("company_id")
    if not company_id:
        return []
        
    clients = await db.clients.find({"company_id": company_id, "deleted": {"$ne": True}}).to_list(1000)
    results = []
    for c in clients:
        # Match by client_id OR client_document
        prop_q = {
            "company_id": company_id,
            "deleted": {"$ne": True},
            "$or": [
                {"client_id": c["id"]},
                {"client_document": c["document"]}
            ]
        }
        proposals = await db.proposals.find(prop_q).to_list(1000)
        
        proposals_count = len(proposals)
        total_value = sum(p.get("grand_total", p.get("total", 0.0)) for p in proposals)
        
        last_proposal_at = ""
        if proposals:
            proposals.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            last_proposal_at = proposals[0].get("created_at", "")
            
        results.append({
            "client_id": c["id"],
            "client_name": c["name"],
            "client_document": c["document"],
            "client_phone": c["phone"],
            "email": c.get("email", ""),
            "company": c.get("company", ""),
            "city": c.get("city", ""),
            "state": c.get("state", ""),
            "address": c.get("address", ""),
            "last_proposal_at": last_proposal_at,
            "proposals_count": proposals_count,
            "total_value": total_value
        })
        
    results.sort(key=lambda x: x.get("last_proposal_at", "") or x.get("client_id", ""), reverse=True)
    return results


@api_router.post("/clients")
async def create_client(data: ClientIn, user=Depends(get_current_user)):
    company_id = user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="Empresa não associada")
        
    await verify_trial_not_expired(company_id, user["id"])
    
    # Check if a client with the same document already exists in this company
    exists = await db.clients.find_one({"company_id": company_id, "document": data.document.strip(), "deleted": {"$ne": True}})
    if exists:
        raise HTTPException(status_code=400, detail="Já existe um cliente cadastrado com este documento")
        
    client_id = f"cli_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc).isoformat()
    new_client = {
        "id": client_id,
        "company_id": company_id,
        "name": data.name.strip(),
        "document": data.document.strip(),
        "phone": data.phone.strip(),
        "email": (data.email or "").strip(),
        "company": (data.company or "").strip(),
        "city": (data.city or "").strip(),
        "state": (data.state or "").strip(),
        "address": (data.address or "").strip(),
        "created_at": now,
        "updated_at": now,
        "created_by": user["id"],
        "deleted": False
    }
    await db.clients.insert_one(new_client)
    
    await log_audit(
        action="create",
        entity_type="client",
        entity_id=client_id,
        old_value=None,
        new_value=new_client,
        user_id=user["id"],
        company_id=company_id
    )
    return {"id": client_id, "success": True}


@api_router.put("/clients/{client_id}")
async def update_client(client_id: str, data: ClientUpdateIn, user=Depends(get_current_user)):
    company_id = user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="Empresa não associada")
        
    client_doc = await db.clients.find_one({"id": client_id, "company_id": company_id, "deleted": {"$ne": True}})
    if not client_doc:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
        
    update_data = {}
    if data.name is not None:
        update_data["name"] = data.name.strip()
    if data.document is not None:
        update_data["document"] = data.document.strip()
    if data.phone is not None:
        update_data["phone"] = data.phone.strip()
    if data.email is not None:
        update_data["email"] = data.email.strip()
    if data.company is not None:
        update_data["company"] = data.company.strip()
    if data.city is not None:
        update_data["city"] = data.city.strip()
    if data.state is not None:
        update_data["state"] = data.state.strip()
    if data.address is not None:
        update_data["address"] = data.address.strip()
        
    if not update_data:
        return {"success": True}
        
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.clients.update_one(
        {"id": client_id, "company_id": company_id},
        {"$set": update_data}
    )
    
    updated_doc = await db.clients.find_one({"id": client_id})
    
    await log_audit(
        action="update",
        entity_type="client",
        entity_id=client_id,
        old_value=client_doc,
        new_value=updated_doc,
        user_id=user["id"],
        company_id=company_id
    )
    
    if "name" in update_data or "document" in update_data or "phone" in update_data:
        prop_updates = {}
        if "name" in update_data:
            prop_updates["client_name"] = update_data["name"]
        if "document" in update_data:
            prop_updates["client_document"] = update_data["document"]
        if "phone" in update_data:
            prop_updates["client_phone"] = update_data["phone"]
            
        await db.proposals.update_many(
            {"company_id": company_id, "client_id": client_id},
            {"$set": prop_updates}
        )
        
    return {"success": True}


@api_router.get("/clients/{client_id}/history")
async def get_client_history(client_id: str, user=Depends(get_current_user)):
    client_doc = await db.clients.find_one({"id": client_id, "company_id": user["company_id"], "deleted": {"$ne": True}})
    if not client_doc:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
        
    proposals = await db.proposals.find({"company_id": user["company_id"], "client_id": client_id, "deleted": {"$ne": True}}).to_list(10000)
    
    proposal_count = len(proposals)
    open_count = 0
    qualified_count = 0
    negotiation_count = 0
    approved_count = 0
    lost_count = 0

    total_value = 0.0
    won_value = 0.0
    lost_value = 0.0
    open_value = 0.0

    last_proposal_date = ""
    dates = []

    for p in proposals:
        status = p.get("status", "aberto")
        val = p.get("grand_total", p.get("total", 0.0))
        total_value += val
        
        if p.get("created_at"):
            dates.append(p["created_at"])
            
        if status == "aberto":
            open_count += 1
            open_value += val
        elif status == "qualificado":
            qualified_count += 1
            open_value += val
        elif status == "negociacao":
            negotiation_count += 1
            open_value += val
        elif status in ("aprovado", "realizado"):
            approved_count += 1
            won_value += val
        elif status == "perdido":
            lost_count += 1
            lost_value += val

    if dates:
        last_proposal_date = max(dates)

    conversion_rate = round((approved_count / proposal_count * 100), 2) if proposal_count > 0 else 0.0
    
    return {
        "client_id": client_id,
        "client_name": client_doc["name"],
        "client_document": client_doc.get("document", ""),
        "client_phone": client_doc.get("phone", ""),
        "email": client_doc.get("email", ""),
        "company": client_doc.get("company", ""),
        "city": client_doc.get("city", ""),
        "state": client_doc.get("state", ""),
        "address": client_doc.get("address", ""),
        "proposal_count": proposal_count,
        "open_count": open_count,
        "qualified_count": qualified_count,
        "negotiation_count": negotiation_count,
        "approved_count": approved_count,
        "lost_count": lost_count,
        "total_value": round(total_value, 2),
        "won_value": round(won_value, 2),
        "lost_value": round(lost_value, 2),
        "open_value": round(open_value, 2),
        "conversion_rate": round(conversion_rate, 2),
        "last_proposal_date": last_proposal_date
    }


@api_router.post("/proposals/{pid}/items/{item_index}/convert")
async def convert_manual_item_to_product(pid: str, item_index: int, user=Depends(require_admin)):
    proposal = await db.proposals.find_one({"id": pid})
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    if proposal.get("company_id") != user["company_id"]:
        raise HTTPException(status_code=403, detail="Acesso negado")
        
    products = proposal.get("products", [])
    if item_index < 0 or item_index >= len(products):
        raise HTTPException(status_code=400, detail="Índice de item inválido")
        
    item = products[item_index]
    item_type = item.get("item_type")
    if not item_type:
        item_type = "catalog" if item.get("product_id") else "manual"
        
    if item_type != "manual":
        raise HTTPException(status_code=400, detail="Apenas itens manuais podem ser convertidos em produtos")
        
    company_id = user["company_id"]
    code = ""
    for _ in range(20):
        rand_suffix = uuid.uuid4().hex[:6].upper()
        test_code = f"PRD-{rand_suffix}"
        existing = await db.products.find_one({"company_id": company_id, "code": test_code})
        if not existing:
            code = test_code
            break
    if not code:
        raise HTTPException(status_code=500, detail="Falha ao gerar código único para o produto")
        
    product_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    new_product = {
        "id": product_id,
        "company_id": company_id,
        "code": code,
        "name": item.get("name", "").strip(),
        "description": item.get("description", "").strip(),
        "unit": item.get("unit", "UN").strip().upper(),
        "price": float(item.get("unit_price") or item.get("price") or 0.0),
        "active": True,
        "created_from_manual_item": True,
        "created_at": now
    }
    await db.products.insert_one(new_product)
    new_product.pop("_id", None)
    return new_product


@api_router.get("/analytics/products")
async def get_products_analytics(user=Depends(get_current_user)):
    proposals = await db.proposals.find({
        "company_id": user["company_id"],
        "status": {"$in": ["aprovado", "realizado"]}
    }).to_list(10000)
    
    product_stats = {}
    for p in proposals:
        p_id = p.get("id")
        seen_names = set()
        for item in p.get("products", []):
            name = item.get("name", "").strip()
            if not name:
                continue
            qty = float(item.get("quantity", 0) or 0)
            price = float(item.get("unit_price") or item.get("price") or 0.0)
            total = float(item.get("total") or (qty * price))
            
            if name not in product_stats:
                product_stats[name] = {
                    "name": name,
                    "quantity_sold": 0.0,
                    "revenue": 0.0,
                    "proposal_ids": set()
                }
            product_stats[name]["quantity_sold"] += qty
            product_stats[name]["revenue"] += total
            product_stats[name]["proposal_ids"].add(p_id)

    result = []
    for name, stats in product_stats.items():
        result.append({
            "name": name,
            "quantity_sold": round(stats["quantity_sold"], 2),
            "proposal_count": len(stats["proposal_ids"]),
            "revenue": round(stats["revenue"], 2)
        })
        
    result.sort(key=lambda x: x["revenue"], reverse=True)
    return result


@api_router.get("/analytics/sellers")
async def get_sellers_analytics(user=Depends(get_current_user)):
    role = user.get("role", "owner")
    if role == "seller":
        query = {
            "company_id": user["company_id"],
            "user_id": user["id"],
            "deleted": {"$ne": True}
        }
    else:
        query = {
            "company_id": user["company_id"],
            "deleted": {"$ne": True}
        }
        
    proposals = await db.proposals.find(query).to_list(10000)
    
    seller_stats = {}
    for p in proposals:
        seller_name = p.get("seller_name", "").strip() or "Vendedor Geral"
        status = p.get("status", "aberto")
        val = p.get("grand_total", p.get("total", 0.0))
        
        if seller_name not in seller_stats:
            seller_stats[seller_name] = {
                "seller_name": seller_name,
                "proposal_count": 0,
                "approved_count": 0,
                "lost_count": 0,
                "open_count": 0,
                "won_count": 0,
                "negotiation_count": 0,
                "revenue": 0.0,
                "value_sold": 0.0,
                "value_negotiated": 0.0
            }
            
        stats = seller_stats[seller_name]
        stats["proposal_count"] += 1
        
        if status in ("aprovado", "realizado"):
            stats["approved_count"] += 1
            stats["won_count"] += 1
            stats["revenue"] += val
            stats["value_sold"] += val
        elif status == "perdido":
            stats["lost_count"] += 1
        elif status in ("aberto", "qualificado", "negociacao"):
            stats["open_count"] += 1
            stats["value_negotiated"] += val
            if status == "negociacao":
                stats["negotiation_count"] += 1

    result = []
    for seller, stats in seller_stats.items():
        proposal_count = stats["proposal_count"]
        approved_count = stats["approved_count"]
        revenue = stats["revenue"]
        
        conversion_rate = round((approved_count / proposal_count * 100), 2) if proposal_count > 0 else 0.0
        ticket_average = round((revenue / approved_count), 2) if approved_count > 0 else 0.0
        
        result.append({
            "seller_name": stats["seller_name"],
            "proposal_count": proposal_count,
            "approved_count": approved_count,
            "lost_count": stats["lost_count"],
            "open_count": stats["open_count"],
            "won_count": stats["won_count"],
            "negotiation_count": stats["negotiation_count"],
            "conversion_rate": conversion_rate,
            "ticket_average": ticket_average,
            "revenue": round(revenue, 2),
            "value_sold": round(stats["value_sold"], 2),
            "value_negotiated": round(stats["value_negotiated"], 2)
        })
        
    result.sort(key=lambda x: x["revenue"], reverse=True)
    return result


# ---------- Subscription / Payments ----------
@api_router.get("/subscription/plans")
async def subscription_plans():
    return {
        "plans": [
            {"id": k, **v} for k, v in SUBSCRIPTION_PLANS.items()
        ],
        "free_monthly_quota": FREE_MONTHLY_QUOTA,
    }


@api_router.get("/subscription/me")
async def subscription_me(user=Depends(get_current_user)):
    return await get_user_plan_state(user["id"])


@api_router.post("/subscription/checkout")
async def create_subscription_checkout(data: CheckoutIn, request: Request, user=Depends(get_current_user)):
    plan = SUBSCRIPTION_PLANS.get(data.plan)
    if not plan:
        raise HTTPException(status_code=400, detail="Plano inválido")
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=500, detail="Pagamentos não configurados")

    host_url = str(request.base_url).rstrip("/")
    success_url = f"{host_url}/api/subscription/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{host_url}/api/subscription/cancel"

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": plan["currency"],
                    "product_data": {"name": f"PROPOSTA JÁ — {plan['label']}"},
                    "unit_amount": int(round(plan["amount"] * 100)),
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=user["email"],
            metadata={
                "user_id": user["id"],
                "email": user["email"],
                "plan": data.plan,
            },
        )
    except stripe.error.StripeError as e:
        logging.exception("stripe error")
        raise HTTPException(status_code=500, detail=str(e))

    await db.payment_transactions.insert_one({
        "session_id": session.id,
        "user_id": user["id"],
        "email": user["email"],
        "plan": data.plan,
        "amount": float(plan["amount"]),
        "currency": plan["currency"],
        "payment_status": "initiated",
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    return {"url": session.url, "session_id": session.id}


@api_router.get("/subscription/status/{session_id}")
async def subscription_status(session_id: str, request: Request, user=Depends(get_current_user)):
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=500, detail="Pagamentos não configurados")

    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx or tx["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Transação não encontrada")

    if tx.get("payment_status") == "paid":
        state = await get_user_plan_state(user["id"])
        return {"payment_status": "paid", "status": "complete", **state}

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        logging.info(f"checkout status pending for {session_id}: {e}")
        state = await get_user_plan_state(user["id"])
        return {"payment_status": "pending", "status": "open", **state}

    payment_status = session.payment_status or "unpaid"
    status_value = session.status or "open"

    if payment_status == "paid" and tx.get("payment_status") != "paid":
        res = await db.payment_transactions.update_one(
            {"session_id": session_id, "payment_status": {"$ne": "paid"}},
            {"$set": {
                "payment_status": "paid",
                "status": "complete",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
        if res.modified_count > 0:
            await _activate_subscription(user["id"], tx["plan"], session_id=session_id)
    else:
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {
                "payment_status": payment_status,
                "status": status_value,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )

    state = await get_user_plan_state(user["id"])
    return {"payment_status": payment_status, "status": status_value, **state}


async def _activate_subscription(user_id: str, plan_id: str, session_id: Optional[str] = None):
    # Founder/Lifetime protection
    user = await db.users.find_one({"id": user_id})
    if user and (user.get("founder") or user.get("lifetime")):
        return
        
    plan = SUBSCRIPTION_PLANS.get(plan_id)
    if not plan:
        return
        
    # 1. Resolve company_id and owner_id
    company_id = None
    owner_id = user_id
    
    if user and user.get("company_id"):
        company_id = user["company_id"]
        company = await db.companies.find_one({"id": company_id})
        if company and company.get("user_id"):
            owner_id = company["user_id"]
            
    # Founder/Lifetime protection on resolved owner
    owner_user = await db.users.find_one({"id": owner_id})
    if owner_user and (owner_user.get("founder") or owner_user.get("lifetime")):
        return
            
    # 2. Idempotency check: check if already processed
    existing = None
    if company_id:
        existing = await db.subscriptions.find_one({"company_id": company_id}, {"_id": 0})
    if not existing:
        existing = await db.subscriptions.find_one({"user_id": owner_id}, {"_id": 0})
        
    if session_id and existing and session_id in existing.get("processed_sessions", []):
        return  # Already processed!
        
    now = datetime.now(timezone.utc)
    base = now
    # If currently on trial, replace base with now (trial does not stack)
    if existing and existing.get("pro_until") and existing.get("last_plan_id") != "trial":
        try:
            pu = datetime.fromisoformat(existing["pro_until"])
            if pu > now:
                base = pu
        except Exception:
            pass
    new_pro_until = base + timedelta(days=plan["days"])
    
    update_doc = {
        "user_id": owner_id,
        "company_id": company_id,
        "plan": "pro",
        "last_plan_id": plan_id,
        "pro_until": new_pro_until.isoformat(),
        "updated_at": now.isoformat(),
    }
    
    update_op = {
        "$set": update_doc
    }
    if session_id:
        update_op["$addToSet"] = {"processed_sessions": session_id}
        
    await db.subscriptions.update_one(
        {"user_id": owner_id},
        update_op,
        upsert=True,
    )

    # Reward referrer on first paid subscription (one-time)
    owner_user = await db.users.find_one({"id": owner_id}, {"_id": 0})
    if owner_user and owner_user.get("referred_by") and not owner_user.get("referral_rewarded"):
        await db.users.update_one({"id": owner_id}, {"$set": {"referral_rewarded": True}})
        await _add_pro_days(owner_user["referred_by"], REFERRAL_REWARD_DAYS, source="referral")


async def _add_pro_days(user_id: str, days: int, source: str = "bonus"):
    # Founder/Lifetime protection
    user = await db.users.find_one({"id": user_id})
    if user and (user.get("founder") or user.get("lifetime")):
        return
        
    now = datetime.now(timezone.utc)
    existing = await db.subscriptions.find_one({"user_id": user_id}, {"_id": 0})
    base = now
    if existing and existing.get("pro_until"):
        try:
            pu = datetime.fromisoformat(existing["pro_until"])
            if pu > now:
                base = pu
        except Exception:
            pass
    new_until = base + timedelta(days=days)
    await db.subscriptions.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "plan": "pro",
            "last_plan_id": existing.get("last_plan_id") if existing else source,
            "pro_until": new_until.isoformat(),
            "updated_at": now.isoformat(),
        }},
        upsert=True,
    )


@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    if not STRIPE_API_KEY:
        return {"ok": False}
    body = await request.body()
    sig = request.headers.get("Stripe-Signature", "")

    # If a webhook secret is configured, verify the signature.
    # Otherwise, parse the JSON payload directly (less secure — only for local/dev).
    try:
        if STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(body, sig, STRIPE_WEBHOOK_SECRET)
        else:
            import json as _json
            event = _json.loads(body.decode("utf-8"))
    except Exception as e:
        logging.info(f"stripe webhook rejected: {e}")
        raise HTTPException(status_code=400, detail="webhook error")

    event_type = event.get("type") if isinstance(event, dict) else event["type"]
    data_object = (event.get("data", {}) if isinstance(event, dict) else event["data"]).get("object", {})

    if event_type == "checkout.session.completed" and data_object.get("payment_status") == "paid":
        session_id = data_object.get("id")
        if session_id:
            tx = await db.payment_transactions.find_one({"session_id": session_id})
            if tx and tx.get("payment_status") != "paid":
                res = await db.payment_transactions.update_one(
                    {"session_id": session_id, "payment_status": {"$ne": "paid"}},
                    {"$set": {"payment_status": "paid", "status": "complete"}},
                )
                if res.modified_count > 0:
                    await _activate_subscription(tx["user_id"], tx["plan"], session_id=session_id)
    return {"ok": True}


@api_router.get("/subscription/success", response_class=HTMLResponse)
async def subscription_success_page():
    return """
    <!doctype html><html><head><meta charset='utf-8'>
    <meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>Pagamento concluído</title>
    <style>body{font-family:-apple-system,Helvetica,Arial;background:#0F172A;color:#fff;margin:0;display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center;padding:24px}
    .c{max-width:420px}h1{font-size:28px;margin:0 0 8px}p{color:#94A3B8;margin:0 0 24px}
    .btn{display:inline-block;background:#25D366;color:#fff;padding:14px 24px;border-radius:12px;text-decoration:none;font-weight:700}
    .ico{font-size:64px;margin-bottom:16px}
    </style></head><body><div class='c'>
    <div class='ico'>✅</div>
    <h1>Pagamento confirmado!</h1>
    <p>Seu plano Pro está ativo. Você pode fechar esta aba e voltar ao app.</p>
    </div></body></html>
    """


@api_router.get("/subscription/cancel", response_class=HTMLResponse)
async def subscription_cancel_page():
    return """
    <!doctype html><html><head><meta charset='utf-8'>
    <meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>Pagamento cancelado</title>
    <style>body{font-family:-apple-system,Helvetica,Arial;background:#0F172A;color:#fff;margin:0;display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center;padding:24px}
    .c{max-width:420px}h1{font-size:24px;margin:0 0 8px}p{color:#94A3B8;margin:0 0 24px}
    </style></head><body><div class='c'>
    <h1>Pagamento cancelado</h1>
    <p>Você pode fechar esta aba e tentar novamente quando quiser.</p>
    </div></body></html>
    """


@api_router.get("/")
async def root():
    return {"service": "proposta-ja", "status": "ok"}


# ---------- Referrals ----------
@api_router.get("/referrals/me")
async def referrals_me(user=Depends(get_current_user)):
    user_doc = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    code = user_doc.get("referral_code") if user_doc else None
    if not code:
        # Backfill for legacy users
        code = make_referral_code(user["id"])
        await db.users.update_one({"id": user["id"]}, {"$set": {"referral_code": code}})

    invited_total = await db.users.count_documents({"referred_by": user["id"]})
    converted = await db.users.count_documents({"referred_by": user["id"], "referral_rewarded": True})
    bonus_days = converted * REFERRAL_REWARD_DAYS

    return {
        "code": code,
        "invited_total": invited_total,
        "converted": converted,
        "bonus_days_earned": bonus_days,
        "reward_days_per_conversion": REFERRAL_REWARD_DAYS,
    }


@api_router.get("/referrals/lookup/{code}")
async def referral_lookup(code: str):
    """Public: lets a registering user verify a code is valid before submit."""
    user_doc = await db.users.find_one({"referral_code": code.upper().strip()}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="Código inválido")
    return {"valid": True, "referrer_name": user_doc.get("name", "").split(" ")[0] or "Alguém"}


# ---------- User CRUD Models ----------
class UserCreateIn(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6)
    role: Literal["admin", "seller"]
    phone: Optional[str] = ""
    whatsapp: Optional[str] = ""
    signature_url: Optional[str] = ""

class UserUpdateIn(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[Literal["admin", "seller"]] = None
    password: Optional[str] = Field(default=None, min_length=6)
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    signature_url: Optional[str] = None

class UserOut(BaseModel):
    id: str
    company_id: str
    name: str
    email: EmailStr
    role: str
    active: bool
    created_at: str
    phone: Optional[str] = ""
    whatsapp: Optional[str] = ""
    signature_url: Optional[str] = ""


# ---------- User CRUD Endpoints ----------
@api_router.get("/users", response_model=List[UserOut])
async def list_users(user=Depends(require_admin)):
    users = await db.users.find(
        {"company_id": user["company_id"], "deleted": {"$ne": True}},
        {
            "_id": 0,
            "id": 1,
            "company_id": 1,
            "name": 1,
            "email": 1,
            "role": 1,
            "active": 1,
            "created_at": 1,
            "phone": 1,
            "whatsapp": 1,
            "signature_url": 1
        }
    ).to_list(1000)
    for u in users:
        if "active" not in u:
            u["active"] = True
        if "role" not in u:
            u["role"] = "owner"
        if "created_at" not in u:
            u["created_at"] = ""
        u["phone"] = u.get("phone") or ""
        u["whatsapp"] = u.get("whatsapp") or ""
        u["signature_url"] = u.get("signature_url") or ""
    return users


@api_router.post("/users", response_model=UserOut)
async def create_user(data: UserCreateIn, user=Depends(require_admin)):
    email = data.email.lower().strip()
    
    # 1. Uniqueness of email globally (including deleted ones to prevent duplicate key collision on sparse/unique index)
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
        
    # 2. Hierarchy of creation
    creator_role = user.get("role", "owner")
    if creator_role == "admin" and data.role == "admin":
        raise HTTPException(status_code=403, detail="Permissão insuficiente: administradores só podem criar vendedores.")
        
    # 3. Insert user
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    new_user = {
        "id": user_id,
        "company_id": user["company_id"],
        "email": email,
        "name": data.name.strip(),
        "password_hash": hash_password(data.password),
        "role": data.role,
        "active": True,
        "created_at": now,
        "deleted": False,
        "verified_email": False,
        "verification_token": str(uuid.uuid4()),
        "verification_sent_at": now,
        "phone": data.phone or "",
        "whatsapp": data.whatsapp or "",
        "signature_url": data.signature_url or "",
    }
    await db.users.insert_one(new_user)
    
    # Audit log creation
    await log_audit(
        action="create",
        entity_type="user",
        entity_id=user_id,
        old_value=None,
        new_value=new_user,
        user_id=user["id"],
        company_id=user["company_id"]
    )
    
    new_user.pop("_id", None)
    new_user.pop("password_hash", None)
    return new_user


@api_router.put("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: str, data: UserUpdateIn, user=Depends(require_admin)):
    # 1. Ensure target user belongs to the same company and is not deleted
    target_user = await db.users.find_one({"id": user_id, "deleted": {"$ne": True}})
    if not target_user or target_user.get("company_id") != user["company_id"]:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
    # 2. Owner protection: Admin cannot edit Owner
    target_role = target_user.get("role", "owner")
    editor_role = user.get("role", "owner")
    
    if target_role == "owner" and user["id"] != user_id:
        raise HTTPException(status_code=403, detail="Permissão insuficiente: administradores não podem modificar o proprietário.")
        
    # 3. Owner role demotion protection
    if target_role == "owner" and data.role and data.role != "owner":
        raise HTTPException(status_code=400, detail="O cargo do proprietário não pode ser alterado.")
        
    # Protect founder/lifetime role demotion
    if target_user.get("founder") or target_user.get("lifetime"):
        if data.role and data.role != "owner":
            raise HTTPException(status_code=400, detail="O cargo do fundador deve ser sempre 'owner'.")
        
    # 4. Hierarchy check for admin editor
    if editor_role == "admin" and data.role == "admin" and target_role != "admin":
        raise HTTPException(status_code=403, detail="Permissão insuficiente: administradores não podem promover usuários a administrador.")

    # 5. Email uniqueness check
    update_data = {}
    if data.email:
        new_email = data.email.lower().strip()
        if new_email != target_user["email"]:
            existing = await db.users.find_one({"email": new_email})
            if existing:
                raise HTTPException(status_code=400, detail="E-mail já cadastrado")
            update_data["email"] = new_email
            
    if data.name:
        update_data["name"] = data.name.strip()
    if data.role:
        update_data["role"] = data.role
    if data.password:
        update_data["password_hash"] = hash_password(data.password)
    if data.phone is not None:
        update_data["phone"] = data.phone
    if data.whatsapp is not None:
        update_data["whatsapp"] = data.whatsapp
    if data.signature_url is not None:
        update_data["signature_url"] = data.signature_url
        
    if update_data:
        await db.users.update_one({"id": user_id}, {"$set": update_data})
        
    updated = await db.users.find_one(
        {"id": user_id},
        {
            "_id": 0,
            "id": 1,
            "company_id": 1,
            "name": 1,
            "email": 1,
            "role": 1,
            "active": 1,
            "created_at": 1,
            "phone": 1,
            "whatsapp": 1,
            "signature_url": 1
        }
    )
    if updated:
        if "active" not in updated:
            updated["active"] = True
        if "role" not in updated:
            updated["role"] = "owner"
        if "created_at" not in updated:
            updated["created_at"] = ""
        updated["phone"] = updated.get("phone") or ""
        updated["whatsapp"] = updated.get("whatsapp") or ""
        updated["signature_url"] = updated.get("signature_url") or ""
            
    # Audit log update
    await log_audit(
        action="update",
        entity_type="user",
        entity_id=user_id,
        old_value=target_user,
        new_value=updated,
        user_id=user["id"],
        company_id=user["company_id"]
    )
            
    return updated


@api_router.delete("/users/{user_id}")
async def delete_user(user_id: str, user=Depends(require_admin)):
    # 1. Ensure target user belongs to same company and is not deleted
    target_user = await db.users.find_one({"id": user_id, "deleted": {"$ne": True}})
    if not target_user or target_user.get("company_id") != user["company_id"]:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
    # 2. Cannot delete owner
    if target_user.get("role") == "owner" or target_user.get("founder") or target_user.get("lifetime"):
        raise HTTPException(status_code=400, detail="A conta do fundador ou proprietário não pode ser desativada.")
        
    # 3. Cannot delete self
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Você não pode desativar sua própria conta.")
        
    now = datetime.now(timezone.utc).isoformat()
    await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "active": False,
            "deleted": True,
            "deleted_at": now,
            "deleted_by": user["id"]
        }}
    )
    
    updated_user = await db.users.find_one({"id": user_id})
    
    # Audit log logical delete
    await log_audit(
        action="delete",
        entity_type="user",
        entity_id=user_id,
        old_value=target_user,
        new_value=updated_user,
        user_id=user["id"],
        company_id=user["company_id"]
    )
    
    return {"ok": True}


@api_router.patch("/users/{user_id}/activate")
async def activate_user(user_id: str, user=Depends(require_admin)):
    # 1. Ensure target user belongs to same company
    target_user = await db.users.find_one({"id": user_id})
    if not target_user or target_user.get("company_id") != user["company_id"]:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
    # 2. change active = True, undelete user
    await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "active": True,
            "deleted": False,
            "deleted_at": None,
            "deleted_by": None
        }}
    )
    
    updated = await db.users.find_one({"id": user_id})
    
    # Audit log user reactivation (update)
    await log_audit(
        action="update",
        entity_type="user",
        entity_id=user_id,
        old_value=target_user,
        new_value=updated,
        user_id=user["id"],
        company_id=user["company_id"]
    )
    
    return {"ok": True}


# ---------- Hardening, Security, Stability and Support (Fase 4) ----------

@api_router.post("/auth/forgot-password")
async def forgot_password(data: ForgotPasswordIn, request: Request):
    email = data.email.lower().strip()
    
    # Rate limit: 3 attempts per hour
    await check_rate_limit(action="forgot", identifier=email, limit=3, window_seconds=3600, request=request)
    
    user = await db.users.find_one({"email": email})
    if user and user.get("deleted") is not True:
        token = str(uuid.uuid4())
        expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": {"reset_token": token, "reset_token_expires_at": expires}}
        )
        # Log to audit (password reset request)
        await log_audit(
            action="request_password_reset",
            entity_type="user",
            entity_id=user["id"],
            old_value=None,
            new_value={"reset_token": token, "expires_at": expires},
            user_id=user["id"],
            company_id=user.get("company_id")
        )
        
    return {"success": True, "message": "Se o e-mail estiver cadastrado, um link de recuperação será enviado."}


@api_router.post("/auth/reset-password")
async def reset_password(data: ResetPasswordIn, request: Request):
    # Rate limit: 10 attempts per hour
    await check_rate_limit(action="reset", identifier=data.token, limit=10, window_seconds=3600, request=request)
    
    user = await db.users.find_one({
        "reset_token": data.token,
        "deleted": {"$ne": True}
    })
    if not user:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado")
        
    expires_str = user.get("reset_token_expires_at")
    if not expires_str:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado")
        
    try:
        expires = datetime.fromisoformat(expires_str)
        if datetime.now(timezone.utc) > expires:
            raise HTTPException(status_code=400, detail="Token inválido ou expirado")
    except Exception:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado")
        
    # Reset password
    await db.users.update_one(
        {"id": user["id"]},
        {
            "$set": {"password_hash": hash_password(data.new_password)},
            "$unset": {"reset_token": "", "reset_token_expires_at": ""}
        }
    )
    
    # Log audit
    await log_audit(
        action="reset_password",
        entity_type="user",
        entity_id=user["id"],
        old_value=None,
        new_value={"password_reset": True},
        user_id=user["id"],
        company_id=user.get("company_id")
    )
    
    return {"success": True, "message": "Senha redefinida com sucesso."}


@api_router.post("/auth/send-verification")
async def send_verification(data: SendVerificationIn, request: Request):
    email = data.email.lower().strip()
    
    user = await db.users.find_one({"email": email, "deleted": {"$ne": True}})
    if user:
        token = str(uuid.uuid4())
        sent_at = datetime.now(timezone.utc).isoformat()
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": {"verification_token": token, "verification_sent_at": sent_at}}
        )
        
        await log_audit(
            action="request_email_verification",
            entity_type="user",
            entity_id=user["id"],
            old_value=None,
            new_value={"verification_token": token, "sent_at": sent_at},
            user_id=user["id"],
            company_id=user.get("company_id")
        )
        
    return {"success": True, "message": "Se o e-mail estiver cadastrado, um link de verificação será enviado."}


@api_router.post("/auth/verify-email")
async def verify_email(data: VerifyEmailIn):
    user = await db.users.find_one({
        "verification_token": data.token,
        "deleted": {"$ne": True}
    })
    if not user:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado")
        
    sent_at_str = user.get("verification_sent_at")
    if not sent_at_str:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado")
        
    try:
        sent_at = datetime.fromisoformat(sent_at_str)
        # 24 hours expiry
        if datetime.now(timezone.utc) > sent_at + timedelta(hours=24):
            raise HTTPException(status_code=400, detail="Token inválido ou expirado")
    except Exception:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado")
        
    await db.users.update_one(
        {"id": user["id"]},
        {
            "$set": {"verified_email": True},
            "$unset": {"verification_token": "", "verification_sent_at": ""}
        }
    )
    
    # Log audit
    await log_audit(
        action="verify_email",
        entity_type="user",
        entity_id=user["id"],
        old_value=None,
        new_value={"verified_email": True},
        user_id=user["id"],
        company_id=user.get("company_id")
    )
    
    return {"success": True, "message": "E-mail verificado com sucesso."}


@api_router.post("/auth/logout")
async def logout(user=Depends(get_current_user)):
    await db.users.update_one({"id": user["id"]}, {"$set": {"session_id": None}})
    await log_audit(
        action="logout",
        entity_type="auth",
        entity_id=user["id"],
        old_value={"session_id": user.get("session_id")},
        new_value=None,
        user_id=user["id"],
        company_id=user.get("company_id")
    )
    return {"success": True, "message": "Desconectado com sucesso."}


@api_router.get("/admin/impersonate/{user_id}")
async def impersonate(user_id: str, request: Request, user=Depends(get_current_user)):
    role = user.get("role", "owner")
    is_master = user.get("is_master", False)
    
    if role != "owner" or not is_master:
        raise HTTPException(status_code=403, detail="Acesso negado: apenas administradores master podem personificar usuários.")
        
    target_user = await db.users.find_one({"id": user_id, "deleted": {"$ne": True}})
    if not target_user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
    # Generate new token for the impersonated user
    token = create_access_token(target_user["id"], target_user["email"], session_id=target_user.get("session_id"))
    
    # Audit log impersonation
    ip = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc).isoformat()
    await log_audit(
        action="impersonate",
        entity_type="user",
        entity_id=user_id,
        old_value={"admin_user_id": user["id"], "admin_email": user["email"]},
        new_value={
            "impersonated_user_id": target_user["id"],
            "impersonated_email": target_user["email"],
            "timestamp": now,
            "ip": ip
        },
        user_id=user["id"],
        company_id=user.get("company_id")
    )
    
    return {
        "success": True,
        "message": "Personificação realizada com sucesso",
        "data": {
            "token": token,
            "user": {
                "id": target_user["id"],
                "email": target_user["email"],
                "name": target_user["name"],
                "role": target_user.get("role", "owner"),
                "company_id": target_user.get("company_id")
            }
        }
    }


@api_router.delete("/clients/{client_id}")
async def delete_client(client_id: str, user=Depends(get_current_user)):
    client_doc = await db.clients.find_one({"id": client_id, "company_id": user["company_id"], "deleted": {"$ne": True}})
    if not client_doc:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
        
    now = datetime.now(timezone.utc).isoformat()
    await db.clients.update_one(
        {"id": client_id, "company_id": user["company_id"]},
        {"$set": {
            "deleted": True,
            "deleted_at": now,
            "deleted_by": user["id"]
        }}
    )
    
    updated_client = await db.clients.find_one({"id": client_id})
    
    # Audit log client deletion
    await log_audit(
        action="delete",
        entity_type="client",
        entity_id=client_id,
        old_value=client_doc,
        new_value=updated_client,
        user_id=user["id"],
        company_id=user["company_id"]
    )
    
    return {"ok": True}


@api_router.get("/audit")
async def list_audit_logs(user=Depends(require_admin)):
    company_id = user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="Empresa não vinculada")
        
    cursor = db.audit_logs.find({"company_id": company_id}, {"_id": 0}).sort("created_at", -1)
    logs = await cursor.to_list(1000)
    return {"success": True, "data": logs}


@api_router.get("/health")
async def health_check():
    try:
        await db.command("ping")
        db_status = "connected"
    except Exception:
        db_status = "disconnected"
        
    return {
        "status": "healthy" if db_status == "connected" else "unhealthy",
        "database": db_status,
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@api_router.get("/metrics")
async def get_metrics(user=Depends(require_owner)):
    users_count = await db.users.count_documents({})
    proposals_count = await db.proposals.count_documents({})
    products_count = await db.products.count_documents({})
    clients_count = await db.clients.count_documents({})
    companies_count = await db.companies.count_documents({})
    
    return {
        "success": True,
        "data": {
            "users_count": users_count,
            "proposals_count": proposals_count,
            "products_count": products_count,
            "clients_count": clients_count,
            "companies_count": companies_count
        }
    }


@api_router.get("/admin/backup-info")
async def get_backup_info(user=Depends(require_admin)):
    collections = ["users", "proposals", "products", "clients", "companies", "subscriptions", "audit_logs", "rate_limits"]
    counts = {}
    for coll in collections:
        counts[coll] = await db[coll].count_documents({})
        
    return {
        "success": True,
        "message": "Informações de backup obtidas com sucesso",
        "data": {
            "last_backup_simulation": datetime.now(timezone.utc).isoformat(),
            "collections": counts
        }
    }


@api_router.delete("/account")
async def delete_account(user=Depends(get_current_user)):
    if user.get("founder") or user.get("lifetime"):
        raise HTTPException(status_code=403, detail="A conta do fundador não pode ser excluída.")
        
    company_id = user.get("company_id")
    role = user.get("role", "owner")
    
    await log_audit(
        action="lgpd_delete",
        entity_type="account",
        entity_id=user["id"],
        old_value={"user_id": user["id"], "role": role, "company_id": company_id},
        new_value=None,
        user_id=user["id"],
        company_id=company_id
    )
    
    if role == "owner" and company_id:
        await db.companies.delete_many({"id": company_id})
        await db.users.delete_many({"company_id": company_id})
        await db.proposals.delete_many({"company_id": company_id})
        await db.products.delete_many({"company_id": company_id})
        await db.clients.delete_many({"company_id": company_id})
        await db.subscriptions.delete_many({"company_id": company_id})
        await db.subscriptions.delete_many({"user_id": user["id"]})
    else:
        await db.users.delete_one({"id": user["id"]})
        
    return {"success": True, "message": "Conta e dados associados excluídos com sucesso."}


@api_router.get("/account/export")
async def export_account_data(user=Depends(get_current_user)):
    company_id = user.get("company_id")
    
    proposals_list = []
    products_list = []
    clients_list = []
    company_doc = None
    subscription_doc = None
    
    if company_id:
        proposals_list = await db.proposals.find({"company_id": company_id}, {"_id": 0}).to_list(1000)
        products_list = await db.products.find({"company_id": company_id}, {"_id": 0}).to_list(1000)
        clients_list = await db.clients.find({"company_id": company_id}, {"_id": 0}).to_list(1000)
        company_doc = await db.companies.find_one({"id": company_id}, {"_id": 0})
        subscription_doc = await db.subscriptions.find_one({"company_id": company_id}, {"_id": 0})
        
    clean_user = dict(user)
    clean_user.pop("password_hash", None)
    clean_user.pop("reset_token", None)
    clean_user.pop("verification_token", None)
    
    return {
        "success": True,
        "message": "Dados exportados com sucesso",
        "data": {
            "user": clean_user,
            "company": company_doc,
            "proposals": proposals_list,
            "products": products_list,
            "clients": clients_list,
            "subscription": subscription_doc
        }
    }


@api_router.get("/public/plans")
async def public_plans():
    return {
        "success": True,
        "data": {
            "plans": [
                {"id": k, **v} for k, v in SUBSCRIPTION_PLANS.items()
            ],
            "free_monthly_quota": FREE_MONTHLY_QUOTA
        }
    }


@api_router.get("/public/features")
async def public_features():
    return {
        "success": True,
        "data": {
            "features": [
                "Criação de propostas rápidas",
                "Catálogo de produtos",
                "Histórico de clientes",
                "Modo Suporte administrative",
                "Auditoria completa de segurança",
                "LGPD compliant"
            ]
        }
    }


# ---------- Bling OAuth (connection only; no synchronization occurs here) ----------
def _bling_configuration() -> BlingOAuthConfiguration:
    return BlingOAuthConfiguration.from_environment()


@api_router.get("/integrations/bling/status")
async def bling_connection_status(user: dict = Depends(get_current_user)):
    company_id = _safe_company_id(user)
    try:
        _bling_configuration()
    except BlingOAuthError:
        return {"configured": False, "connected": False}
    credential = await db.integration_credentials.find_one(
        {"company_id": company_id, "provider": "bling"}, {"_id": 0, "connected_at": 1}
    )
    return {"configured": True, "connected": bool(credential), "connected_at": credential.get("connected_at") if credential else None}


@api_router.post("/integrations/bling/connect")
async def begin_bling_connection(user: dict = Depends(get_current_user)):
    try:
        configuration = _bling_configuration()
    except BlingOAuthError as exc:
        raise HTTPException(status_code=503, detail="Bling integration is not configured") from exc

    state = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    await db.integration_oauth_states.insert_one({
        "state_hash": hashlib.sha256(state.encode()).hexdigest(),
        "provider": "bling",
        "company_id": _safe_company_id(user),
        "user_id": user["id"],
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=10)).isoformat(),
        "consumed_at": None,
    })
    return {"authorization_url": configuration.authorization_url(state)}


async def _bling_read(company_id: str, path: str, params: dict[str, str | int] | None = None) -> dict:
    configuration = _bling_configuration()
    credential = await db.integration_credentials.find_one({"company_id": company_id, "provider": "bling"})
    if not credential:
        raise HTTPException(status_code=409, detail="Bling connection is required")
    access_token = configuration.decrypt(credential["access_token_encrypted"])
    try:
        return await asyncio.to_thread(configuration.get_json, path, access_token, params)
    except BlingApiError as exc:
        if exc.status_code != 401:
            if exc.status_code == 403:
                raise HTTPException(status_code=403, detail="The Bling application does not have this read permission") from exc
            raise HTTPException(status_code=502, detail="Bling could not provide the requested preview") from exc
    refresh_token = configuration.decrypt(credential["refresh_token_encrypted"])
    try:
        refreshed = await asyncio.to_thread(configuration.refresh_access_token, refresh_token)
        await db.integration_credentials.update_one(
            {"company_id": company_id, "provider": "bling"},
            {"$set": {"access_token_encrypted": configuration.encrypt(refreshed["access_token"]), "refresh_token_encrypted": configuration.encrypt(refreshed["refresh_token"]), "expires_in": refreshed.get("expires_in"), "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        return await asyncio.to_thread(configuration.get_json, path, refreshed["access_token"], params)
    except BlingOAuthError as exc:
        raise HTTPException(status_code=502, detail="Bling authorization needs to be renewed") from exc


def _bling_preview_record(record: dict) -> dict:
    contact = record.get("contato") if isinstance(record.get("contato"), dict) else {}
    client = record.get("cliente") if isinstance(record.get("cliente"), dict) else {}
    situation = record.get("situacao")
    return {
        "external_id": str(record.get("id", "")),
        "number": str(record.get("numero") or record.get("numeroOrcamento") or record.get("id", "")),
        "date": record.get("data") or record.get("dataEmissao"),
        "total": record.get("total") or record.get("valorTotal") or 0,
        "client_name": contact.get("nome") or client.get("nome") or "Cliente não informado",
        "status": situation.get("valor") if isinstance(situation, dict) else (situation or ""),
    }


@api_router.get("/integrations/bling/commercial-proposals")
async def preview_bling_commercial_proposals(limit: int = Query(default=25, ge=1, le=100), user: dict = Depends(get_current_user)):
    try:
        payload = await _bling_read(_safe_company_id(user), "/propostas-comerciais", {"limite": limit})
    except BlingOAuthError as exc:
        raise HTTPException(status_code=503, detail="Bling integration is not configured") from exc
    records = payload.get("data", [])
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list):
        records = []
    return {"mode": "PREVIEW", "total": len(records), "proposals": [_bling_preview_record(record) for record in records if isinstance(record, dict)]}


@api_router.get("/integrations/bling/callback", response_class=HTMLResponse)
async def complete_bling_connection(code: str | None = None, state: str | None = None, error: str | None = None):
    if error or not code or not state:
        return HTMLResponse("<h1>Conexão Bling não concluída</h1><p>Retorne ao Proposta Já e tente novamente.</p>", status_code=400)
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    oauth_state = await db.integration_oauth_states.find_one({"state_hash": state_hash, "provider": "bling"})
    now = datetime.now(timezone.utc).isoformat()
    if not oauth_state or oauth_state.get("consumed_at") or oauth_state.get("expires_at", "") < now:
        return HTMLResponse("<h1>Conexão Bling não concluída</h1><p>Esta autorização expirou. Retorne ao Proposta Já e tente novamente.</p>", status_code=400)
    try:
        configuration = _bling_configuration()
        tokens = await asyncio.to_thread(configuration.exchange_code, code)
    except BlingOAuthError:
        return HTMLResponse("<h1>Conexão Bling não concluída</h1><p>Não foi possível concluir a autorização. Retorne ao Proposta Já e tente novamente.</p>", status_code=502)

    connected_at = datetime.now(timezone.utc).isoformat()
    await db.integration_credentials.update_one(
        {"company_id": oauth_state["company_id"], "provider": "bling"},
        {"$set": {"company_id": oauth_state["company_id"], "provider": "bling", "access_token_encrypted": configuration.encrypt(tokens["access_token"]), "refresh_token_encrypted": configuration.encrypt(tokens["refresh_token"]), "expires_in": tokens.get("expires_in"), "connected_at": connected_at, "updated_at": connected_at}},
        upsert=True,
    )
    await db.integration_oauth_states.update_one({"_id": oauth_state["_id"]}, {"$set": {"consumed_at": connected_at}})
    return HTMLResponse("<h1>Bling conectado com sucesso</h1><p>Você pode fechar esta janela e voltar ao Proposta Já.</p>")


# ---------- Register router + middleware ----------
api_router.include_router(create_integration_hub_router(lambda: db, get_current_user, _safe_company_id, create_default_registry()))
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)  # reload 3


# ---------- Exception Handlers (Fase 4 Global Middleware) ----------
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.error(f"HTTPException: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail,
            "detail": exc.detail,
            "data": None
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    logger.error(f"Validation Error: {errors}")
    msg = "Erro de validação de dados"
    if errors:
        msg = f"Erro de validação: {errors[0].get('msg')} no campo {'.'.join(str(loc) for loc in errors[0].get('loc', []))}"
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": msg,
            "detail": errors,
            "data": None
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Internal Server Error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Erro interno do servidor",
            "detail": "Erro interno do servidor",
            "data": None
        }
    )
