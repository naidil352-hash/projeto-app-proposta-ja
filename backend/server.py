from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env", override=True)

import os
import uuid
import logging
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr

import stripe

import cloudinary
import cloudinary.uploader

from fastapi import UploadFile, File

# ---------- DB ----------
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]


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


async def get_user_plan_state(user_id: str) -> dict:
    """Returns {plan, pro_until, month_count, month_quota, is_pro, is_trial}."""
    user = await db.users.find_one({"id": user_id})
    company_id = user.get("company_id") if user else None
    
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
        }
    
    # Resolve company_id and owner_id for fallback
    owner_id = user_id
    if company_id:
        company = await db.companies.find_one({"id": company_id})
        if company and company.get("user_id"):
            owner_id = company["user_id"]
            
    sub = None
    if company_id:
        # Priority 1: Query subscription by company_id
        sub = await db.subscriptions.find_one({"company_id": company_id}, {"_id": 0})
        
    if not sub:
        # Priority 2: Fallback to owner's user_id (legado)
        sub = await db.subscriptions.find_one({"user_id": owner_id}, {"_id": 0})
        
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    
    # Count proposals at the company level
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
        "month_quota": None if is_pro else FREE_MONTHLY_QUOTA,
        "is_pro": is_pro,
        "is_trial": is_trial,
        "subscription_status": "active" if is_pro else "inactive",
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


