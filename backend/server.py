from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import uuid
import logging
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request
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


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
        "type": "access",
    }
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
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    return user


async def get_user_plan_state(user_id: str) -> dict:
    """Returns {plan, pro_until, month_count, month_quota, is_pro, is_trial}."""
    sub = await db.subscriptions.find_one({"user_id": user_id}, {"_id": 0})
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    month_count = await db.proposals.count_documents(
        {"user_id": user_id, "created_at": {"$gte": month_start.isoformat()}}
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


# ---------- Models ----------
class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6)
    referral_code: Optional[str] = None


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


class Product(BaseModel):
    name: str
    quantity: float
    price: float


class CatalogProductIn(BaseModel):
    code: str
    name: str
    description: Optional[str] = ""
    price: float
    unit: str = "UN"


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


ProposalStatus = Literal["aberto", "perdido", "realizado"]


class ProposalIn(BaseModel):
    client_name: str
    client_document: str
    client_phone: str
    products: List[Product]
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
    await db.proposals.create_index("user_id")
    await db.proposals.create_index("created_at")
    await db.subscriptions.create_index("user_id", unique=True)
    await db.payment_transactions.create_index("session_id", unique=True)
    await db.products.create_index("company_id")

    await db.products.create_index(
        [("company_id", 1), ("code", 1)],
        unique=True
    )
    await ensure_company_ids()


@app.on_event("shutdown")
async def on_shutdown():
    client.close()


# ---------- Auth routes ----------
@api_router.post("/auth/register", response_model=AuthOut)
async def register(data: RegisterIn):
    email = data.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email já cadastrado")
    user_id = str(uuid.uuid4())
    referral_code = make_referral_code(user_id)
    now = datetime.now(timezone.utc)

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
            {"$set": {"company_id": company_id, "role": "admin"}},
        )
        doc["company_id"] = company_id
        doc["role"] = "admin"

    # Grant 7-day Pro trial automatically
    trial_until = now + timedelta(days=TRIAL_DAYS)
    await db.subscriptions.insert_one({
        "user_id": user_id,
        "plan": "pro",
        "last_plan_id": "trial",
        "pro_until": trial_until.isoformat(),
        "trial_used": True,
        "updated_at": now.isoformat(),
    })

    token = create_access_token(user_id, email)
    return {"token": token, "user": {"id": user_id, "email": email, "name": data.name}}


@api_router.post("/auth/login", response_model=AuthOut)
async def login(data: LoginIn):
    email = data.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email ou senha inválidos")
    token = create_access_token(user["id"], email)
    return {
        "token": token,
        "user": {"id": user["id"], "email": email, "name": user["name"]},
    }


@api_router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    plan_state = await get_user_plan_state(user["id"])
    return {**user, **plan_state}


# ---------- Company profile ----------
@api_router.get("/company")
async def get_company(user=Depends(get_current_user)):
    doc = await db.companies.find_one({"user_id": user["id"]}, {"_id": 0})
    if not doc:
        return {
            "user_id": user["id"],
            "company_name": "",
            "cnpj": "",
            "phone": "",
            "email": user.get("email", ""),
            "address": "",
            "logo_base64": "",
        }
    await get_company_id(user["id"])
    return doc


@api_router.put("/company")
async def update_company(data: CompanyIn, user=Depends(get_current_user)):
    payload = data.dict()
    payload["user_id"] = user["id"]
    await db.companies.update_one(
        {"user_id": user["id"]}, {"$set": payload}, upsert=True
    )
    await get_company_id(user["id"])
    doc = await db.companies.find_one({"user_id": user["id"]}, {"_id": 0})
    return doc
    
# ---------- Products Catalog ----------

@api_router.get("/products")
async def list_products(user=Depends(get_current_user)):
    company_id = user.get("company_id")

    if not company_id:
        return []

    items = await db.products.find(
        {
            "company_id": company_id,
            "active": True,
        },
        {"_id": 0},
    ).sort("name", 1).to_list(5000)

    return items


