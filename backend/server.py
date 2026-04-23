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
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr


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


# ---------- Models ----------
class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6)


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
    logo_base64: Optional[str] = ""  # data URI or raw base64


class Product(BaseModel):
    name: str
    quantity: float
    price: float


ProposalStatus = Literal["aberto", "perdido", "realizado"]


class ProposalIn(BaseModel):
    client_name: str
    client_document: str  # CNPJ ou CPF
    client_phone: str
    products: List[Product]
    shipping_deadline: str  # prazo de embarque (texto livre / data)
    notes: Optional[str] = ""


class StatusUpdate(BaseModel):
    status: ProposalStatus
    lost_reason: Optional[str] = None


# ---------- Startup ----------
@app.on_event("startup")
async def on_startup():
    await db.users.create_index("email", unique=True)
    await db.proposals.create_index("user_id")
    await db.proposals.create_index("created_at")


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
    doc = {
        "id": user_id,
        "email": email,
        "name": data.name,
        "password_hash": hash_password(data.password),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(doc)
    # Initialize empty company profile
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
    return user


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
    return doc


@api_router.put("/company")
async def update_company(data: CompanyIn, user=Depends(get_current_user)):
    payload = data.dict()
    payload["user_id"] = user["id"]
    await db.companies.update_one(
        {"user_id": user["id"]}, {"$set": payload}, upsert=True
    )
    doc = await db.companies.find_one({"user_id": user["id"]}, {"_id": 0})
    return doc


# ---------- Proposals ----------
def _proposal_total(products: List[dict]) -> float:
    return round(sum((p.get("quantity", 0) or 0) * (p.get("price", 0) or 0) for p in products), 2)


@api_router.post("/proposals")
async def create_proposal(data: ProposalIn, user=Depends(get_current_user)):
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
        "status": "aberto",
        "lost_reason": "",
        "total": _proposal_total(products),
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
        "total": _proposal_total(products),
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


@api_router.delete("/proposals/{pid}")
async def delete_proposal(pid: str, user=Depends(get_current_user)):
    res = await db.proposals.delete_one({"id": pid, "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
    return {"ok": True}


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

    return {
        "open_count": total_open,
        "won_count": total_won,
        "lost_count": total_lost,
        "open_value": round(open_value, 2),
        "month_won_value": round(month_won_value, 2),
        "stale_count": stale_count,
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


@api_router.get("/")
async def root():
    return {"service": "proposta-ja", "status": "ok"}


# ---------- Register router + middleware ----------
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