async def resolve_client_id(company_id: str, name: str, document: str, phone: str, user_id: str | None = None) -> str:
    # Restringe a busca por company_id e document
    client_doc = await db.clients.find_one({"company_id": company_id, "document": document})
    if client_doc:
        # If client doc was soft deleted, reactivate it!
        if client_doc.get("deleted") is True:
            await db.clients.update_one({"id": client_doc["id"]}, {"$set": {"deleted": False, "updated_at": datetime.now(timezone.utc).isoformat()}})
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
    client_id = f"cli_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc).isoformat()
    new_client = {
        "id": client_id,
        "company_id": company_id,
        "name": name,
        "document": document,
        "phone": phone,
        "email": "",
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
    p["seller_role"] = p.get("seller_role") or ""
    # Ensure acceptance fields exist
    p["acceptance_status"] = p.get("acceptance_status") or "pending"
    p["accept_name"] = p.get("accept_name") or ""
    p["accept_document"] = p.get("accept_document") or ""
    p["accept_role"] = p.get("accept_role") or ""
    p["accept_date"] = p.get("accept_date") or ""
    p["accept_ip"] = p.get("accept_ip") or ""
    p["accept_device"] = p.get("accept_device") or ""
    return p


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


class ClientUpdateIn(BaseModel):
    name: Optional[str] = None
    document: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


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


ProposalStatus = Literal["aberto", "qualificado", "negociacao", "aprovado", "perdido", "realizado"]


class ProposalIn(BaseModel):
    client_name: str
    client_document: str
    client_phone: str
    products: List[ProposalItemIn]
    shipping_deadline: str
    notes: Optional[str] = ""
    discount: Optional[float] = 0.0
    payment_terms: Optional[str] = ""
    validity_days: Optional[int] = 15
    images: Optional[List[str]] = []


class StatusUpdate(BaseModel):
    status: ProposalStatus
    lost_reason: Optional[str] = None


class CheckoutIn(BaseModel):
    plan: str  # pro_monthly | pro_yearly


TRIAL_DAYS = 7
REFERRAL_REWARD_DAYS = 30


def make_referral_code(user_id: str) -> str:
    """Short, readable referral code from user_id."""
    return user_id.replace("-", "")[:8].upper()


# ---------- Startup ----------
@app.on_event("startup")
async def on_startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("referral_code", unique=True, sparse=True)
    await db.users.create_index("company_id", sparse=True)
    await db.users.create_index("role", sparse=True)
    await db.users.create_index("active", sparse=True)
    await db.proposals.create_index("id", unique=True)
    await db.proposals.create_index([("company_id", 1), ("created_at", -1)])
    await db.proposals.create_index([
        ("company_id", 1),
        ("user_id", 1),
        ("status", 1),
        ("created_at", -1),
    ])
    await db.proposals.create_index([
        ("company_id", 1),
        ("status", 1),
        ("created_at", -1),
    ])
    await db.proposals.create_index([
        ("user_id", 1),
        ("created_at", -1),
    ])
    await db.subscriptions.create_index("user_id", unique=True)
    await db.payment_transactions.create_index("session_id", unique=True)
    await db.products.create_index("company_id")

    await db.products.create_index(
        [("company_id", 1), ("code", 1)],
        unique=True
    )

    # Clients indexes
    await db.clients.create_index("company_id")
    await db.clients.create_index("owner_user_id")
    await db.clients.create_index("created_by")
    try:
        await db.clients.drop_index("company_id_1_client_document_1")
    except Exception:
        pass
    await db.clients.create_index(
        [("company_id", 1), ("document", 1)],
        unique=True
    )

    # Rate limits indexes
    await db.rate_limits.create_index("key")
    await db.rate_limits.create_index("timestamp")
    
    # Audit logs indexes
    await db.audit_logs.create_index("company_id")
    await db.audit_logs.create_index("user_id")
    await db.audit_logs.create_index("created_at")

    # Users tokens indexes
    await db.users.create_index("verification_token", sparse=True)
    await db.users.create_index("reset_token", sparse=True)
    await db.users.create_index("session_id", sparse=True)

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


@app.on_event("shutdown")
async def on_shutdown():
    client.close()


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
    # Enforce free tier quota
    state = await get_user_plan_state(user["id"])
    if not state["is_pro"] and state["month_count"] >= FREE_MONTHLY_QUOTA:
        raise HTTPException(
            status_code=402,
            detail=f"Você atingiu o limite de {FREE_MONTHLY_QUOTA} propostas do plano grátis este mês. Faça upgrade para Pro para propostas ilimitadas.",
        )

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
        user_id=user["id"]
    )

    pid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": pid,
        "user_id": user["id"],
        "company_id": user["company_id"],
        "seller_name": user["name"],  # Historical snapshot of seller name
        "seller_email": user.get("email", ""),
        "seller_phone": user.get("phone", user.get("telefone", "")),
        "seller_role": user.get("role", "owner"),
        "client_id": client_id,
        "client_name": data.client_name,
        "client_document": data.client_document,
        "client_phone": data.client_phone,
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
        "deleted": False
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
        user_id=user["id"]
    )

    update = {
        "client_id": client_id,
        "client_name": data.client_name,
        "client_document": data.client_document,
        "client_phone": data.client_phone,
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
    role = user.get("role", "owner")
    orig = await db.proposals.find_one({"id": pid, "deleted": {"$ne": True}}, {"_id": 0})
    if not orig:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    belongs_to_company = orig.get("company_id") == user["company_id"] or orig.get("user_id") == user["id"]
    if not belongs_to_company:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    if role == "seller" and orig.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
    state = await get_user_plan_state(user["id"])
    if not state["is_pro"] and state["month_count"] >= FREE_MONTHLY_QUOTA:
        raise HTTPException(
            status_code=402,
            detail=f"Você atingiu o limite de {FREE_MONTHLY_QUOTA} propostas este mês.",
        )
    now = datetime.now(timezone.utc).isoformat()
    new_id = str(uuid.uuid4())
    
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
        "user_id": user["id"],
        "company_id": user["company_id"],
        "seller_name": user["name"],
        "seller_email": user.get("email", ""),
        "seller_phone": user.get("phone", user.get("telefone", "")),
        "seller_role": user.get("role", "owner"),
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
        
    await db.proposals.update_one({"id": pid}, {"$set": update})
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


@api_router.get("/public/proposals/{pid}")
async def get_public_proposal(pid: str):
    doc = await db.proposals.find_one({"id": pid, "deleted": {"$ne": True}}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
        
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
            created = datetime.fromisoformat(p["created_at"])
        except Exception:
            continue
        val = p.get("grand_total", p.get("total", 0.0))
        if p["status"] == "aberto":
            open_value += val
            if (now - created).days >= 3:
                stale_count += 1
        if p["status"] in ("realizado", "aprovado") and created >= month_start:
            month_won_value += val

    # BLOCO 3 fields
    total_proposals = len(items)
    approved_proposals = total_won
    pending_proposals = total_open
    rejected_proposals = total_lost
    conversion_rate = round((approved_proposals / total_proposals * 100), 2) if total_proposals > 0 else 0.0
    total_revenue = sum(p.get("grand_total", p.get("total", 0.0)) for p in items if p["status"] in ("realizado", "aprovado"))

    # BLOCO 8 fields
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
            created_dt = datetime.fromisoformat(created_str)
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
    # Retrieve documents of soft-deleted clients to exclude them
    deleted_clients = await db.clients.find({"company_id": user["company_id"], "deleted": True}).to_list(10000)
    deleted_docs = {c["document"] for c in deleted_clients}

    pipeline = [
        {"$match": {"user_id": user["id"], "deleted": {"$ne": True}}},
        {"$sort": {"created_at": -1}},
        {
            "$group": {
                "_id": "$client_document",
                "client_id": {"$first": "$client_id"},
                "client_name": {"$first": "$client_name"},
                "client_document": {"$first": "$client_document"},
                "client_phone": {"$first": "$client_phone"},
                "last_proposal_at": {"$first": "$created_at"},
                "proposals_count": {"$sum": 1},
                "total_value": {"$sum": "$total"},
            }
        },
        {"$sort": {"last_proposal_at": -1}},
    ]
    results = []
    async for doc in db.proposals.aggregate(pipeline):
        # Exclude client if it has been soft deleted
        if doc.get("client_document") not in deleted_docs:
            doc.pop("_id", None)
            results.append(doc)
    return results


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

class UserUpdateIn(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[Literal["admin", "seller"]] = None
    password: Optional[str] = Field(default=None, min_length=6)

class UserOut(BaseModel):
    id: str
    company_id: str
    name: str
    email: EmailStr
    role: str
    active: bool
    created_at: str


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
            "created_at": 1
        }
    ).to_list(1000)
    for u in users:
        if "active" not in u:
            u["active"] = True
        if "role" not in u:
            u["role"] = "owner"
        if "created_at" not in u:
            u["created_at"] = ""
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
        "verification_sent_at": now
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
            "created_at": 1
        }
    )
    if updated:
        if "active" not in updated:
            updated["active"] = True
        if "role" not in updated:
            updated["role"] = "owner"
        if "created_at" not in updated:
            updated["created_at"] = ""
            
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


# ---------- Register router + middleware ----------
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