@api_router.post("/products")
async def create_product(
    data: CatalogProductIn,
    user=Depends(get_current_user),
):
    company_id = user.get("company_id")

    if not company_id:
        raise HTTPException(
            status_code=400,
            detail="Empresa não vinculada"
        )

    doc = {
        "id": str(uuid.uuid4()),
        "company_id": company_id,
        "code": data.code.strip().upper(),
        "name": data.name.strip(),
        "description": data.description.strip(),
        "price": float(data.price),
        "unit": data.unit.strip().upper(),
        "active": True,
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    await db.products.insert_one(doc)

    doc.pop("_id", None)

    return doc    


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

    pid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    products = [p.dict() for p in data.products]
    doc = {
        "id": pid,
        "user_id": user["id"],
        "client_name": data.client_name,
        "client_document": data.client_document,
        "client_phone": data.client_phone,
        "products": products,
        "shipping_deadline": data.shipping_deadline,
        "notes": data.notes or "",
        "discount": float(data.discount or 0),
        "payment_terms": data.payment_terms or "",
        "validity_days": int(data.validity_days or 15),
        "images": data.images or [],
        "status": "aberto",
        "lost_reason": "",
        "total": _proposal_total(products, data.discount or 0),
        "created_at": now,
        "updated_at": now,
        "last_reminded_at": None,
    }
    await db.proposals.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.get("/proposals")
async def list_proposals(
    status: Optional[str] = None,
    user=Depends(get_current_user),
):
    q = {"user_id": user["id"]}
    if status and status in ("aberto", "perdido", "realizado"):
        q["status"] = status
    items = await db.proposals.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return items


@api_router.get("/proposals/{pid}")
async def get_proposal(pid: str, user=Depends(get_current_user)):
    doc = await db.proposals.find_one({"id": pid, "user_id": user["id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
    return doc


@api_router.put("/proposals/{pid}")
async def update_proposal(pid: str, data: ProposalIn, user=Depends(get_current_user)):
    products = [p.dict() for p in data.products]
    update = {
        "client_name": data.client_name,
        "client_document": data.client_document,
        "client_phone": data.client_phone,
        "products": products,
        "shipping_deadline": data.shipping_deadline,
        "notes": data.notes or "",
        "discount": float(data.discount or 0),
        "payment_terms": data.payment_terms or "",
        "validity_days": int(data.validity_days or 15),
        "images": data.images or [],
        "total": _proposal_total(products, data.discount or 0),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    res = await db.proposals.update_one(
        {"id": pid, "user_id": user["id"]}, {"$set": update}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
    doc = await db.proposals.find_one({"id": pid}, {"_id": 0})
    return doc


@api_router.patch("/proposals/{pid}/status")
async def change_status(pid: str, data: StatusUpdate, user=Depends(get_current_user)):
    if data.status == "perdido" and not (data.lost_reason and data.lost_reason.strip()):
        raise HTTPException(status_code=400, detail="Motivo da perda é obrigatório")
    update = {
        "status": data.status,
        "lost_reason": data.lost_reason or "" if data.status == "perdido" else "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    res = await db.proposals.update_one(
        {"id": pid, "user_id": user["id"]}, {"$set": update}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
    doc = await db.proposals.find_one({"id": pid}, {"_id": 0})
    return doc


@api_router.post("/proposals/{pid}/duplicate")
async def duplicate_proposal(pid: str, user=Depends(get_current_user)):
    state = await get_user_plan_state(user["id"])
    if not state["is_pro"] and state["month_count"] >= FREE_MONTHLY_QUOTA:
        raise HTTPException(
            status_code=402,
            detail=f"Você atingiu o limite de {FREE_MONTHLY_QUOTA} propostas este mês.",
        )
    orig = await db.proposals.find_one({"id": pid, "user_id": user["id"]}, {"_id": 0})
    if not orig:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
    now = datetime.now(timezone.utc).isoformat()
    new_id = str(uuid.uuid4())
    clone = {
        **orig,
        "id": new_id,
        "status": "aberto",
        "lost_reason": "",
        "created_at": now,
        "updated_at": now,
        "last_reminded_at": None,
    }
    clone.pop("_id", None)
    await db.proposals.insert_one(clone)
    clone.pop("_id", None)
    return clone


@api_router.delete("/proposals/{pid}")
async def delete_proposal(pid: str, user=Depends(get_current_user)):
    res = await db.proposals.delete_one({"id": pid, "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
    return {"ok": True}
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
    cursor = db.proposals.find({"user_id": user["id"]}, {"_id": 0})
    items = await cursor.to_list(5000)
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    total_open = sum(1 for p in items if p["status"] == "aberto")
    total_won = sum(1 for p in items if p["status"] == "realizado")
    total_lost = sum(1 for p in items if p["status"] == "perdido")

    month_won_value = 0.0
    open_value = 0.0
    stale_count = 0
    for p in items:
        try:
            created = datetime.fromisoformat(p["created_at"])
        except Exception:
            continue
        if p["status"] == "aberto":
            open_value += p.get("total", 0)
            if (now - created).days >= 3:
                stale_count += 1
        if p["status"] == "realizado" and created >= month_start:
            month_won_value += p.get("total", 0)

    plan_state = await get_user_plan_state(user["id"])
    return {
        "open_count": total_open,
        "won_count": total_won,
        "lost_count": total_lost,
        "open_value": round(open_value, 2),
        "month_won_value": round(month_won_value, 2),
        "stale_count": stale_count,
        **plan_state,
    }


# ---------- Clients history ----------
@api_router.get("/clients")
async def list_clients(user=Depends(get_current_user)):
    pipeline = [
        {"$match": {"user_id": user["id"]}},
        {"$sort": {"created_at": -1}},
        {
            "$group": {
                "_id": "$client_document",
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
        doc.pop("_id", None)
        results.append(doc)
    return results


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

    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$set": {
            "payment_status": payment_status,
            "status": status_value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )

    if payment_status == "paid" and tx.get("payment_status") != "paid":
        await _activate_subscription(user["id"], tx["plan"])

    state = await get_user_plan_state(user["id"])
    return {"payment_status": payment_status, "status": status_value, **state}


async def _activate_subscription(user_id: str, plan_id: str):
    plan = SUBSCRIPTION_PLANS.get(plan_id)
    if not plan:
        return
    now = datetime.now(timezone.utc)
    existing = await db.subscriptions.find_one({"user_id": user_id}, {"_id": 0})
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
    await db.subscriptions.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "plan": "pro",
            "last_plan_id": plan_id,
            "pro_until": new_pro_until.isoformat(),
            "updated_at": now.isoformat(),
        }},
        upsert=True,
    )

    # Reward referrer on first paid subscription (one-time)
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if user and user.get("referred_by") and not user.get("referral_rewarded"):
        ref_id = user["referred_by"]
        await db.users.update_one({"id": user_id}, {"$set": {"referral_rewarded": True}})
        await _add_pro_days(ref_id, REFERRAL_REWARD_DAYS, source="referral")


async def _add_pro_days(user_id: str, days: int, source: str = "bonus"):
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
                await db.payment_transactions.update_one(
                    {"session_id": session_id},
                    {"$set": {"payment_status": "paid", "status": "complete"}},
                )
                await _activate_subscription(tx["user_id"], tx["plan"])
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
logger = logging.getLogger(__name__)
